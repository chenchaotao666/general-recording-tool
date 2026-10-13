"""画板：页面树 + 画布 JSON 内容的 CRUD。严格私有（admin 也不可见他人画板），与记事本一致。

content 为画布的序列化 JSON 字符串，服务端只做长度与 JSON 合法性校验，
不做内容清洗（纯 JSON 无 HTML 注入面）。多引擎：excalidraw 存其序列化 JSON；
drawio 存 {"xml": "<mxfile...>"}（iframe embed 协议收发，XML 包在 JSON 里过同一道校验）。
"""
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Whiteboard
from ..utils.auth import get_current_user

router = APIRouter(prefix="/api/whiteboards", tags=["whiteboards"])

MAX_DEPTH = 3                 # 页面最多 3 层嵌套（顶级为第 1 层）
MAX_CONTENT = 2_000_000       # 单页画布 JSON 长度上限（含内嵌图片 base64，给足余量）
ENGINES = {"excalidraw", "drawio"}


class WhiteboardIn(BaseModel):
    title: str | None = None
    content: str | None = None      # 画布序列化 JSON 字符串
    engine: str | None = None       # 仅创建时有效
    pinned: bool | None = None
    parent_id: int | None = None
    sort: int | None = None


def _clean_content(raw: str) -> str:
    """画布内容校验：长度上限 + 必须是合法 JSON（存的是结构化数据，不接受裸文本）。"""
    if len(raw or "") > MAX_CONTENT:
        raise HTTPException(400, f"画布内容过大，最多 {MAX_CONTENT} 字符")
    try:
        json.loads(raw or '""')
    except json.JSONDecodeError:
        raise HTTPException(400, "画布内容不是合法 JSON") from None
    return raw


def _get_own(db: Session, wb_id: int, user: User) -> Whiteboard:
    w = db.get(Whiteboard, wb_id)
    if not w or w.user_id != user.id:
        raise HTTPException(404, "画板不存在")
    return w


def _depth(db: Session, wb: Whiteboard, user: User) -> int:
    """页面层级深度（顶级 = 1）。"""
    d, cur = 1, wb
    while cur.parent_id and d <= MAX_DEPTH + 1:
        cur = db.get(Whiteboard, cur.parent_id)
        if not cur or cur.user_id != user.id:
            break
        d += 1
    return d


def _out(w: Whiteboard, with_content: bool = False) -> dict:
    d = {
        "id": w.id, "parent_id": w.parent_id, "title": w.title or "",
        "engine": w.engine or "excalidraw",
        "pinned": w.pinned, "sort": w.sort or 0,
        "content_size": len(w.content_json or ""),
        "created_at": w.created_at.isoformat(sep=" ", timespec="seconds") if w.created_at else None,
        "updated_at": w.updated_at.isoformat(sep=" ", timespec="seconds") if w.updated_at else None,
    }
    if with_content:
        d["content"] = w.content_json or ""
    return d


@router.get("/tree")
def whiteboard_tree(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """全部画板（扁平列表，前端组装树）：置顶在前，其余按同级 sort + 更新时间排序。"""
    rows = (
        db.query(Whiteboard).filter(Whiteboard.user_id == user.id)
        .order_by(Whiteboard.pinned.desc(), Whiteboard.sort.asc(), Whiteboard.updated_at.desc())
        .all()
    )
    return {"whiteboards": [_out(w) for w in rows]}


@router.get("/search")
def search_whiteboards(keyword: str = Query("", max_length=100), db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    """标题模糊匹配（画布是 JSON，不做正文匹配）。"""
    kw = (keyword or "").strip()
    if not kw:
        return {"whiteboards": []}
    rows = (
        db.query(Whiteboard).filter(Whiteboard.user_id == user.id)
        .order_by(Whiteboard.pinned.desc(), Whiteboard.updated_at.desc())
        .all()
    )
    hit = [w for w in rows if kw.lower() in (w.title or "").lower()]
    return {"whiteboards": [_out(w) for w in hit[:50]]}


@router.post("")
def create_whiteboard(payload: WhiteboardIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    engine = (payload.engine or "excalidraw").lower()
    if engine not in ENGINES:
        raise HTTPException(400, f"不支持的画板引擎：{engine}")
    parent = None
    if payload.parent_id:
        parent = _get_own(db, payload.parent_id, user)
        if _depth(db, parent, user) >= MAX_DEPTH:
            raise HTTPException(400, f"画板最多嵌套 {MAX_DEPTH} 层")
    w = Whiteboard(
        user_id=user.id,
        parent_id=parent.id if parent else None,
        title=(payload.title or "")[:200],
        engine=engine,
        content_json="",
        sort=0,
    )
    db.add(w)
    db.commit()
    return _out(w, with_content=True)


class GenerateIn(BaseModel):
    description: str
    # auto=模型判断；replace/append/modify/summarize=用户指定。context=当前画布元素概要（修改/汇总/追加用）
    mode: Literal["auto", "replace", "append", "modify", "summarize"] = "auto"
    context: list[dict] | None = None
    images: list[str] | None = None   # 附图（截图/照片）data URL，非空走视觉模型


@router.post("/generate-content")
def generate_content_api(payload: GenerateIn, db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    """AI 画板操作：替换/追加/修改返回内容（结构图 nodes/edges，绘画 elements，组件如表格），
    汇总返回文字；支持附图识别。注意注册在 /{wb_id} 之前：Starlette 只按路径模板匹配。"""
    from ..services.llm import LLMError
    from ..services.llm.gateway import generate_board_content
    try:
        return generate_board_content(db, payload.description, payload.mode, payload.context, payload.images)
    except LLMError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/{wb_id}")
def get_whiteboard(wb_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _out(_get_own(db, wb_id, user), with_content=True)


@router.put("/{wb_id}")
def update_whiteboard(wb_id: int, payload: WhiteboardIn, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    w = _get_own(db, wb_id, user)
    if payload.title is not None:
        w.title = payload.title[:200]
    if payload.content is not None:
        w.content_json = _clean_content(payload.content)
    if payload.pinned is not None:
        w.pinned = payload.pinned
    if payload.sort is not None:
        w.sort = payload.sort
    if "parent_id" in payload.model_fields_set:  # 显式传 null = 移回顶级
        if payload.parent_id is None:
            w.parent_id = None
        else:
            if payload.parent_id == w.id:
                raise HTTPException(400, "不能把画板移到自己下面")
            parent = _get_own(db, payload.parent_id, user)
            # 不能移到自己的子孙页下面（成环）
            cur, guard = parent, 0
            while cur and guard <= MAX_DEPTH + 2:
                if cur.id == w.id:
                    raise HTTPException(400, "不能把画板移到自己的子页面下面")
                cur = db.get(Whiteboard, cur.parent_id) if cur.parent_id else None
                guard += 1
            if _depth(db, parent, user) >= MAX_DEPTH:
                raise HTTPException(400, f"画板最多嵌套 {MAX_DEPTH} 层")
            w.parent_id = parent.id
    db.commit()
    return _out(w, with_content=True)


@router.delete("/{wb_id}")
def delete_whiteboard(wb_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    w = _get_own(db, wb_id, user)
    has_child = db.query(Whiteboard).filter(Whiteboard.parent_id == w.id, Whiteboard.user_id == user.id).first()
    if has_child:
        raise HTTPException(400, "请先删除或移走该画板的子页面")
    db.delete(w)
    db.commit()
    return {"ok": True}
