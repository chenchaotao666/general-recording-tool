"""AI 字段的本地确定性场景（不调用大模型、不计配额）：输入首列的值 → 结果。"""
from __future__ import annotations

import base64
import calendar
import random
import re
import secrets
import string
import uuid
from datetime import date, datetime

from dateutil import parser as date_parser


def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        m = re.search(r"-?\d+(\.\d+)?", str(v or ""))
        return float(m.group(0)) if m else None


def _date(v):
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v)
    try:
        return date_parser.parse(str(v))
    except (ValueError, OverflowError):
        return None


_DIGITS = "零壹贰叁肆伍陆柒捌玖"
_UNITS = ["", "拾", "佰", "仟"]
_BIG = ["", "万", "亿", "兆"]


def rmb_upper(v) -> str | None:
    n = _num(v)
    if n is None:
        return None
    neg = n < 0
    fen_total = round(abs(n) * 100)
    yuan, jiao, fen = fen_total // 100, fen_total // 10 % 10, fen_total % 10
    out = ""
    if yuan:
        groups = []
        while yuan:
            groups.append(yuan % 10000)
            yuan //= 10000
        parts = []
        zero_pending = False
        for gi in range(len(groups) - 1, -1, -1):
            g = groups[gi]
            if g == 0:
                zero_pending = True
                continue
            seg = ""
            for i in range(3, -1, -1):
                d = g // (10 ** i) % 10
                if d:
                    if zero_pending:
                        seg += "零"
                        zero_pending = False
                    seg += _DIGITS[d] + _UNITS[i]
                elif seg:
                    zero_pending = True
            if parts and g < 1000 and not seg.startswith("零"):
                seg = "零" + seg
            parts.append(seg + _BIG[gi])
            zero_pending = False
        out = "".join(parts).replace("零零", "零") + "元"
    if jiao or fen:
        if jiao:
            out += _DIGITS[jiao] + "角"
        elif out:
            out += "零"
        if fen:
            out += _DIGITS[fen] + "分"
    else:
        out = (out or "零元") + "整"
    return ("负" if neg else "") + out


def luhn_ok(v) -> bool:
    digits = re.sub(r"\D", "", str(v or ""))
    if len(digits) < 12:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
    return total % 10 == 0


def _password() -> str:
    pool = string.ascii_letters + string.digits + "!@#$%^&*-_"
    while True:
        p = "".join(secrets.choice(pool) for _ in range(16))
        if (any(c.islower() for c in p) and any(c.isupper() for c in p) and any(c.isdigit() for c in p)
                and any(c in "!@#$%^&*-_" for c in p)):
            return p


def _hex_rgb(v):
    m = re.fullmatch(r"#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})", str(v or "").strip())
    if not m:
        return None
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return f"rgb({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)})"


def _b64dec(v):
    try:
        return base64.b64decode(str(v).strip(), validate=False).decode("utf-8")
    except Exception:  # noqa: BLE001
        return None


def _month_end(v):
    d = _date(v)
    return None if d is None else d.day == calendar.monthrange(d.year, d.month)[1]


def _month_days(v):
    d = _date(v)
    return None if d is None else calendar.monthrange(d.year, d.month)[1]


def _unix(v):
    d = _date(v)
    return None if d is None else int(d.timestamp())


def _from_unix(v):
    n = _num(v)
    if n is None:
        return None
    if n > 1e11:   # 毫秒
        n /= 1000
    return datetime.fromtimestamp(n).strftime("%Y-%m-%d %H:%M:%S")


# 场景 key → (函数, 是否需要输入值)
LOCAL = {
    "cvMonthEnd": (_month_end, True),
    "cvRandom": (lambda v: random.randint(1, 100), False),
    "cvMileKm": (lambda v: None if _num(v) is None else round(_num(v) * 1.609344, 2), True),
    "cvRmbUpper": (rmb_upper, True),
    "cvUuid": (lambda v: str(uuid.uuid4()), False),
    "cvPassword": (lambda v: _password(), False),
    "cvHexRgb": (_hex_rgb, True),
    "cvMonthDays": (_month_days, True),
    "cvWordCount": (lambda v: len(re.sub(r"\s", "", str(v or ""))), True),
    "cvB64Enc": (lambda v: base64.b64encode(str(v).encode("utf-8")).decode("ascii"), True),
    "cvB64Dec": (_b64dec, True),
    "cvDateUnix": (_unix, True),
    "cvUnixDate": (_from_unix, True),
    "fnCardCheck": (luhn_ok, True),
}
