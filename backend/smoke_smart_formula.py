# -*- coding: utf-8 -*-
"""冒烟测试：智能表公式编辑器后端——Excel 风格函数、选项文本求值、全表重算（不动最后编辑时间）、
第 1 行试算（人话诊断）、自引用 / 循环引用检测、函数目录。
用法：cd backend && .venv/Scripts/python -I smoke_smart_formula.py"""
import os
import sys
from pathlib import Path

BASE = Path(__file__).parent
DB = BASE / "smoke_smart_formula.db"
if DB.exists():
    DB.unlink()
os.environ["GRT_DATABASE_URL"] = f"sqlite:///{DB.as_posix()}"
os.environ["GRT_SMART_SYNC"] = "1"
sys.path.insert(0, str(BASE))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services.field_registry import to_field_in  # noqa: E402

cm = TestClient(app)
client = cm.__enter__()
r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
client.headers.update({"Authorization": f"Bearer {r.json()['token']}"})


def call(method, url, expect=200, **kw):
    r = getattr(client, method)(url, **kw)
    assert r.status_code == expect, f"{method.upper()} {url} → {r.status_code} {r.text[:300]}"
    return r.json()


def add_field(tid, ft, label, config=None):
    names = {f["field_name"] for f in call("get", f"/api/tables/{tid}")["fields"]}
    n = 1
    while f"f_{n}" in names:
        n += 1
    call("post", f"/api/tables/{tid}/alter", json={"ops": [{"op": "add_field", "field": to_field_in(ft, label, f"f_{n}", config)}]})
    return f"f_{n}"


doc = call("get", "/api/smart/docs/current")["id"]
tid = call("post", f"/api/smart/docs/{doc}/entries", json={"type": "sheet", "name": "公式表"})["table_id"]
F = {f["field_type"]: f["field_name"] for f in call("get", f"/api/tables/{tid}")["fields"]}
for row in call("get", f"/api/smart/tables/{tid}/grid")["items"]:
    call("delete", f"/api/smart/tables/{tid}/records/{row['id']}")
r1 = call("post", f"/api/smart/tables/{tid}/records", json={"data": {F["text"]: "P001", F["singleSelect"]: "opt_1", F["number"]: 5, F["date"]: "2024-09-14"}})["record"]
r2 = call("post", f"/api/smart/tables/{tid}/records", json={"data": {F["text"]: "P002", F["singleSelect"]: "opt_2", F["number"]: 12}})["record"]
before_ts = r1["updated_at"]

# 1. 新增公式列 → 存量行全表重算；选项按文本比较；& 拼接；Excel 函数
fx = add_field(tid, "formula", "评级", {"formula": f'IF([{F["singleSelect"]}]="选项1", [{F["text"]}]&"-A", "其他")', "returnType": "text"})
fd = add_field(tid, "formula", "星期", {"formula": f'TEXT([{F["date"]}], "ddd")', "returnType": "text"})
rows = {x["id"]: x for x in call("get", f"/api/smart/tables/{tid}/grid")["items"]}
assert rows[r1["id"]][fx] == "P001-A" and rows[r2["id"]][fx] == "其他", (rows[r1["id"]][fx], rows[r2["id"]][fx])
assert rows[r1["id"]][fd] == "周六", rows[r1["id"]][fd]
assert rows[r1["id"]]["updated_at"] == before_ts, "全表重算不应改动最后编辑时间"
print("新增公式列：存量行重算 + 选项文本比较 + & 拼接 + TEXT 日期 通过（最后编辑时间不变）")

# 2. 修改公式 → 重算；记录编辑 → 写时重算
call("post", f"/api/tables/{tid}/alter", json={"ops": [{"op": "update_field", "field_name": fx,
     "options": {"formula": f'[{F["number"]}].ROUND(0) * 2', "returnType": "number"}}]})
rows = {x["id"]: x for x in call("get", f"/api/smart/tables/{tid}/grid")["items"]}
assert float(rows[r2["id"]][fx]) == 24, rows[r2["id"]][fx]
call("patch", f"/api/smart/tables/{tid}/records/{r2['id']}", json={"data": {F["number"]: 20}})
rows = {x["id"]: x for x in call("get", f"/api/smart/tables/{tid}/grid")["items"]}
assert float(rows[r2["id"]][fx]) == 40
print("修改公式：链式调用 值.ROUND() + 全表重算 + 编辑写时重算 通过")

# 3. 试算：第 1 行 = 值 / 人话诊断 / 语法错误 / 自引用 / 循环引用
p = call("post", f"/api/smart/tables/{tid}/formula/preview", json={"formula": f'[{F["text"]}]&"/"&[{F["singleSelect"]}]'})
assert p["ok"] and p["row_no"] == 1 and p["display"] == "P001/选项1" and p["type"] == "text", p
p = call("post", f"/api/smart/tables/{tid}/formula/preview", json={"formula": f'[{F["text"]}]+[{F["number"]}]'})
assert not p["ok"] and p["error"]["title"] == "类型转换错误" and "P001" in p["error"]["message"], p
print("试算诊断：", p["error"]["title"], "—", p["error"]["message"])
p = call("post", f"/api/smart/tables/{tid}/formula/preview", json={"formula": "IF(1>0, 2"})
assert not p["ok"] and "括号" in p["error"]["message"], p
p = call("post", f"/api/smart/tables/{tid}/formula/preview", json={"formula": f"[{fx}]+1", "field_name": fx})
assert not p["ok"] and "自身" in p["error"]["message"], p
p = call("post", f"/api/smart/tables/{tid}/formula/preview", json={"formula": f"[{fx}]&\"!\"", "field_name": fd})
assert p["ok"], p   # fd 引用 fx（fx 不引用 fd）：无环
call("post", f"/api/tables/{tid}/alter", json={"ops": [{"op": "update_field", "field_name": fd,
     "options": {"formula": f"[{fx}]&\"!\"", "returnType": "text"}}]})
p = call("post", f"/api/smart/tables/{tid}/formula/preview", json={"formula": f"[{fd}]+1", "field_name": fx})
assert not p["ok"] and p["error"]["title"] == "循环引用" and "评级" in p["error"]["message"], p
p = call("post", f"/api/smart/tables/{tid}/formula/preview", json={"formula": "DATEDIF(\"2024-01-01\", TODAY(), \"Y\") >= 0"})
assert p["ok"] and p["display"] == "TRUE" and p["type"] == "boolean", p
p = call("post", f"/api/smart/tables/{tid}/formula/preview", json={"formula": f'[{F["text"]}]', "record_id": r2["id"], "row_no": 1})
assert p["ok"] and p["row_no"] == 1 and p["display"] == "P002", p   # 视图首行口径
assert p["row_values"][F["singleSelect"]] == "选项2" and p["row_values"][F["number"]] == "20", p["row_values"]
p = call("post", f"/api/smart/tables/{tid}/formula/preview", json={"formula": "", "field_name": fx})
assert p["blank"] and fx not in p["row_values"] and p["row_values"][F["text"]] == "P001", p   # 空公式：只返回字段取值
print("试算：正常值 / 类型错误 / 语法错误 / 自引用 / 循环引用 / 布尔结果 通过")

# 4. 函数目录
cat = call("get", "/api/smart/formula/functions")
names = {f["name"] for f in cat["functions"]}
assert {"IF", "COUNTA", "TEXT", "DATEDIF", "TEXTJOIN", "IFERROR"} <= names and cat["categories"][0] == "常用函数"
assert all(f["examples"] for f in cat["functions"])
print(f"函数目录：{len(names)} 个函数，{len(cat['categories'])} 个分类，均带示例 通过")

# 6. 整表引用：客户表按订单表汇总（SUMIF / COUNTIF / LOOKUP / FILTER），订单增删改自动刷新
t_ord = call("post", f"/api/smart/docs/{doc}/entries", json={"type": "sheet", "name": "订单表"})["table_id"]
O = {f["field_type"]: f["field_name"] for f in call("get", f"/api/tables/{t_ord}")["fields"]}
for row in call("get", f"/api/smart/tables/{t_ord}/grid")["items"]:
    call("delete", f"/api/smart/tables/{t_ord}/records/{row['id']}")
o1 = call("post", f"/api/smart/tables/{t_ord}/records", json={"data": {O["text"]: "P001", O["number"]: 100}})["record"]
call("post", f"/api/smart/tables/{t_ord}/records", json={"data": {O["text"]: "P001", O["number"]: 50}})
call("post", f"/api/smart/tables/{t_ord}/records", json={"data": {O["text"]: "P002", O["number"]: 70}})
f_sum = add_field(tid, "formula", "订单总额", {"formula": f'SUMIF([#{t_ord}.{O["text"]}], [{F["text"]}], [#{t_ord}.{O["number"]}])', "returnType": "number"})
f_cnt = add_field(tid, "formula", "订单数", {"formula": f'[#{t_ord}.{O["text"]}].COUNTIF([{F["text"]}])', "returnType": "number"})
f_big = add_field(tid, "formula", "大单合计", {"formula": f'FILTER([#{t_ord}.{O["number"]}], [#{t_ord}.{O["text"]}]=[{F["text"]}], [#{t_ord}.{O["number"]}]>60).SUM()', "returnType": "number"})
rows = {x["id"]: x for x in call("get", f"/api/smart/tables/{tid}/grid")["items"]}
assert float(rows[r1["id"]][f_sum]) == 150 and float(rows[r1["id"]][f_cnt]) == 2 and float(rows[r1["id"]][f_big]) == 100, rows[r1["id"]]
assert float(rows[r2["id"]][f_sum]) == 70, rows[r2["id"]][f_sum]
call("post", f"/api/smart/tables/{t_ord}/records", json={"data": {O["text"]: "P001", O["number"]: 30}})   # 新增订单
call("patch", f"/api/smart/tables/{t_ord}/records/{o1['id']}", json={"data": {O["number"]: 200}})        # 修改订单
rows = {x["id"]: x for x in call("get", f"/api/smart/tables/{tid}/grid")["items"]}
assert float(rows[r1["id"]][f_sum]) == 280 and float(rows[r1["id"]][f_cnt]) == 3, (rows[r1["id"]][f_sum], rows[r1["id"]][f_cnt])
call("delete", f"/api/smart/tables/{t_ord}/records/{o1['id']}")                                            # 删除订单
rows = {x["id"]: x for x in call("get", f"/api/smart/tables/{tid}/grid")["items"]}
assert float(rows[r1["id"]][f_sum]) == 80 and rows[r1["id"]]["updated_at"] == before_ts, rows[r1["id"]]
print("整表引用：SUMIF / 链式 COUNTIF / FILTER 多条件 + 订单增删改自动刷新（不改最后编辑时间）通过")

# 7. 本表整列：占比 = 本行数字 / 本表合计；LOOKUP 带出；RECORD_ID
f_share = add_field(tid, "formula", "占比", {"formula": f'ROUND([{F["number"]}] / SUM([#{tid}.{F["number"]}]), 2)', "returnType": "number"})
f_rid = add_field(tid, "formula", "编号", {"formula": '"NO-" & RECORD_ID()', "returnType": "text"})
rows = {x["id"]: x for x in call("get", f"/api/smart/tables/{tid}/grid")["items"]}
assert float(rows[r1["id"]][f_share]) == 0.2 and float(rows[r2["id"]][f_share]) == 0.8, (rows[r1["id"]][f_share], rows[r2["id"]][f_share])
assert rows[r1["id"]][f_rid] == f"NO-{r1['id']}"
r3 = call("post", f"/api/smart/tables/{tid}/records", json={"data": {F["text"]: "P003", F["number"]: 75}})["record"]
assert r3[f_rid] == f"NO-{r3['id']}", r3[f_rid]   # 新建记录插入后补算 RECORD_ID
rows = {x["id"]: x for x in call("get", f"/api/smart/tables/{tid}/grid")["items"]}
assert float(rows[r1["id"]][f_share]) == 0.05, rows[r1["id"]][f_share]   # 新增一行后全表占比重算 5/(5+20+75)
p = call("post", f"/api/smart/tables/{tid}/formula/preview", json={"formula": f'LOOKUP("P002", [#{t_ord}.{O["text"]}], [#{t_ord}.{O["number"]}])'})
assert p["ok"] and p["display"] == "70", p
p = call("post", f"/api/smart/tables/{tid}/formula/preview", json={"formula": "[#99999.f_1].SUM()"})
assert not p["ok"] and p.get("blocking"), p
print("本表整列占比（新增行后全表重算）/ LOOKUP 带出 / RECORD_ID 插入后补算 / 无效表引用拦截 通过")

# 8. 函数目录：清单完整 + 运算符 + 参数说明
cat = call("get", "/api/smart/formula/functions")
names = {f["name"] for f in cat["functions"]}
for need in ["COUNTA", "FILTER", "IF", "UNIQUE", "COUNTIF", "COUNTIFS", "SUMIF", "SUMIFS", "SUMPRODUCT", "MEDIAN", "LARGE", "MROUND",
             "IFBLANK", "ISERROR", "RECORD_ID", "CONTAINTEXT", "REPLACE", "SEARCH", "LENB", "EOMONTH", "DAYS360", "WEEKNUM",
             "YEARFRAC", "AT", "CHOOSE", "CONTAINSALL", "LISTCOMBINE", "LISTJOIN", "LOOKUP", "SEQUENCE", "SORT"]:
    assert need in names, need
assert cat["categories"] == ["常用函数", "数字函数", "逻辑函数", "文本函数", "日期与时间函数", "列表函数"]
assert [o["op"] for o in cat["operators"]][-2:] == ["^", "<>"]
concat = next(f for f in cat["functions"] if f["name"] == "CONCAT")
assert concat["params"][0] == {"name": "文本1", "required": True, "desc": "要联接的文本项。字符串或字符串数组，后续数值是可选的。"}
print(f"函数目录：{len(names)} 个函数 / {len(cat['operators'])} 个运算符 / 参数说明 通过")

# 5. 旧版小写语法仍可用（报表/物理表兼容）
add_field(tid, "formula", "旧语法", {"formula": f"iff([{F['number']}] > 10, 1, 0)", "returnType": "number"})
print("\n公式编辑器后端冒烟全部通过 ✅")
cm.__exit__(None, None, None)
