"""内置报表模板市场：场景报表一键安装。

与工作流模板市场（workflow/templates.py）同一模式：
模板 = 所需表结构 + 报表定义（数据集/区块，table 引用用 "$表key" 占位）。
安装：按 label 复用已有表或自动建表 → 占位符重映射 → validate_template 校验 →
落库（默认停用推送）。可选：为新建的表生成示例数据，装完即可看到真实图表。
布局不落库：设计器打开时 autoLayout 自动生成，用户再按需调整。
"""
from sqlalchemy.orm import Session

from ..models import MetaTable, ReportTemplate, User
from ..schemas import FieldIn, ReportTemplateIn, TableCreate
from . import meta_service
from .report_engine import validate_template
from .workflow.templates import _remap, _seed_demo_data

# 区块公共字段的简写：filters 恒 AND 空条件组
_F = {"logic": "AND", "rules": []}

TEMPLATES: list[dict] = [
    {
        "key": "sales_weekly",
        "category": "销售",
        "name": "销售业绩周报",
        "description": "上周成交概况：单数/总额/客单价环比、销售员排行、每日趋势、产品占比与明细",
        "scenario": "统计卡环比 + 柱状排行 + 折线趋势 + 饼图占比 + 明细表",
        "tables": [{
            "key": "sales", "label": "销售业绩表",
            "fields": [
                {"field_name": "salesperson", "label": "销售员", "data_type": "varchar"},
                {"field_name": "product", "label": "产品", "data_type": "varchar"},
                {"field_name": "amount", "label": "成交金额", "data_type": "decimal", "widget": "number"},
                {"field_name": "deal_date", "label": "成交日期", "data_type": "date", "widget": "date-picker"},
            ],
        }],
        "report": {
            "name": "销售业绩周报",
            "description": "模板安装：上周成交概况（口径可在顶栏切换）",
            "range": {"mode": "last_week"},
            "datasets": [{"id": "d1", "name": "销售业绩表", "base_table_id": "$sales", "joins": [], "computed_fields": []}],
            "blocks": [
                {"id": "b1", "type": "stat", "title": "成交单数", "dataset_id": "d1", "date_field": "deal_date",
                 "agg": "count", "field": None, "compare": True, "filters": dict(_F)},
                {"id": "b2", "type": "stat", "title": "成交总额", "dataset_id": "d1", "date_field": "deal_date",
                 "agg": "sum", "field": "amount", "compare": True, "filters": dict(_F)},
                {"id": "b3", "type": "stat", "title": "平均客单价", "dataset_id": "d1", "date_field": "deal_date",
                 "agg": "avg", "field": "amount", "filters": dict(_F)},
                {"id": "b4", "type": "chart", "title": "销售员成交排行", "dataset_id": "d1", "date_field": "deal_date",
                 "chart_type": "bar", "group": {"kind": "field", "field": "salesperson"}, "agg": "sum", "field": "amount",
                 "top_n": 12, "metrics": [], "group2": {"field": None}, "stack": False, "on_click": "drill", "filters": dict(_F)},
                {"id": "b5", "type": "chart", "title": "每日成交趋势", "dataset_id": "d1", "date_field": "deal_date",
                 "chart_type": "line", "group": {"kind": "day", "field": "deal_date"}, "agg": "sum", "field": "amount",
                 "top_n": 30, "metrics": [], "group2": {"field": None}, "stack": False, "on_click": "drill", "filters": dict(_F)},
                {"id": "b6", "type": "chart", "title": "产品成交占比", "dataset_id": "d1", "date_field": "deal_date",
                 "chart_type": "pie", "group": {"kind": "field", "field": "product"}, "agg": "sum", "field": "amount",
                 "top_n": 8, "metrics": [], "group2": {"field": None}, "stack": False, "on_click": "drill", "filters": dict(_F)},
                {"id": "b7", "type": "table", "title": "成交明细", "dataset_id": "d1", "date_field": "deal_date",
                 "columns": ["salesperson", "product", "amount", "deal_date"],
                 "sort_by": "deal_date", "sort_order": "desc", "filters": dict(_F)},
                {"id": "b8", "type": "text", "title": "使用说明",
                 "content": "统计卡的↑↓是与上一周对比；点柱子/扇区可下钻看该分组明细；顶栏可切换时间口径。"},
            ],
        },
        "notes": "示例数据的成交日期在近 60 天内随机，默认口径「上周」可能数据较少，可在顶栏切成「近30天」看完整图表",
    },
    {
        "key": "stock_board",
        "category": "库存",
        "name": "库存监控看板",
        "description": "库存快照：品种数、总库存、低库存清单（数量 < 10），不随时间筛选",
        "scenario": "统计卡 + 柱状分布 + 低库存明细（块级设为不随时间筛选）",
        "tables": [{
            "key": "stock", "label": "库存表",
            "fields": [
                {"field_name": "item", "label": "品名", "data_type": "varchar"},
                {"field_name": "qty", "label": "数量", "data_type": "int", "widget": "number"},
                {"field_name": "safety", "label": "安全库存", "data_type": "int", "widget": "number"},
            ],
        }],
        "report": {
            "name": "库存监控看板",
            "description": "模板安装：库存快照（区块已设为不随时间筛选）",
            "range": {"mode": "this_month"},
            "datasets": [{"id": "d1", "name": "库存表", "base_table_id": "$stock", "joins": [], "computed_fields": []}],
            "blocks": [
                {"id": "b1", "type": "stat", "title": "品种数", "dataset_id": "d1", "date_field": None,
                 "agg": "count_distinct", "field": "item", "filters": dict(_F)},
                {"id": "b2", "type": "stat", "title": "总库存量", "dataset_id": "d1", "date_field": None,
                 "agg": "sum", "field": "qty", "filters": dict(_F)},
                {"id": "b3", "type": "stat", "title": "低库存品名数（<10）", "dataset_id": "d1", "date_field": None,
                 "agg": "count", "field": None,
                 "filters": {"logic": "AND", "rules": [{"field": "qty", "op": "lt", "value": 10}]}},
                {"id": "b4", "type": "chart", "title": "各品名库存量", "dataset_id": "d1", "date_field": None,
                 "chart_type": "bar", "group": {"kind": "field", "field": "item"}, "agg": "sum", "field": "qty",
                 "top_n": 30, "metrics": [], "group2": {"field": None}, "stack": False, "on_click": "drill", "filters": dict(_F)},
                {"id": "b5", "type": "table", "title": "低库存明细", "dataset_id": "d1", "date_field": None,
                 "columns": ["item", "qty", "safety"], "sort_by": "qty", "sort_order": "asc",
                 "filters": {"logic": "AND", "rules": [{"field": "qty", "op": "lt", "value": 10}]}},
                {"id": "b6", "type": "text", "title": "使用说明",
                 "content": "本看板是库存快照：所有区块的「日期字段」设为不随时间筛选。低库存阈值写死为 10，选中区块可在右侧改成与你业务一致的值。"},
            ],
        },
        "notes": "库存是快照数据，模板把所有区块的日期字段设为「不随时间筛选」；低库存阈值（数量<10）可在区块筛选里调整",
    },
    {
        "key": "follow_weekly",
        "category": "客户",
        "name": "客户跟进周报",
        "description": "本周跟进概况：跟进次数/客户数环比、跟进人排名、每日趋势，可按跟进人筛选",
        "scenario": "统计卡环比 + 筛选组件 + 柱状排名 + 折线趋势 + 明细表",
        "tables": [{
            "key": "follow", "label": "客户跟进表",
            "fields": [
                {"field_name": "customer", "label": "客户", "data_type": "varchar"},
                {"field_name": "owner", "label": "跟进人", "data_type": "varchar",
                 "widget": "select", "options": {"options": ["张伟", "王芳", "李娜", "刘洋", "陈杰"]}},
                {"field_name": "content", "label": "跟进内容", "data_type": "text", "widget": "textarea"},
                {"field_name": "follow_date", "label": "跟进日期", "data_type": "date", "widget": "date-picker"},
            ],
        }],
        "report": {
            "name": "客户跟进周报",
            "description": "模板安装：本周跟进概况（顶栏可切换口径）",
            "range": {"mode": "this_week"},
            "datasets": [{"id": "d1", "name": "客户跟进表", "base_table_id": "$follow", "joins": [], "computed_fields": []}],
            "blocks": [
                {"id": "b1", "type": "stat", "title": "跟进次数", "dataset_id": "d1", "date_field": "follow_date",
                 "agg": "count", "field": None, "compare": True, "filters": dict(_F)},
                {"id": "b2", "type": "stat", "title": "跟进客户数", "dataset_id": "d1", "date_field": "follow_date",
                 "agg": "count_distinct", "field": "customer", "compare": True, "filters": dict(_F)},
                {"id": "b3", "type": "filter", "title": "跟进人", "dataset_id": "d1",
                 "field": "owner", "target": {"mode": "same_dataset"}, "filters": dict(_F)},
                {"id": "b4", "type": "chart", "title": "跟进次数排名", "dataset_id": "d1", "date_field": "follow_date",
                 "chart_type": "bar", "group": {"kind": "field", "field": "owner"}, "agg": "count", "field": None,
                 "top_n": 12, "metrics": [], "group2": {"field": None}, "stack": False, "on_click": "drill", "filters": dict(_F)},
                {"id": "b5", "type": "chart", "title": "每日跟进趋势", "dataset_id": "d1", "date_field": "follow_date",
                 "chart_type": "line", "group": {"kind": "day", "field": "follow_date"}, "agg": "count", "field": None,
                 "top_n": 30, "metrics": [], "group2": {"field": None}, "stack": False, "on_click": "drill", "filters": dict(_F)},
                {"id": "b6", "type": "table", "title": "跟进明细", "dataset_id": "d1", "date_field": "follow_date",
                 "columns": ["customer", "owner", "content", "follow_date"],
                 "sort_by": "follow_date", "sort_order": "desc", "filters": dict(_F)},
            ],
        },
        "notes": "「跟进人」是筛选组件：查看页里选一个人，同数据源的所有区块都会过滤；示例数据的跟进日期在近 60 天内随机",
    },
    {
        "key": "ledger_monthly",
        "category": "财务",
        "name": "收支月报",
        "description": "本月收支概况：收入/支出/净额环比、收支构成占比、每日净额趋势（含计算字段示例）",
        "scenario": "计算字段（净额）+ 统计卡环比 + 饼图构成 + 面积趋势 + 明细表",
        "tables": [{
            "key": "ledger", "label": "收支记录表",
            "fields": [
                {"field_name": "item", "label": "事项", "data_type": "varchar"},
                {"field_name": "type", "label": "类型", "data_type": "varchar",
                 "widget": "select", "options": {"options": ["收入", "支出"]}},
                {"field_name": "amount", "label": "金额", "data_type": "decimal", "widget": "number"},
                {"field_name": "date", "label": "日期", "data_type": "date", "widget": "date-picker"},
            ],
        }],
        "report": {
            "name": "收支月报",
            "description": "模板安装：本月收支概况（含计算字段「净额」示例）",
            "range": {"mode": "this_month"},
            "datasets": [{
                "id": "d1", "name": "收支记录表", "base_table_id": "$ledger", "joins": [],
                "computed_fields": [{"name": "净额", "expr": "iff(type == '收入', amount, -amount)", "type": "decimal"}],
            }],
            "blocks": [
                {"id": "b1", "type": "stat", "title": "总收入", "dataset_id": "d1", "date_field": "date",
                 "agg": "sum", "field": "amount", "compare": True,
                 "filters": {"logic": "AND", "rules": [{"field": "type", "op": "eq", "value": "收入"}]}},
                {"id": "b2", "type": "stat", "title": "总支出", "dataset_id": "d1", "date_field": "date",
                 "agg": "sum", "field": "amount", "compare": True,
                 "filters": {"logic": "AND", "rules": [{"field": "type", "op": "eq", "value": "支出"}]}},
                {"id": "b3", "type": "stat", "title": "净额", "dataset_id": "d1", "date_field": "date",
                 "agg": "sum", "field": "净额", "compare": True, "filters": dict(_F)},
                {"id": "b4", "type": "chart", "title": "收支构成", "dataset_id": "d1", "date_field": "date",
                 "chart_type": "pie", "group": {"kind": "field", "field": "type"}, "agg": "sum", "field": "amount",
                 "top_n": 8, "metrics": [], "group2": {"field": None}, "stack": False, "on_click": "drill", "filters": dict(_F)},
                {"id": "b5", "type": "chart", "title": "每日净额趋势", "dataset_id": "d1", "date_field": "date",
                 "chart_type": "area", "group": {"kind": "day", "field": "date"}, "agg": "sum", "field": "净额",
                 "top_n": 30, "metrics": [], "group2": {"field": None}, "stack": False, "on_click": "drill", "filters": dict(_F)},
                {"id": "b6", "type": "table", "title": "收支明细", "dataset_id": "d1", "date_field": "date",
                 "columns": ["item", "type", "amount", "date"], "sort_by": "date", "sort_order": "desc",
                 "filters": dict(_F)},
            ],
        },
        "notes": "「净额」是数据集的计算字段（收入为正、支出为负），左侧数据源 → 数据集设置里可以看到它的表达式，可仿照添加自己的计算字段",
    },
    {
        "key": "production_daily",
        "category": "生产",
        "name": "生产质量日报",
        "description": "本周生产概况：产量/不良数、不良率仪表盘、操作员产量对比与明细（含计算字段示例）",
        "scenario": "计算字段（不良率）+ 统计卡 + 仪表盘 + 柱状对比 + 明细表",
        "tables": [{
            "key": "production", "label": "生产记录表",
            "fields": [
                {"field_name": "product", "label": "产品", "data_type": "varchar"},
                {"field_name": "qty", "label": "产量", "data_type": "int", "widget": "number"},
                {"field_name": "bad", "label": "不良数", "data_type": "int", "widget": "number"},
                {"field_name": "operator", "label": "操作员", "data_type": "varchar"},
                {"field_name": "produce_date", "label": "生产日期", "data_type": "date", "widget": "date-picker"},
            ],
        }],
        "report": {
            "name": "生产质量日报",
            "description": "模板安装：本周生产概况（含计算字段「不良率」示例）",
            "range": {"mode": "this_week"},
            "datasets": [{
                "id": "d1", "name": "生产记录表", "base_table_id": "$production", "joins": [],
                "computed_fields": [{"name": "不良率", "expr": "bad / qty * 100", "type": "decimal"}],
            }],
            "blocks": [
                {"id": "b1", "type": "stat", "title": "总产量", "dataset_id": "d1", "date_field": "produce_date",
                 "agg": "sum", "field": "qty", "compare": True, "filters": dict(_F)},
                {"id": "b2", "type": "stat", "title": "不良数", "dataset_id": "d1", "date_field": "produce_date",
                 "agg": "sum", "field": "bad", "compare": True, "filters": dict(_F)},
                {"id": "b3", "type": "chart", "title": "平均不良率（%）", "dataset_id": "d1", "date_field": "produce_date",
                 "chart_type": "gauge", "agg": "avg", "field": "不良率", "max": 10, "filters": dict(_F)},
                {"id": "b4", "type": "chart", "title": "各操作员产量", "dataset_id": "d1", "date_field": "produce_date",
                 "chart_type": "bar", "group": {"kind": "field", "field": "operator"}, "agg": "sum", "field": "qty",
                 "top_n": 12, "metrics": [], "group2": {"field": None}, "stack": False, "on_click": "drill", "filters": dict(_F)},
                {"id": "b5", "type": "table", "title": "生产明细", "dataset_id": "d1", "date_field": "produce_date",
                 "columns": ["product", "qty", "bad", "不良率", "operator", "produce_date"],
                 "sort_by": "produce_date", "sort_order": "desc", "filters": dict(_F)},
            ],
        },
        "notes": "「不良率」是计算字段（bad / qty * 100），仪表盘的满刻度 10 表示 10%，可按你的质量目标调整；示例数据的生产日期在近 60 天内随机",
    },
    {
        "key": "signup_stats",
        "category": "通用",
        "name": "活动报名统计",
        "description": "近 30 天报名概况：累计/今日新增、每日报名趋势、来源占比与明细",
        "scenario": "统计卡 + 块级口径（今日）+ 折线趋势 + 饼图占比 + 明细表",
        "tables": [{
            "key": "signup", "label": "活动报名表",
            "fields": [
                {"field_name": "name", "label": "姓名", "data_type": "varchar", "nullable": False},
                {"field_name": "phone", "label": "手机号", "data_type": "varchar"},
                {"field_name": "source", "label": "报名来源", "data_type": "varchar",
                 "widget": "select", "options": {"options": ["朋友圈", "公众号", "朋友推荐", "官网"]}},
                {"field_name": "signup_time", "label": "报名时间", "data_type": "datetime", "widget": "datetime-picker"},
            ],
        }],
        "report": {
            "name": "活动报名统计",
            "description": "模板安装：近 30 天报名概况（「今日新增」演示块级口径覆盖）",
            "range": {"mode": "past_30d"},
            "datasets": [{"id": "d1", "name": "活动报名表", "base_table_id": "$signup", "joins": [], "computed_fields": []}],
            "blocks": [
                {"id": "b1", "type": "stat", "title": "累计报名", "dataset_id": "d1", "date_field": "signup_time",
                 "agg": "count", "field": None, "filters": dict(_F)},
                {"id": "b2", "type": "stat", "title": "今日新增", "dataset_id": "d1", "date_field": "signup_time",
                 "agg": "count", "field": None, "range_mode": "today", "filters": dict(_F)},
                {"id": "b3", "type": "chart", "title": "每日报名趋势", "dataset_id": "d1", "date_field": "signup_time",
                 "chart_type": "line", "group": {"kind": "day", "field": "signup_time"}, "agg": "count", "field": None,
                 "top_n": 30, "metrics": [], "group2": {"field": None}, "stack": False, "on_click": "drill", "filters": dict(_F)},
                {"id": "b4", "type": "chart", "title": "报名来源占比", "dataset_id": "d1", "date_field": "signup_time",
                 "chart_type": "pie", "group": {"kind": "field", "field": "source"}, "agg": "count", "field": None,
                 "top_n": 8, "metrics": [], "group2": {"field": None}, "stack": False, "on_click": "drill", "filters": dict(_F)},
                {"id": "b5", "type": "table", "title": "报名明细", "dataset_id": "d1", "date_field": "signup_time",
                 "columns": ["name", "phone", "source", "signup_time"],
                 "sort_by": "signup_time", "sort_order": "desc", "filters": dict(_F)},
            ],
        },
        "notes": "「今日新增」区块演示了块级口径覆盖：整表看近 30 天，该卡只看今天（选中区块 → 右侧「时间范围」）；报名时间是业务日期字段，比系统创建时间更准确",
    },
]


def list_templates(db: Session, user: User) -> list[dict]:
    """模板列表（不含报表定义细节），附带所需表是否已存在。"""
    owned = {t.label for t in db.query(MetaTable).filter_by(owner_id=user.id, status="active").all()}
    return [
        {
            "key": t["key"], "name": t["name"], "description": t["description"],
            "scenario": t["scenario"], "category": t.get("category", "其他"), "notes": t["notes"],
            "tables": [{"label": tb["label"], "exists": tb["label"] in owned} for tb in t["tables"]],
        }
        for t in TEMPLATES
    ]


def install_template(db: Session, user: User, key: str, with_demo_data: bool = False) -> dict:
    from fastapi import HTTPException
    tpl = next((t for t in TEMPLATES if t["key"] == key), None)
    if not tpl:
        raise HTTPException(404, "模板不存在")

    from . import entitlement
    from .tenancy import default_tenant_id
    tid = default_tenant_id(db, user)
    entitlement.assert_tenant_writable(db, tid)

    notes = []
    table_ids: dict[str, int] = {}
    for tb in tpl["tables"]:
        existing = (
            db.query(MetaTable)
            .filter_by(owner_id=user.id, label=tb["label"], status="active")
            .first()
        )
        if existing:
            table_ids[tb["key"]] = existing.id
            notes.append(f"复用已有表「{tb['label']}」（请确认字段与模板要求一致）")
            continue
        tc = TableCreate(
            label=tb["label"],
            fields=[FieldIn(**f) for f in tb["fields"]],
            storage_mode="json",
        )
        try:
            # 模板市场建表与手工建表同一道配额闸（此前为绕过点）
            entitlement.check_quota(db, tid, "max_tables")
            mt = meta_service.create_business_table(db, tc, owner_id=user.id, tenant_id=tid)
            entitlement.bump_usage(db, tid, "table_count", 1)
        except HTTPException:
            db.rollback()
            raise   # 配额/只读 403 直接透传
        except Exception as e:  # noqa: BLE001
            db.rollback()
            raise HTTPException(400, f"建表失败：{e}")
        table_ids[tb["key"]] = mt.id
        if with_demo_data:
            try:
                cnt = _seed_demo_data(db, mt.id, user)
                notes.append(f"已为「{tb['label']}」生成 {cnt} 条示例数据")
            except Exception as e:  # noqa: BLE001 — 示例数据失败不影响安装
                db.rollback()
                notes.append(f"「{tb['label']}」示例数据生成失败：{e}")

    spec = _remap(tpl["report"], table_ids)
    payload = ReportTemplateIn(
        name=spec["name"], description=spec.get("description"),
        table_id=spec["datasets"][0]["base_table_id"], enabled=False,
        range=spec.get("range") or {"mode": "this_week"},
        blocks=spec["blocks"], layout=spec.get("layout"), source=None,
        datasets=spec["datasets"], filter_fields=[], schedule={}, push={},
    )
    validate_template(db, payload)   # 与手工创建同一套完整校验
    rt = ReportTemplate(
        user_id=user.id, tenant_id=tid, name=payload.name, description=payload.description, enabled=False,
        range_json=payload.range, blocks_json=payload.blocks, layout_json=payload.layout,
        source_json=None, datasets_json=payload.datasets or None, filters_json=[],
        schedule_json={}, push_json={},
        table_id=payload.table_id,
    )
    db.add(rt)
    db.commit()
    db.refresh(rt)
    if tpl.get("notes"):
        notes.append(tpl["notes"])
    return {"report_id": rt.id, "name": rt.name, "notes": "；".join(notes)}
