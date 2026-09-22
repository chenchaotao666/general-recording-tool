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
from .prompts import (
    ANALYZE_SYSTEM, JUDGE_SYSTEM, REPORT_SYSTEM, TASK_SYSTEM, VISION_SYSTEM,
    build_analyze_prompt, build_judge_prompt, build_report_prompt, build_task_prompt, build_vision_prompt,
)


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


# ---------- 报表 AI 辅助 ----------

_REPORT_RANGE_MODES = {"this_week", "last_week", "this_month", "last_month"}
_REPORT_AGGS = {"count", "sum", "avg", "max", "min"}
_REPORT_CHARTS = {"bar", "line", "pie"}
_REPORT_GROUP_KINDS = {"field", "day", "week", "month"}
_REPORT_SYSTEM_FIELDS = {"id", "created_at", "updated_at"}
_REPORT_DATE_SYSTEM_FIELDS = {"created_at", "updated_at"}


def align_report_config(data: dict, fields: list) -> dict:
    """把 LLM 输出的报表配置对齐到真实字段：丢弃非法字段/区块，数值聚合降级为计数。"""
    from ..report_engine import TABLE_LIMIT_MAX

    fields_by_name = {f.field_name: f for f in fields}
    notes_extra = []

    rng = data.get("range") or {}
    mode = rng.get("mode") if rng.get("mode") in _REPORT_RANGE_MODES else "this_week"
    date_field = rng.get("date_field") or "created_at"
    df = fields_by_name.get(date_field)
    if date_field not in _REPORT_DATE_SYSTEM_FIELDS and (df is None or df.data_type not in ("date", "datetime")):
        notes_extra.append(f"统计日期字段 {date_field} 无效，已改为创建时间")
        date_field = "created_at"

    def clean_filters(flt) -> dict:
        from ..dyn_engine import FILTER_OPS, rule_value_ok
        rules = []
        for r in ((flt or {}).get("rules") or []):
            if not isinstance(r, dict):
                continue
            name, op = r.get("field"), r.get("op")
            if name not in fields_by_name and name not in _REPORT_SYSTEM_FIELDS:
                continue
            if op not in FILTER_OPS:
                continue
            if not rule_value_ok(fields_by_name.get(name), op, r.get("value")):
                notes_extra.append(f"筛选条件「{name} {op}」的值无效已丢弃")
                continue
            rules.append({"field": name, "op": op, "value": r.get("value")})
        return {"logic": "OR" if (flt or {}).get("logic") == "OR" else "AND", "rules": rules}

    def numeric_or_count(b, out):
        agg = b.get("agg") if b.get("agg") in _REPORT_AGGS else "count"
        field = b.get("field")
        if agg != "count":
            f = fields_by_name.get(field or "")
            if f is None or f.data_type not in ("int", "decimal"):
                notes_extra.append(f"「{out.get('title') or b.get('type')}」的聚合字段无效，已降级为计数")
                agg, field = "count", None
        out["agg"] = agg
        if agg != "count":
            out["field"] = field

    blocks, stat_seq = [], 0
    for b in data.get("blocks") or []:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        out = {"type": t, "title": str(b.get("title") or "")[:64]}
        if t == "stat":
            stat_seq += 1
            out["id"] = f"b{stat_seq}"   # text 占位符按 stat 顺序编号
            numeric_or_count(b, out)
            out["filters"] = clean_filters(b.get("filters"))
        elif t == "chart":
            chart_type = b.get("chart_type") if b.get("chart_type") in _REPORT_CHARTS else "bar"
            group = b.get("group") or {}
            gkind = group.get("kind") if group.get("kind") in _REPORT_GROUP_KINDS else "field"
            gfield = group.get("field")
            gf = fields_by_name.get(gfield or "")
            if gkind == "field":
                if gfield not in fields_by_name and gfield not in _REPORT_SYSTEM_FIELDS:
                    notes_extra.append(f"「{out['title'] or '图表'}」的分组字段无效，已跳过该图表")
                    continue
            else:
                is_date = (gf is not None and gf.data_type in ("date", "datetime")) or gfield in _REPORT_DATE_SYSTEM_FIELDS
                if not is_date:
                    gfield = "created_at"
            numeric_or_count(b, out)
            out.update({
                "chart_type": chart_type, "group": {"kind": gkind, "field": gfield},
                "filters": clean_filters(b.get("filters")),
            })
            if chart_type == "pie":
                try:
                    out["top_n"] = min(max(int(b.get("top_n") or 8), 2), 30)
                except (TypeError, ValueError):
                    out["top_n"] = 8
        elif t == "table":
            cols = [c for c in (b.get("columns") or []) if c in fields_by_name or c in _REPORT_SYSTEM_FIELDS]
            if not cols:
                notes_extra.append(f"「{out['title'] or '明细表'}」没有有效列，已跳过")
                continue
            sort_by = b.get("sort_by")
            if sort_by not in fields_by_name and sort_by not in _REPORT_SYSTEM_FIELDS:
                sort_by = "created_at"
            try:
                limit = min(max(int(b.get("limit") or 100), 1), TABLE_LIMIT_MAX)
            except (TypeError, ValueError):
                limit = 100
            out.update({
                "columns": cols, "sort_by": sort_by,
                "sort_order": "asc" if b.get("sort_order") == "asc" else "desc",
                "limit": limit, "filters": clean_filters(b.get("filters")),
            })
        elif t == "text":
            out["content"] = str(b.get("content") or "")
        else:
            continue
        blocks.append(out)

    # 统一编号（stat 已按顺序编号，其余类型继续往后排，保证 id 唯一）
    used = {b["id"] for b in blocks if b.get("id")}
    seq = len(used)
    for b in blocks:
        if not b.get("id"):
            seq += 1
            b["id"] = f"b{seq}"

    if not blocks:
        raise LLMError("模型没有生成任何有效的报表区块，请换一种描述再试")

    notes = str(data.get("notes") or "")
    if notes_extra:
        notes = (notes + "；" if notes else "") + "；".join(notes_extra)
    return {
        "name": str(data.get("name") or "")[:128] or "AI 报表",
        "range": {"mode": mode, "date_field": date_field},
        "blocks": blocks,
        "notes": notes,
    }


def assist_report(db: Session, fields: list, description: str) -> dict:
    """LLM 把自然语言需求转成报表配置；JSON 解析失败时回喂重试一次。"""
    provider = get_default_provider(db)
    field_dicts = [
        {"field_name": f.field_name, "label": f.label, "data_type": f.data_type, "options": f.options or {}}
        for f in fields
    ]
    prompt = build_report_prompt(description, field_dicts)
    last_err: Exception | None = None
    for attempt in range(2):
        current = prompt if attempt == 0 else (
            f"你上次的输出无法解析为合法 JSON，错误：{last_err}。"
            "请重新输出，只输出 JSON。\n\n原始任务：\n" + prompt
        )
        try:
            raw = provider.complete(current, system=REPORT_SYSTEM)
            data = extract_json(raw)
            if not isinstance(data.get("blocks"), list):
                raise ValueError("输出缺少 blocks 数组")
            return align_report_config(data, fields)
        except LLMError:
            raise
        except Exception as e:
            last_err = e
    raise LLMError(f"模型输出解析失败：{last_err}")


# ---------- 任务规则 AI 辅助 ----------

_TASK_ACTION_TYPES = {"notify", "email", "sms", "webhook"}


def align_task_config(data: dict, fields: list) -> dict:
    """把 LLM 输出的任务配置对齐到真实字段：清洗条件/周期/动作，非法项给默认值并记入 notes。"""
    from ..dyn_engine import FILTER_OPS, rule_value_ok
    from ..scheduler import trigger_of

    fields_by_name = {f.field_name: f for f in fields}
    notes_extra = []

    # 条件
    mode = data.get("condition_mode") if data.get("condition_mode") in ("structured", "llm") else "structured"
    cond_in = data.get("condition") or {}
    if mode == "llm":
        desc = str(cond_in.get("description") or "").strip()
        if not desc:
            mode = "structured"
            notes_extra.append("LLM 判断条件为空，已改为结构化条件")
    if mode == "structured":
        rules = []
        for r in cond_in.get("rules") or []:
            if not isinstance(r, dict):
                continue
            name, op = r.get("field"), r.get("op")
            if name not in fields_by_name and name not in _REPORT_SYSTEM_FIELDS:
                continue
            if op not in FILTER_OPS:
                continue
            if not rule_value_ok(fields_by_name.get(name), op, r.get("value")):
                notes_extra.append(f"条件「{name} {op}」的值无效已丢弃")
                continue
            rules.append({"field": name, "op": op, "value": r.get("value")})
        if not rules:
            raise LLMError("模型没有生成任何有效的条件，请换一种描述再试")
        condition = {"logic": "OR" if cond_in.get("logic") == "OR" else "AND", "rules": rules}
    else:
        condition = {"description": desc}

    # 周期
    sched_in = data.get("schedule") or {}
    schedule = {"type": sched_in.get("type"), "minutes": sched_in.get("minutes"), "expr": sched_in.get("expr")}
    if trigger_of(schedule) is None:
        notes_extra.append("执行周期无效，已改为每天早上 9 点")
        schedule = {"type": "cron", "expr": "0 9 * * *"}
    schedule = {k: v for k, v in schedule.items() if v is not None}

    # 动作
    act_in = data.get("action") or {}
    act_type = act_in.get("type") if act_in.get("type") in _TASK_ACTION_TYPES else "notify"
    template = str(act_in.get("template") or "").strip()
    if not template:
        template = "有记录命中条件，请及时处理。"
        notes_extra.append("通知内容模板为空，已使用默认文案")
    rec_in = act_in.get("recipients") or {}
    if rec_in.get("type") == "field" and rec_in.get("field") in fields_by_name:
        recipients = {"type": "field", "value": "", "field": rec_in["field"]}
    else:
        if rec_in.get("type") == "field":
            notes_extra.append(f"接收人字段 {rec_in.get('field')} 无效，已改为固定地址（请补充）")
        recipients = {"type": "fixed", "value": str(rec_in.get("value") or ""), "field": ""}
    action = {"type": act_type, "template": template, "recipients": recipients}
    if act_type == "webhook":
        action["webhook_url"] = str(act_in.get("webhook_url") or "")

    try:
        cooldown = max(int(data.get("cooldown_hours", 24)), 0)
    except (TypeError, ValueError):
        cooldown = 24

    notes = str(data.get("notes") or "")
    if notes_extra:
        notes = (notes + "；" if notes else "") + "；".join(notes_extra)
    return {
        "name": str(data.get("name") or "")[:128] or "AI 任务",
        "condition_mode": mode,
        "condition": condition,
        "schedule": schedule,
        "action": action,
        "cooldown_hours": cooldown,
        "notes": notes,
    }


def assist_task(db: Session, fields: list, description: str) -> dict:
    """LLM 把自然语言需求转成任务规则配置；JSON 解析失败时回喂重试一次。"""
    provider = get_default_provider(db)
    field_dicts = [
        {"field_name": f.field_name, "label": f.label, "data_type": f.data_type, "options": f.options or {}}
        for f in fields
    ]
    prompt = build_task_prompt(description, field_dicts)
    last_err: Exception | None = None
    for attempt in range(2):
        current = prompt if attempt == 0 else (
            f"你上次的输出无法解析为合法 JSON，错误：{last_err}。"
            "请重新输出，只输出 JSON。\n\n原始任务：\n" + prompt
        )
        try:
            raw = provider.complete(current, system=TASK_SYSTEM)
            data = extract_json(raw)
            if not isinstance(data.get("condition"), dict):
                raise ValueError("输出缺少 condition 对象")
            return align_task_config(data, fields)
        except LLMError:
            raise
        except Exception as e:
            last_err = e
    raise LLMError(f"模型输出解析失败：{last_err}")


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
