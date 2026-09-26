"""动态 CRUD 引擎：运行时按元数据反射业务表，动态拼 SQL（字段名全部来自服务端元数据）。"""
import json
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import MetaData, Table, and_, func, or_, select
from sqlalchemy.orm import Session

from ..database import engine
from ..models import AuditLog, MetaField, MetaTable
from .meta_service import get_meta_fields
from .typemap import coerce_value

FILTER_OPS = {
    "eq", "ne", "gt", "gte", "lt", "lte", "contains", "startswith", "in", "null", "not_null",
    "today",             # 当天（日期=今天 / 日期时间在今天 00:00~24:00 内）
    "past_days",         # 过去 N 天（含今天）
    "older_than_days",   # 日期字段早于 N 天前（如：超过30天未跟进）
    "within_days",       # 日期字段在未来 N 天内（如：7天内到期）
}
MAX_PAGE_SIZE = 200


def serialize_value(v):
    if isinstance(v, datetime):
        return v.isoformat(sep=" ")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def row_to_dict(row) -> dict:
    return {k: serialize_value(v) for k, v in dict(row).items()}


def _image_field_names(fields: list[MetaField]) -> list[str]:
    return [f.field_name for f in fields if f.data_type == "image"]


def _encode_image_fields(cleaned: dict, fields: list[MetaField]) -> None:
    """physical 模式：image 列是 Text，写入前把 list 编码为 JSON 字符串。"""
    for name in _image_field_names(fields):
        if name in cleaned and cleaned[name] is not None:
            cleaned[name] = json.dumps(cleaned[name], ensure_ascii=False)


def _expand_image_fields(record: dict, fields: list[MetaField]) -> dict:
    """physical 模式：读出时把 image 列的 JSON 字符串还原为 list。"""
    for name in _image_field_names(fields):
        v = record.get(name)
        if isinstance(v, str):
            try:
                record[name] = json.loads(v) if v else None
            except ValueError:
                record[name] = None
    return record


def load_meta(db: Session, table_id: int) -> tuple[MetaTable, list[MetaField]]:
    """只取元数据（不反射物理表）：json 模式与分流判断用。"""
    mt = db.get(MetaTable, table_id)
    if not mt:
        raise HTTPException(404, "数据表不存在")
    return mt, get_meta_fields(db, table_id)


def load_business(db: Session, table_id: int) -> tuple[MetaTable, list[MetaField], Table]:
    mt = db.get(MetaTable, table_id)
    if not mt:
        raise HTTPException(404, "数据表不存在")
    fields = get_meta_fields(db, table_id)
    try:
        table = Table(mt.name, MetaData(), autoload_with=engine)
    except Exception:
        raise HTTPException(500, f"物理表 {mt.name} 加载失败")
    return mt, fields, table


def log_audit(db: Session, action: str, table_id: int | None, record_id: int | None = None,
              before: dict | None = None, after: dict | None = None, user: str | None = None) -> None:
    db.add(AuditLog(action=action, table_id=table_id, record_id=record_id,
                    before_json=before, after_json=after, user=user or "system"))


def build_condition(table: Table, fields_by_name: dict, flt: dict):
    name = flt.get("field")
    op = flt.get("op")
    value = flt.get("value")
    if name not in fields_by_name and name not in ("id", "created_at", "updated_at"):
        raise HTTPException(400, f"未知筛选字段：{name}")
    if op not in FILTER_OPS:
        raise HTTPException(400, f"不支持的筛选操作符：{op}")
    col = table.c[name]
    if op == "null":
        return col.is_(None)
    if op == "not_null":
        return col.isnot(None)

    f = fields_by_name.get(name)
    is_date = f is not None and f.data_type == "date"
    now = datetime.now()
    today = now.date()

    # 无需值的相对日期操作符
    if op == "today":
        if is_date:
            return col == today
        return and_(col >= now.replace(hour=0, minute=0, second=0, microsecond=0),
                    col < now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))

    # 相对日期操作符（任务条件常用）
    if op in ("older_than_days", "within_days", "past_days"):
        try:
            days = int(value)
        except (TypeError, ValueError):
            raise HTTPException(400, "天数必须是整数")
        if op == "older_than_days":
            threshold = now - timedelta(days=days)
            return col < (threshold.date() if is_date else threshold)
        if op == "within_days":
            lo = today if is_date else now
            hi = now + timedelta(days=days)
            return and_(col >= lo, col <= (hi.date() if is_date else hi))
        # past_days：过去 N 天（含今天），N=1 即当天
        start_date = today - timedelta(days=max(days - 1, 0))
        if is_date:
            return and_(col >= start_date, col <= today)
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(today + timedelta(days=1), datetime.min.time())
        return and_(col >= start_dt, col < end_dt)

    def coerce(v):
        if f is None:
            return v
        ok, cv, err = coerce_value(v, f.data_type, True)
        if not ok:
            raise HTTPException(400, f"筛选值无效（{f.label}）：{err}")
        return cv

    if op == "contains":
        return col.like(f"%{value}%")
    if op == "startswith":
        return col.like(f"{value}%")
    if op == "in":
        values = value if isinstance(value, list) else [v.strip() for v in str(value).split(",")]
        return col.in_([coerce(v) for v in values])
    value = coerce(value)
    if op == "eq":
        return col == value
    if op == "ne":
        return col != value
    if op == "gt":
        return col > value
    if op == "gte":
        return col >= value
    if op == "lt":
        return col < value
    return col <= value  # lte


def combine_conditions(conds: list, logic: str):
    """按 AND/OR 组合条件列表（供列表筛选和任务引擎共用）。"""
    from sqlalchemy import or_
    if not conds:
        return []
    if logic == "OR":
        return [or_(*conds)]
    return conds


def rule_value_ok(f: MetaField | None, op: str, value) -> bool:
    """校验筛选值能否按字段类型转换（保存任务/报表前把关，拦截 today 之类的字面量）。"""
    if op in ("null", "not_null", "today") or f is None:
        return True
    if op in ("older_than_days", "within_days", "past_days"):
        try:
            int(value)
            return True
        except (TypeError, ValueError):
            return False
    if op == "in":
        values = value if isinstance(value, list) else [v.strip() for v in str(value).split(",")]
    else:
        values = [value]
    for v in values:
        ok, _, _ = coerce_value(v, f.data_type, True)
        if not ok:
            return False
    return True


def _to_condition(table: Table, fields_by_name: dict, f: dict):
    """单条规则 → SQL 条件；{logic, rules} 形态按 AND/OR 组展开（组内递归仍是扁平规则）。"""
    if isinstance(f, dict) and isinstance(f.get("rules"), list):
        subs = [build_condition(table, fields_by_name, r) for r in f["rules"] if isinstance(r, dict)]
        if not subs:
            return None
        return or_(*subs) if f.get("logic") == "OR" else and_(*subs)
    return build_condition(table, fields_by_name, f)


def list_records(db: Session, table_id: int, page: int, page_size: int,
                 filters: list[dict] | None, sort_by: str | None, sort_order: str | None,
                 page_cap: int = MAX_PAGE_SIZE) -> dict:
    """page_cap：页大小上限，常规列表用默认 200；导出等批量场景可放宽（传 EXPORT_MAX）。
    filters 元素除单条规则外，也接受 {"logic": "AND"|"OR", "rules": [...]} 组合条件。"""
    mt, fields = load_meta(db, table_id)
    if mt.storage_mode == "json":
        from . import json_store
        return json_store.list_records(db, mt, fields, page, page_size, filters, sort_by, sort_order, page_cap)
    _, fields, table = load_business(db, table_id)
    fields_by_name = {f.field_name: f for f in fields}
    conds = [c for c in (_to_condition(table, fields_by_name, f) for f in (filters or [])) if c is not None]

    page = max(page, 1)
    page_size = min(max(page_size, 1), page_cap)
    total = db.execute(select(func.count()).select_from(table).where(*conds)).scalar() or 0

    sortable = set(fields_by_name) | {"id", "created_at", "updated_at"}
    if sort_by in sortable:
        order_col = table.c[sort_by]
        order = order_col.asc() if sort_order == "asc" else order_col.desc()
    else:
        order = table.c.id.desc()

    rows = db.execute(
        select(table).where(*conds).order_by(order)
        .offset((page - 1) * page_size).limit(page_size)
    ).mappings().all()
    return {"total": total, "items": [_expand_image_fields(row_to_dict(r), fields) for r in rows]}


def coerce_payload(fields: list[MetaField], data: dict, partial: bool = False):
    """按字段元数据校验并转换提交的数据。返回 (cleaned, errors)。"""
    by_name = {f.field_name: f for f in fields}
    cleaned, errors = {}, {}
    for key, v in (data or {}).items():
        if key not in by_name:
            continue  # 忽略未知字段，防注入
        f = by_name[key]
        ok, cv, err = coerce_value(v, f.data_type, f.nullable)
        if ok:
            cleaned[key] = cv
        else:
            errors[key] = f"{f.label}：{err}"
    if not partial:
        for f in fields:
            if not f.nullable and cleaned.get(f.field_name) is None and not f.default_value:
                errors.setdefault(f.field_name, f"{f.label}不能为空")
    return cleaned, errors


def get_record(db: Session, table_id: int, record_id: int) -> dict:
    mt, fields = load_meta(db, table_id)
    if mt.storage_mode == "json":
        from . import json_store
        return json_store.get_record(db, table_id, record_id, fields)
    _, _, table = load_business(db, table_id)
    row = db.execute(select(table).where(table.c.id == record_id)).mappings().first()
    if not row:
        raise HTTPException(404, "记录不存在")
    return _expand_image_fields(row_to_dict(row), fields)


def _fire_workflow_hook(kind: str, table_id: int, record: dict, old_record: dict | None = None) -> None:
    """记录变更触发工作流。只投递不执行，失败绝不影响写入主流程。"""
    try:
        from .workflow import triggers
        triggers.fire_record_event(table_id, kind, record, old_record)
    except Exception:
        pass


def create_record(db: Session, table_id: int, data: dict, user: str | None = None) -> dict:
    mt, fields = load_meta(db, table_id)
    if mt.storage_mode == "json":
        from . import json_store
        record = json_store.create_record(db, mt, fields, data, user=user)
        _sync_images(db, table_id, record["id"], fields, {}, record)
        _fire_workflow_hook("record_created", table_id, record)
        return record
    _, fields, table = load_business(db, table_id)
    cleaned, errors = coerce_payload(fields, data)
    if errors:
        raise HTTPException(422, detail=errors)
    for f in fields:
        if cleaned.get(f.field_name) is None and f.default_value is not None:
            ok, cv, _ = coerce_value(f.default_value, f.data_type, True)
            if ok:
                cleaned[f.field_name] = cv
    now = datetime.now()
    cleaned["created_at"] = now
    cleaned["updated_at"] = now
    _encode_image_fields(cleaned, fields)
    result = db.execute(table.insert().values(**cleaned))
    db.commit()
    record = get_record(db, table_id, result.inserted_primary_key[0])
    log_audit(db, "create", table_id, record["id"], after=record, user=user)
    db.commit()
    _sync_images(db, table_id, record["id"], fields, {}, record)
    _fire_workflow_hook("record_created", table_id, record)
    return record


def update_record(db: Session, table_id: int, record_id: int, data: dict, user: str | None = None) -> dict:
    mt, fields = load_meta(db, table_id)
    if mt.storage_mode == "json":
        from . import json_store
        before = json_store.get_record(db, table_id, record_id, fields)
        record = json_store.update_record(db, mt, fields, record_id, data, user=user)
        _sync_images(db, table_id, record_id, fields, before, record)
        _fire_workflow_hook("record_updated", table_id, record)
        return record
    _, fields, table = load_business(db, table_id)
    before = get_record(db, table_id, record_id)
    cleaned, errors = coerce_payload(fields, data, partial=True)
    if errors:
        raise HTTPException(422, detail=errors)
    cleaned["updated_at"] = datetime.now()
    _encode_image_fields(cleaned, fields)
    db.execute(table.update().where(table.c.id == record_id).values(**cleaned))
    db.commit()
    after = get_record(db, table_id, record_id)
    log_audit(db, "update", table_id, record_id, before=before, after=after, user=user)
    db.commit()
    _sync_images(db, table_id, record_id, fields, before, after)
    _fire_workflow_hook("record_updated", table_id, after, before)
    return after


def _sync_images(db: Session, table_id: int, record_id: int, fields, before: dict, after: dict) -> None:
    names = _image_field_names(fields)
    if not names:
        return
    try:
        from . import images
        images.sync_record_images(db, table_id, record_id, names, before or {}, after or {})
    except Exception:  # noqa: BLE001 — 图片归属同步失败不影响写入主流程
        db.rollback()


def delete_record(db: Session, table_id: int, record_id: int, user: str | None = None) -> None:
    mt, fields = load_meta(db, table_id)
    if mt.storage_mode == "json":
        from . import json_store
        json_store.delete_record(db, table_id, record_id, fields=fields, user=user)
        _delete_images(db, record_id)
        return
    _, _, table = load_business(db, table_id)
    before = get_record(db, table_id, record_id)
    db.execute(table.delete().where(table.c.id == record_id))
    log_audit(db, "delete", table_id, record_id, before=before, user=user)
    db.commit()
    _delete_images(db, record_id)


def _delete_images(db: Session, record_id: int) -> None:
    try:
        from . import images
        images.delete_record_images(db, record_id)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
