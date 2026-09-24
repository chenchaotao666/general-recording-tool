"""元数据管理：动态建表、字段元数据读写、表注销。"""
import re
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Integer, MetaData, Table, func, inspect, select, text
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateColumn

from ..database import engine
from ..models import ImportBatch, MetaField, MetaTable
from ..schemas import FieldIn, TableCreate
from ..utils.naming import slugify
from .typemap import coerce_value, default_widget, sa_column

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


# ---------- 表结构变更（加/删/改/重命名字段） ----------

ALTER_OP_TYPES = {"add_field", "update_field", "delete_field", "rename_field"}


def _json_records_rewrite(db: Session, table_id: int, fn) -> int:
    """遍历 json 模式全部记录，用 fn(data) 改写 data（返回 None 表示不改）。返回改动条数。"""
    from ..models import Record

    changed = 0
    for rec in db.query(Record).filter_by(table_id=table_id).all():
        new_data = fn(dict(rec.data or {}))
        if new_data is not None:
            rec.data = new_data   # 整体重赋值才触发 JSON 列 UPDATE
            changed += 1
    return changed


def alter_business_table(db: Session, mt: MetaTable, ops: list[dict]) -> dict:
    """执行结构变更操作序列。返回 {changes: [...], warnings: [...]}；任何一步非法整体抛 MetaError（路由层回滚）。

    op 四种：
    - add_field:    {op, field: {field_name, label, data_type, ...}}   physical 模式同步 ADD COLUMN
    - update_field: {op, field_name, label?/data_type?/nullable?/widget?/options?/default_value?/sort_order?}
                    改 data_type：json 模式尝试转换存量值（失败置空并计数）；physical 模式不支持（抛错）
    - delete_field: {op, field_name}   连带删除存量数据中的该字段（physical 为 DROP COLUMN）
    - rename_field: {op, field_name, new_field_name, label?}   连带迁移存量数据键名（physical 为 RENAME COLUMN）
    """
    changes, warnings = [], []
    fields = get_meta_fields(db, mt.id)
    by_name = {f.field_name: f for f in fields}
    is_json = mt.storage_mode == "json"

    for i, op in enumerate(ops or []):
        kind = op.get("op")
        if kind not in ALTER_OP_TYPES:
            raise MetaError(f"第 {i + 1} 项操作类型无效：{kind}")

        if kind == "add_field":
            try:
                fin = FieldIn(**(op.get("field") or {}))
            except Exception as e:
                raise MetaError(f"第 {i + 1} 项新字段定义无效：{e}")
            if fin.field_name in by_name or fin.field_name in RESERVED_NAMES:
                raise MetaError(f"字段名已存在或为保留字：{fin.field_name}")
            if len(fields) + 1 > 100:
                raise MetaError("单表字段数不能超过 100")
            if not is_json:
                if not _physical_exists(mt.name):
                    raise MetaError("物理表不存在，无法加列")
                ddl = str(CreateColumn(sa_column(fin)).compile(dialect=engine.dialect))
                db.execute(text(f"ALTER TABLE {mt.name} ADD COLUMN {ddl}"))
            f = MetaField(
                table_id=mt.id, field_name=fin.field_name, label=fin.label, data_type=fin.data_type,
                length=fin.length, nullable=fin.nullable, default_value=fin.default_value,
                widget=fin.widget or default_widget(fin.data_type), options=dict(fin.options or {}),
                sort_order=(fields[-1].sort_order + 1) if fields else 0,
            )
            db.add(f)
            db.flush()
            fields.append(f)
            by_name[f.field_name] = f
            changes.append(f"新增字段「{f.label}」({f.field_name}, {f.data_type})")
            continue

        name = op.get("field_name")
        f = by_name.get(name)
        if f is None:
            raise MetaError(f"第 {i + 1} 项操作的字段不存在：{name}")

        if kind == "delete_field":
            if len(fields) <= 1:
                raise MetaError("至少保留一个字段，不能全部删除")
            if is_json:
                def _del(d, fname=name):
                    if fname in d:
                        d.pop(fname)
                        return d
                    return None
                n = _json_records_rewrite(db, mt.id, _del)
            else:
                db.execute(text(f"ALTER TABLE {mt.name} DROP COLUMN {name}"))
                n = None
            if f.data_type == "image":
                from .images import delete_field_images
                delete_field_images(db, mt.id, name)   # 级联删除该字段的全部图片文件
            db.delete(f)
            db.flush()
            fields.remove(f)
            by_name.pop(name)
            changes.append(f"删除字段「{f.label}」({name})" + (f"，清理 {n} 条存量数据" if n else ""))
            continue

        if kind == "rename_field":
            new_name = str(op.get("new_field_name") or "").strip()
            if not re.match(r"^[a-z][a-z0-9_]{0,40}$", new_name):
                raise MetaError(f"新字段名必须是 snake_case：{new_name}")
            if new_name in by_name or new_name in RESERVED_NAMES:
                raise MetaError(f"新字段名已存在或为保留字：{new_name}")
            if is_json:
                def _rename(d, old=name, new=new_name):
                    if old in d:
                        d[new] = d.pop(old)
                        return d
                    return None
                n = _json_records_rewrite(db, mt.id, _rename)
            else:
                db.execute(text(f"ALTER TABLE {mt.name} RENAME COLUMN {name} TO {new_name}"))
                n = None
            old_label = f.label
            f.field_name = new_name
            if op.get("label"):
                f.label = str(op["label"])[:128]
            db.flush()
            by_name.pop(name)
            by_name[new_name] = f
            changes.append(f"字段 {name} 改名为 {new_name}" + (f"，迁移 {n} 条存量数据" if n else ""))
            warnings.append(f"任务/报表/工作流中对字段 {name} 的引用不会自动更新，请检查")
            continue

        # update_field：只改出现的键
        new_type = op.get("data_type")
        if new_type and new_type != f.data_type:
            if new_type not in ("varchar", "text", "int", "decimal", "date", "datetime", "bool"):
                raise MetaError(f"不支持的字段类型：{new_type}")
            if not is_json:
                raise MetaError("physical 模式表暂不支持修改字段类型（可导出数据后重建表，或联系管理员）")
            # json 模式：转换存量值，转不了的置空并计数
            old_type, cleared = f.data_type, 0

            def _convert(d, fname=name, nt=new_type):
                if fname not in d or d[fname] is None:
                    return None
                ok, cv, _ = coerce_value(d[fname], nt, True)
                nonlocal cleared
                if not ok:
                    cv, cleared = None, cleared + 1
                d[fname] = cv
                return d
            n = _json_records_rewrite(db, mt.id, _convert)
            f.data_type = new_type
            if f.widget not in ("select",):   # 控件未显式指定时跟随新类型
                f.widget = op.get("widget") or default_widget(new_type)
            msg = f"字段「{f.label}」类型 {old_type} → {new_type}（转换 {n} 条存量数据"
            msg += f"，{cleared} 条无法转换已置空）" if cleared else "）"
            changes.append(msg)
        for attr in ("label", "nullable", "widget", "options", "default_value", "sort_order"):
            if op.get(attr) is not None:
                setattr(f, attr, op[attr])
        if op.get("label"):
            changes.append(f"字段 {name} 显示名改为「{op['label']}」")
        db.flush()

    mt.updated_at = datetime.now()
    db.commit()
    return {"changes": changes, "warnings": warnings}


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
    from .images import delete_table_images
    delete_table_images(db, mt.id)   # 级联删除本表全部图片文件
    db.delete(mt)
    db.commit()

    from . import scheduler
    scheduler.reload_jobs()
