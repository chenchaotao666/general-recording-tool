"""冒烟测试：不走 LLM，验证 上传解析 -> 建表导入 -> 动态CRUD -> 删表 全链路。"""
import io
import os
import sys

# 用独立的测试数据库，避免污染 grt.db
os.environ["GRT_DATABASE_URL"] = "sqlite:///./smoke_test.db"

import openpyxl
from fastapi.testclient import TestClient

from app.main import app

cm = TestClient(app)
client = cm.__enter__()  # 进入上下文以触发 lifespan（建元数据表 + 种子管理员）

# 0. 登录：未带 token 一律 401；错误密码 401；默认管理员 admin/admin123 可登录
r = client.get("/api/tables")
assert r.status_code == 401, r.text
r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
assert r.status_code == 401, r.text
r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
assert r.status_code == 200, r.text
token = r.json()["token"]
assert r.json()["user"]["role"] == "admin"
assert {"share", "create_physical_table", "max_tables"} <= set(r.json()["user"]["perms"])  # admin 拥有全部权限
client.headers.update({"Authorization": f"Bearer {token}"})
print("登录成功，token 已注入请求头")

# 注册：新用户可注册并直接登录；重名/弱密码被拒绝
r = client.post("/api/auth/register", json={"username": "zhangsan", "password": "secret123"})
assert r.status_code == 200 and r.json()["user"]["role"] == "user", r.text
assert "share" not in r.json()["user"]["perms"]  # 普通用户默认无分享权限
r = client.post("/api/auth/register", json={"username": "zhangsan", "password": "secret123"})
assert r.status_code == 400, r.text
r = client.post("/api/auth/register", json={"username": "lisi", "password": "123"})
assert r.status_code == 400, r.text
r = client.post("/api/auth/login", json={"username": "zhangsan", "password": "secret123"})
assert r.status_code == 200, r.text
print("注册/重名校验/弱密码校验通过")

# 修改密码：原密码错误 400，弱密码 400，改后旧密码失效、新密码可登录（以 zhangsan 身份操作）
r = client.post("/api/auth/login", json={"username": "zhangsan", "password": "secret123"})
zs_headers = {"Authorization": f"Bearer {r.json()['token']}"}
saved_headers = dict(client.headers)
client.headers = zs_headers
r = client.put("/api/auth/password", json={"old_password": "wrong", "new_password": "newpass123"})
assert r.status_code == 400, r.text
r = client.put("/api/auth/password", json={"old_password": "secret123", "new_password": "123"})
assert r.status_code == 400, r.text
r = client.put("/api/auth/password", json={"old_password": "secret123", "new_password": "newpass123"})
assert r.status_code == 200, r.text
client.headers = saved_headers
r = client.post("/api/auth/login", json={"username": "zhangsan", "password": "secret123"})
assert r.status_code == 401, r.text
r = client.post("/api/auth/login", json={"username": "zhangsan", "password": "newpass123"})
assert r.status_code == 200, r.text
print("修改密码通过")

# Excel 序列日期：单元格未设日期格式时读出为数字（45200 → 2023-10-01）
from app.services.typemap import coerce_value

ok, val, err = coerce_value(45200, "date")
assert ok and str(val) == "2023-10-01", (val, err)
ok, val, err = coerce_value("45200", "date")
assert ok and str(val) == "2023-10-01", (val, err)
ok, val, err = coerce_value(45200.5, "datetime")
assert ok and val.hour == 12, (val, err)
ok, _, _ = coerce_value("2026", "date")   # 年份不当作序列日期
assert not ok
print("Excel 序列日期转换通过")

# 1. 构造测试 Excel
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "客户"
ws.append(["客户姓名", "联系电话", "下次跟进日期", "意向金额", "已成交"])
ws.append(["张三", "13800001234", "2026-10-01", 15000.5, "是"])
ws.append(["李四", "13900005678", "2026/10/05", 8000, "否"])
ws.append(["王五", "13700009012", "不是日期", None, "是"])  # 这一行日期转换失败
buf = io.BytesIO()
wb.save(buf)
buf.seek(0)

# 2. 上传解析
r = client.post("/api/excel/upload", files={"file": ("客户跟进.xlsx", buf.getvalue())})
assert r.status_code == 200, r.text
up = r.json()
print("upload:", up["file_name"], "sheets:", [(s["name"], s["header_row"], s["total_rows"]) for s in up["sheets"]])
assert up["sheets"][0]["headers"] == ["客户姓名", "联系电话", "下次跟进日期", "意向金额", "已成交"]

# 3. 确认结构建表 + 导入（模拟用户确认后的字段定义）
fields = [
    {"source_header": "客户姓名", "field_name": "customer_name", "label": "客户姓名", "data_type": "varchar", "length": 64, "nullable": False, "widget": "input"},
    {"source_header": "联系电话", "field_name": "phone", "label": "联系电话", "data_type": "varchar", "length": 32, "widget": "input"},
    {"source_header": "下次跟进日期", "field_name": "next_follow_date", "label": "下次跟进日期", "data_type": "date", "widget": "date-picker"},
    {"source_header": "意向金额", "field_name": "amount", "label": "意向金额", "data_type": "decimal", "widget": "number"},
    {"source_header": "已成交", "field_name": "is_deal", "label": "已成交", "data_type": "bool", "widget": "switch"},
]
r = client.post("/api/tables", json={
    "label": "客户跟进记录",
    "fields": fields,
    "source": {"file_id": up["file_id"], "sheet_name": "客户", "header_row": 1},
})
assert r.status_code == 200, r.text
created = r.json()
tid = created["table"]["id"]
report = created["import_report"]
print("建表:", created["table"]["name"], "导入:", report["success"], "成功 /", report["failed"], "失败")
assert report["success"] == 2 and report["failed"] == 1, report
assert "无法转换为 date" in report["failures"][0]["error"]

# 4. 动态 CRUD
r = client.get(f"/api/dyn/{tid}/records")
assert r.status_code == 200 and r.json()["total"] == 2, r.text
first = r.json()["items"][0]
print("列表首条:", first)
assert first["next_follow_date"] in ("2026-10-01", "2026-10-05")

# 筛选：contains
r = client.get(f"/api/dyn/{tid}/records", params={"filters": '[{"field":"customer_name","op":"contains","value":"张"}]'})
assert r.json()["total"] == 1, r.text

# 筛选：bool eq + 日期范围（李四 is_deal=false 不命中，只有张三命中）
r = client.get(f"/api/dyn/{tid}/records", params={"filters": '[{"field":"is_deal","op":"eq","value":true},{"field":"next_follow_date","op":"gte","value":"2026-10-01"}]'})
assert r.json()["total"] == 1, r.text

# 新增
r = client.post(f"/api/dyn/{tid}/records", json={"customer_name": "赵六", "next_follow_date": "2026-11-01", "amount": 3000, "is_deal": False})
assert r.status_code == 200, r.text
rid = r.json()["id"]

# 必填校验
r = client.post(f"/api/dyn/{tid}/records", json={"phone": "123"})
assert r.status_code == 422, r.text

# 编辑 + 删除
r = client.put(f"/api/dyn/{tid}/records/{rid}", json={"customer_name": "赵六改"})
assert r.status_code == 200 and r.json()["customer_name"] == "赵六改", r.text
r = client.delete(f"/api/dyn/{tid}/records/{rid}")
assert r.status_code == 200, r.text

# 5. 图片识别（mock LLM provider，验证压缩/校验/留痕链路）
from PIL import Image

import app.services.llm.gateway as gw


class FakeProvider:
    def complete(self, prompt, system=None):
        return "{}"

    def recognize(self, images, prompt, system=None):
        assert len(images) == 1 and images[0][:2] == b"\xff\xd8"  # 已压缩为 JPEG
        return '{"fields": {"customer_name": "图片客户", "amount": 6666, "next_follow_date": "2026-12-01", "unknown_field": "x"}, "conflicts": [], "notes": "识别完成"}'


gw.get_default_provider = lambda db: FakeProvider()

img = Image.new("RGB", (300, 120), "white")
img_buf = io.BytesIO()
img.save(img_buf, "PNG")

r = client.post(
    "/api/vision/recognize",
    data={"table_id": str(tid), "current": '{"customer_name": "旧名字"}'},
    files={"images": ("test.png", img_buf.getvalue(), "image/png")},
)
assert r.status_code == 200, r.text
vr = r.json()
print("识别结果:", vr["fields"], "冲突:", vr["conflicts"])
assert vr["fields"]["customer_name"] == "图片客户"
assert vr["fields"]["amount"] == 6666.0
assert vr["fields"]["next_follow_date"] == "2026-12-01"
assert "unknown_field" not in vr["fields"]  # 字段清单外的字段被丢弃
assert any(c["field_name"] == "customer_name" for c in vr["conflicts"])  # 与当前值冲突被检出

# 采纳留痕
r = client.put(f"/api/vision/logs/{vr['log_id']}/adopt", json={"adopted": ["amount", "next_follow_date"]})
assert r.status_code == 200, r.text

# 6. 任务引擎：结构化条件 + 站内通知
r = client.post("/api/tasks", json={
    "name": "10月前需要跟进的客户",
    "table_id": tid,
    "enabled": True,
    "condition_mode": "structured",
    "condition": {"logic": "AND", "rules": [
        {"field": "next_follow_date", "op": "lte", "value": "2026-10-31"},
        {"field": "is_deal", "op": "eq", "value": False},
    ]},
    "schedule": {"type": "interval", "minutes": 60},
    "action": {"type": "notify", "template": "客户【{customer_name}】计划 {next_follow_date} 跟进",
               "recipients": {"type": "fixed", "value": ""}},
    "cooldown_hours": 24,
})
assert r.status_code == 200, r.text
rule = r.json()
print("任务创建:", rule["name"])

# 试运行：李四未成交且跟进日期<=10-31，命中 1 条
r = client.post(f"/api/tasks/{rule['id']}/test")
assert r.status_code == 200, r.text
tr = r.json()
print("试运行: 命中", tr["matched"], "将触发", tr["would_fire"])
assert tr["matched"] == 1 and tr["would_fire"] == 1, tr
assert tr["samples"][0]["customer_name"] == "李四"

# 手动执行：生成站内通知
r = client.post(f"/api/tasks/{rule['id']}/run")
assert r.status_code == 200, r.text
assert r.json()["fired"] == 1 and r.json()["failed"] == 0, r.text
r = client.get("/api/notify/unread_count")
assert r.json()["count"] == 1, r.text
r = client.get("/api/notify")
assert "李四" in r.json()[0]["content"] and "2026-10-05" in r.json()[0]["content"], r.text

# 冷却语义：手动执行跳过冷却（设计如此，便于立即验证）；定时调度路径遵守冷却窗口
r = client.post(f"/api/tasks/{rule['id']}/run")
assert r.json()["matched"] == 1 and r.json()["fired"] == 1, r.text
from app.services.task_engine import execute_rule as _exec_rule
r2 = _exec_rule(rule["id"], trigger="schedule")  # 冷却期内 → 不再触发
assert r2["matched"] == 1 and r2["fired"] == 0, r2

# 时间操作符：within_days（跟进日期在未来 60 天内 → 两条都命中）
r = client.post("/api/tasks", json={
    "name": "历史任务", "table_id": tid,
    "condition_mode": "structured",
    "condition": {"logic": "AND", "rules": [{"field": "next_follow_date", "op": "within_days", "value": 60}]},
    "schedule": {"type": "cron", "expr": "0 9 * * *"},
    "action": {"type": "notify", "template": "x", "recipients": {"type": "fixed", "value": ""}},
})
r2 = client.post(f"/api/tasks/{r.json()['id']}/test")
assert r2.json()["matched"] == 2, r2.text
client.delete(f"/api/tasks/{r.json()['id']}")

# older_than_days：created_at 早于 0 天前（即此刻之前创建）→ 两条都命中
r = client.post("/api/tasks", json={
    "name": "older", "table_id": tid, "condition_mode": "structured",
    "condition": {"logic": "AND", "rules": [{"field": "created_at", "op": "older_than_days", "value": 0}]},
    "schedule": {"type": "interval", "minutes": 60},
    "action": {"type": "notify", "template": "x", "recipients": {"type": "fixed", "value": ""}},
})
r2 = client.post(f"/api/tasks/{r.json()['id']}/test")
assert r2.json()["matched"] == 2, r2.text
client.delete(f"/api/tasks/{r.json()['id']}")

# 7. LLM 判断条件（mock provider 返回 matched_ids）
class JudgeFakeProvider(FakeProvider):
    def complete(self, prompt, system=None):
        return '{"matched_ids": [2], "reason": "test"}'

gw.get_default_provider = lambda db: JudgeFakeProvider()
r = client.post("/api/tasks", json={
    "name": "LLM判断", "table_id": tid,
    "condition_mode": "llm",
    "condition": {"description": "意向金额较高的客户"},
    "schedule": {"type": "interval", "minutes": 30},
    "action": {"type": "notify", "template": "高额客户 {customer_name}", "recipients": {"type": "fixed", "value": ""}},
})
assert r.status_code == 200, r.text
r2 = client.post(f"/api/tasks/{r.json()['id']}/test")
assert r2.json()["matched"] == 1 and r2.json()["samples"][0]["id"] == 2, r2.text
client.delete(f"/api/tasks/{r.json()['id']}")

# 非法 cron 被拒绝
r = client.post("/api/tasks", json={
    "name": "bad", "table_id": tid, "condition_mode": "structured",
    "condition": {"logic": "AND", "rules": [{"field": "customer_name", "op": "contains", "value": "x"}]},
    "schedule": {"type": "cron", "expr": "not-a-cron"},
    "action": {"type": "notify", "template": "x", "recipients": {"type": "fixed", "value": ""}},
})
assert r.status_code == 400, r.text

# 8. 通用设置（SMTP 密码保留逻辑）
r = client.put("/api/settings/general", json={"smtp": {"host": "smtp.example.com", "port": 465, "username": "a@b.com", "password": "secret", "use_ssl": True}})
assert r.status_code == 200, r.text
r = client.get("/api/settings/general")
assert r.json()["smtp"]["host"] == "smtp.example.com" and r.json()["smtp"]["password"] is None and r.json()["smtp"]["has_password"]
r = client.put("/api/settings/general", json={"smtp": {"host": "smtp2.example.com"}})
r = client.get("/api/settings/general")
assert r.json()["smtp"]["host"] == "smtp2.example.com" and r.json()["smtp"]["has_password"]  # 密码保留

# 运行日志（2 次手动 + 1 次定时）
r = client.get(f"/api/tasks/{rule['id']}/runs")
assert r.status_code == 200 and len(r.json()) == 3 and r.json()[0]["trigger"] == "schedule", r.text

# 通知已读
r = client.post("/api/notify/read", json={"all": True})
assert client.get("/api/notify/unread_count").json()["count"] == 0

# 删除任务
r = client.delete(f"/api/tasks/{rule['id']}")
assert r.status_code == 200

# 9. 表列表 + 删除
r = client.get("/api/tables")
assert r.status_code == 200 and r.json()[0]["record_count"] == 2, r.text
r = client.delete(f"/api/tables/{tid}")
assert r.status_code == 200, r.text
r = client.get(f"/api/dyn/{tid}/records")
assert r.status_code == 404

# ========== 混合存储 + 多租户 + 分享权限 ==========

PFIELDS = [
    {"field_name": "customer_name", "label": "客户姓名", "data_type": "varchar", "length": 64, "nullable": False, "widget": "input"},
    {"field_name": "next_follow_date", "label": "下次跟进日期", "data_type": "date", "widget": "date-picker"},
    {"field_name": "amount", "label": "意向金额", "data_type": "decimal", "widget": "number"},
    {"field_name": "is_deal", "label": "已成交", "data_type": "bool", "widget": "switch"},
]
PRECS = [
    {"customer_name": "张三", "next_follow_date": "2026-10-01", "amount": 15000.5, "is_deal": True},
    {"customer_name": "李四", "next_follow_date": "2026-10-05", "amount": 8000, "is_deal": False},
    {"customer_name": "王五", "next_follow_date": "2026-09-15", "amount": 20000.25, "is_deal": True},
    {"customer_name": "赵六", "amount": 500, "is_deal": False},
]


def make_table(label, storage_mode):
    r = client.post("/api/tables", json={"label": label, "storage_mode": storage_mode, "fields": PFIELDS})
    assert r.status_code == 200, r.text
    return r.json()["table"]["id"]


def fill(t):
    for rec in PRECS:
        r = client.post(f"/api/dyn/{t}/records", json=rec)
        assert r.status_code == 200, r.text


# 10. 双模式 parity：同数据集 json vs physical，筛选/排序/报表逐项一致
tj = make_table("parity-json", "json")
tp = make_table("parity-physical", "physical")
fill(tj)
fill(tp)

FILTERS = [
    '[{"field":"customer_name","op":"contains","value":"张"}]',
    '[{"field":"amount","op":"gt","value":9000}]',
    '[{"field":"next_follow_date","op":"gte","value":"2026-10-01"}]',
    '[{"field":"is_deal","op":"eq","value":true}]',
    '[{"field":"next_follow_date","op":"null"}]',
    '[{"field":"customer_name","op":"startswith","value":"李"}]',
    '[{"field":"amount","op":"in","value":"8000,500"}]',
    '[{"field":"next_follow_date","op":"older_than_days","value":3}]',
]
def _strip_ts(items):
    # json/physical 是两次独立插入，created_at/updated_at 必然不同，比较时剔除
    return [{k: v for k, v in r.items() if k not in ("created_at", "updated_at")} for r in items]


for flt in FILTERS:
    a = client.get(f"/api/dyn/{tj}/records", params={"filters": flt}).json()
    b = client.get(f"/api/dyn/{tp}/records", params={"filters": flt}).json()
    assert a["total"] == b["total"] and _strip_ts(a["items"]) == _strip_ts(b["items"]), (flt, a, b)
print("parity 筛选一致:", len(FILTERS), "组")

for params in ({"sort_by": "amount", "sort_order": "asc"}, {"sort_by": "amount", "sort_order": "desc"},
               {"sort_by": "next_follow_date", "sort_order": "desc"}, {}):
    a = client.get(f"/api/dyn/{tj}/records", params=params).json()
    b = client.get(f"/api/dyn/{tp}/records", params=params).json()
    assert _strip_ts(a["items"]) == _strip_ts(b["items"]), params
print("parity 排序一致")

BLOCKS = [
    {"id": "b1", "type": "stat", "title": "总额", "agg": "sum", "field": "amount", "filters": {"logic": "AND", "rules": []}},
    {"id": "b2", "type": "chart", "title": "成交对比", "chart_type": "bar", "group": {"kind": "field", "field": "is_deal"}, "agg": "sum", "field": "amount", "top_n": 8, "filters": {"logic": "AND", "rules": []}},
    {"id": "b3", "type": "chart", "title": "按月", "chart_type": "line", "group": {"kind": "month", "field": "next_follow_date"}, "agg": "count", "filters": {"logic": "AND", "rules": []}},
    {"id": "b4", "type": "table", "title": "明细", "columns": ["customer_name", "amount", "next_follow_date"], "sort_by": "amount", "sort_order": "desc", "limit": 10, "filters": {"logic": "AND", "rules": []}},
]
rep_ids = []
for t in (tj, tp):
    r = client.post("/api/reports", json={
        "name": "parity", "table_id": t, "enabled": False,
        "range": {"mode": "this_month", "date_field": "created_at"},
        "blocks": BLOCKS, "schedule": {}, "push": {},
    })
    assert r.status_code == 200, r.text
    rep_ids.append(r.json()["id"])
ra = client.post(f"/api/reports/{rep_ids[0]}/run").json()
rb = client.post(f"/api/reports/{rep_ids[1]}/run").json()
for ba, bb in zip(ra["blocks"], rb["blocks"]):
    ba.pop("id", None)
    bb.pop("id", None)
    assert ba == bb, (ba, bb)
print("parity 报表四区块一致")
for rid_ in rep_ids:
    client.delete(f"/api/reports/{rid_}")

# 10.5 报表 P0：新时间口径 / 去重计数 / 占比 / 环比 / 查看端筛选
BLOCKS_P0 = [
    {"id": "b1", "type": "stat", "title": "记录数", "agg": "count", "compare": True,
     "filters": {"logic": "AND", "rules": []}},
    {"id": "b2", "type": "stat", "title": "去重客户", "agg": "count_distinct", "field": "customer_name",
     "filters": {"logic": "AND", "rules": []}},
    {"id": "b3", "type": "stat", "title": "成交占比", "agg": "ratio",
     "filters": {"logic": "AND", "rules": [{"field": "is_deal", "op": "eq", "value": True}]}},
    {"id": "b4", "type": "chart", "title": "按成交去重客户", "chart_type": "bar",
     "group": {"kind": "field", "field": "is_deal"}, "agg": "count_distinct", "field": "customer_name",
     "filters": {"logic": "AND", "rules": []}},
]

# 校验：图表不支持占比、去重计数必须有字段、查看端筛选字段必须是表内字段
for bad_blocks, bad_ff in (
    ([{"id": "x", "type": "chart", "chart_type": "bar", "group": {"kind": "field", "field": "is_deal"}, "agg": "ratio"}], None),
    ([{"id": "x", "type": "stat", "agg": "count_distinct"}], None),
    ([{"id": "x", "type": "stat", "agg": "count"}], ["ghost_field"]),
):
    r = client.post("/api/reports", json={
        "name": "bad", "table_id": tj, "range": {"mode": "today"},
        "blocks": bad_blocks, "filter_fields": bad_ff or [],
    })
    assert r.status_code == 400, r.text

p0_ids = []
for t in (tj, tp):
    r = client.post("/api/reports", json={
        "name": "P0报表", "table_id": t, "enabled": False,
        "range": {"mode": "today", "date_field": "created_at"},
        "blocks": BLOCKS_P0, "filter_fields": ["customer_name", "is_deal"],
        "schedule": {}, "push": {},
    })
    assert r.status_code == 200 and r.json()["filter_fields"] == ["customer_name", "is_deal"], r.text
    p0_ids.append(r.json()["id"])


def _blocks_by_id(res):
    return {b["id"]: b for b in res["blocks"]}


# 两种存储引擎结果一致 + 新聚合语义（tj=json / tp=physical，数据均为今天创建）
runs = [client.post(f"/api/reports/{rid}/run").json() for rid in p0_ids]
for res in runs:
    b = _blocks_by_id(res)
    assert res["range"]["label"].startswith("今天"), res["range"]
    assert b["b1"]["value"] == 4 and b["b1"]["compare"] == {"prev": 0, "delta": 4, "delta_pct": None}, b["b1"]
    assert b["b2"]["value"] == 4      # 4 个不同客户名
    assert b["b3"]["value"] == 50.0   # 4 条中 2 条成交
    assert sorted(b["b4"]["values"]) == [2, 2]
for bid in ("b1", "b2", "b3"):
    assert _blocks_by_id(runs[0])[bid] == _blocks_by_id(runs[1])[bid], bid

# 查看端筛选：只筛已成交 → 记录数 2、占比 100%（占比分母是查看者筛选后的集合）
r = client.post(f"/api/reports/{p0_ids[0]}/run", json={
    "filters": {"logic": "AND", "rules": [{"field": "is_deal", "op": "eq", "value": True}]}})
b = _blocks_by_id(r.json())
assert b["b1"]["value"] == 2 and b["b3"]["value"] == 100.0 and sum(b["b4"]["values"]) == 2, b
# 未声明的字段不允许查看端筛选
r = client.post(f"/api/reports/{p0_ids[0]}/run", json={
    "filters": {"logic": "AND", "rules": [{"field": "amount", "op": "gt", "value": 1}]}})
assert r.status_code == 400, r.text

# 新时间口径
for mode, label_prefix, expect in (
    ("yesterday", "昨天", 0), ("past_7d", "近7天", 4), ("past_30d", "近30天", 4),
    ("this_quarter", "本季度", 4), ("this_year", "今年", 4),
):
    res = client.post(f"/api/reports/{p0_ids[0]}/run", json={"range": {"mode": mode}}).json()
    assert res["range"]["label"].startswith(label_prefix), res["range"]
    assert _blocks_by_id(res)["b1"]["value"] == expect, (mode, res["range"])

# 环比：换业务日期字段 + 自定义区间（10 月 2 条 vs 9 月 1 条），两引擎一致
cmp_range = {"range": {"mode": "custom", "start": "2026-10-01", "end": "2026-10-31", "date_field": "next_follow_date"}}
res_py = client.post(f"/api/reports/{p0_ids[0]}/run", json=cmp_range).json()
res_phy = client.post(f"/api/reports/{p0_ids[1]}/run", json=cmp_range).json()
b1 = _blocks_by_id(res_py)["b1"]
assert b1["value"] == 2 and b1["compare"]["prev"] == 1 and b1["compare"]["delta_pct"] == 100.0, b1
assert b1 == _blocks_by_id(res_phy)["b1"]

for rid_ in p0_ids:
    client.delete(f"/api/reports/{rid_}")
print("报表 P0（口径/去重/占比/环比/查看端筛选）通过")

# 11. 权限矩阵：未分享 404 / 分享者按开关 / 主人与 admin 全权
admin_headers = dict(client.headers)
r = client.post("/api/auth/register", json={"username": "worker", "password": "secret123"})
worker_headers = {"Authorization": f"Bearer {r.json()['token']}"}
r = client.post("/api/auth/register", json={"username": "outsider", "password": "secret123"})
outsider_headers = {"Authorization": f"Bearer {r.json()['token']}"}


def as_user(h):
    client.headers = h


as_user(worker_headers)
assert client.get(f"/api/tables/{tj}").status_code == 404
assert client.get(f"/api/dyn/{tj}/records").status_code == 404
as_user(admin_headers)
r = client.post(f"/api/tables/{tj}/shares", json={"username": "worker", "can_view": True})
assert r.status_code == 200, r.text
assert r.json()["status"] == "pending"  # 直发分享需对方确认
as_user(worker_headers)
assert client.get(f"/api/tables/{tj}").status_code == 404  # 待确认不可见
assert all(t["id"] != tj for t in client.get("/api/tables").json())
r = client.get("/api/shares/pending")
share_id = next(s["id"] for s in r.json() if s["table_id"] == tj)
assert client.post(f"/api/shares/{share_id}/accept").status_code == 200
r = client.get(f"/api/tables/{tj}")
assert r.status_code == 200 and r.json()["my_perms"]["can_create"] is False, r.text
assert client.get(f"/api/dyn/{tj}/records").json()["total"] == 4
assert client.post(f"/api/dyn/{tj}/records", json={"customer_name": "x"}).status_code == 404  # 无新增权
assert client.put(f"/api/tables/{tj}", json={"label": "x"}).status_code == 404  # 非主人不能改结构
assert client.delete(f"/api/tables/{tj}").status_code == 404  # 非主人不能删表
assert client.post(f"/api/tables/{tj}/shares", json={"username": "outsider"}).status_code == 404  # 非主人不能分享
assert any(t["id"] == tj and t["owner_label"] == "admin" for t in client.get("/api/tables").json())  # 分享表可见
as_user(admin_headers)
r = client.post(f"/api/tables/{tj}/shares", json={"username": "worker", "can_view": True, "can_create": True})
assert r.status_code == 200 and r.json()["status"] == "accepted"  # 已接受的分享仅更新权限，不回到待确认
as_user(worker_headers)
assert client.post(f"/api/dyn/{tj}/records", json={"customer_name": "worker新增", "amount": 1}).status_code == 200
as_user(outsider_headers)
assert client.get(f"/api/tables/{tj}").status_code == 404  # 未分享不可见
assert all(t["table_id"] != tj for t in client.get("/api/tasks").json())
print("权限矩阵通过")

# 12. VIP 门槛与角色管理
as_user(worker_headers)
r = client.post("/api/tables", json={"label": "vip表", "storage_mode": "physical", "fields": PFIELDS})
assert r.status_code == 403  # user 不能建独立表
r = client.post("/api/tables", json={"label": "worker的表", "fields": PFIELDS})
worker_tid = r.json()["table"]["id"]
assert client.post(f"/api/tables/{worker_tid}/shares", json={"username": "outsider"}).status_code == 403  # user 不能分享
as_user(admin_headers)
assert all(t["id"] != worker_tid for t in client.get("/api/tables").json())  # admin 列表也不含未分享给自己的表
r = client.get("/api/users")
worker_id = next(u["id"] for u in r.json() if u["username"] == "worker")
assert client.put(f"/api/users/{worker_id}/role", json={"role": "vip"}).status_code == 200
me_id = next(u["id"] for u in client.get("/api/users").json() if u["role"] == "admin")
assert client.put(f"/api/users/{me_id}/role", json={"role": "user"}).status_code == 400  # 不能改自己
as_user(worker_headers)
# 分享对象约束： outsider 还不是好友/同组 → 403；建立好友关系后可分享
assert client.post(f"/api/tables/{worker_tid}/shares", json={"username": "outsider", "can_view": True}).status_code == 403
r = client.post("/api/friends/request", json={"username": "outsider"})
assert r.status_code == 200 and r.json()["status"] == "pending", r.text
assert client.post("/api/friends/request", json={"username": "outsider"}).status_code == 400  # 重复申请
as_user(outsider_headers)
r = client.get("/api/friends/requests")
fid = next(f["id"] for f in r.json() if f["username"] == "worker")
assert client.post(f"/api/friends/{fid}/accept").status_code == 200
as_user(worker_headers)
assert any(f["username"] == "outsider" for f in client.get("/api/friends").json())
assert client.post(f"/api/tables/{worker_tid}/shares", json={"username": "outsider", "can_view": True}).status_code == 200  # vip 可分享（待确认）
r = client.post("/api/tables", json={"label": "vip物理表", "storage_mode": "physical", "fields": PFIELDS})
assert r.status_code == 200  # vip 可建独立表
vip_tid = r.json()["table"]["id"]
print("VIP 门槛通过")

# 13. 归属隔离：规则/报表/通知按 user_id 隔离
r = client.post("/api/dyn/{}/records".format(worker_tid), json={"customer_name": "worker客户", "amount": 100, "is_deal": False})
assert r.status_code == 200, r.text
r = client.post("/api/tasks", json={
    "name": "worker规则", "table_id": worker_tid, "enabled": False,
    "condition_mode": "structured",
    "condition": {"logic": "AND", "rules": [{"field": "customer_name", "op": "contains", "value": "worker"}]},
    "schedule": {"type": "interval", "minutes": 60},
    "action": {"type": "notify", "template": "客户【{customer_name}】", "recipients": {"type": "fixed", "value": ""}},
})
assert r.status_code == 200, r.text
worker_rule = r.json()["id"]
assert any(t["id"] == worker_rule for t in client.get("/api/tasks").json())
as_user(outsider_headers)
assert all(t["id"] != worker_rule for t in client.get("/api/tasks").json())
assert all(t["id"] != rep_ids[0] for t in client.get("/api/reports").json())
as_user(outsider_headers)
assert client.post(f"/api/tasks/{worker_rule}/run").status_code == 404  # 他人规则不可操作
as_user(outsider_headers)
client.post("/api/notify/read", json={"all": True})  # 清掉好友申请通知，避免干扰下面的隔离断言
as_user(worker_headers)
client.post("/api/notify/read", json={"all": True})
r = client.post(f"/api/tasks/{worker_rule}/run")
assert r.status_code == 200 and r.json()["fired"] == 1, r.text
assert client.get("/api/notify/unread_count").json()["count"] >= 1  # worker 收到自己的通知
as_user(outsider_headers)
assert client.get("/api/notify/unread_count").json()["count"] == 0  # 别人收不到
as_user(admin_headers)
assert client.get("/api/notify/unread_count").status_code == 200  # admin 也只看到自己的通知（不报错）
print("归属隔离通过")

# 14. 迁移幂等：重复执行不报错、列不重复加
from app.database import engine as _engine
from app.services.migrate import run_migrations
run_migrations(_engine)
run_migrations(_engine)
print("迁移幂等通过")

# 15. RBAC：自定义权限/角色/授权，数值型权限（数据表上限）生效
role_codes = {x["code"] for x in client.get("/api/roles").json()}
assert {"admin", "vip", "user"} <= role_codes
perm_ids = {p["code"]: p["id"] for p in client.get("/api/permissions").json()}
assert {"share", "create_physical_table", "max_tables"} <= set(perm_ids)

r = client.post("/api/permissions", json={"code": "custom_perm", "name": "自定义权限"})
assert r.status_code == 200, r.text
custom_pid = r.json()["id"]
r = client.post("/api/roles", json={"code": "limited", "name": "受限角色"})
assert r.status_code == 200, r.text
limited_id = r.json()["id"]
# 授权：share + max_tables=1（不给 create_physical_table）
r = client.put(f"/api/roles/{limited_id}/permissions", json={"grants": [
    {"permission_id": perm_ids["share"]},
    {"permission_id": perm_ids["max_tables"], "value": 1},
]})
assert r.status_code == 200, r.text

r = client.post("/api/auth/register", json={"username": "limited_user", "password": "secret123"})
lu_headers = {"Authorization": f"Bearer {r.json()['token']}"}
lu_id = r.json()["user"]["id"]
assert client.put(f"/api/users/{lu_id}/role", json={"role": "limited"}).status_code == 200
assert client.put(f"/api/users/{lu_id}/role", json={"role": "ghost"}).status_code == 400  # 角色不存在

client.headers = lu_headers
r = client.post("/api/tables", json={"label": "限额表1", "fields": PFIELDS})
assert r.status_code == 200, r.text
lu_tid = r.json()["table"]["id"]
r = client.post("/api/tables", json={"label": "限额表2", "fields": PFIELDS})
assert r.status_code == 403, r.text  # 上限 1 张
# 分享对象约束：先与 outsider 成为好友
r = client.post("/api/friends/request", json={"username": "outsider"})
lu_fid = r.json()["id"]
saved_h = dict(client.headers)
client.headers = outsider_headers
assert client.post(f"/api/friends/{lu_fid}/accept").status_code == 200
client.headers = saved_h
assert client.post(f"/api/tables/{lu_tid}/shares", json={"username": "outsider", "can_view": True}).status_code == 200  # 有 share
r = client.post("/api/tables", json={"label": "限额物理表", "storage_mode": "physical", "fields": PFIELDS})
assert r.status_code == 403, r.text  # 无 create_physical_table
client.headers = admin_headers
assert client.delete(f"/api/roles/{limited_id}").status_code == 400  # 角色使用中
assert client.delete(f"/api/permissions/{perm_ids['share']}").status_code == 400  # 内置权限
client.headers = lu_headers
client.delete(f"/api/tables/{lu_tid}")  # 清掉唯一一张表
client.headers = admin_headers
assert client.delete(f"/api/roles/{limited_id}").status_code == 400  # 用户仍挂着该角色
assert client.put(f"/api/users/{lu_id}/role", json={"role": "user"}).status_code == 200  # 改回默认角色
assert client.delete(f"/api/roles/{limited_id}").status_code == 200
assert client.delete(f"/api/permissions/{custom_pid}").status_code == 200

# 给内置 user 角色授予 share：普通用户重新登录后即可分享（登录信息携带权限列表）
r = client.get("/api/roles")
user_role = next(x for x in r.json() if x["code"] == "user")
grants = [{"permission_id": p["id"], "value": p["value"]} for p in user_role["permissions"]]
grants.append({"permission_id": perm_ids["share"]})
r = client.put(f"/api/roles/{user_role['id']}/permissions", json={"grants": grants})
assert r.status_code == 200, r.text
r = client.post("/api/auth/register", json={"username": "normie", "password": "secret123"})
normie_headers = {"Authorization": f"Bearer {r.json()['token']}"}
assert "share" in r.json()["user"]["perms"]  # 登录信息携带权限列表
client.headers = normie_headers
r = client.post("/api/friends/request", json={"username": "outsider"})
normie_fid = r.json()["id"]
client.headers = outsider_headers
assert client.post(f"/api/friends/{normie_fid}/accept").status_code == 200
client.headers = normie_headers
r = client.post("/api/tables", json={"label": "normie的表", "fields": PFIELDS})
normie_tid = r.json()["table"]["id"]
assert client.post(f"/api/tables/{normie_tid}/shares", json={"username": "outsider", "can_view": True}).status_code == 200  # 普通用户被授予 share 后可分享
client.headers = admin_headers
print("RBAC 通过")

# 15.5 分享确认流与组约束
r = client.post("/api/auth/register", json={"username": "stranger", "password": "secret123"})
stranger_headers = {"Authorization": f"Bearer {r.json()['token']}"}

# 用户搜索 scope：all 能搜到任何人；shareable 只搜得到好友/同组
as_user(stranger_headers)
r = client.get("/api/users/search", params={"q": "worker", "scope": "all"})
assert any(u["username"] == "worker" for u in r.json())
r = client.get("/api/users/search", params={"q": "worker", "scope": "shareable"})
assert r.json() == []  # 非好友非同组搜不到

# 拒绝 → 分享者看到已拒绝 → 重新发起重置 pending → 接受后可见
as_user(admin_headers)
r = client.post(f"/api/tables/{vip_tid}/shares", json={"username": "stranger", "can_view": True})
assert r.status_code == 200 and r.json()["status"] == "pending", r.text
as_user(stranger_headers)
sid = next(s["id"] for s in client.get("/api/shares/pending").json() if s["table_id"] == vip_tid)
assert client.post(f"/api/shares/{sid}/reject").status_code == 200
assert client.get(f"/api/tables/{vip_tid}").status_code == 404
as_user(admin_headers)
shares_ = client.get(f"/api/tables/{vip_tid}/shares").json()
assert next(s for s in shares_ if s["target"] == "stranger")["status"] == "rejected"
r = client.post(f"/api/tables/{vip_tid}/shares", json={"username": "stranger", "can_view": True})
assert r.status_code == 200 and r.json()["status"] == "pending"  # 重新发起
as_user(stranger_headers)
sid = next(s["id"] for s in client.get("/api/shares/pending").json() if s["table_id"] == vip_tid)
assert client.post(f"/api/shares/{sid}/accept").status_code == 200
assert client.get(f"/api/tables/{vip_tid}").status_code == 200

# 组约束：只能分享到自己所在的组（admin 豁免）；组分享即时生效
as_user(admin_headers)
r = client.post("/api/groups", json={"name": "临时组"})
tmp_gid = r.json()["id"]
assert client.post(f"/api/groups/{tmp_gid}/members", json={"username": "stranger"}).status_code == 200
as_user(worker_headers)
assert client.post(f"/api/tables/{worker_tid}/shares", json={"group_id": tmp_gid, "can_view": True}).status_code == 403  # 非本组
as_user(admin_headers)
assert client.post(f"/api/groups/{tmp_gid}/members", json={"username": "worker"}).status_code == 200
as_user(worker_headers)
r = client.post(f"/api/tables/{worker_tid}/shares", json={"group_id": tmp_gid, "can_view": True})
assert r.status_code == 200 and r.json()["status"] == "accepted", r.text
as_user(stranger_headers)
assert client.get(f"/api/tables/{worker_tid}").status_code == 200  # 组内即时可见
r = client.get("/api/users/search", params={"q": "worker", "scope": "shareable"})
assert any(u["username"] == "worker" for u in r.json())  # 同组即可搜到
assert any(g["id"] == tmp_gid for g in client.get("/api/groups/mine").json())
as_user(admin_headers)
# admin 分享时可见所有用户和用户组（约束对 admin 豁免）
r = client.get("/api/users/search", params={"q": "stranger", "scope": "shareable"})
assert any(u["username"] == "stranger" for u in r.json())
assert any(g["id"] == tmp_gid for g in client.get("/api/groups/mine").json())
client.delete(f"/api/groups/{tmp_gid}")  # 删组 → 组分享同步失效
as_user(stranger_headers)
assert client.get(f"/api/tables/{worker_tid}").status_code == 404

# 互申自动接受 + 删除好友
as_user(stranger_headers)
r = client.post("/api/friends/request", json={"username": "outsider"})
assert r.status_code == 200 and r.json()["status"] == "pending"
as_user(outsider_headers)
r = client.post("/api/friends/request", json={"username": "stranger"})
assert r.status_code == 200 and r.json()["status"] == "accepted"  # 互申自动成为好友
fid = next(f["id"] for f in client.get("/api/friends").json() if f["username"] == "stranger")
assert client.delete(f"/api/friends/{fid}").status_code == 200
r = client.post("/api/friends/request", json={"username": "stranger"})  # 删除后可重新申请
assert r.status_code == 200 and r.json()["status"] == "pending"
as_user(admin_headers)
print("分享确认流与组约束通过")

# 16. 链接分享 + 用户组
# 用户组
r = client.post("/api/groups", json={"name": "生产部", "description": "生产组成员"})
assert r.status_code == 200, r.text
gid = r.json()["id"]
assert client.post(f"/api/groups/{gid}/members", json={"username": "worker"}).status_code == 200
assert client.post(f"/api/groups/{gid}/members", json={"username": "worker"}).status_code == 400  # 重复入组

# 分享给组
tj2 = make_table("组分享表", "json")
fill(tj2)
r = client.post(f"/api/tables/{tj2}/shares", json={"group_id": gid, "can_view": True, "can_create": True})
assert r.status_code == 200 and r.json()["target_type"] == "group", r.text
as_user(worker_headers)  # worker 是组成员：即时生效 + 收到告知通知
assert any("生产部" in n["content"] for n in client.get("/api/notify").json())
as_user(admin_headers)
as_user(outsider_headers)
assert client.get(f"/api/tables/{tj2}").status_code == 404  # outsider 不在组
as_user(admin_headers)
assert client.post(f"/api/groups/{gid}/members", json={"username": "outsider"}).status_code == 200
as_user(outsider_headers)
assert client.get(f"/api/tables/{tj2}").status_code == 200  # 入组后可见
r = client.post(f"/api/dyn/{tj2}/records", json={"customer_name": "组新增", "amount": 1})
assert r.status_code == 200, r.text  # 组分享的 can_create 生效
rid2 = r.json()["id"]
assert client.delete(f"/api/dyn/{tj2}/records/{rid2}").status_code == 404  # 组分享未给 delete
as_user(admin_headers)

# 链接分享（表，无密码）
r = client.post(f"/api/tables/{tj2}/share-links", json={})
assert r.status_code == 200, r.text
token = r.json()["token"]
saved_h = dict(client.headers)
client.headers = {}
r = client.get(f"/api/share/{token}")
assert r.status_code == 200 and r.json()["total"] >= 4 and r.json()["fields"], r.text
# 带密码 + 有效期
client.headers = saved_h
r = client.post(f"/api/tables/{tj2}/share-links", json={"password": "abcd", "expires_in_days": 7})
token2, lid2 = r.json()["token"], r.json()["id"]
client.headers = {}
assert client.get(f"/api/share/{token2}").status_code == 401  # 需要密码
assert client.get(f"/api/share/{token2}", params={"password": "wrong"}).status_code == 401
assert client.get(f"/api/share/{token2}", params={"password": "abcd"}).status_code == 200
client.headers = saved_h
client.delete(f"/api/tables/{tj2}/share-links/{lid2}")  # 撤销
client.headers = {}
assert client.get(f"/api/share/{token2}", params={"password": "abcd"}).status_code == 404
client.headers = saved_h

# 报表链接分享
r = client.post("/api/reports", json={
    "name": "分享报表", "table_id": tj2, "enabled": False,
    "range": {"mode": "this_month", "date_field": "created_at"},
    "blocks": [{"id": "b1", "type": "stat", "title": "总额", "agg": "sum", "field": "amount", "filters": {"logic": "AND", "rules": []}}],
    "schedule": {}, "push": {},
})
tpl_id2 = r.json()["id"]
r = client.post(f"/api/reports/{tpl_id2}/share-links", json={})
rtoken = r.json()["token"]
client.headers = {}
r = client.get(f"/api/share/{rtoken}")
assert r.status_code == 200 and r.json()["resource_type"] == "report" and r.json()["report"]["blocks"][0]["value"] > 0, r.text
client.headers = saved_h

# 删除组 → 组分享失效
client.delete(f"/api/groups/{gid}")
as_user(outsider_headers)
assert client.get(f"/api/tables/{tj2}").status_code == 404
as_user(admin_headers)
print("链接分享 + 用户组通过")

# 清理测试表
as_user(admin_headers)
for t_ in (tj, tp, worker_tid, vip_tid, tj2, normie_tid):
    client.delete(f"/api/tables/{t_}")

print("\nALL SMOKE TESTS PASSED")
cm.__exit__(None, None, None)
