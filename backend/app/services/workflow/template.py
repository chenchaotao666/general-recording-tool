"""模板渲染：{path.to.value} 点路径语法，单花括号点路径语法。

根命名空间：trigger / nodes / workflow / run / now。
- 字符串内插值：解析失败（路径不存在 / 值为 None）渲染为空串，不抛错；
  调用方传入 missing=[] 时，未命中的路径会被收集（引擎据此生成运行警告）；
- 整体模板（值恰好是一个完整模板表达式）：注入原始对象（dict/list/int 等），
  供 JSON 字段整体引用，如 "record": "{trigger.record}"；
- 列表渲染过滤器：{nodes.q_1.records | 表格} / {nodes.q_1.records | 列表}，
  把记录列表渲染成 Markdown 表格 / 编号清单，避免通知里出现原始 JSON；
- 兼容 {{path}} 双花括号写法（渲染前归一化为单花括号），降低其他平台迁移用户的误用。
"""
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

TOKEN_RE = re.compile(r"\{([^{}]+)\}")
WHOLE_TOKEN_RE = re.compile(r"^\{([^{}]+)\}$")
# {{path}} 双花括号兼容：必须先于单花括号规则处理，否则 {{a}} 会被拆成内层 {a} + 残留 }
DOUBLE_TOKEN_RE = re.compile(r"\{\{([^{}]+)\}\}")
WHOLE_DOUBLE_TOKEN_RE = re.compile(r"^\{\{([^{}]+)\}\}$")
# 提取字符串里的全部变量（两种括号风格），lint 静态校验用
VAR_TOKEN_RE = re.compile(r"\{\{?([^{}]+)\}?\}")


def normalize_braces(s: str) -> str:
    """{{path}} → {path}（双花括号兼容归一化）。"""
    return DOUBLE_TOKEN_RE.sub(lambda m: "{" + m.group(1).strip() + "}", s)


def now_vars() -> dict:
    """内置时间变量（{now.xxx}）：每次执行实时计算；中断恢复时取恢复当下的时间。"""
    n = datetime.now()
    today = n.date()
    week_start = today - timedelta(days=today.weekday())          # 本周一
    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    return {
        "today": today.isoformat(),
        "yesterday": (today - timedelta(days=1)).isoformat(),
        "tomorrow": (today + timedelta(days=1)).isoformat(),
        "datetime": n.isoformat(sep=" ", timespec="seconds"),
        "week_start": week_start.isoformat(),
        "last_week_start": (week_start - timedelta(days=7)).isoformat(),
        "last_week_end": (week_start - timedelta(days=1)).isoformat(),
        "month_start": month_start.isoformat(),
        "last_month_start": last_month_end.replace(day=1).isoformat(),
        "last_month_end": last_month_end.isoformat(),
    }


def resolve_path(context: dict, path: str):
    """按点路径取值；数字段作数组下标。任何一段缺失返回 None。"""
    return resolve_path_found(context, path)[0]


def resolve_path_found(context: dict, path: str):
    """同 resolve_path，但区分「路径不存在」和「值本身是 None」：返回 (值, 路径是否存在)。
    运行警告只针对路径不存在（大概率是变量写错），值为 None 是正常数据不告警。"""
    cur = context
    for seg in path.strip().split("."):
        if isinstance(cur, dict):
            if seg not in cur:
                return None, False
            cur = cur[seg]
        elif isinstance(cur, (list, tuple)) and seg.isdigit():
            idx = int(seg)
            if not 0 <= idx < len(cur):
                return None, False
            cur = cur[idx]
        else:
            return None, False
        if cur is None:
            return None, True
    return cur, True


def _miss(missing: list | None, path: str) -> None:
    p = path.strip()
    if missing is not None and p not in missing:
        missing.append(p)


# ---------- 列表渲染过滤器（{路径 | 表格} / {路径 | 列表}） ----------

def split_filter(path: str) -> tuple[str, str]:
    """拆出过滤器：'nodes.q_1.records | 表格' → ('nodes.q_1.records', '表格')。"""
    p, _, f = path.partition("|")
    return p.strip(), f.strip()


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        import json
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, datetime):
        return v.isoformat(sep=" ")
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def _render_table(v) -> str:
    """记录列表 → Markdown 表格（列为字段并集，保持字段顺序）。"""
    if isinstance(v, list) and v and all(isinstance(r, dict) for r in v):
        keys = list(v[0].keys())
        for r in v[1:]:
            keys.extend(k for k in r.keys() if k not in keys)
        lines = ["| " + " | ".join(keys) + " |", "|" + " --- |" * len(keys)]
        lines += ["| " + " | ".join(_cell(r.get(k)) for k in keys) + " |" for r in v]
        return "\n".join(lines)
    if isinstance(v, list):
        return "\n".join(_cell(x) for x in v) or "（无记录）"
    return _cell(v)


def _render_list(v) -> str:
    """记录列表 → 编号清单：每条一行「1. 字段：值，字段：值」。"""
    if isinstance(v, list):
        out = []
        for i, r in enumerate(v, 1):
            if isinstance(r, dict):
                out.append(f"{i}. " + "，".join(f"{k}：{_cell(x)}" for k, x in r.items()))
            else:
                out.append(f"{i}. {_cell(r)}")
        return "\n".join(out) or "（无记录）"
    return _cell(v)


_FILTERS = {"表格": _render_table, "table": _render_table, "列表": _render_list, "list": _render_list}


def apply_filter(v, filt: str):
    """应用过滤器；未知过滤器返回 None（调用方回退到默认字符串化）。"""
    fn = _FILTERS.get(filt)
    return fn(v) if fn else None


def render_string(context: dict, s: str, missing: list | None = None) -> str:
    """字符串内插值：所有 {path} 替换为字符串形式（None → 空串；路径不存在记入 missing）。"""
    def repl(m):
        path, filt = split_filter(m.group(1))
        v, found = resolve_path_found(context, path)
        if not found:
            _miss(missing, path)
            return ""
        if filt:
            out = apply_filter(v, filt)
            if out is not None:
                return out
        if v is None:
            return ""
        if isinstance(v, (dict, list)):
            import json
            return json.dumps(v, ensure_ascii=False)
        if isinstance(v, (datetime, date)):
            return v.isoformat(sep=" ") if isinstance(v, datetime) else v.isoformat()
        return str(v)
    return TOKEN_RE.sub(repl, normalize_braces(s or ""))


def render_value(context: dict, value, missing: list | None = None):
    """递归渲染 config 中的值：整体模板注入原始对象，其余字符串走插值。"""
    if isinstance(value, str):
        stripped = value.strip()
        m = WHOLE_TOKEN_RE.match(stripped) or WHOLE_DOUBLE_TOKEN_RE.match(stripped)
        if m:
            path, filt = split_filter(m.group(1))
            # 带过滤器的整体模板要的是渲染后的文本，不是原始对象
            resolved, found = resolve_path_found(context, path)
            if not found:
                _miss(missing, path)
                return None
            if filt:
                out = apply_filter(resolved, filt)
                if out is not None:
                    return out
            # 原始对象（dict/list/int/bool/None）整体注入；纯字符串也直接返回（保留原样不二次转义）
            if resolved is None or isinstance(resolved, (dict, list, int, float, bool)):
                return resolved
            if isinstance(resolved, (datetime, date)):
                return resolved.isoformat(sep=" ") if isinstance(resolved, datetime) else resolved.isoformat()
            return str(resolved)
        return render_string(context, value, missing)
    if isinstance(value, dict):
        return {k: render_value(context, v, missing) for k, v in value.items()}
    if isinstance(value, list):
        return [render_value(context, v, missing) for v in value]
    return value


def render_config(context: dict, config: dict, missing: list | None = None) -> dict:
    return {k: render_value(context, v, missing) for k, v in (config or {}).items()}


def jsonable(obj):
    """把节点输出/触发数据中的 datetime、Decimal 等转成 JSON 可序列化值（写入 JSON 列前必须过一遍）。"""
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat(sep=" ")
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    return obj


# ---------- 变量路径建议（「是否想填 xxx」） ----------

def enumerate_paths(context: dict, max_depth: int = 3, max_items: int = 400) -> list[str]:
    """枚举 context 里可引用的变量路径（列表只展开首元素 .0），供模糊匹配的候选集。"""
    out: list[str] = []

    def walk(prefix: str, val, depth: int) -> None:
        if len(out) >= max_items or depth > max_depth:
            return
        if isinstance(val, dict):
            for k, v in val.items():
                p = f"{prefix}.{k}"
                out.append(p)
                walk(p, v, depth + 1)
        elif isinstance(val, (list, tuple)) and val:
            p = f"{prefix}.0"
            out.append(p)
            walk(p, val[0], depth + 1)

    for root in ("trigger", "nodes", "now"):
        if root in context:
            walk(root, context[root], 1)
    return out


def suggest_var(context: dict, path: str) -> str | None:
    """对未命中的变量路径给出一个最接近的可引用路径（没有足够相似的则不给）。"""
    import difflib
    matches = difflib.get_close_matches(path.strip(), enumerate_paths(context), n=1, cutoff=0.45)
    return matches[0] if matches else None
