"""冒烟测试：智能表 V1 后端链路——默认文档、工作表模板、视图 CRUD、个人覆盖、
字段依赖扫描、grid 多级排序与聚合、json 类型 coerce、条目移动防环、文件夹非空拒绝。"""
import os

os.environ["GRT_DATABASE_URL"] = "sqlite:///./smoke_smart.db"
# 清库保证幂等
if os.path.exists("smoke_smart.db"):
    os.remove("smoke_smart.db")

from fastapi.testclient import TestClient

from app.main import app

cm = TestClient(app)
client = cm.__enter__()
r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
assert r.status_code == 200, r.text
client.headers.update({"Authorization": f"Bearer {r.json()['token']}"})

# ---------- 默认文档：惰性创建 + 幂等 ----------
r1 = client.get("/api/smart/docs/current")
assert r1.status_code == 200, r1.text
doc_id = r1.json()["id"]
r2 = client.get("/api/smart/docs/current")
assert r2.json()["id"] == doc_id, "默认文档应幂等"
print("默认文档惰性创建 + 幂等通过")

# ---------- 新建工作表（默认 5 字段 + 5 空行 + 默认视图） ----------
r = client.post(f"/api/smart/docs/{doc_id}/entries", json={"type": "sheet", "name": "产品明细"})
assert r.status_code == 200, r.text
entry = r.json()["entry"]
table_id = r.json()["table_id"]
assert entry["type"] == "sheet" and entry["ref_table_id"] == table_id

r = client.get(f"/api/smart/entries/{entry['id']}/table")
meta = r.json()
assert [f["field_type"] for f in meta["fields"]] == ["text", "singleSelect", "member", "number", "date"], meta["fields"]
print("工作表默认字段模板通过（text/singleSelect/member/number/date）")

r = client.get(f"/api/smart/tables/{table_id}/views")
views = r.json()["views"]
assert len(views) == 1 and views[0]["is_default"]
view_id = views[0]["id"]
print("默认视图创建通过")

r = client.get(f"/api/smart/tables/{table_id}/grid")
g = r.json()
assert g["total"] == 5 and len(g["items"]) == 5, g["total"]
print("默认 5 空行通过")

# ---------- 记录 CRUD 复用 dyn 端点 + json 类型 coerce ----------
fn = {f["field_type"]: f["field_name"] for f in meta["fields"]}
rec = {fn["text"]: "P001", fn["singleSelect"]: "opt_1", fn["number"]: 12800.5,
       fn["member"]: [1, 2], fn["date"]: "2026-10-12"}
r = client.post(f"/api/dyn/{table_id}/records", json=rec)
assert r.status_code == 200, r.text
rid = r.json()["record"]["id"] if "record" in r.json() else r.json().get("id")
# 再补一条不同排序值的
client.post(f"/api/dyn/{table_id}/records", json={fn["text"]: "P002", fn["number"]: 100, fn["member"]: [2]})
print("记录创建（含 json 复合值 member 数组）通过")

# ---------- 视图 config：筛选 + 多级排序 + 聚合 ----------
r = client.patch(f"/api/smart/views/{view_id}", json={"config": {
    "filters": {"conjunction": "and", "conditions": [
        {"id": "c1", "fieldId": fn["number"], "operator": "gte", "value": 50}]},
    "sorts": [{"fieldId": fn["number"], "direction": "desc"}, {"fieldId": fn["text"], "direction": "asc"}],
    "aggregations": {fn["number"]: "sum"},
    "rowHeight": "medium",
}})
assert r.status_code == 200, r.text
r = client.get(f"/api/smart/tables/{table_id}/grid?view_id={view_id}")
g = r.json()
assert g["total"] == 2 and g["items"][0][fn["text"]] == "P001", (g["total"], g["items"])
assert g["aggregations"][fn["number"]] == 12800.5 + 100, g["aggregations"]
assert g["view"]["config"]["rowHeight"] == "medium"
print("视图筛选 + 多级排序 + 聚合通过")

# 非法配置拦截
r = client.patch(f"/api/smart/views/{view_id}", json={"config": {
    "filters": {"conditions": [{"fieldId": "nope", "operator": "eq", "value": 1}]}}})
assert r.status_code == 400, r.text
r = client.patch(f"/api/smart/views/{view_id}", json={"config": {
    "aggregations": {fn["text"]: "sum"}}})
assert r.status_code == 400 and "聚合" in str(r.json().get("detail")), r.text
print("非法视图配置拦截通过")

# 数组筛选语义：member contains = 交集非空
client.patch(f"/api/smart/views/{view_id}", json={"config": {
    "filters": {"conjunction": "and", "conditions": [
        {"id": "c1", "fieldId": fn["member"], "operator": "contains", "value": [1]}]}}})
r = client.get(f"/api/smart/tables/{table_id}/grid?view_id={view_id}")
assert r.json()["total"] == 1 and r.json()["items"][0][fn["text"]] == "P001"
print("数组字段 contains（交集）筛选通过")

# ---------- 个人覆盖（仅你可见） ----------
r = client.put(f"/api/smart/views/{view_id}/prefs", json={"config": {
    "filters": {"conjunction": "and", "conditions": []}}})
assert r.status_code == 200, r.text
r = client.get(f"/api/smart/tables/{table_id}/grid?view_id={view_id}")
assert r.json()["total"] == 7 and r.json()["view"]["config"].get("filtersScope") == "personal"
print("个人覆盖 filters 替换语义通过")
client.delete(f"/api/smart/views/{view_id}/prefs")
r = client.get(f"/api/smart/tables/{table_id}/grid?view_id={view_id}")
assert r.json()["total"] == 1, "删除覆盖后应回到视图筛选"

# ---------- 字段删除依赖 ----------
r = client.get(f"/api/smart/tables/{table_id}/fields/{fn['member']}/deps")
deps = r.json()["deps"]
assert deps and "筛选" in deps[0]["usages"], deps
print("字段删除依赖扫描通过")

# ---------- 视图 CRUD：复制/设默认/最后一视图保护 ----------
r = client.post(f"/api/smart/views/{view_id}/duplicate")
v2 = r.json()["view"]["id"]
r = client.delete(f"/api/smart/views/{view_id}")
assert r.status_code == 200
r = client.delete(f"/api/smart/views/{v2}")
assert r.status_code == 400 and "至少保留一个视图" in str(r.json().get("detail"))
print("视图复制/删除/最后保护通过")

# ---------- 条目树：文件夹、移动防环、非空拒绝 ----------
r = client.post(f"/api/smart/docs/{doc_id}/entries", json={"type": "folder", "name": "文件夹1"})
f1 = r.json()["entry"]["id"]
r = client.post(f"/api/smart/docs/{doc_id}/entries", json={"type": "folder", "name": "文件夹2", "parent_id": f1})
f2 = r.json()["entry"]["id"]
r = client.patch(f"/api/smart/entries/{f1}", json={"parent_id": f2})
assert r.status_code == 400 and "子文件夹" in str(r.json().get("detail")), r.text
r = client.delete(f"/api/smart/entries/{f1}")
assert r.status_code == 409, r.text
r = client.delete(f"/api/smart/entries/{f2}")
assert r.status_code == 200
r = client.delete(f"/api/smart/entries/{f1}")
assert r.status_code == 200
print("文件夹嵌套/防环/非空拒绝通过")

# ---------- 引用选项 + 选项联动 config 校验（设计文档 §3.3） ----------
# 默认模板字段：f_1 text / f_2 singleSelect / f_3 member / f_4 number / f_5 date
r = client.post(f"/api/smart/docs/{doc_id}/entries", json={"type": "sheet", "name": "需求池"})
ref_table_id = r.json()["table_id"]


def add_ref_field(ref_cfg):
    return client.post(f"/api/tables/{table_id}/alter", json={"ops": [{
        "op": "add_field",
        "field": {"field_name": "f_ref", "label": "引用单选", "data_type": "varchar", "widget": "select",
                  "nullable": True, "field_type": "singleSelect",
                  "options": {"options": [], **ref_cfg}},
    }]})


# 反例：引用不存在的表 → 400
r = add_ref_field({"optionSource": "reference", "reference": {"tableId": 99999, "fieldId": "f_2"}})
assert r.status_code == 400, r.text
# 反例：引用非单选/多选字段（f_1 是 text）→ 400
r = add_ref_field({"optionSource": "reference", "reference": {"tableId": ref_table_id, "fieldId": "f_1"}})
assert r.status_code == 400, r.text
# 反例：联动条件 operator 一期仅支持「等于」→ 400
r = add_ref_field({"optionSource": "reference", "reference": {"tableId": ref_table_id, "fieldId": "f_2"},
                   "optionLinkage": {"enabled": True, "match": "all", "conditions": [
                       {"localFieldId": "f_1", "operator": "ne", "remoteFieldId": "f_1"}]}})
assert r.status_code == 400, r.text
# 反例：非引用模式带联动 → 400
r = add_ref_field({"optionSource": "manual", "optionLinkage": {"enabled": True, "match": "all", "conditions": []}})
assert r.status_code == 400, r.text
# 正例：合法引用 + 联动 → 200
r = add_ref_field({"optionSource": "reference", "reference": {"tableId": ref_table_id, "fieldId": "f_2"},
                   "optionLinkage": {"enabled": True, "match": "any", "conditions": [
                       {"localFieldId": "f_1", "operator": "eq", "remoteFieldId": "f_1"}]}})
assert r.status_code == 200, r.text
print("引用选项/选项联动校验通过（4 反例 + 1 正例）")

# 清理：删本表新增字段与引用表条目，避免影响后续用例
r = client.post(f"/api/tables/{table_id}/alter", json={"ops": [{"op": "delete_field", "field_name": "f_ref"}]})
assert r.status_code == 200, r.text
r = client.get(f"/api/smart/docs/{doc_id}/tree")
for e in r.json()["entries"]:
    if e["name"] == "需求池":
        client.delete(f"/api/smart/entries/{e['id']}")

# ---------- sheet 条目删除级联删表 ----------
r = client.delete(f"/api/smart/entries/{entry['id']}")
assert r.status_code == 200, r.text
r = client.get(f"/api/smart/tables/{table_id}/views")
assert r.status_code == 404, "级联删表后视图应 404"
print("sheet 级联删除通过")

cm.__exit__(None, None, None)
print("\n全部智能表 V1 冒烟测试通过 [OK]")
