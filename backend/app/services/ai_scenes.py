"""智能表 AI 字段场景市场（设计文档 §10.1，对齐参照 docs/智慧表格/添加列/AI字段）。

一个场景 = 说明（desc，{input} 处渲染为输入字段 chip）+ 默认提示词（你是… / 任务… / 输入…）
+ 输出类型 + 输入类型（text 任意列 / multi 多列 / image 图片列 / file 文件列）。
- local=True：本地确定性计算，不调用大模型、不计配额；
- disabled=True：需要工具调用（联网查询 / 图像编辑等），市场里展示为「即将上线」；
- sample：详情卡「效果」示例表（参照图同款示例数据）。
"""
from __future__ import annotations

CATEGORIES = [
    {"key": "recommend", "label": "推荐", "icon": "star"},
    {"key": "project", "label": "项目管理", "icon": "kanban"},
    {"key": "customer", "label": "客户管理", "icon": "comment"},
    {"key": "extract", "label": "信息提取", "icon": "text"},
    {"key": "convert", "label": "数据转换", "icon": "formula"},
    {"key": "file", "label": "文件解析", "icon": "file"},
    {"key": "image", "label": "图像处理", "icon": "image"},
    {"key": "hr", "label": "人事行政", "icon": "member"},
    {"key": "marketing", "label": "市场营销", "icon": "chart-bar"},
    {"key": "production", "label": "生产制造", "icon": "wand"},
    {"key": "store", "label": "门店管理", "icon": "view-grid"},
    {"key": "logistics", "label": "订单物流", "icon": "location"},
    {"key": "finance", "label": "财务会计", "icon": "currency"},
]

ROLES = {
    "recommend": "专业的数据处理助手", "project": "经验丰富的项目经理", "customer": "资深的销售顾问",
    "extract": "专业的信息提取助手", "convert": "严谨的数据转换助手", "file": "专业的文档解析助手",
    "image": "专业的图像处理助手", "hr": "专业的人事行政助手", "marketing": "资深的市场营销专家",
    "production": "经验丰富的生产管理专家", "store": "专业的门店运营助手", "logistics": "专业的物流订单助手",
    "finance": "专业的财务会计助手",
}
INPUT_DESC = {"text": "待处理的内容 为单条文本。", "multi": "本行相关字段的内容，每行一个「字段名：值」。",
              "image": "待分析的图片文件。", "file": "待解析的文件（已转为文本）。"}

SCENES: list[dict] = []


def S(key, label, cat, out, inp, task, desc=None, prompt=None, **kw):
    """登记场景：未写 prompt/desc 时按「角色 + 任务 + 输入」模板生成。"""
    if prompt is None:
        prompt = f"你是一个{ROLES.get(cat, '专业的数据处理助手')}。\n任务：{task}\n输入：{INPUT_DESC[inp]}"
    if desc is None:
        t = task.rstrip("。")
        desc = f"根据 {{input}} 的内容，{t}。" if inp != "image" else f"识别 {{input}} 中的图片，{t}。"
    SCENES.append({"key": key, "label": label, "category": cat, "outputType": out, "input": inp,
                   "desc": desc, "prompt": prompt, **kw})


# ---------- 推荐（参照图同款说明 / 提示词 / 效果示例） ----------
S("classify", "分类", "recommend", "singleSelect", "text", "对输入的文本内容进行自动分类，输出最匹配的分类标签。",
  desc="根据 {input} 内容自动匹配预设分类，若无法匹配则生成新的合理分类值。",
  prompt="你是一个文本分类专家。\n任务：对输入的文本内容进行自动分类，输出最匹配的分类标签。\n输入：待分类的文本内容 为单条文本。",
  sample={"in": "文本", "inType": "text", "out": "分类结果", "rows": [
      ["这是一段文本对应分类1", "分类1"], ["这是一段文本对应分类2", "分类2"], ["这是一段关于其他内容的文本", "分类4"]]})
S("summary", "总结", "recommend", "text", "multi", "对提供的文本内容进行智能总结，提取核心信息。",
  desc="对长文本内容进行智能总结，提取核心信息。",
  prompt="你是一个专业的文本总结助手。\n任务：对提供的文本内容进行智能总结，提取核心信息。\n输入：待总结内容 列包含需要总结的长文本内容。",
  sample={"in": "文本", "inType": "text", "out": "文本总结", "rows": [
      ["这是一段长文本1", "总结1"], ["这是一段长文本2", "总结2"], ["这是一段长文本3", "总结3"]]})
S("tagMatch", "标签匹配", "recommend", "multiSelect", "text", "根据输入的文本内容，判断其最匹配的分类标签。",
  desc="根据 {input} 列的内容，自动匹配合适的分类标签。",
  prompt="你是一个文本分类专家。\n任务：根据输入的文本内容，判断其最匹配的分类标签。\n输入：待分类的文本 为一段描述性文字。",
  sample={"in": "文本", "inType": "text", "out": "匹配标签", "rows": [
      ["翠林晨曦：阳光如碎金洒落林间", "自然风光"], ["古镇烟雨：青石板路蜿蜒", "人文景观"], ["荒漠长烟：金色的沙丘起伏", "自然风光"]]})
S("extract", "信息提取", "recommend", "text", "text", "从文本中提取关键有效信息，生成简洁的摘要。",
  desc="从文本中自动提取关键有效信息，生成简洁的摘要。",
  prompt="你是一个专业的信息提取助手。\n任务：从文本中提取关键有效信息，生成简洁的摘要。\n输入：待提取的文本列包含需要处理的文本内容。",
  sample={"in": "文本", "inType": "text", "out": "信息摘要", "rows": [
      ["这是一段很长的信息内容……", "核心要点提取"], ["关于项目进展的详细描述……", "项目进展：需求分析完成"]]})
S("imageUnderstand", "图片理解", "recommend", "text", "image", "全面理解并描述图片中的视觉内容。",
  desc="自动识别并理解图片中的视觉内容，适用于各类图片场景的智能分析。",
  prompt="你是一个专业的图像理解助手。\n任务：全面理解并描述图片中的视觉内容。\n输入：待分析的图像文件列包含需要分析的图片文件。",
  sample={"in": "图片", "inType": "image", "out": "图片理解", "rows": [
      ["", "这是一张办公室环境的照片"], ["", "图片展示了一个会议场景"], ["", "这是一张数据图表，展示季度趋势"]]})
S("translate", "翻译为中文", "recommend", "text", "text", "将英文文本准确翻译为中文。",
  desc="将英文文本内容翻译为中文。",
  prompt="你是一个专业的翻译助手。\n任务：将英文文本准确翻译为中文。\n输入：待翻译的英文文本 列包含需要翻译的英文内容。",
  sample={"in": "这是一段英文", "inType": "text", "out": "中文翻译", "rows": [
      ["This is an English paragraph", "这是一个英文段落"], ["Hello world", "你好世界"], ["Artificial Intelligence", "人工智能"]]})
S("markDuplicate", "标记重复值", "recommend", "checkbox", "text", "当值与其他记录重复时自动勾选。",
  desc="{input} 列的值与其他记录重复时自动勾选。", local=True,
  sample={"in": "手机号", "inType": "text", "out": "是否重复", "rows": [
      ["13800000001", True], ["13900000002", False], ["13800000001", True]]})
S("qrcode", "生成二维码图片", "recommend", "text", "text", "根据内容生成二维码图片。", disabled=True)
S("fxLive", "查询实时汇率", "recommend", "number", "text", "查询币种的实时汇率。", disabled=True)
S("fxHistory", "查询历史汇率", "recommend", "number", "multi", "按日期查询币种的历史汇率。", disabled=True)
S("writeFormula", "写公式", "recommend", "text", "multi", "用自然语言描述计算规则，AI 生成公式列。",
  desc="用自然语言描述计算规则，AI 帮你写出公式并添加公式列。", action="formula")
S("pdfToText", "PDF 转文本", "recommend", "text", "file", "提取 PDF 文件中的文字内容。",
  desc="提取 {input} 中 PDF 文件的文字内容。", local=True)

# ---------- 项目管理 ----------
S("workdays", "计算工作日天数", "project", "number", "multi",
  "根据开始与结束日期，计算之间的工作日天数（周一至周五，含首尾），只返回数字。")
S("projectProgress", "总结项目进度", "project", "text", "multi", "用一句话总结项目当前进度，并指出主要风险（如有）。")
S("taskStatus", "判断任务状态", "project", "singleSelect", "multi", "根据任务信息判断其当前状态。",
  defaultOptions=["未开始", "进行中", "已完成", "已延期"])
S("deadlineCountdown", "任务截止倒计时", "project", "text", "multi",
  "根据截止日期与今天（{today}）的差距，输出如「剩余 3 天」「已逾期 2 天」的描述。")
S("memberTaskCount", "计算成员任务数", "project", "number", "multi", "统计负责人承担的任务数量，只返回数字。")
S("memberWorkload", "计算成员工作量", "project", "singleSelect", "multi", "评估成员工作量是否饱和。",
  defaultOptions=["饱和", "适中", "空闲"])
S("riskLevel", "评估项目风险", "project", "singleSelect", "multi", "根据项目信息评估风险等级。",
  defaultOptions=["高风险", "中风险", "低风险"])
S("weeklyReport", "生成周报摘要", "project", "text", "multi", "根据工作记录生成 100 字以内的周报摘要。")

# ---------- 客户管理 ----------
S("customerIntent", "判断客户意向", "customer", "singleSelect", "multi", "根据跟进记录判断客户的购买意向等级。",
  defaultOptions=["高意向", "中意向", "低意向", "无意向"])
S("followSummary", "总结跟进记录", "customer", "text", "multi", "总结跟进记录的要点，并给出下一步行动建议（一句话）。")
S("customerProfile", "生成客户画像", "customer", "text", "multi", "根据客户信息生成 50 字以内的客户画像。")
S("customerLevel", "客户分级", "customer", "singleSelect", "multi", "根据客户规模、成交金额等信息给客户分级。",
  defaultOptions=["A 类", "B 类", "C 类"])
S("followReminder", "生成跟进话术", "customer", "text", "multi", "根据客户情况生成一段礼貌、简短的跟进话术。")
S("churnRisk", "判断流失风险", "customer", "singleSelect", "multi", "根据跟进与成交情况判断客户流失风险。",
  defaultOptions=["高", "中", "低"])

# ---------- 信息提取 ----------
for k, lb, out, inp, task in [
    ("exCity", "提取城市", "text", "text", "从文本中提取城市名称，找不到时返回空。"),
    ("exEmail", "提取邮箱", "text", "text", "从文本中提取邮箱地址，多个用逗号分隔，找不到时返回空。"),
    ("exLink", "提取链接", "text", "text", "从文本中提取网址链接，多个用逗号分隔，找不到时返回空。"),
    ("exImageText", "提取图片中的文字", "text", "image", "识别并提取图片中的全部文字，保持原有段落。"),
    ("exJson", "提取 JSON 中的值", "text", "text", "从 JSON 文本中提取需要的字段值。"),
    ("exAddress", "提取地址", "text", "text", "从文本中提取完整的地址信息。"),
    ("exAmount", "提取金额", "number", "text", "从文本中提取金额数值（只要数字），找不到时返回空。"),
    ("exFirstNumber", "提取首个数字", "number", "text", "提取文本中出现的第一个数字。"),
    ("exName", "提取姓名", "text", "text", "从文本中提取人名，多个用逗号分隔。"),
    ("exDate", "提取日期", "text", "text", "从文本中提取日期，统一格式为 YYYY-MM-DD。"),
    ("cardRecognize", "名片识别", "text", "image", "识别名片，按「姓名 / 公司 / 职位 / 电话 / 邮箱」逐行输出，缺失项留空。"),
    ("addressParse", "地址拆分", "text", "text", "把地址拆分为「省 / 市 / 区 / 详细地址」，用 / 分隔。"),
    ("contactExtract", "提取联系方式", "text", "text", "从文本中提取所有手机号与邮箱，用逗号分隔。"),
]:
    S(k, lb, "extract", out, inp, task)

# ---------- 数据转换（可确定计算的走本地，不耗配额） ----------
for k, lb, out, inp, task, extra in [
    ("cvHoliday", "判断是否节假日", "checkbox", "text", "判断日期是否为中国法定节假日或周末。", {}),
    ("cvMonthEnd", "判断是否月末", "checkbox", "text", "判断日期是否为当月最后一天。", {"local": True}),
    ("cvRandom", "生成随机数(1-100)", "number", "text", "为每行生成一个 1 到 100 之间的随机整数。", {"local": True}),
    ("cvMileKm", "英里转换公里", "number", "text", "把英里数换算为公里（1 英里 = 1.609344 公里），保留两位小数。", {"local": True}),
    ("cvRmbUpper", "转人民币大写金额", "text", "text", "把金额转换为人民币大写，如「壹佰元整」。", {"local": True}),
    ("cvBmi", "计算 BMI", "number", "multi", "根据身高与体重计算 BMI（体重kg / 身高m²），保留一位小数。", {}),
    ("cvBmr", "计算基础代谢率", "number", "multi", "根据性别、年龄、身高、体重按 Mifflin-St Jeor 公式计算基础代谢率（千卡）。", {}),
    ("cvUuid", "生成随机 UUID", "text", "text", "为每行生成一个随机 UUID。", {"local": True}),
    ("cvPassword", "生成高强度密码", "text", "text", "生成 16 位包含大小写字母、数字与符号的随机密码。", {"local": True}),
    ("cvHexRgb", "HEX 颜色转 RGB", "text", "text", "把 #RRGGBB 颜色值转换为 rgb(r, g, b)。", {"local": True}),
    ("cvMonthDays", "计算当月天数", "number", "text", "计算日期所在月份的天数。", {"local": True}),
    ("cvWordCount", "计算文本字数", "number", "text", "统计文本的字符数（不含空白）。", {"local": True}),
    ("cvB64Enc", "Base64 编码", "text", "text", "把文本进行 Base64 编码。", {"local": True}),
    ("cvB64Dec", "Base64 解码", "text", "text", "把 Base64 文本解码为原文。", {"local": True}),
    ("cvDateUnix", "日期转UNIX时间戳", "number", "text", "把日期时间转换为 UNIX 时间戳（秒）。", {"local": True}),
    ("cvUnixDate", "UNIX时间戳转日期", "text", "text", "把 UNIX 时间戳转换为 YYYY-MM-DD HH:mm:ss。", {"local": True}),
    ("cvLunar", "公历转农历", "text", "text", "把公历日期转换为农历日期，如「甲辰年 正月初一」。", {}),
    ("cvPinyin", "汉字转拼音", "text", "text", "把汉字转换为带声调的拼音，字与字之间用空格分隔。", {}),
]:
    S(k, lb, "convert", out, inp, task, **extra)

# ---------- 文件解析（PDF 先转文本再交给模型） ----------
for k, lb, out, task, extra in [
    ("fiInvoice", "识别发票信息", "text", "识别发票，输出「发票号码 / 开票日期 / 购买方 / 销售方 / 价税合计」。", {}),
    ("fiContractDue", "提取合同到期时间", "text", "提取合同的到期日期，格式 YYYY-MM-DD。", {}),
    ("fiResume", "生成简历摘要", "text", "根据简历生成 80 字以内的候选人摘要。", {}),
    ("fiEducation", "提取最高学历", "singleSelect", "提取简历中的最高学历。",
     {"defaultOptions": ["博士", "硕士", "本科", "大专", "其他"]}),
    ("fiPdfImage", "PDF 转图片", "text", "把 PDF 每页转为图片。", {"disabled": True}),
    ("fiPdfWatermark", "PDF 加水印", "text", "为 PDF 添加水印。", {"disabled": True}),
    ("fiImagePdf", "图片转 PDF", "text", "把图片合成为 PDF。", {"disabled": True}),
    ("fiDocxImage", "DOCX 转图片", "text", "把 DOCX 文档转为图片。", {"disabled": True}),
]:
    S(k, lb, "file", out, "file", task, **extra)

# ---------- 图像处理（需图像编辑能力） ----------
for k, lb in [("imWatermarkDel", "去除图片水印"), ("imWatermarkAdd", "添加图片水印"), ("imSolidBg", "替换为纯色背景"),
              ("imRemoveBg", "移除图片背景"), ("imSharpen", "提升清晰度"), ("imIdPhoto", "生成白底证件照")]:
    S(k, lb, "image", "text", "image", f"{lb}。", disabled=True)

# ---------- 人事行政 ----------
for k, lb, out, inp, task, extra in [
    ("hrAge", "计算人员当前年龄", "number", "text", "根据出生日期与今天（{today}）计算周岁年龄，只返回数字。", {}),
    ("hrSeniority", "计算员工工龄", "number", "text", "根据入职日期与今天（{today}）计算工龄（年，保留一位小数）。", {}),
    ("hrHistory", "提取工作履历", "text", "multi", "提取工作履历，按「时间 公司 职位」逐行输出。", {}),
    ("hrBankCard", "识别银行卡信息", "text", "image", "识别银行卡，输出「发卡行 / 卡号」。", {}),
    ("hrIdCard", "提取身份证信息", "text", "text", "从身份证号或文本中提取「出生日期 / 性别 / 籍贯地区」。", {}),
    ("hrGender", "判断性别", "singleSelect", "text", "根据姓名或身份证号判断性别。", {"defaultOptions": ["男", "女"]}),
    ("hrMatch", "评估岗位匹配度", "singleSelect", "multi", "根据候选人信息与岗位要求评估匹配度。",
     {"defaultOptions": ["高", "中", "低"]}),
    ("hrLeave", "计算今年休假天数", "number", "multi", "按《职工带薪年休假条例》根据累计工作年限计算今年年假天数。", {}),
    ("hrContract", "判断合同状态", "singleSelect", "text", "根据合同到期日与今天（{today}）判断合同状态（30 天内到期为即将到期）。",
     {"defaultOptions": ["生效中", "即将到期", "已到期"]}),
    ("hrHolidayQuery", "查询节假日", "text", "text", "查询节假日安排。", {"disabled": True}),
]:
    S(k, lb, "hr", out, inp, task, **extra)

# ---------- 市场营销 ----------
for k, lb, out, inp, task, extra in [
    ("mkRank", "计算排名", "number", "text", "按数值计算在全表中的排名。", {"disabled": True}),
    ("mkFans", "判断粉丝区间", "singleSelect", "text", "根据粉丝数判断达人量级。",
     {"defaultOptions": ["头部(100万+)", "腰部(10-100万)", "尾部(1-10万)", "素人(<1万)"]}),
    ("mkScore", "给文案打分", "number", "text", "从吸引力、清晰度、转化力综合给文案打分（0-100），只返回数字。", {}),
    ("mkCopy", "生成营销文案", "text", "multi", "根据产品信息生成 60 字以内、有吸引力的营销文案。", {}),
    ("mkAccount", "识别达人账号", "text", "text", "从文本或链接中识别达人账号名称与平台。", {}),
    ("mkVideoTitle", "提取视频标题", "text", "text", "从文本或链接内容中提取视频标题。", {}),
    ("mkLikes", "提取点赞量", "number", "text", "提取点赞量（如 1.2w 换算为 12000），只返回数字。", {}),
    ("mkFavs", "提取收藏量", "number", "text", "提取收藏量（如 1.2w 换算为 12000），只返回数字。", {}),
    ("mkComments", "提取评论量", "number", "text", "提取评论量（如 1.2w 换算为 12000），只返回数字。", {}),
    ("mkFansShot", "截图识别粉丝量", "number", "image", "从主页截图中识别粉丝数量，只返回数字。", {}),
    ("mkShares", "提取转发分享量", "number", "text", "提取转发/分享量（如 1.2w 换算为 12000），只返回数字。", {}),
    ("mkCompliance", "检测文案合规性", "singleSelect", "text", "按广告法检测文案是否含绝对化用语、虚假宣传等风险。",
     {"defaultOptions": ["合规", "存在风险", "违规"]}),
    ("mkIdea", "生成创意文案", "text", "multi", "根据主题生成 3 条不同风格的创意标题，用换行分隔。", {}),
]:
    S(k, lb, "marketing", out, inp, task, **extra)

# ---------- 生产制造 ----------
for k, lb, out, inp, task, extra in [
    ("pdBom", "提取BOM物料清单", "text", "multi", "提取物料清单，按「物料 规格 数量」逐行输出。", {}),
    ("pdDefect", "计算批次不良率", "number", "multi", "根据不良数与批次总数计算不良率（百分比数字，保留两位小数）。", {}),
    ("pdOrder", "提取订单信息", "text", "text", "提取「订单号 / 产品 / 数量 / 交期」。", {}),
    ("pdInspect", "巡检现场描述", "text", "image", "描述巡检现场情况，并指出可见的安全或质量隐患。", {}),
    ("pdImprove", "问题改进措施", "text", "multi", "针对问题描述给出 2-3 条具体的改进措施。", {}),
    ("pdBatch", "提取生产批号", "text", "text", "从文本中提取生产批号。", {}),
    ("pdHours", "计算生产总工时", "number", "multi", "根据人数与时长计算总工时（小时），只返回数字。", {}),
    ("pdStock", "计算当前库存", "number", "multi", "根据期初、入库、出库数量计算当前库存，只返回数字。", {}),
    ("pdTicketTime", "工单处理时长", "text", "multi", "根据创建与完成时间计算处理时长，如「2 天 3 小时」。", {}),
    ("pdReview", "工单复盘总结", "text", "multi", "对工单进行复盘：原因、处理、预防，各一句话。", {}),
    ("pdStockAlert", "库存状态预警", "singleSelect", "multi", "根据库存与安全库存判断库存状态。",
     {"defaultOptions": ["充足", "偏低", "缺货"]}),
]:
    S(k, lb, "production", out, inp, task, **extra)

# ---------- 门店管理 ----------
for k, lb, out, inp, task, extra in [
    ("stClose", "关店审核", "singleSelect", "image", "根据关店照片检查灯光、门窗、卫生是否合规。", {"defaultOptions": ["合格", "不合格"]}),
    ("stDisplay", "陈列审核", "singleSelect", "image", "根据陈列照片判断商品陈列是否整齐、规范。", {"defaultOptions": ["合格", "需整改"]}),
    ("stLicense", "识别营业执照", "text", "image", "识别营业执照，输出「名称 / 统一社会信用代码 / 法定代表人 / 成立日期」。", {}),
    ("stName", "识别门店名称", "text", "image", "识别门头照片中的门店名称。", {}),
    ("stAttendance", "判断出勤是否达标", "checkbox", "multi", "根据出勤天数与应出勤天数判断是否达标（≥95%）。", {}),
    ("stHours", "计算员工工时", "number", "multi", "根据上下班时间计算工时（小时，保留一位小数）。", {}),
    ("stHealthDate", "提取健康证日期", "text", "image", "识别健康证上的有效期截止日期，格式 YYYY-MM-DD。", {}),
    ("stHealthDays", "计算健康证到期天数", "number", "text", "计算健康证有效期距今天（{today}）还有多少天，已过期为负数。", {}),
]:
    S(k, lb, "store", out, inp, task, **extra)

# ---------- 订单物流 ----------
for k, lb, out, inp, task, extra in [
    ("lgTracking", "识别物流单号", "text", "text", "从文本中识别快递物流单号。", {}),
    ("lgCity", "判断收货城市", "text", "text", "根据收货地址判断所在城市。", {}),
    ("lgStatus", "识别订单状态", "singleSelect", "text", "根据物流或订单描述判断订单状态。",
     {"defaultOptions": ["待发货", "运输中", "已签收", "异常"]}),
    ("lgPlate", "识别车牌号", "text", "image", "识别图片中的车牌号。", {}),
    ("lgReceiver", "识别收件人", "text", "text", "从文本中识别收件人姓名。", {}),
    ("lgAddress", "识别收货地址", "text", "text", "从文本中识别完整的收货地址。", {}),
    ("lgZip", "提取邮政编码", "text", "text", "提取或推断地址对应的邮政编码。", {}),
    ("lgRegion", "提取省市区", "text", "text", "从地址中提取「省 / 市 / 区」，用 / 分隔。", {}),
]:
    S(k, lb, "logistics", out, inp, task, **extra)

# ---------- 财务会计 ----------
for k, lb, out, inp, task, extra in [
    ("fnIit", "计算个人所得税", "number", "multi", "按综合所得月度预扣税率表，根据应发工资与专项扣除计算个人所得税，只返回数字。", {}),
    ("fnIitLevel", "计算个税档位", "text", "text", "根据应纳税所得额判断适用的个税税率档位，如「10%」。", {}),
    ("fnBonusSeparate", "计算年终奖单独税率", "text", "text", "按年终奖单独计税方法计算适用税率与应纳税额。", {}),
    ("fnBonusMerge", "计算年终合并税率", "text", "multi", "按并入综合所得计税方法计算适用税率与应纳税额。", {}),
    ("fnCardCheck", "银行卡号校验", "checkbox", "text", "按 Luhn 算法校验银行卡号是否有效。", {"local": True}),
    ("fnVat", "计算增值税申报", "text", "multi", "根据销售额与进项税额计算应纳增值税。", {}),
]:
    S(k, lb, "finance", out, inp, task, **extra)

# ---------- 自定义 ----------
S("custom", "自定义 AI 字段", "custom", "text", "multi", "按用户描述的规则处理本行数据。",
  desc="描述数据处理规则，AI 帮你完成提取和计算。",
  prompt="你是一个嵌入在智能表格中的 AI 助手。\n任务：按用户描述的规则处理本行数据，结果简洁准确。\n输入：本行相关字段的内容。")

SCENE_BY_KEY = {s["key"]: s for s in SCENES}
