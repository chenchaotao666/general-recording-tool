"""计算字段表达式引擎：AST 白名单解析，一份表达式两种求值——Python 行内计算（json 引擎）与 SQL 下推（physical 引擎）。

支持：四则运算 / 比较 / and·or·not / 括号 / 数字·字符串·布尔·null 常量；
函数白名单：iff(cond,a,b) coalesce ifnull abs round floor ceil min max year month day datediff；
字段引用：字段名（标识符）或 前缀.字段名（关联字段）；字段名含 - 空格等特殊字符时用括号引用 [任意字段名]。
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


def parse(expr: str, allow_fields: set[str] | None = None) -> ast.AST:
    """解析并白名单校验表达式，返回 AST。allow_fields 给定时校验字段引用存在。
    括号引用：[任意字段名] —— 关联前缀含 - 空格 等 Python 标识符非法字符时，只能这样引用
    （先替换成占位标识符走 ast 解析，再还原为真实字段名；AST 只供自研求值器使用，Name.id 可为任意字符串）。"""
    mapping: dict[str, str] = {}

    def repl(m):
        key = f"FLDREF{len(mapping)}"
        mapping[key] = m.group(1).strip()
        return key

    src = _BRACKET_RE.sub(repl, (expr or "").strip())
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError as e:
        raise ExprError(f"表达式语法错误：{e.msg}") from e
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in mapping:
            node.id = mapping[node.id]
    _check(tree.body, allow_fields)
    return tree.body


def _check(node, allow_fields: set[str] | None) -> None:
    fname = _field_name(node)
    if fname is not None:
        if allow_fields is not None and fname not in allow_fields:
            raise ExprError(f"表达式引用了不存在的字段：{fname}")
        return
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float, str, bool, type(None))):
            raise ExprError("不支持的常量类型")
        return
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
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
    raise ExprError("表达式含不允许的语法（仅支持四则运算/比较/逻辑/白名单函数/字段引用）")


def referenced_fields(node) -> set[str]:
    out: set[str] = set()

    def visit(n) -> None:
        fname = _field_name(n)
        if fname is not None:
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


def evaluate(node, row: dict):
    """对单行记录求值。None 传播（对齐 SQL 三值逻辑）；除零 → None。"""
    fname = _field_name(node)
    if fname is not None:
        return row.get(fname)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp):
        l, r = evaluate(node.left, row), evaluate(node.right, row)
        if l is None or r is None:
            return None
        try:
            if isinstance(node.op, ast.Add):
                return l + r
            if isinstance(node.op, ast.Sub):
                return l - r
            if isinstance(node.op, ast.Mult):
                return l * r
            if r == 0:
                return None
            return l / r
        except TypeError:
            return None
    if isinstance(node, ast.UnaryOp):
        v = evaluate(node.operand, row)
        if isinstance(node.op, ast.Not):
            return not _truth(v)
        return None if v is None else (+v if isinstance(node.op, ast.UAdd) else -v)
    if isinstance(node, ast.Compare):
        l, r = evaluate(node.left, row), evaluate(node.comparators[0], row)
        if l is None or r is None:
            return None
        try:
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
        except TypeError:
            return None
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(_truth(evaluate(v, row)) for v in node.values)
        return any(_truth(evaluate(v, row)) for v in node.values)
    if isinstance(node, ast.Call):
        name = node.func.id
        args = [evaluate(a, row) for a in node.args]
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


# ---------- SQL 下推（physical 引擎） ----------

def to_sql(node, resolve, dialect: str = "sqlite"):
    """AST → SQLAlchemy 表达式。resolve(字段名) → Column；dialect 用于方言分支。"""
    fname = _field_name(node)
    if fname is not None:
        return resolve(fname)
    if isinstance(node, ast.Constant):
        return literal(node.value)
    if isinstance(node, ast.BinOp):
        l, r = to_sql(node.left, resolve, dialect), to_sql(node.right, resolve, dialect)
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
