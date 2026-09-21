"""图片识别填表：上传图片 -> 多模态 LLM 识别 -> 返回字段建议（用户确认后才落入表单）。"""
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import VisionLog
from ..services.image import MAX_IMAGES, ImageError, compress_image
from ..services.llm import LLMError, recognize_form
from ..services.meta_service import get_meta_fields, get_meta_table

router = APIRouter(prefix="/api/vision", tags=["vision"])


class AdoptIn(BaseModel):
    adopted: list[str]


@router.post("/recognize")
async def recognize(
    table_id: int = Form(...),
    current: str = Form("{}"),
    record_id: int | None = Form(None),
    images: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    mt = get_meta_table(db, table_id)
    if not mt:
        raise HTTPException(404, "数据表不存在")
    if not images:
        raise HTTPException(400, "请至少上传一张图片")
    if len(images) > MAX_IMAGES:
        raise HTTPException(400, f"一次最多识别 {MAX_IMAGES} 张图片")

    try:
        current_values = json.loads(current) if current else {}
    except json.JSONDecodeError:
        raise HTTPException(400, "current 参数必须是 JSON")

    # 压缩 + 落盘留痕
    compressed, paths = [], []
    vision_dir = settings.upload_dir / "vision"
    vision_dir.mkdir(parents=True, exist_ok=True)
    for img in images:
        data = await img.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(400, f"图片 {img.filename} 超过 20MB 上限")
        try:
            data = compress_image(data)
        except ImageError as e:
            raise HTTPException(400, f"图片 {img.filename}：{e}")
        compressed.append(data)
        rel = Path("vision") / f"{uuid.uuid4().hex}.jpg"
        (settings.upload_dir / rel).write_bytes(data)
        paths.append(str(rel))

    fields = get_meta_fields(db, table_id)
    try:
        result, raw = recognize_form(db, compressed, fields, current_values)
    except LLMError as e:
        raise HTTPException(400, str(e))

    log = VisionLog(
        table_id=table_id, record_id=record_id,
        image_paths=paths, raw_response=raw[:8000],
    )
    db.add(log)
    db.commit()

    return {**result, "log_id": log.id}


@router.put("/logs/{log_id}/adopt")
def adopt(log_id: int, payload: AdoptIn, db: Session = Depends(get_db)):
    """用户确认后回传采纳了哪些字段，补全留痕。"""
    log = db.get(VisionLog, log_id)
    if not log:
        raise HTTPException(404, "识别记录不存在")
    log.adopted_fields = payload.adopted
    db.commit()
    return {"ok": True}
