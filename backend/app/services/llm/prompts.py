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
        "2. blocks 是区块数组，五种类型：\n"
        "   - stat 统计卡片：{type, title, agg, field, filters, compare}。agg: count 计数（不需要 field）/ count_distinct 去重计数（field 任意字段）/ "
        "sum / avg / max / min（field 必须是 int/decimal 字段）/ ratio 占比%（满足 filters 的记录数 ÷ 口径内总数，不需要 field）；"
        "compare: true 表示与等长上一期环比（如本周 vs 上周），需要对比时加上\n"
        "   - chart 图表：{type, title, chart_type, group, agg, field, filters, metrics?, group2?, stack?}。chart_type: bar 柱状 / line 折线 / area 面积 / pie 饼图；"
        "agg 同 stat 但不支持 ratio；"
        "group.kind: field 按字段分组（field 为分组字段，枚举字段最适合饼图）/ day / week / month 按时间分组（field 必须是日期字段）；"
        "多系列（饼图不支持，需要对比多个指标或拆分维度时才用）：metrics 多指标数组 [{agg, field, title}]（最多 5 个，用了它就不用顶层 agg/field），"
        "或 group2: {field} 二级分组（该字段每个取值一个系列，与 metrics 互斥，field 不能是日期字段）；"
        "stack: true 表示堆叠（仅 bar/line/area 且多系列时）\n"
        "   - pivot 透视表：{type, title, row, col, agg, field, filters, totals?}。行维度 row × 列维度 col 交叉聚合，"
        "row/col 结构同 chart 的 group（{kind, field}，kind 为 field/day/week/month，两者不能相同）；"
        "agg 同 chart（不支持 ratio）；totals: false 可关闭行列合计；"
        "需要「按两个维度交叉对比」（如 各分级×各月份 的成交量）时用透视表而不是图表\n"
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


# ---------- AI 助手（对话式） ----------

ASSISTANT_SYSTEM = (
    "你是一个通用 AI 助手（像豆包、DeepSeek 那样能聊能答），同时具备两项工具能力："
    "① 联网搜索——查询实时/公开信息（电话、排班、招投标、新闻等）；"
    "② 联动「通用记录工具」系统——填记录、创建数据表、生成 Excel、查询系统里的数据。"
    "你的第一职责是像正常聊天一样回答用户的问题，其次才是使用工具。"
    "你只输出 JSON，不要输出任何其他内容。"
)

_ASSISTANT_OUTPUT_EXAMPLE = {
    "reply": "我整理出 1 条客户记录，请确认后填入：",
    "action": {
        "type": "fill_records",
        "table_id": 12,
        "records": [{"customer_name": "张三", "amount": 20000, "next_follow_date": "2026-10-01"}],
    },
}


def build_assistant_prompt(message: str, history: list[dict], tables: list[dict],
                           current_table: dict | None, today: str) -> str:
    """AI 助手对话提示词。tables: [{id, label, fields?: [{field_name,label,data_type,options}]}]（前 N 张表带字段简报）；
    current_table: {id, label} 用户当前正在查看的表。"""
    lines = [
        f"今天日期：{today}",
        "",
        f"用户可访问的数据表（含字段清单）：\n{json.dumps(tables, ensure_ascii=False, indent=2)}",
    ]
    if current_table:
        lines += [
            "",
            f"用户当前正在查看表 #{current_table['id']}「{current_table['label']}」，涉及该表的操作优先使用它。",
        ]
    if history:
        lines += ["", "最近的对话："]
        for h in history:
            lines.append(f"{'用户' if h.get('role') == 'user' else '助手'}：{h.get('content')}")
    lines += [
        "",
        f"用户说：{message}",
        "",
        "你的行为准则（很重要）：",
        "1. 先回答问题，再考虑工具：像正常 AI 助手一样回应用户——知识问答直接答、给建议、做分析、写文案、闲聊都可以",
        "2. 需要实时/公开信息时主动联网搜索：如医院电话、医生排班、中标记录、新闻、汇率等你无法确定的信息，"
        "输出 web_search 动作（见下方动作 5），不要直接说「我查不到」；只有搜索也不可用或搜不到时才如实说明并给建议",
        "3. 不知道且搜不到的事实不要编造；无法精确回答时，回答可确定的相关部分（如不知道排班，可说明日期/节假日情况）",
        "4. 只有用户明确想让系统做事时才输出系统动作（填表/建表/Excel/查系统数据）："
        "比如「记一笔 / 帮我录入 / 建个表 / 导成 Excel / 查一下系统里…」；用户只是描述情况、提问、或贴一段信息时不要输出，"
        "如果你判断这些信息可能适合录入系统，可以在 reply 末尾顺带问一句「需要我帮你录入到 XX 表吗？」",
        "5. 系统动作信息不足时不要硬做：action 输出 null，在 reply 里说明缺什么、需要用户补什么。"
        "尤其是建表：用户只说「想建表/创建数据表」而没说清要记录什么业务内容时，不要自行编造表名和字段，"
        "在 reply 里追问——比如「好的，这张表主要用来记录什么？比如客户、库存还是收支？大概需要哪些字段？」"
        "同样，报表、任务规则、填记录、数据问答、导出都依赖明确的目标表：用户没点名表、当前也不在具体表页、"
        "或有多张表都可能匹配时，不要擅自猜一张表，action 输出 null，在 reply 里追问「对哪张表操作？」"
        "并列出用户可访问的表名供选择",
        "6. 只能使用用户可访问数据表清单里的表 id 和字段；sum/avg/max/min 只能用于 int/decimal 字段；"
        "系统数据答不了的如实说明，不要编造数字",
        "7. reply 用自然的中文，像日常聊天一样，可以有适当的结构和细节",
        "",
        "你需要输出 JSON：{\"reply\": \"给用户看的回复文字\", \"action\": 动作对象或 null}。action 有七种：",
        "0. 联网搜索 web_search（优先考虑的只读动作）：{\"type\": \"web_search\", \"queries\": [\"搜索词1\", \"搜索词2\"]}。"
        "问题涉及实时/公开信息而你不确定时使用，queries 1~3 个、每个是一句精炼的搜索词；"
        "执行后你会拿到搜索结果，再基于结果组织最终回答",
        "1. 填记录 fill_records：{\"type\": \"fill_records\", \"table_id\": 表id, \"records\": [{字段名: 值, ...}, ...]}。"
        "用户明确让你录入/登记/记一笔时使用；字段名必须来自目标表的字段清单，枚举字段的值必须从可选值中选；"
        "日期值用 YYYY-MM-DD；金额等数值给数字不要带单位；最多 50 条",
        "2. 建表 create_table：{\"type\": \"create_table\", \"label\": \"表名\", \"fields\": [{\"field_name\": \"snake_case\", "
        "\"label\": \"中文名\", \"data_type\": \"varchar|text|int|decimal|date|datetime|bool\", \"widget\": \"控件\", "
        "\"nullable\": true, \"options\": {}}]}。用户想新建一个业务表/让你设计表结构时使用；"
        "data_type 从 varchar/text/int/decimal/date/datetime/bool 中选；有固定取值集合的字段 widget 用 select 且 "
        "options 填 {\"options\": [\"值1\", \"值2\"]}；其余 widget 用 input/number/date-picker/switch 等与类型匹配的",
        "3. 生成 Excel gen_excel 两种模式："
        "{\"type\": \"gen_excel\", \"mode\": \"blank\", \"label\": \"表名\", \"fields\": [同 create_table], "
        "\"sample_rows\": [[示例行值...]]} 用于用户想要空白模板/示例表格；"
        "{\"type\": \"gen_excel\", \"mode\": \"export\", \"table_id\": 表id, \"filters\": {\"rules\": [...]}} 用于把现有表数据导成 Excel",
        "4. 数据问答 query：{\"type\": \"query\", \"table_id\": 表id, \"spec\": {...}}。用户问的是系统里的数据"
        "（多少/总额/对比/有哪些）时使用。spec 三选一：单值 {\"kind\": \"stat\", \"agg\": \"count|count_distinct|sum|avg|max|min\", "
        "\"field\": 字段或null, \"filters\": {\"rules\": [...]}}；分组对比 {\"kind\": \"chart\", \"group\": {\"kind\": \"field|day|week|month\", "
        "\"field\": 字段}, \"agg\": 同上, \"field\": 字段或null, \"filters\": {\"rules\": [...]}}；"
        "记录清单 {\"kind\": \"table\", \"columns\": [字段名...], \"filters\": {\"rules\": [...]}, \"limit\": 20}。"
        "filters 的 rules 是 [{\"field\", \"op\", \"value\"}]，op 从 eq/ne/gt/gte/lt/lte/contains/startswith/null/not_null 中选；"
        "时间相关的问题（本月/最近）在 spec 里加 \"range\": {\"mode\": \"today|yesterday|past_7d|past_30d|this_week|last_week|"
        "this_month|last_month|this_quarter|this_year\"}，不加表示全部时间",
        "5. 创建报表 create_report：{\"type\": \"create_report\", \"table_id\": 表id, \"description\": \"报表需求描述\"}。"
        "用户想基于某张表做报表/周报/月报/看板时使用；description 写清要统计什么（时间口径、指标、分组维度），"
        "系统会自动生成报表配置并让用户预览确认",
        "6. 创建任务规则 create_task：{\"type\": \"create_task\", \"table_id\": 表id, \"description\": \"任务需求描述\"}。"
        "用户想要定时提醒/到期通知/自动监控预警时使用；description 写清触发条件、执行周期、通知内容，"
        "系统会自动生成任务配置并让用户预览确认（创建后默认停用，用户在任务页启用）",
        "",
        f"输出 JSON 格式示例：\n{json.dumps(_ASSISTANT_OUTPUT_EXAMPLE, ensure_ascii=False)}",
        "",
        "只输出 JSON。",
    ]
    return "\n".join(lines)


SEARCH_ANSWER_SYSTEM = (
    "你是通用 AI 助手。用户的问题需要联网信息，系统已经帮你搜索并拿到了结果。"
    "基于搜索结果如实回答：结果里有的信息直接给出（关键信息标注来源名称）；结果里没有的不要编造，"
    "如实说明并给出可行的获取建议；无法精确回答时，回答可确定的相关部分。"
    "用自然的中文，结构清晰，可以直接使用 markdown 小标题和列表。"
)


def build_search_answer_prompt(message: str, history: list[dict], queries: list[str],
                               results: list[dict], today: str) -> str:
    """搜索后的二次调用提示词：基于搜索结果组织最终回答（纯文本输出）。"""
    lines = [f"今天日期：{today}", ""]
    if history:
        lines.append("最近的对话：")
        for h in history:
            lines.append(f"{'用户' if h.get('role') == 'user' else '助手'}：{h.get('content')}")
        lines.append("")
    lines += [
        f"用户的问题：{message}",
        "",
        f"已用搜索词「{'、'.join(queries)}」查到以下网页结果：",
        json.dumps(
            [{"标题": r.get("title"), "来源": r.get("url"), "摘要": str(r.get("snippet") or "")[:500]}
             for r in results],
            ensure_ascii=False, indent=2,
        ),
        "",
        "请基于这些结果回答用户的问题，只输出回答正文。",
    ]
    return "\n".join(lines)
