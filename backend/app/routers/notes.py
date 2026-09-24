"""记事本：页面树 + 块模型内容的 CRUD。严格私有（admin 也不可见他人笔记）。"""
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Note, User
from ..utils.auth import get_current_user

router = APIRouter(prefix="/api/notes", tags=["notes"])

MAX_DEPTH = 3            # 页面最多 3 层嵌套（顶级为第 1 层）
MAX_BLOCKS = 500         # 单页块数上限
MAX_BLOCK_TEXT = 10000   # 单块文本上限
_TAG_RE = re.compile(r"<[^>]+>")


class NoteIn(BaseModel):
    title: str | None = None
    blocks: list[dict] | None = None
    pinned: bool | None = None
    parent_id: int | None = None
    sort: int | None = None


def _get_own(db: Session, note_id: int, user: User) -> Note:
    n = db.get(Note, note_id)
    if not n or n.user_id != user.id:
        raise HTTPException(404, "页面不存在")
    return n


def _plain(text: str) -> str:
    """Editor.js 的 text 含 <b>/<i> 等行内标签，剥离后用于搜索与摘要。"""
    return _TAG_RE.sub("", text or "")


def _block_texts(blocks: list) -> list[str]:
    """提取每个块的纯文本。list v2 是嵌套的 {content, items}，checklist 是 {text}，code 用 code 字段。"""
    out = []

    def walk_items(items):
        for it in items:
            if isinstance(it, dict):
                out.append(_plain(str(it.get("text") or it.get("content") or "")))
                if isinstance(it.get("items"), list):
                    walk_items(it["items"])
            else:
                out.append(_plain(str(it)))

    for b in blocks or []:
        data = b.get("data") or {}
        if isinstance(data.get("items"), list):
            walk_items(data["items"])
        else:
            # paragraph/header/quote 用 text；code 用 code；toggle 折叠块有 text+content
            for k in ("text", "content", "code"):
                if data.get(k):
                    out.append(_plain(str(data[k])))
    return out


def _preview(blocks: list, limit: int = 60) -> str:
    for t in _block_texts(blocks):
        t = t.strip()
        if t:
            return t[:limit]
    return ""


def _validate_blocks(blocks: list) -> list:
    if len(blocks) > MAX_BLOCKS:
        raise HTTPException(400, f"单页最多 {MAX_BLOCKS} 个块")
    for t in _block_texts(blocks):
        if len(t) > MAX_BLOCK_TEXT:
            raise HTTPException(400, f"单个块文本不能超过 {MAX_BLOCK_TEXT} 字")
    return blocks


def _depth(db: Session, note: Note, user: User) -> int:
    """页面层级深度（顶级 = 1）。"""
    d, cur = 1, note
    while cur.parent_id and d <= MAX_DEPTH + 1:
        cur = db.get(Note, cur.parent_id)
        if not cur or cur.user_id != user.id:
            break
        d += 1
    return d


def _out(n: Note, with_blocks: bool = False) -> dict:
    d = {
        "id": n.id, "parent_id": n.parent_id, "title": n.title or "",
        "pinned": n.pinned, "sort": n.sort or 0,
        "preview": _preview(n.blocks_json),
        "created_at": n.created_at.isoformat(sep=" ", timespec="seconds") if n.created_at else None,
        "updated_at": n.updated_at.isoformat(sep=" ", timespec="seconds") if n.updated_at else None,
    }
    if with_blocks:
        d["blocks"] = n.blocks_json or []
    return d


@router.get("/tree")
def note_tree(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """全部页面（扁平列表，前端组装树）：置顶在前，其余按同级 sort + 更新时间排序。"""
    rows = (
        db.query(Note).filter(Note.user_id == user.id)
        .order_by(Note.pinned.desc(), Note.sort.asc(), Note.updated_at.desc())
        .all()
    )
    return {"notes": [_out(n) for n in rows]}


@router.get("/search")
def search_notes(keyword: str = Query("", max_length=100), db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    kw = (keyword or "").strip()
    if not kw:
        return {"notes": []}
    rows = (
        db.query(Note).filter(Note.user_id == user.id)
        .order_by(Note.pinned.desc(), Note.updated_at.desc())
        .all()
    )
    # 标题 + 全部块文本模糊匹配（笔记量级小，内存过滤足够）
    hit = [n for n in rows if kw.lower() in (n.title or "").lower()
           or kw.lower() in " ".join(_block_texts(n.blocks_json)).lower()]
    return {"notes": [_out(n) for n in hit[:50]]}


@router.post("")
def create_note(payload: NoteIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    parent = None
    if payload.parent_id:
        parent = _get_own(db, payload.parent_id, user)
        if _depth(db, parent, user) >= MAX_DEPTH:
            raise HTTPException(400, f"页面最多嵌套 {MAX_DEPTH} 层")
    n = Note(
        user_id=user.id,
        parent_id=parent.id if parent else None,
        title=(payload.title or "")[:200],
        blocks_json=[],
        sort=0,
    )
    db.add(n)
    db.commit()
    return _out(n, with_blocks=True)


@router.get("/{note_id}")
def get_note(note_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _out(_get_own(db, note_id, user), with_blocks=True)


@router.put("/{note_id}")
def update_note(note_id: int, payload: NoteIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = _get_own(db, note_id, user)
    if payload.title is not None:
        n.title = payload.title[:200]
    if payload.blocks is not None:
        n.blocks_json = _validate_blocks(payload.blocks)
    if payload.pinned is not None:
        n.pinned = payload.pinned
    if payload.sort is not None:
        n.sort = payload.sort
    if "parent_id" in payload.model_fields_set:  # 显式传 null = 移回顶级
        if payload.parent_id is None:
            n.parent_id = None
        else:
            if payload.parent_id == n.id:
                raise HTTPException(400, "不能把页面移到自己下面")
            parent = _get_own(db, payload.parent_id, user)
            # 不能移到自己的子孙页下面（成环）
            cur, guard = parent, 0
            while cur and guard <= MAX_DEPTH + 2:
                if cur.id == n.id:
                    raise HTTPException(400, "不能把页面移到自己的子页面下面")
                cur = db.get(Note, cur.parent_id) if cur.parent_id else None
                guard += 1
            if _depth(db, parent, user) >= MAX_DEPTH:
                raise HTTPException(400, f"页面最多嵌套 {MAX_DEPTH} 层")
            n.parent_id = parent.id
    db.commit()
    return _out(n, with_blocks=True)


@router.delete("/{note_id}")
def delete_note(note_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = _get_own(db, note_id, user)
    has_child = db.query(Note).filter(Note.parent_id == n.id, Note.user_id == user.id).first()
    if has_child:
        raise HTTPException(400, "请先删除或移走该页面的子页面")
    db.delete(n)
    db.commit()
    return {"ok": True}


# ---------- AI 写作（空块空格唤起） ----------

class NoteAiIn(BaseModel):
    instruction: str
    note_title: str = ""
    context: list[str] = []   # 现有块的纯文本（前端提取，最多取后 20 条）


def _clean_ai_blocks(raw) -> list[dict]:
    """模型输出的块白名单清洗：五种类型、形状归一、超限截断。"""
    out = []
    for b in (raw or [])[:30]:
        if not isinstance(b, dict):
            continue
        t, d = b.get("type"), b.get("data") or {}
        text = str(d.get("text") or "")[:MAX_BLOCK_TEXT]
        if t == "paragraph":
            out.append({"type": t, "data": {"text": text}})
        elif t == "header":
            try:
                level = min(max(int(d.get("level") or 2), 1), 3)
            except (TypeError, ValueError):
                level = 2
            out.append({"type": t, "data": {"text": text, "level": level}})
        elif t == "list":
            style = "ordered" if d.get("style") == "ordered" else "unordered"
            items = []
            for i in (d.get("items") or [])[:50]:
                content = str((i.get("content") or i.get("text") or "") if isinstance(i, dict) else i)[:1000]
                items.append({"content": content, "items": []})
            if items:
                out.append({"type": t, "data": {"style": style, "items": items}})
        elif t == "checklist":
            items = []
            for i in (d.get("items") or [])[:50]:
                if isinstance(i, dict):
                    items.append({"text": str(i.get("text") or "")[:1000], "checked": bool(i.get("checked"))})
                else:
                    items.append({"text": str(i)[:1000], "checked": False})
            if items:
                out.append({"type": t, "data": {"items": items}})
        elif t == "quote":
            out.append({"type": t, "data": {"text": text, "alignment": "left"}})
    return out


@router.post("/ai-assist")
def note_ai_assist(payload: NoteAiIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """AI 写作：按指令生成 Editor.js 块数组（前端插入当前块位置）。"""
    from datetime import datetime

    from ..services.llm import LLMError
    from ..services.llm.gateway import extract_json, get_default_provider
    from ..services.llm.prompts import NOTE_AI_SYSTEM, build_note_ai_prompt

    instruction = (payload.instruction or "").strip()
    if not instruction:
        raise HTTPException(400, "请输入要生成的内容描述")
    provider = get_default_provider(db)
    prompt = build_note_ai_prompt(instruction[:2000], (payload.note_title or "")[:200],
                                  [str(t)[:500] for t in (payload.context or [])[-20:]],
                                  datetime.now().strftime("%Y-%m-%d"))
    last_err: Exception | None = None
    for attempt in range(2):
        current_prompt = prompt if attempt == 0 else (
            f"你上次的输出无法解析为合法 JSON，错误：{last_err}。请重新输出，只输出 JSON。\n\n原始任务：\n" + prompt
        )
        try:
            data = extract_json(provider.complete(current_prompt, system=NOTE_AI_SYSTEM))
            blocks = _clean_ai_blocks(data.get("blocks"))
            if not blocks:
                raise ValueError("输出没有可用的块")
            return {"blocks": blocks}
        except LLMError:
            raise
        except Exception as e:  # noqa: BLE001 — 解析失败重试一次
            last_err = e
    raise HTTPException(400, f"模型输出解析失败：{last_err}")
