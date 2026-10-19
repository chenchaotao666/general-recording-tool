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
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True)  # 归属租户（P0 起强制）
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
    data_type = Column(String(16), nullable=False)   # varchar/text/int/decimal/date/datetime/bool/json
    length = Column(Integer, default=255)
    nullable = Column(Boolean, default=True)
    default_value = Column(String(256))
    widget = Column(String(32), default="input")
    options = Column(JSON, default=dict)             # source_header / 枚举项 / 字段类型 config 等
    sort_order = Column(Integer, default=0)
    field_type = Column(String(32))                  # 智能表字段类型（text/singleSelect/...）；NULL=存量老字段


class SmartDoc(Base):
    """智能表文档：V1 每租户一个默认文档（is_default=1，惰性创建）"""
    __tablename__ = "smart_docs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    name = Column(String(128), nullable=False, default="智能表")
    owner_id = Column(Integer, ForeignKey("users.id"), index=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class SmartDocEntry(Base):
    """智能表文档条目树：folder / sheet（sheet 通过 ref_table_id 关联 meta_tables）"""
    __tablename__ = "smart_doc_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(Integer, ForeignKey("smart_docs.id"), index=True, nullable=False)
    parent_id = Column(Integer, ForeignKey("smart_doc_entries.id"), index=True)  # NULL=根级
    type = Column(String(16), nullable=False)        # folder | sheet | dashboard | form（收集表单=表单视图+结果表）
    name = Column(String(128), nullable=False)
    ref_table_id = Column(Integer, ForeignKey("meta_tables.id"), index=True)  # type=sheet 时非空
    order_no = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class MetaView(Base):
    """表格视图：同一数据的多套展示配置（筛选/排序/填色/行高/列显隐等，见设计文档 §2.3）"""
    __tablename__ = "meta_views"

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_id = Column(Integer, ForeignKey("meta_tables.id"), index=True, nullable=False)
    name = Column(String(100), nullable=False, default="表格视图")
    type = Column(String(16), default="grid")        # grid / form（表单视图，V3）/ kanban（看板，V3）
    config = Column(JSON, default=dict)              # filters/sorts/fillRules/rowHeight/fieldVisibility/fieldOrder/colWidths/frozenFieldId/aggregations
    is_default = Column(Boolean, default=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class MetaViewPref(Base):
    """视图的个人覆盖（「调整仅你可见」）：V1 仅承载 filters 键，合并语义=替换视图 filters"""
    __tablename__ = "meta_view_prefs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    view_id = Column(Integer, ForeignKey("meta_views.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    config = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (UniqueConstraint("view_id", "user_id", name="uq_view_prefs"),)


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
    """角色：权限的集合。admin 为代码级超级角色（直接放行，不查表）。
    tenant_id NULL=全局内置角色（平台超管维护，所有租户可用）；
    非 NULL=租户自定义角色（租户 admin 维护，仅本租户可用，code 不得与全局角色重名）"""
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(64), nullable=False)                # 如 admin / vip / user；按 (tenant_id, code) 唯一
    name = Column(String(64), nullable=False)
    description = Column(String(256))
    is_system = Column(Boolean, default=False)                 # 内置角色不可删除
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True)  # NULL=全局角色
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_roles_tenant_code"),)


class RolePermission(Base):
    """角色-权限关联。value 用于数值型权限（如 max_tables=10），NULL 表示不限"""
    __tablename__ = "role_permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_id = Column(Integer, ForeignKey("roles.id"), index=True, nullable=False)
    permission_id = Column(Integer, ForeignKey("permissions.id"), index=True, nullable=False)
    value = Column(Integer)

    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permissions"),)


class TenantRolePerm(Base):
    """租户级角色功能权限覆盖：租户 admin 调整角色（含全局内置角色）在本租户内的功能权限。
    有行 → 以 granted 为准；无行 → 回落全局 role_permissions。平台超管直接改全局。"""
    __tablename__ = "tenant_role_perms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), index=True, nullable=False)
    permission_id = Column(Integer, ForeignKey("permissions.id"), index=True, nullable=False)
    granted = Column(Boolean, nullable=False, default=True)

    __table_args__ = (UniqueConstraint("tenant_id", "role_id", "permission_id",
                                       name="uq_tenant_role_perms"),)


class RoleTablePerm(Base):
    """角色 × 表 的操作权限（租户内配置）：无行 = 四项全允许（现状）。
    仅收窄 via=member 的企业成员默认访问；表主/租户 admin/显式分享不受限（与数据范围的击穿语义一致）。"""
    __tablename__ = "role_table_perms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), index=True, nullable=False)
    table_id = Column(Integer, ForeignKey("meta_tables.id"), index=True, nullable=False)
    can_view = Column(Boolean, nullable=False, default=True)
    can_create = Column(Boolean, nullable=False, default=True)
    can_edit = Column(Boolean, nullable=False, default=True)
    can_delete = Column(Boolean, nullable=False, default=True)

    __table_args__ = (UniqueConstraint("tenant_id", "role_id", "table_id",
                                       name="uq_role_table_perms"),)


class Record(Base):
    """JSON 模式业务数据：一张表存所有 json 业务表的数据（值已序列化为 ISO 字符串/数字/布尔）"""
    __tablename__ = "records"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    table_id = Column(Integer, ForeignKey("meta_tables.id"), index=True, nullable=False)
    tenant_id = Column(Integer, index=True)                  # 冗余自 meta_tables（配额计数/范围过滤免 join）
    owner_id = Column(Integer, ForeignKey("users.id"), index=True)  # 记录归属人（P1 数据范围用）
    data = Column(JSON, nullable=False, default=dict)
    parent_id = Column(BigInteger, index=True)               # 智能表树形子记录：父记录 id（V2）
    updated_by = Column(Integer, ForeignKey("users.id"))     # 最后编辑人（智能表系统字段，V2）
    updated_by_type = Column(String(16), default="user")      # 最后编辑主体：user / ai / automation（V3 留痕）
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
    tenant_id = Column(Integer, index=True)              # 归属租户（P0 起按租户隔离）
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
    """登录用户：账号密码登录；openid 预留给微信登录。
    role 列已废弃（业务语义下沉到 tenant_members.role），仅为兼容保留；
    is_platform_admin 为平台超管标记（跨租户运维，默认不见租户业务数据）。"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    password_hash = Column(String(256))          # pbkdf2_sha256$iterations$salt$digest
    openid = Column(String(64), unique=True, index=True)  # 微信登录用，可空
    role = Column(String(16), default="user")    # 废弃：见 tenant_members.role
    is_platform_admin = Column(Boolean, default=False)   # 平台超管（仅种子 admin）
    department_id = Column(Integer, ForeignKey("departments.id"))   # 所属部门（单归属，P1）
    manager_id = Column(Integer, ForeignKey("users.id"))            # 直属上级（subtree 范围用）
    created_at = Column(DateTime, default=datetime.now)


class Department(Base):
    """部门树（租户内单树，轻量实现：不支持多维组织/兼任；见 docs/用户与权限体系设计.md §4.6）"""
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    name = Column(String(64), nullable=False)
    parent_id = Column(Integer, ForeignKey("departments.id"))   # NULL=根部门
    leader_id = Column(Integer, ForeignKey("users.id"))         # 部门负责人（展示/审批用，不参与范围判定）
    sort = Column(Integer, default=0)
    enabled = Column(Boolean, default=True)                     # 停用后成员视同未分配
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (Index("ix_departments_tenant_parent", "tenant_id", "parent_id"),)


class RoleTableScope(Base):
    """角色 × 表 的数据范围（P1）：table_id=NULL 表示租户级默认。rank_limit 为 P2 职级占位。"""
    __tablename__ = "role_table_scopes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), index=True, nullable=False)
    table_id = Column(Integer, ForeignKey("meta_tables.id"), index=True)   # NULL=租户默认
    scope = Column(String(16), default="all")   # all / dept_tree（本部门及下级）/ subtree（本人及下属）/ own（仅本人）
    rank_limit = Column(Boolean, default=False)  # P2：dept_tree 叠加"职级不高于我"
    created_at = Column(DateTime, default=datetime.now)


# ---------- 租户与套餐（P0 商业化地基，见 docs/用户与权限体系设计.md §0/§4.7） ----------

class Tenant(Base):
    """租户/工作空间：个人版（1 席）/ 企业版（N 席）/ 私有化（单租户实例）"""
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    type = Column(String(16), default="personal")       # personal / enterprise / private
    owner_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    created_at = Column(DateTime, default=datetime.now)

    # 企业编号不复用，防止删除企业后的历史引用串到新企业。
    __table_args__ = {"sqlite_autoincrement": True}


class EnterpriseProfile(Base):
    """轻企业资料；独立新表兼容已有租户，不改动存量企业的授权策略。"""
    __tablename__ = "enterprise_profiles"

    tenant_id = Column(Integer, ForeignKey("tenants.id"), primary_key=True)
    category = Column(String(32), default="企业")
    industry = Column(String(64), default="")
    size = Column(String(32), default="")
    invite_code = Column(String(64), unique=True, index=True, nullable=False)
    invite_expires_at = Column(DateTime, nullable=False)
    lightweight = Column(Boolean, default=True, nullable=False)


class TenantMember(Base):
    """租户成员关系：role 在此处（同一人可在 A 租户是 admin、B 租户是 user）"""
    __tablename__ = "tenant_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    role = Column(String(64), default="user")           # roles.code：租户内角色
    status = Column(String(16), default="active")       # invited / active / disabled
    invited_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.now)

    # sqlite_autoincrement：id 单调不复用——通知 ref_id 等外部引用不会因"删行后 id 回收"串行
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_tenant_members"),
                      {"sqlite_autoincrement": True})


class Plan(Base):
    """套餐：价格/配额/功能开关全部库表驱动（平台超管后台可改，种子只是默认值）"""
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(64), unique=True, nullable=False)   # free / individual_basic / ent_team / private / legacy ...
    name = Column(String(64), nullable=False)
    audience = Column(String(16), nullable=False)            # individual / enterprise / private
    price_monthly = Column(Integer, default=0)               # 单位：分
    price_yearly = Column(Integer, default=0)                # 单位：分
    sort = Column(Integer, default=0)
    is_public = Column(Boolean, default=True)                # False=隐藏档（legacy / private）
    created_at = Column(DateTime, default=datetime.now)


class PlanEntitlement(Base):
    """套餐权益键值：配额类（max_tables/max_rows/max_storage_mb/max_seats/min_seats）、
    功能开关类（feature_*，1=开通）、宽限类（quota_grace_days/sub_grace_days）、
    保留类（trash_retention_days/audit_retention_days）。value=NULL 表示不限。"""
    __tablename__ = "plan_entitlements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("plans.id"), index=True, nullable=False)
    key = Column(String(64), nullable=False)
    value = Column(Integer)                                  # NULL=不限

    __table_args__ = (UniqueConstraint("plan_id", "key", name="uq_plan_entitlements"),)


class Subscription(Base):
    """租户当前订阅（一租户一条）。expires_at=NULL 永不到期（free/legacy）"""
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), unique=True, nullable=False)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)
    seats = Column(Integer, default=1)
    status = Column(String(16), default="active")   # trial / active / grace / expired
    started_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime)
    grace_until = Column(DateTime)                  # status=grace 时的宽限截止


class UsageCounter(Base):
    """租户用量计数：写路径增减 + 定时全量校准。grace_json={quota_key: 超限起始 ISO 时间}"""
    __tablename__ = "usage_counters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), unique=True, nullable=False)
    table_count = Column(Integer, default=0)
    row_count = Column(BigInteger, default=0)
    storage_bytes = Column(BigInteger, default=0)
    seat_count = Column(Integer, default=0)
    grace_json = Column(JSON, default=dict)
    calibrated_at = Column(DateTime)


class Order(Base):
    """套餐订单：选购 → 支付（当前为模拟支付）→ 订阅生效。金额单位：分。"""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)
    seats = Column(Integer, default=1)              # 企业版按人计费
    years = Column(Integer, default=1)              # 购买年数
    amount = Column(Integer, nullable=False)        # 应付金额（分）
    status = Column(String(16), default="pending")  # pending / paid / cancelled
    created_at = Column(DateTime, default=datetime.now)
    paid_at = Column(DateTime)
    created_by = Column(Integer, ForeignKey("users.id"))


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
    tenant_id = Column(Integer, index=True)                         # 归属租户
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
    """记事本页面：富文本内容（HTML），可嵌套（最多 3 层），严格私有。"""
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)   # 归属用户（仅本人可见，admin 也不例外）
    parent_id = Column(Integer, ForeignKey("notes.id"), nullable=True, index=True)  # 父页面，可空=顶级
    kind = Column(String(16), default="page")    # page / folder（文件夹仅作目录分组，无内容）
    title = Column(String(200), default="")
    content_html = Column(Text, default="")    # 富文本 HTML（服务端白名单清洗后存储）
    pinned = Column(Boolean, default=False)
    sort = Column(Integer, default=0)          # 同级手工排序
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class Whiteboard(Base):
    """画板页面：画布 JSON（Excalidraw 序列化格式），可嵌套（最多 3 层），严格私有。
    engine 字段为将来多引擎预留，当前固定 excalidraw。"""
    __tablename__ = "whiteboards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)   # 归属用户（仅本人可见，admin 也不例外）
    parent_id = Column(Integer, ForeignKey("whiteboards.id"), nullable=True, index=True)  # 父页面，可空=顶级
    kind = Column(String(16), default="page")    # page / folder（文件夹仅作目录分组，无内容）
    title = Column(String(200), default="")
    engine = Column(String(16), default="excalidraw")   # excalidraw / tldraw，创建时选定后不改
    content_json = Column(Text, default="")             # 画布序列化 JSON（服务端只校验长度与 JSON 合法性）
    pinned = Column(Boolean, default=False)
    sort = Column(Integer, default=0)                   # 同级手工排序
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class Mindmap(Base):
    """思维导图：data 存引擎无关的纯文本树 {text, children[]}（前端各引擎组件自行转换），
    租户内成员共享编辑；删除限 所有者/租户 admin。支持文件夹目录（kind=folder 仅分组，无内容）。"""
    __tablename__ = "mindmaps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)   # 创建人
    parent_id = Column(Integer, ForeignKey("mindmaps.id"), nullable=True, index=True)  # 父文件夹，可空=顶级
    kind = Column(String(16), default="page")   # page / folder（文件夹仅作目录分组，无内容）
    title = Column(String(200), default="未命名导图")
    data = Column(JSON, default=dict)   # {text: str, children: [...]}
    pinned = Column(Boolean, default=False)
    sort = Column(Integer, default=0)               # 同级手工排序
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class MindmapShare(Base):
    """思维导图成员分享（可跨租户给好友/组）：查看/编辑两个开关；直发 pending，组分享即时生效。"""
    __tablename__ = "mindmap_shares"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mindmap_id = Column(Integer, ForeignKey("mindmaps.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), index=True)
    can_view = Column(Boolean, default=True)
    can_edit = Column(Boolean, default=False)
    shared_by = Column(Integer, ForeignKey("users.id"))
    status = Column(String(16), default="pending")        # pending / accepted / rejected
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (UniqueConstraint("mindmap_id", "user_id", "group_id",
                                       name="uq_mindmap_shares_target"),)


class Notification(Base):
    """站内通知"""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256))
    content = Column(Text)
    link = Column(String(256))
    user_id = Column(Integer, ForeignKey("users.id"), index=True)   # 接收人
    read = Column(Boolean, default=False)
    # 结构化引用：如 ref_type=tenant_invitation + ref_id=tenant_members.id，
    # 前端据此在通知条目上直接渲染 接受/拒绝 等内联操作（无需跳转详情页）
    ref_type = Column(String(32))
    ref_id = Column(Integer)
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
    tenant_id = Column(Integer, index=True)              # 归属租户（审计查询按租户过滤）
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
    tenant_id = Column(Integer, index=True)                         # 归属租户
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
    note_id = Column(Integer, ForeignKey("notes.id"), index=True)  # 归属记事本页面（富文本插图时回填）
    uploader_id = Column(Integer, ForeignKey("users.id"))
    filename = Column(String(256))                      # 原始文件名
    mime = Column(String(64))
    size = Column(Integer)
    created_at = Column(DateTime, default=datetime.now)


class HomeLayout(Base):
    """首页工作台布局：每用户一份（分区 → 分组 → 卡片三层，见 docs/首页工作台设计.md）。"""
    __tablename__ = "home_layouts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True, nullable=False)
    layout_json = Column(JSON, default=dict)   # {version, sections:[{id,title,x,y,w,h,groups?,cards?}]}
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class HomeDefaultLayout(Base):
    """全员默认首页布局（管理员预设，单行表）。"""
    __tablename__ = "home_default_layout"

    id = Column(Integer, primary_key=True, autoincrement=True)
    layout_json = Column(JSON, default=dict)
    updated_by = Column(Integer, ForeignKey("users.id"))
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class MetaColumnGroup(Base):
    """智能表列编组（多级表头，设计文档 §6.3）：一组字段共享一个组头"""
    __tablename__ = "meta_column_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_id = Column(Integer, ForeignKey("meta_tables.id"), index=True, nullable=False)
    name = Column(String(100), nullable=False)
    field_names = Column(JSON, default=list)         # 成员字段 field_name 列表
    order_no = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)


class DashboardWidget(Base):
    """智能表仪表盘图表（设计文档 §2.5.1）：引用工作表数据的图表 widget"""
    __tablename__ = "dashboard_widgets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_id = Column(Integer, ForeignKey("smart_doc_entries.id"), index=True, nullable=False)
    title = Column(String(200), default="图表")
    chart_type = Column(String(16), default="bar")   # bar/line/pie/barH/metric/table
    sub_type = Column(String(32))                    # stacked / percentStacked
    theme = Column(String(32))
    config = Column(JSON, default=dict)              # {sourceTableId, filter, dimension, subDimension, metric:{field?,agg}, sort}
    layout = Column(JSON, default=dict)              # {x,y,w,h}
    order_no = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)


# ---------- 智能表 V3：内容权限（设计文档 §13） ----------

class SmartEntryPermission(Base):
    """条目级内容权限·全员基线（§13.5 SheetPermission.base）。无行 = 全员「全部权限」（V2 行为）。
    以条目为键：工作表/收集表单/仪表盘统一管理（仪表盘仅 FULL/VIEW 两档）。"""
    __tablename__ = "smart_entry_permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_id = Column(Integer, ForeignKey("smart_doc_entries.id"), nullable=False, unique=True)
    base_profile = Column(JSON, nullable=False, default=dict)   # PermissionProfile
    updated_by = Column(Integer, ForeignKey("users.id"))
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class SmartPermGroup(Base):
    """指定成员组（§13.2）：成员集合 + 备注名（「负责人」「设计」…，对组内成员可见）"""
    __tablename__ = "smart_perm_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(Integer, ForeignKey("smart_docs.id"), index=True, nullable=False)
    name = Column(String(50), nullable=False)
    member_ids = Column(JSON, default=list)
    order_no = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)


class SmartGroupGrant(Base):
    """指定成员组对某条目的额外权限（grant-only 叠加，effective = max(全员, ∪组)）"""
    __tablename__ = "smart_group_grants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("smart_perm_groups.id"), index=True, nullable=False)
    entry_id = Column(Integer, ForeignKey("smart_doc_entries.id"), index=True, nullable=False)
    profile = Column(JSON, nullable=False, default=dict)

    __table_args__ = (UniqueConstraint("group_id", "entry_id", name="uq_smart_group_grants"),)


# ---------- 智能表 V3：自动化（设计文档 §11） ----------

class SmartAutomation(Base):
    """自动化规则：触发器（定时/新增/变更）+ 有序动作链"""
    __tablename__ = "smart_automations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_id = Column(Integer, ForeignKey("meta_tables.id"), index=True, nullable=False)
    tenant_id = Column(Integer, index=True)
    name = Column(String(200), nullable=False, default="自动化")
    enabled = Column(Boolean, default=True)
    trigger_config = Column(JSON, nullable=False, default=dict)
    actions = Column(JSON, nullable=False, default=list)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class SmartAutomationRun(Base):
    """自动化运行日志：触发快照 + 各步结果"""
    __tablename__ = "smart_automation_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, ForeignKey("smart_automations.id"), index=True, nullable=False)
    status = Column(String(16))                      # success / partial / failed / skipped
    trigger_snapshot = Column(JSON)
    step_results = Column(JSON)
    error = Column(Text)
    started_at = Column(DateTime, default=datetime.now)
    finished_at = Column(DateTime)


# ---------- 智能表 V3：AI 字段运行状态（设计文档 §10.2） ----------

class SmartAiRun(Base):
    """AI 字段单元格计算状态（结果落 records.data，这里只记状态/错误/用量）"""
    __tablename__ = "smart_ai_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_id = Column(Integer, index=True, nullable=False)
    tenant_id = Column(Integer, index=True)              # 配额按租户按月计量
    field_name = Column(String(64), nullable=False)
    record_id = Column(BigInteger().with_variant(Integer, "sqlite"), nullable=False)
    status = Column(String(16), default="pending")   # pending / running / ok / error
    error = Column(Text)
    tokens_used = Column(Integer, default=0)
    billable = Column(Boolean, default=False)            # 调用了大模型（计入配额）；本地场景（查重/PDF 抽取）不计
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (UniqueConstraint("table_id", "field_name", "record_id", name="uq_smart_ai_runs"),)
