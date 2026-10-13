"""智能表文档与条目树（设计文档 §2.2/§2.5）：默认文档惰性创建、条目 CRUD、新建工作表模板。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import MetaTable, MetaView, SmartDoc, SmartDocEntry
from ..schemas import FieldIn, TableCreate
from ..services import entitlement, meta_service
from ..services.dyn_engine import log_audit
from ..services.field_registry import default_sheet_fields, gen_field_name, to_field_in
from ..services.meta_service import MetaError
from ..utils.access import get_table_access
from ..utils.context import Context, get_current_context

router = APIRouter(prefix="/api/smart", tags=["smart"])


# ---------- 工具 ----------

def _get_doc(db: Session, doc_id: int, ctx: Context) -> SmartDoc:
    doc = db.get(SmartDoc, doc_id)
    if not doc or doc.tenant_id != ctx.tenant.id:
        raise HTTPException(404, "文档不存在")
    return doc


def _get_entry(db: Session, entry_id: int, ctx: Context) -> SmartDocEntry:
    e = db.get(SmartDocEntry, entry_id)
    if not e:
        raise HTTPException(404, "条目不存在")
    _get_doc(db, e.doc_id, ctx)   # 租户隔离
    return e


def _entry_out(e: SmartDocEntry) -> dict:
    return {
        "id": e.id, "doc_id": e.doc_id, "parent_id": e.parent_id, "type": e.type,
        "name": e.name, "ref_table_id": e.ref_table_id, "order_no": e.order_no,
        "created_at": e.created_at.isoformat(sep=" ") if e.created_at else None,
    }


def _is_descendant(db: Session, ancestor_id: int, maybe_child_id: int) -> bool:
    """防环：maybe_child 是否是 ancestor 的子孙（沿 parent 链向上走）。"""
    cur = maybe_child_id
    depth = 0
    while cur is not None and depth < 50:
        if cur == ancestor_id:
            return True
        cur_e = db.get(SmartDocEntry, cur)
        cur = cur_e.parent_id if cur_e else None
        depth += 1
    return False


def _next_order(db: Session, doc_id: int, parent_id: int | None) -> int:
    q = db.query(SmartDocEntry).filter_by(doc_id=doc_id, parent_id=parent_id)
    return (q.count())


# ---------- 默认文档 ----------

@router.get("/docs/current")
def get_current_doc(db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    """当前租户的默认智能表文档，不存在则惰性创建（V1 单文档）。"""
    doc = (db.query(SmartDoc)
           .filter_by(tenant_id=ctx.tenant.id, is_default=True)
           .first())
    if not doc:
        doc = SmartDoc(tenant_id=ctx.tenant.id, name="智能表", owner_id=ctx.user.id, is_default=True)
        db.add(doc)
        db.commit()
        db.refresh(doc)
    return {"id": doc.id, "name": doc.name, "is_default": doc.is_default}


@router.get("/docs/{doc_id}/tree")
def get_tree(doc_id: int, db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    """条目平铺列表（前端按 parent_id+order_no 组树）。"""
    _get_doc(db, doc_id, ctx)
    rows = (db.query(SmartDocEntry).filter_by(doc_id=doc_id)
            .order_by(SmartDocEntry.order_no, SmartDocEntry.id).all())
    return {"doc_id": doc_id, "entries": [_entry_out(e) for e in rows]}


# ---------- 条目 CRUD ----------

@router.post("/docs/{doc_id}/entries")
def create_entry(doc_id: int, payload: dict, db: Session = Depends(get_db),
                 ctx: Context = Depends(get_current_context)):
    """新建条目。type=folder 直接建行；type=sheet 组合事务：建表(json)+默认5字段+5空行+默认视图+条目。"""
    doc = _get_doc(db, doc_id, ctx)
    etype = payload.get("type")
    name = str(payload.get("name") or "").strip()
    parent_id = payload.get("parent_id")
    if etype not in ("folder", "sheet"):
        raise HTTPException(400, "条目类型必须是 folder 或 sheet")
    if parent_id is not None:
        parent = db.get(SmartDocEntry, parent_id)
        if not parent or parent.doc_id != doc_id or parent.type != "folder":
            raise HTTPException(400, "父条目必须是本文档内的文件夹")

    if etype == "folder":
        e = SmartDocEntry(doc_id=doc_id, parent_id=parent_id, type="folder",
                          name=name or "文件夹", order_no=_next_order(db, doc_id, parent_id))
        db.add(e)
        db.commit()
        db.refresh(e)
        return {"entry": _entry_out(e)}

    # sheet：组合事务
    entitlement.assert_tenant_writable(db, ctx.tenant.id)
    entitlement.check_quota(db, ctx.tenant.id, "max_tables")
    label = name or "工作表"
    fields = []
    names = set()
    for tpl in default_sheet_fields():
        fn = gen_field_name(names)
        names.add(fn)
        fields.append(FieldIn(**to_field_in(tpl["field_type"], tpl["label"], fn, tpl.get("config"))))
    try:
        mt = meta_service.create_business_table(
            db, TableCreate(label=label, fields=fields, storage_mode="json"),
            owner_id=ctx.user.id, tenant_id=ctx.tenant.id)
        # 默认 5 行空记录
        from ..services import json_store
        json_store.bulk_insert(db, mt.id, [{}] * 5)
        # 默认视图
        v = MetaView(table_id=mt.id, name="表格视图", type="grid", config={}, is_default=True,
                     created_by=ctx.user.id)
        db.add(v)
        db.flush()
        e = SmartDocEntry(doc_id=doc_id, parent_id=parent_id, type="sheet", name=label,
                          ref_table_id=mt.id, order_no=_next_order(db, doc_id, parent_id))
        db.add(e)
        db.commit()
    except MetaError as ex:
        db.rollback()
        raise HTTPException(400, str(ex))
    except Exception as ex:
        db.rollback()
        raise HTTPException(400, f"新建工作表失败：{ex}")
    entitlement.bump_usage(db, ctx.tenant.id, "table_count", 1)
    log_audit(db, "create_table", mt.id, after={"name": mt.name, "label": mt.label, "via": "smart"},
              user=ctx.user.username, tenant_id=ctx.tenant.id)
    db.commit()
    db.refresh(e)
    return {"entry": _entry_out(e), "table_id": mt.id}


@router.patch("/entries/{entry_id}")
def update_entry(entry_id: int, payload: dict, db: Session = Depends(get_db),
                 ctx: Context = Depends(get_current_context)):
    """重命名 / 移入文件夹（防环）。"""
    e = _get_entry(db, entry_id, ctx)
    if "name" in payload:
        nm = str(payload["name"] or "").strip()
        if not nm:
            raise HTTPException(400, "名称不能为空")
        e.name = nm[:128]
    if "parent_id" in payload:
        pid = payload["parent_id"]
        if pid is not None:
            parent = db.get(SmartDocEntry, pid)
            if not parent or parent.doc_id != e.doc_id or parent.type != "folder":
                raise HTTPException(400, "目标必须是本文档内的文件夹")
            if e.type == "folder" and _is_descendant(db, e.id, pid):
                raise HTTPException(400, "不能移动到自身或其子文件夹内")
        e.parent_id = pid
    # sheet 改名联动表 label
    if "name" in payload and e.type == "sheet" and e.ref_table_id:
        mt = db.get(MetaTable, e.ref_table_id)
        if mt:
            mt.label = e.name
    db.commit()
    db.refresh(e)
    return {"entry": _entry_out(e)}


@router.delete("/entries/{entry_id}")
def delete_entry(entry_id: int, db: Session = Depends(get_db),
                 ctx: Context = Depends(get_current_context)):
    """folder 非空拒绝；sheet 级联删表（需表的删除权限）。"""
    e = _get_entry(db, entry_id, ctx)
    if e.type == "folder":
        children = db.query(SmartDocEntry).filter_by(parent_id=e.id).count()
        if children:
            raise HTTPException(409, "文件夹非空，请先移出或删除其中的条目")
        db.delete(e)
        db.commit()
        return {"ok": True}
    # sheet：校验表的删除权限
    if e.ref_table_id:
        access = get_table_access(db, e.ref_table_id, ctx.user, ctx)
        if not access.can_delete:
            raise HTTPException(404, "数据表不存在")
        mt = db.get(MetaTable, e.ref_table_id)
        if mt:
            meta_service.drop_business_table(db, mt)
            db.query(MetaView).filter_by(table_id=mt.id).delete()
            entitlement.bump_usage(db, ctx.tenant.id, "table_count", -1)
            log_audit(db, "delete_table", mt.id, before={"name": mt.name, "label": mt.label},
                      user=ctx.user.username, tenant_id=ctx.tenant.id)
    db.delete(e)
    db.commit()
    return {"ok": True}


@router.get("/entries/{entry_id}/table")
def entry_table(entry_id: int, db: Session = Depends(get_db),
                ctx: Context = Depends(get_current_context)):
    """sheet 条目 → 表详情（含字段与我的权限），进入网格页时调用。"""
    e = _get_entry(db, entry_id, ctx)
    if e.type != "sheet" or not e.ref_table_id:
        raise HTTPException(400, "该条目不是工作表")
    mt = db.get(MetaTable, e.ref_table_id)
    if not mt:
        raise HTTPException(404, "数据表不存在")
    access = get_table_access(db, mt.id, ctx.user, ctx)
    if not access.can_view:
        raise HTTPException(404, "数据表不存在")
    return meta_service.table_out(db, mt, with_fields=True, access=access.my_perms())
