from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from .database import Base


class MetaTable(Base):
    """业务表注册表"""
    __tablename__ = "meta_tables"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False)   # 物理表名 dyn_xxx（json 模式下为逻辑名，不建物理表）
    label = Column(String(128), nullable=False)              # 显示名
    source_file = Column(String(256))                        # 来源上传文件 id
    status = Column(String(16), default="active")
    owner_id = Column(Integer, ForeignKey("users.id"), index=True)   # 归属用户（多租户）
    storage_mode = Column(String(16), default="json")        # json（单表存储）/ physical（独立物理表）
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


class SerialCounter(Base):
    """自动编号计数器：按（表, 字段, 重置周期）一行，原子自增发号，保证并发不重号"""
    __tablename__ = "serial_counters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_id = Column(Integer, ForeignKey("meta_tables.id"), index=True, nullable=False)
    field_name = Column(String(64), nullable=False)
    period_key = Column(String(16), default="")   # 周期键：daily=YYYYMMDD / monthly=YYYYMM / never=空串
    value = Column(Integer, default=0, nullable=False)

    __table_args__ = (UniqueConstraint("table_id", "field_name", "period_key", name="uq_serial_counters"),)


class Permission(Base):
    """权限点：内置 + 自定义。value 型权限（如数据表上限）通过 role_permissions.value 配置"""
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(64), unique=True, nullable=False)     # 如 share / create_physical_table / max_tables
    name = Column(String(64), nullable=False)                  # 显示名，如「分享」
    description = Column(String(256))
    is_system = Column(Boolean, default=False)                 # 内置权限不可删除
    created_at = Column(DateTime, default=datetime.now)


class Role(Base):
    """角色：权限的集合。admin 为代码级超级角色（直接放行，不查表）"""
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(64), unique=True, nullable=False)     # 如 admin / vip / user
    name = Column(String(64), nullable=False)
    description = Column(String(256))
    is_system = Column(Boolean, default=False)                 # 内置角色不可删除
    created_at = Column(DateTime, default=datetime.now)


class RolePermission(Base):
    """角色-权限关联。value 用于数值型权限（如 max_tables=10），NULL 表示不限"""
    __tablename__ = "role_permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_id = Column(Integer, ForeignKey("roles.id"), index=True, nullable=False)
    permission_id = Column(Integer, ForeignKey("permissions.id"), index=True, nullable=False)
    value = Column(Integer)

    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permissions"),)


class Record(Base):
    """JSON 模式业务数据：一张表存所有 json 业务表的数据（值已序列化为 ISO 字符串/数字/布尔）"""
    __tablename__ = "records"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    table_id = Column(Integer, ForeignKey("meta_tables.id"), index=True, nullable=False)
    data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (Index("ix_records_table_id_id", "table_id", "id"),)


class TableShare(Base):
    """表级分享授权：查看/新增/编辑/删除 四个开关。分享给用户（user_id）或用户组（group_id）"""
    __tablename__ = "table_shares"

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_id = Column(Integer, ForeignKey("meta_tables.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), index=True)
    can_view = Column(Boolean, default=False)
    can_create = Column(Boolean, default=False)
    can_edit = Column(Boolean, default=False)
    can_delete = Column(Boolean, default=False)
    shared_by = Column(Integer, ForeignKey("users.id"))   # 分享操作者
    status = Column(String(16), default="pending")        # pending（待对方确认）/ accepted / rejected；组分享恒为 accepted
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (UniqueConstraint("table_id", "user_id", "group_id", name="uq_table_shares_target"),)


class Group(Base):
    """用户组：分享授权的对象之一，组成员自动获得组被分享的权限"""
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False)
    description = Column(String(256))
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.now)


class GroupMember(Base):
    __tablename__ = "group_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("groups.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_group_members"),)


class Friendship(Base):
    """好友关系（申请-同意制）：requester 申请，addressee 同意后双向生效"""
    __tablename__ = "friendships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    requester_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    addressee_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    status = Column(String(16), default="pending")        # pending / accepted / rejected
    created_at = Column(DateTime, default=datetime.now)
    responded_at = Column(DateTime)

    __table_args__ = (UniqueConstraint("requester_id", "addressee_id", name="uq_friendships_pair"),)


class SharedLink(Base):
    """链接分享：免登录只读访问表/报表，可设密码和有效期；报表可选开放筛选/口径切换"""
    __tablename__ = "shared_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(64), unique=True, index=True, nullable=False)
    resource_type = Column(String(16), default="table")   # table / report
    resource_id = Column(Integer, nullable=False)         # table_id 或 report_template.id
    password_hash = Column(String(256))
    expires_at = Column(DateTime)
    allow_interact = Column(Boolean, default=False)       # 报表：允许查看者筛选/切口径
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.now)


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


class User(Base):
    """登录用户：账号密码登录；openid 预留给微信登录"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    password_hash = Column(String(256))          # pbkdf2_sha256$iterations$salt$digest
    openid = Column(String(64), unique=True, index=True)  # 微信登录用，可空
    role = Column(String(16), default="user")    # admin / user
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


class ReportTemplate(Base):
    """报表模板：目标表 + 默认时间口径 + 区块列表 + (可选)定时推送"""
    __tablename__ = "report_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    description = Column(String(256))
    table_id = Column(Integer, ForeignKey("meta_tables.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)   # 归属用户（多租户）
    enabled = Column(Boolean, default=False)               # 控制定时推送是否生效
    range_json = Column(JSON, default=dict)
    # {mode: today|yesterday|past_7d|past_30d|this_week|last_week|this_month|last_month|this_quarter|this_year|custom, date_field, start?, end?}
    blocks_json = Column(JSON, default=list)
    # [{id, type: stat|chart|table|text|pivot, title, filters: {logic, rules}, ...}]；stat 支持 agg: ratio（占比）与 compare: 环比；pivot 为行×列交叉聚合
    layout_json = Column(JSON)                           # None=旧版垂直堆叠；{version, grid:{cols,row_height}, pages:[{id,title,items:[{block_id,x,y,w,h}]}]}
    source_json = Column(JSON)                           # 数据集：None=单表；{joins:[{table_id,on:[{left,right}],prefix}], computed_fields:[{name,expr,type?}]}
    datasets_json = Column(JSON)                         # v3 命名数据集 [{id,name,base_table_id,joins,computed_fields}]；空=旧格式运行期合成
    filters_json = Column(JSON, default=list)      # 查看端开放筛选的字段名列表
    schedule_json = Column(JSON, default=dict)   # {type: interval, minutes} | {type: cron, expr}
    push_json = Column(JSON, default=dict)       # {recipients, formats: [html_inline, xlsx], subject}
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class PrintTemplate(Base):
    """工单打印模板：按表共享（view 可见 / owner·admin 可编辑），全部 Excel 方式（xlsx 模板 + 占位符填充）。

    kind/paper/enabled 为历史遗留列，新数据恒为 excel/a4/True，代码不再读取。
    """
    __tablename__ = "print_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_id = Column(Integer, ForeignKey("meta_tables.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)   # 创建者（仅留痕；权限按表 owner/admin 判定）
    code = Column(String(16))                  # 表内序号编码 A001/A002…（创建时服务端取 max+1）
    name = Column(String(128), nullable=False)
    kind = Column(String(16), default="excel")    # 遗留列：恒为 excel
    paper = Column(String(16), default="a4")      # 遗留列：不再使用
    is_default = Column(Boolean, default=False)
    enabled = Column(Boolean, default=True)       # 遗留列：不再有停用功能
    config_json = Column(JSON, default=dict)      # excel 模板元信息：orig_name / uploaded_at
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
    skipped = Column(Boolean, default=False)   # 阈值告警：条件未满足，本次跳过推送
    error = Column(Text)


class Note(Base):
    """记事本页面：块模型内容（Editor.js blocks），可嵌套（最多 3 层），严格私有。"""
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)   # 归属用户（仅本人可见，admin 也不例外）
    parent_id = Column(Integer, ForeignKey("notes.id"), nullable=True, index=True)  # 父页面，可空=顶级
    title = Column(String(200), default="")
    blocks_json = Column(JSON, default=list)   # Editor.js blocks: [{id, type, data}]
    pinned = Column(Boolean, default=False)
    sort = Column(Integer, default=0)          # 同级手工排序
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class Notification(Base):
    """站内通知"""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256))
    content = Column(Text)
    link = Column(String(256))
    user_id = Column(Integer, ForeignKey("users.id"), index=True)   # 接收人
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


class Workflow(Base):
    """工作流定义：一个触发器 + 节点列表 + 连线。见 docs/工作流节点规范.md"""
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    description = Column(String(500), default="")
    user_id = Column(Integer, ForeignKey("users.id"), index=True)   # 归属用户（节点以其身份执行）
    enabled = Column(Boolean, default=False)
    trigger_json = Column(JSON, default=dict)   # {type: schedule|record_created|record_updated|webhook|manual, ...}
    nodes_json = Column(JSON, default=list)     # [{id, type, name, config, on_error?}]
    edges_json = Column(JSON, default=list)     # [{from, to, branch?}]
    schema_version = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class WorkflowRun(Base):
    """工作流的一次执行"""
    __tablename__ = "workflow_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), index=True, nullable=False)
    trigger = Column(String(16), default="manual")  # schedule / manual / record / webhook / test
    status = Column(String(16), default="pending")  # pending / running / success / failed / waiting / cancelled
    context_json = Column(JSON, default=dict)       # {trigger, nodes: {node_id: output}}
    tokens_used = Column(Integer, default=0)
    error = Column(Text)
    started_at = Column(DateTime, default=datetime.now)
    finished_at = Column(DateTime)


class WorkflowNodeRun(Base):
    """一次 Run 中每个节点的执行记录（审计与成本核算的最小粒度）"""
    __tablename__ = "workflow_node_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("workflow_runs.id"), index=True, nullable=False)
    node_id = Column(String(64), nullable=False)
    node_type = Column(String(32), nullable=False)
    status = Column(String(16), default="pending")  # pending / running / success / failed / skipped / waiting
    input_json = Column(JSON, default=dict)         # 渲染后的 config 快照
    output_json = Column(JSON, default=dict)
    warnings_json = Column(JSON, default=list)      # 渲染期告警（如变量路径不存在、已按空值渲染）
    tokens_used = Column(Integer, default=0)
    duration_ms = Column(Integer, default=0)
    error = Column(Text)
    started_at = Column(DateTime, default=datetime.now)
    finished_at = Column(DateTime)


class WorkflowJob(Base):
    """简易任务队列：worker（调度器内轮询）领取执行。支撑异步触发、延迟、重试、审批恢复。"""
    __tablename__ = "workflow_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("workflow_runs.id"), index=True, nullable=False)
    node_id = Column(String(64))                    # resume/retry 时定位节点；start 为空
    kind = Column(String(16), default="start")      # start（从头执行）/ resume（从节点后继继续）/ retry（重跑该节点）
    execute_after = Column(DateTime, default=datetime.now)
    attempts = Column(Integer, default=0)
    status = Column(String(16), default="pending")  # pending / running / done / dead
    locked_at = Column(DateTime)


class ImageFile(Base):
    """图片附件：文件本体存 uploads/images/，本表存元数据与归属（表/记录/字段）。"""
    __tablename__ = "image_files"

    id = Column(String(32), primary_key=True)           # uuid hex，即磁盘文件名
    table_id = Column(Integer, index=True)              # 归属数据表（上传后关联记录时回填）
    record_id = Column(BigInteger, index=True)          # 归属记录
    field_name = Column(String(64))                     # 归属字段
    uploader_id = Column(Integer, ForeignKey("users.id"))
    filename = Column(String(256))                      # 原始文件名
    mime = Column(String(64))
    size = Column(Integer)
    created_at = Column(DateTime, default=datetime.now)
