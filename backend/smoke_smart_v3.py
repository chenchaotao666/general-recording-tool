# -*- coding: utf-8 -*-
"""冒烟测试：智能表 V3——内容权限（行列级 + $viewer + 指定成员组）、自动化（新增/变更/定时 + 动作链 + 变量 + 日志）、
表单（生成/显示条件/必填/公开收集/收集表单组合对象）、AI 字段（标签匹配/查重/配额）、AI 生成公式、AI 匹配标签、看板视图。
用法：cd backend && .venv/Scripts/python -I smoke_smart_v3.py"""
import json
import os
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).parent
DB = BASE / "smoke_smart_v3.db"
if DB.exists():
    DB.unlink()
os.environ["GRT_DATABASE_URL"] = f"sqlite:///{DB.as_posix()}"
os.environ["GRT_SMART_SYNC"] = "1"   # 事件同步执行，便于断言自动化/AI 结果
sys.path.insert(0, str(BASE))

from fastapi.testclient import TestClient  # noqa: E402

import app.services.llm as llm_pkg  # noqa: E402
from app.main import app  # noqa: E402
from app.services.field_registry import to_field_in  # noqa: E402
from app.utils.auth import hash_password  # noqa: E402

cm = TestClient(app)
client = cm.__enter__()

# ---------- 准备：企业租户 B（u2=admin，u3/u4=普通成员） ----------
con = sqlite3.connect(DB)
for name in ("u2", "u3", "u4"):
    con.execute("INSERT INTO users (username, password_hash, role, is_platform_admin) VALUES (?, ?, 'user', 0)",
                (name, hash_password("pass123456")))
uid = {n: con.execute("SELECT id FROM users WHERE username=?", (n,)).fetchone()[0] for n in ("u2", "u3", "u4")}
con.execute("INSERT INTO tenants (name, type, owner_user_id) VALUES ('企业B', 'enterprise', ?)", (uid["u2"],))
tb = con.execute("SELECT id FROM tenants WHERE owner_user_id=?", (uid["u2"],)).fetchone()[0]
con.execute("INSERT INTO tenant_members (tenant_id, user_id, role, status) VALUES (?, ?, 'admin', 'active')", (tb, uid["u2"]))
for n in ("u3", "u4"):
    con.execute("INSERT INTO tenant_members (tenant_id, user_id, role, status) VALUES (?, ?, 'user', 'active')", (tb, uid[n]))
plan = con.execute("SELECT id FROM plans WHERE code='free'").fetchone()[0]
con.execute("INSERT INTO subscriptions (tenant_id, plan_id, seats, status) VALUES (?, ?, 5, 'active')", (tb, plan))
con.commit()
con.close()


def headers(user):
    r = client.post("/api/auth/login", json={"username": user, "password": "pass123456"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}", "X-Tenant-Id": str(tb)}


H2, H3, H4 = headers("u2"), headers("u3"), headers("u4")


def call(method, url, h=H2, expect=200, **kw):
    r = getattr(client, method)(url, headers=h, **kw)
    assert r.status_code == expect, f"{method.upper()} {url} → {r.status_code} {r.text[:300]}"
    return r.json() if r.content else None


def add_field(tid, field_type, label, config=None):
    names = {f["field_name"] for f in call("get", f"/api/tables/{tid}")["fields"]}
    n = 1
    while f"f_{n}" in names:
        n += 1
    call("post", f"/api/tables/{tid}/alter", json={"ops": [{"op": "add_field", "field": to_field_in(field_type, label, f"f_{n}", config)}]})
    return f"f_{n}"


doc_id = call("get", "/api/smart/docs/current")["id"]
r = call("post", f"/api/smart/docs/{doc_id}/entries", json={"type": "sheet", "name": "产品表"})
entry, tid = r["entry"], r["table_id"]
F = {f["field_type"]: f["field_name"] for f in call("get", f"/api/tables/{tid}")["fields"]}
fcb = add_field(tid, "createdBy", "创建人")
# 清掉默认 5 行空记录，便于计数
for row in call("get", f"/api/smart/tables/{tid}/grid")["items"]:
    call("delete", f"/api/smart/tables/{tid}/records/{row['id']}")
ra = call("post", f"/api/smart/tables/{tid}/records", json={"data": {F["text"]: "A-u2", F["number"]: 10}})["record"]
rb = call("post", f"/api/smart/tables/{tid}/records", json={"data": {F["text"]: "B-u2", F["number"]: 20}})["record"]
rc = call("post", f"/api/smart/tables/{tid}/records", h=H3, json={"data": {F["text"]: "C-u3", F["number"]: 30}})["record"]
print("准备：企业租户 + 3 名成员 + 产品表 3 条记录")

# ================= 1. 内容权限 =================
ov = call("get", f"/api/smart/docs/{doc_id}/permissions")
assert ov["entries"][0]["summary"] == "全部权限" and ov["can_manage_groups"]
call("put", f"/api/smart/entries/{entry['id']}/permission/base", h=H3, expect=403,
     json={"profile": {"level": "VIEW"}})   # 普通成员不能配置

base = {"level": "EDIT", "viewManage": False,
        "record": {"editScope": "PARTIAL", "editFallback": "VIEW_ONLY", "add": True, "delete": False,
                   "editConditions": [{"fieldId": fcb, "operator": "contains", "value": "$viewer"}]},
        "fields": {"mode": "PER_FIELD", "newFieldDefault": {"view": True, "firstSubmit": True, "edit": True},
                   "items": {F["number"]: {"view": False, "firstSubmit": False, "edit": False},
                             F["date"]: {"view": True, "firstSubmit": True, "edit": False}}}}
r = call("put", f"/api/smart/entries/{entry['id']}/permission/base", json={"profile": base})
assert r["summary"] == "可编辑部分内容", r

g = call("get", f"/api/smart/tables/{tid}/grid", h=H3)
assert F["number"] not in {f["field_name"] for f in g["fields"]}, "无查看权的列不应返回"
rows = {x["id"]: x for x in g["items"]}
assert F["number"] not in rows[ra["id"]], "行数据里也不应含隐藏列"
assert rows[ra["id"]].get("__readonly") and not rows[rc["id"]].get("__readonly"), "仅自己创建的行可编辑"
assert g["content_perm"]["canDeleteRecord"] is False and g["my_perms"]["can_delete"] is False
print("行列级读路径：隐藏列裁剪 + $viewer 编辑范围 + 只可查看降级 通过")

call("patch", f"/api/smart/tables/{tid}/records/{ra['id']}", h=H3, expect=403, json={"data": {F["text"]: "x"}})
call("patch", f"/api/smart/tables/{tid}/records/{rc['id']}", h=H3, expect=403, json={"data": {F["date"]: "2026-01-01"}})
call("patch", f"/api/smart/tables/{tid}/records/{rc['id']}", h=H3, json={"data": {F["text"]: "C-u3-改"}})
call("delete", f"/api/smart/tables/{tid}/records/{rc['id']}", h=H3, expect=403)
call("post", f"/api/smart/tables/{tid}/views", h=H3, expect=403, json={"name": "我的视图"})
# 新建记录：隐藏列的值被静默丢弃（firstSubmit=false）
nr = call("post", f"/api/smart/tables/{tid}/records", h=H3, json={"data": {F["text"]: "D-u3", F["number"]: 999}})["record"]
assert nr[F["number"]] is None, nr
print("写路径：行条件复核 / 字段白名单 / 删除与视图管理开关 / 新建字段裁剪 通过")

# 指定成员组：u3 → 全部权限（grant-only 叠加）
grp = call("post", f"/api/smart/docs/{doc_id}/perm-groups", json={"name": "负责人", "member_ids": [uid["u3"]]})["group"]
call("put", f"/api/smart/perm-groups/{grp['id']}/grants/{entry['id']}", json={"profile": {"level": "FULL"}})
g = call("get", f"/api/smart/tables/{tid}/grid", h=H3)
assert F["number"] in {f["field_name"] for f in g["fields"]} and not any(x.get("__readonly") for x in g["items"])
call("patch", f"/api/smart/tables/{tid}/records/{ra['id']}", h=H3, json={"data": {F["text"]: "A-u3改"}})
g4 = call("get", f"/api/smart/tables/{tid}/grid", h=H4)
assert F["number"] not in {f["field_name"] for f in g4["fields"]}, "非组成员仍按全员基线"
ov = call("get", f"/api/smart/docs/{doc_id}/permissions")
assert ov["groups"][0]["grants"][0]["summary"] == "全部权限" and ov["groups"][0]["members"][0]["name"] == "u3"
call("delete", f"/api/smart/perm-groups/{grp['id']}/grants/{entry['id']}")
print("指定成员组额外权限：叠加生效 / 非成员不受影响 / 恢复至全员权限 通过")

# 仅浏览 + 部分记录可查看
call("put", f"/api/smart/entries/{entry['id']}/permission/base", json={"profile": {
    "level": "VIEW", "record": {"viewScope": "PARTIAL",
                                "viewConditions": [{"fieldId": fcb, "operator": "contains", "value": "$viewer"}]}}})
g = call("get", f"/api/smart/tables/{tid}/grid", h=H3)
assert {x["id"] for x in g["items"]} == {rc["id"], nr["id"]}, [x["id"] for x in g["items"]]
call("post", f"/api/smart/tables/{tid}/records", h=H3, expect=403, json={"data": {}})
call("put", f"/api/smart/entries/{entry['id']}/permission/base", json={"profile": {"level": "NONE"}})
call("get", f"/api/smart/tables/{tid}/grid", h=H3, expect=404)
call("put", f"/api/smart/entries/{entry['id']}/permission/base", json={"profile": {"level": "FULL"}})
print("仅浏览查看范围 / 无权限 404 通过")

# ================= 2. 自动化 =================
r2 = call("post", f"/api/smart/docs/{doc_id}/entries", json={"type": "sheet", "name": "日志表"})
tid2 = r2["table_id"]
F2 = {f["field_type"]: f["field_name"] for f in call("get", f"/api/tables/{tid2}")["fields"]}
rule1 = call("post", f"/api/smart/tables/{tid}/automations", json={
    "name": "新品提醒",
    "trigger": {"type": "recordCreated",
                "rowConditions": [{"fieldId": F["text"], "operator": "isNotEmpty"}],
                "filter": {"match": "all", "conditions": [{"fieldId": F["text"], "operator": "contains", "value": "新品"}]}},
    "actions": [
        {"type": "sendMessage", "channel": "docMessage", "to": [uid["u4"]], "title": "新品提醒",
         "content": [{"t": "text", "v": "新增了 "}, {"t": "var", "var": {"kind": "step", "step": 1, "key": "field", "field": F["text"]}},
                     {"t": "text", "v": "，操作人 "}, {"t": "var", "var": {"kind": "step", "step": 1, "key": "operator"}}]},
        {"type": "updateRecords", "tableId": tid, "target": "triggered",
         "values": [{"fieldId": F["number"], "value": {"type": "static", "value": 99}}]},
    ]})["automation"]
call("post", f"/api/smart/tables/{tid}/records", json={"data": {}})   # 空行：不满足前置条件，不触发
call("post", f"/api/smart/tables/{tid}/records", json={"data": {F["text"]: "旧品X"}})   # 过滤器不满足
rec = call("post", f"/api/smart/tables/{tid}/records", json={"data": {F["text"]: "新品Y"}})["record"]
runs = call("get", f"/api/smart/automations/{rule1['id']}/runs")["runs"]
assert len(runs) == 1 and runs[0]["status"] == "success", runs
row = next(x for x in call("get", f"/api/smart/tables/{tid}/grid")["items"] if x["id"] == rec["id"])
assert float(row[F["number"]]) == 99, row
notes = call("get", "/api/notify", h=H4)
items = notes if isinstance(notes, list) else (notes.get("items") or notes.get("notifications") or [])
assert any("新品Y" in (n.get("content") or "") and "u2" in (n.get("content") or "") for n in items), items
print("自动化·添加新记录：前置条件 + 过滤器 + 发送消息（变量插值）+ 修改触发记录 + 运行日志 通过")

rule2 = call("post", f"/api/smart/tables/{tid}/automations", json={
    "name": "状态变更留痕",
    "trigger": {"type": "recordUpdated", "watchFields": [F["singleSelect"]], "filter": {"conditions": []}},
    "actions": [
        {"type": "findRecords", "tableId": tid, "conditions": [{"fieldId": F["text"], "operator": "contains", "value": "新品"}],
         "onNotFound": "continue"},
        {"type": "createRecord", "tableId": tid2, "values": [
            {"fieldId": F2["text"], "value": {"type": "var", "var": {"kind": "step", "step": 1, "key": "field", "field": F["singleSelect"]}}},
            {"fieldId": F2["number"], "value": {"type": "var", "var": {"kind": "step", "step": 2, "key": "count"}}}]},
    ]})["automation"]
call("patch", f"/api/smart/tables/{tid}/records/{rec['id']}", json={"data": {F["text"]: "新品Y2"}})   # 非监听列
assert not call("get", f"/api/smart/automations/{rule2['id']}/runs")["runs"]
call("patch", f"/api/smart/tables/{tid}/records/{rec['id']}", json={"data": {F["singleSelect"]: "opt_2"}})
runs = call("get", f"/api/smart/automations/{rule2['id']}/runs")["runs"]
assert len(runs) == 1 and runs[0]["status"] == "success", runs
logs = [x for x in call("get", f"/api/smart/tables/{tid2}/grid")["items"] if x.get(F2["text"])]
assert logs and logs[-1][F2["text"]] == "选项2" and float(logs[-1][F2["number"]]) == 1, logs[-1]
print("自动化·记录内容变更：监听列 + 查找记录 + 新增记录（跨表，变量取选项标签/查找计数）通过")

rule3 = call("post", f"/api/smart/tables/{tid}/automations", json={
    "name": "定时提醒", "trigger": {"type": "schedule", "schedule": {"freq": "weekly", "time": "19:30", "weekdays": [1, 5]}},
    "actions": [{"type": "sendMessage", "channel": "docMessage", "to": [uid["u2"]],
                 "content": [{"t": "text", "v": "请查看文档内容 "}, {"t": "var", "var": {"kind": "time", "key": "today"}}]}]})["automation"]
call("post", f"/api/smart/tables/{tid}/automations", expect=400, json={
    "trigger": {"type": "schedule", "schedule": {"freq": "daily", "time": "25:00"}},
    "actions": [{"type": "sendMessage", "to": [uid["u2"]]}]})
from app.services.scheduler import scheduler as aps  # noqa: E402
assert aps.get_job(f"smart_auto_{rule3['id']}") is not None, "定时规则应注册到调度器"
run = call("post", f"/api/smart/automations/{rule3['id']}/run")["run"]
assert run["status"] == "success", run
call("patch", f"/api/smart/automations/{rule3['id']}", json={"enabled": False})
assert aps.get_job(f"smart_auto_{rule3['id']}") is None
call("post", f"/api/smart/tables/{tid}/automations", h=H4, expect=200, json={
    "trigger": {"type": "recordCreated"}, "actions": [{"type": "sendMessage", "to": [uid["u4"]]}]})
print("自动化·定时：校验 / 调度注册 / 手动运行 / 停用注销 通过")

# ================= 3. 表单 =================
fv = call("post", f"/api/smart/tables/{tid}/views", json={"type": "form", "name": "表单"})["view"]
items = fv["config"]["form"]["items"]
assert fcb not in [i["fieldId"] for i in items] and items[0]["fieldId"] == F["text"]
for it in items:
    if it["fieldId"] == F["text"]:
        it["required"] = True
    if it["fieldId"] == F["number"]:   # 数字题：仅当单选=选项1 时显示且必填
        it["required"] = True
        it["visibility"] = {"match": "all", "conditions": [{"fieldId": F["singleSelect"], "operator": "eq", "value": "opt_1"}]}
call("patch", f"/api/smart/views/{fv['id']}", json={"config": {"form": {**fv["config"]["form"], "items": items}}})
call("post", f"/api/smart/views/{fv['id']}/submit", expect=422, json={"data": {F["singleSelect"]: "opt_2"}})
call("post", f"/api/smart/views/{fv['id']}/submit", expect=422, json={"data": {F["text"]: "表单1", F["singleSelect"]: "opt_1"}})
rr = call("post", f"/api/smart/views/{fv['id']}/submit", json={"data": {F["text"]: "表单2", F["singleSelect"]: "opt_2", F["number"]: 5}})
assert rr["record"][F["number"]] is None, "隐藏题的值不入库"
link = call("post", f"/api/smart/views/{fv['id']}/share-link", json={})["link"]
pub = client.get(f"/api/smart-public/forms/{link['token']}").json()
assert pub["title"] == "表单" and pub["items"][0]["field"]["label"] == "文本"
r = client.post(f"/api/smart-public/forms/{link['token']}/submit", json={"data": {F["text"]: "新品公开填写"}})
assert r.status_code == 200, r.text
row = next(x for x in call("get", f"/api/smart/tables/{tid}/grid")["items"] if x["id"] == r.json()["id"])
assert row[fcb] is None and float(row[F["number"]]) == 99, "匿名填写者 + 回流触发「添加新记录时」自动化"
call("post", f"/api/smart/views/{fv['id']}/share-link", json={"password": "abcd"})
assert client.get(f"/api/smart-public/forms/{link['token']}").status_code == 403
assert client.get(f"/api/smart-public/forms/{link['token']}?password=abcd").status_code == 200
print("表单：生成 / 必填 / 显示条件 / 登录提交 / 公开收集（匿名 + 回流自动化 + 密码）通过")

cf = call("post", f"/api/smart/docs/{doc_id}/entries", json={"type": "form", "name": "报名表"})
views = call("get", f"/api/smart/tables/{cf['table_id']}/views")["views"]
assert [(v["name"], v["type"]) for v in views] == [("收集表单", "form"), ("表单收集结果", "grid")], views
assert len(views[0]["config"]["form"]["items"]) == 3
kb = call("post", f"/api/smart/tables/{tid}/views", json={"type": "kanban"})["view"]
assert kb["config"]["kanban"]["groupField"] == F["singleSelect"]
print("收集表单组合对象（表单 + 结果表，默认 3 题）/ 看板视图 通过")

# ================= 4. AI =================
class FakeProvider:
    last_usage = {"prompt_tokens": 10, "completion_tokens": 5}

    def complete(self, prompt, system=None):
        if "公式专家" in (system or ""):
            return json.dumps({"formula": "[数字] * 2", "returnType": "number", "explanation": "数字翻倍"})
        if "配置助手" in (system or ""):
            return json.dumps({"title": "文本分类", "desc": "根据 [文本] 内容分类", "inputLabel": "待分类的文本",
                               "prompt": "你是一个分类专家。\n任务：分类。\n输入：文本。", "outputType": "singleSelect",
                               "options": ["自然风光", "人文景观"], "inputs": ["文本"]}, ensure_ascii=False)
        if '"items"' in (system or ""):
            ids = [x["id"] for x in json.loads(prompt)]
            return json.dumps({"items": [{"id": i, "value": "电子"} for i in ids]})
        text = prompt
        return json.dumps({"value": ["自然风光"] if "山" in text else ["人文景观"]}, ensure_ascii=False)

    def recognize(self, images, prompt, system=None):
        return json.dumps({"value": "图片"})


llm_pkg.get_default_provider = lambda db: FakeProvider()
fai = add_field(tid, "ai", "匹配标签", {"scene": "tagMatch", "inputFields": [F["text"]], "outputType": "multiSelect",
                                        "options": [], "autoUpdate": True, "allowNewOptions": True})
r = call("post", f"/api/smart/tables/{tid}/records", json={"data": {F["text"]: "青山绿水"}})["record"]
fmeta = next(f for f in call("get", f"/api/tables/{tid}")["fields"] if f["field_name"] == fai)
labels = {o["id"]: o["label"] for o in fmeta["options"]["options"]}
row = next(x for x in call("get", f"/api/smart/tables/{tid}/grid")["items"] if x["id"] == r["id"])
assert [labels[i] for i in row[fai]] == ["自然风光"], row[fai]
fmb = add_field(tid, "lastModifiedBy", "最后编辑人")
row = next(x for x in call("get", f"/api/smart/tables/{tid}/grid")["items"] if x["id"] == r["id"])
assert row[fmb] == "__ai__", row[fmb]
# AI 单元格可手动修正（网格内编辑）；修正后最后编辑人变为用户
call("patch", f"/api/smart/tables/{tid}/records/{r['id']}", json={"data": {fai: []}})
row = next(x for x in call("get", f"/api/smart/tables/{tid}/grid")["items"] if x["id"] == r["id"])
assert row[fai] in (None, []) and row[fmb] != "__ai__", (row[fai], row[fmb])
q = call("post", f"/api/smart/tables/{tid}/fields/{fai}/ai-run", json={"scope": "all"})
assert q["queued"] >= 1 and q["quota"]["limit"] == 200 and q["quota"]["used"] >= 1, q
print(f"AI 字段·标签匹配：自动建选项 / 最后编辑人=AI / 可手动修正 / 批量刷新 / 配额（{q['quota']['used']}/{q['quota']['limit']}）通过")

fdup = add_field(tid, "ai", "重复", {"scene": "markDuplicate", "inputFields": [F["text"]], "outputType": "checkbox"})
call("post", f"/api/smart/tables/{tid}/fields/{fdup}/ai-run", json={})
call("post", f"/api/smart/tables/{tid}/records", json={"data": {F["text"]: "青山绿水"}})
dups = [x for x in call("get", f"/api/smart/tables/{tid}/grid")["items"] if x.get(F["text"]) == "青山绿水"]
assert len(dups) == 2 and all(x[fdup] is True for x in dups), [x[fdup] for x in dups]
print("AI 字段·标记重复值（本地计算，新增行联动全表重算）通过")

gf = call("post", "/api/smart/ai/generate-formula", json={"table_id": tid, "prompt": "数字乘以2"})
assert gf["formula"] == f"[{F['number']}] * 2" and gf["display"] == "[数字] * 2", gf
mt = call("post", f"/api/smart/tables/{tid}/fields/{F['singleSelect']}/ai-match-tags",
          json={"source_fields": [F["text"]], "only_empty": True, "allow_new": True})
assert mt["updated"] >= 1 and mt["created_options"] == 1, mt
print("AI 生成公式（标签→字段名还原 + 语法校验）/ AI 匹配标签（批量 + 自动建选项）通过")

# AI 配置生成 + 真实数据效果预览（不落库）/ 生成前 N 行 / 本地场景（不计配额）
cf = call("post", f"/api/smart/tables/{tid}/ai/configure", json={"scene": "classify", "input_fields": [F["text"]], "instruction": "按风景类型"})
cfg_ = cf["config"]
assert cfg_["title"] == "文本分类" and cfg_["systemPrompt"].startswith("你是一个分类专家") and cfg_["outputType"] == "singleSelect", cfg_
assert cf["preview"] and all(r["error"] is None for r in cf["preview"]), cf["preview"]
olabels = {o["id"]: o["label"] for o in cfg_["options"]}
assert all(olabels.get(r["output"]) in ("自然风光", "人文景观") for r in cf["preview"]), (cf["preview"], olabels)
fcls = add_field(tid, "ai", "文本分类", cfg_)
nrec = len(call("get", f"/api/smart/tables/{tid}/grid")["items"])
q5 = call("post", f"/api/smart/tables/{tid}/fields/{fcls}/ai-run", json={"scope": "all", "limit": 2})
assert q5["queued"] == 2 <= nrec, q5
used0 = call("get", "/api/smart/ai/quota")["used"]
cf2 = call("post", f"/api/smart/tables/{tid}/ai/configure", json={"scene": "cvB64Enc", "input_fields": [F["text"]]})
assert cf2["config"]["systemPrompt"] == "" and cf2["preview"][0]["output"], cf2
assert call("get", "/api/smart/ai/quota")["used"] == used0   # 本地场景不计配额
pv = call("post", f"/api/smart/tables/{tid}/ai/preview", json={"config": {**cfg_, "outputType": "text"}})
assert pv["preview"] and isinstance(pv["preview"][0]["output"], str), pv
call("post", f"/api/smart/tables/{tid}/ai/configure", expect=400, json={"scene": "imRemoveBg", "input_fields": [F["text"]]})
# 自定义 AI 字段：AI 生成的配置（提示词在 systemPrompt）可直接保存并生成
cfc = call("post", f"/api/smart/tables/{tid}/ai/configure", json={"scene": "custom", "input_fields": [F["text"]],
                                                                   "instruction": "根据[文本]生成问候语"})["config"]
assert cfc["systemPrompt"] and not cfc.get("prompt"), cfc
fcus = add_field(tid, "ai", "问候语", cfc)
qc = call("post", f"/api/smart/tables/{tid}/fields/{fcus}/ai-run", json={"scope": "all", "limit": 1})
assert qc["queued"] == 1, qc
print("AI 字段·配置生成 / 效果预览 / 生成前 N 行 / 本地场景不计配额 / 自定义字段保存 通过")
# 编辑 AI 单选字段：提交的选项表缺了仍被单元格引用的选项（前端拿着旧选项表）→ 保留；明确删除（removedOptionIds）→ 不保留
fm_ = next(f for f in call("get", f"/api/tables/{tid}")["fields"] if f["field_name"] == fcls)
used_ids = {r.get(fcls) for r in call("get", f"/api/smart/tables/{tid}/grid")["items"] if r.get(fcls)}
assert used_ids, "分类字段应已生成值"
cfg_stale = {**fm_["options"], "options": []}
call("post", f"/api/tables/{tid}/alter", json={"ops": [{"op": "update_field", "field_name": fcls, "field_type": "ai", "options": cfg_stale}]})
kept = {o["id"] for o in next(f for f in call("get", f"/api/tables/{tid}")["fields"] if f["field_name"] == fcls)["options"]["options"]}
assert used_ids <= kept, (used_ids, kept)
call("post", f"/api/tables/{tid}/alter", json={"ops": [{"op": "update_field", "field_name": fcls, "field_type": "ai",
                                                         "options": {**cfg_stale, "removedOptionIds": list(used_ids)}}]})
fm2 = next(f for f in call("get", f"/api/tables/{tid}")["fields"] if f["field_name"] == fcls)["options"]
assert not ({o["id"] for o in fm2["options"]} & used_ids) and "removedOptionIds" not in fm2, fm2
print("AI 字段·编辑保存：仍在用的选项不被冲掉 / 明确删除的选项不补回 通过")
sc = call("get", "/api/smart/ai/scenes")
assert {"tagMatch", "summary", "extract", "pdfToText", "custom"} <= {s["key"] for s in sc["scenes"]}
# 视图筛选：创建人 包含「我」（$viewer）→ 只剩查看者自己创建的记录（系统字段值注入 + 人员集合语义）
gid_ = next(v for v in call("get", f"/api/smart/tables/{tid}/views", h=H3)["views"] if v["type"] == "grid")["id"]
call("put", f"/api/smart/views/{gid_}/prefs", h=H3, json={"config": {"filters": {"conjunction": "and", "conditions": [
    {"fieldId": fcb, "operator": "contains", "value": ["$viewer"]}]}}})
mine = call("get", f"/api/smart/tables/{tid}/grid", h=H3, params={"view_id": gid_})["items"]
assert mine and all(str(x[fcb]) == str(uid["u3"]) for x in mine), [x[fcb] for x in mine]
call("put", f"/api/smart/views/{gid_}/prefs", h=H3, json={"config": {"filters": {"conjunction": "and", "conditions": [
    {"fieldId": fcb, "operator": "contains", "value": [uid["u2"]]}]}}})
theirs = call("get", f"/api/smart/tables/{tid}/grid", h=H3, params={"view_id": gid_})["items"]
assert theirs and all(str(x[fcb]) == str(uid["u2"]) for x in theirs)
print("视图筛选：创建人 包含 我（$viewer）/ 指定成员 通过")
# 固定到工具栏但尚未填值的条件不生效（不过滤任何记录）
call("put", f"/api/smart/views/{gid_}/prefs", h=H3, json={"config": {"filters": {"conjunction": "and", "conditions": []}}})
all_n = len(call("get", f"/api/smart/tables/{tid}/grid", h=H3, params={"view_id": gid_})["items"])
call("put", f"/api/smart/views/{gid_}/prefs", h=H3, json={"config": {"filters": {"conjunction": "and", "conditions": [
    {"fieldId": fcb, "operator": "contains", "value": [], "pinned": True}]}}})
assert len(call("get", f"/api/smart/tables/{tid}/grid", h=H3, params={"view_id": gid_})["items"]) == all_n
print("视图筛选：未填值的固定条件不生效 通过")

print("\nV3 冒烟全部通过 ✅")
cm.__exit__(None, None, None)
