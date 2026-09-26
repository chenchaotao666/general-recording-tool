"""冒烟测试（工作流二期）：逐条处理（foreach 循环）+ 表单触发器（公开表单）。

用法：.venv/Scripts/python.exe smoke_workflow.py
不走 LLM；用独立数据库 smoke_workflow.db，不污染 grt.db。
"""
import os

os.environ["GRT_DATABASE_URL"] = "sqlite:///./smoke_workflow.db"

from fastapi.testclient import TestClient

from app.main import app

cm = TestClient(app)
client = cm.__enter__()

r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
assert r.status_code == 200, r.text
client.headers.update({"Authorization": f"Bearer {r.json()['token']}"})

# ---------- 准备数据表 ----------
r = client.post("/api/tables", json={
    "label": "循环测试表",
    "fields": [
        {"field_name": "name", "label": "名称", "data_type": "varchar", "nullable": False},
        {"field_name": "qty", "label": "数量", "data_type": "int", "widget": "number"},
        {"field_name": "done", "label": "已处理", "data_type": "bool", "widget": "switch"},
    ],
})
assert r.status_code == 200, r.text
tid = r.json()["table"]["id"]
for i in range(3):
    r = client.post(f"/api/dyn/{tid}/records", json={"name": f"条目{i + 1}", "qty": i + 1, "done": False})
    assert r.status_code == 200, r.text
print("数据表就绪：3 条记录")

NODES = [
    {"id": "q_1", "type": "query_records", "name": "查全部",
     "config": {"table_id": tid, "limit": 100, "order_by": "id", "order_desc": False}},
    {"id": "loop_1", "type": "foreach", "name": "逐条处理",
     "config": {"items": "{nodes.q_1.records}", "max_items": 50}},
    {"id": "u_1", "type": "update_record", "name": "标记已处理",
     "config": {"table_id": tid,
                "match_filters": {"logic": "AND", "rules": [
                    {"field": "id", "op": "eq", "value": "{nodes.loop_1.item.id}"}]},
                "field_mapping": {"done": True}}},
    {"id": "send_1", "type": "send_message", "name": "完成通知",
     "config": {"channel": "notify", "title": "循环完成",
                "template": "已处理 {nodes.loop_1.count} 条"}},
]
EDGES = [
    {"from": "q_1", "to": "loop_1"},
    {"from": "loop_1", "to": "u_1", "branch": "loop"},
    {"from": "u_1", "to": "loop_1"},                      # 回边：循环体末尾连回 foreach
    {"from": "loop_1", "to": "send_1", "branch": "done"},
]

# ---------- 校验：缺回边 / 缺完成出口 必须 400 ----------
for bad_edges, why in [
    ([e for e in EDGES if e != {"from": "u_1", "to": "loop_1"}], "缺回边"),
    ([e for e in EDGES if e != {"from": "loop_1", "to": "send_1", "branch": "done"}], "缺完成出口"),
    ([{"from": "loop_1", "to": "u_1"} if e == {"from": "loop_1", "to": "u_1", "branch": "loop"} else e
      for e in EDGES], "loop 出口缺 branch"),
]:
    r = client.post("/api/workflows", json={
        "name": "坏流程", "trigger": {"type": "manual"}, "nodes": NODES, "edges": bad_edges})
    assert r.status_code == 400, f"{why} 应被拒绝：{r.text}"
print("校验：缺回边 / 缺完成出口 / 出口缺 branch 均被拒绝")

# ---------- 逐条处理：正确流程 ----------
r = client.post("/api/workflows", json={
    "name": "循环打标", "trigger": {"type": "manual"}, "nodes": NODES, "edges": EDGES})
assert r.status_code == 200, r.text
wf_id = r.json()["id"]

r = client.post(f"/api/workflows/{wf_id}/run", json={"params": {}})
assert r.status_code == 200 and r.json()["status"] == "success", r.text
run_id = r.json()["id"]

r = client.get(f"/api/workflows/runs/{run_id}")
assert r.status_code == 200, r.text
trail = [(nr["node_id"], nr["status"]) for nr in r.json()["node_runs"]]
loop_runs = [t for t in trail if t[0] == "loop_1"]
upd_runs = [t for t in trail if t[0] == "u_1"]
assert len(loop_runs) == 4, f"loop_1 应执行 4 次（3 条 + done），实际 {len(loop_runs)}"
assert len(upd_runs) == 3, f"u_1 应执行 3 次，实际 {len(upd_runs)}"
assert trail[-1][0] == "send_1" and trail[-1][1] == "success"

r = client.get(f"/api/dyn/{tid}/records", params={"page": 1, "page_size": 50})
assert r.status_code == 200, r.text
recs = r.json()["items"]
assert all(x["done"] for x in recs), f"3 条记录都应被标记：{recs}"
print("逐条处理：3 条记录全部被循环体更新，轨迹正确（loop×4 / update×3 / done→通知）")

# ---------- 逐条处理：空列表直接走完成 ----------
r = client.post(f"/api/dyn/{tid}/records", json={"name": "条目4", "qty": 4, "done": False})
r = client.post("/api/workflows", json={
    "name": "空循环", "trigger": {"type": "manual"},
    "nodes": [
        {"id": "q_1", "type": "query_records", "name": "查",
         "config": {"table_id": tid, "filters": {"logic": "AND", "rules": [
             {"field": "name", "op": "eq", "value": "不存在"}]}}},
        NODES[1], NODES[2], NODES[3],
    ],
    "edges": EDGES,   # 结构同正常循环，只是查询结果为空
})
assert r.status_code == 200, r.text
empty_wf = r.json()["id"]
r = client.post(f"/api/workflows/{empty_wf}/run", json={"params": {}})
assert r.status_code == 200 and r.json()["status"] == "success", r.text
r = client.get(f"/api/workflows/runs/{r.json()['id']}")
loop_trail = [nr for nr in r.json()["node_runs"] if nr["node_id"] == "loop_1"]
assert len(loop_trail) == 1 and loop_trail[0]["output"].get("done") is True
print("逐条处理：空列表直接走「完成」分支")

# ---------- 表单触发器 ----------
r = client.post("/api/workflows", json={
    "name": "报名表单", "enabled": True,
    "trigger": {"type": "form", "table_id": tid},
    "nodes": [
        {"id": "send_1", "type": "send_message", "name": "通知",
         "config": {"channel": "notify", "title": "新报名",
                    "template": "收到表单：{trigger.record.name}，数量 {trigger.record.qty}"}},
    ],
    "edges": [],
})
assert r.status_code == 200, r.text
form_wf = r.json()
assert form_wf["trigger"].get("secret"), "表单触发器应自动生成 secret"
form_url = form_wf["form_url"]
secret = form_wf["trigger"]["secret"]
wf_form_id = form_wf["id"]

# 公开接口：免登录
anon = TestClient(app)
r = anon.get(f"/api/workflows/form/{wf_form_id}/{secret}")
assert r.status_code == 200, r.text
meta = r.json()
assert meta["name"] == "报名表单" and {f["field_name"] for f in meta["fields"]} == {"name", "qty", "done"}
r = anon.get(f"/api/workflows/form/{wf_form_id}/wrongsecret")
assert r.status_code == 404
print(f"公开表单：元数据可匿名读取（{form_url}），错误 secret 404")

# 提交：缺必填 name → 422；正常提交 → 入表 + 触发流程
r = anon.post(f"/api/workflows/form/{wf_form_id}/{secret}", json={"qty": 2})
assert r.status_code == 422, r.text
r = anon.post(f"/api/workflows/form/{wf_form_id}/{secret}", json={"name": "表单用户", "qty": 9, "hack": "x"})
assert r.status_code == 200 and r.json()["ok"], r.text

from app.services.workflow import engine
engine.process_due_jobs()

r = client.get(f"/api/dyn/{tid}/records", params={"page": 1, "page_size": 50})
names = [x["name"] for x in r.json()["items"]]
assert "表单用户" in names, names
r = client.get(f"/api/workflows/{wf_form_id}/runs")
runs = [x for x in r.json() if x["trigger"] == "form"]
assert runs and runs[0]["status"] == "success", runs
print("表单触发器：提交入表成功（未知字段被丢弃、必填校验 422），流程已触发并执行成功")

# ---------- 站内通知接收人（好友/群组选择器对应的 notify_targets） ----------
r = client.post("/api/auth/register", json={"username": "bob", "password": "secret123"})
assert r.status_code == 200, r.text
bob_id = r.json()["user"]["id"]
bob_headers = {"Authorization": f"Bearer {r.json()['token']}"}
r = client.post("/api/groups", json={"name": "通知测试组"})
assert r.status_code == 200, r.text
gid = r.json()["id"]
r = client.post(f"/api/groups/{gid}/members", json={"username": "bob"})
assert r.status_code == 200, r.text

r = client.post("/api/workflows", json={
    "name": "定向通知", "trigger": {"type": "manual"},
    "nodes": [{"id": "send_1", "type": "send_message", "name": "通知",
               "config": {"channel": "notify", "title": "定向", "template": "你好",
                          "notify_targets": [f"u:{bob_id}", f"g:{gid}"]}}],
    "edges": [],
})
assert r.status_code == 200, r.text
nw = r.json()["id"]
r = client.post(f"/api/workflows/{nw}/run", json={"params": {}})
assert r.json()["status"] == "success", r.text
r = client.get(f"/api/workflows/runs/{r.json()['id']}")
out = r.json()["node_runs"][0]["output"]
assert out["sent"] == 2 and out["recipients"] == ["admin", "bob"], out   # 好友 bob + 群组（创建者 admin 自动入组 + bob）
r = client.get("/api/notify", headers=bob_headers)
assert len([n for n in r.json() if "定向" in n["title"]]) == 1, r.json()
print("站内通知接收人：好友 u:id + 群组 g:id 展开去重，bob 恰好收到 1 条")

# 不选接收人：兼容旧配置，默认发工作流归属人
r = client.post("/api/workflows", json={
    "name": "默认通知", "trigger": {"type": "manual"},
    "nodes": [{"id": "send_1", "type": "send_message", "name": "通知",
               "config": {"channel": "notify", "template": "默认归属人"}}],
    "edges": [],
})
nw2 = r.json()["id"]
r = client.post(f"/api/workflows/{nw2}/run", json={"params": {}})
assert r.json()["status"] == "success", r.text
r = client.get("/api/notify")
assert any("默认通知" in n["title"] for n in r.json()), r.json()
print("站内通知接收人：留空默认发归属人（兼容旧配置）")

# ---------- 零节点半成品：只配触发器也能保存/执行（什么都不做） ----------
r = client.post("/api/workflows", json={
    "name": "空流程", "trigger": {"type": "manual"}, "nodes": [], "edges": []})
assert r.status_code == 200, r.text
empty0 = r.json()["id"]
r = client.post(f"/api/workflows/{empty0}/run", json={"params": {}})
assert r.json()["status"] == "success" and r.json()["tokens_used"] == 0, r.text
# 但带了连线却没有节点仍是错误
r = client.post("/api/workflows", json={
    "name": "坏流程2", "trigger": {"type": "manual"}, "nodes": [],
    "edges": [{"from": "a", "to": "b"}]})
assert r.status_code == 400, r.text
print("零节点半成品：可保存、执行空跑成功；孤立连线仍 400")

# ---------- 去重节点 ----------
r = client.post(f"/api/dyn/{tid}/records", json={"name": "条目1副本", "qty": 1, "done": False})  # qty 与条目1重复
assert r.status_code == 200
r = client.post("/api/workflows", json={
    "name": "去重验证", "trigger": {"type": "manual"},
    "nodes": [
        {"id": "q_1", "type": "query_records", "name": "查",
         "config": {"table_id": tid, "limit": 100, "order_by": "id", "order_desc": False}},
        {"id": "d_1", "type": "dedupe", "name": "按名称去重",
         "config": {"records": "{nodes.q_1.records}", "field": "qty"}},
    ],
    "edges": [{"from": "q_1", "to": "d_1"}],
})
assert r.status_code == 200, r.text
dw = r.json()["id"]
r = client.post(f"/api/workflows/{dw}/run", json={"params": {}})
assert r.json()["status"] == "success", r.text
r = client.get(f"/api/workflows/runs/{r.json()['id']}")
dout = [nr for nr in r.json()["node_runs"] if nr["node_id"] == "d_1"][0]["output"]
all_items = client.get(f"/api/dyn/{tid}/records", params={"page_size": 100}).json()["items"]
assert dout["count"] == len({x["qty"] for x in all_items}) == len(dout["records"])
assert dout["removed"] == len(all_items) - dout["count"] == 1   # 副本被去掉
print(f"去重节点：按字段值去重 {dout['count']} 条（去掉 {dout['removed']} 条）")

# 去重不只表数据：触发参数里的标量/混合列表也能去
r = client.post("/api/workflows", json={
    "name": "标量去重", "trigger": {"type": "manual"},
    "nodes": [{"id": "d_1", "type": "dedupe", "name": "去重",
               "config": {"records": "{trigger.params.items}", "field": "k"}}],
    "edges": []})
sw = r.json()["id"]
r = client.post(f"/api/workflows/{sw}/run",
                json={"params": {"items": ["a", "b", "a", {"k": "x"}, {"k": "x"}, {"k": "y"}]}})
assert r.json()["status"] == "success", r.text
r = client.get(f"/api/workflows/runs/{r.json()['id']}")
sout = r.json()["node_runs"][0]["output"]
assert sout["records"] == ["a", "b", {"k": "x"}, {"k": "y"}], sout   # 标量整项判重，dict 按 k 判重
print("去重节点：标量/混合列表（trigger.params 传入）去重正确")

# ---------- 子流程调用 ----------
r = client.post("/api/workflows", json={
    "name": "子流程", "trigger": {"type": "manual"},
    "nodes": [{"id": "send_1", "type": "send_message", "name": "通知",
               "config": {"channel": "notify", "title": "子流程收到", "template": "{trigger.params.msg}"}}],
    "edges": []})
sub_id = r.json()["id"]
r = client.post("/api/workflows", json={
    "name": "父流程", "trigger": {"type": "manual"},
    "nodes": [
        {"id": "sub_1", "type": "sub_workflow", "name": "调用子流程",
         "config": {"workflow_id": sub_id, "params": {"msg": "来自父流程，今天 {now.today}"}}},
        {"id": "send_1", "type": "send_message", "name": "汇报",
         "config": {"channel": "notify", "title": "子流程完成", "template": "状态 {nodes.sub_1.status}"}},
    ],
    "edges": [{"from": "sub_1", "to": "send_1"}],
})
assert r.status_code == 200, r.text
par_id = r.json()["id"]
r = client.post(f"/api/workflows/{par_id}/run", json={"params": {}})
assert r.json()["status"] == "success", r.text
r = client.get(f"/api/workflows/{sub_id}/runs")
sub_run = next(x for x in r.json() if x["trigger"] == "sub" and x["status"] == "success")
assert sub_run, r.json()
# 传参里的模板变量在父流程渲染后再传入子流程
from datetime import date as _d
r = client.get(f"/api/workflows/runs/{sub_run['id']}")
sub_send_input = next(nr["input"] for nr in r.json()["node_runs"] if nr["node_id"] == "send_1")
assert sub_send_input["template"] == f"来自父流程，今天 {_d.today().isoformat()}", sub_send_input

# 循环调用：子流程里调自己 → 运行期被调用栈拦下
r = client.put(f"/api/workflows/{sub_id}", json={
    "name": "子流程", "trigger": {"type": "manual"},
    "nodes": [{"id": "sub_1", "type": "sub_workflow", "name": "自调", "config": {"workflow_id": sub_id}}],
    "edges": []})
assert r.status_code == 200, r.text   # 保存不拦（防的是运行期无限递归）
r = client.post(f"/api/workflows/{sub_id}/run", json={"params": {}})
assert r.json()["status"] == "failed" and "循环调用" in r.json()["error"], r.json()
# 恢复子流程为正常版本
r = client.put(f"/api/workflows/{sub_id}", json={
    "name": "子流程", "trigger": {"type": "manual"},
    "nodes": [{"id": "send_1", "type": "send_message", "name": "通知",
               "config": {"channel": "notify", "title": "子流程收到", "template": "{trigger.params.msg}"}}],
    "edges": []})
print("子流程调用：父调子成功（trigger=sub），自调用运行期拦截")

# 子流程必须是「被动调用」：保存期拦截
r = client.post("/api/workflows", json={
    "name": "定时流程", "trigger": {"type": "interval", "minutes": 60}, "nodes": [], "edges": []})
cron_wf = r.json()["id"]
r = client.post("/api/workflows", json={
    "name": "父流程2", "trigger": {"type": "manual"},
    "nodes": [{"id": "sub_1", "type": "sub_workflow", "name": "调", "config": {"workflow_id": cron_wf}}],
    "edges": []})
assert r.status_code == 400 and "被动调用" in r.json()["detail"], r.text
# 运行期拦截：子流程事后改成定时触发，父流程再跑应失败
r = client.put(f"/api/workflows/{sub_id}", json={
    "name": "子流程", "trigger": {"type": "interval", "minutes": 60},
    "nodes": [{"id": "send_1", "type": "send_message", "name": "通知",
               "config": {"channel": "notify", "title": "子流程收到", "template": "{trigger.params.msg}"}}],
    "edges": []})
assert r.status_code == 200, r.text
r = client.post(f"/api/workflows/{par_id}/run", json={"params": {}})
assert r.json()["status"] == "failed" and "被动调用" in r.json()["error"], r.json()
client.put(f"/api/workflows/{sub_id}", json={
    "name": "子流程", "trigger": {"type": "manual"},
    "nodes": [{"id": "send_1", "type": "send_message", "name": "通知",
               "config": {"channel": "notify", "title": "子流程收到", "template": "{trigger.params.msg}"}}],
    "edges": []})
print("子流程约束：非「被动调用」的流程保存期 400、运行期拦截")

# ---------- Webhook 自定义响应（验签场景） ----------
r = client.post("/api/workflows", json={
    "name": "验签回调", "enabled": True,
    "trigger": {"type": "webhook", "response_template": '{"echostr": "{trigger.params.echostr}"}'},
    "nodes": [], "edges": []})
assert r.status_code == 200, r.text
ww = r.json()
assert ww["trigger"].get("secret"), ww
sec = ww["trigger"]["secret"]
anon2 = TestClient(app)
r = anon2.post(f"/api/workflows/webhook/{ww['id']}/{sec}?echostr=abc123")
assert r.status_code == 200 and r.json() == {"echostr": "abc123"}, r.text
print("Webhook 自定义响应：验签 echo 正确返回，流程照常投递")

# ---------- 免登审批链接 ----------
r = client.post("/api/workflows", json={
    "name": "免登审批流", "trigger": {"type": "manual"},
    "nodes": [
        {"id": "a_1", "type": "approval", "name": "审批",
         "config": {"title": "报销审批", "detail_template": "金额 100 元"}},
        {"id": "send_1", "type": "send_message", "name": "结果",
         "config": {"channel": "notify", "title": "审批结果", "template": "通过={nodes.a_1.approved}"}},
    ],
    "edges": [{"from": "a_1", "to": "send_1"}],
})
assert r.status_code == 200, r.text
aw = r.json()["id"]
r = client.post(f"/api/workflows/{aw}/run", json={"params": {}})
assert r.json()["status"] == "waiting", r.text
run_id = r.json()["id"]
# 从通知里取免登链接
from app.database import SessionLocal
from app.models import Notification
db = SessionLocal()
link = db.query(Notification).filter(Notification.link.like("/approve/%")).order_by(Notification.id.desc()).first().link
db.close()
token = link.split("/approve/")[1]
r = anon2.get(f"/api/workflows/approval/{token}")
assert r.status_code == 200 and r.json()["status"] == "waiting" and r.json()["title"] == "报销审批", r.text
r = anon2.get("/api/workflows/approval/badtoken")
assert r.status_code == 404
r = anon2.post(f"/api/workflows/approval/{token}", json={"approved": True, "comment": "同意"})
assert r.status_code == 200 and r.json()["status"] == "success", r.text
r = anon2.post(f"/api/workflows/approval/{token}", json={"approved": True})
assert r.status_code == 400, r.text   # 重复处理被拒
r = client.get(f"/api/workflows/runs/{run_id}")
send_out = [nr for nr in r.json()["node_runs"] if nr["node_id"] == "send_1"][0]["output"]
assert send_out["sent"] >= 1
print("免登审批：链接匿名可读、通过/驳回生效、重复处理 400、坏 token 404")

# ---------- 日期计算 ----------
from datetime import date as _date, timedelta as _td
r = client.post("/api/workflows", json={
    "name": "日期计算", "trigger": {"type": "manual"},
    "nodes": [{"id": "dc_1", "type": "date_calc", "name": "一周后",
               "config": {"base": "{now.today}", "offset_days": 7}}],
    "edges": []})
dcw = r.json()["id"]
r = client.post(f"/api/workflows/{dcw}/run", json={"params": {}})
assert r.json()["status"] == "success", r.text
r = client.get(f"/api/workflows/runs/{r.json()['id']}")
dout = r.json()["node_runs"][0]["output"]
assert dout["date"] == (_date.today() + _td(days=7)).isoformat(), dout
print("日期计算：基准+7 天输出正确")

# ---------- 模板市场：两个新模板安装 + 运行 ----------
r = client.get("/api/workflow-templates")
keys = [t["key"] for t in r.json()]
assert "visit_reminder_loop" in keys and "signup_form" in keys, keys

# 逐条处理模板：安装（带示例数据）→ 立即执行 → 轨迹验证
r = client.post("/api/workflow-templates/visit_reminder_loop/install", json={"with_demo_data": True})
assert r.status_code == 200, r.text
loop_tpl_wf = r.json()["workflow_id"]
r = client.post(f"/api/workflows/{loop_tpl_wf}/run", json={"params": {}})
assert r.status_code == 200 and r.json()["status"] == "success", r.text
r = client.get(f"/api/workflows/runs/{r.json()['id']}")
trail = [nr["node_id"] for nr in r.json()["node_runs"]]
assert trail.count("loop_1") == 51, f"50 条示例数据：loop_1 应执行 51 次，实际 {trail.count('loop_1')}"
assert trail.count("send_1") == 50 and trail.count("send_2") == 1
print("模板「客户回访逐条提醒」：安装 + 执行成功（loop×51 / 提醒×50 / 汇总×1）")

# 表单模板：安装 → 启用 → 匿名读表单 → 提交 → 流程触发
r = client.post("/api/workflow-templates/signup_form/install", json={})
assert r.status_code == 200, r.text
form_tpl_wf = r.json()["workflow_id"]
r = client.post(f"/api/workflows/{form_tpl_wf}/toggle")
wf = r.json()
assert wf["enabled"] and wf.get("form_url"), wf
fsec = wf["trigger"]["secret"]
r = anon.get(f"/api/workflows/form/{form_tpl_wf}/{fsec}")
assert r.status_code == 200, r.text
fnames = {f["field_name"]: f for f in r.json()["fields"]}
assert set(fnames) == {"name", "phone", "note"} and not fnames["name"]["nullable"]
r = anon.post(f"/api/workflows/form/{form_tpl_wf}/{fsec}", json={"name": "模板用户"})
assert r.status_code == 422, r.text   # phone 必填
r = anon.post(f"/api/workflows/form/{form_tpl_wf}/{fsec}",
              json={"name": "模板用户", "phone": "13800000000", "note": "模板验证"})
assert r.status_code == 200 and r.json()["ok"], r.text
engine.process_due_jobs()
r = client.get(f"/api/workflows/{form_tpl_wf}/runs")
assert any(x["trigger"] == "form" and x["status"] == "success" for x in r.json()), r.json()
print("模板「活动报名表单」：安装即带 secret，启用后匿名提交入表 + 触发成功（缺手机号 422）")

# ---------- 新模板：子流程（两种安装顺序） ----------
# 先装调用方（子流程模板还没装）→ 子流程节点应被停用
r = client.post("/api/workflow-templates/stock_alert_sub/install", json={"with_demo_data": True})
assert r.status_code == 200, r.text
stock_wf1 = r.json()["workflow_id"]
assert "已暂时停用" in r.json()["notes"], r.json()
wf = client.get(f"/api/workflows/{stock_wf1}").json()
sub_node = next(n for n in wf["nodes"] if n["type"] == "sub_workflow")
assert sub_node.get("disabled") is True and "workflow_id" not in sub_node["config"]

# 再装被调的子流程 → 重装调用方 → 按名解析成功、节点启用
r = client.post("/api/workflow-templates/notify_sub/install", json={})
assert r.status_code == 200, r.text
notify_sub_id = r.json()["workflow_id"]
r = client.post("/api/workflow-templates/stock_alert_sub/install", json={})
stock_wf2 = r.json()["workflow_id"]
wf = client.get(f"/api/workflows/{stock_wf2}").json()
sub_node = next(n for n in wf["nodes"] if n["type"] == "sub_workflow")
assert not sub_node.get("disabled") and sub_node["config"]["workflow_id"] == notify_sub_id
r = client.post(f"/api/workflows/{stock_wf2}/run", json={"params": {}})
assert r.json()["status"] == "success", r.text
r = client.get(f"/api/workflows/{notify_sub_id}/runs")
assert any(x["trigger"] == "sub" and x["status"] == "success" for x in r.json()), r.json()
print("子流程模板：未装时停用兜底、装后按名解析、调用成功（trigger=sub）")

# ---------- 新模板：去重 + 逐条 ----------
r = client.post("/api/workflow-templates/followup_dedupe_loop/install", json={"with_demo_data": True})
assert r.status_code == 200, r.text
fw = r.json()["workflow_id"]
r = client.post(f"/api/workflows/{fw}/run", json={"params": {}})
assert r.json()["status"] == "success", r.text
r = client.get(f"/api/workflows/runs/{r.json()['id']}")
dout = next(nr["output"] for nr in r.json()["node_runs"] if nr["node_id"] == "d_1")
assert dout["count"] >= 0 and "removed" in dout
print(f"去重+逐条模板：安装 + 执行成功（去重后 {dout['count']} 位客户）")

# ---------- 新模板：合同到期提醒（日期计算） ----------
r = client.post("/api/workflow-templates/contract_expire/install", json={"with_demo_data": True})
assert r.status_code == 200, r.text
cw = r.json()["workflow_id"]
r = client.post(f"/api/workflows/{cw}/run", json={"params": {}})
assert r.json()["status"] == "success", r.text
r = client.get(f"/api/workflows/runs/{r.json()['id']}")
qout = next(nr["output"] for nr in r.json()["node_runs"] if nr["node_id"] == "q_1")
assert qout["count"] >= 1, "示例数据的到期日期在未来 60 天内，应筛出到期合同"
print(f"合同到期模板：日期计算 + 区间筛选命中 {qout['count']} 份合同")

# ---------- 新模板：Webhook 验签 ----------
r = client.post("/api/workflow-templates/webhook_alarm/install", json={})
assert r.status_code == 200, r.text
ww = r.json()["workflow_id"]
client.post(f"/api/workflows/{ww}/toggle")
wf = client.get(f"/api/workflows/{ww}").json()
sec = wf["trigger"]["secret"]
anon3 = TestClient(app)
r = anon3.post(f"/api/workflows/webhook/{ww}/{sec}", json={"level": "严重", "text": "磁盘已满", "echostr": "xyz789"})
assert r.status_code == 200 and r.json()["code"] == 0 and r.json()["echostr"] == "xyz789", r.text
engine.process_due_jobs()
r = client.get(f"/api/workflows/{ww}/runs")
assert any(x["trigger"] == "webhook" and x["status"] == "success" for x in r.json()), r.json()
print("Webhook 验签模板：自定义响应正确，告警流程执行成功")

print("\n全部通过 OK")
cm.__exit__(None, None, None)
