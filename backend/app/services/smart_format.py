"""智能表字段值 → 人类可读文本（自动化消息变量渲染、AI 字段提示词组装共用）。

记录里存的是 ID（选项 optionId、人员 userId、附件 id），展示/喂给模型前需翻译成标签。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import User


def option_map(field) -> dict[str, str]:
    return {str(o.get("id")): str(o.get("label") or "") for o in (field.options or {}).get("options") or []
            if isinstance(o, dict)}


def _user_name(db: Session, uid, cache: dict) -> str:
    if uid in ("__ai__",):
        return "AI 生成"
    if uid in ("__automation__",):
        return "自动化"
    key = str(uid)
    if key not in cache:
        u = db.get(User, int(uid)) if key.isdigit() else None
        cache[key] = u.username if u else key
    return cache[key]


def display(db: Session, field, value, cache: dict | None = None) -> str:
    cache = cache if cache is not None else {}
    if value is None or value == "" or value == []:
        return ""
    ft = getattr(field, "field_type", None) or ""
    if ft == "ai":
        ft = (field.options or {}).get("outputType", "text")
    if ft in ("singleSelect", "multiSelect"):
        opts = option_map(field)
        vals = value if isinstance(value, list) else [value]
        return "、".join(opts.get(str(v), str(v)) for v in vals)
    if ft in ("member", "createdBy", "lastModifiedBy"):
        vals = value if isinstance(value, list) else [value]
        return "、".join(_user_name(db, v.get("id") if isinstance(v, dict) else v, cache) for v in vals)
    if ft == "checkbox":
        return "是" if value in (True, 1, "1", "true") else "否"
    if ft == "url":
        if isinstance(value, dict):
            return str(value.get("text") or value.get("url") or "")
        return str(value)
    if ft in ("image", "file"):
        vals = value if isinstance(value, list) else [value]
        names = [str(v.get("name") or v.get("id")) if isinstance(v, dict) else str(v) for v in vals]
        return f"{len(names)} 个附件" if ft == "image" else "、".join(names)
    if ft == "relation":
        vals = value if isinstance(value, list) else [value]
        return "、".join(f"#{v}" for v in vals)
    if isinstance(value, list):
        return "、".join(str(v) for v in value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def record_text(db: Session, fields: list, record: dict, only: list[str] | None = None) -> str:
    """整行 → 「字段名：值」多行文本（AI 总结、消息正文用）。"""
    cache: dict = {}
    lines = []
    for f in fields:
        if only is not None and f.field_name not in only:
            continue
        v = display(db, f, record.get(f.field_name), cache)
        if v:
            lines.append(f"{f.label}：{v}")
    return "\n".join(lines)
