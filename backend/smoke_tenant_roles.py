# -*- coding: utf-8 -*-
"""租户自定义角色冒烟：临时库副本上跑迁移 + TestClient 走接口断言。
用法：GRT_DATABASE_URL=sqlite:///<copy.db> python -I smoke_tenant_roles.py"""
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

BASE = Path(__file__).parent
tmp = Path(tempfile.mkdtemp(prefix="grt_roles_test_"))
db_copy = tmp / "test.db"
shutil.copy(BASE / "grt.db", db_copy)
os.environ["GRT_DATABASE_URL"] = f"sqlite:///{db_copy.as_posix()}"

import sys  # noqa: E402
sys.path.insert(0, str(BASE))  # -I 隔离模式下补回项目路径

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402  (启动钩子跑 create_all + migrate)
from app.utils.auth import create_token, hash_password  # noqa: E402

client = TestClient(app)

# ---------- 准备：企业租户 B + 租户 admin u2 + 普通用户 u3 ----------
con = sqlite3.connect(db_copy)
con.execute("INSERT INTO users (username, password_hash, role, is_platform_admin) VALUES ('u2', ?, 'user', 0)",
            (hash_password("pass123456"),))
con.execute("INSERT INTO users (username, password_hash, role, is_platform_admin) VALUES ('u3', ?, 'user', 0)",
            (hash_password("pass123456"),))
u2 = con.execute("SELECT id FROM users WHERE username='u2'").fetchone()[0]
u3 = con.execute("SELECT id FROM users WHERE username='u3'").fetchone()[0]
con.execute("INSERT INTO tenants (name, type, owner_user_id) VALUES ('企业B', 'enterprise', ?)", (u2,))
tb = con.execute("SELECT id FROM tenants WHERE owner_user_id=?", (u2,)).fetchone()[0]
con.execute("INSERT INTO tenant_members (tenant_id, user_id, role, status) VALUES (?, ?, 'admin', 'active')", (tb, u2))
con.execute("INSERT INTO tenant_members (tenant_id, user_id, role, status) VALUES (?, ?, 'user', 'active')", (tb, u3))
legacy = con.execute("SELECT id FROM plans WHERE code='legacy'").fetchone()[0]
con.execute("INSERT INTO subscriptions (tenant_id, plan_id, seats, status) VALUES (?, ?, 2, 'active')", (tb, legacy))
con.commit()
con.close()


def login(username, pwd):
    r = client.post("/api/auth/login", json={"username": username, "password": pwd})
    assert r.status_code == 200, r.text
    return r.json()["token"]


tok_admin = create_token(1)  # 平台超管 token 直接签发，免依赖 admin 密码
tok_u2 = login("u2", "pass123456")
H2 = {"Authorization": f"Bearer {tok_u2}", "X-Tenant-Id": str(tb)}
HA = {"Authorization": f"Bearer {tok_admin}"}

# ---------- 1. 迁移结果：roles 复合唯一 ----------
con = sqlite3.connect(db_copy)
idx_cols = []
for row in con.execute("PRAGMA index_list('roles')"):
    cols = [r[2] for r in con.execute(f"PRAGMA index_info('{row[1]}')")]
    idx_cols.append(cols)
assert ["code"] not in idx_cols, f"code 单列唯一索引仍存在: {idx_cols}"
assert con.execute("SELECT COUNT(*) FROM roles WHERE tenant_id IS NULL").fetchone()[0] == 4
con.close()
print("1. v4 迁移：roles 复合唯一 ✓")

# ---------- 2. 租户 admin 建自定义角色 ----------
r = client.post("/api/roles", json={"code": "sales", "name": "销售"}, headers=H2)
assert r.status_code == 200, r.text
sales = r.json()
assert sales["tenant_id"] == tb
print("2. 租户 admin 创建自定义角色 ✓", sales["id"])

# ---------- 3. 与内置角色重名被拒 ----------
r = client.post("/api/roles", json={"code": "user", "name": "x"}, headers=H2)
assert r.status_code == 400, r.text
print("3. 与内置角色重名 400 ✓")

# ---------- 4. 租户 admin 不能改全局角色 ----------
global_user = client.get("/api/roles", headers=H2).json()
gu = next(x for x in global_user if x["code"] == "user" and x["tenant_id"] is None)
r = client.put(f"/api/roles/{gu['id']}", json={"name": "篡改"}, headers=H2)
assert r.status_code == 403, r.text
r = client.delete(f"/api/roles/{gu['id']}", headers=H2)
assert r.status_code == 403, r.text
print("4. 全局角色对租户 admin 只读 ✓")

# ---------- 5. 租户角色授权 + 成员角色解析（has_perm 按租户隔离） ----------
share_perm = [p for p in client.get("/api/permissions", headers=H2).json() if p["code"] == "share"][0]
r = client.put(f"/api/roles/{sales['id']}/permissions",
               json={"grants": [{"permission_id": share_perm["id"]}]}, headers=H2)
assert r.status_code == 200, r.text
# 把 u3 改为 sales，重新登录看 perms
m3 = client.get("/api/members", headers=H2).json()
m3id = next(m for m in m3 if m["username"] == "u3")["id"]
r = client.put(f"/api/members/{m3id}/role", json={"role": "sales"}, headers=H2)
assert r.status_code == 200, r.text
tok_u3 = login("u3", "pass123456")
me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok_u3}", "X-Tenant-Id": str(tb)}).json()
assert "share" in me["perms"], me["perms"]
print("5. 自定义角色授权生效（成员 perms 含 share）✓")

# ---------- 6. 数据范围矩阵包含自定义角色 ----------
r = client.get("/api/scopes", headers=H2)
assert r.status_code == 200, r.text
assert any(x["code"] == "sales" for x in r.json()["roles"]), r.json()
print("6. 数据范围矩阵含自定义角色 ✓")

# ---------- 7. 使用中角色不可删；移除引用后可删 ----------
r = client.delete(f"/api/roles/{sales['id']}", headers=H2)
assert r.status_code == 400, r.text
client.put(f"/api/members/{m3id}/role", json={"role": "user"}, headers=H2)
r = client.delete(f"/api/roles/{sales['id']}", headers=H2)
assert r.status_code == 200, r.text
print("7. 删除保护 + 删除 ✓")

# ---------- 8. 平台超管列表看全部、可管租户角色 ----------
r = client.post("/api/roles", json={"code": "sales", "name": "销售"}, headers=H2)  # u2 重建一个
sales = r.json()
all_roles = client.get("/api/roles", headers=HA).json()
assert any(x["id"] == sales["id"] for x in all_roles)
r = client.put(f"/api/roles/{sales['id']}", json={"name": "销售（改）"}, headers=HA)
assert r.status_code == 200 and r.json()["name"] == "销售（改）", r.text
print("8. 平台超管可见/可管租户角色 ✓")

# ---------- 9. 无 feature_custom_roles 的租户被拒 ----------
con = sqlite3.connect(db_copy)
con.execute("INSERT INTO users (username, password_hash, role, is_platform_admin) VALUES ('u4', ?, 'user', 0)",
            (hash_password("pass123456"),))
u4 = con.execute("SELECT id FROM users WHERE username='u4'").fetchone()[0]
con.execute("INSERT INTO tenants (name, type, owner_user_id) VALUES ('个人C', 'personal', ?)", (u4,))
tc_ = con.execute("SELECT id FROM tenants WHERE owner_user_id=?", (u4,)).fetchone()[0]
con.execute("INSERT INTO tenant_members (tenant_id, user_id, role, status) VALUES (?, ?, 'admin', 'active')", (tc_, u4))
free = con.execute("SELECT id FROM plans WHERE code='free'").fetchone()[0]
con.execute("INSERT INTO subscriptions (tenant_id, plan_id, seats, status) VALUES (?, ?, 1, 'active')", (tc_, free))
con.commit()
con.close()
tok_u4 = login("u4", "pass123456")
r = client.post("/api/roles", json={"code": "x1", "name": "x"}, headers={"Authorization": f"Bearer {tok_u4}"})
assert r.status_code == 403 and r.json()["detail"]["code"] == "feature_not_available", r.text
print("9. 套餐功能闸（feature_custom_roles）✓")

print("\n全部通过 ✓")
shutil.rmtree(tmp, ignore_errors=True)
