# 记事本/画板 文件夹功能冒烟测试（打一次性实例 :8011）
import json
import urllib.request

B = "http://127.0.0.1:8011/api"


def call(method, path, body=None, token=None, expect_error=False):
    req = urllib.request.Request(B + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


_, login = call("POST", "/auth/login", {"username": "admin", "password": "admin123"})
tok = login["token"]
ok = 0
fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS {name}")
    else:
        fail += 1
        print(f"  FAIL {name} {extra}")


for prefix, label in (("/notes", "记事本"), ("/whiteboards", "画板")):
    print(f"== {label} ==")
    s, folder = call("POST", prefix, {"kind": "folder", "title": "文件夹1"}, tok)
    check("新建文件夹", s == 200 and folder["kind"] == "folder" and folder["title"] == "文件夹1", folder)
    fid = folder["id"]

    s, page = call("POST", prefix, {"title": "页面A"}, tok)
    check("新建页面默认 kind=page", s == 200 and page["kind"] == "page", page)
    pid = page["id"]

    s, r = call("PUT", f"{prefix}/{pid}", {"parent_id": fid}, tok)
    check("页面移入文件夹", s == 200 and r["parent_id"] == fid, r)

    s, r = call("DELETE", f"{prefix}/{fid}", token=tok)
    check("删除非空文件夹被拒(400)", s == 400 and "非空" in r["detail"], r)

    s, r = call("PUT", f"{prefix}/{pid}", {"parent_id": None}, tok)
    check("页面移回根级", s == 200 and r["parent_id"] is None, r)

    # 防环：F1 下建 F2，再把 F1 移到 F2 下
    s, f2 = call("POST", prefix, {"kind": "folder", "title": "F2", "parent_id": fid}, tok)
    check("文件夹嵌套", s == 200 and f2["parent_id"] == fid, f2)
    s, r = call("PUT", f"{prefix}/{fid}", {"parent_id": f2["id"]}, tok)
    check("移到自己子孙下被拒(400)", s == 400, r)

    s, r = call("GET", prefix + "/tree", token=tok)
    kinds = {n["id"]: n["kind"] for n in r[prefix.strip("/")]}
    check("tree 返回 kind 字段", kinds.get(fid) == "folder" and kinds.get(pid) == "page", kinds)

    s, r = call("PUT", f"{prefix}/{fid}", {"title": "改名为资料夹"}, tok)
    check("文件夹重命名", s == 200 and r["title"] == "改名为资料夹", r)

    s, r = call("DELETE", f"{prefix}/{f2['id']}", token=tok)
    s, r = call("DELETE", f"{prefix}/{fid}", token=tok)
    check("删除空文件夹", s == 200 and r.get("ok"), r)
    call("DELETE", f"{prefix}/{pid}", token=tok)

print(f"\n结果：{ok} 通过，{fail} 失败")
raise SystemExit(1 if fail else 0)
