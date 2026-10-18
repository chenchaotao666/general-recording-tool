"""冒烟测试：智能表 V2——分组、查找引用、公式、自动编号、进度、系统字段、
查找替换、记录/字段副本、列编组、仪表盘图表聚合、Excel 导入、树形子记录。"""
import os

os.environ["GRT_DATABASE_URL"] = "sqlite:///./smoke_smart2.db"
if os.path.exists("smoke_smart2.db"):
    os.remove("smoke_smart2.db")

from fastapi.testclient import TestClient

from app.main import app

cm = TestClient(app)
client = cm.__enter__()
r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
assert r.status_code == 200, r.text
client.headers.update({"Authorization": f"Bearer {r.json()['token']}"})

doc_id = client.get("/api/smart/docs/current").json()["id"]


def new_sheet(name):
    r = client.post(f"/api/smart/docs/{doc_id}/entries", json={"type": "sheet", "name": name})
    assert r.status_code == 200, r.text
    return r.json()["entry"], r.json()["table_id"]


def add_field(tid, field_type, label, config=None):
    """经 alter 端点加智能表字段（field_registry.to_field_in 生成定义）。"""
    from app.services.field_registry import to_field_in
    r = client.get(f"/api/tables/{tid}")
    names = {f["field_name"] for f in r.json()["fields"]}
    n = 1
    while f"f_{n}" in names:
        n += 1
    fin = to_field_in(field_type, label, f"f_{n}", config)
    r = client.post(f"/api/tables/{tid}/alter", json={"ops": [{"op": "add_field", "field": fin}]})
    assert r.status_code == 200, r.text
    return f"f_{n}"


# ---------- 建两张表：需求池（被引用）+ 明细表 ----------
e1, t1 = new_sheet("需求池")
f1 = {f["field_type"]: f["field_name"] for f in client.get(f"/api/tables/{t1}").json()["fields"]}
client.post(f"/api/smart/tables/{t1}/records", json={"data": {f1["text"]: "登录优化", f1["number"]: 10}})
client.post(f"/api/smart/tables/{t1}/records", json={"data": {f1["text"]: "报表导出", f1["number"]: 20}})
client.post(f"/api/smart/tables/{t1}/records", json={"data": {f1["text"]: "权限梳理", f1["number"]: 30}})

e2, t2 = new_sheet("产品明细")
f2 = {f["field_type"]: f["field_name"] for f in client.get(f"/api/tables/{t2}").json()["fields"]}
client.post(f"/api/smart/tables/{t2}/records", json={"data": {f2["text"]: "P001", f2["singleSelect"]: "opt_1", f2["number"]: 100}})
client.post(f"/api/smart/tables/{t2}/records", json={"data": {f2["text"]: "P002", f2["singleSelect"]: "opt_2", f2["number"]: 200}})
r3 = client.post(f"/api/smart/tables/{t2}/records", json={"data": {f2["text"]: "P003", f2["singleSelect"]: "opt_1", f2["number"]: 300}})
rid3 = r3.json()["record"]["id"]

# ---------- V2 字段类型：进度/公式/自动编号/关联/查找引用/系统字段 ----------
fp = add_field(t2, "progress", "进度")
ff = add_field(t2, "formula", "双倍", {"formula": f"[{f2['number']}] * 2", "returnType": "number"})
fa = add_field(t2, "autoNumber", "编号", {"numberType": "custom", "segments": [
    {"type": "fixedText", "text": "NO-"}, {"type": "autoIncrement", "digits": 3}]})
fr = add_field(t2, "relation", "关联需求", {"targetTableId": t1, "multiple": True})
fl = add_field(t2, "lookup", "需求数统计", {"sourceTableId": t1, "sourceFieldId": f1["number"],
                                            "conditionLogic": "and", "conditions": [], "aggregation": "sum"})
fcb = add_field(t2, "createdBy", "创建人")
fct = add_field(t2, "createdTime", "创建时间")
print("V2 字段类型建列通过（progress/formula/autoNumber/relation/lookup/系统字段）")

# 公式写时重算 + 自动编号发号
r = client.post(f"/api/smart/tables/{t2}/records", json={"data": {f2["text"]: "P004", f2["number"]: 50, fp: 60}})
rec = r.json()["record"]
assert float(rec[ff]) == 100, rec   # 公式写时重算（expr.py 引擎）
assert rec[fa] and rec[fa].startswith("NO-"), rec[fa]
assert rec[fcb], "系统字段创建人应注入"
print(f"公式重算（{rec[ff]}）+ 自动编号（{rec[fa]}）+ 系统字段注入通过")

# 只读字段写入拦截
r = client.post(f"/api/smart/tables/{t2}/records", json={"data": {f2["text"]: "P005", ff: "999", fcb: "x"}})
assert r.json()["record"][ff] != "999" and r.json()["record"][fcb] != "x"
print("只读字段写入拦截通过")

# 关联 + 查找引用
t1_rows = client.get(f"/api/smart/tables/{t1}/grid").json()["items"]
t1_ids = [x["id"] for x in t1_rows]
client.patch(f"/api/smart/tables/{t2}/records/{rid3}", json={"data": {fr: t1_ids[:2]}})
g = client.get(f"/api/smart/tables/{t2}/grid").json()
row3 = next(x for x in g["items"] if x["id"] == rid3)
assert row3[fr] == t1_ids[:2], row3[fr]
assert row3[fl] == 60, row3[fl]   # 无条件 lookup sum：10+20+30
print("关联赋值 + 查找引用（无条件 sum=60）通过")

# lookup 条件匹配：源表 文本 == 本行 P003 不存在的场景走空
fl2 = add_field(t2, "lookup", "按名匹配", {"sourceTableId": t1, "sourceFieldId": f1["number"],
                                           "conditionLogic": "and", "aggregation": "count",
                                           "conditions": [{"sourceFieldId": f1["text"], "op": "eq",
                                                           "rightFieldId": f2["text"]}]})
g = client.get(f"/api/smart/tables/{t2}/grid").json()
row3 = next(x for x in g["items"] if x["id"] == rid3)
assert row3[fl2] == 0, row3[fl2]   # 需求池无「P003」
print("查找引用条件匹配（count=0）通过")

# ---------- 分组 ----------
vid = client.get(f"/api/smart/tables/{t2}/views").json()["views"][0]["id"]
r = client.patch(f"/api/smart/views/{vid}", json={"config": {
    "groups": [{"fieldId": f2["singleSelect"], "direction": "asc"}],
    "aggregations": {f2["number"]: "sum"}}})
assert r.status_code == 200, r.text
g = client.get(f"/api/smart/tables/{t2}/grid?view_id={vid}").json()
assert g["grouped"] is True
gh = [x for x in g["items"] if x.get("__rowType") == "group"]
assert len(gh) >= 2 and gh[0]["count"] > 0 and gh[0]["aggs"].get(f2["number"]) is not None, gh
print(f"分组渲染通过（{len(gh)} 组，组内聚合求和 {gh[0]['aggs']}）")

# ---------- 树形子记录 ----------
r = client.post(f"/api/smart/tables/{t2}/records", json={"data": {f2["text"]: "P003-子"}, "parent_id": rid3})
child_id = r.json()["record"]["id"]
assert r.json()["record"]["parent_id"] == rid3
r = client.patch(f"/api/smart/tables/{t2}/records/{rid3}", json={"parent_id": child_id})
assert r.status_code == 400 and "环" in str(r.json().get("detail")), r.text
r = client.delete(f"/api/smart/tables/{t2}/records/{rid3}")
assert r.json()["orphans_lifted"] == 1
g2 = client.get(f"/api/smart/tables/{t2}/grid").json()
child = next(x for x in g2["items"] if x.get("__rowType") != "group" and x.get("id") == child_id)
assert child["parent_id"] is None, "孤子应上提到顶层"
print("树形子记录（建子/防环/孤子上提）通过")

# ---------- 查找替换 ----------
r = client.post(f"/api/smart/tables/{t2}/search-replace", json={"find": "P00"})
assert r.json()["matches"], r.text
r = client.post(f"/api/smart/tables/{t2}/search-replace", json={"find": "P002", "replace": "Q002", "replace_all": True})
assert r.json()["replaced"] >= 1
g = client.get(f"/api/smart/tables/{t2}/grid").json()
assert any(x.get("__rowType") != "group" and x.get(f2["text"]) == "Q002" for x in g["items"])

# 文本公式可查找但不可替换；匹配与实际替换统一为大小写不敏感。
ftext = add_field(t2, "formula", "文本公式", {"formula": f"[{f2['text']}]", "returnType": "text"})
case_ids = []
for _ in range(2):
    r = client.post(f"/api/smart/tables/{t2}/records", json={"data": {f2["text"]: "MixedCaseToken"}})
    assert r.status_code == 200 and r.json()["record"][ftext] == "MixedCaseToken", r.text
    case_ids.append(r.json()["record"]["id"])
r = client.post(f"/api/smart/tables/{t2}/search-replace", json={"find": "mixedcasetoken"})
case_matches = [m for m in r.json()["matches"] if m["recordId"] in case_ids]
assert any(m["field"] == f2["text"] and m["replaceable"] for m in case_matches), r.text
formula_match = next(m for m in case_matches if m["field"] == ftext)
assert formula_match["fieldType"] == "formula" and not formula_match["replaceable"]
assert formula_match["blockedReason"] == "type"

# 单个替换只写指定文本单元格，并返回撤销所需的实际前后值。
r = client.post(f"/api/smart/tables/{t2}/search-replace", json={
    "find": "mixedcasetoken", "replace": "SingleReplaced", "replace_current": True,
    "record_id": case_ids[0], "field": f2["text"]})
assert r.status_code == 200 and r.json()["replacedCells"] == 1, r.text
assert r.json()["changes"] == [{"recordId": case_ids[0], "field": f2["text"],
                                "before": "MixedCaseToken", "after": "SingleReplaced"}]
r = client.post(f"/api/smart/tables/{t2}/search-replace", json={
    "find": "mixedcasetoken", "replace": "Forbidden", "replace_current": True,
    "record_id": case_ids[1], "field": ftext})
assert r.status_code == 403, r.text

# 全部替换跳过公式命中，返回部分失败数量；文本仍按大小写不敏感完成替换。
r = client.post(f"/api/smart/tables/{t2}/search-replace", json={
    "find": "mixedcasetoken", "replace": "AllReplaced", "replace_all": True})
assert r.status_code == 200 and r.json()["replacedCells"] == 1, r.text
assert r.json()["skipped"] >= 1 and all(c["field"] != ftext for c in r.json()["changes"]), r.text
g = client.get(f"/api/smart/tables/{t2}/grid").json()
case_rows = [x for x in g["items"] if x.get("id") in case_ids]
assert any(x.get(f2["text"]) == "SingleReplaced" for x in case_rows)
assert any(x.get(f2["text"]) == "AllReplaced" for x in case_rows)
print("查找替换（只读命中/单个/全部/大小写/部分跳过）通过")

# ---------- 记录副本 + 字段副本 ----------
rid_any = next(x["id"] for x in g["items"] if x.get("__rowType") != "group")
r = client.post(f"/api/smart/tables/{t2}/records/{rid_any}/duplicate")
assert r.status_code == 200 and r.json()["record"]["id"] != rid_any
r = client.post(f"/api/smart/tables/{t2}/fields/{f2['text']}/duplicate")
assert "副本" in r.json()["label"]
print("记录副本 + 字段副本通过")

# ---------- 列编组 ----------
r = client.post(f"/api/smart/tables/{t2}/column-groups",
                json={"name": "基础信息", "field_names": [f2["text"], f2["number"]]})
gid = r.json()["group"]["id"]
assert r.json()["group"]["field_names"] == [f2["text"], f2["number"]]
r = client.patch(f"/api/smart/column-groups/{gid}", json={"name": "基础信息2"})
assert r.json()["group"]["name"] == "基础信息2"
r = client.delete(f"/api/smart/column-groups/{gid}")
assert r.status_code == 200
print("列编组 CRUD 通过")

# ---------- 仪表盘 ----------
r = client.post(f"/api/smart/docs/{doc_id}/entries", json={"type": "dashboard", "name": "销售看板"})
dash_id = r.json()["entry"]["id"]
r = client.post(f"/api/smart/dashboards/{dash_id}/widgets", json={
    "title": "按分类统计", "chart_type": "bar",
    "config": {"sourceTableId": t2, "dimension": f2["singleSelect"],
               "metric": {"agg": "sum", "field": f2["number"]}}})
wid = r.json()["widget"]["id"]
r = client.post("/api/smart/charts/preview", json={
    "tableId": t2, "dimension": f2["singleSelect"], "metric": {"agg": "sum", "field": f2["number"]}})
cats = r.json()["categories"]
assert cats and all("key" in c and "value" in c for c in cats), cats
print(f"仪表盘 widget + 图表聚合通过（{len(cats)} 个类别）")

# ---------- Excel 导入 ----------
import openpyxl
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "数据"
ws.append(["名称", "数量", "日期"])
for i in range(1, 21):
    ws.append([f"项目{i}", i * 10, "2026-10-13"])
wb.save("smoke_import.xlsx")
with open("smoke_import.xlsx", "rb") as fp:
    r = client.post("/api/excel/upload", files={"file": ("smoke_import.xlsx", fp)})
assert r.status_code == 200, r.text
fid = r.json()["file_id"] if "file_id" in r.json() else r.json().get("file", {}).get("id")
r = client.post(f"/api/smart/docs/{doc_id}/import-excel", json={
    "file_id": fid, "sheet_name": "数据", "header_row": 1, "name": "导入测试"})
assert r.status_code == 200, r.text
rep = r.json()["import_report"]
assert rep["success"] == 20, rep
t_imp = r.json()["table_id"]
g = client.get(f"/api/smart/tables/{t_imp}/grid").json()
assert g["total"] == 20
ftypes = {f["label"]: f["field_type"] for f in g["fields"]}
assert ftypes.get("数量") == "number" and ftypes.get("日期") == "date", ftypes
print("Excel 导入建表通过（20 行，类型推断 数量→number 日期→date）")
os.remove("smoke_import.xlsx")

cm.__exit__(None, None, None)
print("\n全部智能表 V2 冒烟测试通过 [OK]")
