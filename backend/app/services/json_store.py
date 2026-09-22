"""JSON 单表存储：所有 json 模式业务表的数据都存 records 表，筛选/排序在 Python 侧（pyquery）。

函数与 dyn_engine 公共函数同名同签名；dyn_engine 按 meta_tables.storage_mode 分流到这里。
数据量约定：单表 ≤1 万行（全量加载内存求值），主力大表请用 physical 模式。
"""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import MetaField, MetaTable, Record
from . import dyn_engine
from .pyquery import match_filters, normalize_record, sort_records


def serialize_data(cleaned: dict) -> dict:
    """coerce 后的类型化值 → JSON 可存标量（ISO 字符串/数字/布尔）。"""
    return {k: dyn_engine.serialize_value(v) for k, v in cleaned.items()}


def _row_to_client(rec: Record, fields_by_name: dict) -> dict:
    """records 行 → 前端 dict（data 展开 + 未赋值字段补 None + id/created_at/updated_at，值序列化）。
    形状与物理表 row_to_dict 对齐：物理表 NULL 列也出现在结果里。"""
    out = {name: None for name in fields_by_name}
    out.update(rec.data or {})
    out["id"] = rec.id
    out["created_at"] = dyn_engine.serialize_value(rec.created_at)
    out["updated_at"] = dyn_engine.serialize_value(rec.updated_at)
    return {k: dyn_engine.serialize_value(v) for k, v in out.items()}


def all_dicts(db: Session, table_id: int, fields: list[MetaField], normalized: bool = False) -> list[dict]:
    """全量记录。normalized=True 时值按字段类型还原（供引擎求值）；否则为客户端序列化形态。"""
    fields_by_name = {f.field_name: f for f in fields}
    rows = db.execute(
        select(Record).where(Record.table_id == table_id).order_by(Record.id)
    ).scalars().all()
    if not normalized:
        return [_row_to_client(r, fields_by_name) for r in rows]
    out = []
    for r in rows:
        rec = {f.field_name: None for f in fields}  # 未赋值字段补 None，对齐物理表 NULL 列形状
        rec.update(r.data or {})
        rec["id"] = r.id
        rec["created_at"] = r.created_at
        rec["updated_at"] = r.updated_at
        out.append(normalize_record(rec, fields_by_name))
    return out


def count(db: Session, table_id: int) -> int:
    return db.execute(
        select(func.count()).select_from(Record).where(Record.table_id == table_id)
    ).scalar() or 0


def list_records(db: Session, mt: MetaTable, fields: list[MetaField], page: int, page_size: int,
                 filters: list[dict] | None, sort_by: str | None, sort_order: str | None) -> dict:
    fields_by_name = {f.field_name: f for f in fields}
    recs = all_dicts(db, mt.id, fields, normalized=True)
    if filters:
        # filters 是顶层 AND（与 dyn list_records 一致；单个 filter 内的 logic 由任务/报表层组合）
        recs = [r for r in recs if all(match_filters(r, fields_by_name, {"logic": "AND", "rules": [f]}) for f in filters)]
    total = len(recs)
    recs = sort_records(recs, sort_by, sort_order, fields_by_name)
    page = max(page, 1)
    page_size = min(max(page_size, 1), dyn_engine.MAX_PAGE_SIZE)
    items = [
        {k: dyn_engine.serialize_value(v) for k, v in r.items()}
        for r in recs[(page - 1) * page_size: page * page_size]
    ]
    return {"total": total, "items": items}


def get_record(db: Session, table_id: int, record_id: int, fields: list[MetaField] | None = None) -> dict:
    rec = db.execute(
        select(Record).where(Record.table_id == table_id, Record.id == record_id)
    ).scalars().first()
    if not rec:
        raise HTTPException(404, "记录不存在")
    return _row_to_client(rec, {f.field_name: f for f in (fields or [])})


def create_record(db: Session, mt: MetaTable, fields: list[MetaField], data: dict, user: str | None = None) -> dict:
    cleaned, errors = dyn_engine.coerce_payload(fields, data)
    if errors:
        raise HTTPException(422, detail=errors)
    for f in fields:
        if cleaned.get(f.field_name) is None and f.default_value is not None:
            from .typemap import coerce_value
            ok, cv, _ = coerce_value(f.default_value, f.data_type, True)
            if ok:
                cleaned[f.field_name] = cv
    now = datetime.now()
    rec = Record(table_id=mt.id, data=serialize_data(cleaned), created_at=now, updated_at=now)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    record = _row_to_client(rec, {f.field_name: f for f in fields})
    dyn_engine.log_audit(db, "create", mt.id, record["id"], after=record, user=user)
    db.commit()
    return record


def update_record(db: Session, mt: MetaTable, fields: list[MetaField], record_id: int, data: dict,
                  user: str | None = None) -> dict:
    rec = db.execute(
        select(Record).where(Record.table_id == mt.id, Record.id == record_id)
    ).scalars().first()
    if not rec:
        raise HTTPException(404, "记录不存在")
    fbn = {f.field_name: f for f in fields}
    before = _row_to_client(rec, fbn)
    cleaned, errors = dyn_engine.coerce_payload(fields, data, partial=True)
    if errors:
        raise HTTPException(422, detail=errors)
    merged = dict(rec.data or {})
    merged.update(serialize_data(cleaned))
    rec.data = merged
    rec.updated_at = datetime.now()
    db.commit()
    after = _row_to_client(rec, fbn)
    dyn_engine.log_audit(db, "update", mt.id, record_id, before=before, after=after, user=user)
    db.commit()
    return after


def delete_record(db: Session, table_id: int, record_id: int, fields: list[MetaField] | None = None, user: str | None = None) -> None:
    rec = db.execute(
        select(Record).where(Record.table_id == table_id, Record.id == record_id)
    ).scalars().first()
    if not rec:
        raise HTTPException(404, "记录不存在")
    before = _row_to_client(rec, {f.field_name: f for f in (fields or [])})
    db.delete(rec)
    db.commit()
    dyn_engine.log_audit(db, "delete", table_id, record_id, before=before, user=user)
    db.commit()


def bulk_insert(db: Session, table_id: int, items: list[dict]) -> None:
    """Excel 导入用。items 已 coerce（含 created_at/updated_at），批量插入。"""
    if not items:
        return
    now = datetime.now()
    rows = [
        Record(table_id=table_id, data=serialize_data(item), created_at=item.get("created_at") or now,
               updated_at=item.get("updated_at") or now)
        for item in items
    ]
    db.add_all(rows)
    db.commit()
