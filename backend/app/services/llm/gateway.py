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
        elif t == "pivot":
            dims = {}
            for axis, axis_label in (("row", "行"), ("col", "列")):
                g = b.get(axis) or {}
                gkind = g.get("kind") if g.get("kind") in _REPORT_GROUP_KINDS else "field"
                gfield = g.get("field")
                gf = fields_by_name.get(gfield or "")
                if gkind == "field":
                    if gfield not in fields_by_name and gfield not in _REPORT_SYSTEM_FIELDS:
                        notes_extra.append(f"「{out['title'] or '透视表'}」的{axis_label}维度字段无效，已跳过该区块")
                        dims = None
                        break
                else:
                    is_date = (gf is not None and gf.data_type in ("date", "datetime")) or gfield in _REPORT_DATE_SYSTEM_FIELDS
                    if not is_date:
                        gfield = "created_at"
                dims[axis] = {"kind": gkind, "field": gfield}
            if not dims:
                continue
            if dims["row"] == dims["col"]:
                notes_extra.append(f"「{out['title'] or '透视表'}」行列维度相同，已跳过该区块")
                continue
            numeric_or_count(b, out)
            out.update({"row": dims["row"], "col": dims["col"], "filters": clean_filters(b.get("filters"))})
            if b.get("totals") is False:
                out["totals"] = False
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


# ---------- AI 助手（对话式） ----------

_ASSISTANT_FILL_MAX = 50
_ASSISTANT_HISTORY_MAX = 20      # 历史窗口（约 10 轮对话）
_ASSISTANT_HISTORY_CHARS = 2000  # 单条历史截断（联网搜索类长回答需保留）


def field_dicts_of(fields: list) -> list[dict]:
    """字段元数据 → 提示词用四元组（与 assist_task/assist_report/recognize 一致）。"""
    return [
        {"field_name": f.field_name, "label": f.label, "data_type": f.data_type, "options": f.options or {}}
        for f in fields
    ]


def _accessible_tables(db: Session, user) -> list:
    """当前用户可访问（自有 + 已接受分享；admin 全部）的数据表清单。"""
    from sqlalchemy import or_

    from ...models import GroupMember, MetaTable, TableShare

    q = db.query(MetaTable)
    if user.role != "admin":
        shared_ids = [
            s.table_id
            for s in db.query(TableShare)
            .outerjoin(GroupMember, TableShare.group_id == GroupMember.group_id)
            .filter(
                TableShare.can_view.is_(True),
                TableShare.status == "accepted",
                or_(TableShare.user_id == user.id, GroupMember.user_id == user.id),
            )
            .all()
        ]
        q = q.filter(or_(MetaTable.owner_id == user.id, MetaTable.id.in_(shared_ids or [-1])))
    return q.order_by(MetaTable.id.desc()).all()


def _clean_assistant_fields(raw_fields, notes: list) -> list[dict]:
    """清洗 create_table / gen_excel blank 的字段定义：非法类型降级、字段名合法化去重。"""
    out, used = [], set()
    for i, f in enumerate(raw_fields or []):
        if not isinstance(f, dict):
            continue
        dt = f.get("data_type") if f.get("data_type") in DATA_TYPES else "varchar"
        widget = f.get("widget") if f.get("widget") in WIDGETS else default_widget(dt)
        label = str(f.get("label") or "").strip()[:64] or f"字段{i + 1}"
        out.append({
            "field_name": safe_field_name(str(f.get("field_name") or ""), used, i + 1),
            "label": label,
            "data_type": dt,
            "length": int(f.get("length") or 255),
            "nullable": bool(f.get("nullable", True)),
            "widget": widget,
            "options": f.get("options") if isinstance(f.get("options"), dict) else {},
        })
    if len(out) > 100:
        notes.append("字段数超过 100，已截断")
    return out[:100]


def align_assistant_action(db: Session, user, action: dict | None, notes: list) -> dict | None:
    """把 LLM 输出的动作清洗成可预览的卡片；query 动作顺带完成只读求值。非法动作返回 None。"""
    from ..assistant_engine import clean_assistant_filters, clean_query_spec, run_query_spec
    from ..meta_service import get_meta_fields
    from ...utils.access import get_table_access

    if not isinstance(action, dict):
        return None
    t = action.get("type")

    def table_ctx(table_id, need_create=False):
        try:
            access = get_table_access(db, int(table_id), user)
        except Exception:  # noqa: BLE001 — 表不存在/无权限统一按不可用处理（404 语义不泄露）
            return None, None
        if need_create and not access.can_create:
            return None, None
        return access.table, get_meta_fields(db, access.table.id)

    if t == "fill_records":
        mt, fields = table_ctx(action.get("table_id"), need_create=True)
        if mt is None:
            notes.append("目标表不存在或没有新增权限，已忽略填表动作")
            return None
        fbn = {f.field_name: f for f in fields}
        records = []
        for rec in (action.get("records") or [])[:_ASSISTANT_FILL_MAX]:
            if not isinstance(rec, dict):
                continue
            cleaned = {}
            for name, v in rec.items():
                f = fbn.get(name)
                if f is None:
                    notes.append(f"字段 {name} 不存在，已忽略")
                    continue
                ok, cv, _ = coerce_value(v, f.data_type, True)
                if not ok:
                    notes.append(f"「{f.label}」的值 {str(v)[:30]} 无法转换为 {f.data_type}，已置空")
                    cv = None
                cleaned[name] = cv
            if cleaned:
                records.append(cleaned)
        if not records:
            notes.append("没有可填入的有效记录")
            return None
        return {
            "type": "fill_records", "table_id": mt.id, "table_label": mt.label,
            "summary": f"新增 {len(records)} 条记录",
            "payload": {"records": records, "fields": field_dicts_of(fields)},
            "warnings": notes,
        }

    if t == "create_table":
        fields = _clean_assistant_fields(action.get("fields"), notes)
        if not fields:
            notes.append("没有有效字段，已忽略建表动作")
            return None
        label = str(action.get("label") or "").strip()[:64] or "新建数据表"
        return {
            "type": "create_table", "summary": f"创建表「{label}」（{len(fields)} 个字段）",
            "payload": {"label": label, "fields": fields}, "warnings": notes,
        }

    if t == "gen_excel":
        mode = action.get("mode")
        if mode == "blank":
            fields = _clean_assistant_fields(action.get("fields"), notes)
            if not fields:
                notes.append("没有有效字段，已忽略生成 Excel 动作")
                return None
            label = str(action.get("label") or "").strip()[:64] or "表格模板"
            sample_rows = [r for r in (action.get("sample_rows") or [])[:20] if isinstance(r, list)]
            return {
                "type": "gen_excel", "summary": f"生成模板「{label}.xlsx」（{len(fields)} 列）",
                "payload": {"mode": "blank", "label": label, "fields": fields, "sample_rows": sample_rows},
                "warnings": notes,
            }
        if mode == "export":
            mt, fields = table_ctx(action.get("table_id"))
            if mt is None:
                notes.append("目标表不存在或没有查看权限，已忽略导出动作")
                return None
            fbn = {f.field_name: f for f in fields}
            filters = clean_assistant_filters(action.get("filters"), fbn, notes)
            return {
                "type": "gen_excel", "summary": f"导出「{mt.label}」记录（{len(filters['rules'])} 个筛选条件）",
                "payload": {"mode": "export", "table_id": mt.id, "table_label": mt.label, "filters": filters},
                "warnings": notes,
            }
        notes.append(f"不支持的 Excel 生成模式：{mode}")
        return None

    if t == "create_report":
        mt, fields = table_ctx(action.get("table_id"))
        if mt is None:
            notes.append("目标表不存在或没有查看权限，已忽略创建报表动作")
            return None
        desc = str(action.get("description") or "").strip()
        if not desc:
            notes.append("缺少报表需求描述，已忽略")
            return None
        cfg = assist_report(db, fields, desc)   # 复用报表 AI 辅助管线（生成 + align 清洗）
        notes.extend([cfg["notes"]] if cfg.get("notes") else [])
        return {
            "type": "create_report", "summary": f"创建报表「{cfg['name']}」（{len(cfg['blocks'])} 个区块）",
            "payload": {"table_id": mt.id, "table_label": mt.label, **cfg},
            "warnings": notes,
        }

    if t == "create_task":
        mt, fields = table_ctx(action.get("table_id"))
        if mt is None:
            notes.append("目标表不存在或没有查看权限，已忽略创建任务动作")
            return None
        desc = str(action.get("description") or "").strip()
        if not desc:
            notes.append("缺少任务需求描述，已忽略")
            return None
        cfg = assist_task(db, fields, desc)   # 复用任务 AI 辅助管线
        notes.extend([cfg["notes"]] if cfg.get("notes") else [])
        return {
            "type": "create_task", "summary": f"创建任务规则「{cfg['name']}」",
            "payload": {"table_id": mt.id, "table_label": mt.label, **cfg},
            "warnings": notes,
        }

    if t == "alter_table":
        import re as _re

        from ..typemap import DATA_TYPES
        try:
            access = get_table_access(db, int(action.get("table_id")), user)
        except Exception:  # noqa: BLE001
            notes.append("目标表不存在，已忽略修改表结构动作")
            return None
        if not (access.is_owner or access.is_admin):
            notes.append("只有表主人或管理员能修改表结构，已忽略")
            return None
        mt = access.table
        fields = get_meta_fields(db, mt.id)
        fbn = {f.field_name: f for f in fields}
        ops, summaries = [], []
        for raw in (action.get("ops") or [])[:20]:
            if not isinstance(raw, dict):
                continue
            kind = raw.get("op")
            if kind == "add_field":
                cleaned = _clean_assistant_fields([raw.get("field") or {}], notes)
                if not cleaned:
                    continue
                f0 = cleaned[0]
                if f0["field_name"] in fbn:
                    notes.append(f"字段 {f0['field_name']} 已存在，已忽略")
                    continue
                ops.append({"op": "add_field", "field": f0})
                summaries.append(f"新增字段「{f0['label']}」({f0['data_type']})")
            elif kind == "delete_field":
                name = raw.get("field_name")
                if name not in fbn:
                    notes.append(f"字段 {name} 不存在，已忽略")
                    continue
                ops.append({"op": "delete_field", "field_name": name})
                summaries.append(f"删除字段「{fbn[name].label}」")
            elif kind == "update_field":
                name = raw.get("field_name")
                if name not in fbn:
                    notes.append(f"字段 {name} 不存在，已忽略")
                    continue
                upd = {"op": "update_field", "field_name": name}
                for k in ("label", "data_type", "nullable", "widget", "options", "default_value"):
                    if raw.get(k) is not None:
                        upd[k] = raw[k]
                if upd.get("data_type") and upd["data_type"] not in DATA_TYPES:
                    notes.append(f"字段 {name} 的目标类型 {upd['data_type']} 无效，已忽略类型修改")
                    upd.pop("data_type")
                if len(upd) <= 2:
                    continue
                ops.append(upd)
                desc = f"修改字段「{fbn[name].label}」"
                if upd.get("data_type"):
                    desc += f"类型→{upd['data_type']}（存量数据将尝试转换）"
                elif upd.get("label"):
                    desc += f"显示名→「{upd['label']}」"
                summaries.append(desc)
            elif kind == "rename_field":
                name, new = raw.get("field_name"), str(raw.get("new_field_name") or "").strip()
                if name not in fbn:
                    notes.append(f"字段 {name} 不存在，已忽略")
                    continue
                if not _re.match(r"^[a-z][a-z0-9_]{0,40}$", new):
                    notes.append(f"新字段名 {new} 不是合法 snake_case，已忽略改名")
                    continue
                if new in fbn:
                    notes.append(f"新字段名 {new} 已存在，已忽略改名")
                    continue
                ops.append({"op": "rename_field", "field_name": name, "new_field_name": new,
                            "label": raw.get("label")})
                summaries.append(f"字段 {name} 改名为 {new}")
            else:
                notes.append(f"不支持的结构变更操作：{kind}")
        if not ops:
            notes.append("没有有效的结构变更操作")
            return None
        return {
            "type": "alter_table", "summary": f"修改表「{mt.label}」结构（{len(ops)} 项）",
            "payload": {"table_id": mt.id, "table_label": mt.label, "ops": ops, "summaries": summaries},
            "warnings": notes,
        }

    if t == "run_workflow":
        from ...models import Workflow
        try:
            wf = db.get(Workflow, int(action.get("workflow_id") or 0))
        except (TypeError, ValueError):
            wf = None
        if wf is None or wf.user_id != user.id:
            notes.append("工作流不存在或不属于你，已忽略执行工作流动作")
            return None
        params = action.get("params") if isinstance(action.get("params"), dict) else {}
        status_note = "" if wf.enabled else "（当前停用，仍可手动执行一次）"
        return {
            "type": "run_workflow", "summary": f"执行工作流「{wf.name}」{status_note}",
            "payload": {"workflow_id": wf.id, "workflow_name": wf.name, "params": params},
            "warnings": notes,
        }

    if t == "query":
        mt, fields = table_ctx(action.get("table_id"))
        if mt is None:
            notes.append("目标表不存在或没有查看权限，已忽略问答动作")
            return None
        spec, spec_notes = clean_query_spec(fields, action.get("spec") or {})
        notes += spec_notes
        if spec is None:
            return None
        result = run_query_spec(db, mt, fields, spec)
        return {
            "type": "query_answer", "table_id": mt.id, "table_label": mt.label,
            "summary": "数据查询结果", "result": result, "warnings": notes,
        }

    if t:
        notes.append(f"不支持的动作类型：{t}")
    return None


def _chat_with_search(db: Session, provider, message: str, history: list, action: dict) -> dict:
    """联网搜索动作：执行搜索 → 二次调用模型基于结果组织回答，附来源卡片（只读，无需确认）。"""
    from datetime import datetime

    from ..web_search import SearchError, web_search
    from .prompts import SEARCH_ANSWER_SYSTEM, build_search_answer_prompt

    queries = action.get("queries") or ([action.get("query")] if action.get("query") else [])
    queries = [str(q).strip() for q in queries if str(q or "").strip()][:3]
    if not queries:
        return {"reply": "你想让我查什么呢？换个说法再试试。", "action_card": None}

    results, errors = [], []
    for q in queries:
        try:
            results += web_search(db, q)
        except SearchError as e:
            errors.append(str(e))
    # 按 URL 去重
    seen, deduped = set(), []
    for r in results:
        if r.get("url") and r["url"] not in seen:
            seen.add(r["url"])
            deduped.append(r)
    results = deduped[:10]

    if not results:
        reason = errors[0] if errors else "没有搜到相关结果"
        return {
            "reply": f"我试着联网查了一下，但{reason}。你可以直接告诉我信息，我帮你整理、分析或录入系统。",
            "action_card": None,
        }

    prompt = build_search_answer_prompt(message, history, queries, results, datetime.now().strftime("%Y-%m-%d"))
    try:
        reply = provider.complete(prompt, system=SEARCH_ANSWER_SYSTEM).strip()
    except LLMError:
        raise
    return {
        "reply": reply,
        "action_card": {
            "type": "search_answer",
            "summary": f"联网搜索：{'、'.join(queries)}",
            "payload": {"queries": queries, "results": results},
        },
    }


def _decode_data_urls(images: list[str] | None) -> list[bytes]:
    """把前端粘贴/上传的 data URL 图片解码为字节。限 4 张、单张 5MB。"""
    import base64
    import binascii

    out = []
    for s in (images or [])[:4]:
        if not isinstance(s, str) or not s.startswith("data:image/") or "," not in s:
            raise LLMError("图片格式不正确（需要 image data URL）")
        try:
            raw = base64.b64decode(s.split(",", 1)[1])
        except (binascii.Error, ValueError):
            raise LLMError("图片解码失败")
        if not raw or len(raw) > 5 * 1024 * 1024:
            raise LLMError("单张图片不能超过 5MB")
        out.append(raw)
    return out


def assist_chat(db: Session, user, message: str, history: list | None, context: dict | None,
                images: list[str] | None = None) -> dict:
    """AI 助手对话：输出 {reply, action_card}；query 动作在 align 阶段已完成只读求值。
    images 为粘贴图片的 data URL 列表，非空时走视觉模型（recognize）。"""
    from datetime import datetime

    from ..meta_service import get_meta_fields
    from .prompts import ASSISTANT_SYSTEM, build_assistant_prompt

    provider = get_default_provider(db)
    tables = _accessible_tables(db, user)
    from ...models import Workflow
    wf_briefs = [
        {"id": w.id, "name": w.name, "description": w.description, "enabled": w.enabled}
        for w in db.query(Workflow).filter(Workflow.user_id == user.id).order_by(Workflow.id.desc()).limit(30).all()
    ]
    # 前 15 张表带字段简报（模型才能在任意页面正确填表/问答）；更多表只给 id+label
    table_briefs = []
    for t in tables[:15]:
        fields = get_meta_fields(db, t.id)
        table_briefs.append({
            "id": t.id, "label": t.label,
            "fields": [
                {"field_name": f.field_name, "label": f.label, "data_type": f.data_type, "options": f.options or {}}
                for f in fields[:40]
            ],
        })
    for t in tables[15:]:
        table_briefs.append({"id": t.id, "label": t.label})

    current = None
    ctx = context or {}
    if ctx.get("table_id"):
        mt = next((t for t in tables if t.id == ctx.get("table_id")), None)
        if mt is not None:
            current = {"id": mt.id, "label": mt.label}

    history = [
        {"role": "user" if h.get("role") == "user" else "assistant", "content": str(h.get("content") or "")[:_ASSISTANT_HISTORY_CHARS]}
        for h in (history or []) if isinstance(h, dict)
    ][-_ASSISTANT_HISTORY_MAX:]
    img_bytes = _decode_data_urls(images)
    prompt = build_assistant_prompt(message, history, table_briefs, current, datetime.now().strftime("%Y-%m-%d"),
                                    workflows=wf_briefs)
    if img_bytes:
        prompt += (f"\n\n注意：用户随消息附上了 {len(img_bytes)} 张图片，请结合图片内容理解需求"
                   "（例如从截图中提取信息填入数据表、根据图片中的表格建表等）。")
    last_err: Exception | None = None
    for attempt in range(2):
        current_prompt = prompt if attempt == 0 else (
            f"你上次的输出无法解析为合法 JSON，错误：{last_err}。"
            "请重新输出，只输出 JSON。\n\n原始任务：\n" + prompt
        )
        try:
            if img_bytes:
                raw = provider.recognize(img_bytes, current_prompt, system=ASSISTANT_SYSTEM)
            else:
                raw = provider.complete(current_prompt, system=ASSISTANT_SYSTEM)
            data = extract_json(raw)
            action = data.get("action")
            # 联网搜索：单独通道（执行搜索 + 二次调用组织回答）
            if isinstance(action, dict) and action.get("type") == "web_search":
                return _chat_with_search(db, provider, message, history, action)
            reply = str(data.get("reply") or "")[:2000]
            notes: list = []
            card = align_assistant_action(db, user, action, notes)
            return {"reply": reply, "action_card": card}
        except LLMError:
            raise
        except Exception as e:
            last_err = e
    raise LLMError(f"模型输出解析失败：{last_err}")
