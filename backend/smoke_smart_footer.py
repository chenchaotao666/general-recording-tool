"""冒烟测试：统计行按列统计方式——field-stats 端点 + 通用统计配置校验 + grid 聚合返回。"""
import os

os.environ["GRT_DATABASE_URL"] = "sqlite:///./smoke_smart_footer.db"
if os.path.exists("smoke_smart_footer.db"):
    os.remove("smoke_smart_footer.db")

from fastapi.testclient import TestClient

from app.main import app

cm = TestClient(app)
client = cm.__enter__()
r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
assert r.status_code == 200, r.text
client.headers.update({"Authorization": f"Bearer {r.json()['token']}"})

doc_id = client.get("/api/smart/docs/current").json()["id"]
r = client.post(f"/api/smart/docs/{doc_id}/entries", json={"type": "sheet", "name": "统计行测试"})
table_id = r.json()["table_id"]
meta = client.get(f"/api/smart/entries/{r.json()['entry']['id']}/table").json()
fn = {f["field_type"]: f["field_name"] for f in meta["fields"]}
view_id = client.get(f"/api/smart/tables/{table_id}/views").json()["views"][0]["id"]

# 5 条空行 + 2 条数据：文本列 P001/P001（去重=1），数字 10/20
client.post(f"/api/dyn/{table_id}/records", json={fn["text"]: "P001", fn["number"]: 10, fn["date"]: "2026-01-01"})
client.post(f"/api/dyn/{table_id}/records", json={fn["text"]: "P001", fn["number"]: 20, fn["date"]: "2026-03-05"})

# ---------- field-stats：文本列 ----------
r = client.get(f"/api/smart/tables/{table_id}/field-stats", params={"field_name": fn["text"]})
assert r.status_code == 200, r.text
s = r.json()["stats"]
assert r.json()["total"] == 7
assert s["countRecords"] == 7 and s["count"] == 2 and s["empty"] == 5, s
assert s["distinct"] == 1, s
assert abs(s["filledRatio"] - 2 / 7) < 1e-6 and abs(s["emptyRatio"] - 5 / 7) < 1e-6, s
assert "sum" not in s, "文本列不应有数值统计"
print("field-stats 文本列（行数/填写/去重/占比）通过")

# ---------- field-stats：数字列 + 日期列 ----------
s = client.get(f"/api/smart/tables/{table_id}/field-stats", params={"field_name": fn["number"]}).json()["stats"]
assert s["sum"] == 30 and s["avg"] == 15 and s["max"] == 20 and s["min"] == 10, s
s = client.get(f"/api/smart/tables/{table_id}/field-stats", params={"field_name": fn["date"]}).json()["stats"]
assert s["max"].startswith("2026-03-05") and s["min"].startswith("2026-01-01"), s
print("field-stats 数字列（求和/平均/最值）+ 日期列（最值）通过")

# ---------- 视图 aggregations 配置：通用统计写入 + grid 返回 ----------
r = client.patch(f"/api/smart/views/{view_id}", json={"config": {
    "aggregations": {fn["text"]: "emptyRatio", fn["number"]: "sum", fn["date"]: "max"}}})
assert r.status_code == 200, r.text
g = client.get(f"/api/smart/tables/{table_id}/grid?view_id={view_id}").json()
assert abs(g["aggregations"][fn["text"]] - 5 / 7) < 1e-6, g["aggregations"]
assert g["aggregations"][fn["number"]] == 30 and g["aggregations"][fn["date"]].startswith("2026-03-05")
print("视图 aggregations 通用统计配置 + grid 返回通过")

# 非法：文本列配 sum 仍拒绝
r = client.patch(f"/api/smart/views/{view_id}", json={"config": {"aggregations": {fn["text"]: "sum"}}})
assert r.status_code == 400, r.status_code
print("文本列数值统计拒绝通过")

# 不存在字段 404
r = client.get(f"/api/smart/tables/{table_id}/field-stats", params={"field_name": "nope"})
assert r.status_code == 404, r.status_code
print("field-stats 不存在字段 404 通过")

print("\n统计行按列统计方式冒烟测试通过 [OK]")
cm.__exit__(None, None, None)
