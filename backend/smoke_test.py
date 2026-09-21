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
client = cm.__enter__()  # 进入上下文以触发 lifespan（建元数据表）

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

# 冷却期内再次执行：不再重复触发
r = client.post(f"/api/tasks/{rule['id']}/run")
assert r.json()["matched"] == 1 and r.json()["fired"] == 0, r.text

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

# 运行日志
r = client.get(f"/api/tasks/{rule['id']}/runs")
assert r.status_code == 200 and len(r.json()) == 2 and r.json()[0]["trigger"] == "manual", r.text

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

print("\nALL SMOKE TESTS PASSED")
cm.__exit__(None, None, None)
