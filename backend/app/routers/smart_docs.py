"""智能表文档与条目树（设计文档 §2.2/§2.5）：默认文档惰性创建、条目 CRUD、新建工作表模板。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (MetaTable, MetaView, SmartAutomation, SmartAutomationRun, SmartDoc, SmartDocEntry,
                      SmartEntryPermission, SmartGroupGrant)
from ..schemas import FieldIn, TableCreate
from ..services import entitlement, meta_service
from ..services.dyn_engine import log_audit
from ..services.field_registry import (FIELD_TYPES, default_sheet_fields, gen_field_name,
                                       infer_select_options, to_field_in)
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
    from ..services.tenancy import is_light_enterprise
    if is_light_enterprise(db, ctx.tenant.id):
        from ..utils.access import _resolve_grant
        rows = [e for e in rows if not e.ref_table_id or _resolve_grant(db, e.ref_table_id, ctx.user, ctx)]
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
    if etype not in ("folder", "sheet", "dashboard", "form"):
        raise HTTPException(400, "条目类型必须是 folder / sheet / dashboard / form")
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

    if etype == "dashboard":
        e = SmartDocEntry(doc_id=doc_id, parent_id=parent_id, type="dashboard",
                          name=name or "仪表盘", order_no=_next_order(db, doc_id, parent_id))
        db.add(e)
        db.commit()
        db.refresh(e)
        return {"entry": _entry_out(e)}

    if etype == "form":
        return _create_collect_form(db, doc_id, parent_id, name or "收集表单", ctx)

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


def _create_collect_form(db: Session, doc_id: int, parent_id, label: str, ctx: Context) -> dict:
    """新建 → 收集表单（§2.5/§12.1）：表单 + 结果表组合对象。默认 3 题（文本题/单选题/图片题），
    视图页签为「收集表单 | 表单收集结果」，表单视图为默认视图。"""
    from ..services import view_config
    entitlement.assert_tenant_writable(db, ctx.tenant.id)
    entitlement.check_quota(db, ctx.tenant.id, "max_tables")
    tpls = [
        ("text", "文本题", None),
        ("singleSelect", "单选题", {"options": [{"id": f"opt_{i}", "label": f"选项{i}",
                                                 "color": c, "order": i - 1}
                                                for i, c in ((1, "blue"), (2, "green"), (3, "orange"))],
                                    "allowAddOptionWhenEditing": True}),
        ("image", "图片题", None),
    ]
    fields, names = [], set()
    for ft, lb, cfg in tpls:
        fn = gen_field_name(names)
        names.add(fn)
        fields.append(FieldIn(**to_field_in(ft, lb, fn, cfg)))
    try:
        mt = meta_service.create_business_table(
            db, TableCreate(label=label, fields=fields, storage_mode="json"),
            owner_id=ctx.user.id, tenant_id=ctx.tenant.id)
        from ..services.meta_service import get_meta_fields
        mfields = get_meta_fields(db, mt.id)
        form_cfg = view_config.validate_view_config(
            {"form": {"title": label, "items": view_config.default_form_items(mfields)}}, mfields)
        db.add(MetaView(table_id=mt.id, name="收集表单", type="form", config=form_cfg, is_default=True,
                        created_by=ctx.user.id))
        db.add(MetaView(table_id=mt.id, name="表单收集结果", type="grid", config={}, is_default=False,
                        created_by=ctx.user.id))
        e = SmartDocEntry(doc_id=doc_id, parent_id=parent_id, type="form", name=label,
                          ref_table_id=mt.id, order_no=_next_order(db, doc_id, parent_id))
        db.add(e)
        db.commit()
    except MetaError as ex:
        db.rollback()
        raise HTTPException(400, str(ex))
    entitlement.bump_usage(db, ctx.tenant.id, "table_count", 1)
    log_audit(db, "create_table", mt.id, after={"name": mt.name, "label": mt.label, "via": "smart_form"},
              user=ctx.user.username, tenant_id=ctx.tenant.id)
    db.commit()
    db.refresh(e)
    return {"entry": _entry_out(e), "table_id": mt.id}


def _purge_entry_extras(db: Session, e: SmartDocEntry) -> None:
    """条目删除前清理 V3 附属配置：内容权限 / 组额外权限 / 自动化规则与日志。"""
    db.query(SmartEntryPermission).filter_by(entry_id=e.id).delete()
    db.query(SmartGroupGrant).filter_by(entry_id=e.id).delete()
    if e.ref_table_id:
        rule_ids = [a.id for a in db.query(SmartAutomation.id).filter_by(table_id=e.ref_table_id).all()]
        if rule_ids:
            db.query(SmartAutomationRun).filter(SmartAutomationRun.rule_id.in_(rule_ids)).delete(
                synchronize_session=False)
            db.query(SmartAutomation).filter(SmartAutomation.id.in_(rule_ids)).delete(synchronize_session=False)
    db.flush()


@router.patch("/entries/{entry_id}")
def update_entry(entry_id: int, payload: dict, db: Session = Depends(get_db),
                 ctx: Context = Depends(get_current_context)):
    """重命名 / 移入文件夹（防环）。"""
    e = _get_entry(db, entry_id, ctx)
    from ..services.tenancy import is_light_enterprise
    if e.ref_table_id and is_light_enterprise(db, ctx.tenant.id):
        access = get_table_access(db, e.ref_table_id, ctx.user, ctx)
        if not (access.is_owner or access.is_admin):
            raise HTTPException(403, "仅创建者或企业管理员可调整表格名称和位置")
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
    # sheet / form 改名联动表 label
    if "name" in payload and e.type in ("sheet", "form") and e.ref_table_id:
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
    _purge_entry_extras(db, e)
    # sheet / form：校验表的删除权限
    if e.ref_table_id:
        table_id = e.ref_table_id
        access = get_table_access(db, table_id, ctx.user, ctx)
        if not access.can_delete:
            raise HTTPException(404, "数据表不存在")
        mt = db.get(MetaTable, table_id)
        if mt:
            # 先取审计所需字段：drop_business_table 内部 commit 后对象即过期不可再访问；
            # 且其已级联删除引用该表的条目（含 e），此处无需也不能再 db.delete(e)
            mt_name, mt_label, mt_pk = mt.name, mt.label, mt.id
            meta_service.drop_business_table(db, mt)
            db.query(MetaView).filter_by(table_id=mt_pk).delete()
            entitlement.bump_usage(db, ctx.tenant.id, "table_count", -1)
            log_audit(db, "delete_table", mt_pk, before={"name": mt_name, "label": mt_label},
                      user=ctx.user.username, tenant_id=ctx.tenant.id)
            db.commit()
            return {"ok": True}
    db.delete(e)
    db.commit()
    return {"ok": True}


@router.get("/entries/{entry_id}/table")
def entry_table(entry_id: int, db: Session = Depends(get_db),
                ctx: Context = Depends(get_current_context)):
    """sheet 条目 → 表详情（含字段与我的权限），进入网格页时调用。"""
    e = _get_entry(db, entry_id, ctx)
    if e.type not in ("sheet", "form") or not e.ref_table_id:
        raise HTTPException(400, "该条目不是工作表")
    mt = db.get(MetaTable, e.ref_table_id)
    if not mt:
        raise HTTPException(404, "数据表不存在")
    access = get_table_access(db, mt.id, ctx.user, ctx)
    if not access.can_view:
        raise HTTPException(404, "数据表不存在")
    return meta_service.table_out(db, mt, with_fields=True, access=access.my_perms())


# ---------- 导入本地 Excel（复用 excel.py 探测/推断 + tables._run_import 批次导入） ----------

_EXCEL_TYPE_MAP = {"varchar": "text", "text": "text", "int": "number", "decimal": "number",
                   "date": "date", "datetime": "date", "bool": "checkbox"}


@router.post("/docs/{doc_id}/import-excel")
def import_excel(doc_id: int, payload: dict, db: Session = Depends(get_db),
                 ctx: Context = Depends(get_current_context)):
    """导入本地 Excel 建工作表：{file_id, sheet_name, header_row, name, parent_id, columns?}。
    columns 缺省时用本地统计推断（excel_parser.infer_column_type）→ 映射为智能表字段类型。"""
    from ..services.excel_parser import read_sheet, trim_rows
    from ..services.typemap import infer_column_type
    from ..services.uploads import get_upload_path
    from .tables import _run_import
    from ..schemas import SourceIn

    _get_doc(db, doc_id, ctx)
    file_id = payload.get("file_id")
    sheet_name = payload.get("sheet_name")
    header_row = int(payload.get("header_row") or 1)
    if not file_id or not sheet_name:
        raise HTTPException(400, "缺少 file_id / sheet_name")

    path = get_upload_path(file_id)
    rows = trim_rows(read_sheet(path, sheet_name))
    if len(rows) < header_row:
        raise HTTPException(400, "表头行超出范围")
    headers = [str(h or f"列{i + 1}") for i, h in enumerate(rows[header_row - 1])]
    samples = rows[header_row: header_row + 50]

    # 列映射：默认本地推断；调用方可传 columns 覆盖（label/field_type）
    overrides = {c["index"]: c for c in (payload.get("columns") or []) if isinstance(c, dict)}
    fields = []
    names = set()
    for i, h in enumerate(headers):
        ov = overrides.get(i) or {}
        ft = ov.get("field_type")
        cfg = None
        if ft not in FIELD_TYPES:
            col_samples = [r[i] if i < len(r) else None for r in samples]
            ft = _EXCEL_TYPE_MAP.get(infer_column_type(col_samples), "text")
            if ft == "text":
                # 低基数文本列 → 单选（选项从全量数据提取，避免 50 行样本外的取值漏配）
                col_all = [r[i] if i < len(r) else None for r in rows[header_row:]]
                sel_opts = infer_select_options(col_all)
                if sel_opts:
                    ft = "singleSelect"
                    cfg = {"options": sel_opts, "allowAddOptionWhenEditing": True}
        fn = gen_field_name(names)
        names.add(fn)
        fin = to_field_in(ft, str(ov.get("label") or h), fn, config=cfg)
        fin["source_header"] = h
        fields.append(FieldIn(**fin))

    entitlement.assert_tenant_writable(db, ctx.tenant.id)
    entitlement.check_quota(db, ctx.tenant.id, "max_tables")
    try:
        mt = meta_service.create_business_table(
            db, TableCreate(label=str(payload.get("name") or "导入的工作表"), fields=fields, storage_mode="json"),
            owner_id=ctx.user.id, tenant_id=ctx.tenant.id)
        v = MetaView(table_id=mt.id, name="表格视图", type="grid", config={}, is_default=True,
                     created_by=ctx.user.id)
        db.add(v)
        db.flush()
        e = SmartDocEntry(doc_id=doc_id, parent_id=payload.get("parent_id"), type="sheet",
                          name=mt.label, ref_table_id=mt.id,
                          order_no=_next_order(db, doc_id, payload.get("parent_id")))
        db.add(e)
        db.commit()
        report = _run_import(db, mt, SourceIn(file_id=file_id, sheet_name=sheet_name, header_row=header_row))
    except MetaError as ex:
        db.rollback()
        raise HTTPException(400, str(ex))
    entitlement.bump_usage(db, ctx.tenant.id, "table_count", 1)
    log_audit(db, "create_table", mt.id, after={"name": mt.name, "label": mt.label, "via": "smart_import"},
              user=ctx.user.username, tenant_id=ctx.tenant.id)
    db.commit()
    db.refresh(e)
    return {"entry": _entry_out(e), "table_id": mt.id, "import_report": report}
