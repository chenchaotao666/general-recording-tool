"""元数据管理：动态建表、字段元数据读写、表注销。"""
import re
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Integer, MetaData, Table, func, inspect, select
from sqlalchemy.orm import Session

from ..database import engine
from ..models import ImportBatch, MetaField, MetaTable
from ..schemas import TableCreate
from ..utils.naming import slugify
from .typemap import sa_column

RESERVED_NAMES = {"id", "created_at", "updated_at"}
PHYSICAL_NAME_RE = re.compile(r"^dyn_[a-z][a-z0-9_]{0,50}$")


class MetaError(Exception):
    pass


def _physical_exists(name: str) -> bool:
    return inspect(engine).has_table(name)


def unique_physical_name(db: Session, base: str) -> str:
    base = re.sub(r"[^a-z0-9_]", "_", base.lower())[:50] or "table"
    if not base.startswith("dyn_"):
        base = f"dyn_{base}"
    name, k = base, 2
    while db.query(MetaTable).filter_by(name=name).first() or _physical_exists(name):
        name = f"{base}_{k}"
        k += 1
        if k > 99:
            raise MetaError("无法生成唯一表名，请手动指定物理表名")
    return name


def validate_fields(fields) -> None:
    if not fields:
        raise MetaError("至少需要一个字段")
    if len(fields) > 100:
        raise MetaError("单表字段数不能超过 100")
    seen = set()
    for f in fields:
        if f.field_name in RESERVED_NAMES:
            raise MetaError(f"字段名 {f.field_name} 为保留字")
        if f.field_name in seen:
            raise MetaError(f"字段名重复：{f.field_name}")
        seen.add(f.field_name)


def create_business_table(db: Session, payload: TableCreate, owner_id: int) -> MetaTable:
    validate_fields(payload.fields)
    base = payload.name or slugify(payload.label)
    name = unique_physical_name(db, base)
    storage_mode = getattr(payload, "storage_mode", None) or "json"

    if storage_mode == "physical":
        md = MetaData()
        id_col = Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
        cols = [id_col] + [sa_column(f) for f in payload.fields]
        cols += [
            Column("created_at", DateTime, default=datetime.now),
            Column("updated_at", DateTime, default=datetime.now, onupdate=datetime.now),
        ]
        Table(name, md, *cols)
        md.create_all(engine)
    # json 模式不建物理表，name 仅作唯一逻辑标识

    mt = MetaTable(
        name=name,
        label=payload.label,
        source_file=payload.source.file_id if payload.source else None,
        owner_id=owner_id,
        storage_mode=storage_mode,
    )
    db.add(mt)
    db.flush()
    for i, f in enumerate(payload.fields):
        options = dict(f.options or {})
        if f.source_header:
            options["source_header"] = f.source_header
        db.add(MetaField(
            table_id=mt.id, field_name=f.field_name, label=f.label, data_type=f.data_type,
            length=f.length, nullable=f.nullable, default_value=f.default_value,
            widget=f.widget, options=options, sort_order=i,
        ))
    db.commit()
    db.refresh(mt)
    return mt


def get_meta_table(db: Session, table_id: int) -> MetaTable | None:
    return db.get(MetaTable, table_id)


def get_meta_fields(db: Session, table_id: int) -> list[MetaField]:
    return (
        db.query(MetaField)
        .filter_by(table_id=table_id)
        .order_by(MetaField.sort_order, MetaField.id)
        .all()
    )


def reflect_table(name: str) -> Table:
    return Table(name, MetaData(), autoload_with=engine)


def record_count(db: Session, mt: MetaTable) -> int:
    """physical 模式反射物理表计数；json 模式走 records 单表。"""
    if mt.storage_mode == "json":
        from . import json_store
        return json_store.count(db, mt.id)
    if not _physical_exists(mt.name):
        return 0
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(reflect_table(mt.name))).scalar() or 0


def field_out(f: MetaField) -> dict:
    return {
        "id": f.id, "field_name": f.field_name, "label": f.label,
        "data_type": f.data_type, "length": f.length, "nullable": f.nullable,
        "default_value": f.default_value, "widget": f.widget,
        "options": f.options or {}, "sort_order": f.sort_order,
    }


def table_out(db: Session, mt: MetaTable, with_fields: bool = True, access: dict | None = None) -> dict:
    out = {
        "id": mt.id, "name": mt.name, "label": mt.label,
        "source_file": mt.source_file, "status": mt.status,
        "owner_id": mt.owner_id, "storage_mode": mt.storage_mode or "json",
        "record_count": record_count(db, mt),
        "created_at": mt.created_at.isoformat(sep=" ") if mt.created_at else None,
    }
    if access:
        out.update(access)  # is_owner / my_perms 等
    if with_fields:
        out["fields"] = [field_out(f) for f in get_meta_fields(db, mt.id)]
    return out


def drop_business_table(db: Session, mt: MetaTable) -> None:
    """删表：物理表（如有）+ 元数据 + 全部关联数据（记录/分享/规则/报表/识别留痕/导入批次）。"""
    from ..models import (Record, ReportRunLog, ReportTemplate, SharedLink, TableShare, TaskRule, TaskRunLog,
                          TaskTriggerLog, VisionLog)

    if mt.storage_mode == "physical" and _physical_exists(mt.name):
        reflect_table(mt.name).drop(engine)
    rule_ids = [r.id for r in db.query(TaskRule).filter_by(table_id=mt.id).all()]
    if rule_ids:
        db.query(TaskTriggerLog).filter(TaskTriggerLog.rule_id.in_(rule_ids)).delete(synchronize_session=False)
        db.query(TaskRunLog).filter(TaskRunLog.rule_id.in_(rule_ids)).delete(synchronize_session=False)
        db.query(TaskRule).filter(TaskRule.id.in_(rule_ids)).delete(synchronize_session=False)
    tpl_ids = [t.id for t in db.query(ReportTemplate).filter_by(table_id=mt.id).all()]
    if tpl_ids:
        db.query(ReportRunLog).filter(ReportRunLog.template_id.in_(tpl_ids)).delete(synchronize_session=False)
        db.query(SharedLink).filter(SharedLink.resource_type == "report", SharedLink.resource_id.in_(tpl_ids)).delete(synchronize_session=False)
        db.query(ReportTemplate).filter(ReportTemplate.id.in_(tpl_ids)).delete(synchronize_session=False)
    db.query(SharedLink).filter(SharedLink.resource_type == "table", SharedLink.resource_id == mt.id).delete(synchronize_session=False)
    db.query(VisionLog).filter_by(table_id=mt.id).delete(synchronize_session=False)
    db.query(Record).filter_by(table_id=mt.id).delete(synchronize_session=False)
    db.query(TableShare).filter_by(table_id=mt.id).delete(synchronize_session=False)
    db.query(MetaField).filter_by(table_id=mt.id).delete(synchronize_session=False)
    db.query(ImportBatch).filter_by(table_id=mt.id).delete(synchronize_session=False)
    db.delete(mt)
    db.commit()

    from . import scheduler
    scheduler.reload_jobs()
