"""上传文件的保存与定位（file_id = UUID 目录名，防目录穿越）。"""
import json
import re
import uuid
from pathlib import Path

from fastapi import UploadFile

from ..config import settings

FILE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class UploadNotFound(Exception):
    pass


async def save_upload(file: UploadFile) -> tuple[str, Path]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".xlsx", ".csv"):
        raise ValueError("仅支持 .xlsx / .csv 文件（.xls 请另存为 .xlsx）")
    file_id = uuid.uuid4().hex
    folder = settings.upload_dir / file_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"data{suffix}"
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise ValueError("文件超过 50MB 上限")
    path.write_bytes(content)
    (folder / "meta.json").write_text(
        json.dumps({"filename": file.filename}, ensure_ascii=False), encoding="utf-8"
    )
    return file_id, path


def save_generated(content: bytes, filename: str) -> str:
    """保存 AI 生成的文件（与上传同目录布局，供下载接口按 file_id 取用）。"""
    file_id = uuid.uuid4().hex
    folder = settings.upload_dir / file_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "data.xlsx").write_bytes(content)
    (folder / "meta.json").write_text(
        json.dumps({"filename": filename}, ensure_ascii=False), encoding="utf-8"
    )
    return file_id


def get_upload_path(file_id: str) -> Path:
    if not FILE_ID_RE.match(file_id or ""):
        raise UploadNotFound("非法的文件标识")
    path = settings.upload_dir / file_id / "data.xlsx"
    if not path.exists():
        path = path.with_suffix(".csv")
    if not path.exists():
        raise UploadNotFound("上传文件不存在或已过期，请重新上传")
    return path


def get_upload_filename(file_id: str) -> str:
    meta = settings.upload_dir / file_id / "meta.json"
    if meta.exists():
        try:
            return json.loads(meta.read_text(encoding="utf-8")).get("filename", "")
        except Exception:
            pass
    return ""
