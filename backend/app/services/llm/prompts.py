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
