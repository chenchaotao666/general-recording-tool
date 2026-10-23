"""智能表 AI 字段（设计文档 §10）+ AI 生成公式 / AI 匹配标签（§18 V3）。

场景 = 提示词模板 + 输入字段 + 输出类型；AI 字段值落 records.data（与普通字段同存储），
单元格状态（生成中/失败）落 smart_ai_runs；手动生成标记「AI 生成」，自动重算保留记录原操作人。

执行：单线程后台队列（smart_events.submit），触发 = 新增行 / 输入字段变更（config.autoUpdate）/ 手动刷新。
配额：套餐权益 smart_ai_calls_monthly（缺省=不限），按租户自然月计调用大模型的单元格次数。
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from ..models import MetaField, MetaTable, Record, SmartAiRun
from . import entitlement, json_store, smart_events
from .field_registry import OPTION_COLOR_ORDER
from .meta_service import get_meta_fields
from .ai_scenes import CATEGORIES, SCENE_BY_KEY, SCENES
from .smart_format import display, option_map, record_text

log = logging.getLogger(__name__)
QUOTA_KEY = "smart_ai_calls_monthly"
MAX_BATCH = 2000

# 场景市场目录（§10.1）见 ai_scenes；前端 GET /smart/ai/scenes 渲染
OUTPUT_RULES = {
    "text": '以 JSON 返回：{"value": "结果文本"}。',
    "number": '以 JSON 返回：{"value": 数字}，无法计算时 value 为 null。',
    "checkbox": '以 JSON 返回：{"value": true 或 false}。',
}


# ---------- 配额 ----------

def quota_status(db: Session, tenant_id: int | None) -> dict:
    limit = entitlement.get_entitlements(db, tenant_id).get(QUOTA_KEY) if tenant_id else None
    start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    used = (db.query(SmartAiRun).filter(SmartAiRun.tenant_id == tenant_id, SmartAiRun.billable.is_(True),
                                        SmartAiRun.updated_at >= start).count()) if tenant_id else 0
    return {"used": used, "limit": limit}


def _quota_ok(db: Session, tenant_id: int | None) -> bool:
    q = quota_status(db, tenant_id)
    return q["limit"] is None or q["used"] < q["limit"]


# ---------- 提示词组装 ----------

def _field_by(fields, fn):
    return next((f for f in fields if f.field_name == fn), None)


def _options_of(field: MetaField) -> list[dict]:
    return [o for o in (field.options or {}).get("options") or [] if isinstance(o, dict)]


def build_prompt_cfg(db: Session, cfg: dict, fields: list, record: dict, labels: list[str]) -> tuple[str, str]:
    """按配置组装 (system, user)；labels = 单选/多选的现有选项名。
    新配置用 systemPrompt（AI 配置生成、可编辑的「你是… / 任务… / 输入…」）；旧配置回落到场景默认提示词。"""
    scene = SCENE_BY_KEY.get(cfg.get("scene") or "custom", SCENE_BY_KEY["custom"])
    out_type = cfg.get("outputType") or scene["outputType"]
    inputs = [x for x in cfg.get("inputFields") or [] if _field_by(fields, x)]
    today = datetime.now().strftime("%Y-%m-%d")
    if cfg.get("systemPrompt"):
        system = str(cfg["systemPrompt"]).replace("{today}", today)
        user = "输入内容：\n" + (record_text(db, fields, record, inputs) or "（空）")
    elif scene["key"] == "custom":   # 旧版自定义：提示词模板内 {字段名} 替换为本行值
        cache: dict = {}
        by_label = {f.label: f for f in fields}

        def sub(m):
            f = by_label.get(m.group(1)) or _field_by(fields, m.group(1))
            return display(db, f, record.get(f.field_name), cache) if f else m.group(0)
        user = re.sub(r"\{([^{}]+)\}", sub, str(cfg.get("prompt") or ""))
        if inputs:
            user += "\n\n参考内容：\n" + record_text(db, fields, record, inputs)
        system = "你是一个嵌入在智能表格中的 AI 助手，按用户要求处理本行数据，结果简洁准确。"
    else:
        system = scene.get("prompt", "").replace("{target}", str(cfg.get("target") or "关键信息")).replace("{today}", today)
        if cfg.get("prompt"):
            system += "\n补充要求：" + str(cfg["prompt"])
        user = "输入内容：\n" + (record_text(db, fields, record, inputs) or "（空）")
    system += f"\n（今天是 {today}）"
    if out_type in ("singleSelect", "multiSelect"):
        multi = out_type == "multiSelect"
        rule = f"可选{'标签' if multi else '分类'}：{json.dumps(labels, ensure_ascii=False)}。"
        rule += ("若都不合适，可给出新的简短名称。" if cfg.get("allowNewOptions", True) or not labels
                 else "必须从可选项中选择。")
        rule += ('以 JSON 返回：{"value": ["标签1", "标签2"]}。' if multi else '以 JSON 返回：{"value": "分类名"}。')
    else:
        rule = OUTPUT_RULES.get(out_type, OUTPUT_RULES["text"])
    return system + "\n\n输出要求：" + rule + "只输出 JSON，不要解释。", user


def build_prompt(db: Session, field: MetaField, fields: list, record: dict) -> tuple[str, str]:
    return build_prompt_cfg(db, field.options or {}, fields, record, [o.get("label") for o in _options_of(field)])


def _parse_value(text: str):
    from .llm.gateway import extract_json
    try:
        data = extract_json(text)
        return data.get("value") if isinstance(data, dict) else data
    except Exception:  # noqa: BLE001 — 非 JSON 输出：整段当作文本
        return text.strip()


def _ensure_options(db: Session, field: MetaField, labels: list[str], allow_new: bool) -> list[str]:
    """标签 → optionId；允许时自动创建新选项（§10.1「可自动建选项」）。"""
    opts = _options_of(field)
    by_label = {str(o.get("label")).strip(): o["id"] for o in opts}
    ids, changed = [], False
    for lb in labels:
        lb = str(lb or "").strip()[:30]
        if not lb:
            continue
        if lb in by_label:
            ids.append(by_label[lb])
        elif allow_new:
            nid = f"opt_ai_{len(opts) + 1}_{int(datetime.now().timestamp() * 1000) % 100000}"
            opts.append({"id": nid, "label": lb, "color": OPTION_COLOR_ORDER[len(opts) % len(OPTION_COLOR_ORDER)],
                         "order": len(opts)})
            by_label[lb] = nid
            ids.append(nid)
            changed = True
    if changed:
        field.options = {**(field.options or {}), "options": opts}
        flag_modified(field, "options")
        db.commit()
    return ids


def coerce_basic(out_type: str, value):
    """非选项类输出的类型归一（数字 / 复选框 / 文本）。"""
    if value in (None, "", []):
        return None
    if out_type == "number":
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return value
        try:
            return float(str(value).replace(",", "").strip())
        except ValueError:
            m = re.search(r"-?\d+(\.\d+)?", str(value))
            return float(m.group(0)) if m else None
    if out_type == "checkbox":
        return value is True or str(value).strip().lower() in ("true", "1", "是", "yes", "√", "✓")
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)[:5000]


def coerce_output(db: Session, field: MetaField, value):
    cfg = field.options or {}
    out_type = cfg.get("outputType") or "text"
    if out_type in ("singleSelect", "multiSelect"):
        if value in (None, "", []):
            return None
        labels = value if isinstance(value, list) else [value]
        ids = _ensure_options(db, field, [str(x) for x in labels], cfg.get("allowNewOptions", True))
        if out_type == "singleSelect":
            return ids[0] if ids else None
        return ids
    return coerce_basic(out_type, value)


# ---------- 单元格计算 ----------

def _image_bytes(db: Session, value) -> list[bytes]:
    from . import images
    out = []
    for fid in (value if isinstance(value, list) else [value])[:4]:
        try:
            _, path = images.get_image(db, str(fid.get("id") if isinstance(fid, dict) else fid))
            out.append(path.read_bytes())
        except Exception:  # noqa: BLE001
            continue
    return out


def _file_text(record: dict, inputs: list[str], max_chars: int = 12000) -> str:
    from . import smart_files
    texts = []
    for fn in inputs:
        for v in record.get(fn) or []:
            fid = v.get("id") if isinstance(v, dict) else v
            texts.append(smart_files.pdf_text(str(fid)))
    return "\n\n".join(t for t in texts if t)[:max_chars]


def compute_raw(db: Session, cfg: dict, fields: list, record: dict, labels: list[str], all_records=None) -> tuple:
    """按配置计算单元格原始结果 → (raw, billable, tokens)。选项类返回标签名（尚未落成 optionId）。"""
    from .ai_local import LOCAL
    from .llm import get_default_provider
    scene_key = cfg.get("scene") or "custom"
    scene = SCENE_BY_KEY.get(scene_key, SCENE_BY_KEY["custom"])
    if scene.get("disabled"):
        raise ValueError(f"「{scene['label']}」需要工具调用能力，即将上线")
    inputs = [x for x in cfg.get("inputFields") or [] if _field_by(fields, x)]
    first = record.get(inputs[0]) if inputs else None
    if scene_key == "markDuplicate":
        if not inputs:
            raise ValueError("请选择要查重的字段")
        if first in (None, "", []):
            return False, False, 0
        key = json.dumps(first, sort_keys=True, default=str, ensure_ascii=False)
        cnt = sum(1 for r in all_records or [] if json.dumps(r.get(inputs[0]), sort_keys=True, default=str,
                                                             ensure_ascii=False) == key)
        return cnt > 1, False, 0
    if scene_key == "pdfToText":
        if not inputs:
            raise ValueError("请选择 PDF 所在的文件字段")
        return _file_text(record, inputs, 20000) or None, False, 0
    if scene_key in LOCAL:
        fn, needs_input = LOCAL[scene_key]
        if needs_input and first in (None, "", []):
            return None, False, 0
        return fn(first), False, 0
    provider = get_default_provider(db)
    system, user = build_prompt_cfg(db, cfg, fields, record, labels)
    if scene["input"] == "image":
        imgs = []
        for fn in inputs:
            imgs += _image_bytes(db, record.get(fn))
        if not imgs:
            return None, False, 0
        text = provider.recognize(imgs, user, system=system)
    else:
        if not any(record.get(fn) not in (None, "", []) for fn in inputs) and scene_key != "custom":
            return None, False, 0   # 输入全空不调用模型（不计配额）
        if scene["input"] == "file":
            user += "\n\n文件内容：\n" + (_file_text(record, inputs) or "（无可识别文字）")
        text = provider.complete(user, system=system)
    usage = provider.last_usage or {}
    tokens = int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)
    return _parse_value(text), True, tokens


def compute_cell(db: Session, field: MetaField, fields: list, record: dict, all_records=None) -> tuple:
    """返回 (value, billable, tokens)；选项类结果落成 optionId（允许时自动建选项）。"""
    labels = [o.get("label") for o in _options_of(field)]
    raw, billable, tokens = compute_raw(db, field.options or {}, fields, record, labels, all_records)
    return coerce_output(db, field, raw), billable, tokens


def _run_row(db: Session, table_id: int, fn: str, rid: int) -> SmartAiRun:
    row = db.query(SmartAiRun).filter_by(table_id=table_id, field_name=fn, record_id=rid).first()
    if row is None:
        mt = db.get(MetaTable, table_id)
        row = SmartAiRun(table_id=table_id, tenant_id=mt.tenant_id if mt else None, field_name=fn, record_id=rid)
        db.add(row)
    return row


def process(db: Session, table_id: int, field_name: str, record_ids: list[int], preserve_editor: bool = False) -> None:
    mt = db.get(MetaTable, table_id)
    if not mt:
        return
    fields = get_meta_fields(db, table_id)
    field = _field_by(fields, field_name)
    if field is None or field.field_type != "ai":
        return
    all_recs = None
    if (field.options or {}).get("scene") == "markDuplicate":
        all_recs = json_store.all_dicts(db, table_id, fields)
    for rid in record_ids:
        run = _run_row(db, table_id, field_name, rid)
        try:
            record = json_store.get_record(db, table_id, rid, fields)
        except HTTPException:
            db.delete(run)
            db.commit()
            continue
        run.status, run.error = "running", None
        db.commit()
        try:
            scene = SCENE_BY_KEY.get((field.options or {}).get("scene") or "custom", SCENE_BY_KEY["custom"])
            if not preserve_editor and not _is_local(scene) and scene["key"] != "custom":
                inputs = [f for f in fields if f.field_name in ((field.options or {}).get("inputFields") or [])]
                if not inputs:
                    raise ValueError("请先在 AI 字段设置中选择输入字段")
                if not any(record.get(f.field_name) not in (None, "", []) for f in inputs):
                    names = "、".join(f"「{f.label or f.field_name}」" for f in inputs)
                    raise ValueError(f"本行输入为空，请先填写{names}后重新生成")
            if not _is_local(scene) and not _quota_ok(db, mt.tenant_id):
                raise ValueError("本月 AI 调用次数已用完，请升级套餐")
            field = db.get(MetaField, field.id)   # 选项可能被上一行新建，重新取
            value, billable, tokens = compute_cell(db, field, fields, record, all_recs)
            before = record
            if before.get(field_name) != value:
                after = json_store.update_record(db, mt, get_meta_fields(db, table_id), rid, {field_name: value},
                                                 user="AI", editor_id=None, actor_type="ai",
                                                 allow_fields={field_name}, preserve_editor=preserve_editor)
                smart_events.record_updated(db, mt, before, after, [field_name], actor_type="ai")
            run = _run_row(db, table_id, field_name, rid)
            run.status, run.billable, run.tokens_used = "ok", billable, tokens
            db.commit()
        except Exception as e:  # noqa: BLE001 — 单格失败不影响其余行
            db.rollback()
            run = _run_row(db, table_id, field_name, rid)
            run.status = "error"
            run.error = str(e.detail if isinstance(e, HTTPException) else e)[:500]
            db.commit()


def enqueue(db: Session, table_id: int, field_name: str, record_ids: list[int], preserve_editor: bool = False) -> int:
    ids = list(dict.fromkeys(int(x) for x in record_ids))[:MAX_BATCH]
    for rid in ids:
        run = _run_row(db, table_id, field_name, rid)
        run.status, run.error = "pending", None
    db.commit()
    if ids:
        smart_events.submit(process, table_id, field_name, ids, preserve_editor=preserve_editor)
    return len(ids)


def handle_event(db: Session, event: dict) -> None:
    """新增行 / 输入字段变更 → 自动重算开启了 autoUpdate 的 AI 字段。"""
    fields = get_meta_fields(db, event["table_id"])
    for f in fields:
        if f.field_type != "ai":
            continue
        cfg = f.options or {}
        if not cfg.get("autoUpdate", True):
            continue
        inputs = set(cfg.get("inputFields") or [])
        if event["type"] == "recordUpdated" and not inputs & set(event.get("changed") or []):
            continue
        if event["type"] == "recordCreated":
            after = event.get("after") or {}
            if not any(after.get(x) not in (None, "", []) for x in inputs):
                continue
        if cfg.get("scene") == "markDuplicate":
            ids = [r.id for r in db.query(Record.id).filter_by(table_id=event["table_id"]).all()]
        else:
            ids = [event["record_id"]]
        # Derived updates must not replace the author of the user's edit/copy/paste.
        # Explicit AI generation uses enqueue's default and still records an AI author.
        enqueue(db, event["table_id"], f.field_name, ids, preserve_editor=True)


def attach_status(db: Session, table_id: int, fields: list, rows: list[dict]) -> None:
    """网格行附加 AI 单元格状态：row.__ai = {field_name: {status, error}}（仅生成中/失败）。"""
    ai_fields = [f.field_name for f in fields if f.field_type == "ai"]
    if not ai_fields or not rows:
        return
    ids = {r.get("id") for r in rows}
    runs = (db.query(SmartAiRun).filter(SmartAiRun.table_id == table_id, SmartAiRun.field_name.in_(ai_fields),
                                        SmartAiRun.status.in_(("pending", "running", "error"))).all())
    by_row: dict = {}
    for run in runs:
        if run.record_id in ids:
            by_row.setdefault(run.record_id, {})[run.field_name] = {"status": run.status, "error": run.error}
    for r in rows:
        if r.get("id") in by_row:
            r["__ai"] = by_row[r["id"]]


# ---------- AI 生成公式（§9 与公式编辑器打通） ----------

def _formula_system() -> str:
    from .formula_funcs import FUNCTIONS
    funcs = "\n".join(f"- {f['signature']}：{f['desc']}" for f in FUNCTIONS.values())
    return ("你是智能表格的公式专家。根据用户描述写出一个 Excel 风格的公式。\n"
            "语法：+ - * / 运算、& 拼接文本、比较 = <> > >= < <=；字符串用双引号；TRUE/FALSE；\n"
            "字段引用一律写成 [字段名]（用下方给出的字段名原文）；单选/多选字段的值是选项文本。\n"
            f"可用函数：\n{funcs}\n"
            '以 JSON 返回：{"formula": "表达式", "returnType": "number" 或 "text" 或 "date", "explanation": "一句话说明"}，只输出 JSON。')


def generate_formula(db: Session, table_id: int, prompt: str) -> dict:
    from . import expr
    from .llm import get_default_provider
    from .llm.gateway import extract_json
    fields = [f for f in get_meta_fields(db, table_id) if (f.field_type or "") not in ("ai",)]
    desc = "\n".join(f"- {f.label}（{f.field_type or f.data_type}）" for f in fields)
    provider = get_default_provider(db)
    text = provider.complete(f"表格字段：\n{desc}\n\n需求：{prompt}", system=_formula_system())
    try:
        data = extract_json(text)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"AI 返回无法解析：{text[:200]}") from e
    display_formula = str(data.get("formula") or "").strip()
    by_label = {f.label: f.field_name for f in fields}

    def to_name(m):
        key = m.group(1).strip()
        return f"[{by_label.get(key, key)}]"
    stored = re.sub(r"\[([^\[\]]+)\]", to_name, display_formula)
    try:
        expr.parse(stored, allow_fields={f.field_name for f in fields})
    except expr.ExprError as e:
        raise HTTPException(422, f"AI 生成的公式校验未通过：{e}（{display_formula}）")
    return {"formula": stored, "display": display_formula,
            "returnType": data.get("returnType") if data.get("returnType") in ("number", "date") else "text",
            "explanation": str(data.get("explanation") or "")}


# ---------- AI 匹配标签（单选/多选列按来源列内容批量打标签） ----------

def match_tags(db: Session, mt: MetaTable, field: MetaField, source_fields: list[str], only_empty: bool,
               allow_new: bool, user_id: int | None) -> dict:
    from .llm import get_default_provider
    from .llm.gateway import extract_json
    fields = get_meta_fields(db, mt.id)
    sources = [x for x in source_fields if _field_by(fields, x)]
    if not sources:
        raise HTTPException(400, "请选择依据的字段")
    recs = json_store.all_dicts(db, mt.id, fields)
    todo = [r for r in recs if not only_empty or r.get(field.field_name) in (None, "", [])]
    todo = [r for r in todo if any(r.get(s) not in (None, "", []) for s in sources)][:200]
    if not todo:
        return {"updated": 0, "created_options": 0}
    q = quota_status(db, mt.tenant_id)
    if q["limit"] is not None and q["used"] >= q["limit"]:
        raise HTTPException(403, "本月 AI 调用次数已用完，请升级套餐")
    multi = field.field_type == "multiSelect"
    labels = [o.get("label") for o in _options_of(field)]
    items = [{"id": r["id"], "text": record_text(db, fields, r, sources)[:400]} for r in todo]
    system = ("你是一个文本分类专家。为每条记录匹配" + ("一个或多个标签" if multi else "一个分类") + "。"
              f"可选：{json.dumps(labels, ensure_ascii=False)}。"
              + ("若都不合适可给出新的简短名称。" if allow_new or not labels else "必须从可选项中选择。")
              + '以 JSON 返回：{"items": [{"id": 记录id, "value": ' + ('["标签"]' if multi else '"分类"') + '}]}，只输出 JSON。')
    provider = get_default_provider(db)
    text = provider.complete(json.dumps(items, ensure_ascii=False), system=system)
    try:
        data = extract_json(text)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"AI 返回无法解析：{text[:200]}") from e
    before_opts = len(_options_of(field))
    cfg_backup = dict(field.options or {})
    field.options = {**cfg_backup, "outputType": field.field_type, "allowNewOptions": allow_new}
    updated = 0
    for it in data.get("items") or []:
        rid = it.get("id")
        if not isinstance(rid, int) or rid not in {r["id"] for r in todo}:
            continue
        vals = it.get("value")
        ids = _ensure_options(db, field, [str(x) for x in (vals if isinstance(vals, list) else [vals])], allow_new)
        if not ids:
            continue
        value = ids if multi else ids[0]
        before = json_store.get_record(db, mt.id, rid, fields)
        after = json_store.update_record(db, mt, get_meta_fields(db, mt.id), rid, {field.field_name: value},
                                         user="AI", editor_id=None, actor_type="ai")
        smart_events.record_updated(db, mt, before, after, [field.field_name], actor_type="ai")
        updated += 1
    # 恢复字段 config（outputType/allowNewOptions 只是复用 _ensure_options 的临时键），保留新增选项
    field = db.get(MetaField, field.id)
    opts = (field.options or {}).get("options")
    field.options = {**cfg_backup, "options": opts}
    flag_modified(field, "options")
    run = SmartAiRun(table_id=mt.id, tenant_id=mt.tenant_id, field_name=f"__tags_{field.field_name}",
                     record_id=-int(datetime.now().timestamp()), status="ok", billable=True,
                     tokens_used=sum(int(v or 0) for v in (provider.last_usage or {}).values()))
    db.add(run)
    db.commit()
    return {"updated": updated, "created_options": len(opts or []) - before_opts}


# ---------- AI 配置生成 + 效果预览（参照 添加列/AI字段：选场景 → 选字段/补充描述 → 正在配置… → 结果确认） ----------

PREVIEW_ROWS = 3


def _is_local(scene: dict) -> bool:
    from .ai_local import LOCAL
    return bool(scene.get("local")) or scene["key"] in LOCAL


def _config_system() -> str:
    return ("你是智能表格「AI 字段」的配置助手。用户选了一个场景、输入字段，并可能补充了描述或修改要求。"
            "请据此生成该 AI 字段的配置。\n"
            '以 JSON 返回：{"title": "字段标题，12 字以内，如「产品名称分类」", '
            '"desc": "一句话说明这个字段做什么，引用字段时写成 [字段名]", '
            '"inputLabel": "输入字段在任务中的角色，如「待分类的产品名称」", '
            '"prompt": "给模型的提示词，三行：你是一个……。\\n任务：……\\n输入：……", '
            '"outputType": "text / number / singleSelect / multiSelect / checkbox 之一", '
            '"options": ["仅单选/多选时给出 3-6 个候选选项，否则为空数组"], '
            '"inputs": ["需要用到的字段名（必须来自表格字段列表）"]}。只输出 JSON。')


def _template_config(scene: dict, inputs: list, base: dict) -> dict:
    lb = inputs[0].label if inputs else "文本"
    desc = (base.get("desc") or scene["desc"]).replace("{input}", f"[{lb}]")
    title = base.get("title") or (f"{lb}{scene['label']}" if scene["key"] != "custom" and len(lb) <= 8 else scene["label"])
    return {"title": title[:20], "desc": desc, "inputLabel": base.get("inputLabel") or f"待处理的{lb}",
            "prompt": base.get("systemPrompt") or scene.get("prompt") or "", "options": [], "inputs": []}


def _llm_config(db: Session, scene: dict, fields: list, inputs: list, instruction: str, base: dict) -> dict:
    from .llm import get_default_provider
    from .llm.gateway import extract_json
    flist = "\n".join(f"- {f.label}（{f.field_type or f.data_type}）" for f in fields if f.field_type != "ai")
    parts = [f"场景：{scene['label']}", f"场景说明：{scene['desc'].replace('{input}', '[输入字段]')}",
             f"场景默认提示词：\n{scene.get('prompt') or ''}",
             f"默认输出类型：{scene['outputType']}", f"表格字段：\n{flist}",
             f"用户选择的输入字段：{', '.join(f.label for f in inputs) or '（未选择，请从表格字段中挑选最合适的）'}"]
    if base.get("systemPrompt"):
        parts.append(f"当前配置：标题={base.get('title')}；提示词=\n{base['systemPrompt']}\n输出类型={base.get('outputType')}；"
                     f"选项={[o.get('label') for o in base.get('options') or []]}")
        parts.append(f"修改要求：{instruction or '（无）'}")
    else:
        parts.append(f"用户补充描述：{instruction or '（无）'}")
    provider = get_default_provider(db)
    text = provider.complete("\n\n".join(parts), system=_config_system())
    data = extract_json(text)
    if not isinstance(data, dict):
        raise ValueError("AI 返回格式不正确")
    return data


def _assign_options(cfg: dict, labels) -> list[str]:
    """预览结果（标签名）→ 配置里的选项 id；新标签追加为候选选项（保存时才落库）。"""
    opts = cfg.setdefault("options", [])
    by_label = {str(o.get("label")).strip(): o["id"] for o in opts}
    ids = []
    for lb in labels if isinstance(labels, list) else [labels]:
        lb = str(lb or "").strip()[:30]
        if not lb:
            continue
        if lb not in by_label:
            if opts and not cfg.get("allowNewOptions", True):
                continue
            oid = f"opt_{len(opts) + 1}_{int(datetime.now().timestamp() * 1000) % 100000}"
            opts.append({"id": oid, "label": lb, "color": OPTION_COLOR_ORDER[len(opts) % len(OPTION_COLOR_ORDER)],
                         "order": len(opts)})
            by_label[lb] = oid
        ids.append(by_label[lb])
    return ids


def preview_rows(db: Session, mt: MetaTable, cfg: dict, fields: list, limit: int = PREVIEW_ROWS) -> list[dict]:
    """在真实数据的前几行（输入非空）上试算，生成「效果」表；不写记录、不落选项。"""
    inputs = [x for x in cfg.get("inputFields") or [] if _field_by(fields, x)]
    recs = json_store.all_dicts(db, mt.id, fields)
    scene = SCENE_BY_KEY.get(cfg.get("scene") or "custom", SCENE_BY_KEY["custom"])
    needs_input = not (scene["key"] in ("cvRandom", "cvUuid", "cvPassword"))
    sample = [r for r in recs if not needs_input or any(r.get(fn) not in (None, "", []) for fn in inputs)][:limit]
    out_type = cfg.get("outputType") or "text"
    rows = []
    for r in sample:
        item = {"record_id": r["id"], "inputs": {fn: r.get(fn) for fn in inputs}, "output": None, "error": None}
        try:
            labels = [o.get("label") for o in cfg.get("options") or []]
            raw, billable, tokens = compute_raw(db, cfg, fields, r, labels, recs)
            if out_type in ("singleSelect", "multiSelect"):
                ids = _assign_options(cfg, raw) if raw not in (None, "", []) else []
                item["output"] = (ids[0] if ids else None) if out_type == "singleSelect" else ids
            else:
                item["output"] = coerce_basic(out_type, raw)
            if billable:
                db.add(SmartAiRun(table_id=mt.id, tenant_id=mt.tenant_id, field_name="__preview",
                                  record_id=-int(datetime.now().timestamp() * 1000) % 2_000_000_000,
                                  status="ok", billable=True, tokens_used=tokens))
                db.commit()
        except Exception as e:  # noqa: BLE001 — 单行失败展示原因，不中断预览
            db.rollback()
            item["error"] = str(e.detail if isinstance(e, HTTPException) else e)[:200]
        rows.append(item)
    return rows


def configure(db: Session, mt: MetaTable, payload: dict) -> dict:
    """AI 配置：场景 + 输入字段 + 补充描述（或在已有配置上按修改要求调整）→ 配置 + 真实数据效果预览。"""
    scene = SCENE_BY_KEY.get(payload.get("scene") or "custom")
    if scene is None or scene.get("disabled") or scene.get("action"):
        raise HTTPException(400, "该场景暂不支持")
    editing = payload.get("field_name")
    fields = [f for f in get_meta_fields(db, mt.id) if f.field_name != editing]
    base = dict(payload.get("base") or {})
    inputs = [f for fn in payload.get("input_fields") or [] for f in [_field_by(fields, fn)] if f]
    instruction = str(payload.get("instruction") or "").strip()[:1000]
    if not _is_local(scene) and not _quota_ok(db, mt.tenant_id):
        raise HTTPException(403, "本月 AI 调用次数已用完，请升级套餐")
    warning = None
    gen = _template_config(scene, inputs, base)
    if not _is_local(scene):
        try:
            got = _llm_config(db, scene, fields, inputs, instruction, base)
            gen.update({k: v for k, v in got.items() if v not in (None, "", [])})
        except Exception as e:  # noqa: BLE001 — 模型不可用：回落到场景模板，仍可保存
            log.warning("AI 字段配置生成失败，使用场景模板：%s", e)
            warning = f"AI 配置生成失败，已使用场景默认配置（{str(e)[:80]}）"
    if not inputs:   # 未选字段：用模型挑的（标签 → 字段名）
        by_label = {f.label: f for f in fields if f.field_type != "ai"}
        inputs = [by_label[x] for x in gen.get("inputs") or [] if x in by_label]
    if not inputs and scene["key"] not in ("cvRandom", "cvUuid", "cvPassword"):
        raise HTTPException(400, f"请提供要「{scene['label']}」的字段")
    out_type = payload.get("output_type") or base.get("outputType")
    if not out_type:
        out_type = gen.get("outputType") if scene["key"] == "custom" else scene["outputType"]
    if out_type not in ("text", "number", "singleSelect", "multiSelect", "checkbox"):
        out_type = "text"
    cfg = {
        "scene": scene["key"], "inputFields": [f.field_name for f in inputs],
        "title": str(gen.get("title") or scene["label"])[:20], "desc": str(gen.get("desc") or ""),
        "inputLabel": str(gen.get("inputLabel") or "")[:30],
        "systemPrompt": "" if _is_local(scene) else str(gen.get("prompt") or scene.get("prompt") or ""),
        "instruction": instruction if not base.get("systemPrompt") else base.get("instruction", ""),
        "outputType": out_type, "autoUpdate": base.get("autoUpdate", True),
        "allowNewOptions": base.get("allowNewOptions", True),
        "options": [dict(o) for o in base.get("options") or []],
    }
    if out_type in ("singleSelect", "multiSelect") and not cfg["options"]:
        seeds = scene.get("defaultOptions") or [str(x) for x in gen.get("options") or []][:8]
        for lb in seeds:
            _assign_options(cfg, lb)
    rows = preview_rows(db, mt, cfg, get_meta_fields(db, mt.id))
    return {"config": cfg, "preview": rows, "warning": warning, "quota": quota_status(db, mt.tenant_id)}


def scene_catalog() -> dict:
    return {"categories": CATEGORIES, "scenes": SCENES}
