"""Deterministic template execution. Roles are explicit field mappings, never guessed by an LLM."""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta, timezone

from .ai_local import _date, _num

SHANGHAI = timezone(timedelta(hours=8))
AGGREGATES = {"memberTaskCount", "memberWorkload", "taskCompletion", "mkRank", "hrLeaveUsed", "stTotalHours"}


def number(value):
    n = _num(value)
    return n if n is not None and math.isfinite(n) else None


def day(value):
    if isinstance(value, str):
        value = re.sub(r"(\d{4})年(\d{1,2})月(\d{1,2})日?", r"\1-\2-\3", value)
        m = re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", value)
        if m:
            value = m.group()
    d = _date(value)
    return d.date() if d else None


def _json_values(value):
    obj = json.loads(str(value))
    result = []
    def walk(v, prefix=""):
        if isinstance(v, dict):
            for k, item in v.items():
                walk(item, f"{prefix}.{k}" if prefix else str(k))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                walk(item, f"{prefix}[{i}]")
        else:
            result.append(f"{prefix}: {json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v}")
    walk(obj)
    return "\n".join(result)


def _gender(value):
    text = str(value or "").strip().upper()
    if not re.fullmatch(r"\d{17}[\dX]", text):
        return None
    if not day(f"{text[6:10]}-{text[10:12]}-{text[12:14]}"):
        return None
    weights = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
    if "10X98765432"[sum(int(n) * w for n, w in zip(text, weights)) % 11] != text[-1]:
        return None
    return "男" if int(text[16]) % 2 else "女"


def _fans(value):
    s = str(value or "").strip().lower().replace(",", "")
    n = number(s)
    if n is None or n < 0:
        return None
    n *= 10000 if "万" in s or "w" in s else 1000 if "k" in s else 1
    return "头部(100万+)" if n >= 1e6 else "腰部(10-100万)" if n >= 1e5 else "尾部(1-10万)" if n >= 1e4 else "素人(<1万)"


def scalar(key, value):
    text = str(value or "")
    if key == "exEmail":
        return ", ".join(dict.fromkeys(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text))) or None
    if key == "exLink":
        return ", ".join(dict.fromkeys(v.rstrip(".,;，。；）)") for v in re.findall(r"https?://[^\s<>\"'，。；]+", text))) or None
    if key == "exFirstNumber":
        return number(value)
    if key == "exJson":
        try:
            return _json_values(value)
        except (ValueError, TypeError):
            raise ValueError("输入不是有效的 JSON") from None
    if key == "exDate":
        d = day(value)
        return d.isoformat() if d else None
    if key == "cvPinyin":
        from pypinyin import lazy_pinyin
        return "".join(lazy_pinyin(text))
    if key == "hrGender":
        return _gender(value)
    if key == "mkFans":
        return _fans(value)
    if key in ("cvHoliday", "hrHolidayQuery"):
        from chinese_calendar import get_holiday_detail, is_workday
        d = day(value)
        if not d:
            return None
        try:
            off, name = get_holiday_detail(d)
            work = is_workday(d)
        except NotImplementedError:
            raise ValueError("该年份的节假日安排尚未收录，请更新 chinese-calendar 数据") from None
        names = {"New Year's Day": "元旦", "Spring Festival": "春节", "Tomb-sweeping Day": "清明节", "Labour Day": "劳动节", "Dragon Boat Festival": "端午节", "National Day": "国庆节", "Mid-autumn Festival": "中秋节"}
        return not work if key == "cvHoliday" else names.get(name, name) or ("工作日" if work else "周末")
    if key == "cvLunar":
        from lunardate import LunarDate
        d = day(value)
        if not d:
            return None
        if not 1900 <= d.year < 2100:
            raise ValueError("农历转换支持 1900—2099 年")
        ld = LunarDate.fromSolarDate(d.year, d.month, d.day)
        return f"{ld.year}-{ld.month:02d}-{ld.day:02d}" + ("（闰月）" if ld.isLeapMonth else "")
    raise ValueError(f"未知的本地模板：{key}")


SCALARS = {"exEmail", "exLink", "exFirstNumber", "exJson", "exDate", "cvPinyin", "hrGender", "mkFans", "cvHoliday", "hrHolidayQuery", "cvLunar"}
ROW_SCENES = {"workdays", "taskStatus", "deadlineCountdown", "cvBmi", "cvBmr", "hrAge", "hrSeniority", "hrContract", "pdDefect", "pdHours", "pdStock", "pdTicketTime", "pdStockAlert", "stAttendance", "stHours", "stHealthDays", "stHealthExpiry", "orderShippingStatus"} | AGGREGATES


def compute(key, cfg, record, records, today=None):
    today = today or datetime.now(SHANGHAI).date()
    from .ai_scenes import SCENE_BY_KEY
    roles = SCENE_BY_KEY[key].get("inputRoles", [])
    mapping = cfg.get("inputBindings") or {}
    inputs = cfg.get("inputFields") or []
    def field(role):
        index = next((i for i, r in enumerate(roles) if r["key"] == role), -1)
        return mapping.get(role) or (inputs[index] if not mapping and 0 <= index < len(inputs) else None)
    def get(role, row=None):
        return (record if row is None else row).get(field(role))
    def num(role):
        return number(get(role))
    def date(role):
        return day(get(role))
    if key in AGGREGATES:
        if records is None:
            raise ValueError("该模板需要当前表的全部记录")
        group = get("group")
        if key == "mkRank":
            n = num("value")
            return None if n is None else 1 + sum(number(get("value", r)) is not None and number(get("value", r)) > n for r in records)
        if group in (None, "", []):
            return None
        rows = [r for r in records if get("group", r) == group or (isinstance(group, list) and isinstance(get("group", r), list) and set(map(str, group)) & set(map(str, get("group", r))))]
        if key == "memberTaskCount":
            return len(rows)
        if key == "taskCompletion":
            return round(100 * sum(get("status", r) == "已完成" for r in rows) / len(rows), 2) if rows else None
        if key == "hrLeaveUsed":
            rows = [r for r in rows if day(get("date", r)) and day(get("date", r)).year == today.year]
        values = [number(get("value", r)) for r in rows]
        return round(sum(v for v in values if v is not None), 2)
    if key == "workdays":
        start, end = date("start"), date("end")
        if not start or not end:
            return None
        if end < start:
            raise ValueError("结束日期不能早于开始日期")
        if (end - start).days > 3660:
            raise ValueError("工作日计算区间不能超过 10 年")
        from chinese_calendar import is_workday
        try:
            return sum(is_workday(start + timedelta(days=i)) for i in range((end - start).days + 1))
        except NotImplementedError:
            raise ValueError("计算区间包含尚未收录节假日安排的年份") from None
    if key == "taskStatus":
        return "已完成" if date("done") else "未开始" if not date("start") else "已延期" if date("end") and date("end") < today else "进行中"
    if key in ("deadlineCountdown", "stHealthDays"):
        d = date("end")
        if not d:
            return None
        days = (d - today).days
        return days if key == "stHealthDays" else f"剩余 {days} 天" if days >= 0 else f"已逾期 {-days} 天"
    if key in ("hrAge", "hrSeniority"):
        start = date("start")
        if not start or start > today:
            return None
        return today.year - start.year - ((today.month, today.day) < (start.month, start.day)) if key == "hrAge" else round((today - start).days / 365.25, 1)
    if key == "hrContract":
        d = date("end")
        return None if not d else "已到期" if d < today else "即将到期" if (d - today).days <= 30 else "生效中"
    if key == "stHealthExpiry":
        d = date("start")
        if not d:
            return None
        try:
            return d.replace(year=d.year + 1).isoformat()
        except ValueError:
            return d.replace(year=d.year + 1, day=28).isoformat()
    if key == "orderShippingStatus":
        ordered, shipped = date("start"), date("end")
        if ordered and shipped and shipped < ordered:
            raise ValueError("发货日期不能早于下单日期")
        return "待发货" if not shipped else None if not ordered else "延迟发货" if (shipped - ordered).days > 1 else "已发货"
    if key in ("cvBmi", "cvBmr"):
        height, weight = num("height"), num("weight")
        if height is None or weight is None:
            return None
        if height <= 0 or weight <= 0:
            raise ValueError("身高（厘米）和体重（千克）必须大于 0")
        if key == "cvBmi":
            return round(weight / (height / 100) ** 2, 1)
        age, gender = num("age"), get("gender")
        if age is None or age < 0 or gender not in ("男", "女"):
            return None
        return round(10 * weight + 6.25 * height - 5 * age + (5 if gender == "男" else -161))
    if key in ("pdTicketTime", "stHours"):
        start, end = _date(get("start")), _date(get("end"))
        if not start or not end:
            return None
        start = start.replace(tzinfo=SHANGHAI) if start.tzinfo is None else start
        end = end.replace(tzinfo=SHANGHAI) if end.tzinfo is None else end
        if end < start:
            raise ValueError("结束时间不能早于开始时间")
        return round((end - start).total_seconds() / 3600, 2)
    if key == "pdStock":
        values = [num(r) for r in ("opening", "incoming", "outgoing")]
        return None if None in values else round(values[0] + values[1] - values[2], 4)
    if key == "pdStockAlert":
        stock, minimum = num("stock"), num("minimum")
        return None if stock is None or minimum is None else "缺货" if stock <= 0 else "偏低" if stock < minimum else "充足"
    a, b = num("value"), num("total")
    if a is None or b is None:
        return None
    if a < 0 or b < 0 or (b == 0 and key != "pdHours"):
        raise ValueError("数量不能为负，作为分母的总数必须大于 0")
    if key == "pdDefect":
        if a > b:
            raise ValueError("不良数不能大于批次总数")
        return round(a / b * 100, 2)
    if key == "stAttendance":
        return a / b >= .95
    if key == "pdHours":
        return round(a * b, 2)
    raise ValueError(f"未知的本地模板：{key}")
