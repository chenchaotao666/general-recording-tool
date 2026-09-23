"""Prompt 模板集中管理。"""
import json
import re

ANALYZE_SYSTEM = (
    "你是数据结构分析专家。用户会给你一张 Excel 表的表头、每列的本地类型推断结果和脱敏样例数据，"
    "你要推断合理的表结构。只输出 JSON，不要输出任何其他内容。"
)

_OUTPUT_EXAMPLE = {
    "table_name_suggestion": "客户跟进记录",
    "columns": [
        {
            "source_header": "客户姓名",
            "field_name": "customer_name",
            "label": "客户姓名",
            "data_type": "varchar",
            "length": 64,
            "nullable": False,
            "widget": "input",
            "options": {},
            "confidence": 0.95,
        },
        {
            "source_header": "跟进状态",
            "field_name": "status",
            "label": "跟进状态",
            "data_type": "varchar",
            "length": 32,
            "nullable": True,
            "widget": "select",
            "options": {"options": ["进行中", "已成交", "已流失"]},
            "confidence": 0.9,
        },
    ],
    "notes": "分析结论与注意事项（如：表头不在第一行、某列数据多为空等）",
}


def mask_sensitive(text: str) -> str:
    """发给 LLM 前对手机号/身份证做掩码。"""
    text = re.sub(r"(1[3-9]\d)\d{4}(\d{4})", r"\1****\2", text)
    text = re.sub(r"(\d{6})\d{8}(\d{3}[0-9Xx])", r"\1********\2", text)
    return text


JUDGE_SYSTEM = (
    "你是数据筛选助手。用户给你一个自然语言条件和一批数据记录，"
    "你要判断每条记录是否满足条件。只输出 JSON，不要输出任何其他内容。"
)

_JUDGE_OUTPUT_EXAMPLE = {"matched_ids": [1, 3], "reason": "判断依据的简要说明"}


def build_judge_prompt(description: str, fields: list[dict], records: list[dict]) -> str:
    """LLM 逐批判断记录是否满足自然语言条件。"""
    field_desc = [{"field_name": f["field_name"], "含义": f["label"], "类型": f["data_type"]} for f in fields]
    return (
        f"判断条件：{description}\n\n"
        f"字段说明：\n{json.dumps(field_desc, ensure_ascii=False)}\n\n"
        f"记录列表：\n{json.dumps(records, ensure_ascii=False, default=str)}\n\n"
        "要求：\n"
        "1. 逐条判断记录是否满足条件，把满足的记录 id 放入 matched_ids\n"
        "2. 拿不准的记录视为不满足\n"
        "3. id 必须来自上面的记录列表，不要编造\n\n"
        f"输出 JSON 格式示例：\n{json.dumps(_JUDGE_OUTPUT_EXAMPLE, ensure_ascii=False)}\n\n"
        "只输出 JSON。"
    )


VISION_SYSTEM = (
    "你是表单智能填写助手。用户会给你一张或多张图片和一个表单的字段清单，"
    "你要从图片中提取信息辅助填写表单。只输出 JSON，不要输出任何其他内容。"
)

_VISION_OUTPUT_EXAMPLE = {
    "fields": {"customer_name": "张三", "next_follow_date": "2026-10-01"},
    "conflicts": [
        {"field_name": "phone", "recognized": "13900005678", "reason": "图片中的电话与表单当前值不同"}
    ],
    "notes": "识别说明，如：图片中未找到XX字段的信息",
}


def build_vision_prompt(fields: list[dict], current: dict) -> str:
    """fields: [{field_name, label, data_type, options}]；current: 当前表单值（编辑场景）。"""
    desc = []
    for f in fields:
        item = {
            "field_name": f["field_name"],
            "label": f["label"],
            "data_type": f["data_type"],
            "当前值": current.get(f["field_name"]),
        }
        opts = (f.get("options") or {}).get("options")
        if opts:
            item["可选值"] = opts
        desc.append(item)
    return (
        f"请识别图片内容，抽取能对应到以下表单字段的信息：\n\n"
        f"字段清单：\n{json.dumps(desc, ensure_ascii=False, indent=2)}\n\n"
        "要求：\n"
        "1. fields 中只返回图片中能明确确认的字段，不确定的不要猜、不要返回\n"
        "2. 日期统一 YYYY-MM-DD，日期时间统一 YYYY-MM-DD HH:mm:ss\n"
        "3. 数字只给数值（不要带单位/千分位），布尔给 true/false\n"
        "4. 有可选值的字段必须从可选值中选，不要自创\n"
        "5. 识别值与该字段当前值不一致时，放入 conflicts 并说明原因；当前值为空不算冲突\n"
        "6. 不要返回字段清单之外的 field_name\n\n"
        f"输出 JSON 格式示例：\n{json.dumps(_VISION_OUTPUT_EXAMPLE, ensure_ascii=False, indent=2)}\n\n"
        "只输出 JSON。"
    )


def build_analyze_prompt(headers: list[str], columns: list[dict]) -> str:
    cols_desc = [
        {"表头": h, "本地类型推断": c.get("local_type"), "样例值": c.get("samples", [])}
        for h, c in zip(headers, columns)
    ]
    return (
        "请分析以下 Excel 表的结构，给出建表建议。\n\n"
        f"各列信息：\n{json.dumps(cols_desc, ensure_ascii=False, indent=2)}\n\n"
        "要求：\n"
        "1. data_type 只能是 varchar / text / int / decimal / date / datetime / bool 之一\n"
        "2. widget 只能是 input / textarea / number / date-picker / datetime-picker / select / switch 之一\n"
        "3. field_name 用英文小写 snake_case 命名（如 next_follow_date）\n"
        "4. 参考本地类型推断；若语义类型与数据不符（如“到期时间”存的是文本），以数据实际类型为准并在 notes 说明\n"
        "5. 取值高度重复的列（枚举）用 select 控件，并在 options.options 里列出枚举值\n"
        "6. 长文本用 text + textarea；布尔（是/否）用 bool + switch\n"
        "7. confidence 表示你对该列判断的置信度（0~1），不确定的列给低分\n"
        "8. 每一列都必须出现在 columns 中，不要遗漏\n\n"
        f"输出 JSON 格式示例：\n{json.dumps(_OUTPUT_EXAMPLE, ensure_ascii=False, indent=2)}\n\n"
        "只输出 JSON。"
    )


TASK_SYSTEM = (
    "你是自动化任务设计专家。用户会给你一张数据表的字段清单和一句自然语言需求，"
    "你要设计出任务规则配置（触发条件 + 执行周期 + 通知动作）。只输出 JSON，不要输出任何其他内容。"
)

_TASK_OUTPUT_EXAMPLE = {
    "name": "超过30天未跟进客户提醒",
    "condition_mode": "structured",
    "condition": {"logic": "AND", "rules": [
        {"field": "updated_at", "op": "older_than_days", "value": 30},
        {"field": "customer_grade", "op": "ne", "value": "已流失"},
    ]},
    "schedule": {"type": "cron", "expr": "0 9 * * *"},
    "action": {
        "type": "email",
        "template": "客户【{customer_name}】已超过30天未跟进，分级：{customer_grade}，请及时处理。",
        "recipients": {"type": "fixed", "value": "manager@example.com"},
    },
    "cooldown_hours": 24,
    "notes": "设计说明（可选）",
}


def build_task_prompt(description: str, fields: list[dict]) -> str:
    """把自然语言需求转成任务规则配置。fields: [{field_name, label, data_type, options}]"""
    field_desc = []
    for f in fields:
        item = {"field_name": f["field_name"], "含义": f["label"], "类型": f["data_type"]}
        opts = (f.get("options") or {}).get("options")
        if opts:
            item["可选值"] = opts
        field_desc.append(item)
    return (
        f"用户的任务需求：{description}\n\n"
        f"数据表字段（另有系统字段 id / created_at 创建时间 / updated_at 更新时间）：\n"
        f"{json.dumps(field_desc, ensure_ascii=False, indent=2)}\n\n"
        "任务规则配置规则：\n"
        "1. condition_mode 判断方式：\n"
        "   - structured 结构化条件（优先）：condition = {logic: AND|OR, rules: [{field, op, value}]}。\n"
        "     op 只能是 eq/ne/gt/gte/lt/lte/contains/startswith/in/null/not_null/"
        "today（当天，不需要 value）/past_days（过去 N 天含今天，value 为天数）/"
        "older_than_days（早于 N 天前）/within_days（未来 N 天内）；\n"
        "     past_days/older_than_days/within_days 的 value 是天数整数；枚举字段 value 必须从可选值中选；null/not_null/today 不需要 value；\n"
        "     日期字段的值必须是具体日期（YYYY-MM-DD），禁止 today/yesterday 等字面量——「等于今天」用 today 操作符，「过去一周/一个月」用 past_days 且 value=7/30\n"
        "   - llm 智能判断：条件是语义化、结构化条件表达不了时用，condition = {description: \"自然语言判断条件\"}\n"
        "2. schedule 执行周期：{type: \"cron\", expr: \"分 时 日 月 周\"}（如每天 9 点 = 0 9 * * *，每周一 9 点 = 0 9 * * 1）"
        "或 {type: \"interval\", minutes: 间隔分钟数}\n"
        "3. action 动作：\n"
        "   - type: notify 站内通知 / email 邮件 / sms 短信 / webhook\n"
        "   - template 通知内容模板，用 {字段名} 引用记录字段，如：客户【{customer_name}】已超期\n"
        "   - recipients 接收人：邮件/短信必填。{type: \"fixed\", value: \"邮箱或手机号，逗号分隔\"} 或 "
        "{type: \"field\", field: \"取记录里某个字段的值作为接收人\"}；用户没明确给出接收地址时 type 用 fixed、value 留空字符串\n"
        "4. cooldown_hours 同一记录冷却期（小时，默认 24；0 = 永不重复提醒同一条记录）\n"
        "5. name 给任务起个简洁的名字\n"
        "6. 只使用字段清单中存在的 field_name\n\n"
        f"输出 JSON 格式示例：\n{json.dumps(_TASK_OUTPUT_EXAMPLE, ensure_ascii=False, indent=2)}\n\n"
        "只输出 JSON。"
    )


REPORT_SYSTEM = (
    "你是报表设计专家。用户会给你一张数据表的字段清单和一句自然语言需求，"
    "你要设计出报表的时间口径和区块配置。只输出 JSON，不要输出任何其他内容。"
)

_REPORT_OUTPUT_EXAMPLE = {
    "name": "客户跟进周报",
    "range": {"mode": "last_week", "date_field": "created_at"},
    "blocks": [
        {"type": "stat", "title": "新增客户数", "agg": "count",
         "filters": {"logic": "AND", "rules": []}},
        {"type": "chart", "title": "客户分级分布", "chart_type": "pie",
         "group": {"kind": "field", "field": "customer_grade"}, "agg": "count",
         "filters": {"logic": "AND", "rules": []}},
        {"type": "chart", "title": "每日新增趋势", "chart_type": "line",
         "group": {"kind": "day", "field": "created_at"}, "agg": "count",
         "filters": {"logic": "AND", "rules": []}},
        {"type": "table", "title": "客户明细",
         "columns": ["customer_name", "customer_grade", "created_at"],
         "sort_by": "created_at", "sort_order": "desc", "limit": 100,
         "filters": {"logic": "AND", "rules": []}},
        {"type": "text", "title": "小结", "content": "{range_label}共新增 {b1} 条记录。"},
    ],
    "notes": "设计说明（可选）",
}


def build_report_prompt(description: str, fields: list[dict]) -> str:
    """把自然语言需求转成报表模板配置。fields: [{field_name, label, data_type, options}]"""
    field_desc = []
    for f in fields:
        item = {"field_name": f["field_name"], "含义": f["label"], "类型": f["data_type"]}
        opts = (f.get("options") or {}).get("options")
        if opts:
            item["可选值"] = opts
        field_desc.append(item)
    return (
        f"用户的报表需求：{description}\n\n"
        f"数据表字段（另有系统字段 id / created_at 创建时间 / updated_at 更新时间）：\n"
        f"{json.dumps(field_desc, ensure_ascii=False, indent=2)}\n\n"
        "报表配置规则：\n"
        "1. range.mode 时间口径：today 今天 / yesterday 昨天 / past_7d 近7天 / past_30d 近30天 / this_week 本周 / last_week 上周 / "
        "this_month 本月 / last_month 上月 / this_quarter 本季度 / this_year 今年；"
        "date_field 统计所依据的日期字段（默认 created_at，也可选业务日期字段）\n"
        "2. blocks 是区块数组，四种类型：\n"
        "   - stat 统计卡片：{type, title, agg, field, filters, compare}。agg: count 计数（不需要 field）/ count_distinct 去重计数（field 任意字段）/ "
        "sum / avg / max / min（field 必须是 int/decimal 字段）/ ratio 占比%（满足 filters 的记录数 ÷ 口径内总数，不需要 field）；"
        "compare: true 表示与等长上一期环比（如本周 vs 上周），需要对比时加上\n"
        "   - chart 图表：{type, title, chart_type, group, agg, field, filters, metrics?, group2?, stack?}。chart_type: bar 柱状 / line 折线 / area 面积 / pie 饼图；"
        "agg 同 stat 但不支持 ratio；"
        "group.kind: field 按字段分组（field 为分组字段，枚举字段最适合饼图）/ day / week / month 按时间分组（field 必须是日期字段）；"
        "多系列（饼图不支持，需要对比多个指标或拆分维度时才用）：metrics 多指标数组 [{agg, field, title}]（最多 5 个，用了它就不用顶层 agg/field），"
        "或 group2: {field} 二级分组（该字段每个取值一个系列，与 metrics 互斥，field 不能是日期字段）；"
        "stack: true 表示堆叠（仅 bar/line/area 且多系列时）\n"
        "   - table 明细表：{type, title, columns, sort_by, sort_order, limit, filters}。columns 是字段名数组，limit ≤ 500\n"
        "   - text 文本：{type, title, content}。content 支持占位符 {range_label} 时间范围、{b1} 引用第 1 个 stat 区块的值（按 blocks 中 stat 的顺序编号 b1、b2…）\n"
        "3. filters 为可选筛选：{logic: AND|OR, rules: [{field, op, value}]}。"
        "op 只能是 eq/ne/gt/gte/lt/lte/contains/startswith/in/null/not_null/today（当天）/past_days（过去 N 天含今天）/older_than_days/within_days；"
        "枚举字段的 value 必须从可选值中选；日期字段的值必须是具体日期（YYYY-MM-DD），禁止 today 等字面量——「等于今天」用 today 操作符，「过去一周/一个月」用 past_days 且 value=7/30\n"
        "4. 只使用字段清单中存在的 field_name；数值聚合只能用 int/decimal 字段\n"
        "5. 区块数量 2~6 个，按「统计卡片 → 图表 → 明细 → 文本小结」组织\n"
        "6. name 给报表起个简洁的名字\n\n"
        f"输出 JSON 格式示例：\n{json.dumps(_REPORT_OUTPUT_EXAMPLE, ensure_ascii=False, indent=2)}\n\n"
        "只输出 JSON。"
    )
