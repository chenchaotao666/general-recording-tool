"""智能表网格与记录操作（设计文档 §16.3、§7）：

grid 查询处理链：视图+个人覆盖合并 → DSL 适配 → 筛选 → 分组/多级排序 → 树形组装 → 聚合分页；
lookup 字段读时计算；系统字段（创建人/时间等）从记录系统列注入。
记录写操作包装 json_store（parent_id/updated_by/只读字段拦截在 json_store 层）。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import MetaField, MetaTable, MetaView, MetaViewPref, Record
from ..services import dyn_engine, json_store, lookup_service, perm_service, smart_events, view_config
from ..services.field_registry import FIELD_TYPES
from ..services.meta_service import get_meta_fields
from ..services.pyquery import match_filters, sort_records_multi
from ..services.smart_cond import match_conditions

_NO_VALUE_OPS = {"isEmpty", "isNotEmpty"}


def _complete(cond: dict) -> bool:
    """未填值的条件（如固定到工具栏、尚未选值的筛选）不生效，与前端「条件不完整不计数」一致。"""
    if cond.get("operator") in _NO_VALUE_OPS:
        return True
    v = cond.get("value")
    if isinstance(v, dict) and v.get("mode") == "exact":
        return bool(v.get("date"))   # 日期模式「具体日期」未选日期：不完整
    return not (v is None or v == "" or (isinstance(v, list) and not v))
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
            r[f.field_name] = json_store.actor_value(r, SYSTEM_FIELD_KEYS[f.field_type])


def _normalized_one(db: Session, table_id: int, record_id: int, fields: list[MetaField]) -> dict:
    return json_store.normalized_one(db, table_id, record_id, fields)


def _effective(db: Session, access: TableAccess) -> perm_service.Effective:
    eff = perm_service.effective_for_access(db, access)
    if eff.level == "NONE":
        raise HTTPException(404, "数据表不存在")
    return eff


def _require_row_editable(eff, rec: dict, fields) -> None:
    if not eff.row_editable(rec, fields):
        raise HTTPException(403, "没有编辑这条记录的权限")


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
    all_fields = get_meta_fields(db, table_id)
    eff = _effective(db, access)
    rights = eff.field_rights_map(all_fields)
    # 列投影：无查看权的字段接口层面不返回（§13.6 读路径）
    fields = [f for f in all_fields if rights[f.field_name]["view"]]
    hidden = {f.field_name for f in all_fields} - {f.field_name for f in fields}
    fields_by_name = {f.field_name: f for f in fields}

    flt = effective.get("filters") or {}
    view_conds = [c for c in flt.get("conditions") or []
                  if c.get("fieldId") and c["fieldId"] not in hidden and _complete(c)]
    view_config.conditions_to_rules({"conditions": view_conds})   # 仅做运算符合法性校验
    recs = json_store.all_dicts(db, table_id, all_fields, normalized=True)
    if not eff.managed:
        recs = [r for r in recs if eff.row_viewable(r, all_fields)]   # 行级查看范围
    if view_conds:
        match = "any" if flt.get("conjunction") == "or" else "all"
        recs = [r for r in recs if match_conditions(r, all_fields, view_conds, match, user.id)]
    aggs = view_config.compute_aggregations(
        recs, {k: v for k, v in (effective.get("aggregations") or {}).items() if k not in hidden}, fields)
    total = len(recs)
    row_scoped = (not eff.managed) and eff.can_edit
    editable_ids = {r["id"] for r in recs if eff.row_editable(r, all_fields)} if row_scoped else None

    groups = [g for g in (effective.get("groups") or []) if g.get("fieldId") not in hidden]
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
    for r in data_rows:
        for fn in hidden:
            r.pop(fn, None)
        if editable_ids is not None and r.get("id") not in editable_ids:
            r["__readonly"] = True   # 行级编辑范围外：只可查看
    from ..services import ai_field_service
    ai_field_service.attach_status(db, table_id, fields, data_rows)

    return {
        "items": rows, "total": total, "aggregations": aggs, "grouped": bool(groups),
        "view": {"id": view.id, "name": view.name, "type": view.type, "config": effective,
                 "is_default": bool(view.is_default)} if view else None,
        "fields": [
            {"id": f.id, "field_name": f.field_name, "label": f.label, "data_type": f.data_type,
             "field_type": f.field_type, "options": f.options or {}, "sort_order": f.sort_order}
            for f in fields
        ],
        "my_perms": {**access.my_perms(),
                     "can_create": eff.can_add_record,
                     "can_edit": access.can_edit and perm_service.LEVEL_RANK[eff.level] >= 2,
                     "can_delete": eff.can_delete_record},
        "content_perm": eff.to_client(fields),
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

    eff = _effective(db, access)
    if not eff.field_rights_map(fields)[field_name]["view"]:
        raise HTTPException(404, f"字段不存在：{field_name}")
    flt = effective.get("filters") or {}
    view_conds = [c for c in flt.get("conditions") or [] if c.get("fieldId") and _complete(c)]
    recs = json_store.all_dicts(db, table_id, fields, normalized=True)
    if not eff.managed:
        recs = [r for r in recs if eff.row_viewable(r, fields)]
    if view_conds:
        match = "any" if flt.get("conjunction") == "or" else "all"
        recs = [r for r in recs if match_conditions(r, fields, view_conds, match, user.id)]
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
    eff = _effective(db, access)
    if not eff.can_add_record:
        raise HTTPException(403, "没有添加记录的权限")
    rights = eff.field_rights_map(fields)
    # 新建用 firstSubmit ∪ edit 白名单（§13.6 写路径）；无权字段静默丢弃（分组预设值等）
    data = {k: v for k, v in (payload.get("data") or {}).items()
            if k in rights and (rights[k]["firstSubmit"] or rights[k]["edit"])}
    rec = json_store.create_record(db, access.table, fields, data,
                                   user=access.ctx.user.username, owner_id=access.ctx.user.id,
                                   parent_id=parent_id)
    smart_events.record_created(db, access.table, rec, actor_id=access.ctx.user.id)
    return {"record": rec}


@router.patch("/tables/{table_id}/records/{record_id}")
def update_record(table_id: int, record_id: int, payload: dict, db: Session = Depends(get_db),
                  access: TableAccess = Depends(require_table("edit"))):
    fields = get_meta_fields(db, table_id)
    eff = _effective(db, access)
    if not eff.managed:
        perm_service.require_level(eff, "EDIT", "没有编辑记录的权限")
        _require_row_editable(eff, _normalized_one(db, table_id, record_id, fields), fields)
        rights = eff.field_rights_map(fields)
        locked = [k for k in (payload.get("data") or {}) if k in rights and not rights[k]["edit"]]
        if locked:
            labels = {f.field_name: f.label for f in fields}
            raise HTTPException(403, f"没有编辑字段「{'、'.join(labels.get(k, k) for k in locked)}」的权限")
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
        before = json_store.get_record(db, table_id, record_id, fields)
        rec = json_store.update_record(db, access.table, fields, record_id, data,
                                       user=access.ctx.user.username, editor_id=access.ctx.user.id)
        smart_events.record_updated(db, access.table, before, rec, list(data), actor_id=access.ctx.user.id)
        return {"record": rec}
    rec = db.get(Record, record_id)
    fbn = {f.field_name: f for f in fields}
    return {"record": json_store._row_to_client(rec, fbn)}


@router.delete("/tables/{table_id}/records/{record_id}")
def delete_record(table_id: int, record_id: int, db: Session = Depends(get_db),
                  access: TableAccess = Depends(require_table("delete"))):
    """删除记录：子记录上提一级（孤子上提策略，设计文档 §7.4）。"""
    eff = _effective(db, access)
    if not eff.managed:
        if not eff.can_delete_record:
            raise HTTPException(403, "没有删除记录的权限")
        fs = get_meta_fields(db, table_id)
        _require_row_editable(eff, _normalized_one(db, table_id, record_id, fs), fs)
    children = db.query(Record).filter_by(table_id=table_id, parent_id=record_id).all()
    rec = db.get(Record, record_id)
    for c in children:
        c.parent_id = rec.parent_id if rec else None
    fields = get_meta_fields(db, table_id)
    json_store.delete_record(db, table_id, record_id, fields, user=access.ctx.user.username)
    smart_events.table_changed(db, access.table)
    return {"ok": True, "orphans_lifted": len(children)}


@router.post("/tables/{table_id}/records:batch-delete")
def batch_delete(table_id: int, payload: dict, db: Session = Depends(get_db),
                 access: TableAccess = Depends(require_table("delete"))):
    """批量删除记录（撤销栈靠前端快照重建）。"""
    ids = payload.get("ids") or []
    if not isinstance(ids, list) or not ids or len(ids) > 500:
        raise HTTPException(400, "ids 必须是非空数组（最多 500 条）")
    fields = get_meta_fields(db, table_id)
    eff = _effective(db, access)
    if not eff.can_delete_record:
        raise HTTPException(403, "没有删除记录的权限")
    deleted = 0
    for rid in ids:
        try:
            rec = db.get(Record, int(rid))
            if not rec or rec.table_id != table_id:
                continue
            if not eff.managed and not eff.row_editable(_normalized_one(db, table_id, int(rid), fields), fields):
                continue   # 行级编辑范围外的记录跳过
            for c in db.query(Record).filter_by(table_id=table_id, parent_id=int(rid)).all():
                c.parent_id = rec.parent_id
            json_store.delete_record(db, table_id, int(rid), fields, user=access.ctx.user.username)
            deleted += 1
        except HTTPException:
            continue
    db.commit()
    if deleted:
        smart_events.table_changed(db, access.table)
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
    eff = _effective(db, access)
    if not eff.can_add_record:
        raise HTTPException(403, "没有添加记录的权限")
    rights = eff.field_rights_map(fields)
    data = {f.field_name: (rec.data or {}).get(f.field_name)
            for f in fields if (f.field_type or "") not in READONLY_TYPES
            and (rights[f.field_name]["firstSubmit"] or rights[f.field_name]["edit"])}
    data = {k: v for k, v in data.items() if v is not None}
    new_rec = json_store.create_record(db, access.table, fields, data,
                                       user=access.ctx.user.username, owner_id=access.ctx.user.id,
                                       parent_id=rec.parent_id)
    smart_events.record_created(db, access.table, new_rec, actor_id=access.ctx.user.id)
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
    eff = _effective(db, access)
    rights = eff.field_rights_map(fields)
    text_types = {"text", "url", "phone", "email", None, ""}
    text_fields = [f for f in fields
                   if (f.field_type in text_types) and f.data_type in ("varchar", "text")
                   and rights[f.field_name]["view"] and (not do_replace or rights[f.field_name]["edit"])]
    recs = json_store.all_dicts(db, table_id, fields, normalized=False)
    if not eff.managed:
        visible = {r["id"] for r in json_store.all_dicts(db, table_id, fields, normalized=True)
                   if (eff.row_editable(r, fields) if do_replace else eff.row_viewable(r, fields))}
        recs = [r for r in recs if r["id"] in visible]
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
            before = json_store.get_record(db, table_id, rid, fields)
            after = json_store.update_record(db, access.table, fields, rid, data,
                                             user=access.ctx.user.username, editor_id=access.ctx.user.id)
            smart_events.record_updated(db, access.table, before, after, list(data), actor_id=access.ctx.user.id)
    return {"matches": matches, "replaced": len({m['recordId'] for m in matches}) if do_replace else 0}


# ---------- 字段级操作：创建副本（设计文档 §6.2） ----------

@router.post("/tables/{table_id}/fields/{field_name}/duplicate")
def duplicate_field(table_id: int, field_name: str, db: Session = Depends(get_db),
                    access: TableAccess = Depends(require_table("edit"))):
    """创建字段副本：复制字段定义（名称加「副本」）+ 存量数据值（读时计算字段只复制定义）。"""
    from ..services.field_registry import COMPUTED_TYPES, SYSTEM_TYPES, gen_field_name
    from ..services.meta_service import alter_business_table
    if not _effective(db, access).schema_edit:
        raise HTTPException(403, "没有修改字段设置的权限")
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


# ---------- 公式编辑器（设计文档 §9.1）：函数目录 + 第 1 行试算 ----------

@router.get("/formula/functions")
def formula_functions():
    from ..services.formula_funcs import CATEGORIES, catalog, operators
    return {"categories": CATEGORIES, "functions": catalog(), "operators": operators()}


def _formula_cycle(fields: list[MetaField], self_name: str | None, refs: set[str]) -> list[str] | None:
    """检测「本公式 → 引用的公式字段 → … → 本公式」的循环，返回环上的字段名链。"""
    from ..services import expr
    if not self_name:
        return None
    graph = {}
    for f in fields:
        src = (f.options or {}).get("formula")
        if isinstance(src, str) and f.field_name != self_name:
            try:
                graph[f.field_name] = expr.referenced_fields(expr.parse(src))
            except expr.ExprError:
                graph[f.field_name] = set()
    graph[self_name] = refs
    path, seen = [], set()

    def dfs(n):
        if n == self_name and path:
            return True
        if n in seen:
            return False
        seen.add(n)
        path.append(n)
        for m in graph.get(n, ()):
            if m == self_name or m in graph:
                if dfs(m):
                    return True
        path.pop()
        return False
    return path + [self_name] if dfs(self_name) else None


@router.post("/tables/{table_id}/formula/preview")
def formula_preview(table_id: int, payload: dict, db: Session = Depends(get_db),
                    access: TableAccess = Depends(require_table("view"))):
    """用真实数据试算公式（严格模式，错误给出人话诊断）。{formula, field_name?(编辑中的公式字段，禁止自引用), record_id?, row_no?}
    同时返回试算行各字段的展示值 row_values（编辑器字段列表旁显示「第 1 行」取值）。公式为空时只返回 row_values。"""
    from datetime import date

    from ..services import expr
    from ..services.dyn_engine import _numify, formula_context
    from ..services.formula_funcs import FormulaError, to_text
    from ..services.smart_format import display
    fields = get_meta_fields(db, table_id)
    labels = {f.field_name: f.label for f in fields}
    self_name = payload.get("field_name")
    src = str(payload.get("formula") or "").strip()

    # 试算行：前端传当前视图首行 record_id + row_no=1 时按视图口径；否则取 id 最小的记录
    q = db.query(Record).filter_by(table_id=table_id).order_by(Record.id)
    rid = payload.get("record_id")
    rec = db.get(Record, int(rid)) if rid else q.first()
    if rec is not None and rec.table_id != table_id:
        rec = None
    base = {"empty": rec is None}
    row = None
    if rec is not None:
        base["row_no"] = int(payload["row_no"]) if payload.get("row_no") and rid else q.filter(Record.id <= rec.id).count()
        base["record_id"] = rec.id
        row = json_store.get_record(db, table_id, rec.id, fields)
        _inject_system_and_lookup(db, fields, [row])
        cache: dict = {}
        base["row_values"] = {f.field_name: display(db, f, row.get(f.field_name), cache)[:80]
                              for f in fields if f.field_name != self_name}
    if not src:
        return {"ok": True, "blank": True, **base}

    allow = {f.field_name for f in fields} - ({self_name} if self_name else set())
    try:
        node = expr.parse(src, allow)
    except expr.ExprError as e:
        msg = str(e)
        if self_name and self_name in msg:
            msg = "公式不能引用字段自身"
        for fn, lb in labels.items():
            msg = msg.replace(f"：{fn}", f"：{lb}")
        return {"ok": False, **base, "error": {"title": "公式错误", "message": msg}, "blocking": True}
    refs = expr.referenced_fields(node)
    cyc = _formula_cycle(fields, self_name, refs)
    if cyc:
        return {"ok": False, **base, "blocking": True, "error": {
            "title": "循环引用", "message": " → ".join(labels.get(x, x) for x in cyc) + "，公式之间不能互相引用成环。"}}
    referenced = [labels.get(r, r) for r in refs]
    for t in expr.referenced_tables(node):
        ref_mt = db.get(MetaTable, t)
        if not ref_mt or ref_mt.tenant_id != access.table.tenant_id:
            return {"ok": False, **base, "blocking": True,
                    "error": {"title": "公式错误", "message": "引用的表不存在或无权访问"}}
    if row is None:
        return {"ok": True, **base, "referenced": referenced}
    from ..services import formula_tables
    try:
        with formula_tables.scope(db, access.table.tenant_id):
            value = expr.evaluate(node, _numify(formula_context(fields, row)), strict=True)
    except FormulaError as e:
        return {"ok": False, **base, "referenced": referenced, "error": {"title": e.title, "message": e.message}}
    kind = ("boolean" if isinstance(value, bool) else "number" if isinstance(value, (int, float)) else
            "date" if isinstance(value, date) else "text")
    return {"ok": True, **base, "value": dyn_engine.serialize_value(value),
            "display": "TRUE" if value is True else "FALSE" if value is False else to_text(value),
            "type": kind, "referenced": referenced}
