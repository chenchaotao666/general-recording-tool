"""轻量迁移：create_all 只建新表，已有库加列/回填在这里幂等执行（无 alembic 的过渡方案）。

迁移机制两层：
1. _NEW_COLUMNS：缺列则 ALTER（加列前自动备份 sqlite）
2. _MIGRATIONS：版本化数据迁移（schema_migrations 表记录已执行版本，跳过已跑）——
   解决"新库 create_all 建齐列后旧回填逻辑不触发"的问题，数据迁移与加列解耦。
"""
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from ..config import settings

# (表名, 列名, 列 DDL)
_NEW_COLUMNS = [
    ("meta_tables", "owner_id", "INTEGER"),
    ("meta_tables", "storage_mode", "VARCHAR(16)"),
    ("task_rules", "user_id", "INTEGER"),
    ("report_templates", "user_id", "INTEGER"),
    ("notifications", "user_id", "INTEGER"),
    ("table_shares", "group_id", "INTEGER"),
    ("table_shares", "status", "VARCHAR(16) DEFAULT 'accepted'"),
    ("report_templates", "filters_json", "JSON"),
    ("report_templates", "layout_json", "JSON"),
    ("report_templates", "source_json", "JSON"),
    ("report_templates", "datasets_json", "JSON"),
    ("workflow_node_runs", "warnings_json", "JSON"),
    ("report_run_logs", "skipped", "BOOLEAN DEFAULT 0"),
    ("shared_links", "allow_interact", "INTEGER DEFAULT 0"),
    ("print_templates", "kind", "VARCHAR(16) DEFAULT 'excel'"),
    # P0 商业化地基：租户/归属列
    ("users", "is_platform_admin", "BOOLEAN DEFAULT 0"),
    ("meta_tables", "tenant_id", "INTEGER"),
    ("records", "tenant_id", "INTEGER"),
    ("records", "owner_id", "INTEGER"),
    ("audit_logs", "tenant_id", "INTEGER"),
    ("groups", "tenant_id", "INTEGER"),
    ("workflows", "tenant_id", "INTEGER"),
    ("report_templates", "tenant_id", "INTEGER"),
    # P1 数据范围+组织树：用户组织归属
    ("users", "department_id", "INTEGER"),
    ("users", "manager_id", "INTEGER"),
    # 租户自定义角色：NULL=全局内置角色
    ("roles", "tenant_id", "INTEGER"),
    # 通知结构化引用（邀请通知内联 接受/拒绝 用）
    ("notifications", "ref_type", "VARCHAR(32)"),
    ("notifications", "ref_id", "INTEGER"),
    # 记事本改富文本 HTML 存储（替代 Editor.js blocks_json）
    ("notes", "content_html", "TEXT"),
    # 记事本插图归属（孤儿清理跳过已关联笔记的图片）
    ("image_files", "note_id", "INTEGER"),
    # 智能表：字段类型标识（text/singleSelect/...，NULL=存量老字段）
    ("meta_fields", "field_type", "VARCHAR(32)"),
]


def _columns(engine: Engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


def _backup_sqlite():
    """改结构前备份 SQLite 数据文件（仅当库文件存在且是 sqlite）"""
    if not settings.database_url.startswith("sqlite"):
        return
    db_file = Path(settings.database_url.replace("sqlite:///", ""))
    if db_file.exists():
        shutil.copy(db_file, db_file.with_suffix(f".db.bak-{datetime.now():%Y%m%d%H%M%S}"))


def _seed_rbac(conn) -> None:
    """种子角色/权限（幂等）。admin 为代码级超管；vip 可分享+独立表。
    max_tables 配额类权限已上移 plan_entitlements（P0），此处仅保留权限点行防止外键断链，不再新种子授权。"""
    roles = [
        ("admin", "管理员", "超级管理员，拥有全部权限（代码级放行）"),
        ("user", "普通用户", "默认角色"),
        ("manager", "经理", "可查看本部门及下级部门数据（配合「数据范围」配置使用）"),
    ]
    for code, name, desc in roles:
        conn.execute(
            text("INSERT INTO roles (code, name, description, is_system) "
                 "SELECT :c, :n, :d, 1 WHERE NOT EXISTS (SELECT 1 FROM roles WHERE code = :c AND tenant_id IS NULL)"),
            {"c": code, "n": name, "d": desc},
        )
    perms = [
        ("share", "分享", "把数据表分享给其他用户"),
        ("create_physical_table", "创建独立表", "建表时可选独立物理表存储（数据量大/报表重的表）"),
        ("max_tables", "数据表上限", "已废弃：配额由套餐 plan_entitlements 承接（保留行防外键断链）"),
        # 菜单功能权限（P2 角色矩阵）：控制侧边菜单入口显隐；admin 代码级恒有
        ("menu_tables", "菜单-数据表", "侧边「数据表」入口"),
        ("menu_import", "菜单-导入Excel", "侧边「导入 Excel」入口"),
        ("menu_notes", "菜单-记事本", "侧边「记事本」入口"),
        ("menu_reports", "菜单-报表", "侧边「报表」入口"),
        ("menu_workflows", "菜单-工作流", "侧边「工作流」入口"),
        ("menu_notifications", "菜单-通知", "侧边「通知」入口"),
        ("menu_friends", "菜单-好友", "侧边「好友」入口"),
        ("menu_groups", "菜单-用户组", "侧边「用户组」入口"),
        ("menu_billing", "菜单-套餐与用量", "侧边「套餐与用量」入口"),
        ("menu_mindmaps", "菜单-思维导图", "侧边「思维导图」入口"),
        ("menu_whiteboard", "菜单-画板", "侧边「画板」入口"),
        ("menu_smart_tables", "菜单-智能表", "侧边「智能表」入口（智慧表格）"),
    ]
    for code, name, desc in perms:
        conn.execute(
            text("INSERT INTO permissions (code, name, description, is_system) "
                 "SELECT :c, :n, :d, 1 WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :c)"),
            {"c": code, "n": name, "d": desc},
        )
    grants = [
        ("admin", "share", None), ("admin", "create_physical_table", None),
    ]
    # 菜单权限默认全开（user/manager/vip），租户 admin 可按角色关闭入口
    menu_perms = [c for c, _, _ in perms if c.startswith("menu_")]
    for rc in ("user", "manager"):
        grants += [(rc, c, None) for c in menu_perms]
    for role_code, perm_code, value in grants:
        conn.execute(
            text("INSERT INTO role_permissions (role_id, permission_id, value) "
                 "SELECT r.id, p.id, :v FROM roles r, permissions p "
                 "WHERE r.code = :rc AND r.tenant_id IS NULL AND p.code = :pc "
                 "AND NOT EXISTS (SELECT 1 FROM role_permissions WHERE role_id = r.id AND permission_id = p.id)"),
            {"rc": role_code, "pc": perm_code, "v": value},
        )


# ---------- 套餐种子（定价文档 §3/§4 的初始默认值；平台超管后台可改，此处不覆盖已有配置） ----------
# (code, name, audience, price_monthly分, price_yearly分, sort, is_public, {entitlement_key: value(None=不限)})
_PLAN_SEEDS = [
    ("free", "免费版", "individual", 0, 0, 10, True, {
        "max_tables": 3, "max_rows": 5000, "max_storage_mb": 512, "max_seats": 1,
        "quota_grace_days": 7, "sub_grace_days": 7,
        "feature_print_templates": 1}),
    ("individual_basic", "个人基础版", "individual", 990, 9900, 11, True, {
        "max_tables": 20, "max_rows": 50000, "max_storage_mb": 5120, "max_seats": 1,
        "quota_grace_days": 7, "sub_grace_days": 7,
        "feature_print_templates": 1, "trash_retention_days": 7}),
    ("individual_standard", "个人标准版", "individual", 2390, 23900, 12, True, {
        "max_tables": 100, "max_rows": 500000, "max_storage_mb": 20480, "max_seats": 1,
        "quota_grace_days": 7, "sub_grace_days": 7,
        "feature_print_templates": 1, "feature_automation": 1, "feature_api": 1,
        "trash_retention_days": 30}),
    ("individual_pro", "个人高级版", "individual", 4990, 49900, 13, True, {
        "max_tables": None, "max_rows": 2000000, "max_storage_mb": 102400, "max_seats": 1,
        "quota_grace_days": 7, "sub_grace_days": 7,
        "feature_print_templates": 1, "feature_automation": 1, "feature_api": 1,
        "trash_retention_days": 90}),
    ("ent_team", "企业团队版", "enterprise", None, 12000, 20, True, {
        "max_rows": 500000, "max_storage_mb": 51200, "min_seats": 5,
        "quota_grace_days": 7, "sub_grace_days": 7,
        "feature_print_templates": 1}),
    ("ent_standard", "企业标准版", "enterprise", None, 24000, 21, True, {
        "max_rows": 2000000, "max_storage_mb": 204800, "min_seats": 5,
        "quota_grace_days": 7, "sub_grace_days": 7,
        "feature_print_templates": 1, "feature_data_scope": 1, "feature_owd": 1,
        "feature_custom_roles": 1, "feature_audit": 1, "audit_retention_days": 90}),
    ("ent_flagship", "企业旗舰版", "enterprise", None, 40000, 22, True, {
        "max_rows": 5000000, "max_storage_mb": 512000, "min_seats": 5,
        "quota_grace_days": 7, "sub_grace_days": 7,
        "feature_print_templates": 1, "feature_data_scope": 1, "feature_owd": 1,
        "feature_share_rules": 1, "feature_perm_diagnose": 1, "feature_field_perm": 1,
        "feature_custom_roles": 1, "feature_audit": 1, "feature_automation": 1, "feature_api": 1}),
    ("private", "私有化部署", "private", None, None, 90, False, {
        "quota_grace_days": 7, "sub_grace_days": 7,
        "feature_print_templates": 1, "feature_data_scope": 1, "feature_owd": 1,
        "feature_share_rules": 1, "feature_perm_diagnose": 1, "feature_field_perm": 1,
        "feature_custom_roles": 1, "feature_audit": 1, "feature_automation": 1, "feature_api": 1}),
    # 存量迁移隐藏档：全不限 + 功能全开，保证老用户迁移零锁死（不对外售卖）
    ("legacy", "存量迁移档", "individual", 0, 0, 99, False, {
        "quota_grace_days": 7, "sub_grace_days": 7,
        "feature_print_templates": 1, "feature_data_scope": 1, "feature_owd": 1,
        "feature_share_rules": 1, "feature_perm_diagnose": 1, "feature_field_perm": 1,
        "feature_custom_roles": 1, "feature_audit": 1, "feature_automation": 1, "feature_api": 1}),
]


def _seed_plans(conn) -> None:
    """种子套餐与权益（幂等，不覆盖平台超管已修改的值）。"""
    if "plans" not in inspect(conn).get_table_names():
        return
    for code, name, audience, pm, py, sort, is_public, ents in _PLAN_SEEDS:
        conn.execute(
            text("INSERT INTO plans (code, name, audience, price_monthly, price_yearly, sort, is_public, created_at) "
                 "SELECT :c, :n, :a, :pm, :py, :s, :ip, :ca "
                 "WHERE NOT EXISTS (SELECT 1 FROM plans WHERE code = :c)"),
            {"c": code, "n": name, "a": audience, "pm": pm, "py": py, "s": sort,
             "ip": bool(is_public), "ca": datetime.now()},
        )
        plan_id = conn.execute(text("SELECT id FROM plans WHERE code = :c"), {"c": code}).scalar()
        for key, value in ents.items():
            conn.execute(
                text("INSERT INTO plan_entitlements (plan_id, key, value) "
                     "SELECT :p, :k, :v "
                     "WHERE NOT EXISTS (SELECT 1 FROM plan_entitlements WHERE plan_id = :p AND key = :k)"),
                {"p": plan_id, "k": key, "v": value},
            )


# ---------- v2 数据迁移：存量单池 → 多租户 ----------

def _migrate_v2_tenants(conn) -> None:
    """每个存量用户拆一个个人租户（legacy 不限档）；数据按表主/归属人回填 tenant_id；
    记录 owner_id 回填为表主（存量无 created_by）；种子 admin 转平台超管。"""
    now = datetime.now()
    legacy_plan_id = conn.execute(text("SELECT id FROM plans WHERE code = 'legacy'")).scalar()

    # 1. 平台超管：第一个 admin（种子 admin）
    conn.execute(text(
        "UPDATE users SET is_platform_admin = 1 "
        "WHERE id = (SELECT min(id) FROM users WHERE role = 'admin')"
    ))

    # 2. 逐用户建个人租户 + admin membership + legacy 订阅 + 用量行
    users = conn.execute(text("SELECT id, username FROM users ORDER BY id")).all()
    for uid, username in users:
        if conn.execute(text("SELECT 1 FROM tenant_members WHERE user_id = :u"), {"u": uid}).first():
            continue
        conn.execute(
            text("INSERT INTO tenants (name, type, owner_user_id, created_at) "
                 "VALUES (:n, 'personal', :u, :t)"),
            {"n": f"{username}的空间", "u": uid, "t": now},
        )
        tid = conn.execute(
            text("SELECT id FROM tenants WHERE owner_user_id = :u ORDER BY id DESC LIMIT 1"), {"u": uid}
        ).scalar()
        conn.execute(
            text("INSERT INTO tenant_members (tenant_id, user_id, role, status, created_at) "
                 "VALUES (:t, :u, 'admin', 'active', :ts)"),
            {"t": tid, "u": uid, "ts": now},
        )
        conn.execute(
            text("INSERT INTO subscriptions (tenant_id, plan_id, seats, status, started_at) "
                 "VALUES (:t, :p, 1, 'active', :ts)"),
            {"t": tid, "p": legacy_plan_id, "ts": now},
        )
        conn.execute(
            text("INSERT INTO usage_counters (tenant_id, table_count, row_count, storage_bytes, seat_count) "
                 "VALUES (:t, 0, 0, 0, 1)"),
            {"t": tid},
        )
    print(f"[migrate] v2: 个人租户迁移完成（用户 {len(users)} 个）", flush=True)

    # 3. 回填 tenant_id（按归属人 → 其个人租户；标量子查询，存量用户此时每人恰一个租户）
    member_tenant = "SELECT tm.tenant_id FROM tenant_members tm WHERE tm.user_id = %s LIMIT 1"
    for table, owner_col in (
        ("meta_tables", "owner_id"),
        ("groups", "created_by"),
        ("workflows", "user_id"),
        ("report_templates", "user_id"),
    ):
        conn.execute(text(
            f"UPDATE {table} SET tenant_id = ({member_tenant % (table + '.' + owner_col)}) "
            f"WHERE tenant_id IS NULL AND {owner_col} IS NOT NULL"
        ))
    # records / audit_logs 按所属表回填；记录 owner_id = 表主（存量无 created_by）
    conn.execute(text(
        "UPDATE records SET "
        "tenant_id = (SELECT mt.tenant_id FROM meta_tables mt WHERE mt.id = records.table_id), "
        "owner_id = (SELECT mt.owner_id FROM meta_tables mt WHERE mt.id = records.table_id) "
        "WHERE tenant_id IS NULL"
    ))
    conn.execute(text(
        "UPDATE audit_logs SET "
        "tenant_id = (SELECT mt.tenant_id FROM meta_tables mt WHERE mt.id = audit_logs.table_id) "
        "WHERE tenant_id IS NULL AND table_id IS NOT NULL"
    ))
    print("[migrate] v2: tenant_id / owner_id 回填完成", flush=True)

    # 4. 存量 physical 物理表补 tenant_id / owner_id 列并回填
    insp = inspect(conn)
    phys = conn.execute(
        text("SELECT id, name, tenant_id, owner_id FROM meta_tables WHERE storage_mode = 'physical'")
    ).all()
    for mt_id, name, tid, oid in phys:
        existing_cols = {c["name"] for c in insp.get_columns(name)}
        if "tenant_id" not in existing_cols:
            conn.execute(text(f"ALTER TABLE {name} ADD COLUMN tenant_id INTEGER"))
        if "owner_id" not in existing_cols:
            conn.execute(text(f"ALTER TABLE {name} ADD COLUMN owner_id INTEGER"))
        conn.execute(text(f"UPDATE {name} SET tenant_id = :t, owner_id = :o WHERE tenant_id IS NULL"),
                     {"t": tid, "o": oid})
    if phys:
        print(f"[migrate] v2: 物理表结构迁移完成（{len(phys)} 张）", flush=True)

    # 5. 删除 role_permissions 的 max_tables 授权（配额上移 plan_entitlements；权限点行保留）
    conn.execute(text(
        "DELETE FROM role_permissions WHERE permission_id = (SELECT id FROM permissions WHERE code = 'max_tables')"
    ))

    # 6. usage_counters 全量校准
    from sqlalchemy.orm import Session
    from .entitlement import recalibrate_usage
    db = Session(bind=conn)
    try:
        recalibrate_usage(db)
    finally:
        db.close()
    print("[migrate] v2: usage_counters 校准完成", flush=True)


def _migrate_v3_scope_org(conn) -> None:
    """P1 占位迁移：无存量回填（存量无 role_table_scopes 行 → scope 默认 all，行为=现状；
    users.department_id/manager_id 新列 NULL=未分配）。版本行的意义是记录与未来挂载点。"""
    print("[migrate] v3: 数据范围+组织树 schema 就绪（存量 scope 默认 all，零回填）", flush=True)


def _migrate_v4_tenant_roles(conn) -> None:
    """租户自定义角色：老库 roles.code 上有单列唯一索引（建表 unique=True 的产物），
    重建表为 (tenant_id, code) 复合唯一，让不同租户可各自定义同名角色。
    新库 create_all 已按复合唯一建表（无 code 单列唯一索引），自动跳过。"""
    need = False
    for row in conn.execute(text("PRAGMA index_list('roles')")):
        if not row[2]:   # 非唯一索引跳过
            continue
        cols = [r[2] for r in conn.execute(text(f"PRAGMA index_info('{row[1]}')"))]
        if cols == ["code"]:
            need = True
    if not need:
        print("[migrate] v4: roles 已是 (tenant_id, code) 复合唯一，跳过重建", flush=True)
        return
    conn.execute(text("""
        CREATE TABLE roles_v4 (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            code VARCHAR(64) NOT NULL,
            name VARCHAR(64) NOT NULL,
            description VARCHAR(256),
            is_system BOOLEAN,
            tenant_id INTEGER,
            created_at DATETIME,
            CONSTRAINT uq_roles_tenant_code UNIQUE (tenant_id, code),
            FOREIGN KEY(tenant_id) REFERENCES tenants (id)
        )
    """))
    conn.execute(text(
        "INSERT INTO roles_v4 (id, code, name, description, is_system, tenant_id, created_at) "
        "SELECT id, code, name, description, is_system, tenant_id, created_at FROM roles"
    ))
    conn.execute(text("DROP TABLE roles"))
    conn.execute(text("ALTER TABLE roles_v4 RENAME TO roles"))
    conn.execute(text("CREATE INDEX ix_roles_tenant_id ON roles (tenant_id)"))
    print("[migrate] v4: roles 重建完成（code 全局唯一 → (tenant_id, code) 复合唯一）", flush=True)


def _migrate_v5_members_autoinc(conn) -> None:
    """tenant_members 重建为 AUTOINCREMENT 主键：老表是 rowid 表，删行后新行会回收 max(id)+1，
    通知 ref_id（tenant_invitation）等外部引用因此串到新行上（拒绝后再邀请出现两条可操作邀请）。
    新库 create_all 已带 AUTOINCREMENT，自动跳过。"""
    ddl = conn.execute(
        text("SELECT sql FROM sqlite_master WHERE type='table' AND name='tenant_members'")
    ).scalar()
    if ddl and "AUTOINCREMENT" in ddl.upper():
        print("[migrate] v5: tenant_members 已是 AUTOINCREMENT，跳过重建", flush=True)
        return
    conn.execute(text("""
        CREATE TABLE tenant_members_v5 (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role VARCHAR(64),
            status VARCHAR(16),
            invited_by INTEGER,
            created_at DATETIME,
            CONSTRAINT uq_tenant_members UNIQUE (tenant_id, user_id),
            FOREIGN KEY(tenant_id) REFERENCES tenants (id),
            FOREIGN KEY(user_id) REFERENCES users (id),
            FOREIGN KEY(invited_by) REFERENCES users (id)
        )
    """))
    conn.execute(text(
        "INSERT INTO tenant_members_v5 (id, tenant_id, user_id, role, status, invited_by, created_at) "
        "SELECT id, tenant_id, user_id, role, status, invited_by, created_at FROM tenant_members"
    ))
    conn.execute(text("DROP TABLE tenant_members"))
    conn.execute(text("ALTER TABLE tenant_members_v5 RENAME TO tenant_members"))
    conn.execute(text("CREATE INDEX ix_tenant_members_tenant_id ON tenant_members (tenant_id)"))
    conn.execute(text("CREATE INDEX ix_tenant_members_user_id ON tenant_members (user_id)"))
    print("[migrate] v5: tenant_members 重建完成（AUTOINCREMENT，id 不再复用）", flush=True)


def _migrate_v5b_invite_notification_cleanup(conn) -> None:
    """清理 id 复用时代留下的串行邀请通知（独立版本：v5 可能被先行重启的库应用过）。
    判定：邀请通知早于其引用的 membership 创建时间 → 上一个邀请周期的残留。
    注意：悬空 ref（membership 已删）不是垃圾——那是「已拒绝」的留痕，不能清。"""
    r1 = conn.execute(text("""
        DELETE FROM notifications WHERE ref_type = 'tenant_invitation'
        AND ref_id IN (SELECT id FROM tenant_members)
        AND created_at < (SELECT created_at FROM tenant_members WHERE tenant_members.id = notifications.ref_id)
    """))
    print(f"[migrate] v5b: 清理串行邀请通知 {r1.rowcount} 条", flush=True)


def _migrate_v6_drop_vip_role(conn) -> None:
    """删除内置 vip 角色（付费等级概念，已由套餐承接）：
    vip 成员回落为 user；清理 vip 的全部授权与范围/覆盖配置；种子同步移除。"""
    row = conn.execute(text("SELECT id FROM roles WHERE code = 'vip' AND tenant_id IS NULL")).first()
    if not row:
        print("[migrate] v6: vip 角色已不存在，跳过", flush=True)
        return
    vid = row[0]
    n = conn.execute(text("UPDATE tenant_members SET role = 'user' WHERE role = 'vip'")).rowcount
    conn.execute(text("DELETE FROM role_permissions WHERE role_id = :v"), {"v": vid})
    conn.execute(text("DELETE FROM role_table_scopes WHERE role_id = :v"), {"v": vid})
    # P2 新表可能不存在（老库未建）：有则清
    tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
    for t in ("tenant_role_perms", "role_table_perms"):
        if t in tables:
            conn.execute(text(f"DELETE FROM {t} WHERE role_id = :v"), {"v": vid})
    conn.execute(text("DELETE FROM roles WHERE id = :v"), {"v": vid})
    print(f"[migrate] v6: vip 角色已删除（{n} 个成员回落为 user）", flush=True)


# (版本, 迁移函数)——已执行的版本记录在 schema_migrations，跳过
_MIGRATIONS = [
    ("v2_tenants", _migrate_v2_tenants),
    ("v3_scope_org", _migrate_v3_scope_org),
    ("v4_tenant_roles", _migrate_v4_tenant_roles),
    ("v5_members_autoinc", _migrate_v5_members_autoinc),
    ("v5b_invite_notification_cleanup", _migrate_v5b_invite_notification_cleanup),
    ("v6_drop_vip_role", _migrate_v6_drop_vip_role),
]


def _applied_versions(conn) -> set[str]:
    conn.execute(text(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version VARCHAR(64) PRIMARY KEY, applied_at DATETIME)"
    ))
    return {r[0] for r in conn.execute(text("SELECT version FROM schema_migrations")).all()}


def run_migrations(engine: Engine):
    """幂等：缺列则 ALTER + 回填；版本化数据迁移跳过已跑；种子每次启动都跑。需在 _seed_admin 之后调用。"""
    existing = set(inspect(engine).get_table_names())
    pending = [(t, c, ddl) for t, c, ddl in _NEW_COLUMNS if t in existing and c not in _columns(engine, t)]

    with engine.begin() as conn:
        applied = _applied_versions(conn)
    pending_migs = [(v, fn) for v, fn in _MIGRATIONS if v not in applied]

    if pending or pending_migs:
        _backup_sqlite()

    if pending:
        with engine.begin() as conn:
            for t, c, ddl in pending:
                conn.execute(text(f"ALTER TABLE {t} ADD COLUMN {c} {ddl}"))

            # 回填：存量数据归属第一个 admin
            admin = conn.execute(
                text("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1")
            ).first()
            admin_id = admin[0] if admin else None
            if admin_id is not None:
                pending_keys = [(t, c) for t, c, _ in pending]
                if ("meta_tables", "owner_id") in pending_keys:
                    conn.execute(text("UPDATE meta_tables SET owner_id = :uid WHERE owner_id IS NULL"), {"uid": admin_id})
                if ("meta_tables", "storage_mode") in pending_keys:
                    # 存量 dyn_xxx 物理表视为 physical 模式
                    conn.execute(text("UPDATE meta_tables SET storage_mode = 'physical' WHERE storage_mode IS NULL"))
                for t in ("task_rules", "report_templates", "notifications"):
                    if (t, "user_id") in pending_keys:
                        conn.execute(text(f"UPDATE {t} SET user_id = :uid WHERE user_id IS NULL"), {"uid": admin_id})

    # 种子每次启动都跑（幂等）：内置角色/权限 + 套餐/权益
    with engine.begin() as conn:
        if {"roles", "permissions", "role_permissions"} <= existing:
            _seed_rbac(conn)
        _seed_plans(conn)

    # 版本化数据迁移（依赖加列与套餐种子完成）
    for version, fn in pending_migs:
        with engine.begin() as conn:
            fn(conn)
            conn.execute(
                text("INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :t)"),
                {"v": version, "t": datetime.now()},
            )
        print(f"[migrate] 数据迁移 {version} 完成", flush=True)
