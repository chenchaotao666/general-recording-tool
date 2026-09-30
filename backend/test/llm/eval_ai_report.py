# -*- coding: utf-8 -*-
"""AI 生成报表的准确性评测：按「界面上的每个可配置选项」逐条验证 AI 是否设置正确。

用法（在 backend 目录，用项目 venv）：
    ./.venv/Scripts/python test/llm/eval_ai_report.py            # 全部用例
    ./.venv/Scripts/python test/llm/eval_ai_report.py 6 12       # 只跑指定编号
    ./.venv/Scripts/python test/llm/eval_ai_report.py --group chart   # 只跑某组

评测在独立数据库（test/llm/eval_ai_report.db）里进行：每个用例建临时表（带示例数据），
AI 生成配置 → 结构断言 → 落库保存 → 试运行，结束后临时表即删，不影响业务数据。

评分只认结构与可运行性（块类型/聚合/分组/口径/明细列…），不评文案。
某选项持续 FAIL 通常意味着提示词（app/services/llm/prompts.py 的 build_report_prompt）
没有向模型说明这个选项——把 FAIL 用例的「生成结果」和界面选项对照着补提示词即可。
"""
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("GRT_DATABASE_URL", f"sqlite:///{(Path(__file__).parent / 'eval_ai_report.db').as_posix()}")
os.environ.setdefault("GRT_SECRET_KEY", "eval")

from types import SimpleNamespace  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.services.llm.gateway import assist_report  # noqa: E402

# ---------- 测试表结构 ----------
# (field_name, label, data_type[, 枚举可选值])
PROD_FIELDS = [
    ("batch_no", "批次号", "varchar"), ("line", "生产线", "varchar"),
    ("product", "产品名称", "varchar"),
    ("shift", "班次", "varchar", ["一班", "二班"]),
    ("plan_qty", "计划产量", "decimal"), ("actual_qty", "实际产量", "decimal"),
    ("defect_qty", "不良品数", "decimal"), ("production_date", "生产日期", "date"),
]


# ---------- 断言 DSL ----------
def block(btype=None, **conds):
    """找一个满足全部条件的块。支持的键（与界面配置一一对应）：
    agg / field（统计字段）/ chart_type / group_kind / group_field / top_n / stack / compare /
    compare_type / quick_calc / group2_field / metrics_len / metrics（[{agg, field}] 全包含）/
    row_kind / row_field / col_kind / col_field / totals / on_click /
    columns（数组全包含）/ sort_by / sort_order / limit / has_rules（有筛选条件）/ target_mode /
    range_mode / range_start / range_end / date_field（块级时间口径与日期字段）/
    max（仪表盘满值）/ drill_field（层级钻取字段）/ row_top_n / col_top_n（透视表取前 N）/
    logic（筛选条件 AND/OR）/ content_contains（文本块内容包含）
    返回断言函数：result → [失败原因...]（空 = 通过）。"""

    def check(result):
        cands = [b for b in (result.get("blocks") or []) if not btype or b.get("type") == btype]
        if not cands:
            return [f"没有 {btype} 块"]
        for b in cands:
            bad = _match(b, conds)
            if not bad:
                return []
        return [f"{btype} 块不满足：{bad[0]}（{conds}）"]

    return check


def _match(b, conds):
    bad = []
    g = b.get("group") or {}
    metrics = b.get("metrics") or []
    row, col = b.get("row") or {}, b.get("col") or {}
    for k, want in conds.items():
        got = {
            "agg": b.get("agg") or "count",
            "field": b.get("field"),
            "chart_type": b.get("chart_type"),
            "group_kind": g.get("kind"), "group_field": g.get("field"),
            "top_n": b.get("top_n"), "stack": bool(b.get("stack")),
            "compare": b.get("compare"), "compare_type": b.get("compare_type") or "mom",
            "quick_calc": b.get("quick_calc"),
            "group2_field": (b.get("group2") or {}).get("field"),
            "metrics_len": len(metrics),
            "on_click": b.get("on_click"),
            "columns": b.get("columns") or [],
            "sort_by": b.get("sort_by"), "sort_order": b.get("sort_order"),
            "limit": b.get("limit"),
            "row_kind": row.get("kind"), "row_field": row.get("field"),
            "col_kind": col.get("kind"), "col_field": col.get("field"),
            "totals": b.get("totals") is not False,
            "has_rules": bool((b.get("filters") or {}).get("rules")),
            "target_mode": (b.get("target") or {}).get("mode") or "same_dataset",
            "range_mode": b.get("range_mode"),
            "range_start": b.get("range_start"), "range_end": b.get("range_end"),
            "date_field": b.get("date_field"),
            "max": b.get("max"),
            "drill_field": (b.get("drill_down") or {}).get("field"),
            "row_top_n": b.get("row_top_n"), "col_top_n": b.get("col_top_n"),
            "logic": (b.get("filters") or {}).get("logic") or "AND",
        }.get(k)
        if k == "metrics":
            ok = all(any(m.get("agg") == w["agg"] and m.get("field") == w["field"] for m in metrics) for w in want)
            if not ok:
                bad.append(f"metrics 应含 {want}，实际 {[(m.get('agg'), m.get('field')) for m in metrics]}")
        elif k == "columns":
            missing = [c for c in want if c not in got]
            if missing:
                bad.append(f"明细列缺 {missing}，实际 {got}")
        elif k == "content_contains":
            if want not in (b.get("content") or ""):
                bad.append(f"文本块内容应包含 {want}，实际 {(b.get('content') or '')[:60]}")
        elif got != want:
            bad.append(f"{k} 应为 {want}，实际 {got}")
    return bad


def range_eq(mode):
    def check(result):
        got = (result.get("range") or {}).get("mode")
        return [] if got == mode else [f"全局口径应为 {mode}，实际 {got}"]
    return check


def range_field(field):
    def check(result):
        got = (result.get("range") or {}).get("date_field")
        return [] if got == field else [f"口径日期字段应为 {field}，实际 {got}"]
    return check


def no_date_filters(result):
    """时间范围类需求必须走口径（range），不能在 filters 里堆日期条件。"""
    bad = []
    for b in result.get("blocks") or []:
        for r in ((b.get("filters") or {}).get("rules") or []):
            if r.get("field") in ("created_at", "updated_at", "production_date"):
                bad.append(f"「{b.get('title')}」用筛选条件凑时间范围（{r.get('field')} {r.get('op')}），应改用口径")
    return bad


def no_blocks(result):
    """纯口径调整不应生成新区块。"""
    n = len(result.get("blocks") or [])
    return [] if n == 0 else [f"纯口径调整不应生成区块，实际生成了 {n} 个"]


def settings_eq(path, want):
    """报表设置断言：path 支持点路径（schedule.type / push.guard.rules.0.op / enabled 等）。"""
    def check(result):
        cur = result
        for seg in path.split("."):
            if isinstance(cur, list):
                cur = cur[int(seg)] if seg.isdigit() and int(seg) < len(cur) else None
            else:
                cur = (cur or {}).get(seg) if isinstance(cur, dict) else None
        return [] if cur == want else [f"设置 {path} 应为 {want}，实际 {cur}"]
    return check


def no_push_settings(result):
    """用户没提推送/周期时，不应输出 schedule/push。"""
    return [f"用户没提推送，不应输出 {k}" for k in ("schedule", "push") if result.get(k)]


def guard_rule(block_types, op, value):
    """阈值告警条件断言：有规则、op/value 正确、引用的统计卡真实存在。"""
    def check(result):
        g = (result.get("push") or {}).get("guard") or {}
        rules = g.get("rules") or []
        if not rules:
            return ["没有阈值告警条件"]
        bad = []
        r = rules[0]
        if r.get("op") != op or r.get("value") != value:
            bad.append(f"告警条件应为 {op} {value}，实际 {r.get('op')} {r.get('value')}")
        stat_ids = {b.get("id") for b in (result.get("blocks") or []) if b.get("type") in block_types}
        if r.get("block_id") not in stat_ids:
            bad.append(f"告警引用的统计卡 {r.get('block_id')} 不存在（现有：{sorted(stat_ids)}）")
        return bad
    return check


# ---------- 用例（按界面选项分组） ----------
CASES = [
    # ---- 统计卡：聚合方式 / 占比 / 对比 ----
    {"group": "stat", "name": "stat·count 计数", "fields": PROD_FIELDS,
     "requirement": "这批生产记录一共多少条，给我个统计卡",
     "expect": [block("stat", agg="count")]},
    {"group": "stat", "name": "stat·count_distinct 去重计数", "fields": PROD_FIELDS,
     "requirement": "一共生产了多少种产品（按产品名称去重计数）",
     "expect": [block("stat", agg="count_distinct", field="product")]},
    {"group": "stat", "name": "stat·sum 求和", "fields": PROD_FIELDS,
     "requirement": "实际产量总共多少件",
     "expect": [block("stat", agg="sum", field="actual_qty")]},
    {"group": "stat", "name": "stat·avg 平均", "fields": PROD_FIELDS,
     "requirement": "平均每批的不良品数是多少",
     "expect": [block("stat", agg="avg", field="defect_qty")]},
    {"group": "stat", "name": "stat·ratio 占比", "fields": PROD_FIELDS,
     "requirement": "合格率：没有不良品的记录占总记录的百分比",
     "expect": [block("stat", agg="ratio")]},
    {"group": "stat", "name": "stat·compare 环比", "fields": PROD_FIELDS,
     "requirement": "本周实际产量，并和上周对比",
     "expect": [block("stat", agg="sum", field="actual_qty", compare=True)]},
    {"group": "stat", "name": "stat·compare_type 同比", "fields": PROD_FIELDS,
     "requirement": "本月实际产量，和去年同期对比",
     "expect": [block("stat", agg="sum", field="actual_qty", compare=True, compare_type="yoy")]},

    # ---- 图表：类型 ----
    {"group": "chart_type", "name": "chart·bar 柱状图", "fields": PROD_FIELDS,
     "requirement": "柱状图对比各生产线的实际产量",
     "expect": [block("chart", chart_type="bar", group_field="line")]},
    {"group": "chart_type", "name": "chart·line 折线趋势", "fields": PROD_FIELDS,
     "requirement": "折线图看实际产量按月的变化趋势",
     "expect": [block("chart", chart_type="line", group_kind="month", group_field="production_date")]},
    {"group": "chart_type", "name": "chart·pie 饼图占比", "fields": PROD_FIELDS,
     "requirement": "饼图看各产品的产量占比",
     "expect": [block("chart", chart_type="pie", group_field="product")]},
    {"group": "chart_type", "name": "chart·funnel 漏斗", "fields": PROD_FIELDS,
     "requirement": "漏斗图看各班次产量从大到小的分布",
     "expect": [block("chart", chart_type="funnel", group_field="shift")]},
    {"group": "chart_type", "name": "chart·area 面积图", "fields": PROD_FIELDS,
     "requirement": "面积图展示实际产量按月趋势",
     "expect": [block("chart", chart_type="area")]},
    {"group": "chart_type", "name": "chart·gauge 仪表盘+max", "fields": PROD_FIELDS,
     "requirement": "仪表盘显示实际产量总量，满值按 5000 件",
     "expect": [block("chart", chart_type="gauge", agg="sum", field="actual_qty", max=5000)]},

    # ---- 图表：多系列（多指标 / 二级分组 / 堆叠 / 组合图） ----
    {"group": "chart_series", "name": "chart·metrics 多指标", "fields": PROD_FIELDS,
     "requirement": "按月对比计划产量和实际产量两个指标",
     "expect": [block("chart", metrics_len=2, metrics=[{"agg": "sum", "field": "plan_qty"}, {"agg": "sum", "field": "actual_qty"}])]},
    {"group": "chart_series", "name": "chart·group2 二级分组", "fields": PROD_FIELDS,
     "requirement": "按月看产量，各班次的产量拆成不同系列",
     "expect": [block("chart", group2_field="shift")]},
    {"group": "chart_series", "name": "chart·stack 堆叠", "fields": PROD_FIELDS,
     "requirement": "各产品产量堆叠成一根柱子按月对比",
     "expect": [block("chart", stack=True, group2_field="product")]},
    {"group": "chart_series", "name": "chart·mixed 柱线组合", "fields": PROD_FIELDS,
     "requirement": "组合图：柱子看各月实际产量，折线看各月不良品数",
     "expect": [block("chart", chart_type="mixed", metrics_len=2)]},

    # ---- 图表：对比 / 占比 / 取前 N / 联动 ----
    {"group": "chart_extra", "name": "chart·compare 环比折线", "fields": PROD_FIELDS,
     "requirement": "按月产量趋势，并叠加环比上周期的对比线",
     "expect": [block("chart", group_kind="month", compare="mom")]},
    {"group": "chart_extra", "name": "chart·compare 同比折线", "fields": PROD_FIELDS,
     "requirement": "按月产量趋势，并叠加去年同期的对比线",
     "expect": [block("chart", group_kind="month", compare="yoy")]},
    {"group": "chart_extra", "name": "chart·drill_down 层级钻取", "fields": PROD_FIELDS,
     "requirement": "产量按生产线分组，点柱子后再按产品名称细分钻取",
     "expect": [block("chart", group_field="line", drill_field="product")]},
    {"group": "chart_extra", "name": "chart·quick_calc 占比显示", "fields": PROD_FIELDS,
     "requirement": "各产品产量，数值显示为占总量的百分比",
     "expect": [block("chart", quick_calc="pct", group_field="product")]},
    {"group": "chart_extra", "name": "chart·top_n 前 N 项", "fields": PROD_FIELDS,
     "requirement": "只看产量最高的前 5 个产品",
     "expect": [block("chart", top_n=5)]},
    {"group": "chart_extra", "name": "chart·on_click 联动过滤", "fields": PROD_FIELDS,
     "requirement": "产量对比图，点击某个生产线时联动过滤其他区块",
     "expect": [block("chart", on_click="link")]},

    # ---- 透视表：行列维度 / 合计开关 ----
    {"group": "pivot", "name": "pivot·字段×字段交叉", "fields": PROD_FIELDS,
     "requirement": "透视表：班次和产品名称交叉统计实际产量",
     "expect": [block("pivot", agg="sum", field="actual_qty")]},
    {"group": "pivot", "name": "pivot·字段×时间交叉", "fields": PROD_FIELDS,
     "requirement": "透视表：各生产线按月统计实际产量",
     "expect": [block("pivot", row_field="line", col_kind="month", col_field="production_date")]},
    {"group": "pivot", "name": "pivot·totals 关闭合计", "fields": PROD_FIELDS,
     "requirement": "班次×产品交叉统计产量，不要行列合计",
     "expect": [block("pivot", totals=False)]},
    {"group": "pivot", "name": "pivot·row_top_n 行前 N 项", "fields": PROD_FIELDS,
     "requirement": "透视表交叉统计产量，行维度的生产线只显示前 5 个",
     "expect": [block("pivot", row_top_n=5)]},

    # ---- 明细表：展示列 / 排序 / 条数 ----
    {"group": "table", "name": "table·columns 展示列", "fields": PROD_FIELDS,
     "requirement": "明细表只显示批次号、产品名称、实际产量三列",
     "expect": [block("table", columns=["batch_no", "product", "actual_qty"])]},
    {"group": "table", "name": "table·sort 排序", "fields": PROD_FIELDS,
     "requirement": "明细表按实际产量从高到低排",
     "expect": [block("table", sort_by="actual_qty", sort_order="desc")]},
    {"group": "table", "name": "table·limit 条数", "fields": PROD_FIELDS,
     "requirement": "明细表最多显示 20 条",
     "expect": [block("table", limit=20)]},

    # ---- 筛选条件 / 全局口径 / 日期字段 ----
    {"group": "filters_range", "name": "块级筛选 filters", "fields": PROD_FIELDS,
     "requirement": "统计卡只看一班的实际产量总和",
     "expect": [block("stat", agg="sum", field="actual_qty", has_rules=True)]},
    {"group": "filters_range", "name": "块级筛选·OR 任一条件", "fields": PROD_FIELDS,
     "requirement": "统计卡只看一班或者二班的记录（满足任一即可）",
     "expect": [block("stat", logic="OR", has_rules=True)]},
    {"group": "filters_range", "name": "range·近30天", "fields": PROD_FIELDS,
     "requirement": "给我近 30 天的生产情况概览",
     "expect": [range_eq("past_30d")]},
    {"group": "filters_range", "name": "range·今年（不设筛选条件）", "fields": PROD_FIELDS,
     "requirement": "时间范围设置为今年",
     "expect": [range_eq("this_year"), no_date_filters]},
    {"group": "filters_range", "name": "range·上月", "fields": PROD_FIELDS,
     "requirement": "把口径改成上月",
     "expect": [range_eq("last_month"), no_date_filters]},
    {"group": "filters_range", "name": "range·追加模式调口径为今年", "fields": PROD_FIELDS, "append": True,
     "requirement": "时间范围设置为今年",
     "expect": [range_eq("this_year"), no_blocks, no_date_filters]},
    {"group": "filters_range", "name": "range·追加模式调口径为上月", "fields": PROD_FIELDS, "append": True,
     "requirement": "把口径改成上月",
     "expect": [range_eq("last_month"), no_blocks, no_date_filters]},
    {"group": "filters_range", "name": "range·date_field 业务日期", "fields": PROD_FIELDS,
     "requirement": "按生产日期统计本周产量",
     "expect": [range_field("production_date")]},

    # ---- 块级时间范围（设计器里块的「时间范围/日期字段」覆盖） ----
    {"group": "block_range", "name": "块级口径·固定上周", "fields": PROD_FIELDS,
     "requirement": "报表主体看本周，但加一个统计卡固定统计上周的实际产量（不跟随全局口径）",
     "expect": [block("stat", agg="sum", field="actual_qty", range_mode="last_week")]},
    {"group": "block_range", "name": "块级口径·自定义区间", "fields": PROD_FIELDS,
     "requirement": "报表看整体产量概览，另外加一个图表只看 2026年9月1日到9月7日 的产量（其他块不受这个区间影响）",
     "expect": [block("chart", range_mode="custom", range_start="2026-09-01", range_end="2026-09-07")]},
    {"group": "block_range", "name": "块级日期字段·生产日期", "fields": PROD_FIELDS,
     "requirement": "加一个统计卡按生产日期统计产量（不要按创建时间）",
     "expect": [block("stat", date_field="production_date")]},

    # ---- 文本小结 / 筛选块 ----
    {"group": "misc", "name": "text 文本小结", "fields": PROD_FIELDS,
     "requirement": "一个产量统计卡，再加一段文字小结引用这个统计值",
     "expect": [block("stat"), block("text", content_contains="{b1}")]},
    {"group": "misc", "name": "filter 筛选块", "fields": PROD_FIELDS,
     "requirement": "报表顶部加一个班次筛选器，让看报表的人可以自己选班次",
     "expect": [block("filter", field="shift")]},

    # ---- 报表设置：执行周期 / 推送渠道 / 阈值告警（仅用户明确要求才输出，enabled 恒 false） ----
    {"group": "settings", "name": "设置·interval 每小时推送", "fields": PROD_FIELDS,
     "requirement": "给我一份产量概览报表，每小时推送一次",
     "expect": [settings_eq("schedule.type", "interval"), settings_eq("schedule.minutes", 60),
                settings_eq("enabled", False)]},
    {"group": "settings", "name": "设置·cron 每周一9点", "fields": PROD_FIELDS,
     "requirement": "每周一早上 9 点生成上周的产量报表推送给我",
     "expect": [settings_eq("schedule.type", "cron"), settings_eq("schedule.expr", "0 9 * * 1"),
                settings_eq("enabled", False)]},
    {"group": "settings", "name": "设置·guard 阈值告警", "fields": PROD_FIELDS,
     "requirement": "产量概览，实际产量总量低于 100 件的时候才推送提醒我",
     "expect": [guard_rule({"stat"}, "lt", 100.0)]},
    {"group": "settings", "name": "设置·push 收件邮箱", "fields": PROD_FIELDS,
     "requirement": "每天早上 9 点把产量报表发到 ops@example.com",
     "expect": [settings_eq("schedule.type", "cron"), settings_eq("push.recipients", "ops@example.com"),
                settings_eq("enabled", False)]},
    {"group": "settings", "name": "设置·不提推送则不输出", "fields": PROD_FIELDS,
     "requirement": "各生产线产量对比图",
     "expect": [no_push_settings]},
]


def run_case(client, db, idx, case):
    """单用例：AI 生成 → 结构断言 → 落临时表试运行。返回 (失败列表, 生成结果)。"""
    fields = [SimpleNamespace(field_name=f[0], label=f[1], data_type=f[2],
                              options={"options": f[3]} if len(f) > 3 else {})
              for f in case["fields"]]
    try:
        result = assist_report(db, fields, case["requirement"], append=bool(case.get("append")))
    except Exception as e:  # noqa: BLE001
        return [f"生成失败：{e}"], None
    fails = []
    for fn in case["expect"]:
        fails += fn(result)
    if case.get("append"):
        return fails, result   # 追加模式不验落库/试运行（blocks 可能为空）

    tid = None
    try:
        r = client.post("/api/tables", json={
            "label": f"eval_{idx}",
            "fields": [{"field_name": f[0], "label": f[1], "data_type": f[2], "nullable": True,
                        **({"widget": "select", "options": {"options": f[3]}} if len(f) > 3 else {})}
                       for f in case["fields"]],
        })
        tid = r.json()["table"]["id"]
        for i in (1, 2):
            rec = {}
            for f in case["fields"]:
                if f[2] in ("int", "decimal"):
                    rec[f[0]] = i * 100
                elif f[2] == "date":
                    rec[f[0]] = "2026-09-29"
                else:
                    rec[f[0]] = (f[3] if len(f) > 3 else ["样例1", "样例2"])[i - 1]
            client.post(f"/api/dyn/{tid}/records", json=rec)
        r = client.post("/api/reports", json={
            "name": f"eval_{idx}", "table_id": tid,
            "range": result.get("range") or {"mode": "this_week"},
            "datasets": [{"id": "d1", "name": "eval", "base_table_id": tid, "joins": [], "computed_fields": []}],
            "blocks": [{**b, "dataset_id": "d1",
                        "date_field": b.get("date_field") or "production_date"} for b in result.get("blocks") or []],
            "layout": None,
        })
        if r.status_code != 200:
            fails.append(f"报表保存被拒：{r.text[:150]}")
        else:
            rep = r.json()["id"]
            r = client.post(f"/api/reports/{rep}/run", json={})
            if r.status_code != 200:
                fails.append(f"试运行失败：{r.text[:150]}")
            client.delete(f"/api/reports/{rep}")
    finally:
        if tid:
            client.delete(f"/api/tables/{tid}")
    return fails, result


def main():
    args = [a for a in sys.argv[1:]]
    only = [int(a) for a in args if a.isdigit()]
    group = None
    if "--group" in args:
        group = args[args.index("--group") + 1]

def main():
    args = [a for a in sys.argv[1:]]
    only = [int(a) for a in args if a.isdigit()]
    group = None
    if "--group" in args:
        group = args[args.index("--group") + 1]

    client = TestClient(app)
    client.__enter__()   # 触发 lifespan 建表（评测库是独立新库）

    # 供应商配置存在主库（backend/grt.db），评测库是空库——把模型供应商行复制过去
    import sqlite3
    main_db = BACKEND_DIR / "grt.db"
    if main_db.exists():
        src = sqlite3.connect(main_db)
        rows = src.execute("SELECT name, type, base_url, api_key_enc, model, vision_model, is_default, enabled FROM llm_providers").fetchall()
        src.close()
        dst = sqlite3.connect(Path(__file__).parent / "eval_ai_report.db")
        dst.executemany(
            "INSERT INTO llm_providers (name, type, base_url, api_key_enc, model, vision_model, is_default, enabled) VALUES (?,?,?,?,?,?,?,?)",
            rows)
        dst.commit()
        dst.close()

    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    client.headers["Authorization"] = "Bearer " + r.json()["token"]

    passed = failed = 0
    fail_groups = {}
    for i, case in enumerate(CASES, 1):
        if only and i not in only:
            continue
        if group and case["group"] != group:
            continue
        db = SessionLocal()
        try:
            fails, result = run_case(client, db, i, case)
        finally:
            db.close()
        if fails:
            failed += 1
            fail_groups.setdefault(case["group"], []).append(i)
            print(f"[{i}] ({case['group']}) {case['name']}: FAIL")
            for f in fails:
                print(f"    - {f}")
            if result:
                print(f"    生成结果：{json.dumps(result.get('blocks'), ensure_ascii=False)[:400]}")
        else:
            passed += 1
            print(f"[{i}] ({case['group']}) {case['name']}: PASS")
    print(f"\n通过 {passed}/{passed + failed}")
    if fail_groups:
        print("FAIL 集中在选项组：" + "、".join(f"{g}（{len(v)} 个）" for g, v in fail_groups.items()))
        print("提示：对应选项多半没写进生成提示词（prompts.py 的 build_report_prompt），对照补上再复跑。")


if __name__ == "__main__":
    main()
