"""打印模板的字段识别辅助函数（起始模板生成用：挑单号/日期/金额列）。

系统不再自动播种默认模板；新建模板从起始模板或模板库起步。
"""
from ..models import MetaField

_DATE_PREFER = ("发货", "送货", "delivery", "deliver")
_NO_HINTS = ("no", "code", "单号", "编号")
_PRICE_HINTS = ("单价", "price")
_AMOUNT_HINTS = ("金额", "amount", "合计", "小计")


def _match(rule_keywords, *texts: str) -> bool:
    blob = " ".join(t for t in texts if t).lower()
    return any(k in blob for k in rule_keywords)


def _pick_no_field(fields: list[MetaField]) -> str:
    for f in fields:
        if f.data_type == "serial":
            return f.field_name
    for f in fields:
        if f.data_type == "varchar" and _match(_NO_HINTS, f.field_name, f.label):
            return f.field_name
    return ""


def _pick_date_field(fields: list[MetaField]) -> str:
    dates = [f for f in fields if f.data_type in ("date", "datetime")]
    for f in dates:
        if _match(_DATE_PREFER, f.field_name, f.label):
            return f.field_name
    return dates[0].field_name if dates else ""


