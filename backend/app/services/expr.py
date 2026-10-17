"""计算字段表达式引擎：AST 白名单解析，一份表达式两种求值——Python 行内计算（json 引擎）与 SQL 下推（physical 引擎）。

支持：四则运算 / 比较 / and·or·not / 括号 / 数字·字符串·布尔·null 常量；
函数白名单：iff(cond,a,b) coalesce ifnull abs round floor ceil min max year month day datediff；
字段引用：字段名（标识符）或 前缀.字段名（关联字段）；字段名含 - 空格等特殊字符时用括号引用 [任意字段名]。

智能表公式扩展（V3，见 formula_funcs.py）：Excel 风格大写函数（IF/IFS/TEXT/DATEDIF/COUNTA…，大小写不敏感）、
= 与 <> 比较、& 文本拼接、TRUE/FALSE、全角标点、链式调用 值.函数(参数)（等价于 函数(值, 参数)）。
旧版小写函数名保持原语义（报表/物理表 SQL 下推依赖），同名大写走新函数库。
"""
import ast
import re
from datetime import date, datetime

from sqlalchemy import Integer, and_, case, cast, func, literal, or_

# 函数白名单：参数个数（None=不限，至少 1）
FUNCS = {
    "iff": 3, "coalesce": None, "ifnull": 2, "concat": None,
    "abs": 1, "round": None, "floor": 1, "ceil": 1,
    "min": None, "max": None,
    "year": 1, "month": 1, "day": 1, "datediff": 2,
}
NUM_TYPES = {"int", "decimal"}

# 整表引用解析器：调用方（json_store 写路径 / 公式试算）在求值前设置，返回 table_id → 行列表（公式上下文形态）。
# 未设置时（报表/物理表等场景）整表引用求值报错。
from contextvars import ContextVar  # noqa: E402

TABLE_RESOLVER: ContextVar = ContextVar("formula_table_resolver", default=None)
_TABLE_REF_RE = re.compile(r"^#(\d+)(?:\.(.+))?$")


def parse_table_ref(name: str):
    """"#12" → (12, None) 整表；"#12.f_3" → (12, "f_3") 整列；非整表引用 → None。"""
    m = _TABLE_REF_RE.match(name or "")
    return (int(m.group(1)), m.group(2)) if m else None


def referenced_tables(node) -> set[int]:
    out: set[int] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            ref = parse_table_ref(n.id)
            if ref:
                out.add(ref[0])
    return out


class ExprError(ValueError):
    pass


def _field_name(node) -> str | None:
    """Name 或单级 Attribute（关联字段 前缀.字段名）→ 字段名；其余 → None。
    下划线开头的段一律拒绝（堵 __class__ 等属性逃逸）。"""
    if isinstance(node, ast.Name):
        return None if node.id.startswith("_") else node.id
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if node.value.id.startswith("_") or node.attr.startswith("_"):
            return None
        return f"{node.value.id}.{node.attr}"
    return None


_BRACKET_RE = re.compile(r"\[([^\[\]]+)\]")

_FULLWIDTH = str.maketrans({"，": ",", "（": "(", "）": ")", "“": '"', "”": '"', "‘": "'", "’": "'",
                            "＝": "=", "＞": ">", "＜": "<", "！": "!", "＋": "+", "－": "-", "＊": "*", "／": "/"})
_KW_CALLS = {"if", "and", "or", "not"}


def _excelize(src: str) -> str:
    """Excel 写法 → Python 表达式：全角标点、单个 = → ==、<> → !=、小写 if/and/or/not( → 大写函数、true/false。
    字符串字面量内部原样保留。"""
    src = src.translate(_FULLWIDTH)
    out, i, n, quote = [], 0, len(src), None
    while i < n:
        c = src[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "\"'":
            quote = c
            out.append(c)
            i += 1
            continue
        if c == "!" and src[i:i + 3] == "!==":
            out.append("!=")
            i += 3
            continue
        if c == "<" and i + 1 < n and src[i + 1] == ">":
            out.append("!=")
            i += 2
            continue
        if c == "=":
            prev = src[i - 1] if i else ""
            nxt = src[i + 1] if i + 1 < n else ""
            out.append("=" if prev in "<>!=" or nxt == "=" else "==")
            i += 1
            continue
        if c.isalpha() or c == "_":
            j = i
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            word = src[i:j]
            k = j
            while k < n and src[k] == " ":
                k += 1
            if word.lower() in _KW_CALLS and k < n and src[k] == "(":
                out.append(word.upper())
            elif word.lower() in ("true", "false"):
                out.append("True" if word.lower() == "true" else "False")
            else:
                out.append(word)
            i = j
            continue
        out.append(c)
        i += 1
    return "".join(out)


def canonical_func(name: str) -> str | None:
    """函数名归一：旧版小写名精确匹配优先（保持语义），否则大小写不敏感匹配新函数库。"""
    from .formula_funcs import FUNCTIONS
    if name in FUNCS:
        return name
    if name.upper() in FUNCTIONS:
        return name.upper()
    if name.lower() in FUNCS:
        return name.lower()
    return None


class _Rewriter(ast.NodeTransformer):
    """链式调用 值.FUNC(参数) → FUNC(值, 参数)；函数名归一化。"""

    def visit_Call(self, node):
        self.generic_visit(node)
        if isinstance(node.func, ast.Attribute) and canonical_func(node.func.attr):
            node = ast.Call(func=ast.Name(id=canonical_func(node.func.attr), ctx=ast.Load()),
                            args=[node.func.value, *node.args], keywords=node.keywords)
        elif isinstance(node.func, ast.Name) and canonical_func(node.func.id):
            node.func.id = canonical_func(node.func.id)
        return node


def parse(expr: str, allow_fields: set[str] | None = None) -> ast.AST:
    """解析并白名单校验表达式，返回 AST。allow_fields 给定时校验字段引用存在。
    括号引用：[任意字段名] —— 关联前缀含 - 空格 等 Python 标识符非法字符时，只能这样引用
    （先替换成占位标识符走 ast 解析，再还原为真实字段名；AST 只供自研求值器使用，Name.id 可为任意字符串）。"""
    mapping: dict[str, str] = {}

    def repl(m):
        key = f"FLDREF{len(mapping)}"
        mapping[key] = m.group(1).strip()
        return key

    src = _excelize(_BRACKET_RE.sub(repl, (expr or "").strip().lstrip("=")))
    if not src.strip():
        raise ExprError("公式内容不能为空")
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError as e:
        raise ExprError(f"表达式语法错误：{_syntax_hint(e)}") from e
    tree = ast.fix_missing_locations(_Rewriter().visit(tree))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in mapping:
            node.id = mapping[node.id]
    _check(tree.body, allow_fields)
    return tree.body


def _syntax_hint(e: SyntaxError) -> str:
    msg = e.msg or ""
    if "never closed" in msg or "unexpected EOF" in msg or "was never closed" in msg:
        return "括号未闭合"
    if "unmatched" in msg:
        return "多了右括号"
    if "unterminated string" in msg:
        return "字符串缺少结束引号"
    if "invalid syntax" in msg or "Perhaps you forgot a comma" in msg:
        return f"第 {e.offset or 1} 个字符附近有误（检查逗号、运算符是否完整）"
    return msg


def _check(node, allow_fields: set[str] | None) -> None:
    fname = _field_name(node)
    if fname is not None:
        if parse_table_ref(fname):
            return
        if allow_fields is not None and fname not in allow_fields:
            raise ExprError(f"表达式引用了不存在的字段：{fname}")
        return
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float, str, bool, type(None))):
            raise ExprError("不支持的常量类型")
        return
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.BitAnd, ast.Mod, ast.BitXor)):
        _check(node.left, allow_fields)
        _check(node.right, allow_fields)
        return
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd, ast.Not)):
        _check(node.operand, allow_fields)
        return
    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or not isinstance(node.ops[0], (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
            raise ExprError("比较运算只支持单层 == != < <= > >=")
        _check(node.left, allow_fields)
        _check(node.comparators[0], allow_fields)
        return
    if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
        for v in node.values:
            _check(v, allow_fields)
        return
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id not in FUNCS:
        from .formula_funcs import FUNCTIONS
        spec = FUNCTIONS.get(node.func.id)
        if spec is None:
            raise ExprError(f"不支持的函数：{node.func.id}")
        if node.keywords:
            raise ExprError("函数不支持关键字参数")
        n = len(node.args)
        if n < spec["min"] or (spec["max"] is not None and n > spec["max"]):
            rng = (f"{spec['min']}" if spec["min"] == spec["max"] else
                   f"{spec['min']}~{spec['max']}" if spec["max"] is not None else f"至少 {spec['min']}")
            raise ExprError(f"函数 {node.func.id} 需要 {rng} 个参数，当前 {n} 个（{spec['signature']}）")
        for a in node.args:
            _check(a, allow_fields)
        return
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCS:
        if node.keywords:
            raise ExprError("函数不支持关键字参数")
        want = FUNCS[node.func.id]
        if want is not None and len(node.args) != want:
            raise ExprError(f"函数 {node.func.id} 需要 {want} 个参数")
        if want is None and not node.args:
            raise ExprError(f"函数 {node.func.id} 至少需要 1 个参数")
        for a in node.args:
            _check(a, allow_fields)
        return
    if isinstance(node, ast.Call):
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None) or "?"
        raise ExprError(f"不支持的函数：{name}")
    raise ExprError("表达式含不允许的语法（仅支持四则运算/比较/逻辑/白名单函数/字段引用）")


def referenced_fields(node) -> set[str]:
    out: set[str] = set()

    def visit(n) -> None:
        fname = _field_name(n)
        if fname is not None:
            if not parse_table_ref(fname):   # 整表引用不计入本行字段依赖
                out.add(fname)
            return
        if isinstance(n, ast.Call):
            for a in n.args:  # func 名（iff/coalesce…）不是字段引用
                visit(a)
            return
        for child in ast.iter_child_nodes(n):
            visit(child)

    visit(node)
    return out


# ---------- Python 行内求值（json 引擎） ----------

def _truth(v) -> bool:
    return bool(v)


_OP_SYMBOL = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Mod: "%", ast.BitXor: "^"}


def _arith(op, l, r, strict: bool):
    """四则运算：数字样式文本自动转数字；日期 ± 天数、日期 - 日期 = 天数；文本 + 文本 保持拼接（旧语义）。"""
    from .formula_funcs import FormulaError, to_number
    sym = _OP_SYMBOL[type(op)]
    if isinstance(op, ast.Add) and isinstance(l, str) and isinstance(r, str):
        try:
            l, r = to_number(l, sym, 1), to_number(r, sym, 2)
        except FormulaError:
            return l + r
    if isinstance(l, (date, datetime)) or isinstance(r, (date, datetime)):
        from datetime import timedelta
        if isinstance(op, ast.Sub) and isinstance(l, (date, datetime)) and isinstance(r, (date, datetime)):
            a = l.date() if isinstance(l, datetime) and not isinstance(r, datetime) else l
            b = r.date() if isinstance(r, datetime) and not isinstance(l, datetime) else r
            return (a - b).days
        if isinstance(op, (ast.Add, ast.Sub)) and isinstance(l, (date, datetime)):
            k = to_number(r, sym, 2)
            return l + timedelta(days=k) if isinstance(op, ast.Add) else l - timedelta(days=k)
        if isinstance(op, ast.Add) and isinstance(r, (date, datetime)):
            return r + timedelta(days=to_number(l, sym, 1))
        raise FormulaError("类型转换错误", f"“{sym}”运算不能用于日期。")
    a, b = to_number(l, sym, 1), to_number(r, sym, 2)
    if isinstance(op, ast.BitXor):
        return a ** b
    if isinstance(op, ast.Add):
        return a + b
    if isinstance(op, ast.Sub):
        return a - b
    if isinstance(op, ast.Mult):
        return a * b
    if b == 0:
        if strict:
            raise FormulaError("除零错误", f"“{sym}”运算的除数为 0。")
        return None
    return a / b if isinstance(op, ast.Div) else a % b


def _call_new(node, row: dict, strict: bool):
    """新函数库求值（惰性函数 IF/IFS/IFERROR/SWITCH 在此特判）。"""
    from .formula_funcs import FUNCTIONS, FormulaError, to_bool
    name = node.func.id
    if name == "IF":
        cond = evaluate(node.args[0], row, strict)
        if to_bool(cond):
            return evaluate(node.args[1], row, strict)
        return evaluate(node.args[2], row, strict) if len(node.args) > 2 else None
    if name == "IFS":
        if len(node.args) % 2:
            raise FormulaError("参数错误", "“IFS”函数的条件与返回值需成对出现。")
        for i in range(0, len(node.args), 2):
            if to_bool(evaluate(node.args[i], row, strict)):
                return evaluate(node.args[i + 1], row, strict)
        return None
    if name == "IFERROR":
        try:
            return evaluate(node.args[0], row, True)
        except (FormulaError, ExprError, TypeError, ValueError, ZeroDivisionError):
            return evaluate(node.args[1], row, strict)
    if name in ("ISERROR", "ISERR"):
        try:
            evaluate(node.args[0], row, True)
            return False
        except (FormulaError, ExprError, TypeError, ValueError, ZeroDivisionError):
            return True
    if name == "RECORD_ID":
        return row.get("id")
    if name == "SWITCH":
        target = evaluate(node.args[0], row, strict)
        rest = node.args[1:]
        for i in range(0, len(rest) - 1, 2):
            v = evaluate(rest[i], row, strict)
            if v == target or (v is not None and target is not None and str(v) == str(target)):
                return evaluate(rest[i + 1], row, strict)
        return evaluate(rest[-1], row, strict) if len(rest) % 2 else None
    args = [evaluate(a, row, strict) for a in node.args]
    return FUNCTIONS[name]["impl"](*args)


def evaluate(node, row: dict, strict: bool = False):
    """对单行记录求值。None 传播（对齐 SQL 三值逻辑）；除零 → None。
    strict=True（编辑器试算）：类型转换/除零/参数错误抛 FormulaError，供前端展示「第 1 行 = 错误」。"""
    from .formula_funcs import Column, FormulaError
    fname = _field_name(node)
    if fname is not None:
        ref = parse_table_ref(fname)
        return _resolve_table(ref) if ref else row.get(fname)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitAnd):
        from .formula_funcs import to_text
        l, r = evaluate(node.left, row, strict), evaluate(node.right, row, strict)
        if isinstance(l, Column) or isinstance(r, Column):
            return _broadcast(lambda a, b: to_text(a) + to_text(b), l, r)
        return to_text(l) + to_text(r)
    if isinstance(node, ast.BinOp):
        l, r = evaluate(node.left, row, strict), evaluate(node.right, row, strict)
        if isinstance(l, Column) or isinstance(r, Column):
            return _broadcast(lambda a, b: _binop_scalar(node.op, a, b, False), l, r)
        return _binop_scalar(node.op, l, r, strict)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id not in FUNCS:
        try:
            return _call_new(node, row, strict)
        except FormulaError:
            if strict:
                raise
            return None
        except (TypeError, ValueError, OverflowError, ZeroDivisionError) as e:
            if strict:
                raise FormulaError("计算错误", f"“{node.func.id}”函数计算失败：{e}")
            return None
    if isinstance(node, ast.UnaryOp):
        v = evaluate(node.operand, row, strict)
        if isinstance(node.op, ast.Not):
            return not _truth(v)
        return None if v is None else (+v if isinstance(node.op, ast.UAdd) else -v)
    if isinstance(node, ast.Compare):
        l, r = evaluate(node.left, row, strict), evaluate(node.comparators[0], row, strict)
        op = node.ops[0]
        if isinstance(l, Column) or isinstance(r, Column):
            return _broadcast(lambda a, b: _compare_scalar(op, a, b), l, r)
        return _compare_scalar(op, l, r)
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(_truth(evaluate(v, row, strict)) for v in node.values)
        return any(_truth(evaluate(v, row, strict)) for v in node.values)
    if isinstance(node, ast.Call):
        name = node.func.id
        args = [evaluate(a, row, strict) for a in node.args]
        if name == "iff":
            return args[1] if _truth(args[0]) else args[2]
        if name in ("coalesce", "ifnull"):
            return next((a for a in args if a is not None), None)
        if name == "concat":
            # 字符串拼接：任一为 None 则整体 None（对齐 SQL || 三值逻辑）
            if any(a is None for a in args):
                return None
            return "".join(str(a) for a in args)
        if name in ("min", "max"):
            if any(a is None for a in args):
                return None
            return min(args) if name == "min" else max(args)
        if name == "datediff":
            a, b = args
            if a is None or b is None:
                return None
            if not isinstance(a, (date, datetime)) or not isinstance(b, (date, datetime)):
                return None
            return (a - b).days
        if name in ("year", "month", "day"):
            v = args[0]
            if v is None or not isinstance(v, (date, datetime)):
                return None
            return getattr(v, name)
        v = args[0]
        if v is None:
            return None
        if name == "abs":
            return abs(v)
        if name == "floor":
            import math
            return math.floor(v)
        if name == "ceil":
            import math
            return math.ceil(v)
        if name == "round":
            n = args[1] if len(args) > 1 else 0
            return None if n is None else round(v, int(n))
    raise ExprError("表达式求值失败")


def _resolve_table(ref):
    """[#表] → 整表记录列；[#表.字段] → 该字段整列取值。"""
    from .formula_funcs import Column, FormulaError
    resolver = TABLE_RESOLVER.get()
    if resolver is None:
        raise FormulaError("引用错误", "当前场景不支持整表引用。")
    table_id, field = ref
    rows = resolver(table_id)
    if rows is None:
        raise FormulaError("引用错误", "引用的表不存在或无权访问。")
    if field is None:
        return Column(rows)
    if rows and field not in rows[0]:
        raise FormulaError("引用错误", "引用的字段不存在。")
    return Column(r.get(field) for r in rows)


def _broadcast(fn, l, r):
    """整列逐元素运算：列 ∘ 标量 / 列 ∘ 列（取较短长度）。单元素出错记为空，不中断整列。"""
    from .formula_funcs import Column
    if isinstance(l, Column) and isinstance(r, Column):
        pairs = zip(l, r)
    elif isinstance(l, Column):
        pairs = ((a, r) for a in l)
    else:
        pairs = ((l, b) for b in r)
    out = []
    for a, b in pairs:
        try:
            out.append(fn(a, b))
        except Exception:  # noqa: BLE001
            out.append(None)
    return Column(out)


def _binop_scalar(op, l, r, strict: bool):
    from .formula_funcs import FormulaError
    if l is None or r is None:
        return None
    try:
        return _arith(op, l, r, strict)
    except FormulaError:
        if strict:
            raise
        return None
    except (TypeError, ValueError, OverflowError):
        if strict:
            raise FormulaError("类型转换错误", f"“{_OP_SYMBOL[type(op)]}”运算的参数类型不匹配。")
        return None


def _compare_scalar(op, l, r):
    if l is None or r is None:
        # Excel 语义：空值与空字符串相等（[电话]="" 判断未填写）
        if isinstance(op, (ast.Eq, ast.NotEq)) and (l in (None, "") and r in (None, "")):
            return isinstance(op, ast.Eq)
        if isinstance(op, (ast.Eq, ast.NotEq)) and (l in (None, "") or r in (None, "")):
            return isinstance(op, ast.NotEq)
        return None
    l, r = _cmp_coerce(l, r)
    try:
        if isinstance(op, ast.Eq):
            return l == r
        if isinstance(op, ast.NotEq):
            return l != r
        if isinstance(op, ast.Lt):
            return l < r
        if isinstance(op, ast.LtE):
            return l <= r
        if isinstance(op, ast.Gt):
            return l > r
        return l >= r
    except TypeError:
        return None


def _cmp_coerce(l, r):
    """比较前对齐类型：数字 vs 数字样式文本 → 数字；日期 vs 日期文本 → 日期；多值（列表）与单值比较取「包含」前的文本形态。"""
    from .formula_funcs import FormulaError, to_date, to_number, to_text
    if isinstance(l, bool) or isinstance(r, bool):
        return l, r
    if isinstance(l, (int, float)) and isinstance(r, str) or isinstance(r, (int, float)) and isinstance(l, str):
        try:
            return to_number(l, "=", 1), to_number(r, "=", 2)
        except FormulaError:
            return to_text(l), to_text(r)
    if isinstance(l, (date, datetime)) and isinstance(r, str) or isinstance(r, (date, datetime)) and isinstance(l, str):
        try:
            a, b = to_date(l, "=", 1), to_date(r, "=", 2)
            if isinstance(a, datetime) != isinstance(b, datetime):
                a = a.date() if isinstance(a, datetime) else a
                b = b.date() if isinstance(b, datetime) else b
            return a, b
        except FormulaError:
            return to_text(l), to_text(r)
    if isinstance(l, list) or isinstance(r, list):
        return to_text(l), to_text(r)
    return l, r


# ---------- SQL 下推（physical 引擎） ----------

def to_sql(node, resolve, dialect: str = "sqlite"):
    """AST → SQLAlchemy 表达式。resolve(字段名) → Column；dialect 用于方言分支。"""
    fname = _field_name(node)
    if fname is not None:
        if parse_table_ref(fname):
            raise ExprError("整表引用暂不支持在该场景下计算")
        return resolve(fname)
    if isinstance(node, ast.Constant):
        return literal(node.value)
    if isinstance(node, ast.BinOp):
        l, r = to_sql(node.left, resolve, dialect), to_sql(node.right, resolve, dialect)
        if isinstance(node.op, ast.BitAnd):
            return l.op("||")(r) if dialect == "sqlite" else func.concat(l, r)
        if isinstance(node.op, ast.Mod):
            return l % r
        if isinstance(node.op, ast.BitXor):
            return func.power(l, r)
        if isinstance(node.op, ast.Add):
            return l + r
        if isinstance(node.op, ast.Sub):
            return l - r
        if isinstance(node.op, ast.Mult):
            return l * r
        return l / r
    if isinstance(node, ast.UnaryOp):
        v = to_sql(node.operand, resolve, dialect)
        if isinstance(node.op, ast.Not):
            return ~v
        return +v if isinstance(node.op, ast.UAdd) else -v
    if isinstance(node, ast.Compare):
        l, r = to_sql(node.left, resolve, dialect), to_sql(node.comparators[0], resolve, dialect)
        op = node.ops[0]
        if isinstance(op, ast.Eq):
            return l == r
        if isinstance(op, ast.NotEq):
            return l != r
        if isinstance(op, ast.Lt):
            return l < r
        if isinstance(op, ast.LtE):
            return l <= r
        if isinstance(op, ast.Gt):
            return l > r
        return l >= r
    if isinstance(node, ast.BoolOp):
        vs = [to_sql(v, resolve, dialect) for v in node.values]
        return and_(*vs) if isinstance(node.op, ast.And) else or_(*vs)
    if isinstance(node, ast.Call):
        name = node.func.id
        if name not in FUNCS:
            legacy = {"IF": "iff", "ROUND": "round", "ABS": "abs", "MIN": "min", "MAX": "max", "YEAR": "year",
                      "MONTH": "month", "DAY": "day", "CONCAT": "concat"}.get(name)
            if not legacy or (name == "IF" and len(node.args) != 3):
                raise ExprError(f"函数 {name} 暂不支持在该场景下计算")
            name = legacy
        args = [to_sql(a, resolve, dialect) for a in node.args]
        if name == "iff":
            return case((args[0], args[1]), else_=args[2])
        if name in ("coalesce", "ifnull"):
            return func.coalesce(*args)
        if name == "concat":
            # SQLite 用 || 拼接（NULL 传染，与 evaluate 语义一致）；其他方言用标准 concat
            if dialect == "sqlite":
                out = args[0]
                for a in args[1:]:
                    out = out.op("||")(a)
                return out
            return func.concat(*args)
        if name == "min":
            return func.min(*args) if dialect == "sqlite" else func.least(*args)
        if name == "max":
            return func.max(*args) if dialect == "sqlite" else func.greatest(*args)
        if name == "datediff":
            if dialect == "sqlite":
                return cast(func.julianday(args[0]) - func.julianday(args[1]), Integer)
            return func.datediff(args[0], args[1])
        if name in ("year", "month", "day"):
            if dialect == "sqlite":
                fmt = {"year": "%Y", "month": "%m", "day": "%d"}[name]
                return cast(func.strftime(fmt, args[0]), Integer)
            return getattr(func, name)(args[0])
        return getattr(func, name)(*args)
    raise ExprError("表达式无法下推为 SQL")


# ---------- 类型推导 ----------

def infer_type(node, fields_by_name: dict) -> str:
    """推导表达式结果类型：int / decimal / bool / varchar。date/datetime 参与运算仅允许作为 datediff/year 等函数参数。"""
    fname = _field_name(node)
    if fname is not None:
        f = fields_by_name.get(fname)
        t = getattr(f, "data_type", None) or "varchar"
        return t if t in ("int", "decimal", "bool", "varchar") else t
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return "bool"
        if isinstance(node.value, int):
            return "int"
        if isinstance(node.value, float):
            return "decimal"
        return "varchar"
    if isinstance(node, (ast.Compare, ast.BoolOp)) or (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not)):
        return "bool"
    if isinstance(node, ast.BinOp):
        lt, rt = infer_type(node.left, fields_by_name), infer_type(node.right, fields_by_name)
        if lt not in NUM_TYPES or rt not in NUM_TYPES:
            return "decimal"  # 容错：非数值运算结果按 decimal（求值时多半为 None）
        if isinstance(node.op, ast.Div) or "decimal" in (lt, rt):
            return "decimal"
        return "int"
    if isinstance(node, ast.UnaryOp):
        return infer_type(node.operand, fields_by_name)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitAnd):
        return "varchar"
    if isinstance(node, ast.Call) and node.func.id not in FUNCS:
        from .formula_funcs import FUNCTIONS
        ret = FUNCTIONS.get(node.func.id, {}).get("returns")
        return {"number": "decimal", "text": "varchar", "boolean": "bool", "date": "date"}.get(ret, "varchar")
    if isinstance(node, ast.Call):
        name = node.func.id
        if name in ("year", "month", "day", "datediff", "floor", "ceil"):
            return "int"
        if name == "concat":
            return "varchar"
        if name == "iff":
            ts = {infer_type(node.args[1], fields_by_name), infer_type(node.args[2], fields_by_name)}
        else:
            ts = {infer_type(a, fields_by_name) for a in node.args}
        if "decimal" in ts:
            return "decimal"
        if "int" in ts:
            return "int"
        if ts == {"bool"}:
            return "bool"
        return "varchar"
    return "varchar"
