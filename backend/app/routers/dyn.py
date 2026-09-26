"""动态数据 CRUD：/api/dyn/{table_id}/records（表级权限：查看/新增/编辑/删除）"""
import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..services import dyn_engine, meta_service
from ..services.records_export import export_records_xlsx
from ..utils.access import TableAccess, require_table
from ..utils.auth import get_current_user

router = APIRouter(prefix="/api/dyn", tags=["dyn"])

EXPORT_MAX = 5000  # 导出记录数上限


def _parse_filters(filters: str | None) -> list[dict]:
    """兼容两种形态：JSON 数组（每条规则顶层 AND，旧）/ {logic, rules} 对象（AND/OR 组合，新）。
    统一规整成数组：对象形态作为唯一一个「组合条件」元素。"""
    if not filters:
        return []
    try:
        data = json.loads(filters)
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(400, "filters 参数必须是 JSON 数组或 {\"logic\", \"rules\"} 对象")
    if isinstance(data, dict) and isinstance(data.get("rules"), list):
        rules = [r for r in data["rules"] if isinstance(r, dict)]
        return [{"logic": data.get("logic"), "rules": rules}] if rules else []
    if isinstance(data, list):
        return [f for f in data if isinstance(f, dict)]
    raise HTTPException(400, "filters 参数必须是 JSON 数组或 {\"logic\", \"rules\"} 对象")


@router.get("/{table_id}/records")
def list_records(
    table_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=dyn_engine.MAX_PAGE_SIZE),
    sort_by: str | None = None,
    sort_order: str | None = None,
    filters: str | None = None,
    db: Session = Depends(get_db),
    access: TableAccess = Depends(require_table("view")),
):
    return dyn_engine.list_records(db, table_id, page, page_size, _parse_filters(filters), sort_by, sort_order)


@router.get("/{table_id}/export")
def export_records(
    table_id: int,
    sort_by: str | None = None,
    sort_order: str | None = None,
    filters: str | None = None,
    db: Session = Depends(get_db),
    access: TableAccess = Depends(require_table("view")),
):
    """导出记录为 xlsx：参数与列表一致（filters/sort 同参），上限 EXPORT_MAX 条。"""
    res = dyn_engine.list_records(
        db, table_id, 1, EXPORT_MAX, _parse_filters(filters), sort_by or "id", sort_order or "asc",
        page_cap=EXPORT_MAX,
    )
    fields = meta_service.get_meta_fields(db, table_id)
    columns = ([{"prop": f.field_name, "label": f.label} for f in fields]
               + [{"prop": "created_at", "label": "创建时间"}])
    buf = export_records_xlsx(access.table.label, columns, res["items"])
    filename = quote(f"{access.table.label}-导出.xlsx")
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{filename}"},
    )


@router.post("/{table_id}/records")
def create_record(
    table_id: int, data: dict,
    db: Session = Depends(get_db),
    access: TableAccess = Depends(require_table("create")),
    user: User = Depends(get_current_user),
):
    return dyn_engine.create_record(db, table_id, data, user=user.username)


@router.get("/{table_id}/records/{record_id}")
def get_record(
    table_id: int, record_id: int,
    db: Session = Depends(get_db),
    access: TableAccess = Depends(require_table("view")),
):
    return dyn_engine.get_record(db, table_id, record_id)


@router.put("/{table_id}/records/{record_id}")
def update_record(
    table_id: int, record_id: int, data: dict,
    db: Session = Depends(get_db),
    access: TableAccess = Depends(require_table("edit")),
    user: User = Depends(get_current_user),
):
    return dyn_engine.update_record(db, table_id, record_id, data, user=user.username)


@router.delete("/{table_id}/records/{record_id}")
def delete_record(
    table_id: int, record_id: int,
    db: Session = Depends(get_db),
    access: TableAccess = Depends(require_table("delete")),
    user: User = Depends(get_current_user),
):
    dyn_engine.delete_record(db, table_id, record_id, user=user.username)
    return {"ok": True}
