"""冒烟测试：子表（subform）/ 关联字段（relation-picker + carry_fields）/ 公式字段 / 合计回填。
覆盖 json 与 physical 两种存储模式；不走 LLM。"""
import os

os.environ["GRT_DATABASE_URL"] = "sqlite:///./smoke_subform.db"

from fastapi.testclient import TestClient

from app.main import app

cm = TestClient(app)
client = cm.__enter__()
r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
assert r.status_code == 200, r.text
client.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
print("登录成功")


def create_table(payload):
    r = client.post("/api/tables", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["table"]["id"]


# ---------- 基础资料：供应商 ----------
sup_id = create_table({
    "label": "供应商", "storage_mode": "json",
    "fields": [
        {"field_name": "code", "label": "编号", "data_type": "varchar"},
        {"field_name": "name", "label": "名称", "data_type": "varchar"},
        {"field_name": "address", "label": "地址", "data_type": "varchar"},
        {"field_name": "phone", "label": "电话", "data_type": "varchar"},
    ],
})
r = client.post(f"/api/dyn/{sup_id}/records", json={"code": "00001", "name": "aaa", "address": "东莞", "phone": "139"})
assert r.status_code == 200, r.text
print("供应商表 + 记录就绪")

relation_cfg = {
    "table_id": sup_id, "value_field": "code", "label_field": "name",
    "carry_fields": [{"from": "name", "to": "supplier_name"}, {"from": "address", "to": "supplier_addr"}],
}
subform_columns = [
    {"field_name": "product_code", "label": "产品编号", "data_type": "varchar"},
    {"field_name": "qty", "label": "数量", "data_type": "decimal"},
    {"field_name": "unit_price", "label": "单价", "data_type": "decimal"},
    {"field_name": "amt", "label": "金额", "data_type": "decimal",
     "options": {"formula": "qty * unit_price", "sum_to": "total_amount"}},
]


def order_fields(storage):
    return [
        {"field_name": "supplier_code", "label": "供应商编号", "data_type": "varchar",
         "widget": "relation-picker", "options": {"relation": relation_cfg}},
        {"field_name": "supplier_name", "label": "供应商名称", "data_type": "varchar"},
        {"field_name": "supplier_addr", "label": "地址", "data_type": "varchar"},
        {"field_name": "items", "label": "产品明细", "data_type": "subform",
         "widget": "subform", "options": {"columns": subform_columns}},
        {"field_name": "total_amount", "label": "合计金额", "data_type": "decimal"},
        {"field_name": "tax", "label": "税额", "data_type": "decimal",
         "options": {"formula": "round(total_amount * 0.13, 2)"}},
    ]


# ---------- 非法配置拦截 ----------
bad = client.post("/api/tables", json={
    "label": "坏表", "fields": [
        {"field_name": "x", "label": "x", "data_type": "decimal", "options": {"formula": "ghost_field * 2"}},
    ],
})
assert bad.status_code == 400, bad.text
bad2 = client.post("/api/tables", json={
    "label": "坏表2", "fields": [
        {"field_name": "x", "label": "x", "data_type": "varchar", "widget": "relation-picker",
         "options": {"relation": {"table_id": 99999, "value_field": "code", "label_field": "name"}}},
    ],
})
assert bad2.status_code == 400, bad2.text
bad3 = client.post("/api/tables", json={
    "label": "坏表3", "fields": [
        {"field_name": "s", "label": "s", "data_type": "subform",
         "options": {"columns": [{"field_name": "sub", "label": "嵌套", "data_type": "subform"}]}},
    ],
})
assert bad3.status_code == 400, bad3.text
print("非法配置拦截（公式引用不存在字段/关联不存在表/嵌套子表）通过")

# ---------- json 模式：单据保存时服务端计算 ----------
order_json = create_table({"label": "采购订单-json", "storage_mode": "json", "fields": order_fields("json")})
payload = {
    "supplier_code": "00001",
    "items": [
        {"product_code": "P1", "qty": 2, "unit_price": 10},
        {"product_code": "P2", "qty": 3, "unit_price": 5},
    ],
    "total_amount": 999,   # 客户端乱填也应被服务端合计覆盖
    "tax": 0,
}
r = client.post(f"/api/dyn/{order_json}/records", json=payload)
assert r.status_code == 200, r.text
rec = r.json()
assert rec["items"][0]["amt"] == 20, rec["items"]
assert rec["items"][1]["amt"] == 15, rec["items"]
assert rec["total_amount"] == 35, rec["total_amount"]
assert rec["tax"] == 4.55, rec["tax"]
rid = rec["id"]
print("json 模式：行内公式 + sum_to 合计回填 + 顶层公式（round）通过")

# 更新：改明细行 → 合计与税额级联重算
r = client.put(f"/api/dyn/{order_json}/records/{rid}", json={
    "items": [{"product_code": "P1", "qty": 10, "unit_price": 10}],
})
assert r.status_code == 200, r.text
rec = r.json()
assert rec["total_amount"] == 100 and rec["tax"] == 13.0, rec
# 列表接口返回明细数组
r = client.get(f"/api/dyn/{order_json}/records")
assert r.status_code == 200 and r.json()["items"][0]["items"][0]["amt"] == 100, r.text
print("json 模式：更新级联重算 + 列表返回明细数组通过")

# ---------- physical 模式 ----------
order_phy = create_table({"label": "采购订单-phy", "storage_mode": "physical", "fields": order_fields("phy")})
r = client.post(f"/api/dyn/{order_phy}/records", json=payload)
assert r.status_code == 200, r.text
rec = r.json()
assert rec["items"][0]["amt"] == 20 and rec["total_amount"] == 35 and rec["tax"] == 4.55, rec
rid = rec["id"]
r = client.get(f"/api/dyn/{order_phy}/records/{rid}")
assert r.status_code == 200 and r.json()["items"][1]["amt"] == 15, r.text   # 读出时 JSON 解码还原
r = client.put(f"/api/dyn/{order_phy}/records/{rid}", json={"items": [{"product_code": "P9", "qty": 1, "unit_price": 7.5}]})
assert r.status_code == 200 and r.json()["total_amount"] == 7.5 and r.json()["tax"] == 0.98, r.text
# 明细行类型错误被拦截
r = client.post(f"/api/dyn/{order_phy}/records", json={"items": [{"qty": "abc"}]})
assert r.status_code == 422, r.text
# 导出排除子表列不报 500
r = client.get(f"/api/dyn/{order_phy}/export")
assert r.status_code == 200, r.text
print("physical 模式：写入/读出/更新/校验/导出通过")

# ---------- 清理 ----------
for tid in (order_json, order_phy, sup_id):
    r = client.delete(f"/api/tables/{tid}")
    assert r.status_code == 200, r.text
print("清理完成")

cm.__exit__(None, None, None)
print("✅ 全部通过")
