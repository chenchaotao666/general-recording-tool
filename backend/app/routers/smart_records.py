"""智能表网格与记录操作（设计文档 §16.3、§7）：

grid 查询处理链：视图+个人覆盖合并 → DSL 适配 → 筛选 → 分组/多级排序 → 树形组装 → 聚合分页；
lookup 字段读时计算；系统字段（创建人/时间等）从记录系统列注入。
记录写操作包装 json_store（parent_id/updated_by/只读字段拦截在 json_store 层）。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import MetaField, MetaTable, MetaView, MetaViewPref, Record
from ..services import dyn_engine, json_store, lookup_service, view_config
from ..services.field_registry import FIELD_TYPES
from ..services.meta_service import get_meta_fields
from ..services.pyquery import match_filters, sort_records_multi
from ..utils.access import TableAccess, require_table

router = APIRouter(prefix="/api/smart", tags=["smart-records"])

SYSTEM_FIELD_KEYS = {ft: reg["sys_key"] for ft, reg in FIELD_TYPES.items() if reg.get("sys_key")}


def _load_effective_view(db: Session, table_id: int, view_id: int | None, user_id: int):
    vq = db.query(MetaView).filter_by(table_id=table_id)
    view = vq.filter_by(id=view_id).first() if view_id else None
    if view is None:
        view = vq.order_by(MetaView.is_default.desc(), MetaView.id).first()
    vcfg = (view.config or {}) if view else {}
    pref = None
    if view:
        pref = db.query(MetaViewPref).filter_by(view_id=view.id, user_id=user_id).first()
    return view, view_config.merge_pref(vcfg, pref.config if pref else None)


def _inject_system_and_lookup(db: Session, fields: list[MetaField], rows: list[dict]) -> None:
    """就地填充：系统字段值（sys_key → 记录系统列）+ lookup 读时计算。"""
    src_cache = {}
    lookup_fields = [f for f in fields if f.field_type == "lookup"]
    for f in lookup_fields:
        for rid, val in lookup_service.compute_lookup(db, f, rows, src_cache).items():
            for r in rows:
                if r.get("id") == rid:
                    r[f.field_name] = val
    sys_fields = [f for f in fields if (f.field_type or "") in SYSTEM_FIELD_KEYS]
    for r in rows:
        for f in sys_fields:
            r[f.field_name] = r.get(SYSTEM_FIELD_KEYS[f.field_type])


@router.get("/tables/{table_id}/grid")
def grid_query(table_id: int, view_id: int | None = None, page: int = 1, page_size: int = 200,
               db: Session = Depends(get_db),
               access: TableAccess = Depends(require_table("view"))):
    """一次请求给齐网格渲染所需：生效视图配置 + 字段 + 记录行序列 + 聚合 + 我的权限。
    有分组时返回扁平的 [分组标题行, ...数据行] 序列（上限 5000 行，不分页）。"""
    mt = access.table
    if mt.storage_mode != "json":
        raise HTTPException(400, "智能表网格仅支持 JSON 存储模式的表")
    user = access.ctx.user

    view, effective = _load_effective_view(db, table_id, view_id, user.id)
    fields = get_meta_fields(db, table_id)
    fields_by_name = {f.field_name: f for f in fields}

    rules = view_config.conditions_to_rules(effective.get("filters"))
    recs = json_store.all_dicts(db, table_id, fields, normalized=True)
    if rules:
        logic = "OR" if (effective.get("filters") or {}).get("conjunction") == "or" else "AND"
        recs = [r for r in recs if match_filters(r, fields_by_name, {"logic": logic, "rules": rules})]
    aggs = view_config.compute_aggregations(recs, effective.get("aggregations"), fields)
    total = len(recs)

    groups = effective.get("groups") or []
    if groups:
        # 分组模式：扁平序列（组头+行），不分页，上限 5000
        flat = view_config.flatten_grouped(
            recs[:5000], groups, fields_by_name, effective.get("sorts"), effective.get("aggregations"))
        rows = [{k: dyn_engine.serialize_value(v) for k, v in r.items()} if r.get("__rowType") != "group"
                else r for r in flat]
    else:
        recs = sort_records_multi(recs, effective.get("sorts"), fields_by_name)
        page = max(page, 1)
        page_size = min(max(page_size, 1), dyn_engine.MAX_PAGE_SIZE)
        rows = [{k: dyn_engine.serialize_value(v) for k, v in r.items()}
                for r in recs[(page - 1) * page_size: page * page_size]]

    # 系统字段 + lookup（仅对输出的数据行计算）
    data_rows = [r for r in rows if r.get("__rowType") != "group"]
    _inject_system_and_lookup(db, fields, data_rows)

    return {
        "items": rows, "total": total, "aggregations": aggs, "grouped": bool(groups),
        "view": {"id": view.id, "name": view.name, "type": view.type, "config": effective,
                 "is_default": bool(view.is_default)} if view else None,
        "fields": [
            {"id": f.id, "field_name": f.field_name, "label": f.label, "data_type": f.data_type,
             "field_type": f.field_type, "options": f.options or {}, "sort_order": f.sort_order}
            for f in fields
        ],
        "my_perms": access.my_perms(),
    }


# ---------- 统计行：按列统计方式选择 ----------
@router.get("/tables/{table_id}/field-stats")
def field_stats(table_id: int, field_name: str, view_id: int | None = None,
                db: Session = Depends(get_db),
                access: TableAccess = Depends(require_table("view"))):
    """某字段在当前视图筛选后全集上的全部可用统计值（统计行菜单展示用）。"""
    user = access.ctx.user
    view, effective = _load_effective_view(db, table_id, view_id, user.id)
    fields = get_meta_fields(db, table_id)
    fields_by_name = {f.field_name: f for f in fields}
    f = fields_by_name.get(field_name)
    if f is None:
        raise HTTPException(404, f"字段不存在：{field_name}")

    rules = view_config.conditions_to_rules(effective.get("filters"))
    recs = json_store.all_dicts(db, table_id, fields, normalized=True)
    if rules:
        logic = "OR" if (effective.get("filters") or {}).get("conjunction") == "or" else "AND"
        recs = [r for r in recs if match_filters(r, fields_by_name, {"logic": logic, "rules": rules})]
    stats = {a: view_config.compute_stat(recs, field_name, a) for a in view_config.field_stat_kinds(f)}
    return {"field_name": field_name, "total": len(recs), "stats": stats}


# ---------- 记录 CRUD（包装 json_store，带 parent_id/updated_by） ----------

@router.post("/tables/{table_id}/records")
def create_record(table_id: int, payload: dict, db: Session = Depends(get_db),
                  access: TableAccess = Depends(require_table("create"))):
    """新增记录。data=字段值；parent_id=树形父记录（校验同表存在且防环由更新路径把关）。"""
    parent_id = payload.get("parent_id")
    if parent_id is not None:
        parent = db.get(Record, int(parent_id))
        if not parent or parent.table_id != table_id:
            raise HTTPException(400, "父记录不存在")
    fields = get_meta_fields(db, table_id)
    rec = json_store.create_record(db, access.table, fields, payload.get("data") or {},
                                   user=access.ctx.user.username, owner_id=access.ctx.user.id,
                                   parent_id=parent_id)
    return {"record": rec}


@router.patch("/tables/{table_id}/records/{record_id}")
def update_record(table_id: int, record_id: int, payload: dict, db: Session = Depends(get_db),
                  access: TableAccess = Depends(require_table("edit"))):
    fields = get_meta_fields(db, table_id)
    # 树形父记录变更（防环：父不能是自身或其后代）
    if "parent_id" in payload:
        pid = payload["parent_id"]
        if pid is not None:
            pid = int(pid)
            if pid == record_id:
                raise HTTPException(400, "父记录不能是自身")
            cur, depth = pid, 0
            while cur is not None and depth < 100:
                if cur == record_id:
                    raise HTTPException(400, "不能移动到自己的子记录下（会形成环）")
                p = db.get(Record, cur)
                cur = p.parent_id if p and p.table_id == table_id else None
                depth += 1
        rec = db.get(Record, record_id)
        if not rec or rec.table_id != table_id:
            raise HTTPException(404, "记录不存在")
        rec.parent_id = pid
        db.commit()
    data = payload.get("data") or {}
    if data:
        rec = json_store.update_record(db, access.table, fields, record_id, data,
                                       user=access.ctx.user.username, editor_id=access.ctx.user.id)
        return {"record": rec}
    rec = db.get(Record, record_id)
    fbn = {f.field_name: f for f in fields}
    return {"record": json_store._row_to_client(rec, fbn)}


@router.delete("/tables/{table_id}/records/{record_id}")
def delete_record(table_id: int, record_id: int, db: Session = Depends(get_db),
                  access: TableAccess = Depends(require_table("delete"))):
    """删除记录：子记录上提一级（孤子上提策略，设计文档 §7.4）。"""
    children = db.query(Record).filter_by(table_id=table_id, parent_id=record_id).all()
    rec = db.get(Record, record_id)
    for c in children:
        c.parent_id = rec.parent_id if rec else None
    fields = get_meta_fields(db, table_id)
    json_store.delete_record(db, table_id, record_id, fields, user=access.ctx.user.username)
    return {"ok": True, "orphans_lifted": len(children)}


@router.post("/tables/{table_id}/records:batch-delete")
def batch_delete(table_id: int, payload: dict, db: Session = Depends(get_db),
                 access: TableAccess = Depends(require_table("delete"))):
    """批量删除记录（撤销栈靠前端快照重建）。"""
    ids = payload.get("ids") or []
    if not isinstance(ids, list) or not ids or len(ids) > 500:
        raise HTTPException(400, "ids 必须是非空数组（最多 500 条）")
    fields = get_meta_fields(db, table_id)
    deleted = 0
    for rid in ids:
        try:
            rec = db.get(Record, int(rid))
            if not rec or rec.table_id != table_id:
                continue
            for c in db.query(Record).filter_by(table_id=table_id, parent_id=int(rid)).all():
                c.parent_id = rec.parent_id
            json_store.delete_record(db, table_id, int(rid), fields, user=access.ctx.user.username)
            deleted += 1
        except HTTPException:
            continue
    db.commit()
    return {"deleted": deleted}


@router.post("/tables/{table_id}/records/{record_id}/duplicate")
def duplicate_record(table_id: int, record_id: int, db: Session = Depends(get_db),
                     access: TableAccess = Depends(require_table("create"))):
    """创建副本：复制记录的业务字段值（自动编号/公式等由服务端重新生成）。"""
    from ..services.field_registry import READONLY_TYPES
    rec = db.get(Record, record_id)
    if not rec or rec.table_id != table_id:
        raise HTTPException(404, "记录不存在")
    fields = get_meta_fields(db, table_id)
    data = {f.field_name: (rec.data or {}).get(f.field_name)
            for f in fields if (f.field_type or "") not in READONLY_TYPES}
    data = {k: v for k, v in data.items() if v is not None}
    new_rec = json_store.create_record(db, access.table, fields, data,
                                       user=access.ctx.user.username, owner_id=access.ctx.user.id,
                                       parent_id=rec.parent_id)
    return {"record": new_rec}


# ---------- 查找替换（设计文档 §7.5） ----------

@router.post("/tables/{table_id}/search-replace")
def search_replace(table_id: int, payload: dict, db: Session = Depends(get_db),
                   access: TableAccess = Depends(require_table("edit"))):
    """查找：返回匹配单元格坐标；replace=true 时执行替换（全部或指定记录）。仅文本类字段。"""
    find = str(payload.get("find") or "")
    replace = str(payload.get("replace") or "")
    do_replace = bool(payload.get("replace_all"))
    if not find:
        raise HTTPException(400, "查找内容不能为空")
    fields = get_meta_fields(db, table_id)
    text_types = {"text", "url", "phone", "email", None, ""}
    text_fields = [f for f in fields
                   if (f.field_type in text_types) and f.data_type in ("varchar", "text")]
    recs = json_store.all_dicts(db, table_id, fields, normalized=False)
    matches = []
    for r in recs:
        for f in text_fields:
            v = r.get(f.field_name)
            if isinstance(v, str) and find.casefold() in v.casefold():
                matches.append({"recordId": r["id"], "field": f.field_name,
                                "fieldLabel": f.label, "value": v})
    if do_replace and matches:
        by_rec: dict[int, dict] = {}
        for m in matches:
            by_rec.setdefault(m["recordId"], {})[m["field"]] = m["value"].replace(find, replace)
        for rid, data in by_rec.items():
            json_store.update_record(db, access.table, fields, rid, data,
                                     user=access.ctx.user.username, editor_id=access.ctx.user.id)
    return {"matches": matches, "replaced": len({m['recordId'] for m in matches}) if do_replace else 0}


# ---------- 字段级操作：创建副本（设计文档 §6.2） ----------

@router.post("/tables/{table_id}/fields/{field_name}/duplicate")
def duplicate_field(table_id: int, field_name: str, db: Session = Depends(get_db),
                    access: TableAccess = Depends(require_table("edit"))):
    """创建字段副本：复制字段定义（名称加「副本」）+ 存量数据值（读时计算字段只复制定义）。"""
    from ..services.field_registry import COMPUTED_TYPES, SYSTEM_TYPES, gen_field_name
    from ..services.meta_service import alter_business_table
    fields = get_meta_fields(db, table_id)
    src = next((f for f in fields if f.field_name == field_name), None)
    if not src:
        raise HTTPException(404, "字段不存在")
    new_name = gen_field_name({f.field_name for f in fields})
    alter_business_table(db, access.table, [{"op": "add_field", "field": {
        "field_name": new_name, "label": f"{src.label} 副本", "data_type": src.data_type,
        "widget": src.widget, "options": dict(src.options or {}), "field_type": src.field_type,
        "nullable": True,
    }}])
    if (src.field_type or "") not in COMPUTED_TYPES | SYSTEM_TYPES:
        for rec in db.query(Record).filter_by(table_id=table_id).all():
            d = dict(rec.data or {})
            if src.field_name in d:
                d[new_name] = d[src.field_name]
                rec.data = d
        db.commit()
    return {"field_name": new_name, "label": f"{src.label} 副本"}
