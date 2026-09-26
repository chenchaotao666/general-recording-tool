"""模板渲染：{path.to.value} 点路径语法，沿用 actions.render_template 的单花括号风格。

根命名空间：trigger / nodes / workflow / run / now。
- 字符串内插值：解析失败（路径不存在 / 值为 None）渲染为空串，不抛错；
- 整体模板（值恰好是一个完整模板表达式）：注入原始对象（dict/list/int 等），
  供 JSON 字段整体引用，如 "record": "{trigger.record}"。
"""
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

TOKEN_RE = re.compile(r"\{([^{}]+)\}")
WHOLE_TOKEN_RE = re.compile(r"^\{([^{}]+)\}$")


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
    cur = context
    for seg in path.strip().split("."):
        if isinstance(cur, dict):
            cur = cur.get(seg)
        elif isinstance(cur, (list, tuple)) and seg.isdigit():
            idx = int(seg)
            cur = cur[idx] if 0 <= idx < len(cur) else None
        else:
            return None
        if cur is None:
            return None
    return cur


def render_string(context: dict, s: str) -> str:
    """字符串内插值：所有 {path} 替换为字符串形式（None → 空串）。"""
    def repl(m):
        v = resolve_path(context, m.group(1))
        if v is None:
            return ""
        if isinstance(v, (dict, list)):
            import json
            return json.dumps(v, ensure_ascii=False)
        if isinstance(v, (datetime, date)):
            return v.isoformat(sep=" ") if isinstance(v, datetime) else v.isoformat()
        return str(v)
    return TOKEN_RE.sub(repl, s or "")


def render_value(context: dict, value):
    """递归渲染 config 中的值：整体模板注入原始对象，其余字符串走插值。"""
    if isinstance(value, str):
        m = WHOLE_TOKEN_RE.match(value.strip())
        if m:
            resolved = resolve_path(context, m.group(1))
            # 原始对象（dict/list/int/bool/None）整体注入；纯字符串也直接返回（保留原样不二次转义）
            if resolved is None or isinstance(resolved, (dict, list, int, float, bool)):
                return resolved
            if isinstance(resolved, (datetime, date)):
                return resolved.isoformat(sep=" ") if isinstance(resolved, datetime) else resolved.isoformat()
            return str(resolved)
        return render_string(context, value)
    if isinstance(value, dict):
        return {k: render_value(context, v) for k, v in value.items()}
    if isinstance(value, list):
        return [render_value(context, v) for v in value]
    return value


def render_config(context: dict, config: dict) -> dict:
    return {k: render_value(context, v) for k, v in (config or {}).items()}


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
