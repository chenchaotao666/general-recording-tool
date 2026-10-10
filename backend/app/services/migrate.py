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
        ("vip", "VIP", "可分享数据表、可创建独立物理表"),
        ("user", "普通用户", "默认角色"),
    ]
    for code, name, desc in roles:
        conn.execute(
            text("INSERT INTO roles (code, name, description, is_system) "
                 "SELECT :c, :n, :d, 1 WHERE NOT EXISTS (SELECT 1 FROM roles WHERE code = :c)"),
            {"c": code, "n": name, "d": desc},
        )
    perms = [
        ("share", "分享", "把数据表分享给其他用户"),
        ("create_physical_table", "创建独立表", "建表时可选独立物理表存储（数据量大/报表重的表）"),
        ("max_tables", "数据表上限", "已废弃：配额由套餐 plan_entitlements 承接（保留行防外键断链）"),
    ]
    for code, name, desc in perms:
        conn.execute(
            text("INSERT INTO permissions (code, name, description, is_system) "
                 "SELECT :c, :n, :d, 1 WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :c)"),
            {"c": code, "n": name, "d": desc},
        )
    grants = [
        ("admin", "share", None), ("admin", "create_physical_table", None),
        ("vip", "share", None), ("vip", "create_physical_table", None),
    ]
    for role_code, perm_code, value in grants:
        conn.execute(
            text("INSERT INTO role_permissions (role_id, permission_id, value) "
                 "SELECT r.id, p.id, :v FROM roles r, permissions p "
                 "WHERE r.code = :rc AND p.code = :pc "
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
        "feature_audit": 1, "audit_retention_days": 90}),
    ("ent_flagship", "企业旗舰版", "enterprise", None, 40000, 22, True, {
        "max_rows": 5000000, "max_storage_mb": 512000, "min_seats": 5,
        "quota_grace_days": 7, "sub_grace_days": 7,
        "feature_print_templates": 1, "feature_data_scope": 1, "feature_owd": 1,
        "feature_share_rules": 1, "feature_perm_diagnose": 1, "feature_field_perm": 1,
        "feature_audit": 1, "feature_automation": 1, "feature_api": 1}),
    ("private", "私有化部署", "private", None, None, 90, False, {
        "quota_grace_days": 7, "sub_grace_days": 7,
        "feature_print_templates": 1, "feature_data_scope": 1, "feature_owd": 1,
        "feature_share_rules": 1, "feature_perm_diagnose": 1, "feature_field_perm": 1,
        "feature_audit": 1, "feature_automation": 1, "feature_api": 1}),
    # 存量迁移隐藏档：全不限 + 功能全开，保证老用户迁移零锁死（不对外售卖）
    ("legacy", "存量迁移档", "individual", 0, 0, 99, False, {
        "quota_grace_days": 7, "sub_grace_days": 7,
        "feature_print_templates": 1, "feature_data_scope": 1, "feature_owd": 1,
        "feature_share_rules": 1, "feature_perm_diagnose": 1, "feature_field_perm": 1,
        "feature_audit": 1, "feature_automation": 1, "feature_api": 1}),
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


# (版本, 迁移函数)——已执行的版本记录在 schema_migrations，跳过
_MIGRATIONS = [
    ("v2_tenants", _migrate_v2_tenants),
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
