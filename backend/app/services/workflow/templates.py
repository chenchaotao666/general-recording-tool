"""内置工作流模板市场：场景模板一键安装。

模板 = 所需表结构 + 工作流定义（table 引用用 "$表key" 占位）。
安装：按 label 复用已有表或自动建表 → 占位符重映射为真实 table_id →
validate_definition 校验 → 落库（默认停用，用户到画布确认后启用）。
可选：为新建的表生成示例数据，方便装完直接试运行。
"""
import random
import uuid
from datetime import date, timedelta

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
        "key": "weekly_sales_report",
        "name": "销售业绩周报（汇总统计）",
        "description": "每周一早上汇总上周销售业绩：单数、总额、按销售员分组排名，AI 写成周报推送",
        "scenario": "定时触发 → 查询上周记录 → 汇总统计（分组）→ AI 写周报 → 站内通知",
        "tables": [{
            "key": "sales", "label": "销售业绩表",
            "fields": [
                {"field_name": "salesperson", "label": "销售员", "data_type": "varchar"},
                {"field_name": "product", "label": "产品", "data_type": "varchar"},
                {"field_name": "amount", "label": "成交金额", "data_type": "decimal", "widget": "number"},
                {"field_name": "deal_date", "label": "成交日期", "data_type": "date", "widget": "date-picker"},
            ],
        }],
        "workflow": {
            "name": "销售业绩周报",
            "description": "每周一 9 点汇总上周业绩并生成周报（模板安装，默认停用）",
            "trigger": {"type": "cron", "expr": "0 9 * * 1"},
            "nodes": [
                {"id": "q_1", "type": "query_records", "name": "查上周业绩",
                 "config": {"table_id": "$sales",
                            "filters": {"logic": "AND", "rules": [
                                {"field": "deal_date", "op": "gte", "value": "{now.last_week_start}"},
                                {"field": "deal_date", "op": "lte", "value": "{now.last_week_end}"}]},
                            "limit": 500, "order_by": "deal_date", "order_desc": True}},
                {"id": "s_1", "type": "aggregate", "name": "汇总并分组",
                 "config": {"records": "{nodes.q_1.records}", "group_by": "salesperson",
                            "aggs": [{"op": "count", "title": "成交单数"},
                                     {"op": "sum", "field": "amount", "title": "成交总额"},
                                     {"op": "avg", "field": "amount", "title": "平均单价"},
                                     {"op": "max", "field": "amount", "title": "最大一单"}]}},
                {"id": "llm_1", "type": "llm_transform", "name": "AI 写周报",
                 "config": {
                     "prompt": "上周销售业绩（共 {nodes.q_1.count} 条）：\n整体统计：{nodes.s_1.stats}\n按销售员分组：{nodes.s_1.groups}\n\n请写一份简短的上周销售业绩周报：整体概况、销售员排名点评、一句下周建议。",
                     "system": "你是一个简洁的销售分析助理。",
                     "output_format": "text",
                 }},
                {"id": "send_1", "type": "send_message", "name": "推送周报",
                 "config": {"channel": "notify", "title": "销售业绩周报", "template": "{nodes.llm_1.text}"}},
            ],
            "edges": [{"from": "q_1", "to": "s_1"}, {"from": "s_1", "to": "llm_1"},
                      {"from": "llm_1", "to": "send_1"}],
        },
        "notes": "「查上周业绩」的筛选值用了内置时间变量 {now.last_week_start} ~ {now.last_week_end}（上周一到周日），点「插入变量」可换成本周/本月等；「汇总并分组」节点可按需改成分组到产品；示例数据里的成交日期在近 60 天内随机，试运行时点「查上周业绩」节点的 ▶ 可先验证查询",
    },
    {
        "key": "feedback_switch",
        "name": "客户反馈三路分流（多路分支）",
        "description": "新反馈录入后 AI 判断紧急程度和情感，按结果走三条路：紧急通知负责人 / 负面标记跟进 / 其余归档",
        "scenario": "记录新增 → AI 分析（JSON）→ 多路分支（紧急 / 负面 / 默认）→ 通知或回写级别",
        "tables": [{
            "key": "feedback3", "label": "意见反馈表",
            "fields": [
                {"field_name": "customer", "label": "客户", "data_type": "varchar"},
                {"field_name": "content", "label": "反馈内容", "data_type": "text"},
                {"field_name": "level", "label": "处理级别", "data_type": "varchar",
                 "widget": "select", "options": {"options": ["待处理", "紧急处理", "需跟进", "正常"]},
                 "default_value": "待处理"},
            ],
        }],
        "workflow": {
            "name": "客户反馈三路分流",
            "description": "AI 分析 + 多路分支处理（模板安装，默认停用）",
            "trigger": {"type": "record_created", "table_id": "$feedback3"},
            "nodes": [
                {"id": "llm_1", "type": "llm_transform", "name": "AI 分析",
                 "config": {
                     "prompt": "请判断以下客户反馈的情感倾向（正面/负面/中性）和紧急程度（高/中/低）。\n输出 JSON：{\"sentiment\": \"...\", \"urgency\": \"...\", \"reason\": \"一句话理由\"}\n判断标准：涉及安全、资金损失、强烈投诉、无法正常使用为「高」。\n\n客户：{trigger.record.customer}\n反馈内容：{trigger.record.content}",
                     "system": "你是一个情感分析助手，只输出 JSON。",
                     "output_format": "json",
                 }},
                {"id": "sw_1", "type": "switch", "name": "分流",
                 "config": {"record": "{nodes.llm_1.data}",
                            "cases": [
                                {"label": "紧急", "field": "urgency", "op": "eq", "value": "高"},
                                {"label": "负面", "field": "sentiment", "op": "eq", "value": "负面"},
                            ]}},
                {"id": "send_1", "type": "send_message", "name": "紧急通知",
                 "config": {"channel": "notify", "title": "紧急客户反馈",
                            "template": "客户「{trigger.record.customer}」的反馈被 AI 判定为紧急：\n{trigger.record.content}\n原因：{nodes.llm_1.data.reason}"}},
                {"id": "u_1", "type": "update_record", "name": "标记需跟进",
                 "config": {"table_id": "$feedback3",
                            "match_filters": {"logic": "AND", "rules": [{"field": "id", "op": "eq", "value": "{trigger.record.id}"}]},
                            "field_mapping": {"level": "需跟进"}}},
                {"id": "u_2", "type": "update_record", "name": "归档为正常",
                 "config": {"table_id": "$feedback3",
                            "match_filters": {"logic": "AND", "rules": [{"field": "id", "op": "eq", "value": "{trigger.record.id}"}]},
                            "field_mapping": {"level": "正常"}}},
            ],
            "edges": [
                {"from": "llm_1", "to": "sw_1"},
                {"from": "sw_1", "to": "send_1", "branch": "紧急"},
                {"from": "sw_1", "to": "u_1", "branch": "负面"},
                {"from": "sw_1", "to": "u_2", "branch": "default"},
            ],
        },
        "notes": "多路分支从上到下第一个命中生效；紧急分支只发了通知，可加一个更新记录节点把级别改成「紧急处理」",
    },
    {
        "key": "stock_wecom_digest",
        "name": "每日库存汇总（企业微信）",
        "description": "每天傍晚统计库存：品种数、总库存量、低于安全线的品名，推送到企业微信群机器人",
        "scenario": "定时触发 → 查询全部库存 → 汇总统计 → 企业微信机器人",
        "tables": [{
            "key": "stock2", "label": "库存表",
            "fields": [
                {"field_name": "item", "label": "品名", "data_type": "varchar"},
                {"field_name": "qty", "label": "数量", "data_type": "int", "widget": "number"},
                {"field_name": "safety", "label": "安全库存", "data_type": "int", "widget": "number"},
            ],
        }],
        "workflow": {
            "name": "每日库存汇总",
            "description": "每天 18 点汇总库存推企业微信（模板安装，默认停用）",
            "trigger": {"type": "cron", "expr": "0 18 * * *"},
            "nodes": [
                {"id": "q_1", "type": "query_records", "name": "查全部库存",
                 "config": {"table_id": "$stock2", "limit": 500}},
                {"id": "s_1", "type": "aggregate", "name": "库存统计",
                 "config": {"records": "{nodes.q_1.records}",
                            "aggs": [{"op": "count_distinct", "field": "item", "title": "品种数"},
                                     {"op": "sum", "field": "qty", "title": "总库存量"},
                                     {"op": "min", "field": "qty", "title": "最少库存"}]}},
                {"id": "send_1", "type": "send_message", "name": "推企业微信",
                 "config": {"channel": "wecom", "title": "每日库存汇总",
                            "template": "今日库存：共 {nodes.s_1.stats.品种数} 个品种，总库存量 {nodes.s_1.stats.总库存量}，最少库存 {nodes.s_1.stats.最少库存}。\n明细：{nodes.q_1.records}"}},
            ],
            "edges": [{"from": "q_1", "to": "s_1"}, {"from": "s_1", "to": "send_1"}],
        },
        "notes": "需要在「推企业微信」节点填入群机器人 Webhook 地址（企业微信群 → 群机器人 → 添加 → 复制 Webhook）；也可把通道改成钉钉机器人，格式一样",
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
        "notes": "审批人默认是工作流归属人；如需指定其他同事，编辑审批节点的「审批人」配置；审批通知里的链接免登录，点开即可通过/驳回（7 天内有效）",
    },
    {
        "key": "visit_reminder_loop",
        "name": "客户回访逐条提醒（逐条处理）",
        "description": "每天早上查出到期未回访的客户，逐条发回访提醒，全部发完再发一条汇总",
        "scenario": "定时触发 → 查询到期客户 → 逐条处理（循环体：逐条发提醒）→ 完成 → 汇总通知",
        "tables": [{
            "key": "visit", "label": "客户回访表",
            "fields": [
                {"field_name": "customer", "label": "客户", "data_type": "varchar"},
                {"field_name": "visit_date", "label": "回访日期", "data_type": "date", "widget": "date-picker"},
                {"field_name": "note", "label": "回访备注", "data_type": "text", "widget": "textarea"},
            ],
        }],
        "workflow": {
            "name": "客户回访逐条提醒",
            "description": "每天 9 点对到期客户逐条发回访提醒（模板安装，默认停用）",
            "trigger": {"type": "cron", "expr": "0 9 * * *"},
            "nodes": [
                {"id": "q_1", "type": "query_records", "name": "查到期客户",
                 "config": {"table_id": "$visit",
                            "filters": {"logic": "AND", "rules": [
                                {"field": "visit_date", "op": "lte", "value": "{now.today}"}]},
                            "limit": 100, "order_by": "visit_date", "order_desc": False}},
                {"id": "loop_1", "type": "foreach", "name": "逐条处理",
                 "config": {"items": "{nodes.q_1.records}", "max_items": 50}},
                {"id": "send_1", "type": "send_message", "name": "发回访提醒",
                 "config": {"channel": "notify", "title": "回访提醒：{nodes.loop_1.item.customer}",
                            "template": "第 {nodes.loop_1.index} 条（共 {nodes.loop_1.count} 条）\n客户：{nodes.loop_1.item.customer}\n回访日期：{nodes.loop_1.item.visit_date}\n备注：{nodes.loop_1.item.note}"}},
                {"id": "send_2", "type": "send_message", "name": "发汇总通知",
                 "config": {"channel": "notify", "title": "今日回访提醒已发完",
                            "template": "今天到期客户共 {nodes.loop_1.count} 位，已逐条提醒。"}},
            ],
            "edges": [
                {"from": "q_1", "to": "loop_1"},
                {"from": "loop_1", "to": "send_1", "branch": "loop"},
                {"from": "send_1", "to": "loop_1"},   # 回边：循环体末尾连回逐条处理节点
                {"from": "loop_1", "to": "send_2", "branch": "done"},
            ],
        },
        "notes": "「逐条处理」的两个出口：每条 → 循环体（末尾必须连回本节点形成循环），完成 → 后续节点；循环体内用 {nodes.loop_1.item.字段名} 引用当前客户。示例数据的回访日期在近 60 天内随机，安装后点「立即执行」即可看到逐条提醒",
    },
    {
        "key": "signup_form",
        "name": "活动报名表单（公开表单）",
        "description": "生成免登录的公开报名表单链接，外部人员填写提交后自动入表并通知你",
        "scenario": "表单提交（公开链接）→ 写入报名表 → 站内通知",
        "tables": [{
            "key": "signup", "label": "活动报名表",
            "fields": [
                {"field_name": "name", "label": "姓名", "data_type": "varchar", "nullable": False},
                {"field_name": "phone", "label": "手机号", "data_type": "varchar", "nullable": False},
                {"field_name": "note", "label": "备注", "data_type": "text", "widget": "textarea"},
            ],
        }],
        "workflow": {
            "name": "活动报名表单",
            "description": "公开表单提交后通知负责人（模板安装，默认停用——启用后链接才生效）",
            "trigger": {"type": "form", "table_id": "$signup"},
            "nodes": [
                {"id": "send_1", "type": "send_message", "name": "通知负责人",
                 "config": {"channel": "notify", "title": "新报名：{trigger.record.name}",
                            "template": "姓名：{trigger.record.name}\n手机号：{trigger.record.phone}\n备注：{trigger.record.note}"}},
            ],
            "edges": [],
        },
        "notes": "安装后到画布启用工作流，触发器面板里的公开链接即生效，发给任何人都能填表；{trigger.record.字段名} 可引用提交的内容。图片字段不会出现在公开表单里",
    },
    {
        "key": "feedback_form_ai",
        "name": "意见收集 + AI 分析（表单触发）",
        "description": "公开表单收集意见，提交后 AI 立刻判断情感倾向和要点，推送给负责人",
        "scenario": "表单提交（公开链接）→ AI 分析（情感/要点）→ 站内通知负责人",
        "tables": [{
            "key": "fbform", "label": "意见收集表",
            "fields": [
                {"field_name": "name", "label": "称呼", "data_type": "varchar"},
                {"field_name": "content", "label": "意见内容", "data_type": "text",
                 "widget": "textarea", "nullable": False},
                {"field_name": "contact", "label": "联系方式（可选）", "data_type": "varchar"},
            ],
        }],
        "workflow": {
            "name": "意见收集 AI 分析",
            "description": "公开表单提交后 AI 分析并通知（模板安装，默认停用——启用后链接才生效）",
            "trigger": {"type": "form", "table_id": "$fbform"},
            "nodes": [
                {"id": "llm_1", "type": "llm_transform", "name": "AI 分析",
                 "config": {
                     "prompt": "请分析以下用户意见，输出 JSON：{\"sentiment\": \"正面/负面/中性\", \"points\": \"一句话要点\"}\n\n称呼：{trigger.record.name}\n内容：{trigger.record.content}",
                     "system": "你是一个严谨的用户反馈分析助手，只输出 JSON。",
                     "output_format": "json",
                 }},
                {"id": "send_1", "type": "send_message", "name": "通知负责人",
                 "config": {"channel": "notify", "title": "新意见（{nodes.llm_1.data.sentiment}）",
                            "template": "来自：{trigger.record.name}（{trigger.record.contact}）\n要点：{nodes.llm_1.data.points}\n\n原文：{trigger.record.content}"}},
            ],
            "edges": [{"from": "llm_1", "to": "send_1"}],
        },
        "notes": "启用后把触发器面板的公开链接发给用户即可收集意见；负面意见想单独告警的话，在「AI 分析」后加一个多路分支节点按 sentiment 分流",
    },
    {
        "key": "notify_sub",
        "name": "统一通知子流程（被调用）",
        "description": "可复用的通知子流程：其他工作流用「子流程调用」节点传 title/content 即可发通知",
        "scenario": "被「子流程调用」节点调用 → 站内通知",
        "tables": [],
        "workflow": {
            "name": "统一通知子流程",
            "description": "供其他工作流复用（模板安装，默认停用不影响被调用）",
            "trigger": {"type": "manual"},
            "nodes": [
                {"id": "send_1", "type": "send_message", "name": "发通知",
                 "config": {"channel": "notify", "title": "{trigger.params.title}",
                            "template": "{trigger.params.content}"}},
            ],
            "edges": [],
        },
        "notes": "本身不用启用：其他工作流加「子流程调用」节点选择它，传参 {\"title\": \"标题\", \"content\": \"内容\"} 即可；想换成邮件/企业微信通知，改这一个流程就全局生效",
    },
    {
        "key": "stock_alert_sub",
        "name": "库存低量预警（子流程复用）",
        "description": "每天早上查出库存低于预警线的品名，通过「统一通知子流程」发预警",
        "scenario": "定时触发 → 查询低库存 → 子流程调用（复用统一通知）",
        "tables": [{
            "key": "stock3", "label": "库存预警表",
            "fields": [
                {"field_name": "item", "label": "品名", "data_type": "varchar"},
                {"field_name": "qty", "label": "库存数量", "data_type": "int", "widget": "number"},
            ],
        }],
        "workflow": {
            "name": "库存低量预警",
            "description": "每天 8 点预警低库存（模板安装，默认停用）",
            "trigger": {"type": "cron", "expr": "0 8 * * *"},
            "nodes": [
                {"id": "q_1", "type": "query_records", "name": "查低库存",
                 "config": {"table_id": "$stock3",
                            "filters": {"logic": "AND", "rules": [{"field": "qty", "op": "lte", "value": 10}]},
                            "limit": 100, "order_by": "qty", "order_desc": False}},
                {"id": "sub_1", "type": "sub_workflow", "name": "发预警（子流程）",
                 "config": {"workflow_name": "统一通知子流程",
                            "params": {"title": "库存低量预警", "content": "低于预警线的品名明细：{nodes.q_1.records}"}}},
            ],
            "edges": [{"from": "q_1", "to": "sub_1"}],
        },
        "notes": "建议先安装「统一通知子流程」模板——本模板的子流程节点会按名字自动对上；没装也能用：该节点会被停用，编辑它手动选一个子流程再启用即可",
    },
    {
        "key": "followup_dedupe_loop",
        "name": "客户跟进去重提醒（去重 + 逐条）",
        "description": "每天早上汇总近 3 天的跟进记录，按客户去重后逐条发提醒，避免同一客户轰炸多次",
        "scenario": "定时触发 → 查询近 3 天跟进 → 按客户去重 → 逐条处理（发提醒）→ 汇总通知",
        "tables": [{
            "key": "follow", "label": "客户跟进表",
            "fields": [
                {"field_name": "customer", "label": "客户", "data_type": "varchar"},
                {"field_name": "owner", "label": "跟进人", "data_type": "varchar"},
                {"field_name": "content", "label": "跟进内容", "data_type": "text", "widget": "textarea"},
                {"field_name": "follow_date", "label": "跟进日期", "data_type": "date", "widget": "date-picker"},
            ],
        }],
        "workflow": {
            "name": "客户跟进去重提醒",
            "description": "每天 9 点按客户去重后逐条提醒（模板安装，默认停用）",
            "trigger": {"type": "cron", "expr": "0 9 * * *"},
            "nodes": [
                {"id": "q_1", "type": "query_records", "name": "查近 3 天跟进",
                 "config": {"table_id": "$follow",
                            "filters": {"logic": "AND", "rules": [{"field": "follow_date", "op": "past_days", "value": 3}]},
                            "limit": 200, "order_by": "follow_date", "order_desc": True}},
                {"id": "d_1", "type": "dedupe", "name": "按客户去重",
                 "config": {"records": "{nodes.q_1.records}", "field": "customer"}},
                {"id": "loop_1", "type": "foreach", "name": "逐条提醒",
                 "config": {"items": "{nodes.d_1.records}", "max_items": 50}},
                {"id": "send_1", "type": "send_message", "name": "发提醒",
                 "config": {"channel": "notify", "title": "跟进提醒：{nodes.loop_1.item.customer}",
                            "template": "跟进人：{nodes.loop_1.item.owner}\n最近跟进：{nodes.loop_1.item.follow_date}\n内容：{nodes.loop_1.item.content}"}},
                {"id": "send_2", "type": "send_message", "name": "发汇总",
                 "config": {"channel": "notify", "title": "今日跟进提醒已发完",
                            "template": "近 3 天跟进记录去重后共 {nodes.d_1.count} 位客户（去掉重复 {nodes.d_1.removed} 条）。"}},
            ],
            "edges": [
                {"from": "q_1", "to": "d_1"},
                {"from": "d_1", "to": "loop_1"},
                {"from": "loop_1", "to": "send_1", "branch": "loop"},
                {"from": "send_1", "to": "loop_1"},
                {"from": "loop_1", "to": "send_2", "branch": "done"},
            ],
        },
        "notes": "同一客户多条跟进只提醒一次（保留最新查询排序的第一条）；示例数据的跟进日期在近 60 天内随机，点「立即执行」即可看到效果",
    },
    {
        "key": "contract_expire",
        "name": "合同到期提醒（日期计算）",
        "description": "每天早上查未来 30 天内到期的合同，汇总金额并通知，提醒提前续约",
        "scenario": "定时触发 → 日期计算（今天+30 天）→ 查询区间内到期合同 → 汇总 → 通知",
        "tables": [{
            "key": "contract", "label": "合同表",
            "fields": [
                {"field_name": "customer", "label": "客户", "data_type": "varchar"},
                {"field_name": "amount", "label": "合同金额", "data_type": "decimal", "widget": "number"},
                {"field_name": "expire_date", "label": "到期日期", "data_type": "date", "widget": "date-picker"},
            ],
        }],
        "workflow": {
            "name": "合同到期提醒",
            "description": "每天 9 点提醒未来 30 天到期合同（模板安装，默认停用）",
            "trigger": {"type": "cron", "expr": "0 9 * * *"},
            "nodes": [
                {"id": "dc_1", "type": "date_calc", "name": "算 30 天后",
                 "config": {"base": "{now.today}", "offset_days": 30}},
                {"id": "q_1", "type": "query_records", "name": "查到期合同",
                 "config": {"table_id": "$contract",
                            "filters": {"logic": "AND", "rules": [
                                {"field": "expire_date", "op": "gte", "value": "{now.today}"},
                                {"field": "expire_date", "op": "lte", "value": "{nodes.dc_1.date}"}]},
                            "limit": 200, "order_by": "expire_date", "order_desc": False}},
                {"id": "s_1", "type": "aggregate", "name": "汇总",
                 "config": {"records": "{nodes.q_1.records}",
                            "aggs": [{"op": "count", "title": "到期合同数"},
                                     {"op": "sum", "field": "amount", "title": "到期总金额"}]}},
                {"id": "send_1", "type": "send_message", "name": "发通知",
                 "config": {"channel": "notify", "title": "合同到期提醒",
                            "template": "未来 30 天有 {nodes.s_1.stats.到期合同数} 份合同到期，总金额 {nodes.s_1.stats.到期总金额} 元。\n明细：{nodes.q_1.records}"}},
            ],
            "edges": [{"from": "dc_1", "to": "q_1"}, {"from": "q_1", "to": "s_1"}, {"from": "s_1", "to": "send_1"}],
        },
        "notes": "「算 30 天后」节点的输出 {nodes.dc_1.date} 直接插在筛选条件里——想提前 60 天提醒就改偏移天数；示例数据的到期日期在未来 60 天内随机，装完点「立即执行」即可看到效果",
    },
    {
        "key": "webhook_alarm",
        "name": "外部告警接入（Webhook 验签）",
        "description": "给外部系统一个 Webhook 地址收告警，自定义响应格式通过验签，告警内容发站内通知",
        "scenario": "Webhook 回调（自定义响应验签）→ 站内通知",
        "tables": [],
        "workflow": {
            "name": "外部告警接入",
            "description": "接收外部系统告警（模板安装，默认停用）",
            "trigger": {"type": "webhook",
                        "response_template": "{\"code\": 0, \"msg\": \"received\", \"echostr\": \"{trigger.params.echostr}\"}"},
            "nodes": [
                {"id": "send_1", "type": "send_message", "name": "告警通知",
                 "config": {"channel": "notify", "title": "外部告警：{trigger.params.level}",
                            "template": "内容：{trigger.params.text}\n来源：{trigger.params.source}\n时间：{now.datetime}"}},
            ],
            "edges": [],
        },
        "notes": "保存并启用后，把 Webhook 地址配到外部系统；自定义响应里的 echostr 用于验签（对方发什么就回什么）；告警参数按对方系统的字段名改 {trigger.params.xxx}",
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


# ---------- 示例数据 ----------

DEMO_DATA_COUNT = 50

_DEMO_NAMES = ["张伟", "王芳", "李娜", "刘洋", "陈杰", "杨静", "赵磊", "黄敏", "周涛", "吴倩"]
_DEMO_ITEMS = ["办公用品采购", "差旅费", "客户招待", "团队建设", "设备维修", "软件订阅", "快递费", "培训费", "市场推广", "日常采购"]
_DEMO_TEXTS = [
    "使用过程中整体顺畅，建议优化操作步骤",
    "响应速度有些慢，高峰期明显",
    "功能很实用，希望增加批量导出",
    "遇到一次数据不同步，请帮忙排查",
    "界面清晰，上手很快",
    "建议增加移动端支持",
]


def _demo_value(f, i: int):
    """按字段类型/控件/名称语义生成示例值。"""
    dt, w, label = f.data_type, f.widget, (f.label or f.field_name)
    if w == "select" and (f.options or {}).get("options"):
        opts = f.options["options"]
        return opts[i % len(opts)]
    if dt == "bool":
        return i % 2 == 0
    if dt == "int":
        return random.randint(1, 100)
    if dt == "decimal":
        return round(random.uniform(10, 2000), 2)
    if dt == "date":
        # 「到期/截止」类字段生成未来日期（到期提醒类模板才能筛出数据），其余生成近 60 天
        if any(k in label for k in ("到期", "截止")):
            return (date.today() + timedelta(days=random.randint(0, 60))).isoformat()
        return (date.today() - timedelta(days=random.randint(0, 60))).isoformat()
    if dt == "datetime":
        d = date.today() - timedelta(days=random.randint(0, 60))
        return f"{d.isoformat()} {random.randint(8, 20):02d}:{random.randint(0, 59):02d}"
    if any(k in label for k in ("申请人", "负责人", "客户", "姓名", "联系人", "销售", "业务员", "经手人")):
        return _DEMO_NAMES[i % len(_DEMO_NAMES)]
    if any(k in label for k in ("内容", "备注", "说明", "反馈")):
        return _DEMO_TEXTS[i % len(_DEMO_TEXTS)]
    if any(k in label for k in ("事项", "品名", "名称", "标题")):
        return _DEMO_ITEMS[i % len(_DEMO_ITEMS)]
    return f"{label}{i + 1}"


def _seed_demo_data(db: Session, table_id: int, user: User, count: int = DEMO_DATA_COUNT) -> int:
    """为新建的表生成示例数据（复用的已有表不动，避免污染真实数据）。"""
    from .. import dyn_engine
    _, fields = dyn_engine.load_meta(db, table_id)
    for i in range(count):
        dyn_engine.create_record(db, table_id, {f.field_name: _demo_value(f, i) for f in fields},
                                 user=user.username)
    return count


def install_template(db: Session, user: User, key: str, with_demo_data: bool = False) -> dict:
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
        if with_demo_data:
            try:
                cnt = _seed_demo_data(db, mt.id, user)
                notes.append(f"已为「{tb['label']}」生成 {cnt} 条示例数据")
            except Exception as e:  # noqa: BLE001 — 示例数据失败不影响安装
                db.rollback()
                notes.append(f"「{tb['label']}」示例数据生成失败：{e}")

    wf_def = _remap(tpl["workflow"], table_ids)
    # 子流程占位：config.workflow_name = 目标工作流名，安装时按名解析为 id；
    # 找不到（对应模板未安装）则停用该节点，由用户在画布手动选择
    for n in wf_def.get("nodes") or []:
        cfg = n.get("config") or {}
        if n.get("type") == "sub_workflow" and not isinstance(cfg.get("workflow_id"), int) and cfg.get("workflow_name"):
            target = db.query(Workflow).filter_by(user_id=user.id, name=cfg["workflow_name"]).first()
            if target:
                cfg["workflow_id"] = target.id
            else:
                n["disabled"] = True
                notes.append(f"子流程节点「{n.get('name') or n['id']}」未找到工作流「{cfg['workflow_name']}」，已暂时停用：请先安装对应模板，或在节点里手动选择子流程后启用")
            cfg.pop("workflow_name", None)
    validate_definition(db, wf_def["trigger"], wf_def["nodes"], wf_def["edges"], user)
    # webhook/表单触发器的 URL 凭证：安装时生成（与画布保存时的行为一致）
    if wf_def["trigger"].get("type") in ("webhook", "form") and not wf_def["trigger"].get("secret"):
        wf_def["trigger"] = {**wf_def["trigger"], "secret": uuid.uuid4().hex}
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
