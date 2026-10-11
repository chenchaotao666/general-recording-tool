"""冒烟测试：记事本富文本化 —— 页面树 CRUD + HTML 白名单清洗 + 搜索。

不走 LLM（AI 接口依赖配置的模型服务商，不在此测）。
用独立的测试数据库，避免污染 grt.db。
"""
import os
import sys

os.environ["GRT_DATABASE_URL"] = "sqlite:///./smoke_notes.db"
# 清掉上次的测试库，保证幂等
if os.path.exists("smoke_notes.db"):
    os.remove("smoke_notes.db")

from fastapi.testclient import TestClient

from app.main import app

cm = TestClient(app)
client = cm.__enter__()
r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
assert r.status_code == 200, r.text
client.headers.update({"Authorization": f"Bearer {r.json()['token']}"})

# 1. 新建页面（空 HTML）
r = client.post("/api/notes", json={})
assert r.status_code == 200, r.text
note = r.json()
assert note["content"] == ""
nid = note["id"]
print("1. 新建页面 OK")

# 2. 保存富文本：白名单外的标签/属性被清洗，合法结构保留
dirty_html = (
    '<h2>周报</h2><p>完成了<strong>富文本改造</strong>'
    '<span style="color: #e03e3e; position: fixed">重点</span>'
    '<span style="font-family: 宋体; font-size: 19px; width: expression(x)">字体</span></p>'
    '<p style="text-align: center; margin-left: -100px">居中</p>'
    '<p style="text-indent: 2em">缩进</p>'
    '<table style="width: auto; border: 1px solid red"><tbody><tr>'
    '<th colspan="2">表头</th><td rowspan="1" width="100">单元格</td></tr></tbody></table>'
    '<img src="/api/uploads/image/abc?token=x" alt="配图" style="width: 300px; height: 200px; top: 0">'
    '<img src="data:text/html;base64,PHNjcmlwdA==" onerror="x()">'
    '<ul data-type="taskList"><li data-type="taskItem" data-checked="false">'
    '<label><input type="checkbox" disabled></label><div><p>写周报</p></div></li></ul>'
    '<div data-w-e-type="todo"><input type="checkbox" checked disabled>wang待办</div>'
    '<a href="javascript:alert(1)">坏链接</a><a href="https://ok.com" target="_blank">好链接</a>'
    '<script>alert(1)</script><img src=x onerror=alert(1)><hr>'
)
r = client.put(f"/api/notes/{nid}", json={"content": dirty_html})
assert r.status_code == 200, r.text
saved = r.json()["content"]
assert "<script" not in saved and "alert(1)" not in saved, saved
assert "onerror" not in saved and "data:text" not in saved, saved
assert 'style="color: #e03e3e"' in saved, saved          # 颜色保留
assert "position" not in saved, saved                    # 危险样式被剥
assert "font-family: 宋体" in saved and "font-size: 19px" in saved, saved   # 字体字号保留
assert "expression" not in saved, saved                  # 表达式注入被剥
assert 'style="text-align: center"' in saved, saved      # 对齐保留
assert "margin-left" not in saved, saved                 # 外边距注入被剥
assert 'style="text-indent: 2em"' in saved, saved        # 缩进保留
assert "<table" in saved and 'colspan="2"' in saved and 'width="100"' in saved, saved  # 表格保留
assert 'style="width: auto"' in saved, saved
assert 'src="/api/uploads/image/abc?token=x"' in saved, saved               # 站内图片保留
assert "width: 300px" in saved and "top: 0" not in saved, saved             # 图片尺寸保留、定位样式被剥
assert 'href="https://ok.com"' in saved, saved
assert "坏链接" in saved and 'href="javascript' not in saved, saved
assert 'data-type="taskList"' in saved and 'data-checked="false"' in saved, saved
assert 'data-w-e-type="todo"' in saved, saved
assert "<hr>" in saved, saved
print("2. HTML 白名单清洗 OK")

# 3. 读取回来 + 树里 preview 是纯文本
r = client.get(f"/api/notes/{nid}")
assert r.status_code == 200 and r.json()["content"] == saved, r.text
r = client.get("/api/notes/tree")
items = r.json()["notes"]
assert len(items) == 1 and "content" not in items[0], items
assert items[0]["preview"] and "<" not in items[0]["preview"], items[0]
print("3. 读取/摘要 OK，preview =", items[0]["preview"])

# 4. 搜索命中正文（剥标签后的纯文本）
r = client.get("/api/notes/search", params={"keyword": "富文本改造"})
assert len(r.json()["notes"]) == 1, r.text
r = client.get("/api/notes/search", params={"keyword": "不存在的词"})
assert r.json()["notes"] == [], r.text
print("4. 搜索 OK")

# 5. 标题/置顶/子页/删除
r = client.put(f"/api/notes/{nid}", json={"title": "测试页", "pinned": True})
assert r.json()["pinned"] is True
r = client.post("/api/notes", json={"parent_id": nid})
child = r.json()
r = client.delete(f"/api/notes/{nid}")
assert r.status_code == 400, r.text            # 有子页不能删
client.delete(f"/api/notes/{child['id']}")
r = client.delete(f"/api/notes/{nid}")
assert r.status_code == 200, r.text
r = client.get("/api/notes/tree")
assert r.json()["notes"] == []
print("5. 标题/置顶/子页/删除约束 OK")

# 6. 超长内容拦截
r = client.post("/api/notes", json={})
r = client.put(f"/api/notes/{r.json()['id']}", json={"content": "<p>" + "x" * 300_000 + "</p>"})
assert r.status_code == 400, r.text
print("6. 超长内容 400 OK")

print("\n全部通过 ✅")
cm.__exit__(None, None, None)
os.remove("smoke_notes.db")
sys.exit(0)
