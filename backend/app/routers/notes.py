"""记事本：页面树 + 富文本 HTML 内容的 CRUD。严格私有（admin 也不可见他人笔记）。

内容安全：所有写入（手工保存 / AI 生成）都过 _clean_html 白名单清洗，
只放行排版标签与少量属性（tiptap 待办列表的 data-* / checkbox），
href 仅允许 http(s)/mailto，彻底挡住 script/on* 注入。
"""
import html as _html
import re
from html.parser import HTMLParser

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Note, User
from ..utils.auth import get_current_user

router = APIRouter(prefix="/api/notes", tags=["notes"])

MAX_DEPTH = 3             # 页面最多 3 层嵌套（顶级为第 1 层）
MAX_CONTENT = 200_000     # 单页 HTML 长度上限
_TAG_RE = re.compile(r"<[^>]+>")

# 标签白名单：排版 + 列表 + 待办（tiptap taskList 结构 ul/li[data-type] > label > input + div；
# wangEditor 待办结构 div[data-w-e-type="todo"] > input）+ 表格 + 图片
_ALLOWED = {
    "p": {"style"}, "h1": {"style"}, "h2": {"style"}, "h3": {"style"},
    "ul": {"data-type"}, "ol": set(), "li": {"data-type", "data-checked", "style"},
    "blockquote": {"style"}, "pre": set(), "code": {"class"},
    "strong": set(), "b": set(), "em": set(), "i": set(), "u": set(), "s": set(), "del": set(),
    "br": set(), "hr": set(), "span": {"style"}, "div": {"data-w-e-type"}, "label": set(),
    "a": {"href", "target", "rel"},
    "input": {"type", "checked", "disabled"},
    "table": {"style"}, "tbody": set(), "thead": set(), "tr": set(),
    "td": {"colspan", "rowspan", "width", "style"}, "th": {"colspan", "rowspan", "width", "style"},
    "img": {"src", "alt", "style", "data-href"},   # data-href = 图片点击跳转链接（wangEditor 网络图片的「图片链接」）
}
_VOID = {"br", "hr", "input", "img"}
_DROP = {"script", "style", "iframe", "object", "embed"}   # 连内容一起丢弃的标签
_HREF_RE = re.compile(r"^(https?://|mailto:)", re.I)
# 裸域名（www.baidu.com / baidu.com/path）：用户常省略协议，清洗时补 https:// 而不是丢弃
_DOMAIN_RE = re.compile(r"^[\w\-]+(\.[\w\-]+)+(/[^\s]*)?$", re.I)
# 图片 src：本站上传接口或 http(s) 外链
_IMG_SRC_RE = re.compile(r"^(/api/uploads/|https?://)", re.I)
# style 属性按声明过滤：每个属性单独校验值形态，不放行的一律丢弃
_STYLE_VALUE_RE = {
    "color": re.compile(r"^(#[0-9a-f]{3,8}|rgba?\([\d\s.,%]+\)|[a-zA-Z]+)$", re.I),
    "background-color": re.compile(r"^(#[0-9a-f]{3,8}|rgba?\([\d\s.,%]+\)|[a-zA-Z]+)$", re.I),
    "font-family": re.compile(r"^[\w　-鿿\s,\"'\-.]+$"),
    "font-size": re.compile(r"^\d+(\.\d+)?(px|em|rem|%)$", re.I),
    "text-align": re.compile(r"^(left|center|right|justify)$", re.I),
    "text-indent": re.compile(r"^\d+(\.\d+)?(em|px)$", re.I),
    "width": re.compile(r"^(\d+(\.\d+)?(px|%)|auto)$", re.I),
    "height": re.compile(r"^(\d+(\.\d+)?(px|%)|auto)$", re.I),
}


def _filter_style(value: str) -> str:
    """style 属性白名单过滤：只保留值形态合法的声明（颜色/字体/字号/对齐/缩进/宽高）。"""
    kept = []
    for decl in (value or "").split(";"):
        decl = decl.strip()
        prop, sep, val = decl.partition(":")
        if not sep:
            continue
        pattern = _STYLE_VALUE_RE.get(prop.strip().lower())
        if pattern and pattern.match(val.strip()):
            kept.append(f"{prop.strip().lower()}: {val.strip()}")
    return "; ".join(kept)


class _Sanitizer(HTMLParser):
    """白名单 HTML 清洗：标签/属性不在 _ALLOWED 的一律丢弃，文本转义后重新序列化。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._drop_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _DROP:
            self._drop_depth += 1
            return
        if self._drop_depth or tag not in _ALLOWED:
            return
        kept = []
        for k, v in attrs:
            k, v = k.lower(), v or ""
            if k not in _ALLOWED[tag]:
                continue
            if k in ("href", "data-href"):
                v = v.strip()
                if _HREF_RE.match(v):
                    pass
                elif _DOMAIN_RE.match(v):
                    v = "https://" + v   # 裸域名补协议，避免被浏览器当站内相对路径
                else:
                    continue
            if k == "src" and not _IMG_SRC_RE.match(v):
                continue
            if k == "style":
                v = _filter_style(v)
                if not v:
                    continue
            kept.append(f'{k}="{_html.escape(v, quote=True)}"')
        self.parts.append("<" + tag + (" " + " ".join(kept) if kept else "") + ">")

    def handle_startendtag(self, tag, attrs):
        if tag.lower() in _DROP:
            return
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _DROP:
            self._drop_depth = max(0, self._drop_depth - 1)
            return
        if self._drop_depth:
            return
        if tag in _ALLOWED and tag not in _VOID:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if self._drop_depth:
            return
        self.parts.append(_html.escape(data))


def _clean_html(raw: str) -> str:
    if len(raw or "") > MAX_CONTENT:
        raise HTTPException(400, f"内容过长，最多 {MAX_CONTENT} 字符")
    s = _Sanitizer()
    s.feed(raw or "")
    return "".join(s.parts)


def _plain_text(content_html: str) -> str:
    """HTML → 纯文本（搜索与摘要用）。"""
    return _html.unescape(_TAG_RE.sub("", content_html or ""))


def _preview(content_html: str, limit: int = 60) -> str:
    t = _plain_text(content_html).strip()
    return t[:limit]


class NoteIn(BaseModel):
    title: str | None = None
    content: str | None = None     # 富文本 HTML
    pinned: bool | None = None
    parent_id: int | None = None
    sort: int | None = None


def _get_own(db: Session, note_id: int, user: User) -> Note:
    n = db.get(Note, note_id)
    if not n or n.user_id != user.id:
        raise HTTPException(404, "页面不存在")
    return n


def _depth(db: Session, note: Note, user: User) -> int:
    """页面层级深度（顶级 = 1）。"""
    d, cur = 1, note
    while cur.parent_id and d <= MAX_DEPTH + 1:
        cur = db.get(Note, cur.parent_id)
        if not cur or cur.user_id != user.id:
            break
        d += 1
    return d


def _out(n: Note, with_content: bool = False) -> dict:
    d = {
        "id": n.id, "parent_id": n.parent_id, "title": n.title or "",
        "pinned": n.pinned, "sort": n.sort or 0,
        "preview": _preview(n.content_html),
        "created_at": n.created_at.isoformat(sep=" ", timespec="seconds") if n.created_at else None,
        "updated_at": n.updated_at.isoformat(sep=" ", timespec="seconds") if n.updated_at else None,
    }
    if with_content:
        d["content"] = n.content_html or ""
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
    # 标题 + 正文纯文本模糊匹配（笔记量级小，内存过滤足够）
    hit = [n for n in rows if kw.lower() in (n.title or "").lower()
           or kw.lower() in _plain_text(n.content_html).lower()]
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
        content_html="",
        sort=0,
    )
    db.add(n)
    db.commit()
    return _out(n, with_content=True)


@router.get("/{note_id}")
def get_note(note_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _out(_get_own(db, note_id, user), with_content=True)


@router.put("/{note_id}")
def update_note(note_id: int, payload: NoteIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = _get_own(db, note_id, user)
    if payload.title is not None:
        n.title = payload.title[:200]
    if payload.content is not None:
        n.content_html = _clean_html(payload.content)
        db.flush()  # 拿到 n.id 用于图片归属（理论上已有，防御性）
        from ..services import images
        images.sync_note_images(db, n.id, n.content_html, uploader_id=user.id)
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
    return _out(n, with_content=True)


@router.delete("/{note_id}")
def delete_note(note_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = _get_own(db, note_id, user)
    has_child = db.query(Note).filter(Note.parent_id == n.id, Note.user_id == user.id).first()
    if has_child:
        raise HTTPException(400, "请先删除或移走该页面的子页面")
    from ..services import images
    images.delete_note_images(db, n.id)   # 级联删除笔记插图
    db.delete(n)
    db.commit()
    return {"ok": True}


# ---------- AI 写作（工具栏按钮唤起，插入光标处） ----------

class NoteAiIn(BaseModel):
    instruction: str
    note_title: str = ""
    context: list[str] = []   # 现有正文的纯文本（前端提取，最多取后 20 段）
    selection: str = ""       # 编辑器中选中的内容（有则作为本次操作的主要对象）
    images: list[str] | None = None   # 附图（截图/照片）data URL，非空走视觉模型


@router.post("/ai-assist")
def note_ai_assist(payload: NoteAiIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """AI 写作：按指令生成 HTML 片段（前端预览确认后插入光标处）；支持附图识别。"""
    from datetime import datetime

    from ..services.llm import LLMError
    from ..services.llm.gateway import _decode_data_urls, extract_json, get_default_provider
    from ..services.llm.prompts import NOTE_AI_SYSTEM, build_note_ai_prompt

    instruction = (payload.instruction or "").strip()
    if not instruction:
        raise HTTPException(400, "请输入要生成的内容描述")
    try:
        provider = get_default_provider(db)
        img_bytes = _decode_data_urls(payload.images)
    except LLMError as e:
        raise HTTPException(400, str(e))
    prompt = build_note_ai_prompt(instruction[:2000], (payload.note_title or "")[:200],
                                  [str(t)[:500] for t in (payload.context or [])[-20:]],
                                  datetime.now().strftime("%Y-%m-%d"),
                                  selection=(payload.selection or "")[:2000])
    if img_bytes:
        prompt += (f"\n\n注意：用户附上了 {len(img_bytes)} 张图片，请结合图片内容写作"
                   "（例如：提取图片中的文字/表格整理成文、按图片描述的场景展开）。")
    last_err: Exception | None = None
    for attempt in range(2):
        current_prompt = prompt if attempt == 0 else (
            f"你上次的输出无法解析为合法 JSON，错误：{last_err}。请重新输出，只输出 JSON。\n\n原始任务：\n" + prompt
        )
        try:
            if img_bytes:
                raw = provider.recognize(img_bytes, current_prompt, system=NOTE_AI_SYSTEM)
            else:
                raw = provider.complete(current_prompt, system=NOTE_AI_SYSTEM)
            data = extract_json(raw)
            fragment = _clean_html(str(data.get("html") or ""))
            if not _plain_text(fragment).strip():
                raise ValueError("输出没有可用的内容")
            return {"html": fragment}
        except LLMError as e:
            # 模型服务类错误（未配置/调用失败/超时）不重试，直接返回可读信息
            raise HTTPException(400, str(e))
        except Exception as e:  # noqa: BLE001 — 解析失败重试一次
            last_err = e
    raise HTTPException(400, f"模型输出解析失败：{last_err}")
