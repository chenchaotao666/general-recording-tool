"""图片附件：上传（登录，存储配额闸）+ 读取（登录 + 归属校验，支持 ?token= 供 <img> 直接引用）。"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..services import images
from ..utils.access import get_table_access
from ..utils.auth import get_current_user
from ..utils.context import Context, get_current_context

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.post("/image")
async def upload_image(files: list[UploadFile], db: Session = Depends(get_db),
                       ctx: Context = Depends(get_current_context)):
    """上传图片（JPG/PNG/WebP，单张 ≤5MB，单次 ≤5 张），返回 file_id 列表。"""
    if not files:
        raise HTTPException(400, "没有收到文件")
    if len(files) > images.MAX_PER_UPLOAD:
        raise HTTPException(400, f"单次最多上传 {images.MAX_PER_UPLOAD} 张")
    out = []
    try:
        for f in files:
            row = await images.save_image(db, f, ctx.user.id, tenant_id=ctx.tenant.id)
            out.append({"id": row.id, "filename": row.filename, "size": row.size, "mime": row.mime})
    except images.ImageError as e:
        raise HTTPException(400, str(e))
    return {"files": out}


@router.get("/image/{file_id}")
def read_image(file_id: str, db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    row, path = _accessible_image(file_id, db, ctx)
    return FileResponse(path, media_type=row.mime or "image/jpeg", filename=row.filename or "image")


def _accessible_image(file_id, db, ctx):
    user = ctx.user
    row, path = None, None
    try:
        row, path = images.get_image(db, file_id)
    except images.ImageError as e:
        raise HTTPException(404, str(e))
    # 归属校验：本人上传，或对图片归属表/笔记有查看权（无权限 404，不泄露存在性）
    if row.uploader_id != user.id:
        if row.note_id:
            from ..models import Note
            note = db.get(Note, row.note_id)
            if not note or note.user_id != user.id or note.tenant_id != ctx.tenant.id:
                raise HTTPException(404, "图片不存在")  # 笔记严格私有，他人不可读
        elif not row.table_id:
            raise HTTPException(404, "图片不存在")
        else:
            get_table_access(db, row.table_id, user)
    return row, path


@router.get("/image/{file_id}/meta")
def image_meta(file_id: str, db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    row, _ = _accessible_image(file_id, db, ctx)
    return {"id": row.id, "filename": row.filename, "size": row.size, "mime": row.mime}


class ImageName(BaseModel):
    filename: str = Field(min_length=1, max_length=255)


@router.patch("/image/{file_id}/meta")
def rename_image(file_id: str, body: ImageName, db: Session = Depends(get_db),
                 ctx: Context = Depends(get_current_context)):
    row, _ = _accessible_image(file_id, db, ctx)
    if row.table_id:
        access = get_table_access(db, row.table_id, ctx.user, ctx)
        if not access.can_edit:
            raise HTTPException(403, "没有编辑图片的权限")
        if access.table.storage_mode == "json":
            from .smart_records import _effective, _normalized_one, _require_row_editable, get_meta_fields, perm_service
            fields = get_meta_fields(db, row.table_id)
            eff = _effective(db, access)
            if not eff.managed:
                perm_service.require_level(eff, "EDIT", "没有编辑记录的权限")
                _require_row_editable(eff, _normalized_one(db, row.table_id, row.record_id, fields), fields)
                if not eff.field_rights_map(fields).get(row.field_name, {}).get("edit"):
                    raise HTTPException(403, "没有编辑图片字段的权限")
    elif row.uploader_id != ctx.user.id:
        raise HTTPException(403, "没有编辑图片的权限")
    name = body.filename.strip()
    if not name or any(c in name for c in '/\\\r\n\x00'):
        raise HTTPException(422, "图片名称不能为空或包含路径字符")
    original = row.filename or ''
    suffix = original[original.rfind('.'):] if original.rfind('.') > 0 else ''
    if suffix and (not name.endswith(suffix) or not name[:-len(suffix)].strip()):
        raise HTTPException(422, "重命名不能修改图片后缀")
    row.filename = name
    db.commit()
    return {"id": row.id, "filename": row.filename}
