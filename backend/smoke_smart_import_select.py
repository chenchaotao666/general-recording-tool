"""冒烟测试：智能表 Excel 导入的单选启发式——低基数文本列识别为 singleSelect，
选项从全量数据提取（频次降序+自动配色），记录值落库为 optionId；
高基数/长文本列保持文本，数字/日期/布尔列不受影响。"""
import io
import os

os.environ["GRT_DATABASE_URL"] = "sqlite:///./smoke_smart_import_select.db"
if os.path.exists("smoke_smart_import_select.db"):
    os.remove("smoke_smart_import_select.db")

import openpyxl
from fastapi.testclient import TestClient

from app.main import app
from app.services.field_registry import infer_select_options

# ---------- 单元级：启发式规则 ----------
assert infer_select_options(["张三", "李四", "张三", "王五", "张三", "李四"]) is not None          # 低基数
assert infer_select_options([f"联系人{i}" for i in range(30)]) is None           # 全唯一
assert infer_select_options(["甲"] * 10) is None                                 # 只有 1 种取值
assert infer_select_options(["这是一段超过三十个字符的备注文本内容呀" * 2] * 5) is None  # 长文本
assert infer_select_options([None, "", "  "]) is None                            # 全空
opts = infer_select_options(["B", "A", "B", "C", "B", "A"])
assert [o["label"] for o in opts] == ["B", "A", "C"], opts                        # 频次降序
print("infer_select_options 启发式规则通过")

cm = TestClient(app)
client = cm.__enter__()
r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
assert r.status_code == 200, r.text
client.headers.update({"Authorization": f"Bearer {r.json()['token']}"})

# ---------- 造 Excel ----------
CONTACTS = ["张三", "李四", "王五", "赵六"]
LEVELS = ["普通", "重要", "VIP"]
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "客户"
ws.append(["联系人", "客户等级", "公司名称", "备注", "金额", "下单日期", "启用"])
for i in range(40):
    ws.append([
        CONTACTS[i % 4], LEVELS[i % 3], f"测试公司{i + 1}号",
        "这是一段超过三十个字符的备注文本内容呀" * 2,
        round(100.5 + i, 2), f"2026-09-{(i % 28) + 1:02d}", "是" if i % 2 else "否",
    ])
buf = io.BytesIO()
wb.save(buf)
buf.seek(0)

r = client.post("/api/excel/upload",
                files={"file": ("客户表.xlsx", buf,
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
assert r.status_code == 200, r.text
file_id = r.json()["file_id"]

doc_id = client.get("/api/smart/docs/current").json()["id"]
r = client.post(f"/api/smart/docs/{doc_id}/import-excel",
                json={"file_id": file_id, "sheet_name": "客户", "header_row": 1, "name": "客户表"})
assert r.status_code == 200, r.text
table_id = r.json()["table_id"]
rep = r.json()["import_report"]
assert rep["success"] == 40 and rep["failed"] == 0, rep
print("导入成功：40/40")

# ---------- 字段类型断言 ----------
meta = client.get(f"/api/smart/tables/{table_id}/grid").json()
fields = client.get(f"/api/smart/entries/{r.json()['entry']['id']}/table").json()["fields"]
by_label = {f["label"]: f for f in fields}

assert by_label["联系人"]["field_type"] == "singleSelect", by_label["联系人"]
assert by_label["客户等级"]["field_type"] == "singleSelect"
assert by_label["公司名称"]["field_type"] == "text"
assert by_label["备注"]["field_type"] == "text"
assert by_label["金额"]["field_type"] == "number"
assert by_label["下单日期"]["field_type"] == "date"
assert by_label["启用"]["field_type"] == "checkbox"
print("字段类型推断通过：联系人/客户等级→单选，公司/备注→文本，金额→数字，日期→日期，是/否→复选框")

# ---------- 选项提取断言 ----------
c_opts = {o["label"]: o for o in by_label["联系人"]["options"]["options"]}
assert set(c_opts) == set(CONTACTS), c_opts
assert all(o["color"] for o in c_opts.values())                       # 自动配色
assert [o["label"] for o in by_label["联系人"]["options"]["options"]][0] == "张三"  # 频次相同按出现顺序
assert set(o["label"] for o in by_label["客户等级"]["options"]["options"]) == set(LEVELS)
assert by_label["联系人"]["options"].get("allowAddOptionWhenEditing") is True
print("选项提取通过（去重值→选项，含颜色/order）")

# ---------- 记录值断言：存 optionId 且能匹配回选项 ----------
items = meta["items"]
assert len(items) == 40
contact_fn = by_label["联系人"]["field_name"]
valid_ids = {o["id"] for o in by_label["联系人"]["options"]["options"]}
vals = [it[contact_fn] for it in items]
assert all(v in valid_ids for v in vals), vals[:5]
id_to_label = {o["id"]: o["label"] for o in by_label["联系人"]["options"]["options"]}
assert {id_to_label[v] for v in vals} == set(CONTACTS)                # 无标签丢失/漏映射
print("记录值映射通过：全部为 optionId，无未匹配原始值")

print("\n冒烟测试全部通过")
