"""LLM 网关：按配置选择供应商，结构化输出解析与重试，结果对齐。"""
import json

from sqlalchemy.orm import Session

from ...models import LLMProvider as LLMProviderRow
from ...utils.naming import safe_field_name
from ...utils.security import decrypt
from ..typemap import DATA_TYPES, WIDGETS, coerce_value, default_widget
from .base import LLMError, LLMProvider
from .claude import ClaudeProvider
from .openai_compat import OpenAICompatProvider
from .prompts import ANALYZE_SYSTEM, JUDGE_SYSTEM, VISION_SYSTEM, build_analyze_prompt, build_judge_prompt, build_vision_prompt


def build_provider(row: LLMProviderRow) -> LLMProvider:
    api_key = decrypt(row.api_key_enc) if row.api_key_enc else ""
    if row.type == "claude":
        return ClaudeProvider(row.base_url, api_key, row.model, row.vision_model)
    return OpenAICompatProvider(row.base_url, api_key, row.model, row.vision_model)


def get_default_provider(db: Session) -> LLMProvider:
    row = (
        db.query(LLMProviderRow)
        .filter(LLMProviderRow.enabled.is_(True))
        .order_by(LLMProviderRow.is_default.desc(), LLMProviderRow.id)
        .first()
    )
    if not row:
        raise LLMError("尚未配置可用的大模型服务，请先到「模型设置」中添加")
    return build_provider(row)


def extract_json(text: str) -> dict:
    """从模型输出中提取 JSON 对象（容忍 markdown 代码块和前后废话）。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end:
            return json.loads(text[start:end + 1])
        raise


def align_columns(result: dict, headers: list[str]) -> dict:
    """把 LLM 输出对齐到真实表头：补遗漏列、清洗非法值，保证前端拿到完整可用的结构。"""
    cols_in = result.get("columns") or []
    by_src: dict[str, dict] = {}
    for c in cols_in:
        if isinstance(c, dict):
            by_src.setdefault(str(c.get("source_header") or ""), c)

    out, used = [], set()
    for i, h in enumerate(headers):
        c = by_src.get(h) or {}
        dt = c.get("data_type") if c.get("data_type") in DATA_TYPES else "varchar"
        widget = c.get("widget") if c.get("widget") in WIDGETS else default_widget(dt)
        try:
            confidence = float(c.get("confidence", 0.8 if c else 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        out.append({
            "source_header": h,
            "field_name": safe_field_name(str(c.get("field_name") or ""), used, i + 1),
            "label": str(c.get("label") or h),
            "data_type": dt,
            "length": int(c.get("length") or 255),
            "nullable": bool(c.get("nullable", True)),
            "widget": widget,
            "options": c.get("options") if isinstance(c.get("options"), dict) else {},
            "confidence": round(confidence, 2),
        })
    result["columns"] = out
    return result


def analyze_excel(db: Session, headers: list[str], columns: list[dict]) -> dict:
    """调 LLM 分析 Excel 结构；JSON 解析失败时把错误回喂重试一次。"""
    provider = get_default_provider(db)
    prompt = build_analyze_prompt(headers, columns)
    last_err: Exception | None = None
    for attempt in range(2):
        if attempt == 0:
            current = prompt
        else:
            current = (
                f"你上次的输出无法解析为合法 JSON，错误：{last_err}。"
                "请重新输出，只输出 JSON。\n\n原始任务：\n" + prompt
            )
        try:
            raw = provider.complete(current, system=ANALYZE_SYSTEM)
            data = extract_json(raw)
            if not isinstance(data.get("columns"), list):
                raise ValueError("输出缺少 columns 数组")
            return align_columns(data, headers)
        except LLMError:
            raise
        except Exception as e:
            last_err = e
    raise LLMError(f"模型输出解析失败：{last_err}")


def _serialize(v):
    from datetime import date, datetime
    from decimal import Decimal
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def recognize_form(db: Session, images: list[bytes], fields: list, current: dict) -> tuple[dict, str]:
    """多模态识别表单填写建议。返回 (结构化结果, 模型原始输出)。
    识别值会按字段类型转换，无法转换的字段丢弃并在 notes 中说明。"""
    provider = get_default_provider(db)
    field_dicts = [
        {"field_name": f.field_name, "label": f.label, "data_type": f.data_type, "options": f.options or {}}
        for f in fields
    ]
    prompt = build_vision_prompt(field_dicts, current or {})

    last_err: Exception | None = None
    data, raw = None, ""
    for attempt in range(2):
        if attempt == 0:
            current_prompt = prompt
        else:
            current_prompt = (
                f"你上次的输出无法解析为合法 JSON，错误：{last_err}。"
                "请重新输出，只输出 JSON。\n\n原始任务：\n" + prompt
            )
        try:
            raw = provider.recognize(images, current_prompt, system=VISION_SYSTEM)
            data = extract_json(raw)
            if not isinstance(data.get("fields", {}), dict):
                raise ValueError("输出缺少 fields 对象")
            break
        except LLMError:
            raise
        except Exception as e:
            last_err = e
    if data is None:
        raise LLMError(f"模型输出解析失败：{last_err}")

    # 按字段元数据校验转换识别值
    by_name = {f.field_name: f for f in fields}
    out_fields, skipped = {}, []
    for key, v in (data.get("fields") or {}).items():
        f = by_name.get(key)
        if f is None:
            continue
        ok, cv, err = coerce_value(v, f.data_type, True)
        if ok and cv is not None:
            out_fields[key] = _serialize(cv)
        elif not ok:
            skipped.append(f"{f.label}（{err}）")

    # 冲突：识别值与当前值都有值且不一致
    conflicts = []
    seen = set()
    for c in (data.get("conflicts") or []):
        if isinstance(c, dict) and c.get("field_name") in by_name:
            conflicts.append({"field_name": c["field_name"], "reason": str(c.get("reason") or "")})
            seen.add(c["field_name"])
    for key, recognized in out_fields.items():
        cur = (current or {}).get(key)
        if cur not in (None, "") and str(cur) != str(recognized) and key not in seen:
            conflicts.append({"field_name": key, "reason": "与当前值不一致"})
            seen.add(key)

    notes = str(data.get("notes") or "")
    if skipped:
        notes = (notes + "；" if notes else "") + "以下字段识别值无法转换已忽略：" + "、".join(skipped)

    return {"fields": out_fields, "conflicts": conflicts, "notes": notes}, raw


JUDGE_BATCH_SIZE = 20


def judge_records(db: Session, description: str, field_dicts: list[dict], records: list[dict]) -> set[int]:
    """LLM 分批判断记录是否满足自然语言条件，返回命中的记录 id 集合。"""
    provider = get_default_provider(db)
    matched: set[int] = set()
    for i in range(0, len(records), JUDGE_BATCH_SIZE):
        batch = records[i:i + JUDGE_BATCH_SIZE]
        prompt = build_judge_prompt(description, field_dicts, batch)
        last_err: Exception | None = None
        for attempt in range(2):
            current = prompt if attempt == 0 else (
                f"你上次的输出无法解析为合法 JSON，错误：{last_err}。"
                "请重新输出，只输出 JSON。\n\n原始任务：\n" + prompt
            )
            try:
                raw = provider.complete(current, system=JUDGE_SYSTEM)
                data = extract_json(raw)
                ids = data.get("matched_ids") or []
                if not isinstance(ids, list):
                    raise ValueError("matched_ids 必须是数组")
                valid_ids = {r["id"] for r in batch}
                for x in ids:
                    try:
                        ix = int(x)
                    except (TypeError, ValueError):
                        continue
                    if ix in valid_ids:
                        matched.add(ix)
                break
            except LLMError:
                raise
            except Exception as e:
                last_err = e
        else:
            raise LLMError(f"LLM 条件判断结果解析失败：{last_err}")
    return matched
