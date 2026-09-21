"""动态数据 CRUD：/api/dyn/{table_id}/records"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import dyn_engine

router = APIRouter(prefix="/api/dyn", tags=["dyn"])


def _parse_filters(filters: str | None) -> list[dict]:
    if not filters:
        return []
    try:
        data = json.loads(filters)
        if not isinstance(data, list):
            raise ValueError
        return [f for f in data if isinstance(f, dict)]
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(400, "filters 参数必须是 JSON 数组")


@router.get("/{table_id}/records")
def list_records(
    table_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=dyn_engine.MAX_PAGE_SIZE),
    sort_by: str | None = None,
    sort_order: str | None = None,
    filters: str | None = None,
    db: Session = Depends(get_db),
):
    return dyn_engine.list_records(db, table_id, page, page_size, _parse_filters(filters), sort_by, sort_order)


@router.post("/{table_id}/records")
def create_record(table_id: int, data: dict, db: Session = Depends(get_db)):
    return dyn_engine.create_record(db, table_id, data)


@router.get("/{table_id}/records/{record_id}")
def get_record(table_id: int, record_id: int, db: Session = Depends(get_db)):
    return dyn_engine.get_record(db, table_id, record_id)


@router.put("/{table_id}/records/{record_id}")
def update_record(table_id: int, record_id: int, data: dict, db: Session = Depends(get_db)):
    return dyn_engine.update_record(db, table_id, record_id, data)


@router.delete("/{table_id}/records/{record_id}")
def delete_record(table_id: int, record_id: int, db: Session = Depends(get_db)):
    dyn_engine.delete_record(db, table_id, record_id)
    return {"ok": True}
