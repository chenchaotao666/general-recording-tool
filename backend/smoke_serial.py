"""冒烟测试：自动编号（serial 字段）——规则模板、计数器发号、重置周期、手改策略、更新不可变。"""
import os
import re
from datetime import datetime

os.environ["GRT_DATABASE_URL"] = "sqlite:///./smoke_serial.db"

from fastapi.testclient import TestClient

from app.main import app

cm = TestClient(app)
client = cm.__enter__()
r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
client.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
now = datetime.now()


def create_table(payload):
    r = client.post("/api/tables", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["table"]["id"]


# ---------- 非法规则拦截 ----------
r = client.post("/api/tables", json={
    "label": "坏编号", "fields": [
        {"field_name": "no", "label": "单号", "data_type": "serial",
         "options": {"serial": {"pattern": "PO-{YYYY}"}}},   # 缺流水占位
    ],
})
assert r.status_code == 400 and "流水占位" in str(r.json().get("detail")), r.text
r = client.post("/api/tables", json={
    "label": "坏编号2", "fields": [
        {"field_name": "no", "label": "单号", "data_type": "serial",
         "options": {"serial": {"reset": "hourly"}}},
    ],
})
assert r.status_code == 400, r.text
print("非法编号规则拦截通过")

# ---------- json 模式：自定义模板 + 每月重置 ----------
t1 = create_table({
    "label": "采购订单-编号", "storage_mode": "json",
    "fields": [
        {"field_name": "order_no", "label": "单号", "data_type": "serial", "widget": "serial",
         "options": {"serial": {"pattern": f"PO{{YYYY}}{{MM}}-{{0000}}", "reset": "monthly"}}},
        {"field_name": "memo", "label": "备注", "data_type": "varchar"},
    ],
})
r1 = client.post(f"/api/dyn/{t1}/records", json={"memo": "第一单"})
assert r1.status_code == 200, r1.text
no1 = r1.json()["order_no"]
assert no1 == f"PO{now:%Y%m}-0001", no1
r2 = client.post(f"/api/dyn/{t1}/records", json={"memo": "第二单", "order_no": "HACK-999"})   # 不允许手改：提交值被忽略
no2 = r2.json()["order_no"]
assert no2 == f"PO{now:%Y%m}-0002", no2
print("json 模式：模板渲染 + 连续发号 + 强制服务端生成通过")

# 更新不可变
rid = r1.json()["id"]
r = client.put(f"/api/dyn/{t1}/records/{rid}", json={"memo": "改名", "order_no": "HACK-000"})
assert r.status_code == 200 and r.json()["order_no"] == no1, r.text
print("更新时编号不可变通过")

# ---------- physical 模式：默认模板（{YYYY}{MM}{DD}{0000}）+ 允许手改 ----------
t2 = create_table({
    "label": "送货单-编号", "storage_mode": "physical",
    "fields": [
        {"field_name": "no", "label": "单号", "data_type": "serial",
         "options": {"serial": {"allow_manual": True}}},
        {"field_name": "memo", "label": "备注", "data_type": "varchar"},
    ],
})
r = client.post(f"/api/dyn/{t2}/records", json={"memo": "手工单", "no": "MANUAL-1"})
assert r.json()["no"] == "MANUAL-1", r.text   # 允许手改时保留提交值
r = client.post(f"/api/dyn/{t2}/records", json={"memo": "自动单"})
assert r.json()["no"] == f"{now:%Y%m%d}0001", r.json()["no"]   # 手改不占流水
r = client.post(f"/api/dyn/{t2}/records", json={"memo": "自动单2"})
assert r.json()["no"] == f"{now:%Y%m%d}0002", r.json()["no"]
print("physical 模式：默认模板 + 允许手改（手工不占流水）通过")

# ---------- {SEQ} 占位（默认 4 位） ----------
t3 = create_table({
    "label": "SEQ占位", "fields": [
        {"field_name": "no", "label": "编号", "data_type": "serial",
         "options": {"serial": {"pattern": "X{YY}{SEQ}"}}},
    ],
})
r = client.post(f"/api/dyn/{t3}/records", json={})
assert r.json()["no"] == f"X{now:%y}0001", r.json()["no"]
print("{SEQ} 占位通过")

for tid in (t1, t2, t3):
    assert client.delete(f"/api/tables/{tid}").status_code == 200
cm.__exit__(None, None, None)
print("✅ 全部通过")
