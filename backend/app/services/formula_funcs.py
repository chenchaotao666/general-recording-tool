"""智能表公式函数库（设计文档 §9.2）：Excel 风格大写函数 —— 校验（参数个数）、求值、编辑器文档共用一份目录。

与 expr.py 的关系：expr 负责解析/AST 白名单/运算符；这里只提供函数。
旧版小写函数（iff/coalesce/concat/round…）仍由 expr 内建实现，语义不变（报表/物理表 SQL 下推依赖）。

错误模型：函数内部遇到无法处理的输入抛 FormulaError(标题, 说明)，
严格模式（编辑器试算）原样展示给用户；保存/重算时（非严格）吞掉错误，单元格结果为空。
"""
from __future__ import annotations

import calendar
import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from dateutil import parser as date_parser


class FormulaError(ValueError):
    def __init__(self, title: str, message: str = ""):
        super().__init__(f"{title}：{message}" if message else title)
        self.title = title
        self.message = message


class Column(list):
    """整表引用的一整列取值（[#表.字段]）/ 整表记录（[#表]）。与多选等「单元格多值」区分：
    参与比较、四则运算、& 拼接时逐元素广播（[#表.城市]="北京" → 每行一个 TRUE/FALSE），供 FILTER/SUMIF 等使用。"""


WEEKDAY_SHORT = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
WEEKDAY_LONG = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


# ---------- 值规整 ----------

def is_blank(v) -> bool:
    return v is None or v == "" or (isinstance(v, (list, tuple)) and len(v) == 0)


def flatten(args) -> list:
    out = []
    for a in args:
        if isinstance(a, (list, tuple)):
            out.extend(flatten(a))
        else:
            out.append(a)
    return out


def show(v) -> str:
    """错误信息里引用值的写法。"""
    if isinstance(v, (list, tuple)):
        return "、".join(show(x) for x in v)
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def to_number(v, fn: str, idx: int, allow_blank: bool = True):
    """数字参数：数字原样，数字样式文本转换，空值按 0 / None。"""
    if v is None or v == "":
        return 0 if allow_blank else None
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        pct = s.endswith("%")
        try:
            n = float(s[:-1] if pct else s)
            return n / 100 if pct else (int(n) if n.is_integer() and "." not in s else n)
        except ValueError:
            pass
    if isinstance(v, (list, tuple)) and len(v) == 1:
        return to_number(v[0], fn, idx, allow_blank)
    kind = "运算" if not fn[:1].isalpha() else "函数"
    raise FormulaError("类型转换错误", f"“{fn}”{kind}中的第{idx}个参数需要数字值，但“{show(v)}”无法强制转换为数字。")


def to_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, dict):
        return "记录"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M") if (v.hour or v.minute) else v.strftime("%Y-%m-%d")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return "、".join(to_text(x) for x in v)
    return str(v)


def to_date(v, fn: str, idx: int):
    if v is None or v == "":
        return None
    if isinstance(v, (date, datetime)):
        return v
    if isinstance(v, str):
        try:
            d = date_parser.parse(v)
            return d if (d.hour or d.minute or d.second) else d.date()
        except (ValueError, OverflowError):
            pass
    if isinstance(v, (list, tuple)) and len(v) == 1:
        return to_date(v[0], fn, idx)
    raise FormulaError("类型转换错误", f"“{fn}”函数中的第{idx}个参数需要日期，但“{show(v)}”无法识别为日期。")


def to_bool(v) -> bool:
    if isinstance(v, str):
        return v.strip().upper() not in ("", "FALSE", "0", "否")
    if isinstance(v, (list, tuple)):
        return len(v) > 0
    return bool(v)


def _as_date(d):
    return d.date() if isinstance(d, datetime) else d


# ---------- 文本 ----------

def f_concat(*args):
    return "".join(to_text(a) for a in flatten(args))


def f_textjoin(sep, ignore_empty, *args):
    vals = flatten(args)
    if to_bool(ignore_empty):
        vals = [v for v in vals if not is_blank(v)]
    return to_text(sep).join(to_text(v) for v in vals)


def f_split(text, sep, index=None):
    parts = to_text(text).split(to_text(sep)) if to_text(sep) else list(to_text(text))
    if index is None:
        return parts
    i = int(to_number(index, "SPLIT", 3))
    return parts[i - 1] if 1 <= i <= len(parts) else ""


def f_substitute(text, old, new, nth=None):
    t, o, n = to_text(text), to_text(old), to_text(new)
    if not o:
        return t
    if nth is None:
        return t.replace(o, n)
    k = int(to_number(nth, "SUBSTITUTE", 4))
    pos = -1
    for _ in range(k):
        pos = t.find(o, pos + 1)
        if pos < 0:
            return t
    return t[:pos] + n + t[pos + len(o):]


def _fmt_number(n: float, fmt: str) -> str:
    pct = fmt.endswith("%")
    core = fmt[:-1] if pct else fmt
    if pct:
        n = n * 100
    decimals = len(core.split(".")[1]) if "." in core else 0
    s = f"{n:,.{decimals}f}" if "," in core else f"{n:.{decimals}f}"
    return s + ("%" if pct else "")


def _fmt_date(d, fmt: str) -> str:
    tokens = [("YYYY", lambda x: f"{x.year:04d}"), ("yyyy", lambda x: f"{x.year:04d}"),
              ("dddd", lambda x: WEEKDAY_LONG[x.weekday()]), ("ddd", lambda x: WEEKDAY_SHORT[x.weekday()]),
              ("YY", lambda x: f"{x.year % 100:02d}"), ("yy", lambda x: f"{x.year % 100:02d}"),
              ("MM", lambda x: f"{x.month:02d}"), ("DD", lambda x: f"{x.day:02d}"), ("dd", lambda x: f"{x.day:02d}"),
              ("HH", lambda x: f"{getattr(x, 'hour', 0):02d}"), ("hh", lambda x: f"{getattr(x, 'hour', 0):02d}"),
              ("mm", lambda x: f"{getattr(x, 'minute', 0):02d}"), ("ss", lambda x: f"{getattr(x, 'second', 0):02d}"),
              ("M", lambda x: str(x.month)), ("D", lambda x: str(x.day)), ("d", lambda x: str(x.day))]
    out, i = [], 0
    while i < len(fmt):
        for tok, fn in tokens:
            if fmt.startswith(tok, i):
                out.append(fn(d))
                i += len(tok)
                break
        else:
            out.append(fmt[i])
            i += 1
    return "".join(out)


def f_text(value, fmt):
    f = to_text(fmt)
    if value is None:
        return ""
    if isinstance(value, (date, datetime)) or (isinstance(value, str) and any(t in f for t in ("Y", "y", "D", "d", "M"))
                                               and not any(c in f for c in "0#")):
        d = to_date(value, "TEXT", 1)
        return _fmt_date(d, f) if d else ""
    if any(c in f for c in "0#"):
        return _fmt_number(float(to_number(value, "TEXT", 1)), f)
    return to_text(value)


def f_left(text, n=1):
    return to_text(text)[: max(int(to_number(n, "LEFT", 2)), 0)]


def f_right(text, n=1):
    k = max(int(to_number(n, "RIGHT", 2)), 0)
    return to_text(text)[-k:] if k else ""


def f_mid(text, start, n):
    s = max(int(to_number(start, "MID", 2)), 1)
    return to_text(text)[s - 1: s - 1 + max(int(to_number(n, "MID", 3)), 0)]


def f_find(sub, text, start=1):
    pos = to_text(text).find(to_text(sub), max(int(to_number(start, "FIND", 3)), 1) - 1)
    return pos + 1 if pos >= 0 else 0


def f_value(text):
    return to_number(text, "VALUE", 1, allow_blank=False)


# ---------- 数字 ----------

def _nums(args, fn):
    out = []
    for i, v in enumerate(flatten(args), start=1):
        if is_blank(v):
            continue
        out.append(to_number(v, fn, i))
    return out


def f_sum(*args):
    return sum(_nums(args, "SUM"))


def f_average(*args):
    ns = _nums(args, "AVERAGE")
    if not ns:
        raise FormulaError("除零错误", "“AVERAGE”函数没有可计算的数值。")
    return sum(ns) / len(ns)


def f_max(*args):
    ns = _nums(args, "MAX")
    return max(ns) if ns else 0


def f_min(*args):
    ns = _nums(args, "MIN")
    return min(ns) if ns else 0


def f_count(*args):
    n = 0
    for v in flatten(args):
        try:
            if not is_blank(v):
                to_number(v, "COUNT", 1)
                n += 1
        except FormulaError:
            pass
    return n


def f_counta(*args):
    return sum(1 for v in flatten(args) if not is_blank(v))


def f_round(x, n=0):
    v = to_number(x, "ROUND", 1)
    d = int(to_number(n, "ROUND", 2))
    q = Decimal(str(v)).quantize(Decimal(1).scaleb(-d), rounding="ROUND_HALF_UP") if d >= 0 else round(v, d)
    r = float(q)
    return int(r) if d <= 0 else r


def f_abs(x):
    return abs(to_number(x, "ABS", 1))


def f_int(x):
    return math.floor(to_number(x, "INT", 1))


def f_mod(x, y):
    b = to_number(y, "MOD", 2)
    if b == 0:
        raise FormulaError("除零错误", "“MOD”函数的除数不能为 0。")
    return to_number(x, "MOD", 1) % b


def f_power(x, y):
    return to_number(x, "POWER", 1) ** to_number(y, "POWER", 2)


def f_sqrt(x):
    v = to_number(x, "SQRT", 1)
    if v < 0:
        raise FormulaError("数值错误", "“SQRT”函数的参数不能为负数。")
    return math.sqrt(v)


def f_ceiling(x, sig=1):
    s = to_number(sig, "CEILING", 2) or 1
    return math.ceil(to_number(x, "CEILING", 1) / s) * s


def f_floor(x, sig=1):
    s = to_number(sig, "FLOOR", 2) or 1
    return math.floor(to_number(x, "FLOOR", 1) / s) * s


# ---------- 日期 ----------

def f_today():
    return date.today()


def f_now():
    return datetime.now().replace(microsecond=0)


def _date_part(name, attr):
    def fn(d):
        v = to_date(d, name, 1)
        return None if v is None else getattr(v, attr, 0)
    return fn


def f_date(y, m, d):
    try:
        return date(int(to_number(y, "DATE", 1)), int(to_number(m, "DATE", 2)), int(to_number(d, "DATE", 3)))
    except ValueError as e:
        raise FormulaError("日期错误", f"“DATE”函数无法生成有效日期：{e}")


def f_weekday(d, kind=2):
    v = to_date(d, "WEEKDAY", 1)
    if v is None:
        return None
    k = int(to_number(kind, "WEEKDAY", 2))
    wd = v.weekday()   # 周一=0
    return (wd + 1) % 7 + 1 if k == 1 else wd + 1   # 1：周日=1；2（默认）：周一=1


def f_datedif(start, end, unit="D"):
    a, b = to_date(start, "DATEDIF", 1), to_date(end, "DATEDIF", 2)
    if a is None or b is None:
        return None
    u = to_text(unit).upper()
    if u == 'S':
        zone = timezone(timedelta(hours=8))
        a = a if isinstance(a, datetime) else datetime.combine(a, datetime.min.time())
        b = b if isinstance(b, datetime) else datetime.combine(b, datetime.min.time())
        a = a.replace(tzinfo=zone) if a.tzinfo is None else a
        b = b.replace(tzinfo=zone) if b.tzinfo is None else b
        return (b - a).total_seconds()
    a, b = _as_date(a), _as_date(b)
    if u == "D":
        return (b - a).days
    months = (b.year - a.year) * 12 + (b.month - a.month) - (1 if b.day < a.day else 0)
    if u == "M":
        return months
    if u == "Y":
        return months // 12
    raise FormulaError("参数错误", f"“DATEDIF”函数的单位只支持 \"D\" / \"M\" / \"Y\" / \"S\"，收到“{show(unit)}”。")


def f_networkdays_cn(start, end):
    a, b = to_date(start, 'NETWORKDAYS_CN', 1), to_date(end, 'NETWORKDAYS_CN', 2)
    if a is None or b is None:
        return None
    a, b = _as_date(a), _as_date(b)
    if b < a or (b-a).days > 3660:
        raise FormulaError('日期错误', '结束日期不能早于开始日期，区间不能超过3660天')
    from chinese_calendar import is_workday
    try:
        return sum(is_workday(a+timedelta(days=i)) for i in range((b-a).days+1))
    except NotImplementedError:
        raise FormulaError('日期错误', '计算区间包含尚未收录节假日安排的年份') from None


def _add_months(d, n):
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


def f_dateadd(d, n, unit="day"):
    v = to_date(d, "DATEADD", 1)
    if v is None:
        return None
    k = to_number(n, "DATEADD", 2)
    u = to_text(unit).lower()
    if u in ("day", "days", "d", "天", "日"):
        return v + timedelta(days=k)
    if u in ("week", "weeks", "w", "周"):
        return v + timedelta(weeks=k)
    if u in ("month", "months", "m", "月"):
        return _add_months(v, int(k))
    if u in ("year", "years", "y", "年"):
        return _add_months(v, int(k) * 12)
    if u in ("hour", "hours", "h", "小时"):
        return (v if isinstance(v, datetime) else datetime.combine(v, datetime.min.time())) + timedelta(hours=k)
    raise FormulaError("参数错误", f"“DATEADD”函数的单位不支持“{show(unit)}”（可用 day/week/month/year/hour）。")


def f_workday(start, days):
    v = to_date(start, "WORKDAY", 1)
    if v is None:
        return None
    d, left = _as_date(v), int(to_number(days, "WORKDAY", 2))
    step = 1 if left >= 0 else -1
    while left:
        d += timedelta(days=step)
        if d.weekday() < 5:
            left -= step
    return d


def f_networkdays(start, end):
    a, b = to_date(start, "NETWORKDAYS", 1), to_date(end, "NETWORKDAYS", 2)
    if a is None or b is None:
        return None
    a, b = _as_date(a), _as_date(b)
    sign = 1
    if b < a:
        a, b, sign = b, a, -1
    days = sum(1 for i in range((b - a).days + 1) if (a + timedelta(days=i)).weekday() < 5)
    return days * sign


# ---------- 逻辑（IF/IFS/IFERROR/SWITCH 需惰性求值，由 expr.evaluate 特判） ----------

def f_and(*args):
    return all(to_bool(a) for a in flatten(args)) if args else True


def f_or(*args):
    return any(to_bool(a) for a in flatten(args))


def f_not(v):
    return not to_bool(v)


def f_isblank(v):
    return is_blank(v)




# ---------- 扩展函数（对齐参照 docs/PixPin_2026-10-16_23-15-37.png 函数清单） ----------

import random as _random
import re as _re


def _num(v, fn, i=1):
    return to_number(v, fn, i)


def _round_dir(x, n, fn, mode):
    v = Decimal(str(_num(x, fn, 1)))
    d = int(_num(n, fn, 2))
    q = Decimal(1).scaleb(-d)
    r = float(v.quantize(q, rounding={"up": "ROUND_UP", "down": "ROUND_DOWN"}[mode]))
    return int(r) if d <= 0 else r


def f_roundup(x, n=0):
    return _round_dir(x, n, "ROUNDUP", "up")


def f_rounddown(x, n=0):
    return _round_dir(x, n, "ROUNDDOWN", "down")


def f_trunc(x, n=0):
    return _round_dir(x, n, "TRUNC", "down")


def f_mround(x, multiple):
    m = _num(multiple, "MROUND", 2)
    if m == 0:
        return 0
    return round(_num(x, "MROUND", 1) / m) * m


def f_sign(x):
    v = _num(x, "SIGN")
    return (v > 0) - (v < 0)


def f_quotient(a, b):
    d = _num(b, "QUOTIENT", 2)
    if d == 0:
        raise FormulaError("除零错误", "“QUOTIENT”函数的除数不能为 0。")
    return int(_num(a, "QUOTIENT", 1) / d)


def f_product(*args):
    out = 1
    for n in _nums(args, "PRODUCT"):
        out *= n
    return out


def f_median(*args):
    ns = sorted(_nums(args, "MEDIAN"))
    if not ns:
        return None
    m = len(ns) // 2
    return ns[m] if len(ns) % 2 else (ns[m - 1] + ns[m]) / 2


def _kth(args, k, fn, largest):
    ns = sorted(_nums([args], fn), reverse=largest)
    i = int(_num(k, fn, 2))
    if not 1 <= i <= len(ns):
        raise FormulaError("参数错误", f"“{fn}”函数的第 2 个参数需在 1~{len(ns)} 之间。")
    return ns[i - 1]


def f_large(values, k):
    return _kth(values, k, "LARGE", True)


def f_small(values, k):
    return _kth(values, k, "SMALL", False)


def f_log(x, base=10):
    v, b = _num(x, "LOG", 1), _num(base, "LOG", 2)
    if v <= 0 or b <= 0 or b == 1:
        raise FormulaError("数值错误", "“LOG”函数的参数必须为正数，底数不能为 1。")
    return math.log(v, b)


def f_ln(x):
    v = _num(x, "LN")
    if v <= 0:
        raise FormulaError("数值错误", "“LN”函数的参数必须为正数。")
    return math.log(v)


def f_randbetween(a, b):
    lo, hi = int(_num(a, "RANDBETWEEN", 1)), int(_num(b, "RANDBETWEEN", 2))
    return _random.randint(min(lo, hi), max(lo, hi))


def f_sumproduct(*lists):
    cols = [flatten([x]) for x in lists]
    n = min(len(c) for c in cols) if cols else 0
    total = 0
    for i in range(n):
        p = 1
        for c in cols:
            p *= to_number(c[i], "SUMPRODUCT", 1)
        total += p
    return total


# ---------- 条件统计：COUNTIF / SUMIF / …（条件写法：">10" "<>北京" "北京" "*科技*"） ----------

_CRIT_RE = _re.compile(r"^\s*(<=|>=|<>|!=|==|=|<|>)(.*)$", _re.S)


def criterion(c):
    """条件 → 判定函数。数值比较优先；文本比较不区分大小写，= 支持 * ? 通配。"""
    if callable(c):
        return c
    op, operand = "=", c
    if isinstance(c, str):
        m = _CRIT_RE.match(c)
        if m:
            op, operand = m.group(1), m.group(2)
            op = {"==": "=", "!=": "<>"}.get(op, op)

    def num_or_none(v):
        try:
            return None if is_blank(v) else float(to_number(v, "条件", 1))
        except FormulaError:
            return None

    target_n = num_or_none(operand)
    target_t = to_text(operand).casefold()
    wildcard = isinstance(operand, str) and any(ch in operand for ch in "*?") and op in ("=", "<>")
    pattern = _re.compile("^" + _re.escape(target_t).replace(r"\*", ".*").replace(r"\?", ".") + "$") if wildcard else None

    def test(v):
        if isinstance(v, (list, tuple)) and not isinstance(v, Column):
            return any(test(x) for x in v) if v else test(None)
        if op in ("=", "<>"):
            if pattern is not None:
                hit = bool(pattern.match(to_text(v).casefold()))
            elif target_n is not None and num_or_none(v) is not None:
                hit = num_or_none(v) == target_n
            else:
                hit = to_text(v).casefold() == target_t
            return hit if op == "=" else not hit
        a = num_or_none(v)
        if a is None or target_n is None:
            if isinstance(v, (date, datetime)):
                try:
                    a, b = _as_date(v), _as_date(to_date(operand, "条件", 1))
                except FormulaError:
                    return False
                return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
            return False
        return {"<": a < target_n, "<=": a <= target_n, ">": a > target_n, ">=": a >= target_n}[op]
    return test


def _as_list(v):
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v]


def f_countif(rng, crit):
    t = criterion(crit)
    return sum(1 for v in _as_list(rng) if t(v))


def f_countifs(*pairs):
    if len(pairs) % 2:
        raise FormulaError("参数错误", "“COUNTIFS”函数的区域与条件需成对出现。")
    ranges = [(_as_list(pairs[i]), criterion(pairs[i + 1])) for i in range(0, len(pairs), 2)]
    n = min(len(r) for r, _ in ranges)
    return sum(1 for i in range(n) if all(t(r[i]) for r, t in ranges))


def f_sumif(rng, crit, sum_rng=None):
    t = criterion(crit)
    vals = _as_list(rng)
    sums = _as_list(sum_rng) if sum_rng is not None else vals
    return sum(to_number(sums[i], "SUMIF", 3) for i in range(min(len(vals), len(sums)))
               if t(vals[i]) and not is_blank(sums[i]))


def f_sumifs(sum_rng, *pairs):
    if len(pairs) % 2:
        raise FormulaError("参数错误", "“SUMIFS”函数的条件区域与条件需成对出现。")
    sums = _as_list(sum_rng)
    ranges = [(_as_list(pairs[i]), criterion(pairs[i + 1])) for i in range(0, len(pairs), 2)]
    n = min([len(sums)] + [len(r) for r, _ in ranges])
    return sum(to_number(sums[i], "SUMIFS", 1) for i in range(n)
               if all(t(r[i]) for r, t in ranges) and not is_blank(sums[i]))


# ---------- 逻辑 ----------

def f_ifblank(v, alt):
    return alt if is_blank(v) else v


def f_isnumber(v):
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


def f_istext(v):
    return isinstance(v, str)


def f_iseven(v):
    return int(_num(v, "ISEVEN")) % 2 == 0


def f_isodd(v):
    return int(_num(v, "ISODD")) % 2 == 1


# ---------- 文本 ----------

def f_char(n):
    return chr(int(_num(n, "CHAR")))


def f_code(t):
    s = to_text(t)
    return ord(s[0]) if s else None


def f_clean(t):
    return "".join(ch for ch in to_text(t) if ch.isprintable() or ch in "\n")


def f_containtext(text, sub):
    return to_text(sub) in to_text(text)


def f_exact(a, b):
    return to_text(a) == to_text(b)


def f_hyperlink(url, text=None):
    return to_text(text) if text not in (None, "") else to_text(url)


def f_lenb(t):
    return sum(2 if ord(ch) > 127 else 1 for ch in to_text(t))


def f_proper(t):
    return to_text(t).title()


def f_replace(text, start, n, new):
    s = to_text(text)
    i = max(int(_num(start, "REPLACE", 2)), 1) - 1
    k = max(int(_num(n, "REPLACE", 3)), 0)
    return s[:i] + to_text(new) + s[i + k:]


def f_rept(text, n):
    return to_text(text) * max(int(_num(n, "REPT", 2)), 0)


def f_search(sub, text, start=1):
    pos = to_text(text).casefold().find(to_text(sub).casefold(), max(int(_num(start, "SEARCH", 3)), 1) - 1)
    return pos + 1 if pos >= 0 else 0


# ---------- 日期与时间 ----------

def f_datevalue(t):
    return _as_date(to_date(t, "DATEVALUE", 1))


def f_todate(v):
    """数字（时间戳秒/毫秒）或文本 → 日期。"""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        ts = v / 1000 if v > 1e11 else v
        return datetime.fromtimestamp(ts)
    return to_date(v, "TODATE", 1)


def f_days(end, start):
    a, b = to_date(end, "DAYS", 1), to_date(start, "DAYS", 2)
    if a is None or b is None:
        return None
    return (_as_date(a) - _as_date(b)).days


def f_days360(start, end):
    a, b = to_date(start, "DAYS360", 1), to_date(end, "DAYS360", 2)
    if a is None or b is None:
        return None
    a, b = _as_date(a), _as_date(b)
    d1, d2 = min(a.day, 30), b.day
    if d1 == 30 and d2 == 31:
        d2 = 30
    return (b.year - a.year) * 360 + (b.month - a.month) * 30 + (d2 - d1)


def f_edate(start, months):
    v = to_date(start, "EDATE", 1)
    return None if v is None else _add_months(_as_date(v), int(_num(months, "EDATE", 2)))


def f_eomonth(start, months):
    v = to_date(start, "EOMONTH", 1)
    if v is None:
        return None
    d = _add_months(_as_date(v).replace(day=1), int(_num(months, "EOMONTH", 2)))
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def f_isoweeknum(d):
    v = to_date(d, "ISOWEEKNUM", 1)
    return None if v is None else _as_date(v).isocalendar()[1]


def f_weeknum(d, kind=1):
    v = to_date(d, "WEEKNUM", 1)
    if v is None:
        return None
    v = _as_date(v)
    first = date(v.year, 1, 1)
    start_wd = 6 if int(_num(kind, "WEEKNUM", 2)) == 1 else 0   # 1：周日为一周开始；2：周一
    offset = (first.weekday() - start_wd) % 7                     # 1 月 1 日距其所在周首日的天数
    return ((v - first).days + offset) // 7 + 1


def f_time(h, m, s=0):
    total = int(_num(h, "TIME", 1)) * 3600 + int(_num(m, "TIME", 2)) * 60 + int(_num(s, "TIME", 3))
    total %= 86400
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def f_timevalue(t):
    v = to_date(t if ":" not in to_text(t) or "-" in to_text(t) else f"2000-01-01 {to_text(t)}", "TIMEVALUE", 1)
    if not isinstance(v, datetime):
        return 0
    return round((v.hour * 3600 + v.minute * 60 + v.second) / 86400, 10)


def f_yearfrac(start, end):
    a, b = to_date(start, "YEARFRAC", 1), to_date(end, "YEARFRAC", 2)
    if a is None or b is None:
        return None
    return round(abs(f_days360(_as_date(a), _as_date(b))) / 360, 6)


# ---------- 列表 ----------

def f_list(*args):
    return list(args)


def f_listcombine(*args):
    return flatten(args)


def f_listjoin(values, sep="、"):
    return to_text(sep).join(to_text(v) for v in flatten([values]) if not is_blank(v))


def f_at(values, index):
    vs = _as_list(values)
    i = int(_num(index, "AT", 2))
    if not 1 <= i <= len(vs):
        return None
    return vs[i - 1]


def f_choose(index, *values):
    i = int(_num(index, "CHOOSE", 1))
    if not 1 <= i <= len(values):
        raise FormulaError("参数错误", f"“CHOOSE”函数的序号需在 1~{len(values)} 之间。")
    return values[i - 1]


def _contains(values, v):
    tv = to_text(v)
    return any(to_text(x) == tv for x in flatten([values]))


def f_contains(values, v):
    return _contains(values, v)


def f_containsall(values, *vs):
    return all(_contains(values, v) for v in flatten(vs))


def f_containsonly(values, *vs):
    allowed = {to_text(v) for v in flatten(vs)}
    items = [to_text(x) for x in flatten([values]) if not is_blank(x)]
    return bool(items) and all(x in allowed for x in items)


def f_first(values):
    vs = _as_list(values)
    return vs[0] if vs else None


def f_last(values):
    vs = _as_list(values)
    return vs[-1] if vs else None


def f_unique(values):
    out, seen = [], set()
    for v in flatten([values]):
        k = to_text(v)
        if is_blank(v) or k in seen:
            continue
        seen.add(k)
        out.append(v)
    return Column(out) if isinstance(values, Column) else out


def f_sort(values, order="asc"):
    vs = [v for v in flatten([values]) if not is_blank(v)]
    desc = to_text(order).lower() in ("desc", "降序", "-1", "false")

    def key(v):
        try:
            return (0, float(to_number(v, "SORT", 1)), "")
        except FormulaError:
            return (1, 0, to_text(v))
    return sorted(vs, key=key, reverse=desc)


def f_sequence(n, start=1, step=1):
    k = int(_num(n, "SEQUENCE", 1))
    if k > 10000:
        raise FormulaError("参数错误", "“SEQUENCE”最多生成 10000 个数。")
    a, d = _num(start, "SEQUENCE", 2), _num(step, "SEQUENCE", 3)
    return [a + d * i for i in range(max(k, 0))]


def f_filter(values, *conds):
    """FILTER(列表, 条件1, [条件2…])：条件为与列表等长的逻辑列（如 [#表.城市]="北京"）或单个逻辑值。"""
    vs = _as_list(values)
    keep = [True] * len(vs)
    for c in conds:
        if isinstance(c, (list, tuple)):
            cl = list(c)
            keep = [k and i < len(cl) and to_bool(cl[i]) for i, k in enumerate(keep)]
        elif not to_bool(c):
            keep = [False] * len(vs)
    out = [v for v, k in zip(vs, keep) if k]
    return Column(out) if isinstance(values, Column) else out


def f_lookup(value, lookup_values, result_values=None):
    """LOOKUP(查找值, 查找列, [结果列])：返回第一个匹配项对应的结果。"""
    keys = _as_list(lookup_values)
    res = _as_list(result_values) if result_values is not None else keys
    t = criterion(value) if isinstance(value, str) and _CRIT_RE.match(value) else None
    tv = to_text(value)
    for i, k in enumerate(keys):
        if (t(k) if t else to_text(k) == tv) and i < len(res):
            return res[i]
    return None


LAZY = {"IF", "IFS", "IFERROR", "SWITCH", "ISERROR", "ISERR"}


# ---------- 参数说明（编辑器说明栏「*参数名  说明」）：按参数名通用描述 + 少量专属覆盖 ----------
PARAM_DESC = {
    "文本": "要处理的文本，可以是字段、文本或公式结果。", "文本1": "要联接的文本项。字符串或字符串数组，后续数值是可选的。",
    "文本2, ...": "其他要联接的文本项。", "数值": "要计算的数字。", "数值1": "要计算的第一个数字或数字列表。",
    "数值2, ...": "其他要计算的数字或列表。", "值": "要判断或处理的值。", "值1": "第一个值或列表。", "值2, ...": "其他值或列表。",
    "逻辑表达式": "结果为 TRUE 或 FALSE 的表达式，如 [状态]=\"完成\"。", "为 TRUE 时的返回值": "条件成立时返回的值。",
    "为 FALSE 时的返回值": "条件不成立时返回的值，省略时返回空。", "日期": "日期字段、日期文本或日期函数结果。",
    "开始日期": "起始日期。", "结束日期": "结束日期。", "单位": "计算单位，如 \"D\" 天、\"M\" 月、\"Y\" 年。",
    "格式": "格式代码，如 \"YYYY-MM-DD\"、\"ddd\"、\"0.00\"、\"0%\"。", "小数位数": "保留的小数位数，省略为 0。",
    "区域": "要判断的一列值，如 [#客户表.城市]，或多值字段。", "条件": "判断条件，如 \"北京\"、\">10\"、\"<>已完成\"、\"*科技*\"。",
    "求和区域": "实际求和的一列值，省略时对「区域」本身求和。", "列表": "一组值：整列引用、多选字段或 LIST() 的结果。",
    "查找值": "要查找的值。", "查找列": "在其中查找的一列值。", "结果列": "返回结果所在的一列值，与查找列一一对应。",
    "分隔符": "连接各项时使用的分隔文本。", "序号": "第几个（从 1 开始）。", "字符数": "要截取的字符个数。",
    "开始位置": "从第几个字符开始（从 1 开始）。", "原文本": "要被替换掉的文本。", "新文本": "替换成的文本。",
}


def _params(sig: str) -> list[dict]:
    open_i, close_i = sig.find("("), sig.rfind(")")
    out = []
    for raw in _split_args(sig[open_i + 1: close_i]):
        optional = raw.startswith("[")
        name = raw.strip("[] ").strip()
        if not name or name == "...":
            continue
        out.append({"name": name, "required": not optional,
                    "desc": PARAM_DESC.get(name) or PARAM_DESC.get(name.rstrip("0123456789")) or ""})
    return out


def _split_args(inner: str) -> list[str]:
    args, depth, cur = [], 0, ""
    for ch in inner:
        if ch in "[(":
            depth += 1
        if ch in "])":
            depth -= 1
        if ch == "," and depth == 0:
            args.append(cur.strip())
            cur = ""
            continue
        cur += ch
    if cur.strip():
        args.append(cur.strip())
    return args


# ---------- 目录 ----------
# (名称, 分类, 最少参数, 最多参数(None=不限), 实现, 签名, 说明, 返回类型, [(示例, 结果/说明)])
C, N, L, T, D, LS = "常用函数", "数字函数", "逻辑函数", "文本函数", "日期与时间函数", "列表函数"
_CATALOG = [
    # 常用
    ("COUNTA", C, 1, None, f_counta, "COUNTA(值1, [值2, ...])", "计算非空值的个数；多选、人员等多值字段与整列引用按项计数。", "number",
     [("COUNTA([负责人])", "负责人有 3 人时 = 3"), ("COUNTA([#客户表])", "客户表的记录数")]),
    ("FILTER", C, 2, None, f_filter, "FILTER(列表, 条件1, [条件2, ...])", "按条件筛选列表中的值，常与整表引用配合使用。", "list",
     [('FILTER([#订单表.金额], [#订单表.客户]=[客户名称])', "本行客户的所有订单金额"),
      ('FILTER([#订单表.金额], [#订单表.城市]="北京").SUM()', "北京订单金额合计")]),
    ("IF", C, 2, 3, None, "IF(逻辑表达式, 为 TRUE 时的返回值, [为 FALSE 时的返回值])",
     "当逻辑表达式结果为TRUE时返回一个值，为FALSE时返回另一个值。", "any",
     [('IF([是否完成]="是",1,2)', "表示如果是否完成等于是，则返回 1, 否则返回 2。")]),
    ("UNIQUE", C, 1, 1, f_unique, "UNIQUE(列表)", "去除列表中的重复值与空值。", "list",
     [('UNIQUE([#订单表.客户]).COUNTA()', "下过单的客户数")]),
    # 数字
    ("ABS", N, 1, 1, f_abs, "ABS(数值)", "返回数值的绝对值。", "number", [("ABS(-5)", "= 5")]),
    ("AVERAGE", N, 1, None, f_average, "AVERAGE(数值1, [数值2, ...])", "计算平均值，忽略空值。", "number",
     [("AVERAGE([语文], [数学], [英语])", "三科平均分"), ("AVERAGE([#订单表.金额])", "订单平均金额")]),
    ("CEILING", N, 1, 2, f_ceiling, "CEILING(数值, [基数])", "向上舍入为基数的倍数。", "number", [("CEILING(12.3, 5)", "= 15")]),
    ("COS", N, 1, 1, lambda x: math.cos(_num(x, "COS")), "COS(数值)", "返回角度（弧度）的余弦值。", "number", [("COS(0)", "= 1")]),
    ("COUNT", N, 1, None, f_count, "COUNT(值1, [值2, ...])", "计算其中数字的个数。", "number", [('COUNT(1, "a", 3)', "= 2")]),
    ("COUNTA", N, 1, None, f_counta, "COUNTA(值1, [值2, ...])", "计算非空值的个数。", "number", [("COUNTA([电话], [邮箱])", "已填写的联系方式个数")]),
    ("COUNTIF", N, 2, 2, f_countif, "COUNTIF(区域, 条件)", "统计区域中满足条件的个数。", "number",
     [('COUNTIF([#订单表.客户], [客户名称])', "本行客户的订单数"), ('COUNTIF([#订单表.金额], ">1000")', "大额订单数")]),
    ("COUNTIFS", N, 2, None, f_countifs, "COUNTIFS(区域1, 条件1, [区域2, 条件2, ...])", "统计同时满足多组条件的个数。", "number",
     [('COUNTIFS([#订单表.客户], [客户名称], [#订单表.状态], "已付款")', "本行客户已付款订单数")]),
    ("EXP", N, 1, 1, lambda x: math.exp(_num(x, "EXP")), "EXP(数值)", "返回 e 的数值次幂。", "number", [("EXP(1)", "= 2.718…")]),
    ("FLOOR", N, 1, 2, f_floor, "FLOOR(数值, [基数])", "向下舍入为基数的倍数。", "number", [("FLOOR(12.3, 5)", "= 10")]),
    ("INT", N, 1, 1, f_int, "INT(数值)", "向下取整为最接近的整数。", "number", [("INT(8.9)", "= 8")]),
    ("LARGE", N, 2, 2, f_large, "LARGE(列表, 序号)", "返回列表中第 k 大的值。", "number", [("LARGE([#销售表.业绩], 1)", "最高业绩")]),
    ("LN", N, 1, 1, f_ln, "LN(数值)", "返回自然对数。", "number", [("LN(EXP(2))", "= 2")]),
    ("LOG", N, 1, 2, f_log, "LOG(数值, [底数])", "返回指定底数的对数，底数默认 10。", "number", [("LOG(100)", "= 2")]),
    ("MAX", N, 1, None, f_max, "MAX(数值1, [数值2, ...])", "返回最大值。", "number", [("MAX([#销售表.业绩])", "全表最高业绩")]),
    ("MEDIAN", N, 1, None, f_median, "MEDIAN(数值1, [数值2, ...])", "返回中位数。", "number", [("MEDIAN(1, 3, 8)", "= 3")]),
    ("MIN", N, 1, None, f_min, "MIN(数值1, [数值2, ...])", "返回最小值。", "number", [("MIN([库存], [安全库存])", "取较小者")]),
    ("MOD", N, 2, 2, f_mod, "MOD(被除数, 除数)", "返回两数相除的余数。", "number", [("MOD(10, 3)", "= 1")]),
    ("MROUND", N, 2, 2, f_mround, "MROUND(数值, 基数)", "舍入到最接近的基数倍数。", "number", [("MROUND(17, 5)", "= 15")]),
    ("PI", N, 0, 0, lambda: math.pi, "PI()", "返回圆周率 π。", "number", [("PI() * [半径] ^ 2", "圆面积")]),
    ("POWER", N, 2, 2, f_power, "POWER(底数, 指数)", "返回底数的指数次幂，也可写作 底数 ^ 指数。", "number", [("POWER(2, 10)", "= 1024")]),
    ("PRODUCT", N, 1, None, f_product, "PRODUCT(数值1, [数值2, ...])", "返回所有数值的乘积。", "number", [("PRODUCT([单价], [数量])", "= 单价 × 数量")]),
    ("QUOTIENT", N, 2, 2, f_quotient, "QUOTIENT(被除数, 除数)", "返回整除结果（舍去小数）。", "number", [("QUOTIENT(10, 3)", "= 3")]),
    ("RAND", N, 0, 0, lambda: _random.random(), "RAND()", "返回 0~1 之间的随机数（记录保存时重新生成）。", "number", [("RAND()", "= 0.37…")]),
    ("RANDBETWEEN", N, 2, 2, f_randbetween, "RANDBETWEEN(最小值, 最大值)", "返回区间内的随机整数。", "number", [("RANDBETWEEN(1, 100)", "1~100 的随机数")]),
    ("ROUND", N, 1, 2, f_round, "ROUND(数值, [小数位数])", "按指定小数位数四舍五入。", "number", [("ROUND(3.1415, 2)", "= 3.14")]),
    ("ROUNDDOWN", N, 1, 2, f_rounddown, "ROUNDDOWN(数值, [小数位数])", "向零方向舍去。", "number", [("ROUNDDOWN(3.19, 1)", "= 3.1")]),
    ("ROUNDUP", N, 1, 2, f_roundup, "ROUNDUP(数值, [小数位数])", "远离零方向进位。", "number", [("ROUNDUP(3.11, 1)", "= 3.2")]),
    ("SIGN", N, 1, 1, f_sign, "SIGN(数值)", "正数返回 1，负数返回 -1，零返回 0。", "number", [("SIGN(-8)", "= -1")]),
    ("SIN", N, 1, 1, lambda x: math.sin(_num(x, "SIN")), "SIN(数值)", "返回角度（弧度）的正弦值。", "number", [("SIN(PI()/2)", "= 1")]),
    ("SMALL", N, 2, 2, f_small, "SMALL(列表, 序号)", "返回列表中第 k 小的值。", "number", [("SMALL([#销售表.业绩], 1)", "最低业绩")]),
    ("SQRT", N, 1, 1, f_sqrt, "SQRT(数值)", "返回平方根。", "number", [("SQRT(16)", "= 4")]),
    ("SUM", N, 1, None, f_sum, "SUM(数值1, [数值2, ...])", "计算所有数值之和，空值按 0 计。", "number",
     [("SUM([单价], [运费])", "= 单价 + 运费"), ("SUM([#订单表.金额])", "订单表金额总计")]),
    ("SUMIF", N, 2, 3, f_sumif, "SUMIF(区域, 条件, [求和区域])", "对满足条件的值求和。", "number",
     [('SUMIF([#订单表.客户], [客户名称], [#订单表.金额])', "本行客户的订单总额")]),
    ("SUMIFS", N, 3, None, f_sumifs, "SUMIFS(求和区域, 区域1, 条件1, [区域2, 条件2, ...])", "对同时满足多组条件的值求和。", "number",
     [('SUMIFS([#订单表.金额], [#订单表.客户], [客户名称], [#订单表.状态], "已付款")', "本行客户已付款总额")]),
    ("SUMPRODUCT", N, 1, None, f_sumproduct, "SUMPRODUCT(列表1, [列表2, ...])", "对应项相乘后求和。", "number",
     [("SUMPRODUCT([#订单表.单价], [#订单表.数量])", "订单表总金额")]),
    ("TAN", N, 1, 1, lambda x: math.tan(_num(x, "TAN")), "TAN(数值)", "返回角度（弧度）的正切值。", "number", [("TAN(0)", "= 0")]),
    ("TRUNC", N, 1, 2, f_trunc, "TRUNC(数值, [小数位数])", "截去小数部分（不四舍五入）。", "number", [("TRUNC(8.97, 1)", "= 8.9")]),
    # 逻辑
    ("AND", L, 1, None, f_and, "AND(逻辑表达式1, [逻辑表达式2, ...])", "所有参数都为 TRUE 时返回 TRUE。", "boolean",
     [('AND([数量]>0, [状态]="在产")', "两个条件同时满足")]),
    ("FALSE", L, 0, 0, lambda: False, "FALSE()", "返回逻辑值 FALSE，也可直接写 FALSE。", "boolean", [("IF([已付款], TRUE, FALSE)", "")]),
    ("IF", L, 2, 3, None, "IF(逻辑表达式, 为 TRUE 时的返回值, [为 FALSE 时的返回值])",
     "当逻辑表达式结果为TRUE时返回一个值，为FALSE时返回另一个值。", "any",
     [('IF([是否完成]="是",1,2)', "表示如果是否完成等于是，则返回 1, 否则返回 2。")]),
    ("IFBLANK", L, 2, 2, f_ifblank, "IFBLANK(值, 为空时的返回值)", "值为空时返回指定值，否则返回值本身。", "any",
     [('IFBLANK([电话], "未填写")', "")]),
    ("IFERROR", L, 2, 2, None, "IFERROR(值, 出错时的返回值)", "值计算出错时返回指定的值。", "any", [("IFERROR([金额]/[数量], 0)", "数量为 0 时返回 0")]),
    ("IFS", L, 2, None, None, "IFS(条件1, 值1, [条件2, 值2, ...])", "依次判断条件，返回第一个为 TRUE 的条件对应的值。", "any",
     [('IFS([分数]>=90, "优", [分数]>=60, "及格", TRUE, "不及格")', "按分数段评级")]),
    ("ISBLANK", L, 1, 1, f_isblank, "ISBLANK(值)", "判断值是否为空。", "boolean", [('IF(ISBLANK([电话]), "缺电话", "")', "提示缺失")]),
    ("ISERR", L, 1, 1, None, "ISERR(值)", "判断值计算是否出错。", "boolean", [("ISERR([金额]/0)", "= TRUE")]),
    ("ISERROR", L, 1, 1, None, "ISERROR(值)", "判断值计算是否出错。", "boolean", [("ISERROR(VALUE(\"abc\"))", "= TRUE")]),
    ("ISEVEN", L, 1, 1, f_iseven, "ISEVEN(数值)", "判断是否为偶数。", "boolean", [("ISEVEN(4)", "= TRUE")]),
    ("ISNULL", L, 1, 1, f_isblank, "ISNULL(值)", "判断值是否为空（同 ISBLANK）。", "boolean", [("ISNULL([备注])", "")]),
    ("ISNUMBER", L, 1, 1, f_isnumber, "ISNUMBER(值)", "判断值是否为数字。", "boolean", [("ISNUMBER([金额])", "")]),
    ("ISODD", L, 1, 1, f_isodd, "ISODD(数值)", "判断是否为奇数。", "boolean", [("ISODD(3)", "= TRUE")]),
    ("ISTEXT", L, 1, 1, f_istext, "ISTEXT(值)", "判断值是否为文本。", "boolean", [("ISTEXT([编号])", "")]),
    ("NOT", L, 1, 1, f_not, "NOT(逻辑表达式)", "对逻辑值取反。", "boolean", [("NOT([是否完成])", "未完成时为 TRUE")]),
    ("OR", L, 1, None, f_or, "OR(逻辑表达式1, [逻辑表达式2, ...])", "任一参数为 TRUE 时返回 TRUE。", "boolean",
     [('OR([状态]="停产", [库存]=0)', "任一条件满足")]),
    ("RECORD_ID", L, 0, 0, None, "RECORD_ID()", "返回当前记录的 ID。", "number", [('"NO-" & RECORD_ID()', "= NO-128")]),
    ("SWITCH", L, 3, None, None, "SWITCH(表达式, 值1, 结果1, [值2, 结果2, ...], [默认结果])",
     "将表达式与各值依次比较，返回匹配值对应的结果。", "any", [('SWITCH([状态], "在产", 1, "停产", 0, -1)', "状态映射为数字")]),
    ("TRUE", L, 0, 0, lambda: True, "TRUE()", "返回逻辑值 TRUE，也可直接写 TRUE。", "boolean", [("IFS([分数]>=60, \"及格\", TRUE, \"不及格\")", "")]),
    # 文本
    ("CHAR", T, 1, 1, f_char, "CHAR(数值)", "返回编码对应的字符。", "text", [("CHAR(65)", "= A")]),
    ("CLEAN", T, 1, 1, f_clean, "CLEAN(文本)", "删除文本中不可打印的字符。", "text", [("CLEAN([备注])", "")]),
    ("CODE", T, 1, 1, f_code, "CODE(文本)", "返回文本第一个字符的编码。", "number", [('CODE("A")', "= 65")]),
    ("CONCAT", T, 1, None, f_concat, "CONCAT(文本1, [文本2, ...])", "将多个文本拼接成单个文本。 要拼接双引号，需要连续输入两个双引号。", "text",
     [('CONCAT([姓名], "-", [年龄])', "= 小明 - 28"), ('[产品编号].CONCAT("-", [产品名称])', "= P001-骨密度仪")]),
    ("CONCATENATE", T, 1, None, f_concat, "CONCATENATE(文本1, [文本2, ...])", "将多个文本拼接成单个文本（同 CONCAT）。", "text",
     [('CONCATENATE([省], [市])', "= 广东广州")]),
    ("CONTAINTEXT", T, 2, 2, f_containtext, "CONTAINTEXT(文本, 要查找的文本)", "判断文本中是否包含指定内容。", "boolean",
     [('CONTAINTEXT([公司名称], "科技")', "= TRUE")]),
    ("EXACT", T, 2, 2, f_exact, "EXACT(文本1, 文本2)", "判断两段文本是否完全相同（区分大小写）。", "boolean", [('EXACT("A", "a")', "= FALSE")]),
    ("FIND", T, 2, 3, f_find, "FIND(要查找的文本, 文本, [开始位置])", "返回要查找的文本首次出现的位置（区分大小写），找不到返回 0。", "number",
     [('FIND("-", "P-001")', "= 2")]),
    ("HYPERLINK", T, 1, 2, f_hyperlink, "HYPERLINK(链接地址, [显示文本])", "生成链接文本。", "text", [('HYPERLINK([官网], "访问官网")', "")]),
    ("LEFT", T, 1, 2, f_left, "LEFT(文本, [字符数])", "从文本开头截取指定个数的字符。", "text", [('LEFT("骨密度仪", 2)', "= 骨密")]),
    ("LEN", T, 1, 1, lambda t: len(to_text(t)), "LEN(文本)", "返回文本的字符个数。", "number", [('LEN("智能表格")', "= 4")]),
    ("LENB", T, 1, 1, f_lenb, "LENB(文本)", "返回文本的字节数（中文按 2 计）。", "number", [('LENB("智能A")', "= 5")]),
    ("LOWER", T, 1, 1, lambda t: to_text(t).lower(), "LOWER(文本)", "将文本中的英文字母转为小写。", "text", [('LOWER("ABC")', "= abc")]),
    ("MID", T, 3, 3, f_mid, "MID(文本, 开始位置, 字符数)", "从文本的指定位置开始截取指定个数的字符。", "text", [('MID("2024-09-14", 6, 2)', "= 09")]),
    ("PROPER", T, 1, 1, f_proper, "PROPER(文本)", "将英文单词首字母大写。", "text", [('PROPER("hello world")', "= Hello World")]),
    ("REPLACE", T, 4, 4, f_replace, "REPLACE(文本, 开始位置, 字符数, 新文本)", "将文本中指定位置的若干字符替换为新文本。", "text",
     [('REPLACE("13812345678", 4, 4, "****")', "= 138****5678")]),
    ("REPT", T, 2, 2, f_rept, "REPT(文本, 次数)", "将文本重复指定次数。", "text", [('REPT("★", [评分])', "评分 3 时 = ★★★")]),
    ("RIGHT", T, 1, 2, f_right, "RIGHT(文本, [字符数])", "从文本末尾截取指定个数的字符。", "text", [('RIGHT("P001", 3)', "= 001")]),
    ("SEARCH", T, 2, 3, f_search, "SEARCH(要查找的文本, 文本, [开始位置])", "返回要查找的文本首次出现的位置（不区分大小写）。", "number",
     [('SEARCH("b", "ABC")', "= 2")]),
    ("SPLIT", T, 2, 3, f_split, "SPLIT(文本, 分隔符, [第几段])", "按分隔符拆分文本，指定第几段时返回该段。", "list", [('SPLIT("A-B-C", "-", 2)', "= B")]),
    ("SUBSTITUTE", T, 3, 4, f_substitute, "SUBSTITUTE(文本, 原文本, 新文本, [第几处])", "将文本中的原文本替换为新文本。", "text",
     [('SUBSTITUTE("2024-09-14", "-", "/")', "= 2024/09/14")]),
    ("TEXT", T, 2, 2, f_text, "TEXT(数值, 格式)", "按指定格式将数字或日期转为文本。", "text",
     [('TEXT("2024-09-14", "ddd")', "= 周六"), ('TEXT("2024-09-14", "YYYY")', "= 2024"), ('TEXT(0.256, "0.0%")', "= 25.6%")]),
    ("TEXTJOIN", T, 3, None, f_textjoin, "TEXTJOIN(分隔符, 是否忽略空值, 文本1, [文本2, ...])", "用分隔符把多个文本连接起来，可选择忽略空值。", "text",
     [('TEXTJOIN("/", TRUE, [省], [市], [区])', "= 广东/广州/天河")]),
    ("TRIM", T, 1, 1, lambda t: " ".join(to_text(t).split()), "TRIM(文本)", "去掉文本首尾空格，并把中间连续空格合并为一个。", "text",
     [('TRIM("  智能  表格 ")', "= 智能 表格")]),
    ("UPPER", T, 1, 1, lambda t: to_text(t).upper(), "UPPER(文本)", "将文本中的英文字母转为大写。", "text", [('UPPER("abc")', "= ABC")]),
    ("VALUE", T, 1, 1, f_value, "VALUE(文本)", "将数字样式的文本转为数字。", "number", [('VALUE("12.5")', "= 12.5")]),
    # 日期与时间
    ("DATE", D, 3, 3, f_date, "DATE(年, 月, 日)", "由年、月、日生成日期。", "date", [("DATE(2024, 9, 14)", "= 2024-09-14")]),
    ("DATEDIF", D, 2, 3, f_datedif, "DATEDIF(开始日期, 结束日期, [单位])", "计算间隔：D为自然日、M为整月、Y为整年、S为精确秒数（无时区按北京时间）。", "number",
     [('DATEDIF("2024-01-01", "2024-09-14", "D")', "= 257"), ('DATEDIF([入职日期], TODAY(), "Y")', "司龄（年）")]),
    ("DATEVALUE", D, 1, 1, f_datevalue, "DATEVALUE(文本)", "将日期文本转为日期。", "date", [('DATEVALUE("2024/9/14")', "= 2024-09-14")]),
    ("DAY", D, 1, 1, _date_part("DAY", "day"), "DAY(日期)", "返回日期是当月第几天。", "number", [('DAY("2024-09-14")', "= 14")]),
    ("DAYS", D, 2, 2, f_days, "DAYS(结束日期, 开始日期)", "返回两个日期相差的天数。", "number", [('DAYS("2024-09-14", "2024-09-01")', "= 13")]),
    ("DAYS360", D, 2, 2, f_days360, "DAYS360(开始日期, 结束日期)", "按一年 360 天计算两个日期相差的天数。", "number",
     [('DAYS360("2024-01-01", "2024-03-01")', "= 60")]),
    ("EDATE", D, 2, 2, f_edate, "EDATE(开始日期, 月数)", "返回若干个月之前/之后的日期。", "date", [('EDATE("2024-01-31", 1)', "= 2024-02-29")]),
    ("EOMONTH", D, 2, 2, f_eomonth, "EOMONTH(开始日期, 月数)", "返回若干个月之前/之后那个月的最后一天。", "date",
     [('EOMONTH("2024-09-14", 0)', "= 2024-09-30")]),
    ("HOUR", D, 1, 1, _date_part("HOUR", "hour"), "HOUR(日期)", "返回小时数。", "number", [('HOUR("2024-09-14 18:30")', "= 18")]),
    ("ISOWEEKNUM", D, 1, 1, f_isoweeknum, "ISOWEEKNUM(日期)", "返回 ISO 周数。", "number", [('ISOWEEKNUM("2024-09-14")', "= 37")]),
    ("MINUTE", D, 1, 1, _date_part("MINUTE", "minute"), "MINUTE(日期)", "返回分钟数。", "number", [('MINUTE("2024-09-14 18:30")', "= 30")]),
    ("MONTH", D, 1, 1, _date_part("MONTH", "month"), "MONTH(日期)", "返回日期的月份。", "number", [('MONTH("2024-09-14")', "= 9")]),
    ("NETWORKDAYS", D, 2, 2, f_networkdays, "NETWORKDAYS(开始日期, 结束日期)", "返回两个日期之间（含首尾）的工作日天数。", "number",
     [('NETWORKDAYS("2024-09-09", "2024-09-15")', "= 5")]),
    ("NETWORKDAYS_CN", D, 2, 2, f_networkdays_cn, "NETWORKDAYS_CN(开始日期, 结束日期)", "按中国节假日及调休安排计算工作日，含首尾；区间不超过3660天，未收录年份报错。", "number", [('NETWORKDAYS_CN("2026-10-12", "2026-10-16")', '= 5')]),
    ("NOW", D, 0, 0, f_now, "NOW()", "返回当前的日期和时间。", "date", [("NOW()", "= 2026-10-16 22:11")]),
    ("SECOND", D, 1, 1, _date_part("SECOND", "second"), "SECOND(日期)", "返回秒数。", "number", [('SECOND("2024-09-14 18:30:15")', "= 15")]),
    ("TIME", D, 2, 3, f_time, "TIME(时, 分, [秒])", "由时、分、秒生成时间。", "text", [("TIME(9, 30)", "= 09:30:00")]),
    ("TIMEVALUE", D, 1, 1, f_timevalue, "TIMEVALUE(文本)", "将时间文本转为一天中的比例（0~1）。", "number", [('TIMEVALUE("12:00")', "= 0.5")]),
    ("TODATE", D, 1, 1, f_todate, "TODATE(值)", "将时间戳或日期文本转为日期。", "date", [('TODATE("2024年9月14日")', "= 2024-09-14")]),
    ("TODAY", D, 0, 0, f_today, "TODAY()", "返回今天的日期。", "date", [("DATEDIF([入职日期], TODAY(), \"Y\")", "司龄（年）")]),
    ("WEEKDAY", D, 1, 2, f_weekday, "WEEKDAY(日期, [类型])", "返回星期几：类型 2（默认）周一为 1，类型 1 周日为 1。", "number",
     [('WEEKDAY("2024-09-14")', "= 6（周六）")]),
    ("WEEKNUM", D, 1, 2, f_weeknum, "WEEKNUM(日期, [类型])", "返回日期是一年中的第几周（类型 1 周日起，类型 2 周一起）。", "number",
     [('WEEKNUM("2024-09-14")', "= 37")]),
    ("WORKDAY", D, 2, 2, f_workday, "WORKDAY(开始日期, 工作日天数)", "返回若干个工作日（不含周末）之后的日期。", "date",
     [('WORKDAY("2024-09-13", 1)', "= 2024-09-16")]),
    ("YEAR", D, 1, 1, _date_part("YEAR", "year"), "YEAR(日期)", "返回日期的年份。", "number", [('YEAR("2024-09-14")', "= 2024")]),
    ("YEARFRAC", D, 2, 2, f_yearfrac, "YEARFRAC(开始日期, 结束日期)", "返回两个日期之间相差的年数（小数，按 360 天/年）。", "number",
     [('YEARFRAC("2024-01-01", "2024-07-01")', "= 0.5")]),
    ("DATEADD", D, 2, 3, f_dateadd, "DATEADD(日期, 数量, [单位])", "在日期上加减指定的天/周/月/年。", "date",
     [('DATEADD("2024-09-14", 1, "month")', "= 2024-10-14")]),
    # 列表
    ("AT", LS, 2, 2, f_at, "AT(列表, 序号)", "返回列表中第几个值（从 1 开始）。", "any", [('AT(SPLIT("A-B-C", "-"), 2)', "= B")]),
    ("CHOOSE", LS, 2, None, f_choose, "CHOOSE(序号, 值1, [值2, ...])", "按序号从候选值中选取一个。", "any",
     [('CHOOSE(WEEKDAY(TODAY()), "一", "二", "三", "四", "五", "六", "日")', "今天星期几")]),
    ("CONTAINS", LS, 2, 2, f_contains, "CONTAINS(列表, 值)", "判断列表中是否包含某个值。", "boolean", [('CONTAINS([标签], "重点")', "多选含「重点」")]),
    ("CONTAINSALL", LS, 2, None, f_containsall, "CONTAINSALL(列表, 值1, [值2, ...])", "判断列表是否包含所有指定值。", "boolean",
     [('CONTAINSALL([标签], "重点", "紧急")', "")]),
    ("CONTAINSONLY", LS, 2, None, f_containsonly, "CONTAINSONLY(列表, 值1, [值2, ...])", "判断列表是否只包含指定的值。", "boolean",
     [('CONTAINSONLY([负责人], "张三")', "仅张三负责")]),
    ("FILTER", LS, 2, None, f_filter, "FILTER(列表, 条件1, [条件2, ...])", "按条件筛选列表中的值，常与整表引用配合使用。", "list",
     [('FILTER([#订单表.金额], [#订单表.客户]=[客户名称])', "本行客户的所有订单金额")]),
    ("FIRST", LS, 1, 1, f_first, "FIRST(列表)", "返回列表的第一个值。", "any", [("FIRST([负责人])", "第一负责人")]),
    ("LAST", LS, 1, 1, f_last, "LAST(列表)", "返回列表的最后一个值。", "any", [("LAST(SPLIT([路径], \"/\"))", "路径最后一段")]),
    ("LIST", LS, 1, None, f_list, "LIST(值1, [值2, ...])", "把多个值组成一个列表。", "list", [('LIST("A", "B").LISTJOIN("/")', "= A/B")]),
    ("LISTCOMBINE", LS, 1, None, f_listcombine, "LISTCOMBINE(列表1, [列表2, ...])", "把多个列表合并为一个列表。", "list",
     [("LISTCOMBINE([负责人], [协作人]).UNIQUE()", "所有参与人（去重）")]),
    ("LISTJOIN", LS, 1, 2, f_listjoin, "LISTJOIN(列表, [分隔符])", "把列表中的值用分隔符连接为文本。", "text", [('[标签].LISTJOIN("/")', "= 重点/紧急")]),
    ("LOOKUP", LS, 2, 3, f_lookup, "LOOKUP(查找值, 查找列, [结果列])", "在查找列中查找值，返回结果列中对应位置的值。", "any",
     [("LOOKUP([客户名称], [#客户表.名称], [#客户表.电话])", "从客户表带出电话")]),
    ("SEQUENCE", LS, 1, 3, f_sequence, "SEQUENCE(个数, [起始值], [步长])", "生成一组等差数列。", "list", [("SEQUENCE(3)", "= 1、2、3")]),
    ("SORT", LS, 1, 2, f_sort, "SORT(列表, [顺序])", "对列表排序，顺序为 \"asc\" 升序（默认）或 \"desc\" 降序。", "list",
     [('SORT([#销售表.业绩], "desc").FIRST()', "最高业绩")]),
    ("UNIQUE", LS, 1, 1, f_unique, "UNIQUE(列表)", "去除列表中的重复值与空值。", "list", [('UNIQUE([#订单表.客户]).COUNTA()', "下过单的客户数")]),
]

FUNCTIONS: dict = {}
_ENTRIES: list[dict] = []
for name, cat, mn, mx, impl, sig, desc, ret, ex in _CATALOG:
    spec = {"category": cat, "min": mn, "max": mx, "impl": impl, "signature": sig, "desc": desc,
            "returns": ret, "examples": ex}
    FUNCTIONS.setdefault(name, spec)       # 同名多分类（COUNTA/FILTER/IF/UNIQUE）共用一个实现
    _ENTRIES.append({"name": name, **spec})
CATEGORIES = [C, N, L, T, D, LS]

# 运算符（编辑器「运算符」分组，点击插入）
OPERATORS = [
    ("+", "加", "[单价] + [运费]"), ("-", "减", "[收入] - [成本]"), ("*", "乘", "[单价] * [数量]"), ("/", "除", "[金额] / [数量]"),
    ("&", "拼接文本", '[姓] & [名]'), (">", "大于", "[分数] > 60"), (">=", "大于等于", "[分数] >= 60"), ("<", "小于", "[库存] < 10"),
    ("<=", "小于等于", "[库存] <= 10"), ("=", "等于", '[状态] = "完成"'), ("!=", "不等于", '[状态] != "完成"'),
    ("==", "等于（同 =）", '[状态] == "完成"'), ("!==", "不等于（同 !=）", '[状态] !== "完成"'), ("^", "乘方", "[边长] ^ 2"),
    ("<>", "不等于（同 !=）", '[状态] <> "完成"'),
]

# 搜索同义词：编辑器函数搜索按「想做什么」找函数（输入「相差」「拼接」「四舍五入」也能命中）
KEYWORDS = {
    "IF": "如果 判断 条件 否则", "IFS": "多条件 分级 评级 区间", "SWITCH": "映射 对应 转换 匹配",
    "IFERROR": "出错 错误 容错 除零", "ISBLANK": "为空 空值 未填写 是否填写", "IFBLANK": "为空 默认值 未填写",
    "AND": "并且 同时 都满足", "OR": "或者 任一 满足其一", "NOT": "取反 不是",
    "CONCAT": "拼接 合并 连接 组合", "CONCATENATE": "拼接 合并 连接", "TEXTJOIN": "拼接 合并 分隔符 连接",
    "TEXT": "格式化 转文本 星期 年月日 百分比", "SPLIT": "拆分 分割", "SUBSTITUTE": "替换", "REPLACE": "替换 打码 脱敏",
    "LEFT": "截取 开头 前几位", "RIGHT": "截取 末尾 后几位", "MID": "截取 中间", "LEN": "长度 字数 字符数",
    "FIND": "查找 位置 包含", "SEARCH": "查找 位置 包含", "CONTAINTEXT": "包含 含有", "TRIM": "去空格", "VALUE": "转数字",
    "UPPER": "大写", "LOWER": "小写", "REPT": "重复 星级",
    "SUM": "求和 合计 总数 相加", "SUMIF": "条件求和 合计 汇总 统计金额", "SUMIFS": "多条件求和 汇总",
    "COUNTIF": "条件计数 统计个数 数量", "COUNTIFS": "多条件计数", "AVERAGE": "平均 均值", "MEDIAN": "中位数",
    "ROUND": "四舍五入 保留小数 取整", "ROUNDUP": "进位 向上", "ROUNDDOWN": "舍去 向下", "TRUNC": "截断 去小数",
    "COUNTA": "计数 个数 数量 记录数", "COUNT": "计数 数字个数", "MAX": "最大 较大 最高", "MIN": "最小 较小 最低",
    "LARGE": "第几大 排名 前几名", "SMALL": "第几小 倒数", "INT": "取整 向下取整", "MOD": "余数 取余",
    "ABS": "绝对值", "POWER": "次方 幂 乘方", "SQRT": "开方 平方根", "CEILING": "向上取整", "FLOOR": "向下取整",
    "PRODUCT": "乘积 相乘", "SUMPRODUCT": "乘积求和 金额合计",
    "TODAY": "今天 当前日期", "NOW": "现在 当前时间", "DATEDIF": "相差 间隔 天数 月数 年龄 工龄 账龄 时长",
    "DAYS": "相差 天数 间隔", "DATEADD": "加减日期 几天后 到期日 推算", "EDATE": "几个月后 到期 续费",
    "EOMONTH": "月末 月底 最后一天", "WORKDAY": "工作日 截止日 排除周末", "NETWORKDAYS": "工作日天数 工期",
    "WEEKDAY": "星期几 周几", "WEEKNUM": "第几周 周数", "YEAR": "年份", "MONTH": "月份", "DAY": "日 几号",
    "HOUR": "小时", "DATE": "生成日期 组合日期", "TODATE": "转日期 时间戳",
    "FILTER": "筛选 过滤 符合条件 整表", "LOOKUP": "查找 带出 匹配 关联 vlookup 整表", "UNIQUE": "去重 不重复",
    "SORT": "排序", "FIRST": "第一个", "LAST": "最后一个", "LISTJOIN": "连接 拼接 列表转文本", "CONTAINS": "包含 是否含有",
    "RECORD_ID": "记录 ID 编号",
}


def catalog() -> list[dict]:
    return [{"name": e["name"], "category": e["category"], "signature": e["signature"], "desc": e["desc"],
             "returns": e["returns"], "keywords": KEYWORDS.get(e["name"], ""), "params": _params(e["signature"]),
             "examples": [{"code": c, "result": r} for c, r in e["examples"]]}
            for e in _ENTRIES]


def operators() -> list[dict]:
    return [{"op": o, "desc": d, "example": ex} for o, d, ex in OPERATORS]
