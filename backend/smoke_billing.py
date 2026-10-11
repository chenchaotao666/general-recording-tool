"""冒烟测试：商业化链路 —— 续费时长累加 + 待支付订单取消。用独立测试库，不污染 grt.db。"""
import os
import sys

os.environ["GRT_DATABASE_URL"] = "sqlite:///./smoke_billing.db"
if os.path.exists("smoke_billing.db"):
    os.remove("smoke_billing.db")

from fastapi.testclient import TestClient

from app.main import app

cm = TestClient(app)
client = cm.__enter__()
r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
assert r.status_code == 200, r.text
client.headers.update({"Authorization": f"Bearer {r.json()['token']}"})

# 1. 套餐列表：带折扣档位下发
r = client.get("/api/billing/plans")
assert r.status_code == 200, r.text
body = r.json()
assert "seat_discount_tiers" in body and body["seat_discount_tiers"], body
plans = body["plans"]
assert plans, "没有可选购套餐"
plan = plans[-1]   # 取最后一档（通常是付费档）
MIN_SEATS = (plan.get("entitlements") or {}).get("min_seats") or 1
print(f"1. 套餐列表 OK（{len(plans)} 档，折扣档位 {body['seat_discount_tiers']}）")

# 2. 下单并支付（首次购买）
def buy(years=1):
    r = client.post("/api/billing/orders", json={"plan_code": plan["code"], "seats": MIN_SEATS, "years": years})
    assert r.status_code == 200, r.text
    order = r.json()
    r = client.post(f"/api/billing/orders/{order['id']}/pay")
    assert r.status_code == 200, r.text
    return order

o1 = buy(years=1)
r = client.get("/api/tenants/current")
sub1 = r.json()["subscription"]
exp1 = sub1["expires_at"]
print(f"2. 首次购买 OK，到期时间 {exp1}")

# 3. 续费同档：时长应顺延累加（≈ +1 年），订单 kind=renewal
o2 = buy(years=1)
assert o2["kind"] == "renewal", o2
r = client.get("/api/tenants/current")
exp2 = r.json()["subscription"]["expires_at"]
from datetime import datetime
d1 = datetime.fromisoformat(exp1)
d2 = datetime.fromisoformat(exp2)
delta_days = (d2 - d1).days
assert 364 <= delta_days <= 366, f"续费只加了 {delta_days} 天"
print(f"3. 续费累加 OK（kind=renewal，+{delta_days} 天）")

# 4. 待支付订单：可取消；取消后不能再支付/再取消
r = client.post("/api/billing/orders", json={"plan_code": plan["code"], "seats": MIN_SEATS, "years": 1})
o3 = r.json()
r = client.post(f"/api/billing/orders/{o3['id']}/cancel")
assert r.status_code == 200 and r.json()["status"] == "cancelled", r.text
r = client.post(f"/api/billing/orders/{o3['id']}/pay")
assert r.status_code == 400, r.text
r = client.post(f"/api/billing/orders/{o3['id']}/cancel")
assert r.status_code == 400, r.text
print("4. 取消订单 OK（取消后禁止支付/重复取消）")

# 5. 订单列表带 kind 字段
r = client.get("/api/billing/orders")
kinds = {o["id"]: o.get("kind") for o in r.json()}
assert kinds.get(o2["id"]) == "renewal" and kinds.get(o3["id"]) == "renewal", kinds
print("5. 订单列表 kind 标记 OK")

print("\n全部通过 ✅")
cm.__exit__(None, None, None)
sys.exit(0)
