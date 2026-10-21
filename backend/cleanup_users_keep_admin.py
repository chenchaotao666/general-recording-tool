# -*- coding: utf-8 -*-
"""一次性清理脚本：删除除 admin(id=1) 外的所有用户、其个人租户及全部关联数据。"""
import sqlite3

ADMIN_ID = 1
ADMIN_TENANT = 1

con = sqlite3.connect("grt.db")
con.isolation_level = None  # autocommit off, manual transaction
cur = con.cursor()
cur.execute("PRAGMA foreign_keys = OFF")

try:
    cur.execute("BEGIN IMMEDIATE")

    dead_users = [r[0] for r in cur.execute("SELECT id FROM users WHERE id != ?", (ADMIN_ID,))]
    dead_tenants = [r[0] for r in cur.execute("SELECT id FROM tenants WHERE id != ?", (ADMIN_TENANT,))]
    dead_tables = [r[0] for r in cur.execute(
        "SELECT id FROM meta_tables WHERE tenant_id != ? OR owner_id != ?", (ADMIN_TENANT, ADMIN_ID))]
    dyn_names = [r[0] for r in cur.execute(
        f"SELECT name FROM meta_tables WHERE id IN ({','.join('?'*len(dead_tables))})", dead_tables)] if dead_tables else []
    dead_groups = [r[0] for r in cur.execute(
        f"SELECT id FROM groups WHERE tenant_id IN ({','.join('?'*len(dead_tenants))})", dead_tenants)] if dead_tenants else []
    dead_rules = [r[0] for r in cur.execute(
        f"SELECT id FROM task_rules WHERE table_id IN ({','.join('?'*len(dead_tables))}) OR user_id != ?", (*dead_tables, ADMIN_ID))] if dead_tables else \
        [r[0] for r in cur.execute("SELECT id FROM task_rules WHERE user_id != ?", (ADMIN_ID,))]
    dead_reports = [r[0] for r in cur.execute("SELECT id FROM report_templates WHERE user_id != ?", (ADMIN_ID,))]

    def in_list(ids):
        return ",".join("?" * len(ids))

    def exec_(label, sql, params=()):
        cur.execute(sql, params)
        print(f"{label}: {cur.rowcount} rows")

    # 2. 任务规则日志 -> 规则
    if dead_rules:
        exec_("task_run_logs", f"DELETE FROM task_run_logs WHERE rule_id IN ({in_list(dead_rules)})", dead_rules)
        exec_("task_trigger_logs", f"DELETE FROM task_trigger_logs WHERE rule_id IN ({in_list(dead_rules)})", dead_rules)
        exec_("task_rules", f"DELETE FROM task_rules WHERE id IN ({in_list(dead_rules)})", dead_rules)

    # 3. 报表模板及运行日志
    if dead_reports:
        exec_("report_run_logs", f"DELETE FROM report_run_logs WHERE template_id IN ({in_list(dead_reports)})", dead_reports)
        exec_("report_templates", f"DELETE FROM report_templates WHERE id IN ({in_list(dead_reports)})", dead_reports)

    # 4. 打印模板 / 表分享 / 分享链接
    exec_("print_templates", "DELETE FROM print_templates WHERE user_id != ?", (ADMIN_ID,))
    if dead_tables:
        exec_("table_shares", f"DELETE FROM table_shares WHERE table_id IN ({in_list(dead_tables)}) OR user_id != ? OR shared_by != ?", (*dead_tables, ADMIN_ID, ADMIN_ID))
        exec_("shared_links", f"DELETE FROM shared_links WHERE created_by != ? OR (resource_type='table' AND resource_id IN ({in_list(dead_tables)}))", (ADMIN_ID, *dead_tables))

    # 5. 动态表子数据
    if dead_tables:
        for t, fk in [("serial_counters", "table_id"), ("vision_logs", "table_id"),
                      ("import_batches", "table_id"), ("meta_fields", "table_id"),
                      ("records", "table_id")]:
            exec_(t, f"DELETE FROM {t} WHERE {fk} IN ({in_list(dead_tables)})", dead_tables)
        exec_("role_table_scopes", f"DELETE FROM role_table_scopes WHERE table_id IN ({in_list(dead_tables)}) OR tenant_id != ?", (*dead_tables, ADMIN_TENANT))
        exec_("meta_tables", f"DELETE FROM meta_tables WHERE id IN ({in_list(dead_tables)})", dead_tables)

    # 6. 删除被清租户的动态物理表
    for name in dyn_names:
        exists = cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
        if exists:
            cur.execute(f'DROP TABLE "{name}"')
            print(f"dropped dyn table: {name}")

    # 7. 群组
    if dead_groups:
        exec_("group_members", f"DELETE FROM group_members WHERE group_id IN ({in_list(dead_groups)})", dead_groups)
        exec_("groups", f"DELETE FROM groups WHERE id IN ({in_list(dead_groups)})", dead_groups)
    exec_("group_members(orphan)", f"DELETE FROM group_members WHERE user_id != ?", (ADMIN_ID,))

    # 8. 用户级数据
    exec_("friendships", "DELETE FROM friendships WHERE requester_id != ? OR addressee_id != ?", (ADMIN_ID, ADMIN_ID))
    exec_("notes", "DELETE FROM notes WHERE user_id != ?", (ADMIN_ID,))
    exec_("home_layouts", "DELETE FROM home_layouts WHERE user_id != ?", (ADMIN_ID,))
    exec_("notifications", "DELETE FROM notifications WHERE user_id != ?", (ADMIN_ID,))
    exec_("departments", "DELETE FROM departments WHERE tenant_id != ?", (ADMIN_TENANT,))

    # 9. 租户级商业化数据
    exec_("orders", "DELETE FROM orders WHERE tenant_id != ?", (ADMIN_TENANT,))
    exec_("subscriptions", "DELETE FROM subscriptions WHERE tenant_id != ?", (ADMIN_TENANT,))
    exec_("usage_counters", "DELETE FROM usage_counters WHERE tenant_id != ?", (ADMIN_TENANT,))
    exec_("tenant_members", "DELETE FROM tenant_members WHERE tenant_id != ?", (ADMIN_TENANT,))
    exec_("audit_logs", "DELETE FROM audit_logs WHERE tenant_id IS NOT NULL AND tenant_id != ?", (ADMIN_TENANT,))

    # 10. 租户与用户
    exec_("tenants", "DELETE FROM tenants WHERE id != ?", (ADMIN_TENANT,))
    exec_("users", "DELETE FROM users WHERE id != ?", (ADMIN_ID,))

    cur.execute("COMMIT")
    print("\nCOMMIT OK")
except Exception:
    cur.execute("ROLLBACK")
    raise
finally:
    con.close()
