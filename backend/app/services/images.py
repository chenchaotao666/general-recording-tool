"""图片附件：存盘 + 元数据/归属管理 + 级联清理。

文件本体：uploads/images/{file_id}（内容即 JPEG/PNG/WebP 字节）。
归属：写入/更新记录时按 image 字段值回填 table_id/record_id/field_name；
记录删除、字段删除、表删除时级联删除文件；未关联的孤儿文件超期自动清理。
"""
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from ..config import settings
from ..models import ImageFile

MAX_SIZE = 5 * 1024 * 1024          # 单张 5MB（前端已压缩，这里兜底）
MAX_PER_UPLOAD = 5
MAX_PER_FIELD = 5
ORPHAN_TTL_HOURS = 24               # 未关联记录的临时文件保留时长

_MAGIC = {
    b"\xff\xd8\xff": ("jpg", "image/jpeg"),
    b"\x89PNG\r\n\x1a\n": ("png", "image/png"),
    b"RIFF": ("webp", "image/webp"),   # 第 8 字节起为 WEBP，下面单独校验
}


class ImageError(Exception):
    pass


def _sniff(content: bytes) -> tuple[str, str] | None:
    for magic, (ext, mime) in _MAGIC.items():
        if content.startswith(magic):
            if magic == b"RIFF" and content[8:12] != b"WEBP":
                continue
            return ext, mime
    return None


def images_dir() -> Path:
    d = settings.upload_dir / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


async def save_image(db: Session, file: UploadFile, uploader_id: int) -> ImageFile:
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise ImageError("单张图片不能超过 5MB")
    sniffed = _sniff(content)
    if not sniffed:
        raise ImageError("仅支持 JPG / PNG / WebP 图片")
    ext, mime = sniffed
    row = ImageFile(
        id=uuid.uuid4().hex, uploader_id=uploader_id,
        filename=(file.filename or "")[:256], mime=mime, size=len(content),
    )
    (images_dir() / row.id).write_bytes(content)
    db.add(row)
    db.commit()
    return row


def get_image(db: Session, file_id: str) -> tuple[ImageFile, Path]:
    row = db.get(ImageFile, file_id or "")
    if not row:
        raise ImageError("图片不存在")
    path = images_dir() / row.id
    if not path.exists():
        raise ImageError("图片文件已丢失")
    return row, path


def _delete_rows(db: Session, rows: list[ImageFile]) -> int:
    n = 0
    for row in rows:
        try:
            (images_dir() / row.id).unlink(missing_ok=True)
        except OSError:
            pass
        db.delete(row)
        n += 1
    return n


def sync_record_images(db: Session, table_id: int, record_id: int,
                       image_fields: list[str], before: dict, after: dict) -> None:
    """写入/更新记录后调用：新增的图片回填归属，移除的图片级联删除。"""
    for fname in image_fields:
        old_ids = set(before.get(fname) or [])
        new_ids = set(after.get(fname) or [])
        for fid in new_ids - old_ids:
            row = db.get(ImageFile, fid)
            if row:
                row.table_id, row.record_id, row.field_name = table_id, record_id, fname
        removed = db.query(ImageFile).filter(
            ImageFile.table_id == table_id, ImageFile.record_id == record_id,
            ImageFile.field_name == fname, ImageFile.id.in_(old_ids - new_ids),
        ).all() if old_ids - new_ids else []
        _delete_rows(db, removed)
    db.commit()


def delete_record_images(db: Session, record_id: int) -> None:
    rows = db.query(ImageFile).filter_by(record_id=record_id).all()
    _delete_rows(db, rows)


def delete_field_images(db: Session, table_id: int, field_name: str) -> None:
    rows = db.query(ImageFile).filter_by(table_id=table_id, field_name=field_name).all()
    _delete_rows(db, rows)


def delete_table_images(db: Session, table_id: int) -> None:
    rows = db.query(ImageFile).filter_by(table_id=table_id).all()
    _delete_rows(db, rows)


def cleanup_orphans(db: Session) -> int:
    """清理超期未关联记录的临时图片（上传后最终没保存进任何记录）。"""
    deadline = datetime.now() - timedelta(hours=ORPHAN_TTL_HOURS)
    rows = db.query(ImageFile).filter(
        ImageFile.record_id.is_(None), ImageFile.created_at < deadline,
    ).all()
    n = _delete_rows(db, rows)
    if n:
        db.commit()
    return n
