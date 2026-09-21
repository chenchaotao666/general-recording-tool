"""表名/字段名生成工具。"""
import re

from pypinyin import lazy_pinyin


def slugify(label: str) -> str:
    """中文标签转拼音蛇形命名，英文直接转小写蛇形。"""
    label = (label or "").strip()
    if not label:
        return "table"
    if re.fullmatch(r"[A-Za-z0-9 _\-]+", label):
        s = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    else:
        s = "_".join(lazy_pinyin(label))
        s = re.sub(r"[^a-z0-9_]", "", s)
        s = re.sub(r"_+", "_", s).strip("_")
    if not s or not s[0].isalpha():
        s = "t_" + s
    return s[:40] or "table"


def safe_field_name(name: str, used: set, idx: int) -> str:
    """把 LLM 给的 field_name 清洗成合法 snake_case，并保证唯一。"""
    n = re.sub(r"[^a-z0-9_]", "_", (name or "").lower())
    n = re.sub(r"_+", "_", n).strip("_")
    if not n or not n[0].isalpha():
        n = slugify(name) if name else f"col_{idx}"
        if not n or not n[0].isalpha():
            n = f"col_{idx}"
    n = n[:40]
    base, k = n, 2
    while n in used:
        n = f"{base}_{k}"
        k += 1
    used.add(n)
    return n
