"""智能表字段类型注册表（设计文档 §3）：12 种业务字段类型的后端单一事实来源。

每种类型注册：field_type 标识 → 底层 data_type/widget、默认 config、config 校验。
值存储约定：一律存 ID/原始标量不存展示值（选项存 optionId、人员存 userId、链接存 {url,text}）。
"""
from __future__ import annotations


class FieldTypeError(ValueError):
    """字段类型 config 校验失败（调用方按需包装为 MetaError/HTTPException）。"""


# 预设选项色板（单选/多选）
OPTION_COLORS = {
    "blue", "cyan", "green", "orange", "red", "purple", "pink", "yellow", "gray",
    "lightBlue", "lightGreen", "lightOrange", "lightPurple",
}

CURRENCY_CODES = {"CNY": "￥", "USD": "$", "EUR": "€", "JPY": "¥", "HKD": "HK$", "GBP": "£"}

DATE_FORMATS = ["yyyy-MM-dd", "yyyy/MM/dd", "yyyy年M月d日", "yyyy-MM-dd HH:mm", "yyyy年M月d日 HH:mm"]

ROW_HEIGHTS = {"default", "medium", "tall", "extraTall"}

# 视图筛选运算符（设计文档 §5.1），按字段类型族分发
OP_TEXT = ["contains", "notContains", "eq", "neq", "isEmpty", "isNotEmpty"]
OP_NUMBER = ["eq", "neq", "gt", "gte", "lt", "lte", "isEmpty", "isNotEmpty"]
OP_ENUM = ["contains", "notContains", "eq", "neq", "isEmpty", "isNotEmpty"]
OP_DATE = ["eq", "neq", "gt", "gte", "lt", "lte", "today", "pastDays", "withinDays", "isEmpty", "isNotEmpty"]
OP_BOOL = ["eq", "isEmpty", "isNotEmpty"]


def _num_config(precision="default", thousand=False, **extra):
    return {"precision": precision, "thousandSeparator": thousand, **extra}


# field_type → 注册项
FIELD_TYPES: dict[str, dict] = {
    "text": {
        "label": "文本", "data_type": "varchar", "widget": "input",
        "default_config": {}, "filter_ops": OP_TEXT, "aggregations": ["count"],
    },
    "singleSelect": {
        "label": "单选", "data_type": "varchar", "widget": "select",
        "default_config": {"options": [], "allowAddOptionWhenEditing": True},
        "filter_ops": OP_ENUM, "aggregations": ["count"],
    },
    "multiSelect": {
        "label": "多选", "data_type": "json", "widget": "select",
        "default_config": {"options": [], "allowAddOptionWhenEditing": True},
        "filter_ops": OP_ENUM, "aggregations": ["count"],
    },
    "number": {
        "label": "数字", "data_type": "decimal", "widget": "number",
        "default_config": _num_config(), "filter_ops": OP_NUMBER,
        "aggregations": ["count", "sum", "avg", "max", "min"],
    },
    "percent": {
        "label": "百分数", "data_type": "decimal", "widget": "number",
        "default_config": _num_config(), "filter_ops": OP_NUMBER,
        "aggregations": ["count", "sum", "avg", "max", "min"],
    },
    "currency": {
        "label": "货币", "data_type": "decimal", "widget": "number",
        "default_config": {"currencyCode": "CNY", "currencySymbol": "￥", "precision": 2, "thousandSeparator": True},
        "filter_ops": OP_NUMBER, "aggregations": ["count", "sum", "avg", "max", "min"],
    },
    "date": {
        "label": "日期", "data_type": "datetime", "widget": "datetime-picker",
        "default_config": {"format": "yyyy-MM-dd", "includeTime": False, "autoFillCreatedTime": False},
        "filter_ops": OP_DATE, "aggregations": ["count", "max", "min"],
    },
    "checkbox": {
        "label": "复选框", "data_type": "bool", "widget": "switch",
        "default_config": {"defaultChecked": False},
        "filter_ops": OP_BOOL, "aggregations": ["count"],
    },
    "url": {
        "label": "链接", "data_type": "json", "widget": "input",
        "default_config": {"displayStyle": "iconText"},
        "filter_ops": OP_TEXT, "aggregations": ["count"],
    },
    "phone": {
        "label": "电话", "data_type": "varchar", "widget": "input",
        "default_config": {}, "filter_ops": OP_TEXT, "aggregations": ["count"],
    },
    "email": {
        "label": "邮箱", "data_type": "varchar", "widget": "input",
        "default_config": {}, "filter_ops": OP_TEXT, "aggregations": ["count"],
    },
    "member": {
        "label": "人员", "data_type": "json", "widget": "input",
        "default_config": {"multiple": True, "notifyOnAdd": True},
        "filter_ops": OP_ENUM, "aggregations": ["count"],
    },
}

# 数字家族无损互转（共享 decimal 存储）
NUMBER_FAMILY = {"number", "percent", "currency"}


def default_config(field_type: str) -> dict:
    reg = FIELD_TYPES.get(field_type)
    return dict(reg["default_config"]) if reg else {}


def validate_field_type_config(field_type: str, config: dict, label: str = "") -> None:
    """按 field_type 校验 options 中的 config（建/改字段时把关）。非法抛 FieldTypeError。"""
    reg = FIELD_TYPES.get(field_type)
    if reg is None:
        raise FieldTypeError(f"字段「{label}」的字段类型不支持：{field_type}")
    cfg = config or {}
    prefix = f"字段「{label}」"

    if field_type in ("singleSelect", "multiSelect"):
        opts = cfg.get("options")
        if opts is not None:
            if not isinstance(opts, list):
                raise FieldTypeError(f"{prefix}的选项配置必须是数组")
            seen = set()
            for o in opts:
                if not isinstance(o, dict) or not o.get("id") or not str(o.get("label") or "").strip():
                    raise FieldTypeError(f"{prefix}的选项必须包含 id 和 label")
                if o["id"] in seen:
                    raise FieldTypeError(f"{prefix}的选项 id 重复：{o['id']}")
                seen.add(o["id"])
                if o.get("color") and o["color"] not in OPTION_COLORS:
                    raise FieldTypeError(f"{prefix}的选项颜色不支持：{o['color']}")

    if field_type in NUMBER_FAMILY:
        prec = cfg.get("precision", "default")
        if prec != "default" and not (isinstance(prec, int) and 0 <= prec <= 10):
            raise FieldTypeError(f"{prefix}的小数位数必须是 default 或 0~10")
        if field_type == "currency" and cfg.get("currencyCode", "CNY") not in CURRENCY_CODES:
            raise FieldTypeError(f"{prefix}的币种不支持：{cfg.get('currencyCode')}")

    if field_type == "date":
        fmt = cfg.get("format", "yyyy-MM-dd")
        if fmt not in DATE_FORMATS:
            raise FieldTypeError(f"{prefix}的日期格式不支持：{fmt}")

    if field_type == "member":
        for k in ("multiple", "notifyOnAdd"):
            if k in cfg and not isinstance(cfg[k], bool):
                raise FieldTypeError(f"{prefix}的 {k} 必须是布尔值")


def default_sheet_fields() -> list[dict]:
    """新建工作表的默认字段模板（设计文档 §2.5：文本/单选/人员/数字/日期）。"""
    return [
        {"field_type": "text", "label": "文本"},
        {"field_type": "singleSelect", "label": "单选",
         "config": {"options": [{"id": "opt_1", "label": "选项1", "color": "blue", "order": 0},
                                {"id": "opt_2", "label": "选项2", "color": "green", "order": 1},
                                {"id": "opt_3", "label": "选项3", "color": "orange", "order": 2}],
                    "allowAddOptionWhenEditing": True}},
        {"field_type": "member", "label": "人员"},
        {"field_type": "number", "label": "数字"},
        {"field_type": "date", "label": "日期"},
    ]


def to_field_in(field_type: str, label: str, field_name: str, config: dict | None = None) -> dict:
    """注册项 → FieldIn 字典（建表/加字段用）。"""
    reg = FIELD_TYPES[field_type]
    return {
        "field_name": field_name, "label": label,
        "data_type": reg["data_type"], "widget": reg["widget"],
        "options": config if config is not None else default_config(field_type),
        "field_type": field_type,
    }


def gen_field_name(existing: set[str]) -> str:
    """json 模式下 field_name 仅为 data 键：f_1 / f_2 … 递增。"""
    n = 1
    while f"f_{n}" in existing:
        n += 1
    return f"f_{n}"
