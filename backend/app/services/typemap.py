"""字段类型体系：本地类型推断、SQLAlchemy 类型映射、值转换。"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from dateutil import parser as dtparser
from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, Numeric, String, Text

DATA_TYPES = ["varchar", "text", "int", "decimal", "date", "datetime", "bool", "image"]
WIDGETS = ["input", "textarea", "number", "date-picker", "datetime-picker", "select", "switch", "image-uploader"]

DATE_FORMATS = [
    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日",
    "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y年%m月%d日 %H:%M:%S",
    "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y-%m", "%Y/%m",
]

BOOL_TRUE = {"是", "true", "1", "yes", "y", "对", "√"}
BOOL_FALSE = {"否", "false", "0", "no", "n", "错", "×"}

_INT_RE = re.compile(r"^-?\d{1,18}$")
_NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")

# Excel 序列日期范围：数字 1~2958465 对应 1900-01-01~9999-12-31；
# 纯数字字符串保守收窄到 20000~60000（1954~2064），避免把年份、数量误判成日期
_EXCEL_EPOCH = datetime(1899, 12, 30)


def _from_excel_serial(v) -> datetime | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) and 1 <= v <= 2958465:
        return _EXCEL_EPOCH + timedelta(days=float(v))
    if isinstance(v, str):
        s = v.strip()
        if s.isdigit() and 20000 <= int(s) <= 60000:
            return _EXCEL_EPOCH + timedelta(days=int(s))
    return None


def default_widget(data_type: str) -> str:
    return {
        "varchar": "input", "text": "textarea", "int": "number", "decimal": "number",
        "date": "date-picker", "datetime": "datetime-picker", "bool": "switch",
        "image": "image-uploader",
    }.get(data_type, "input")


def sa_column(field) -> Column:
    """按字段元数据（MetaField 或 FieldIn，属性同名即可）生成 SQLAlchemy Column。"""
    t = field.data_type
    if t == "varchar":
        col_type = String(field.length or 255)
    elif t == "text":
        col_type = Text()
    elif t == "int":
        col_type = BigInteger()
    elif t == "decimal":
        col_type = Numeric(18, 4)
    elif t == "date":
        col_type = Date()
    elif t == "datetime":
        col_type = DateTime()
    elif t == "bool":
        col_type = Boolean()
    elif t == "image":
        col_type = Text()   # 存图片 file_id 的 JSON 数组
    else:
        raise ValueError(f"不支持的字段类型：{t}")
    return Column(field.field_name, col_type, nullable=field.nullable, comment=field.label)


def try_parse_datetime(v) -> datetime | None:
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    # Excel 序列日期：单元格未设日期格式时，openpyxl 读出来是天数（1899-12-30 起）
    serial = _from_excel_serial(v)
    if serial is not None:
        return serial
    if not isinstance(v, str):
        return None
    s = v.strip()
    if not s or s.isdigit():   # 纯数字（超出序列日期范围）不当作日期
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return dtparser.parse(s, fuzzy=False)
    except (ValueError, OverflowError):
        return None


def _is_int(v) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    if isinstance(v, float):
        return v.is_integer()
    return bool(_INT_RE.match(str(v).strip().replace(",", "")))


def _is_num(v) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    return bool(_NUM_RE.match(str(v).strip().replace(",", "")))


def _is_bool(v) -> bool:
    if isinstance(v, bool):
        return True
    return str(v).strip().lower() in BOOL_TRUE | BOOL_FALSE


def infer_column_type(values: list) -> str:
    """本地统计推断：扫描一列的样例值给出类型建议（供 LLM 参考）。"""
    vals = [v for v in values if v not in (None, "")]
    if not vals:
        return "varchar"

    def ratio(fn) -> float:
        return sum(1 for v in vals if fn(v)) / len(vals)

    if len(vals) >= 2 and ratio(_is_bool) == 1.0 and len({str(v).strip() for v in vals}) <= 2:
        return "bool"
    if ratio(_is_int) >= 0.9:
        return "int"
    if ratio(_is_num) >= 0.9:
        return "decimal"
    if ratio(lambda v: try_parse_datetime(v) is not None) >= 0.9:
        dts = [try_parse_datetime(v) for v in vals[:20]]
        has_time = any(d and (d.hour or d.minute or d.second) for d in dts)
        return "datetime" if has_time else "date"
    max_len = max(len(str(v)) for v in vals)
    return "text" if max_len > 200 else "varchar"


def coerce_value(v, data_type: str, nullable: bool = True):
    """把原始值转换为字段类型。返回 (ok, value, error)。"""
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return (True, None, None) if nullable else (False, None, "不能为空")
    try:
        if data_type in ("varchar", "text"):
            return True, str(v), None
        if data_type == "int":
            if isinstance(v, bool):
                raise ValueError
            if isinstance(v, int):
                return True, v, None
            if isinstance(v, float):
                if v.is_integer():
                    return True, int(v), None
                raise ValueError
            return True, int(str(v).strip().replace(",", "")), None
        if data_type == "decimal":
            if isinstance(v, bool):
                raise ValueError
            return True, Decimal(str(v).strip().replace(",", "")), None
        if data_type == "date":
            dt = try_parse_datetime(v)
            if dt is None:
                raise ValueError
            return True, dt.date(), None
        if data_type == "datetime":
            dt = try_parse_datetime(v)
            if dt is None:
                raise ValueError
            return True, dt, None
        if data_type == "bool":
            if isinstance(v, bool):
                return True, v, None
            s = str(v).strip().lower()
            if s in BOOL_TRUE:
                return True, True, None
            if s in BOOL_FALSE:
                return True, False, None
            raise ValueError
        if data_type == "image":
            ids = v if isinstance(v, list) else [v]
            out = []
            for item in ids[:5]:   # 单字段最多 5 张
                if not isinstance(item, str) or not item.strip():
                    return False, None, "图片标识无效"
                out.append(item.strip())
            return (True, out or None, None) if out else (True, None, None)
        raise ValueError
    except (ValueError, InvalidOperation):
        return False, None, f"值「{v}」无法转换为 {data_type}"
