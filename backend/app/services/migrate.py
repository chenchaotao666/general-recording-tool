"""轻量迁移：create_all 只建新表，已有库加列/回填在这里幂等执行（无 alembic 的过渡方案）。"""
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
    """种子角色/权限（幂等）。admin 为代码级超管；vip 可分享+独立表；user 默认限 10 张表"""
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
        ("max_tables", "数据表上限", "可创建数据表的数量上限（数值型权限）"),
    ]
    for code, name, desc in perms:
        conn.execute(
            text("INSERT INTO permissions (code, name, description, is_system) "
                 "SELECT :c, :n, :d, 1 WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :c)"),
            {"c": code, "n": name, "d": desc},
        )
    grants = [
        ("admin", "share", None), ("admin", "create_physical_table", None), ("admin", "max_tables", None),
        ("vip", "share", None), ("vip", "create_physical_table", None),
        ("user", "max_tables", 10),
    ]
    for role_code, perm_code, value in grants:
        conn.execute(
            text("INSERT INTO role_permissions (role_id, permission_id, value) "
                 "SELECT r.id, p.id, :v FROM roles r, permissions p "
                 "WHERE r.code = :rc AND p.code = :pc "
                 "AND NOT EXISTS (SELECT 1 FROM role_permissions WHERE role_id = r.id AND permission_id = p.id)"),
            {"rc": role_code, "pc": perm_code, "v": value},
        )


def run_migrations(engine: Engine):
    """幂等：缺列则 ALTER + 回填；已是最新则空跑。需在 _seed_admin 之后调用（回填依赖 admin）。"""
    existing = set(inspect(engine).get_table_names())
    pending = [(t, c, ddl) for t, c, ddl in _NEW_COLUMNS if t in existing and c not in _columns(engine, t)]
    if pending:
        _backup_sqlite()
        with engine.begin() as conn:
            for t, c, ddl in pending:
                conn.execute(text(f"ALTER TABLE {t} ADD COLUMN {c} {ddl}"))

            # 回填：存量数据归属第一个 admin
            admin = conn.execute(
                text("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1")
            ).first()
            admin_id = admin[0] if admin else None
            if admin_id is None:
                return

            if ("meta_tables", "owner_id") in [(t, c) for t, c, _ in pending]:
                conn.execute(text("UPDATE meta_tables SET owner_id = :uid WHERE owner_id IS NULL"), {"uid": admin_id})
            if ("meta_tables", "storage_mode") in [(t, c) for t, c, _ in pending]:
                # 存量 dyn_xxx 物理表视为 physical 模式
                conn.execute(text("UPDATE meta_tables SET storage_mode = 'physical' WHERE storage_mode IS NULL"))
            for t in ("task_rules", "report_templates", "notifications"):
                if (t, "user_id") in [(x, c) for x, c, _ in pending]:
                    conn.execute(text(f"UPDATE {t} SET user_id = :uid WHERE user_id IS NULL"), {"uid": admin_id})

    # RBAC 种子每次启动都跑（幂等）：内置角色/权限/授权
    if {"roles", "permissions", "role_permissions"} <= existing:
        with engine.begin() as conn:
            _seed_rbac(conn)
