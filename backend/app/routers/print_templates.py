"""工单打印模板：按表共享（view 可见 / owner·admin 可编辑），全部 Excel 方式。

版式由 xlsx 模板文件承载（浏览器内编辑器 / 上传），打印时按占位符填充下载。
首次打开某表的模板列表时自动播种一个「默认打印模板」（起始 xlsx 已布好占位符）。
"""
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PrintTemplate, User
from ..schemas import PrintExcelJsonIn, PrintTemplateIn
from ..services import dyn_engine
from ..services.luckysheet_xlsx import sheets_to_xlsx
from ..services.meta_service import get_meta_fields
from ..services.print_excel import MAX_FILL_RECORDS, fill_workbook, starter_workbook, tpl_path
from ..services.print_html import render_fill_html
from ..utils.access import TableAccess, get_table_access, require_table
from ..utils.auth import get_current_user
from .dyn import _parse_filters

router = APIRouter(prefix="/api/print-templates", tags=["print-templates"])
nested = APIRouter(prefix="/api/tables/{table_id}/print-templates", tags=["print-templates"])

MAX_TEMPLATE_SIZE = 2 * 1024 * 1024   # xlsx 模板上传上限


def _out(db: Session, tpl: PrintTemplate) -> dict:
    creator = db.get(User, tpl.user_id) if tpl.user_id else None
    return {
        "id": tpl.id, "table_id": tpl.table_id, "name": tpl.name,
        "is_default": bool(tpl.is_default),
        "config": tpl.config_json or {},
        "has_excel": tpl_path(tpl.id).exists(),
        "creator": creator.username if creator else None,
        "created_at": str(tpl.created_at or ""), "updated_at": str(tpl.updated_at or ""),
    }


def _require_manage(access: TableAccess) -> None:
    """模板是表级共享配置：写权限 = 表 owner/admin（同 canAlter 语义；分享者只到记录级）。"""
    if not (access.is_owner or access.is_admin):
        raise HTTPException(404, "数据表不存在")


def _clear_default(db: Session, table_id: int, keep_id: int | None = None) -> None:
    q = db.query(PrintTemplate).filter_by(table_id=table_id, is_default=True)
    if keep_id is not None:
        q = q.filter(PrintTemplate.id != keep_id)
    q.update({"is_default": False}, synchronize_session=False)


def _get_tpl_access(db: Session, tpl_id: int, user: User) -> tuple[PrintTemplate, TableAccess]:
    tpl = db.get(PrintTemplate, tpl_id)
    if not tpl:
        raise HTTPException(404, "打印模板不存在")
    return tpl, get_table_access(db, tpl.table_id, user)


@nested.get("")
def list_templates(access: TableAccess = Depends(require_table("view")), db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """列出该表全部模板（不再自动播种；新建模板从起始模板/模板库起步）。"""
    rows = (db.query(PrintTemplate).filter_by(table_id=access.table.id)
            .order_by(PrintTemplate.id).all())
    return {
        "templates": [_out(db, t) for t in rows],
        "can_manage": bool(access.is_owner or access.is_admin),
    }


@nested.post("")
def create_template(payload: PrintTemplateIn, access: TableAccess = Depends(require_table("view")),
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_manage(access)
    tpl = PrintTemplate(
        table_id=access.table.id, user_id=user.id,
        name=payload.name, kind="excel", paper="a4", enabled=True,
        is_default=payload.is_default, config_json={},
    )
    if tpl.is_default:
        _clear_default(db, access.table.id)
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return _out(db, tpl)


# ---------- 模板库：docs/打印模板 下的样例模板，编辑器里可一键套用 ----------
# 对照预览图已发布为前端静态资源（frontend/public/print-library/，
# 由 docs/打印模板/compress_library_images.py 从 docs/工单打印截图 生成），
# 前端按约定路径 /print-library/<行业>/<名称>.jpg 直接引用，不经过本接口。

from ..config import BASE_DIR as _BASE_DIR

_LIB_XLSX = _BASE_DIR.parent / "docs" / "打印模板"


def _lib_safe(root: Path, rel: str) -> Path:
    p = (root / rel).resolve()
    if not str(p).startswith(str(root.resolve())) or not p.is_file():
        raise HTTPException(404, "文件不存在")
    return p


@router.get("/library")
def library_list(user: User = Depends(get_current_user)):
    """模板库清单：分行业目录列出样例模板；img 为前端静态预览图的约定路径（可能不存在，前端兜底）。"""
    items = []
    for f in sorted(_LIB_XLSX.glob("*/*.xlsx")):
        if f.name.startswith("~$"):
            continue
        items.append({
            "dir": f.parent.name, "name": f.stem,
            "file": f"{f.parent.name}/{f.name}",
            "img": f"{f.parent.name}/{f.stem}.jpg",
        })
    return {"items": items}


@router.get("/library/file")
def library_file(path: str, user: User = Depends(get_current_user)):
    """取模板库 xlsx 模板文件。"""
    from fastapi.responses import FileResponse

    p = _lib_safe(_LIB_XLSX, path)
    return FileResponse(p, media_type=_XLSX_MIME)




@router.get("/{tpl_id}")
def get_template(tpl_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl, _ = _get_tpl_access(db, tpl_id, user)
    return _out(db, tpl)


@router.put("/{tpl_id}")
def update_template(tpl_id: int, payload: PrintTemplateIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    tpl, access = _get_tpl_access(db, tpl_id, user)
    _require_manage(access)
    tpl.name = payload.name
    # config（文件名/上传时间等）由 excel 接口维护，这里不动
    if payload.is_default:
        _clear_default(db, tpl.table_id, keep_id=tpl.id)
    tpl.is_default = payload.is_default
    db.commit()
    return _out(db, tpl)


@router.delete("/{tpl_id}")
def delete_template(tpl_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl, access = _get_tpl_access(db, tpl_id, user)
    _require_manage(access)
    tpl_path(tpl.id).unlink(missing_ok=True)   # excel 模板文件一并清理
    db.delete(tpl)
    db.commit()
    return {"ok": True}


@router.post("/{tpl_id}/duplicate")
def duplicate_template(tpl_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl, _ = _get_tpl_access(db, tpl_id, user)
    dup = PrintTemplate(
        table_id=tpl.table_id, user_id=user.id,
        name=f"{tpl.name}（副本）", kind="excel", paper="a4",
        enabled=True, is_default=False,
        config_json=dict(tpl.config_json or {}),
    )
    db.add(dup)
    db.flush()   # 先拿到 dup.id 再复制 excel 模板文件
    src = tpl_path(tpl.id)
    if src.exists():
        import shutil
        shutil.copyfile(src, tpl_path(dup.id))
    db.commit()
    db.refresh(dup)
    return _out(db, dup)


@router.post("/{tpl_id}/set-default")
def set_default_template(tpl_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl, access = _get_tpl_access(db, tpl_id, user)
    _require_manage(access)
    _clear_default(db, tpl.table_id)
    tpl.is_default = True
    db.commit()
    return _out(db, tpl)


# ---------- Excel 模板：起始模板 / 上传 / 下载 / 填充打印 ----------

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _download(data: bytes, filename: str):
    return Response(
        content=data, media_type=_XLSX_MIME,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@nested.get("/starter")
def download_starter(access: TableAccess = Depends(require_table("view")), db: Session = Depends(get_db)):
    """下载按表结构生成的起始 xlsx 模板（占位符已布好，新建/编辑模板都可用）。"""
    data = starter_workbook(access.table, get_meta_fields(db, access.table.id))
    return _download(data, f"{access.table.label}-打印起始模板.xlsx")


@router.post("/{tpl_id}/excel")
async def upload_excel(tpl_id: int, file: UploadFile, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    """上传/替换 xlsx 模板文件（owner/admin）。"""
    tpl, access = _get_tpl_access(db, tpl_id, user)
    _require_manage(access)
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(400, "只支持 .xlsx 文件")
    content = await file.read()
    if not content.startswith(b"PK"):
        raise HTTPException(400, "文件内容不是有效的 xlsx")
    if len(content) > MAX_TEMPLATE_SIZE:
        raise HTTPException(400, "模板文件不能超过 2MB")
    try:
        import io as _io
        from openpyxl import load_workbook
        load_workbook(_io.BytesIO(content))
    except Exception:
        raise HTTPException(400, "xlsx 文件解析失败，请检查文件是否损坏")
    tpl.kind = "excel"
    tpl_path(tpl.id).write_bytes(content)
    cfg = dict(tpl.config_json or {})
    cfg.update({"orig_name": file.filename, "uploaded_at": datetime.now().isoformat(timespec="seconds")})
    tpl.config_json = cfg
    db.commit()
    return _out(db, tpl)


@nested.post("/preview-fill")
def preview_fill(payload: PrintExcelJsonIn, access: TableAccess = Depends(require_table("view")),
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """编辑器内容即时预览：sheets JSON → xlsx → 按当前筛选口径填充 → HTML（不落盘）。

    与 /fill-view 同口径（filters/sort/上限），保证"编辑器里看到的预览 == 打印预览"。
    """
    import io
    import json as _json

    if len(_json.dumps(payload.sheets, ensure_ascii=False)) > 8 * 1024 * 1024:
        raise HTTPException(400, "表格数据过大")
    try:
        data = sheets_to_xlsx(payload.sheets)
        # 编辑器未承载的图片（解析不了的锚点）从该模板已保存的文件里带入，预览与打印一致；
        # 编辑器已带回的图按 xl/media 内容去重（不能读 openpyxl 图片流判断，读后 save 会崩）
        if payload.template_id:
            old = tpl_path(payload.template_id)
            if old.exists():
                from openpyxl import load_workbook as _lw
                from ..services.print_excel import _copy_images, xlsx_media_bytes

                old_wb = _lw(old)
                if old_wb.active._images:
                    new_wb = _lw(io.BytesIO(data))
                    _copy_images(old_wb.active, new_wb.active, skip=xlsx_media_bytes(data))
                    buf = io.BytesIO()
                    new_wb.save(buf)
                    data = buf.getvalue()
    except Exception as e:
        raise HTTPException(400, f"表格数据无法转换为 xlsx：{e}")
    res = dyn_engine.list_records(
        db, access.table.id, 1, MAX_FILL_RECORDS, _parse_filters(payload.filters),
        payload.sort_by or "id", payload.sort_order or "asc", page_cap=MAX_FILL_RECORDS,
    )
    if not res["items"]:
        raise HTTPException(400, "当前筛选结果为空，没有可预览的记录")
    fields = get_meta_fields(db, access.table.id)
    paper = payload.paper if payload.paper in ("a4", "half", "third") else "a4"
    # 模板预览只看版式效果：非整表（_row）模式只填第一条记录出一份样例；
    # 整表模式全部记录本来就是同一份单据的明细行
    from openpyxl import load_workbook

    from ..services.print_excel import _has_flat_tokens

    wb_probe = load_workbook(io.BytesIO(data))
    items = res["items"] if _has_flat_tokens(wb_probe.active) else res["items"][:1]
    html = render_fill_html(io.BytesIO(data), access.table, fields, items,
                            title="模板预览", paper=paper)
    return Response(content=html, media_type="text/html; charset=utf-8")



@router.post("/{tpl_id}/excel-json")
def save_excel_json(tpl_id: int, payload: PrintExcelJsonIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """保存浏览器内编辑器的表格 JSON（luckysheet getAllSheets），后端还原为 xlsx。"""
    import json as _json

    tpl, access = _get_tpl_access(db, tpl_id, user)
    _require_manage(access)
    if len(_json.dumps(payload.sheets, ensure_ascii=False)) > 8 * 1024 * 1024:
        raise HTTPException(400, "表格数据过大，请精简后再保存")
    try:
        data = sheets_to_xlsx(payload.sheets)
        # 编辑器未承载的图片（如 luckyexcel 解析不了的锚点）从原模板文件带回；
        # 编辑器已带回的图按 xl/media 内容去重（不能读 openpyxl 图片流判断，读后 save 会崩）
        import io
        from openpyxl import load_workbook
        from ..services.print_excel import _copy_images, xlsx_media_bytes

        old_path = tpl_path(tpl.id)
        if old_path.exists():
            old_wb = load_workbook(old_path)
            if old_wb.active._images:
                new_wb = load_workbook(io.BytesIO(data))
                _copy_images(old_wb.active, new_wb.active, skip=xlsx_media_bytes(data))
                buf = io.BytesIO()
                new_wb.save(buf)
                data = buf.getvalue()
    except Exception as e:
        raise HTTPException(400, f"表格数据无法转换为 xlsx：{e}")
    tpl.kind = "excel"
    tpl_path(tpl.id).write_bytes(data)
    cfg = dict(tpl.config_json or {})
    cfg.update({"orig_name": f"{tpl.name}.xlsx",
                "uploaded_at": datetime.now().isoformat(timespec="seconds")})
    tpl.config_json = cfg
    db.commit()
    return _out(db, tpl)


@router.get("/{tpl_id}/excel")
def download_excel(tpl_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """下载当前已上传的 xlsx 模板（继续编辑用）。"""
    tpl, _ = _get_tpl_access(db, tpl_id, user)
    path = tpl_path(tpl.id)
    if not path.exists():
        raise HTTPException(404, "该模板还没有上传 xlsx 文件")
    name = (tpl.config_json or {}).get("orig_name") or f"{tpl.name}.xlsx"
    return _download(path.read_bytes(), name)


@router.get("/{tpl_id}/excel-images")
def get_excel_images(tpl_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """编辑器载入模板时的图片注入。luckyexcel 解析不了 openpyxl 写出的 drawing
    （元素无 xdr: 前缀，且 rels 用绝对路径），图片+位置（luckysheet 像素坐标，
    与 sheets_to_xlsx 写入时同一口径）由后端直接给前端注入编辑器。"""
    tpl, _ = _get_tpl_access(db, tpl_id, user)
    path = tpl_path(tpl.id)
    if not path.exists():
        return {"images": []}
    from openpyxl import load_workbook

    from ..services.luckysheet_xlsx import extract_images
    try:
        return {"images": extract_images(load_workbook(path).active)}
    except Exception:
        return {"images": []}   # 图片读取失败不阻塞模板编辑


@router.get("/{tpl_id}/fill")
def fill_excel(tpl_id: int, filters: str | None = None, sort_by: str | None = None,
               sort_order: str | None = None, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """填充打印：与列表同口径（filters/sort 同参）取记录，每条记录一个工作表，返回 xlsx。"""
    tpl, access = _get_tpl_access(db, tpl_id, user)
    path = tpl_path(tpl.id)
    if not path.exists():
        raise HTTPException(400, "该模板还没有 xlsx 文件，请先在模板编辑器中保存")
    res = dyn_engine.list_records(
        db, tpl.table_id, 1, MAX_FILL_RECORDS, _parse_filters(filters),
        sort_by or "id", sort_order or "asc", page_cap=MAX_FILL_RECORDS,
    )
    if not res["items"]:
        raise HTTPException(400, "当前筛选结果为空，没有可打印的记录")
    fields = get_meta_fields(db, tpl.table_id)
    data = fill_workbook(path, access.table, fields, res["items"])
    return _download(data, f"{tpl.name}-填充.xlsx")


@router.get("/{tpl_id}/fill-view")
def fill_view(tpl_id: int, filters: str | None = None, sort_by: str | None = None,
              sort_order: str | None = None, paper: str = "a4",
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """填充预览/打印页：与 /fill 同口径，返回 HTML（每条记录一页；paper=a4/half/third 控制分页）。"""
    tpl, access = _get_tpl_access(db, tpl_id, user)
    path = tpl_path(tpl.id)
    if not path.exists():
        raise HTTPException(400, "该模板还没有 xlsx 文件，请先在模板编辑器中保存")
    res = dyn_engine.list_records(
        db, tpl.table_id, 1, MAX_FILL_RECORDS, _parse_filters(filters),
        sort_by or "id", sort_order or "asc", page_cap=MAX_FILL_RECORDS,
    )
    if not res["items"]:
        raise HTTPException(400, "当前筛选结果为空，没有可打印的记录")
    fields = get_meta_fields(db, tpl.table_id)
    if paper not in ("a4", "half", "third"):
        paper = "a4"
    html = render_fill_html(path, access.table, fields, res["items"], title=tpl.name, paper=paper)
    return Response(content=html, media_type="text/html; charset=utf-8")
