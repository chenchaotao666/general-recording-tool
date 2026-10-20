"""JSON 单表存储：所有 json 模式业务表的数据都存 records 表，筛选/排序在 Python 侧（pyquery）。

函数与 dyn_engine 公共函数同名同签名；dyn_engine 按 meta_tables.storage_mode 分流到这里。
数据量约定：单表 ≤1 万行（全量加载内存求值），主力大表请用 physical 模式。
"""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..models import MetaField, MetaTable, Record
from . import dyn_engine
from .pyquery import match_filters, normalize_record, sort_records


def serialize_data(cleaned: dict) -> dict:
    """coerce 后的类型化值 → JSON 可存标量（ISO 字符串/数字/布尔）。"""
    return {k: dyn_engine.serialize_value(v) for k, v in cleaned.items()}


def _row_to_client(rec: Record, fields_by_name: dict) -> dict:
    """records 行 → 前端 dict（data 展开 + 未赋值字段补 None + id/created_at/updated_at，值序列化）。
    形状与物理表 row_to_dict 对齐：物理表 NULL 列也出现在结果里。
    智能表系统字段（createdBy/createdTime 等）：从记录系统列注入（sys_key 映射）。"""
    from .field_registry import FIELD_TYPES
    out = {name: None for name in fields_by_name}
    out.update(rec.data or {})
    out["id"] = rec.id
    out["__sort_index"] = rec.sort_index if rec.sort_index is not None else rec.id
    out["tenant_id"] = rec.tenant_id
    out["owner_id"] = rec.owner_id
    out["parent_id"] = rec.parent_id
    out["updated_by"] = rec.updated_by
    out["updated_by_type"] = rec.updated_by_type or "user"
    out["created_at"] = dyn_engine.serialize_value(rec.created_at)
    out["updated_at"] = dyn_engine.serialize_value(rec.updated_at)
    for name, f in fields_by_name.items():
        sys_key = FIELD_TYPES.get(getattr(f, "field_type", None) or "", {}).get("sys_key")
        if sys_key:
            out[name] = actor_value(out, sys_key)
    return {k: dyn_engine.serialize_value(v) for k, v in out.items()}


def actor_value(rec: dict, sys_key: str):
    """系统字段取值：最后编辑人遇非人主体（AI/自动化）时返回占位标识，前端渲染为「AI 生成」/「自动化」。"""
    if sys_key == "updated_by" and rec.get("updated_by_type") in ("ai", "automation"):
        return f"__{rec['updated_by_type']}__"
    return rec.get(sys_key)


def all_dicts(db: Session, table_id: int, fields: list[MetaField], normalized: bool = False) -> list[dict]:
    """全量记录。normalized=True 时值按字段类型还原（供引擎求值）；否则为客户端序列化形态。"""
    fields_by_name = {f.field_name: f for f in fields}
    rows = db.execute(
        select(Record).where(Record.table_id == table_id)
        .order_by(func.coalesce(Record.sort_index, Record.id).desc(), Record.id.desc())
    ).scalars().all()
    if not normalized:
        return [_row_to_client(r, fields_by_name) for r in rows]
    out = []
    for r in rows:
        rec = {f.field_name: None for f in fields}  # 未赋值字段补 None，对齐物理表 NULL 列形状
        rec.update(r.data or {})
        rec["id"] = r.id
        rec["__sort_index"] = r.sort_index if r.sort_index is not None else r.id
        rec["owner_id"] = r.owner_id      # P1 数据范围过滤用（引擎/报表 json 链路）
        rec["tenant_id"] = r.tenant_id
        rec["parent_id"] = r.parent_id    # 智能表树形子记录
        rec["updated_by"] = r.updated_by  # 智能表系统字段（最后编辑人）
        rec["updated_by_type"] = r.updated_by_type or "user"
        rec["created_at"] = r.created_at
        rec["updated_at"] = r.updated_at
        out.append(normalize_record(rec, fields_by_name))
    return out


def normalized_one(db: Session, table_id: int, record_id: int, fields: list[MetaField]) -> dict:
    """单条记录的 normalized 形态（与 all_dicts(normalized=True) 同形；权限行条件/自动化条件求值用）。"""
    rec = db.get(Record, record_id)
    if not rec or rec.table_id != table_id:
        raise HTTPException(404, "记录不存在")
    out = {f.field_name: None for f in fields}
    out.update(rec.data or {})
    out.update({"id": rec.id, "owner_id": rec.owner_id, "tenant_id": rec.tenant_id,
                "parent_id": rec.parent_id, "updated_by": rec.updated_by,
                "updated_by_type": rec.updated_by_type or "user",
                "created_at": rec.created_at, "updated_at": rec.updated_at})
    return normalize_record(out, {f.field_name: f for f in fields})


def recompute_formulas(db: Session, mt: MetaTable, fields: list[MetaField]) -> int:
    """公式新增/修改后全表重算（§9.3：保存公式后全表计算）。只改公式结果，不动「最后编辑人/时间」。"""
    from sqlalchemy import update
    formula_names = [f.field_name for f in fields if isinstance((f.options or {}).get("formula"), str)]
    if not formula_names:
        return 0
    from . import formula_tables
    fbn = {f.field_name: f for f in fields}
    changed = 0
    with formula_tables.scope(db, mt.tenant_id):
        for rec in db.execute(select(Record).where(Record.table_id == mt.id)).scalars().all():
            computed: dict = {}
            dyn_engine.apply_computed(fields, computed, base=_row_to_client(rec, fbn))
            new_vals = {k: dyn_engine.serialize_value(computed.get(k)) for k in formula_names}
            data = dict(rec.data or {})
            if all(data.get(k) == v for k, v in new_vals.items()):
                continue
            data.update(new_vals)
            db.execute(update(Record).where(Record.id == rec.id)
                       .values(data=data, updated_at=Record.updated_at))   # 显式自赋值：屏蔽 onupdate
            changed += 1
    db.commit()
    return changed


def _post_insert_formulas(db: Session, mt: MetaTable, fields: list[MetaField], rec: Record, commit: bool = True) -> None:
    """RECORD_ID() 在插入前没有 id：含该函数的公式在插入后补算一次。"""
    from . import formula_tables
    names = [f.field_name for f in fields
             if "RECORD_ID" in str((f.options or {}).get("formula") or "").upper()]
    if not names:
        return
    computed: dict = {}
    with formula_tables.scope(db, mt.tenant_id):
        dyn_engine.apply_computed(fields, computed, base=_row_to_client(rec, {f.field_name: f for f in fields}))
    data = dict(rec.data or {})
    data.update({k: dyn_engine.serialize_value(computed.get(k)) for k in names})
    rec.data = data
    db.commit() if commit else db.flush()
    db.refresh(rec)


def count(db: Session, table_id: int) -> int:
    return db.execute(
        select(func.count()).select_from(Record).where(Record.table_id == table_id)
    ).scalar() or 0


def list_records(db: Session, mt: MetaTable, fields: list[MetaField], page: int, page_size: int,
                 filters: list[dict] | None, sort_by: str | None, sort_order: str | None,
                 page_cap: int | None = None, kw: str | None = None) -> dict:
    fields_by_name = {f.field_name: f for f in fields}
    recs = all_dicts(db, mt.id, fields, normalized=True)
    if filters:
        # 元素是单条规则 → 顶层 AND；{"logic", "rules"} 形态 → 按组的 AND/OR 组合
        def _hit(r, f):
            if isinstance(f, dict) and isinstance(f.get("rules"), list):
                return match_filters(r, fields_by_name, {"logic": f.get("logic"), "rules": f["rules"]})
            return match_filters(r, fields_by_name, {"logic": "AND", "rules": [f]})
        recs = [r for r in recs if all(_hit(r, f) for f in filters)]
    if kw:
        # 全局关键字：跨所有 varchar/text 字段 OR 模糊匹配（不区分大小写）
        text_fields = [f.field_name for f in fields if f.data_type in ("varchar", "text")]
        needle = kw.lower()
        if text_fields and needle:
            recs = [r for r in recs
                    if any(needle in str(r.get(fn) or "").lower() for fn in text_fields)]
    total = len(recs)
    recs = sort_records(recs, sort_by, sort_order, fields_by_name)
    page = max(page, 1)
    page_size = min(max(page_size, 1), page_cap or dyn_engine.MAX_PAGE_SIZE)
    # 数字列合计：口径 = 全部筛选结果（非当前页）
    num_fields = [f for f in fields if f.data_type in ("int", "decimal")]
    summary = {}
    for f in num_fields:
        nums = [r.get(f.field_name) for r in recs]
        nums = [v for v in nums if isinstance(v, (int, float)) and not isinstance(v, bool)]
        summary[f.field_name] = sum(nums) if nums else None
    items = [
        {k: dyn_engine.serialize_value(v) for k, v in r.items()}
        for r in recs[(page - 1) * page_size: page * page_size]
    ]
    return {"total": total, "summary": summary, "items": items}


def get_record(db: Session, table_id: int, record_id: int, fields: list[MetaField] | None = None) -> dict:
    rec = db.execute(
        select(Record).where(Record.table_id == table_id, Record.id == record_id)
    ).scalars().first()
    if not rec:
        raise HTTPException(404, "记录不存在")
    return _row_to_client(rec, {f.field_name: f for f in (fields or [])})


def _strip_readonly(fields: list[MetaField], data: dict) -> dict:
    """智能表只读/系统/读时计算字段（公式/查找引用/创建人等）不接收提交值（设计文档 §3.3 系统字段纪律）。"""
    from .field_registry import READONLY_TYPES
    # AI 字段可在网格里手动修正（如单选/多选改标签，参照企微）；表单等入口仍按只读处理（READONLY_TYPES）
    blocked = {f.field_name for f in fields if (f.field_type or "") in READONLY_TYPES and f.field_type != "ai"}
    return {k: v for k, v in (data or {}).items() if k not in blocked}


def create_record(db: Session, mt: MetaTable, fields: list[MetaField], data: dict,
                  user: str | None = None, owner_id: int | None = None,
                  parent_id: int | None = None, actor_type: str = "user",
                  anonymous: bool = False, commit: bool = True) -> dict:
    """anonymous=True：公开表单的匿名外部填写者（创建人为空）；actor_type：user / ai / automation。"""
    cleaned, errors = dyn_engine.coerce_payload(fields, _strip_readonly(fields, data))
    if errors:
        raise HTTPException(422, detail=errors)
    for f in fields:
        if cleaned.get(f.field_name) is None and f.default_value is not None:
            from .typemap import coerce_value
            ok, cv, _ = coerce_value(f.default_value, f.data_type, True)
            if ok:
                cleaned[f.field_name] = cv
    dyn_engine.apply_serials(db, mt.id, fields, cleaned)
    from . import formula_tables
    with formula_tables.scope(db, mt.tenant_id):
        dyn_engine.apply_computed(fields, cleaned)
    now = datetime.now()
    owner = None if anonymous else (owner_id if owner_id is not None else mt.owner_id)
    # 与插入接口共用表锁，避免并发写入覆盖手动顺序。
    db.execute(select(MetaTable.id).where(MetaTable.id == mt.id).with_for_update())
    rank = db.scalar(select(func.max(func.coalesce(Record.sort_index, Record.id))).where(Record.table_id == mt.id)) or 0
    rec = Record(table_id=mt.id, tenant_id=mt.tenant_id,
                 sort_index=rank + 1,
                 owner_id=owner, parent_id=parent_id, updated_by=owner, updated_by_type=actor_type,
                 data=serialize_data(cleaned), created_at=now, updated_at=now)
    db.add(rec)
    db.commit() if commit else db.flush()
    db.refresh(rec)
    _post_insert_formulas(db, mt, fields, rec, commit=commit)
    record = _row_to_client(rec, {f.field_name: f for f in fields})
    dyn_engine.log_audit(db, "create", mt.id, record["id"], after=record, user=user,
                         tenant_id=mt.tenant_id)
    db.commit() if commit else db.flush()
    return record


def insert_records(db: Session, mt: MetaTable, fields: list[MetaField], anchor: Record,
                   direction: str, count: int, data: dict, user: str, owner_id: int) -> list[dict]:
    """批量插入与顺序调整在同一事务完成，失败不留下半批记录。"""
    try:
        db.execute(select(MetaTable.id).where(MetaTable.id == mt.id).with_for_update())
        ids = list(db.scalars(select(Record.id).where(Record.table_id == mt.id)
                             .order_by(func.coalesce(Record.sort_index, Record.id).desc(), Record.id.desc())))
        offset = ids.index(anchor.id) + (1 if direction == "down" else 0)
        records = [create_record(db, mt, fields, data, user=user, owner_id=owner_id,
                                 parent_id=anchor.parent_id, commit=False) for _ in range(count)]
        ids[offset:offset] = [r["id"] for r in records]
        # 整数重排不累积分数精度误差，不改变原记录的编辑时间。
        for index, rid in enumerate(ids):
            db.execute(update(Record).where(Record.id == rid)
                       .values(sort_index=len(ids) - index, updated_at=Record.updated_at))
        db.commit()
        return records
    except Exception:
        db.rollback()
        raise


def update_record(db: Session, mt: MetaTable, fields: list[MetaField], record_id: int, data: dict,
                  user: str | None = None, editor_id: int | None = None,
                  actor_type: str = "user", allow_fields: set[str] | None = None) -> dict:
    """allow_fields：额外放行的只读字段（AI 字段由 AI 服务回写，普通提交一律拦截）。"""
    rec = db.execute(
        select(Record).where(Record.table_id == mt.id, Record.id == record_id)
    ).scalars().first()
    if not rec:
        raise HTTPException(404, "记录不存在")
    fbn = {f.field_name: f for f in fields}
    before = _row_to_client(rec, fbn)
    payload = _strip_readonly(fields, data)
    for k in allow_fields or ():
        if k in (data or {}):
            payload[k] = data[k]
    cleaned, errors = dyn_engine.coerce_payload(fields, payload, partial=True)
    if errors:
        raise HTTPException(422, detail=errors)
    dyn_engine.strip_serial_fields(fields, cleaned)
    from . import formula_tables
    with formula_tables.scope(db, mt.tenant_id):
        dyn_engine.apply_computed(fields, cleaned, base=before)
    merged = dict(rec.data or {})
    merged.update(serialize_data(cleaned))
    rec.data = merged
    rec.updated_at = datetime.now()
    if editor_id is not None:
        rec.updated_by = editor_id
    rec.updated_by_type = actor_type
    db.commit()
    after = _row_to_client(rec, fbn)
    dyn_engine.log_audit(db, "update", mt.id, record_id, before=before, after=after, user=user,
                         tenant_id=mt.tenant_id)
    db.commit()
    return after


def delete_record(db: Session, table_id: int, record_id: int, fields: list[MetaField] | None = None, user: str | None = None) -> None:
    rec = db.execute(
        select(Record).where(Record.table_id == table_id, Record.id == record_id)
    ).scalars().first()
    if not rec:
        raise HTTPException(404, "记录不存在")
    before = _row_to_client(rec, {f.field_name: f for f in (fields or [])})
    tenant_id = rec.tenant_id
    db.delete(rec)
    db.commit()
    dyn_engine.log_audit(db, "delete", table_id, record_id, before=before, user=user,
                         tenant_id=tenant_id)
    db.commit()


def bulk_insert(db: Session, table_id: int, items: list[dict]) -> None:
    """Excel 导入用。items 已 coerce（含 created_at/updated_at），批量插入。
    引擎层闸：配额按批次校验 + 用量累计（tenant/owner 列从 meta 自取）。"""
    if not items:
        return
    from . import entitlement
    mt = db.get(MetaTable, table_id)
    entitlement.check_quota(db, mt.tenant_id, "max_rows", delta=len(items))
    now = datetime.now()
    rows = [
        Record(table_id=table_id, tenant_id=mt.tenant_id, owner_id=mt.owner_id,
               data=serialize_data(item), created_at=item.get("created_at") or now,
               updated_at=item.get("updated_at") or now)
        for item in items
    ]
    db.add_all(rows)
    entitlement.bump_usage(db, mt.tenant_id, "row_count", len(rows))
    db.commit()
