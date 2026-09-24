"""图片附件：上传（登录）+ 读取（登录，支持 ?token= 供 <img> 直接引用）。"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..services import images
from ..utils.auth import get_current_user

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.post("/image")
async def upload_image(files: list[UploadFile], db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    """上传图片（JPG/PNG/WebP，单张 ≤5MB，单次 ≤5 张），返回 file_id 列表。"""
    if not files:
        raise HTTPException(400, "没有收到文件")
    if len(files) > images.MAX_PER_UPLOAD:
        raise HTTPException(400, f"单次最多上传 {images.MAX_PER_UPLOAD} 张")
    out = []
    try:
        for f in files:
            row = await images.save_image(db, f, user.id)
            out.append({"id": row.id, "filename": row.filename, "size": row.size, "mime": row.mime})
    except images.ImageError as e:
        raise HTTPException(400, str(e))
    return {"files": out}


@router.get("/image/{file_id}")
def read_image(file_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        row, path = images.get_image(db, file_id)
    except images.ImageError as e:
        raise HTTPException(404, str(e))
    return FileResponse(path, media_type=row.mime or "image/jpeg", filename=row.filename or "image")
