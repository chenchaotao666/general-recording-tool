"""图片附件：存盘 + 元数据/归属管理 + 级联清理。

文件本体：uploads/images/{file_id}（内容即 JPEG/PNG/WebP 字节）。
归属：写入/更新记录时按 image 字段值回填 table_id/record_id/field_name；
记录删除、字段删除、表删除时级联删除文件；未关联的孤儿文件超期自动清理。
"""
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from ..config import settings
from ..models import ImageFile, MetaTable, MetaField, Record, User

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


async def save_image(db: Session, file: UploadFile, uploader_id: int,
                     tenant_id: int | None = None) -> ImageFile:
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise ImageError("单张图片不能超过 5MB")
    sniffed = _sniff(content)
    if not sniffed:
        raise ImageError("仅支持 JPG / PNG / WebP 图片")
    ext, mime = sniffed
    # 存储配额闸（宽限期模型）+ 只读闸
    from . import entitlement
    entitlement.assert_tenant_writable(db, tenant_id)
    entitlement.check_quota(db, tenant_id, "max_storage_mb", delta=len(content))
    row = ImageFile(
        id=uuid.uuid4().hex, uploader_id=uploader_id,
        filename=(file.filename or "")[:256], mime=mime, size=len(content),
    )
    (images_dir() / row.id).write_bytes(content)
    db.add(row)
    entitlement.bump_usage(db, tenant_id, "storage_bytes", len(content))
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


def _tenant_of_image(db: Session, row: ImageFile) -> int | None:
    """图片归属租户：已关联记录 → 表租户；孤儿文件 → 上传者默认工作空间（与校准口径一致）。"""
    if row.table_id:
        mt = db.get(MetaTable, row.table_id)
        if mt:
            return mt.tenant_id
    if row.uploader_id:
        u = db.get(User, row.uploader_id)
        if u:
            try:
                from .tenancy import default_tenant_id
                return default_tenant_id(db, u)
            except Exception:  # noqa: BLE001
                return None
    return None


def _smart_references(db: Session) -> dict:
    """以实际单元格为准；一个附件可以被多条记录/多个字段引用。"""
    db.flush()
    fields = {}
    for tid, name in db.query(MetaField.table_id, MetaField.field_name).join(
        MetaTable, MetaTable.id == MetaField.table_id
    ).filter(MetaTable.storage_mode == "json", MetaField.field_type == "image"):
        fields.setdefault(tid, []).append(name)
    refs = {}
    if fields:
        for rec in db.query(Record).filter(Record.table_id.in_(fields)):
            for name in fields[rec.table_id]:
                for fid in (rec.data or {}).get(name) or []:
                    if isinstance(fid, str):
                        refs.setdefault(fid, (rec.table_id, rec.id, name))
    return refs


def sync_smart_images(db: Session) -> None:
    """在调用方事务内同步归属；最后一个引用移除后保留 24 小时供撤销。"""
    refs = _smart_references(db)
    smart_tables = {tid for (tid,) in db.query(MetaTable.id).filter(MetaTable.storage_mode == "json")}
    for row in db.query(ImageFile):
        if row.id in refs:
            row.table_id, row.record_id, row.field_name = refs[row.id]
        elif row.table_id in smart_tables and row.record_id is not None:
            # 保留表归属，供宽限期访问校验和清理时扣减正确租户的存储用量。
            row.record_id = row.field_name = None
            row.created_at = datetime.now()


def _delete_rows(db: Session, rows: list[ImageFile]) -> int:
    from . import entitlement
    n = 0
    refs = _smart_references(db)
    for row in rows:
        if row.id in refs:
            row.table_id, row.record_id, row.field_name = refs[row.id]
            continue
        try:
            (images_dir() / row.id).unlink(missing_ok=True)
        except OSError:
            pass
        tid = _tenant_of_image(db, row)
        db.delete(row)
        if tid and row.size:
            entitlement.bump_usage(db, tid, "storage_bytes", -row.size)
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
    mt = db.get(MetaTable, table_id)
    if mt and mt.storage_mode == "json":
        # 调用方已移除记录；仅解绑，提交失败时文件仍然可用。
        sync_smart_images(db)
        return
    rows = db.query(ImageFile).filter_by(table_id=table_id).all()
    _delete_rows(db, rows)


# ---------- 记事本插图 ----------

_NOTE_IMG_RE = re.compile(r"/api/uploads/image/([a-f0-9]{32})")


def sync_note_images(db: Session, note_id: int, content_html: str, uploader_id: int | None = None) -> None:
    """笔记保存后调用：HTML 里引用的图片回填 note_id；从笔记移除的图片级联删除。
    只认领本人上传的图片（防止引用他人图片 id 抢占归属）。"""
    used = set(_NOTE_IMG_RE.findall(content_html or ""))
    for fid in used:
        row = db.get(ImageFile, fid)
        if not row or row.note_id == note_id or row.record_id:
            continue
        if uploader_id is not None and row.uploader_id != uploader_id:
            continue
        row.note_id = note_id
    removed = db.query(ImageFile).filter(
        ImageFile.note_id == note_id, ~ImageFile.id.in_(used),
    ).all()
    _delete_rows(db, removed)
    db.commit()


def delete_note_images(db: Session, note_id: int) -> None:
    rows = db.query(ImageFile).filter_by(note_id=note_id).all()
    _delete_rows(db, rows)


def cleanup_orphans(db: Session) -> int:
    """清理超期未关联记录/笔记的临时图片（上传后最终没保存进任何地方）。"""
    # 先修复历史智能表归属，防止已使用的旧图片被当作孤儿删除。
    sync_smart_images(db)
    # 已删除的表也不能留下永久归属。
    table_ids = {tid for (tid,) in db.query(MetaTable.id)}
    for row in db.query(ImageFile).filter(ImageFile.table_id.isnot(None)):
        if row.table_id not in table_ids:
            row.table_id = row.record_id = row.field_name = None
    db.flush()
    deadline = datetime.now() - timedelta(hours=ORPHAN_TTL_HOURS)
    rows = db.query(ImageFile).filter(
        ImageFile.record_id.is_(None), ImageFile.note_id.is_(None),
        ImageFile.created_at < deadline,
    ).all()
    n = _delete_rows(db, rows)
    db.commit()
    return n
