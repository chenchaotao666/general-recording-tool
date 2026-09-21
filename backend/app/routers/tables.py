"""数据表管理：确认建表 + 导入、表/字段元数据查询与调整、删表。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ImportBatch, MetaField
from ..schemas import TableCreate, TableUpdate
from ..services import meta_service
from ..services.dyn_engine import log_audit, row_to_dict
from ..services.excel_parser import ExcelParseError, build_headers, read_sheet
from ..services.meta_service import MetaError
from ..services.typemap import coerce_value
from ..services.uploads import UploadNotFound, get_upload_filename, get_upload_path

router = APIRouter(prefix="/api/tables", tags=["tables"])

IMPORT_BATCH_SIZE = 500
FAIL_DETAIL_CAP = 200


@router.get("")
def list_tables(db: Session = Depends(get_db)):
    from ..models import MetaTable
    rows = db.query(MetaTable).order_by(MetaTable.id.desc()).all()
    return [meta_service.table_out(db, t, with_fields=False) for t in rows]


@router.get("/{table_id}")
def get_table(table_id: int, db: Session = Depends(get_db)):
    mt = meta_service.get_meta_table(db, table_id)
    if not mt:
        raise HTTPException(404, "数据表不存在")
    return meta_service.table_out(db, mt)


@router.post("")
def create_table(payload: TableCreate, db: Session = Depends(get_db)):
    try:
        mt = meta_service.create_business_table(db, payload)
    except MetaError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(400, f"建表失败：{e}")

    log_audit(db, "create_table", mt.id, after={"name": mt.name, "label": mt.label})
    db.commit()

    report = None
    if payload.source:
        report = _run_import(db, mt, payload.source)
    return {"table": meta_service.table_out(db, mt), "import_report": report}


@router.put("/{table_id}")
def update_table(table_id: int, payload: TableUpdate, db: Session = Depends(get_db)):
    mt = meta_service.get_meta_table(db, table_id)
    if not mt:
        raise HTTPException(404, "数据表不存在")
    if payload.label is not None:
        mt.label = payload.label
    for fu in (payload.fields or []):
        f = db.get(MetaField, fu.id)
        if not f or f.table_id != table_id:
            continue
        for attr in ("label", "nullable", "widget", "options", "sort_order"):
            v = getattr(fu, attr)
            if v is not None:
                setattr(f, attr, v)
    db.commit()
    return meta_service.table_out(db, mt)


@router.delete("/{table_id}")
def delete_table(table_id: int, db: Session = Depends(get_db)):
    mt = meta_service.get_meta_table(db, table_id)
    if not mt:
        raise HTTPException(404, "数据表不存在")
    log_audit(db, "drop_table", mt.id, before={"name": mt.name, "label": mt.label})
    meta_service.drop_business_table(db, mt)
    return {"ok": True}


def _run_import(db: Session, mt, source) -> dict:
    """把 Excel 数据按字段映射批量写入业务表，返回导入报告。"""
    fields = meta_service.get_meta_fields(db, mt.id)
    try:
        path = get_upload_path(source.file_id)
        rows = read_sheet(path, source.sheet_name)
    except (UploadNotFound, ExcelParseError) as e:
        raise HTTPException(400, str(e))

    h_idx = source.header_row - 1
    if h_idx < 0 or h_idx >= len(rows):
        raise HTTPException(400, "表头行号超出范围")
    headers = build_headers(rows[h_idx])
    data_rows = rows[h_idx + 1:]

    # 源表头 -> 字段 映射（以字段上记录的 source_header 为准）
    header_to_field: dict[str, MetaField] = {}
    for f in fields:
        src = (f.options or {}).get("source_header")
        if src and src not in header_to_field:
            header_to_field[src] = f

    table = meta_service.reflect_table(mt.name)
    total = len(data_rows)
    success, failures = 0, []

    def flush_batch(batch: list[tuple[int, dict]]):
        nonlocal success
        if not batch:
            return
        try:
            db.execute(table.insert(), [item for _, item in batch])
            db.commit()
            success += len(batch)
        except Exception:
            db.rollback()
            # 批量失败则逐行隔离坏数据
            for row_no, item in batch:
                try:
                    db.execute(table.insert().values(**item))
                    db.commit()
                    success += 1
                except Exception as e:
                    db.rollback()
                    failures.append({"row_no": row_no, "error": str(e)[:200],
                                     "values": {k: str(v)[:50] for k, v in item.items()}})

    batch: list[tuple[int, dict]] = []
    for idx, row in enumerate(data_rows):
        row_no = h_idx + 2 + idx  # Excel 中的 1-based 行号
        item, row_errors = {}, {}
        for i, h in enumerate(headers):
            f = header_to_field.get(h)
            if f is None:
                continue
            raw = row[i] if i < len(row) else None
            ok, cv, err = coerce_value(raw, f.data_type, f.nullable)
            if ok:
                item[f.field_name] = cv
            else:
                row_errors[f.field_name] = f"{f.label}：{err}"
        if row_errors:
            failures.append({"row_no": row_no, "error": "; ".join(row_errors.values()),
                             "values": {h: str(row[i])[:50] for i, h in enumerate(headers) if i < len(row)}})
            continue
        now = datetime.now()
        item["created_at"] = now
        item["updated_at"] = now
        batch.append((row_no, item))
        if len(batch) >= IMPORT_BATCH_SIZE:
            flush_batch(batch)
            batch = []
    flush_batch(batch)

    batch_row = ImportBatch(
        table_id=mt.id, file_name=get_upload_filename(source.file_id),
        total=total, success=success, failed=len(failures),
        fail_detail=failures[:FAIL_DETAIL_CAP],
    )
    db.add(batch_row)
    db.commit()
    return {"total": total, "success": success, "failed": len(failures), "failures": failures[:FAIL_DETAIL_CAP]}
