"""智能表「文件」字段附件存储（V3：PDF 转文本等需要非图片附件）。

布局：upload_dir/smart_files/<32位hex>/<原文件名>（file_id 即目录名，防目录穿越）；
单文件 ≤20MB；归属表记录在 meta.json，读取时按表权限校验。
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from ..config import settings

FILE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
MAX_BYTES = 20 * 1024 * 1024
_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


class SmartFileError(ValueError):
    pass


def _root() -> Path:
    p = settings.upload_dir / "smart_files"
    p.mkdir(parents=True, exist_ok=True)
    return p


def save(content: bytes, filename: str, table_id: int | None, uploader_id: int | None) -> dict:
    if len(content) > MAX_BYTES:
        raise SmartFileError("文件超过 20MB 上限")
    name = _BAD_CHARS.sub("_", Path(filename or "file").name)[:120] or "file"
    fid = uuid.uuid4().hex
    folder = _root() / fid
    folder.mkdir(parents=True)
    (folder / name).write_bytes(content)
    (folder / "meta.json").write_text(json.dumps(
        {"filename": name, "table_id": table_id, "uploader_id": uploader_id, "size": len(content)},
        ensure_ascii=False), encoding="utf-8")
    return {"id": fid, "name": name, "size": len(content)}


def locate(file_id: str) -> tuple[Path, dict]:
    if not FILE_ID_RE.match(file_id or ""):
        raise SmartFileError("非法的文件标识")
    folder = _root() / file_id
    meta_p = folder / "meta.json"
    if not meta_p.exists():
        raise SmartFileError("文件不存在")
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    path = folder / meta["filename"]
    if not path.exists():
        raise SmartFileError("文件不存在")
    return path, meta


def pdf_text(file_id: str, max_chars: int = 20000) -> str:
    """PDF → 纯文本（pypdf，可选依赖；未安装时给出明确错误）。"""
    path, meta = locate(file_id)
    if path.suffix.lower() != ".pdf":
        raise SmartFileError(f"「{meta['filename']}」不是 PDF 文件")
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise SmartFileError("服务器未安装 pypdf，无法解析 PDF（pip install pypdf）") from e
    reader = PdfReader(str(path))
    parts = []
    total = 0
    for page in reader.pages:
        t = page.extract_text() or ""
        parts.append(t)
        total += len(t)
        if total >= max_chars:
            break
    return "\n".join(parts).strip()[:max_chars]
