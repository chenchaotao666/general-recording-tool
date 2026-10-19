"""智能表内容权限（设计文档 §13）：总览面板 / 全员基线 / 指定成员组 / 组额外权限 / 我的有效权限。

管理者：条目所在表的主人或租户 admin（仪表盘：租户 admin 或文档主人）。
权限配置变更写审计日志（组、条目、等级快照）。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (MetaColumnGroup, Record, SmartDoc, SmartDocEntry, SmartEntryPermission,
                      SmartGroupGrant, SmartPermGroup, TenantMember, User)
from ..services import perm_service as ps
from ..services.dyn_engine import log_audit
from ..services.meta_service import get_meta_fields
from ..utils.access import TableAccess, get_table_access, require_table
from ..utils.context import Context, get_current_context

router = APIRouter(prefix="/api/smart", tags=["smart-perms"])

# 备注名内置词典（§13.2：通用/产品研发/常见岗位/项目分工/客户服务/订单采购）
REMARK_DICTIONARY = [
    {"category": "通用", "items": ["负责人", "参与人", "提出人", "跟进人", "审核人", "内部", "其他团队"]},
    {"category": "产品研发", "items": ["产品经理", "设计", "开发", "测试", "运维"]},
    {"category": "常见岗位", "items": ["经理", "组长", "员工", "实习生", "财务", "人事"]},
    {"category": "项目分工", "items": ["项目经理", "执行人", "协作人", "验收人"]},
    {"category": "客户服务", "items": ["客服", "客户经理", "售后", "销售"]},
    {"category": "订单采购", "items": ["采购", "仓管", "供应商", "物流"]},
]


# ---------- 工具 ----------

def _get_doc(db: Session, doc_id: int, ctx: Context) -> SmartDoc:
    doc = db.get(SmartDoc, doc_id)
    if not doc or doc.tenant_id != ctx.tenant.id:
        raise HTTPException(404, "文档不存在")
    return doc


def _get_entry(db: Session, entry_id: int, ctx: Context) -> SmartDocEntry:
    e = db.get(SmartDocEntry, entry_id)
    if not e or e.type == "folder":
        raise HTTPException(404, "条目不存在")
    _get_doc(db, e.doc_id, ctx)
    return e


def _is_doc_manager(db: Session, doc: SmartDoc, ctx: Context) -> bool:
    return bool(ctx.is_tenant_admin or doc.owner_id == ctx.user.id)


def _can_manage_entry(db: Session, e: SmartDocEntry, ctx: Context) -> bool:
    if e.ref_table_id:
        try:
            access = get_table_access(db, e.ref_table_id, ctx.user, ctx)
        except HTTPException:
            return False
        return access.is_owner or access.is_admin
    return _is_doc_manager(db, db.get(SmartDoc, e.doc_id), ctx)


def _require_entry_manager(db: Session, e: SmartDocEntry, ctx: Context) -> None:
    if not _can_manage_entry(db, e, ctx):
        raise HTTPException(403, "仅表格所有者或管理员可设置内容权限")


def _require_doc_manager(db: Session, doc: SmartDoc, ctx: Context) -> None:
    if not _is_doc_manager(db, doc, ctx):
        raise HTTPException(403, "仅文档所有者或管理员可管理指定成员")


def _user_names(db: Session, ids) -> list[dict]:
    out = []
    for uid in ids or []:
        try:
            u = db.get(User, int(uid))
        except (TypeError, ValueError):
            continue
        if u:
            out.append({"id": u.id, "name": u.username})
    return out


def _entries_of_doc(db: Session, doc_id: int) -> list[SmartDocEntry]:
    """非文件夹条目，按目录树先序排列（与左侧导航一致）。"""
    rows = (db.query(SmartDocEntry).filter_by(doc_id=doc_id)
            .order_by(SmartDocEntry.order_no, SmartDocEntry.id).all())
    by_parent: dict = {}
    for e in rows:
        by_parent.setdefault(e.parent_id, []).append(e)
    out = []

    def walk(pid, depth=0):
        if depth > 50:
            return
        for e in by_parent.get(pid, []):
            if e.type != "folder":
                out.append(e)
            walk(e.id, depth + 1)
    walk(None)
    return out


def _fields_of(db: Session, e: SmartDocEntry):
    return get_meta_fields(db, e.ref_table_id) if e.ref_table_id else []


def _group_out(db: Session, g: SmartPermGroup, entries: list[SmartDocEntry] | None = None) -> dict:
    grants = db.query(SmartGroupGrant).filter_by(group_id=g.id).all()
    by_entry = {gr.entry_id: gr for gr in grants}
    items = []
    for e in entries or []:
        gr = by_entry.get(e.id)
        if gr:
            prof = ps.normalize_profile(gr.profile, e.type)
            items.append({"entry_id": e.id, "name": e.name, "type": e.type,
                          "level": prof["level"], "summary": ps.summarize(prof, _fields_of(db, e), grant=True)})
    return {"id": g.id, "name": g.name, "member_ids": [int(x) for x in (g.member_ids or [])],
            "members": _user_names(db, g.member_ids), "grants": items}


# ---------- 成员目录（选人用：任何文档成员可读，返回 user_id） ----------

@router.get("/docs/{doc_id}/members")
def doc_members(doc_id: int, db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    _get_doc(db, doc_id, ctx)
    rows = db.query(TenantMember).filter_by(tenant_id=ctx.tenant.id, status="active").all()
    return {"members": _user_names(db, [m.user_id for m in rows])}


@router.get("/perm-dictionary")
def perm_dictionary():
    return {"categories": REMARK_DICTIONARY}


# ---------- 总览面板（§13.7） ----------

@router.get("/docs/{doc_id}/permissions")
def permission_overview(doc_id: int, db: Session = Depends(get_db),
                        ctx: Context = Depends(get_current_context)):
    doc = _get_doc(db, doc_id, ctx)
    entries = _entries_of_doc(db, doc_id)
    out_entries = []
    for e in entries:
        base = ps.base_profile_of(db, e)
        out_entries.append({
            "entry_id": e.id, "type": e.type, "name": e.name, "table_id": e.ref_table_id,
            "level": base["level"], "summary": ps.summarize(base, _fields_of(db, e)),
            "can_manage": _can_manage_entry(db, e, ctx),
        })
    groups = (db.query(SmartPermGroup).filter_by(doc_id=doc_id)
              .order_by(SmartPermGroup.order_no, SmartPermGroup.id).all())
    return {"entries": out_entries, "groups": [_group_out(db, g, entries) for g in groups],
            "can_manage_groups": _is_doc_manager(db, doc, ctx)}


# ---------- 条目权限详情（全员基线 + 各组额外权限） ----------

def _field_meta(db: Session, e: SmartDocEntry) -> list[dict]:
    fields = _fields_of(db, e)
    primary = ps.primary_field_name(fields)
    groups = (db.query(MetaColumnGroup).filter_by(table_id=e.ref_table_id)
              .order_by(MetaColumnGroup.order_no, MetaColumnGroup.id).all()) if e.ref_table_id else []
    group_of = {}
    for g in groups:
        for fn in g.field_names or []:
            group_of.setdefault(fn, g.name)
    return [{
        "field_name": f.field_name, "label": f.label, "field_type": f.field_type,
        "lockedEdit": (f.field_type or "") in ps.LOCKED_EDIT_TYPES,
        "forcedView": (f.field_type or "") in ps.SYSTEM_TYPES or f.field_name == primary,
        "group": group_of.get(f.field_name),
    } for f in fields]


@router.get("/entries/{entry_id}/permission")
def entry_permission(entry_id: int, db: Session = Depends(get_db),
                     ctx: Context = Depends(get_current_context)):
    e = _get_entry(db, entry_id, ctx)
    from ..services.tenancy import is_light_enterprise
    if e.ref_table_id and is_light_enterprise(db, ctx.tenant.id):
        get_table_access(db, e.ref_table_id, ctx.user, ctx)
    row = db.query(SmartEntryPermission).filter_by(entry_id=e.id).first()
    grants = (db.query(SmartGroupGrant).filter_by(entry_id=e.id).all())
    total = db.query(Record).filter_by(table_id=e.ref_table_id).count() if e.ref_table_id else 0
    return {
        "entry": {"id": e.id, "name": e.name, "type": e.type, "table_id": e.ref_table_id},
        "configured": row is not None,
        "base": ps.base_profile_of(db, e),
        "grants": {gr.group_id: ps.normalize_profile(gr.profile, e.type) for gr in grants},
        "record_total": total,
        "fields": _field_meta(db, e),
        "can_manage": _can_manage_entry(db, e, ctx),
    }


@router.put("/entries/{entry_id}/permission/base")
def put_base(entry_id: int, payload: dict, db: Session = Depends(get_db),
             ctx: Context = Depends(get_current_context)):
    e = _get_entry(db, entry_id, ctx)
    _require_entry_manager(db, e, ctx)
    prof = ps.normalize_profile(payload.get("profile"), e.type)
    row = db.query(SmartEntryPermission).filter_by(entry_id=e.id).first()
    before = row.base_profile if row else None
    if row is None:
        row = SmartEntryPermission(entry_id=e.id, base_profile=prof, updated_by=ctx.user.id)
        db.add(row)
    else:
        row.base_profile = prof
        row.updated_by = ctx.user.id
    log_audit(db, "smart_perm_base", e.ref_table_id,
              before={"entry_id": e.id, "profile": before},
              after={"entry_id": e.id, "level": prof["level"], "profile": prof},
              user=ctx.user.username, tenant_id=ctx.tenant.id)
    db.commit()
    return {"base": prof, "summary": ps.summarize(prof, _fields_of(db, e))}


@router.put("/entries/permission/base:batch")
def put_base_batch(payload: dict, db: Session = Depends(get_db),
                   ctx: Context = Depends(get_current_context)):
    """全员权限对话框「保存」一次提交多个条目：{items: [{entry_id, profile}]}。"""
    items = payload.get("items") or []
    if not isinstance(items, list) or len(items) > 200:
        raise HTTPException(400, "items 必须是数组（最多 200 项）")
    out = []
    for it in items:
        r = put_base(int(it.get("entry_id")), {"profile": it.get("profile")}, db, ctx)
        out.append({"entry_id": it.get("entry_id"), **r})
    return {"items": out}


# ---------- 指定成员组 ----------

def _get_group(db: Session, gid: int, ctx: Context) -> SmartPermGroup:
    g = db.get(SmartPermGroup, gid)
    if not g:
        raise HTTPException(404, "指定成员不存在")
    _get_doc(db, g.doc_id, ctx)
    return g


def _clean_members(db: Session, ctx: Context, ids) -> list[int]:
    out = []
    for x in ids or []:
        try:
            uid = int(x)
        except (TypeError, ValueError):
            continue
        if uid in out:
            continue
        if db.query(TenantMember).filter_by(tenant_id=ctx.tenant.id, user_id=uid, status="active").first():
            out.append(uid)
    return out


@router.post("/docs/{doc_id}/perm-groups")
def create_group(doc_id: int, payload: dict, db: Session = Depends(get_db),
                 ctx: Context = Depends(get_current_context)):
    doc = _get_doc(db, doc_id, ctx)
    _require_doc_manager(db, doc, ctx)
    name = str(payload.get("name") or "").strip()[:50]
    members = _clean_members(db, ctx, payload.get("member_ids"))
    if not members:
        raise HTTPException(400, "请选择指定成员")
    if not name:
        raise HTTPException(400, "请填写或选择备注")
    g = SmartPermGroup(doc_id=doc_id, name=name, member_ids=members,
                       order_no=db.query(SmartPermGroup).filter_by(doc_id=doc_id).count())
    db.add(g)
    db.commit()
    db.refresh(g)
    log_audit(db, "smart_perm_group", None, after={"group_id": g.id, "name": name, "members": members},
              user=ctx.user.username, tenant_id=ctx.tenant.id)
    db.commit()
    return {"group": _group_out(db, g, _entries_of_doc(db, doc_id))}


@router.patch("/perm-groups/{gid}")
def update_group(gid: int, payload: dict, db: Session = Depends(get_db),
                 ctx: Context = Depends(get_current_context)):
    g = _get_group(db, gid, ctx)
    _require_doc_manager(db, db.get(SmartDoc, g.doc_id), ctx)
    if "name" in payload:
        nm = str(payload["name"] or "").strip()[:50]
        if not nm:
            raise HTTPException(400, "备注不能为空")
        g.name = nm
    if "member_ids" in payload:
        members = _clean_members(db, ctx, payload["member_ids"])
        if not members:
            raise HTTPException(400, "请选择指定成员")
        g.member_ids = members
    db.commit()
    return {"group": _group_out(db, g, _entries_of_doc(db, g.doc_id))}


@router.delete("/perm-groups/{gid}")
def delete_group(gid: int, db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    g = _get_group(db, gid, ctx)
    _require_doc_manager(db, db.get(SmartDoc, g.doc_id), ctx)
    db.query(SmartGroupGrant).filter_by(group_id=g.id).delete()
    log_audit(db, "smart_perm_group_delete", None, before={"group_id": g.id, "name": g.name},
              user=ctx.user.username, tenant_id=ctx.tenant.id)
    db.delete(g)
    db.commit()
    return {"ok": True}


@router.get("/perm-groups/{gid}/grants")
def group_grants(gid: int, db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    g = _get_group(db, gid, ctx)
    entries = _entries_of_doc(db, g.doc_id)
    grants = {gr.entry_id: gr for gr in db.query(SmartGroupGrant).filter_by(group_id=g.id).all()}
    items = []
    for e in entries:
        gr = grants.get(e.id)
        prof = ps.normalize_profile(gr.profile, e.type) if gr else None
        items.append({"entry_id": e.id, "name": e.name, "type": e.type, "table_id": e.ref_table_id,
                      "profile": prof, "summary": ps.summarize(prof, _fields_of(db, e), grant=True)})
    return {"group": _group_out(db, g, entries), "items": items}


@router.put("/perm-groups/{gid}/grants/{entry_id}")
def put_grant(gid: int, entry_id: int, payload: dict, db: Session = Depends(get_db),
              ctx: Context = Depends(get_current_context)):
    g = _get_group(db, gid, ctx)
    e = _get_entry(db, entry_id, ctx)
    if e.doc_id != g.doc_id:
        raise HTTPException(400, "条目不属于该文档")
    _require_entry_manager(db, e, ctx)
    from ..services.tenancy import is_light_enterprise
    if is_light_enterprise(db, ctx.tenant.id) and not db.query(SmartEntryPermission).filter_by(entry_id=e.id).first():
        db.add(SmartEntryPermission(entry_id=e.id, base_profile=ps.level_profile("NONE"), updated_by=ctx.user.id))
    prof = ps.normalize_profile(payload.get("profile"), e.type)
    gr = db.query(SmartGroupGrant).filter_by(group_id=g.id, entry_id=e.id).first()
    if gr is None:
        gr = SmartGroupGrant(group_id=g.id, entry_id=e.id, profile=prof)
        db.add(gr)
    else:
        gr.profile = prof
    log_audit(db, "smart_perm_grant", e.ref_table_id,
              after={"group_id": g.id, "group": g.name, "entry_id": e.id, "level": prof["level"], "profile": prof},
              user=ctx.user.username, tenant_id=ctx.tenant.id)
    db.commit()
    return {"profile": prof, "summary": ps.summarize(prof, _fields_of(db, e), grant=True)}


@router.delete("/perm-groups/{gid}/grants/{entry_id}")
def delete_grant(gid: int, entry_id: int, db: Session = Depends(get_db),
                 ctx: Context = Depends(get_current_context)):
    """恢复至全员权限：删除该组对该条目的额外权限。"""
    g = _get_group(db, gid, ctx)
    e = _get_entry(db, entry_id, ctx)
    _require_entry_manager(db, e, ctx)
    db.query(SmartGroupGrant).filter_by(group_id=g.id, entry_id=e.id).delete()
    log_audit(db, "smart_perm_grant_delete", e.ref_table_id, before={"group_id": g.id, "entry_id": e.id},
              user=ctx.user.username, tenant_id=ctx.tenant.id)
    db.commit()
    return {"ok": True}


# ---------- 我的有效权限（网格页/表单渲染用） ----------

@router.get("/tables/{table_id}/my-permission")
def my_permission(table_id: int, db: Session = Depends(get_db),
                  access: TableAccess = Depends(require_table("view"))):
    eff = ps.effective_for_access(db, access)
    if eff.level == "NONE":
        raise HTTPException(404, "数据表不存在")
    return eff.to_client(get_meta_fields(db, table_id))
