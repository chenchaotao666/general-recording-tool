"""内置工作流模板市场：场景模板一键安装。

模板 = 所需表结构 + 工作流定义（table 引用用 "$表key" 占位）。
安装：按 label 复用已有表或自动建表 → 占位符重映射为真实 table_id →
validate_definition 校验 → 落库（默认停用，用户到画布确认后启用）。
"""
from sqlalchemy.orm import Session

from ...models import MetaTable, User, Workflow
from ...schemas import FieldIn, TableCreate
from .. import meta_service
from .engine import WorkflowError, validate_definition

TEMPLATES: list[dict] = [
    {
        "key": "stock_alert",
        "name": "低库存预警",
        "description": "库存数量修改后自动检查，低于安全线立刻通知负责人",
        "scenario": "记录修改 → 条件判断（数量 < 安全线）→ 站内通知",
        "tables": [{
            "key": "stock", "label": "库存表",
            "fields": [
                {"field_name": "item", "label": "品名", "data_type": "varchar"},
                {"field_name": "qty", "label": "数量", "data_type": "int", "widget": "number"},
                {"field_name": "safety", "label": "安全库存", "data_type": "int", "widget": "number"},
            ],
        }],
        "workflow": {
            "name": "低库存预警",
            "description": "库存低于安全线自动提醒（模板安装，默认停用）",
            "trigger": {"type": "record_updated", "table_id": "$stock", "watch_fields": ["qty"]},
            "nodes": [
                {"id": "c_1", "type": "condition", "name": "低于安全线？",
                 "config": {"record": "{trigger.record}", "table_id": "$stock", "logic": "AND",
                            "rules": [{"field": "qty", "op": "lt", "value": "{trigger.record.safety}"}]}},
                {"id": "send_1", "type": "send_message", "name": "通知负责人",
                 "config": {"channel": "notify", "title": "低库存提醒",
                            "template": "「{trigger.record.item}」库存仅剩 {trigger.record.qty}，低于安全线，请安排补货"}},
            ],
            "edges": [{"from": "c_1", "to": "send_1", "branch": "true"}],
        },
        "notes": "条件中「安全线」取自记录自身的 safety 字段，如想统一阈值可直接改成数字",
    },
    {
        "key": "feedback_triage",
        "name": "客户反馈智能分流",
        "description": "新反馈录入后 AI 自动判断紧急程度，紧急的立刻通知，并回写定级结果",
        "scenario": "记录新增 → LLM 定级 → 条件分支（紧急）→ 通知 / 回写级别",
        "tables": [{
            "key": "feedback", "label": "客户反馈表",
            "fields": [
                {"field_name": "customer", "label": "客户", "data_type": "varchar"},
                {"field_name": "content", "label": "反馈内容", "data_type": "text"},
                {"field_name": "level", "label": "紧急程度", "data_type": "varchar",
                 "widget": "select", "options": {"options": ["紧急", "普通"]}, "default_value": "普通"},
            ],
        }],
        "workflow": {
            "name": "客户反馈智能分流",
            "description": "AI 定级 + 紧急通知（模板安装，默认停用）",
            "trigger": {"type": "record_created", "table_id": "$feedback"},
            "nodes": [
                {"id": "llm_1", "type": "llm_transform", "name": "AI 定级",
                 "config": {
                     "prompt": "请判断以下客户反馈的紧急程度，输出 JSON：{\"urgent\": true或false, \"reason\": \"一句话原因\"}。\n判断标准：涉及安全、资金损失、强烈投诉、影响正常使用的为紧急。\n客户：{trigger.record.customer}\n反馈内容：{trigger.record.content}",
                     "output_format": "json",
                 }},
                {"id": "u_1", "type": "update_record", "name": "回写定级",
                 "config": {"table_id": "$feedback",
                            "match_filters": {"logic": "AND", "rules": [{"field": "id", "op": "eq", "value": "{trigger.record.id}"}]},
                            "field_mapping": {"level": "{nodes.llm_1.data.urgent}"}}},
                {"id": "c_1", "type": "condition", "name": "紧急？",
                 "config": {"record": "{nodes.llm_1.data}", "logic": "AND",
                            "rules": [{"field": "urgent", "op": "eq", "value": True}]}},
                {"id": "send_1", "type": "send_message", "name": "紧急通知",
                 "config": {"channel": "notify", "title": "紧急客户反馈",
                            "template": "客户「{trigger.record.customer}」的反馈被 AI 判定为紧急：\n{trigger.record.content}\n原因：{nodes.llm_1.data.reason}"}},
            ],
            "edges": [
                {"from": "llm_1", "to": "u_1"},
                {"from": "u_1", "to": "c_1"},
                {"from": "c_1", "to": "send_1", "branch": "true"},
            ],
        },
        "notes": "「回写定级」节点把 urgent 写入 level 字段（true/false），可改为映射成 紧急/普通 文案",
    },
    {
        "key": "daily_digest",
        "name": "每日收支日报",
        "description": "每天早上 AI 汇总昨天的收支记录，生成一段分析结论推送给你",
        "scenario": "定时触发 → 查询昨日记录 → LLM 总结 → 站内通知",
        "tables": [{
            "key": "ledger", "label": "收支记录表",
            "fields": [
                {"field_name": "item", "label": "事项", "data_type": "varchar"},
                {"field_name": "amount", "label": "金额", "data_type": "decimal", "widget": "number"},
                {"field_name": "type", "label": "类型", "data_type": "varchar",
                 "widget": "select", "options": {"options": ["收入", "支出"]}},
                {"field_name": "date", "label": "日期", "data_type": "date", "widget": "date-picker"},
            ],
        }],
        "workflow": {
            "name": "每日收支日报",
            "description": "每天 9 点 AI 生成昨日收支摘要（模板安装，默认停用）",
            "trigger": {"type": "cron", "expr": "0 9 * * *"},
            "nodes": [
                {"id": "q_1", "type": "query_records", "name": "查昨日收支",
                 "config": {"table_id": "$ledger",
                            "filters": {"logic": "AND", "rules": [{"field": "date", "op": "past_days", "value": 1}]},
                            "limit": 200, "order_by": "date", "order_desc": True}},
                {"id": "llm_1", "type": "llm_transform", "name": "AI 写日报",
                 "config": {
                     "prompt": "以下是昨天的收支记录（共 {nodes.q_1.count} 条）：\n{nodes.q_1.records}\n\n请生成一份简短的昨日收支日报：总收入、总支出、净额、最大的一笔支出是什么、一句简评。",
                     "system": "你是一个简洁的财务助理。",
                     "output_format": "text",
                 }},
                {"id": "send_1", "type": "send_message", "name": "推送日报",
                 "config": {"channel": "notify", "title": "每日收支日报", "template": "{nodes.llm_1.text}"}},
            ],
            "edges": [{"from": "q_1", "to": "llm_1"}, {"from": "llm_1", "to": "send_1"}],
        },
        "notes": "想把通知改成邮件，编辑「推送日报」节点的通道并填收件人即可",
    },
    {
        "key": "expense_approval",
        "name": "报销审批流",
        "description": "新报销单自动进入审批：负责人在通知里一键通过/驳回，结果自动回写状态",
        "scenario": "记录新增 → 人工审批 → 条件分支 → 回写状态 + 通知申请人",
        "tables": [{
            "key": "expense", "label": "报销单",
            "fields": [
                {"field_name": "title", "label": "报销事项", "data_type": "varchar"},
                {"field_name": "amount", "label": "金额", "data_type": "decimal", "widget": "number"},
                {"field_name": "applicant", "label": "申请人", "data_type": "varchar"},
                {"field_name": "status", "label": "状态", "data_type": "varchar",
                 "widget": "select", "options": {"options": ["待审批", "已通过", "已驳回"]},
                 "default_value": "待审批"},
            ],
        }],
        "workflow": {
            "name": "报销审批流",
            "description": "审批通过后自动回写状态（模板安装，默认停用）",
            "trigger": {"type": "record_created", "table_id": "$expense"},
            "nodes": [
                {"id": "a_1", "type": "approval", "name": "负责人审批",
                 "config": {"title": "报销审批：{trigger.record.title}（¥{trigger.record.amount}）",
                            "detail_template": "申请人：{trigger.record.applicant}\n金额：{trigger.record.amount} 元\n请到执行详情页处理。"}},
                {"id": "c_1", "type": "condition", "name": "通过？",
                 "config": {"record": "{nodes.a_1}", "logic": "AND",
                            "rules": [{"field": "approved", "op": "eq", "value": True}]}},
                {"id": "u_1", "type": "update_record", "name": "回写已通过",
                 "config": {"table_id": "$expense",
                            "match_filters": {"logic": "AND", "rules": [{"field": "id", "op": "eq", "value": "{trigger.record.id}"}]},
                            "field_mapping": {"status": "已通过"}}},
                {"id": "u_2", "type": "update_record", "name": "回写已驳回",
                 "config": {"table_id": "$expense",
                            "match_filters": {"logic": "AND", "rules": [{"field": "id", "op": "eq", "value": "{trigger.record.id}"}]},
                            "field_mapping": {"status": "已驳回"}}},
            ],
            "edges": [
                {"from": "a_1", "to": "c_1"},
                {"from": "c_1", "to": "u_1", "branch": "true"},
                {"from": "c_1", "to": "u_2", "branch": "false"},
            ],
        },
        "notes": "审批人默认是工作流归属人；如需指定其他同事，编辑审批节点的「审批人」配置",
    },
]


def list_templates(db: Session, user: User) -> list[dict]:
    """模板列表（不含工作流定义细节），附带所需表是否已存在。"""
    owned = {t.label for t in db.query(MetaTable).filter_by(owner_id=user.id, status="active").all()}
    return [
        {
            "key": t["key"], "name": t["name"], "description": t["description"],
            "scenario": t["scenario"], "notes": t["notes"],
            "tables": [{"label": tb["label"], "exists": tb["label"] in owned} for tb in t["tables"]],
        }
        for t in TEMPLATES
    ]


def _remap(obj, table_ids: dict[str, int]):
    """递归把 "$表key" 占位符替换为真实 table_id。"""
    if isinstance(obj, str) and obj.startswith("$") and obj[1:] in table_ids:
        return table_ids[obj[1:]]
    if isinstance(obj, dict):
        return {k: _remap(v, table_ids) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_remap(v, table_ids) for v in obj]
    return obj


def install_template(db: Session, user: User, key: str) -> dict:
    tpl = next((t for t in TEMPLATES if t["key"] == key), None)
    if not tpl:
        raise WorkflowError("模板不存在")

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
            mt = meta_service.create_business_table(db, tc, owner_id=user.id)
        except Exception as e:  # noqa: BLE001
            db.rollback()
            raise WorkflowError(f"建表失败：{e}")
        table_ids[tb["key"]] = mt.id

    wf_def = _remap(tpl["workflow"], table_ids)
    validate_definition(db, wf_def["trigger"], wf_def["nodes"], wf_def["edges"], user)
    wf = Workflow(
        user_id=user.id, name=wf_def["name"], description=wf_def.get("description") or "",
        enabled=False, trigger_json=wf_def["trigger"],
        nodes_json=wf_def["nodes"], edges_json=wf_def["edges"],
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    if tpl.get("notes"):
        notes.append(tpl["notes"])
    return {"workflow_id": wf.id, "name": wf.name, "notes": "；".join(notes)}
