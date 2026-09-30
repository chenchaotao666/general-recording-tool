# -*- coding: utf-8 -*-
"""AI 单区块配置（「AI 帮我设置」）的准确性评测：覆盖每种区块类型的所有设置项。

与 eval_ai_report.py（整表生成）对应——这条链路是设计器里选中区块后的一句话改配置，
提示词是独立的（prompts.py 的 _BLOCK_SPEC_DOCS），两边漂移过不止一次，必须单独评测。

用法（在 backend 目录，用项目 venv）：
    ./.venv/Scripts/python test/llm/eval_ai_block.py             # 全部用例
    ./.venv/Scripts/python test/llm/eval_ai_block.py 3 7         # 只跑指定编号
    ./.venv/Scripts/python test/llm/eval_ai_block.py --type chart  # 只跑某类区块

每个用例：assist_block_config(当前配置 + 一句话需求) → 断言返回的 patch 里对应键被正确设置。
评测库 test/llm/eval_ai_block.db 由 grt.db 克隆 schema + 供应商配置（业务数据清空）。
"""
import json
import os
import shutil
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))
EVAL_DB = Path(__file__).parent / "eval_ai_block.db"
os.environ.setdefault("GRT_DATABASE_URL", f"sqlite:///{EVAL_DB.as_posix()}")
os.environ.setdefault("GRT_SECRET_KEY", "eval")


def prepare_db():
    """克隆主库 schema + 供应商配置（业务数据清空），幂等。"""
    if EVAL_DB.exists():
        return
    import sqlite3
    shutil.copy(BACKEND_DIR / "grt.db", EVAL_DB)
    conn = sqlite3.connect(EVAL_DB)
    for t in ("meta_tables", "meta_fields", "records", "report_templates", "workflows"):
        try:
            conn.execute(f"DELETE FROM {t}")
        except sqlite3.Error:
            pass
    conn.commit()
    conn.close()


from types import SimpleNamespace  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.services.llm.gateway import assist_block_config  # noqa: E402

# ---------- 测试表结构 ----------
PROD_FIELDS = [
    ("batch_no", "批次号", "varchar"), ("line", "生产线", "varchar"),
    ("product", "产品名称", "varchar"), ("shift", "班次", "varchar"),
    ("plan_qty", "计划产量", "decimal"), ("actual_qty", "实际产量", "decimal"),
    ("defect_qty", "不良品数", "decimal"), ("production_date", "生产日期", "date"),
]

# 各块类型的「当前配置」基线（模拟界面上已配好一块，AI 在其上按需求修改）
BASE = {
    "stat": {"title": "实际产量", "agg": "sum", "field": "actual_qty", "filters": {"logic": "AND", "rules": []}},
    "chart": {"title": "产量统计", "chart_type": "bar", "group": {"kind": "field", "field": "line"},
              "agg": "sum", "field": "actual_qty", "filters": {"logic": "AND", "rules": []}},
    "pivot": {"title": "产量透视", "row": {"kind": "field", "field": "line"},
              "col": {"kind": "month", "field": "production_date"}, "agg": "sum", "field": "actual_qty",
              "totals": True, "filters": {"logic": "AND", "rules": []}},
    "table": {"title": "明细", "columns": ["batch_no", "actual_qty"],
              "sort_by": "created_at", "sort_order": "desc", "filters": {"logic": "AND", "rules": []}},
    "filter": {"title": "筛选", "field": "shift"},
    "text": {"title": "小结", "content": "本周产量平稳。"},
}


def expect_cfg(**conds):
    """断言 patch 配置：键支持嵌套点路径（如 group.field / drill_down.field）。
    特殊键：metrics_len（多指标个数）、columns_contains / columns_no（明细列包含/不含）。"""

    def check(cfg, notes):
        bad = []
        for k, want in conds.items():
            if k == "metrics_len":
                got = len(cfg.get("metrics") or [])
                if got != want:
                    bad.append(f"metrics 个数应为 {want}，实际 {got}")
                continue
            if k in ("columns_contains", "columns_no"):
                cols = cfg.get("columns") or []
                if k == "columns_contains":
                    missing = [c for c in want if c not in cols]
                    if missing:
                        bad.append(f"明细列应含 {missing}，实际 {cols}")
                else:
                    extra = [c for c in want if c in cols]
                    if extra:
                        bad.append(f"明细列不应含 {extra}，实际 {cols}")
                continue
            cur = cfg
            for seg in k.split("."):
                cur = (cur or {}).get(seg) if isinstance(cur, dict) else None
            if cur != want:
                bad.append(f"{k} 应为 {want}，实际 {cur}")
        return bad

    return check


CASES = [
    # ---- 统计卡：聚合方式全部 7 种 ----
    {"type": "stat", "name": "stat·count", "requirement": "改成统计记录总条数",
     "expect": expect_cfg(agg="count", field=None)},
    {"type": "stat", "name": "stat·count_distinct", "requirement": "改成统计产品种类数（去重）",
     "expect": expect_cfg(agg="count_distinct", field="product")},
    {"type": "stat", "name": "stat·sum", "requirement": "改成实际产量求和",
     "expect": expect_cfg(agg="sum", field="actual_qty")},
    {"type": "stat", "name": "stat·avg", "requirement": "改成平均每批不良品数",
     "expect": expect_cfg(agg="avg", field="defect_qty")},
    {"type": "stat", "name": "stat·max", "requirement": "改成最高单批产量",
     "expect": expect_cfg(agg="max", field="actual_qty")},
    {"type": "stat", "name": "stat·min", "requirement": "改成最低单批产量",
     "expect": expect_cfg(agg="min", field="actual_qty")},
    {"type": "stat", "name": "stat·ratio 占比", "requirement": "改成合格率（没有不良品的记录占比）",
     "expect": expect_cfg(agg="ratio")},
    {"type": "stat", "name": "stat·compare 环比", "requirement": "加上环比上周的对比",
     "expect": expect_cfg(compare=True, compare_type="mom")},
    {"type": "stat", "name": "stat·compare 同比", "requirement": "改成和去年同期对比",
     "expect": expect_cfg(compare=True, compare_type="yoy")},
    {"type": "stat", "name": "stat·filters 筛选", "requirement": "只看一班的数据",
     "expect": expect_cfg(**{"filters.logic": "AND"})},
    {"type": "stat", "name": "stat·range_mode 口径", "requirement": "时间范围设置为今年",
     "expect": expect_cfg(range_mode="this_year")},
    {"type": "stat", "name": "stat·date_field 日期字段", "requirement": "按生产日期统计，不要按创建时间",
     "expect": expect_cfg(date_field="production_date")},
    {"type": "stat", "name": "stat·title 改名", "requirement": "显示名改成「总产量」",
     "expect": expect_cfg(title="总产量")},

    # ---- 图表：类型 × 7 ----
    {"type": "chart", "name": "chart·bar", "requirement": "改成柱状图", "expect": expect_cfg(chart_type="bar")},
    {"type": "chart", "name": "chart·line", "requirement": "改成折线图", "expect": expect_cfg(chart_type="line")},
    {"type": "chart", "name": "chart·area", "requirement": "改成面积图", "expect": expect_cfg(chart_type="area")},
    {"type": "chart", "name": "chart·pie", "requirement": "改成饼图看占比", "expect": expect_cfg(chart_type="pie")},
    {"type": "chart", "name": "chart·funnel", "requirement": "改成漏斗图", "expect": expect_cfg(chart_type="funnel")},
    {"type": "chart", "name": "chart·gauge+max", "requirement": "改成仪表盘，满值 5000",
     "expect": expect_cfg(chart_type="gauge", max=5000)},
    {"type": "chart", "name": "chart·mixed", "requirement": "改成组合图：柱子看产量、折线看不良数",
     "expect": expect_cfg(chart_type="mixed")},
    # ---- 图表：分组 / 多系列 / 其它 ----
    {"type": "chart", "name": "chart·group 按月", "requirement": "改成按月看趋势",
     "expect": expect_cfg(**{"group.kind": "month", "group.field": "production_date"})},
    {"type": "chart", "name": "chart·metrics 多指标", "requirement": "加上计划产量一起对比（两个指标）",
     "expect": expect_cfg(metrics_len=2)},
    {"type": "chart", "name": "chart·group2 二级分组", "requirement": "再按班次拆成不同系列",
     "expect": expect_cfg(**{"group2.field": "shift"})},
    {"type": "chart", "name": "chart·stack 堆叠", "requirement": "系列堆叠起来",
     "base": {"title": "产量统计", "chart_type": "bar", "group": {"kind": "field", "field": "line"},
              "group2": {"field": "shift"}, "filters": {"logic": "AND", "rules": []}},   # 堆叠需要多系列基线
     "expect": expect_cfg(stack=True)},
    {"type": "chart", "name": "chart·top_n", "requirement": "只显示前 5 个分组", "expect": expect_cfg(top_n=5)},
    {"type": "chart", "name": "chart·compare 环比", "requirement": "按月分组并叠加环比折线",
     "expect": expect_cfg(**{"group.kind": "month"}, compare="mom")},
    {"type": "chart", "name": "chart·quick_calc 占比", "requirement": "数值改成显示占总计百分比",
     "expect": expect_cfg(quick_calc="pct")},
    {"type": "chart", "name": "chart·drill_down 层级钻取", "requirement": "点柱子后按产品名称细分钻取",
     "expect": expect_cfg(**{"drill_down.field": "product"})},
    {"type": "chart", "name": "chart·on_click 联动", "requirement": "点击图表帮我联动其它区块",
     "expect": expect_cfg(on_click="link")},
    {"type": "chart", "name": "chart·range_mode 口径", "requirement": "这个图固定看今年的",
     "expect": expect_cfg(range_mode="this_year")},
    {"type": "chart", "name": "chart·range custom 区间", "requirement": "只看 2026-09-01 到 2026-09-07",
     "expect": expect_cfg(range_mode="custom", range_start="2026-09-01", range_end="2026-09-07")},
    {"type": "chart", "name": "chart·date_field", "requirement": "口径的日期字段改成生产日期（分组保持不变）",
     "expect": expect_cfg(date_field="production_date")},
    {"type": "chart", "name": "chart·口径追问", "requirement": "覆盖全局时间",
     "expect_fn": lambda cfg, notes: (
         [] if (cfg.get("range_mode") or cfg.get("date_field") or notes)
         else ["既没设置口径/日期字段，也没在 notes 里追问"]),   # 没给口径值：设置一个或追问都算对
     },

    # ---- 透视表 ----
    {"type": "pivot", "name": "pivot·row 行维度", "requirement": "行改成按班次",
     "expect": expect_cfg(**{"row.field": "shift"})},
    {"type": "pivot", "name": "pivot·col 列维度", "requirement": "列改成按产品名称",
     "expect": expect_cfg(**{"col.field": "product", "col.kind": "field"})},
    {"type": "pivot", "name": "pivot·agg 平均", "requirement": "改成平均产量",
     "expect": expect_cfg(agg="avg")},
    {"type": "pivot", "name": "pivot·totals 关合计", "requirement": "不要行列合计",
     "expect": expect_cfg(totals=False)},
    {"type": "pivot", "name": "pivot·row_top_n", "requirement": "行只显示前 5 个",
     "expect": expect_cfg(row_top_n=5)},
    {"type": "pivot", "name": "pivot·range_mode", "requirement": "这个透视表固定看上月",
     "expect": expect_cfg(range_mode="last_month")},

    # ---- 明细表 ----
    {"type": "table", "name": "table·columns", "requirement": "只显示批次号和实际产量两列",
     "expect": expect_cfg(columns_contains=["batch_no", "actual_qty"], columns_no=["product"])},
    {"type": "table", "name": "table·sort", "requirement": "按实际产量从低到高排",
     "expect": expect_cfg(sort_by="actual_qty", sort_order="asc")},
    {"type": "table", "name": "table·range_mode", "requirement": "明细固定看近 30 天",
     "expect": expect_cfg(range_mode="past_30d")},

    # ---- 筛选组件 / 文本 ----
    {"type": "filter", "name": "filter·field", "requirement": "改成按产品名称筛选",
     "expect": expect_cfg(field="product")},
    {"type": "text", "name": "text·content 改写", "requirement": "改成一句乐观的总结",
     "expect": None, "expect_fn": lambda cfg, notes: [] if cfg.get("content") and cfg["content"] != BASE["text"]["content"] else ["文本内容没有变化"]},
]


def run_case(db, idx, case):
    fields = [SimpleNamespace(field_name=f[0], label=f[1], data_type=f[2], options={}) for f in PROD_FIELDS]
    current = dict(case.get("base") or BASE[case["type"]])
    try:
        r = assist_block_config(db, fields, case["type"], case["requirement"], current=current)
    except Exception as e:  # noqa: BLE001
        return [f"调用失败：{e}"], None
    cfg, notes = r.get("config") or {}, r.get("notes") or ""

    if case.get("expect"):
        return case["expect"](cfg, notes), cfg
    if case.get("expect_fn"):
        return case["expect_fn"](cfg, notes), cfg
    return [], cfg


def main():
    args = sys.argv[1:]
    only = [int(a) for a in args if a.isdigit()]
    only_type = None
    if "--type" in args:
        only_type = args[args.index("--type") + 1]

    prepare_db()
    passed = failed = 0
    fail_types = {}
    for i, case in enumerate(CASES, 1):
        if only and i not in only:
            continue
        if only_type and case["type"] != only_type:
            continue
        db = SessionLocal()
        try:
            fails, cfg = run_case(db, i, case)
        finally:
            db.close()
        if fails:
            failed += 1
            fail_types.setdefault(case["type"], []).append(i)
            print(f"[{i}] ({case['type']}) {case['name']}: FAIL")
            for f in fails:
                print(f"    - {f}")
            if cfg:
                print(f"    patch：{json.dumps(cfg, ensure_ascii=False)[:300]}")
        else:
            passed += 1
            print(f"[{i}] ({case['type']}) {case['name']}: PASS")
    print(f"\n通过 {passed}/{passed + failed}")
    if fail_types:
        print("FAIL 集中在类型：" + "、".join(f"{t}（{len(v)}）" for t, v in fail_types.items()))
        print("提示：先查 prompts.py 的 _BLOCK_SPEC_DOCS 是否包含该设置项，再查 align 透传。")


if __name__ == "__main__":
    main()
