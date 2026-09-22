from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from .database import Base


class MetaTable(Base):
    """业务表注册表"""
    __tablename__ = "meta_tables"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False)   # 物理表名 dyn_xxx
    label = Column(String(128), nullable=False)              # 显示名
    source_file = Column(String(256))                        # 来源上传文件 id
    status = Column(String(16), default="active")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class MetaField(Base):
    """字段定义：动态表单/列表/校验的唯一依据"""
    __tablename__ = "meta_fields"

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_id = Column(Integer, ForeignKey("meta_tables.id"), index=True, nullable=False)
    field_name = Column(String(64), nullable=False)
    label = Column(String(128), nullable=False)
    data_type = Column(String(16), nullable=False)   # varchar/text/int/decimal/date/datetime/bool
    length = Column(Integer, default=255)
    nullable = Column(Boolean, default=True)
    default_value = Column(String(256))
    widget = Column(String(32), default="input")
    options = Column(JSON, default=dict)             # source_header / 枚举项 / show_in_list 等
    sort_order = Column(Integer, default=0)


class ImportBatch(Base):
    """导入批次记录"""
    __tablename__ = "import_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_id = Column(Integer, ForeignKey("meta_tables.id"), index=True, nullable=False)
    file_name = Column(String(256))
    total = Column(Integer, default=0)
    success = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    fail_detail = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.now)


class LLMProvider(Base):
    """大模型供应商配置（可多家，运行时切换）"""
    __tablename__ = "llm_providers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False)
    type = Column(String(32), default="openai_compat")   # openai_compat / claude
    base_url = Column(String(256))
    api_key_enc = Column(Text)                           # Fernet 加密存储
    model = Column(String(128), nullable=False)
    vision_model = Column(String(128))
    is_default = Column(Boolean, default=False)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)


class VisionLog(Base):
    """图片识别留痕：图片、原始返回、用户采纳的字段"""
    __tablename__ = "vision_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_id = Column(Integer, ForeignKey("meta_tables.id"), index=True, nullable=False)
    record_id = Column(Integer)                          # 编辑场景的记录 id，新增为空
    image_paths = Column(JSON, default=list)             # 相对 uploads 的路径
    raw_response = Column(Text)                          # 模型原始输出
    adopted_fields = Column(JSON)                        # 用户最终采纳的字段名列表
    created_at = Column(DateTime, default=datetime.now)


class TaskRule(Base):
    """任务规则：目标表 + 条件 + 周期 + 动作"""
    __tablename__ = "task_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    table_id = Column(Integer, ForeignKey("meta_tables.id"), index=True, nullable=False)
    enabled = Column(Boolean, default=False)
    condition_mode = Column(String(16), default="structured")  # structured / llm
    condition_json = Column(JSON, default=dict)
    # structured: {logic: AND|OR, rules: [{field, op, value}]}
    # llm:        {description: "...", prefilter?: {logic, rules}}
    schedule_json = Column(JSON, default=dict)   # {type: interval, minutes} | {type: cron, expr}
    action_json = Column(JSON, default=dict)
    # {type: notify|email|sms|webhook, template, webhook_url?, recipients: {type: fixed|field, value|field}}
    cooldown_hours = Column(Integer, default=24)  # 同一记录冷却期；0 = 永不重复触发
    max_per_run = Column(Integer, default=100)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class TaskTriggerLog(Base):
    """触发去重：同一规则同一记录只记一条，重复触发时更新 fired_at"""
    __tablename__ = "task_trigger_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, ForeignKey("task_rules.id"), index=True, nullable=False)
    record_id = Column(Integer, nullable=False)
    fired_at = Column(DateTime, default=datetime.now)


class TaskRunLog(Base):
    """每次执行（计划/手动/试运行）的日志"""
    __tablename__ = "task_run_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, ForeignKey("task_rules.id"), index=True, nullable=False)
    trigger = Column(String(16), default="schedule")   # schedule / manual / test
    run_at = Column(DateTime, default=datetime.now)
    matched_count = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    fail_count = Column(Integer, default=0)
    detail_json = Column(JSON, default=list)
    error = Column(Text)


class ReportTemplate(Base):
    """报表模板：目标表 + 默认时间口径 + 区块列表 + (可选)定时推送"""
    __tablename__ = "report_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    description = Column(String(256))
    table_id = Column(Integer, ForeignKey("meta_tables.id"), index=True, nullable=False)
    enabled = Column(Boolean, default=False)               # 控制定时推送是否生效
    range_json = Column(JSON, default=dict)
    # {mode: this_week|last_week|this_month|last_month|custom, date_field, start?, end?}
    blocks_json = Column(JSON, default=list)
    # [{id, type: stat|chart|table|text, title, filters: {logic, rules}, ...}]
    schedule_json = Column(JSON, default=dict)   # {type: interval, minutes} | {type: cron, expr}
    push_json = Column(JSON, default=dict)       # {recipients, formats: [html_inline, xlsx], subject}
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class ReportRunLog(Base):
    """报表推送日志（定时/手动）"""
    __tablename__ = "report_run_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(Integer, ForeignKey("report_templates.id"), index=True, nullable=False)
    trigger = Column(String(16), default="schedule")   # schedule / manual
    run_at = Column(DateTime, default=datetime.now)
    range_label = Column(String(64))
    sent_count = Column(Integer, default=0)
    error = Column(Text)


class Notification(Base):
    """站内通知"""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256))
    content = Column(Text)
    link = Column(String(256))
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)


class AppSetting(Base):
    """通用配置（SMTP、短信网关等），key-value JSON"""
    __tablename__ = "app_settings"

    key = Column(String(64), primary_key=True)
    value = Column(JSON)


class AuditLog(Base):
    """审计日志"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user = Column(String(64), default="admin")
    action = Column(String(32), nullable=False)          # create/update/delete/create_table/drop_table
    table_id = Column(Integer, index=True)
    record_id = Column(Integer)
    before_json = Column(JSON)
    after_json = Column(JSON)
    created_at = Column(DateTime, default=datetime.now)
