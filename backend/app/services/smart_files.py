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


def recent(table_id: int, uploader_id: int, limit: int = 30) -> list[dict]:
    """只返回本人在当前表上传的附件，不扩展其他记录的可见范围。"""
    found = []
    for folder in _root().iterdir():
        if not folder.is_dir() or not FILE_ID_RE.fullmatch(folder.name):
            continue
        try:
            path, meta = locate(folder.name)
            if meta.get('table_id') == table_id and meta.get('uploader_id') == uploader_id:
                found.append((path.stat().st_mtime, {"id": folder.name, "name": meta['filename'], "size": meta.get('size', 0)}))
        except (SmartFileError, OSError, ValueError, KeyError):
            continue
    return [item for _, item in sorted(found, key=lambda pair: pair[0], reverse=True)[:limit]]


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


def document_text(file_id: str, max_chars: int = 20000) -> str:
    """Extract text from PDF, DOCX or UTF-8/GB18030 text without executing document content."""
    from zipfile import ZipFile
    from xml.etree import ElementTree
    path, meta = locate(file_id)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return pdf_text(file_id, max_chars)
    if suffix == ".docx":
        with ZipFile(path) as archive:
            members = [i for i in archive.infolist() if i.filename == "word/document.xml" or re.fullmatch(r"word/(header|footer)\d+\.xml", i.filename)]
            if sum(i.file_size for i in members) > 20 * 1024 * 1024:
                raise SmartFileError("DOCX 解压后文本过大")
            parts = []
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            for item in members:
                root = ElementTree.fromstring(archive.read(item))
                parts.extend("".join(t.text or "" for t in p.iter(ns + "t")) for p in root.iter(ns + "p"))
            return "\n".join(parts)[:max_chars]
    if suffix in (".txt", ".csv", ".md", ".json", ".log"):
        data = path.read_bytes()
        try:
            return data.decode("utf-8-sig")[:max_chars]
        except UnicodeDecodeError:
            return data.decode("gb18030")[:max_chars]
    raise SmartFileError(f"暂不支持解析「{meta['filename']}」，请选择 PDF、DOCX 或文本文件")
