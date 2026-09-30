"""冒烟测试：只有表头没有数据的 Excel 也能走通「上传 → 建表（仅结构）」。"""
import io
import os

os.environ["GRT_DATABASE_URL"] = "sqlite:///./smoke_header_only.db"

import openpyxl
from fastapi.testclient import TestClient

from app.main import app

cm = TestClient(app)
client = cm.__enter__()
r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
client.headers.update({"Authorization": f"Bearer {r.json()['token']}"})

# 构造只有表头的 xlsx
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Sheet1"
ws.append(["编号", "名称", "数量", "单价"])
buf = io.BytesIO()
wb.save(buf)
buf.seek(0)

r = client.post("/api/excel/upload", files={"file": ("空模板.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
assert r.status_code == 200, r.text
file_id = r.json()["file_id"]
print("上传成功")

# analyze：不再以「没有数据行」拒绝（无 LLM 环境下可能报模型错误，但不许是数据行校验错误）
r = client.post("/api/excel/analyze", json={"file_id": file_id, "sheet_name": "Sheet1", "header_row": 1})
assert not (r.status_code == 400 and "没有数据行" in str(r.json().get("detail"))), r.text
print(f"analyze 不再拦截空数据（本环境返回 {r.status_code}：无 LLM 时走不到模型分析属预期）")

# 建表 + 仅表头导入：结构与数据分离，0 条数据也应成功建表
r = client.post("/api/tables", json={
    "label": "空模板表",
    "fields": [
        {"field_name": "code", "label": "编号", "data_type": "varchar", "source_header": "编号"},
        {"field_name": "name", "label": "名称", "data_type": "varchar", "source_header": "名称"},
        {"field_name": "qty", "label": "数量", "data_type": "decimal", "source_header": "数量"},
        {"field_name": "price", "label": "单价", "data_type": "decimal", "source_header": "单价"},
    ],
    "source": {"file_id": file_id, "sheet_name": "Sheet1", "header_row": 1},
})
assert r.status_code == 200, r.text
rep = r.json()["import_report"]
assert rep["total"] == 0 and rep["success"] == 0 and rep["failed"] == 0, rep
tid = r.json()["table"]["id"]
assert len(r.json()["table"]["fields"]) == 4
print("仅表头建表成功（导入报告 total=0）")

# 表可正常使用：新增记录、列表
r = client.post(f"/api/dyn/{tid}/records", json={"code": "A1", "name": "测试", "qty": 2, "price": 3})
assert r.status_code == 200, r.text
r = client.get(f"/api/dyn/{tid}/records")
assert r.json()["total"] == 1
print("空模板表可正常录入数据")

r = client.delete(f"/api/tables/{tid}")
assert r.status_code == 200, r.text
cm.__exit__(None, None, None)
print("✅ 全部通过")
