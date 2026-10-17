"""智能表字段类型注册表（设计文档 §3）：12 种业务字段类型的后端单一事实来源。

每种类型注册：field_type 标识 → 底层 data_type/widget、默认 config、config 校验。
值存储约定：一律存 ID/原始标量不存展示值（选项存 optionId、人员存 userId、链接存 {url,text}）。
"""
from __future__ import annotations


class FieldTypeError(ValueError):
    """字段类型 config 校验失败（调用方按需包装为 MetaError/HTTPException）。"""


# 预设选项色板（单选/多选）
OPTION_COLORS = {
    "blue", "cyan", "green", "orange", "red", "purple", "pink", "yellow", "gray",
    "lightBlue", "lightGreen", "lightOrange", "lightPurple",
}
# 自动分配选项颜色时的取用顺序（默认选项/导入推断共用）
OPTION_COLOR_ORDER = ["blue", "green", "orange", "cyan", "red", "purple", "pink",
                      "yellow", "lightBlue", "lightGreen", "lightOrange", "lightPurple", "gray"]

# Excel 导入的单选启发式阈值：低基数短文本列 → 单选（对齐企业微信/飞书导入体验）
SELECT_MAX_OPTIONS = 50      # 去重值种类上限
SELECT_MAX_RATIO = 0.5       # 去重值数 / 非空行数 上限（全唯一的列不算枚举）
SELECT_MAX_LABEL_LEN = 30    # 单个选项文案长度上限（长文本不算枚举）


def infer_select_options(values: list) -> list[dict] | None:
    """低基数文本列 → 单选选项列表（按出现频次降序）；不满足启发式返回 None（该列按文本处理）。
    调用方应传入全量数据行（而非 50 行样本），保证样本外的取值也有选项可映射。"""
    from collections import Counter
    vals = [str(v).strip() for v in values if v is not None and str(v).strip()]
    if len(vals) < 2:
        return None
    if max(len(v) for v in vals) > SELECT_MAX_LABEL_LEN:
        return None
    freq = Counter(vals)
    if not (2 <= len(freq) <= SELECT_MAX_OPTIONS):
        return None
    if len(freq) / len(vals) > SELECT_MAX_RATIO:
        return None
    return [
        {"id": f"opt_{i + 1}", "label": label,
         "color": OPTION_COLOR_ORDER[i % len(OPTION_COLOR_ORDER)], "order": i}
        for i, (label, _) in enumerate(freq.most_common(SELECT_MAX_OPTIONS))
    ]

CURRENCY_CODES = {"CNY": "￥", "USD": "$", "EUR": "€", "JPY": "¥", "HKD": "HK$", "GBP": "£"}

DATE_FORMATS = ["yyyy-MM-dd", "yyyy/MM/dd", "yyyy年M月d日", "yyyy-MM-dd HH:mm", "yyyy年M月d日 HH:mm"]

ROW_HEIGHTS = {"default", "medium", "tall", "extraTall"}

# 视图筛选运算符（设计文档 §5.1），按字段类型族分发
OP_TEXT = ["contains", "notContains", "eq", "neq", "isEmpty", "isNotEmpty"]
OP_NUMBER = ["eq", "neq", "gt", "gte", "lt", "lte", "isEmpty", "isNotEmpty"]
OP_ENUM = ["contains", "notContains", "eq", "neq", "isEmpty", "isNotEmpty"]
OP_DATE = ["eq", "neq", "gt", "gte", "lt", "lte", "today", "pastDays", "withinDays", "isEmpty", "isNotEmpty"]
OP_BOOL = ["eq", "isEmpty", "isNotEmpty"]


def _num_config(precision="default", thousand=False, **extra):
    return {"precision": precision, "thousandSeparator": thousand, **extra}


# field_type → 注册项
FIELD_TYPES: dict[str, dict] = {
    "text": {
        "label": "文本", "data_type": "varchar", "widget": "input",
        "default_config": {}, "filter_ops": OP_TEXT, "aggregations": ["count"],
    },
    "singleSelect": {
        "label": "单选", "data_type": "varchar", "widget": "select",
        "default_config": {"options": [], "allowAddOptionWhenEditing": True},
        "filter_ops": OP_ENUM, "aggregations": ["count"],
    },
    "multiSelect": {
        "label": "多选", "data_type": "json", "widget": "select",
        "default_config": {"options": [], "allowAddOptionWhenEditing": True},
        "filter_ops": OP_ENUM, "aggregations": ["count"],
    },
    "number": {
        "label": "数字", "data_type": "decimal", "widget": "number",
        "default_config": _num_config(), "filter_ops": OP_NUMBER,
        "aggregations": ["count", "sum", "avg", "max", "min"],
    },
    "percent": {
        "label": "百分数", "data_type": "decimal", "widget": "number",
        "default_config": _num_config(), "filter_ops": OP_NUMBER,
        "aggregations": ["count", "sum", "avg", "max", "min"],
    },
    "currency": {
        "label": "货币", "data_type": "decimal", "widget": "number",
        "default_config": {"currencyCode": "CNY", "currencySymbol": "￥", "precision": 2, "thousandSeparator": True},
        "filter_ops": OP_NUMBER, "aggregations": ["count", "sum", "avg", "max", "min"],
    },
    "date": {
        "label": "日期", "data_type": "datetime", "widget": "datetime-picker",
        "default_config": {"format": "yyyy-MM-dd", "includeTime": False, "autoFillCreatedTime": False},
        "filter_ops": OP_DATE, "aggregations": ["count", "max", "min"],
    },
    "checkbox": {
        "label": "复选框", "data_type": "bool", "widget": "switch",
        "default_config": {"defaultChecked": False},
        "filter_ops": OP_BOOL, "aggregations": ["count"],
    },
    "url": {
        "label": "链接", "data_type": "json", "widget": "input",
        "default_config": {"displayStyle": "iconText"},
        "filter_ops": OP_TEXT, "aggregations": ["count"],
    },
    "phone": {
        "label": "电话", "data_type": "varchar", "widget": "input",
        "default_config": {}, "filter_ops": OP_TEXT, "aggregations": ["count"],
    },
    "email": {
        "label": "邮箱", "data_type": "varchar", "widget": "input",
        "default_config": {}, "filter_ops": OP_TEXT, "aggregations": ["count"],
    },
    "member": {
        "label": "人员", "data_type": "json", "widget": "input",
        "default_config": {"multiple": True, "notifyOnAdd": True},
        "filter_ops": OP_ENUM, "aggregations": ["count"],
    },
    # ---------- V2：数据组织能力 ----------
    "progress": {
        "label": "进度", "data_type": "decimal", "widget": "number",
        "default_config": {"color": "green", "numberFormat": "value", "precision": "default",
                           "range": {"min": 0, "max": 100}, "showNumber": True},
        "filter_ops": OP_NUMBER, "aggregations": ["count", "sum", "avg", "max", "min"],
    },
    "image": {
        "label": "图片", "data_type": "image", "widget": "image-uploader",
        "default_config": {"cameraOnly": False},
        "filter_ops": ["isEmpty", "isNotEmpty"], "aggregations": ["count"],
    },
    "file": {
        "label": "文件", "data_type": "json", "widget": "input",
        "default_config": {},
        "filter_ops": ["isEmpty", "isNotEmpty"], "aggregations": ["count"],
    },
    "autoNumber": {
        "label": "自动编号", "data_type": "serial", "widget": "serial",
        # segments → options.serial.pattern（自增段 {000}、固定字符、创建日期 {YYYY}{MM}{DD}）
        "default_config": {"numberType": "autoIncrement", "segments": [{"type": "autoIncrement", "digits": 3}]},
        "filter_ops": OP_TEXT, "aggregations": ["count"], "readonly": True,
    },
    "relation": {
        "label": "关联", "data_type": "json", "widget": "input",
        "default_config": {"targetTableId": None, "multiple": True, "bidirectional": False},
        "filter_ops": OP_ENUM, "aggregations": ["count"],
    },
    "lookup": {
        "label": "查找引用", "data_type": "json", "widget": "input",
        "default_config": {"sourceTableId": None, "sourceFieldId": None, "conditionLogic": "and",
                           "conditions": [], "aggregation": "raw"},
        "filter_ops": ["isEmpty", "isNotEmpty"], "aggregations": ["count"],
        "readonly": True, "computed": True,   # 读时计算，不落库、不可写
    },
    "formula": {
        "label": "公式", "data_type": "varchar", "widget": "input",
        # 表达式存 options.formula（复用 expr.py 引擎 + apply_computed 写时重算）
        "default_config": {"formula": "", "returnType": "text"},
        "filter_ops": OP_TEXT, "aggregations": ["count"],
        "readonly": True,
    },
    # ---------- V3：AI 字段（设计文档 §10）：场景模板 + 输入字段 → 输出类型；由 AI 服务异步回写 ----------
    "ai": {
        "label": "AI 字段", "data_type": "json", "widget": "input",
        "default_config": {"scene": "custom", "inputFields": [], "prompt": "", "outputType": "text",
                           "options": [], "autoUpdate": True, "allowNewOptions": True},
        "filter_ops": OP_TEXT, "aggregations": ["count"], "readonly": True,
    },
    # 系统字段：值来自记录系统列（owner_id/updated_by/created_at/updated_at），不可写
    "createdBy": {
        "label": "创建人", "data_type": "varchar", "widget": "input", "sys_key": "owner_id",
        "default_config": {}, "filter_ops": OP_ENUM, "aggregations": ["count"], "readonly": True, "system": True,
    },
    "lastModifiedBy": {
        "label": "最后编辑人", "data_type": "varchar", "widget": "input", "sys_key": "updated_by",
        "default_config": {}, "filter_ops": OP_ENUM, "aggregations": ["count"], "readonly": True, "system": True,
    },
    "createdTime": {
        "label": "创建时间", "data_type": "datetime", "widget": "datetime-picker", "sys_key": "created_at",
        "default_config": {"format": "yyyy-MM-dd"}, "filter_ops": OP_DATE, "aggregations": ["count"],
        "readonly": True, "system": True,
    },
    "lastModifiedTime": {
        "label": "最后编辑时间", "data_type": "datetime", "widget": "datetime-picker", "sys_key": "updated_at",
        "default_config": {"format": "yyyy-MM-dd"}, "filter_ops": OP_DATE, "aggregations": ["count"],
        "readonly": True, "system": True,
    },
}

# 数字家族无损互转（共享 decimal 存储）
NUMBER_FAMILY = {"number", "percent", "currency"}


def default_config(field_type: str) -> dict:
    reg = FIELD_TYPES.get(field_type)
    return dict(reg["default_config"]) if reg else {}


def validate_field_type_config(field_type: str, config: dict, label: str = "") -> None:
    """按 field_type 校验 options 中的 config（建/改字段时把关）。非法抛 FieldTypeError。"""
    reg = FIELD_TYPES.get(field_type)
    if reg is None:
        raise FieldTypeError(f"字段「{label}」的字段类型不支持：{field_type}")
    cfg = config or {}
    prefix = f"字段「{label}」"

    if field_type in ("singleSelect", "multiSelect"):
        opts = cfg.get("options")
        if opts is not None:
            if not isinstance(opts, list):
                raise FieldTypeError(f"{prefix}的选项配置必须是数组")
            seen = set()
            for o in opts:
                if not isinstance(o, dict) or not o.get("id") or not str(o.get("label") or "").strip():
                    raise FieldTypeError(f"{prefix}的选项必须包含 id 和 label")
                if o["id"] in seen:
                    raise FieldTypeError(f"{prefix}的选项 id 重复：{o['id']}")
                seen.add(o["id"])
                if o.get("color") and o["color"] not in OPTION_COLORS:
                    raise FieldTypeError(f"{prefix}的选项颜色不支持：{o['color']}")
        # 引用选项（设计文档 §3.3）：optionSource=reference 时选项集来自他表 select 字段
        source = cfg.get("optionSource", "manual")
        if source not in ("manual", "reference"):
            raise FieldTypeError(f"{prefix}的选项来源不支持：{source}")
        if source == "reference":
            ref = cfg.get("reference") or {}
            if not ref.get("tableId") or not ref.get("fieldId"):
                raise FieldTypeError(f"{prefix}引用选项必须选择引用的表和字段")
        # 选项联动（级联下拉）：本表行字段值 vs 引用表行字段值，一期仅「等于」
        linkage = cfg.get("optionLinkage")
        if linkage is not None:
            if source != "reference":
                raise FieldTypeError(f"{prefix}的选项联动仅在引用选项模式下可用")
            if not isinstance(linkage, dict):
                raise FieldTypeError(f"{prefix}的选项联动配置必须是对象")
            if linkage.get("match", "all") not in ("all", "any"):
                raise FieldTypeError(f"{prefix}的联动满足方式仅支持 all/any")
            for c in linkage.get("conditions") or []:
                if not isinstance(c, dict) or not c.get("localFieldId") or not c.get("remoteFieldId"):
                    raise FieldTypeError(f"{prefix}的联动条件必须包含本表字段和引用表字段")
                if c.get("operator", "eq") != "eq":
                    raise FieldTypeError(f"{prefix}的联动条件一期仅支持「等于」")

    if field_type in NUMBER_FAMILY:
        prec = cfg.get("precision", "default")
        if prec != "default" and not (isinstance(prec, int) and 0 <= prec <= 10):
            raise FieldTypeError(f"{prefix}的小数位数必须是 default 或 0~10")
        if field_type == "currency" and cfg.get("currencyCode", "CNY") not in CURRENCY_CODES:
            raise FieldTypeError(f"{prefix}的币种不支持：{cfg.get('currencyCode')}")

    if field_type == "date":
        fmt = cfg.get("format", "yyyy-MM-dd")
        if fmt not in DATE_FORMATS:
            raise FieldTypeError(f"{prefix}的日期格式不支持：{fmt}")

    if field_type == "member":
        for k in ("multiple", "notifyOnAdd"):
            if k in cfg and not isinstance(cfg[k], bool):
                raise FieldTypeError(f"{prefix}的 {k} 必须是布尔值")

    # ---------- V2 类型校验 ----------
    if field_type == "progress":
        rng = cfg.get("range") or {}
        if not isinstance(rng.get("min", 0), (int, float)) or not isinstance(rng.get("max", 100), (int, float)):
            raise FieldTypeError(f"{prefix}的进度条范围无效")
        if rng.get("max", 100) <= rng.get("min", 0):
            raise FieldTypeError(f"{prefix}的进度条最大值必须大于最小值")

    if field_type == "autoNumber":
        segs = cfg.get("segments") or []
        if cfg.get("numberType") == "custom" and not segs:
            raise FieldTypeError(f"{prefix}自定义编号至少需要一个编号段")
        if not any(s.get("type") == "autoIncrement" for s in segs) and cfg.get("numberType") == "custom":
            raise FieldTypeError(f"{prefix}自定义编号必须包含一个自增数字段")

    if field_type == "relation":
        if not cfg.get("targetTableId"):
            raise FieldTypeError(f"{prefix}必须选择关联的智能表")

    if field_type == "lookup":
        if not cfg.get("sourceTableId") or not cfg.get("sourceFieldId"):
            raise FieldTypeError(f"{prefix}必须选择要引用的表和字段")
        if cfg.get("aggregation", "raw") not in LOOKUP_AGGS:
            raise FieldTypeError(f"{prefix}的统计方式不支持：{cfg.get('aggregation')}")

    if field_type == "ai":
        if cfg.get("outputType", "text") not in AI_OUTPUT_TYPES:
            raise FieldTypeError(f"{prefix}的输出类型不支持：{cfg.get('outputType')}")
        if not isinstance(cfg.get("inputFields", []), list):
            raise FieldTypeError(f"{prefix}的输入字段必须是数组")
        # 自定义场景：新版配置的提示词在 systemPrompt（AI 配置生成），旧版在 prompt（模板），有其一即可
        if cfg.get("scene", "custom") == "custom" and not (
                str(cfg.get("systemPrompt") or "").strip() or str(cfg.get("prompt") or "").strip()):
            raise FieldTypeError(f"{prefix}的自定义提示词不能为空")

    if field_type == "formula":
        expr = (cfg.get("formula") or "").strip()
        if not expr:
            raise FieldTypeError(f"{prefix}的公式内容不能为空")


def default_sheet_fields() -> list[dict]:
    """新建工作表的默认字段模板（设计文档 §2.5：文本/单选/人员/数字/日期）。"""
    return [
        {"field_type": "text", "label": "文本"},
        {"field_type": "singleSelect", "label": "单选",
         "config": {"options": [{"id": "opt_1", "label": "选项1", "color": "blue", "order": 0},
                                {"id": "opt_2", "label": "选项2", "color": "green", "order": 1},
                                {"id": "opt_3", "label": "选项3", "color": "orange", "order": 2}],
                    "allowAddOptionWhenEditing": True}},
        {"field_type": "member", "label": "人员"},
        {"field_type": "number", "label": "数字"},
        {"field_type": "date", "label": "日期"},
    ]


def to_field_in(field_type: str, label: str, field_name: str, config: dict | None = None) -> dict:
    """注册项 → FieldIn 字典（建表/加字段用）。
    autoNumber：segments → options.serial.pattern；formula：config.formula → options.formula（复用 expr.py 引擎）。"""
    reg = FIELD_TYPES[field_type]
    cfg = config if config is not None else default_config(field_type)
    options = dict(cfg)
    if field_type == "autoNumber":
        options["serial"] = {"pattern": autonumber_segments_to_pattern(cfg.get("segments")),
                             "reset": "never", "allow_manual": False}
    if field_type == "formula":
        options["formula"] = cfg.get("formula", "")
    return {
        "field_name": field_name, "label": label,
        "data_type": reg["data_type"], "widget": reg["widget"],
        "options": options,
        "field_type": field_type,
    }


def gen_field_name(existing: set[str]) -> str:
    """json 模式下 field_name 仅为 data 键：f_1 / f_2 … 递增。"""
    n = 1
    while f"f_{n}" in existing:
        n += 1
    return f"f_{n}"


# ---------- V2 补充常量与帮助函数 ----------

# 只读/系统/读时计算字段：写入时一律忽略（防提交污染）
READONLY_TYPES = {ft for ft, reg in FIELD_TYPES.items() if reg.get("readonly")}
SYSTEM_TYPES = {ft for ft, reg in FIELD_TYPES.items() if reg.get("system")}
COMPUTED_TYPES = {"formula", "lookup"}

# AI 字段输出类型（V3）
AI_OUTPUT_TYPES = {"text", "number", "singleSelect", "multiSelect", "checkbox"}

# 查找引用统计方式（设计文档 §8.2）
LOOKUP_AGGS = {"raw", "rawDistinct", "sum", "count", "countDistinct", "avg", "max", "min"}


def autonumber_segments_to_pattern(segments: list) -> str:
    """自定义编号段 → serial pattern。自增段 {000}（位数补零）、固定字符原样、创建日期 {YYYY}{MM}{DD}。"""
    parts = []
    for seg in segments or []:
        t = seg.get("type")
        if t == "autoIncrement":
            parts.append("{" + "0" * int(seg.get("digits", 3)) + "}")
        elif t == "fixedText":
            parts.append(str(seg.get("text") or ""))
        elif t == "createDate":
            fmt = seg.get("format", "yyyyMMdd")
            parts.append({"yyyyMMdd": "{YYYY}{MM}{DD}", "yyyy-MM-dd": "{YYYY}-{MM}-{DD}",
                          "yyyyMM": "{YYYY}{MM}", "yyyy": "{YYYY}"}.get(fmt, "{YYYY}{MM}{DD}"))
    return "".join(parts) or "{000}"
