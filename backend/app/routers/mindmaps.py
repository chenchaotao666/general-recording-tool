"""思维导图：租户内共享的导图 CRUD。data 为引擎无关纯文本树，引擎切换由前端转换。"""
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Group, GroupMember, Mindmap, MindmapShare, User
from ..services import entitlement
from ..services.notify import notify_user
from ..utils.context import Context, get_current_context
from sqlalchemy import or_

router = APIRouter(prefix="/api/mindmaps", tags=["mindmaps"])

# 引擎原生文档（simple-mind-map getData(withConfig=True)）：root 节点树含全部装饰字段
# （图标/图片/超链接/备注/概要/关联线），layout/theme 随文档持久化；兼容旧中间格式 {text, children[]}
DEFAULT_DATA = {
    "root": {"data": {"text": "中心主题"}, "children": []},
    "layout": "logicalStructure",
    "theme": {"template": "default", "config": {}},
}


class MindmapIn(BaseModel):
    title: str | None = None
    data: dict | None = None


def _out(m: Mindmap, user: User, ctx: Context, owner_name: str | None = None) -> dict:
    return {
        "id": m.id, "title": m.title,
        "owner_id": m.user_id, "owner_name": owner_name or str(m.user_id),
        "can_delete": m.user_id == user.id or ctx.is_tenant_admin,
        "created_at": m.created_at.isoformat(sep=" ") if m.created_at else None,
        "updated_at": m.updated_at.isoformat(sep=" ") if m.updated_at else None,
    }


def _check_data(data: dict) -> None:
    """两种合法格式：原生文档 {root: {...}} 或旧中间格式 {text, children[]}（加载时自动升级）。"""
    if not isinstance(data, dict):
        raise HTTPException(400, "data 结构不合法")
    if isinstance(data.get("root"), dict):
        return
    if isinstance(data.get("text"), str) and isinstance(data.get("children", []), list):
        return
    raise HTTPException(400, "data 必须是 {root: {...}} 或 {text, children[]} 结构")


def _share_grant(db: Session, mid: int, user: User) -> dict | None:
    """已接受的成员分享（人/组并集，可跨租户）：None=无分享；否则 {can_view, can_edit}。"""
    shares = (
        db.query(MindmapShare)
        .outerjoin(GroupMember, MindmapShare.group_id == GroupMember.group_id)
        .filter(
            MindmapShare.mindmap_id == mid,
            or_(MindmapShare.user_id == user.id, GroupMember.user_id == user.id),
            MindmapShare.status == "accepted",
        )
        .all()
    )
    shares = [s for s in shares if s.can_view]
    if not shares:
        return None
    return {"can_view": True, "can_edit": any(s.can_edit for s in shares)}


def _get(db: Session, ctx: Context, mid: int) -> Mindmap:
    """读取闸：本租户成员 / 被分享者（can_view）。"""
    m = db.get(Mindmap, mid)
    if not m:
        raise HTTPException(404, "思维导图不存在")
    if m.tenant_id == ctx.tenant.id:
        return m
    if _share_grant(db, mid, ctx.user):
        return m
    raise HTTPException(404, "思维导图不存在")


def _check_editable(db: Session, m: Mindmap, ctx: Context) -> None:
    """编辑闸：本租户成员（协作定位，同现状）/ 被分享者需 can_edit。"""
    if m.tenant_id == ctx.tenant.id:
        return
    grant = _share_grant(db, m.id, ctx.user)
    if grant and grant["can_edit"]:
        return
    raise HTTPException(404, "思维导图不存在")


# ---------- AI 生成（渐进渲染由前端完成，接口一次返回整棵树） ----------

class MindmapAiIn(BaseModel):
    instruction: str
    mode: str = "rebuild"        # rebuild=整图重建 | expand=在选中节点下扩写
    node_text: str = ""          # expand 模式的父节点文本
    context: list[str] = []      # 现有节点文本（供衔接，可选）
    images: list[str] | None = None   # 附图（截图/照片）data URL，非空走视觉模型


def _clean_ai_tree(node, depth, budget: list) -> dict | None:
    """递归清洗 AI 输出的节点树：限 5 层、共 50 节点；装饰字段白名单透传。"""
    if not isinstance(node, dict) or depth > 5 or budget[0] <= 0:
        return None
    text = str(node.get("text") or "").strip()[:30]
    if not text:
        return None
    budget[0] -= 1
    out = {"text": text, "children": []}
    # 备注：需要详细解释的内容
    note = str(node.get("note") or "").strip()[:500]
    if note:
        out["note"] = note
    # 超链接：仅 http(s)
    link = str(node.get("hyperlink") or "").strip()[:300]
    if link.lower().startswith(("http://", "https://")):
        out["hyperlink"] = link
    # 颜色：#rgb/#rrggbb 才放行（重点文字色/背景色）
    for key in ("color", "fillColor"):
        v = str(node.get(key) or "").strip()
        if re.fullmatch(r"#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?", v):
            out[key] = v
    # 图标：合法分组前缀白名单，最多 2 个
    icons = [
        str(i) for i in (node.get("icon") or [])
        if re.fullmatch(r"(priority|progress|expression|sign)_[0-9a-zA-Z一-龥]+", str(i))
    ][:2]
    if icons:
        out["icon"] = icons
    for c in (node.get("children") or []):
        cc = _clean_ai_tree(c, depth + 1, budget)
        if cc:
            out["children"].append(cc)
    return out


def _clean_ai_lines(data: dict, budget: list) -> list:
    """关联线 [{from, to}]：文字截断，最多 3 条。"""
    out = []
    for l in (data.get("associativeLines") or [])[:3]:
        if not isinstance(l, dict):
            continue
        a, b = str(l.get("from") or "").strip()[:30], str(l.get("to") or "").strip()[:30]
        if a and b and a != b:
            out.append({"from": a, "to": b})
    return out


def _clean_ai_gens(data: dict) -> list:
    """概要 [{text, members[]}]：members 2~6 个，最多 2 组。"""
    out = []
    for g in (data.get("generalizations") or [])[:2]:
        if not isinstance(g, dict):
            continue
        text = str(g.get("text") or "").strip()[:30]
        members = [str(m).strip()[:30] for m in (g.get("members") or [])][:6]
        members = [m for m in members if m]
        if text and len(members) >= 2:
            out.append({"text": text, "members": members})
    return out


@router.post("/ai-assist")
def mindmap_ai_assist(payload: MindmapAiIn, db: Session = Depends(get_db),
                      ctx: Context = Depends(get_current_context)):
    """AI 生成导图结构：rebuild 返回 {text, children}；expand 返回 {children}；支持附图识别。"""
    from ..services.llm import LLMError
    from ..services.llm.gateway import _decode_data_urls, extract_json, get_default_provider
    from ..services.llm.prompts import (
        MINDMAP_AI_SYSTEM, build_mindmap_ai_prompt,
        build_mindmap_rewrite_prompt, build_mindmap_summary_prompt,
    )

    try:
        provider = get_default_provider(db)
        img_bytes = _decode_data_urls(payload.images)
    except LLMError as e:
        raise HTTPException(400, str(e))
    mode = payload.mode if payload.mode in ("expand", "rewrite", "summarize") else "rebuild"
    instruction = (payload.instruction or "").strip()
    if mode != "summarize" and not instruction:
        # 只传图不写字：按图片内容生成导图（视觉模型路径）
        if not img_bytes:
            raise HTTPException(400, "请输入要生成的内容描述，或上传图片")
        instruction = "分析图片内容，提取主题与层次结构，生成思维导图"
    context_texts = [str(t)[:60] for t in (payload.context or [])[-30:]]
    if mode == "summarize":
        # instruction 可空（默认概括）；有值时是自定义分析任务（如改进建议），不改导图
        prompt = build_mindmap_summary_prompt(context_texts, instruction[:2000])
    elif mode == "rewrite":
        prompt = build_mindmap_rewrite_prompt(instruction[:2000], (payload.node_text or "")[:100],
                                              context_texts)
    else:
        prompt = build_mindmap_ai_prompt(instruction[:2000], mode, (payload.node_text or "")[:100],
                                         context_texts)
    if img_bytes:
        prompt += (f"\n\n注意：用户附上了 {len(img_bytes)} 张图片，请从图片中提取主题和层次结构生成导图"
                   "（例如：大纲文档、板书/白板照片、流程图、表格）。"
                   "图片中的条目/步骤/栏目都要展开为导图节点（必要时再细分出子节点），不要把它们塞进备注。")
    last_err: Exception | None = None
    for attempt in range(2):
        current_prompt = prompt if attempt == 0 else (
            f"你上次的输出无法解析为合法 JSON，错误：{last_err}。请重新输出，只输出 JSON。\n\n原始任务：\n" + prompt
        )
        try:
            if img_bytes:
                raw = provider.recognize(img_bytes, current_prompt, system=MINDMAP_AI_SYSTEM)
            else:
                raw = provider.complete(current_prompt, system=MINDMAP_AI_SYSTEM)
            data = extract_json(raw)
            if not isinstance(data, dict):
                raise ValueError("输出不是 JSON 对象")
            if mode == "summarize":
                summary = str(data.get("summary") or "").strip()[:4000]
                if not summary:
                    raise ValueError("输出没有可用的总结")
                return {"summary": summary}
            if mode in ("expand", "rewrite"):
                # 宽容解析：模型可能返回整棵树，取其 children
                kids = data.get("children") or (data.get("root") or {}).get("children") or []
                budget = [50]
                cleaned = [_clean_ai_tree(c, 1, budget) for c in kids]
                cleaned = [c for c in cleaned if c]
                if not cleaned:
                    raise ValueError("输出没有可用的分支")
                return {"children": cleaned}
            budget = [50]
            tree = _clean_ai_tree(data.get("root") or data, 0, budget)
            if not tree or not tree["children"]:
                raise ValueError("输出没有可用的导图结构")
            tree["associativeLines"] = _clean_ai_lines(data, budget)
            tree["generalizations"] = _clean_ai_gens(data)
            return tree
        except LLMError as e:
            raise HTTPException(400, str(e))
        except Exception as e:  # noqa: BLE001 — 解析失败回喂重试一次
            last_err = e
    raise HTTPException(400, f"模型输出解析失败：{last_err}")


# ---------- 成员分享（好友/用户组；直发 pending，组即时生效） ----------

class MindmapShareIn(BaseModel):
    user_id: int | None = None
    username: str | None = None
    group_id: int | None = None
    can_view: bool = True
    can_edit: bool = False


def _share_out(db: Session, s: MindmapShare) -> dict:
    target, target_type = "?", "user"
    if s.user_id:
        u = db.get(User, s.user_id)
        target = u.username if u else str(s.user_id)
    elif s.group_id:
        g = db.get(Group, s.group_id)
        target, target_type = (g.name if g else str(s.group_id)), "group"
    return {
        "id": s.id, "target": target, "target_type": target_type,
        "can_view": s.can_view, "can_edit": s.can_edit,
        "status": s.status,
        "created_at": s.created_at.isoformat(sep=" ") if s.created_at else None,
    }


def _get_sharable(db: Session, ctx: Context, mid: int) -> Mindmap:
    """分享管理闸：创建人 / 本租户 admin。"""
    m = db.get(Mindmap, mid)
    if not m or m.tenant_id != ctx.tenant.id:
        raise HTTPException(404, "思维导图不存在")
    if m.user_id != ctx.user.id and not ctx.is_tenant_admin:
        raise HTTPException(403, "只有创建人或管理员可以管理分享")
    return m


@router.get("/{mid}/shares")
def list_shares(mid: int, db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    _get_sharable(db, ctx, mid)
    return [_share_out(db, s) for s in db.query(MindmapShare).filter_by(mindmap_id=mid).all()]


@router.post("/{mid}/shares")
def put_share(mid: int, payload: MindmapShareIn, db: Session = Depends(get_db),
              ctx: Context = Depends(get_current_context)):
    """UPSERT 分享（按 user/group 唯一约束）。直发对象约束与表分享一致：好友或同组（admin 豁免）。"""
    from .friends import is_friend, same_group
    m = _get_sharable(db, ctx, mid)
    user = ctx.user
    is_admin = ctx.is_tenant_admin
    notify_target = None
    notify_members: list[int] = []
    if payload.group_id is not None:
        group = db.get(Group, payload.group_id)
        if not group:
            raise HTTPException(404, "用户组不存在")
        if not is_admin and not db.query(GroupMember).filter_by(
                group_id=payload.group_id, user_id=user.id).first():
            raise HTTPException(403, "只能分享到自己所在的组")
        share = db.query(MindmapShare).filter_by(mindmap_id=mid, group_id=payload.group_id).first()
        if not share:
            share = MindmapShare(mindmap_id=mid, group_id=payload.group_id, shared_by=user.id)
            db.add(share)
            notify_members = [
                gm.user_id for gm in db.query(GroupMember).filter_by(group_id=payload.group_id).all()
                if gm.user_id != user.id
            ]
        share.status = "accepted"
    else:
        target = None
        if payload.user_id is not None:
            target = db.get(User, payload.user_id)
        elif payload.username:
            target = db.query(User).filter(User.username == payload.username.strip()).first()
        if not target:
            raise HTTPException(404, "用户不存在" if (payload.user_id is not None or payload.username) else "请指定分享的用户或用户组")
        if target.id == m.user_id:
            raise HTTPException(400, "不能分享给创建人")
        if not is_admin and not (is_friend(db, user.id, target.id) or same_group(db, user.id, target.id)):
            raise HTTPException(403, "只能分享给好友或同组用户")
        share = db.query(MindmapShare).filter_by(mindmap_id=mid, user_id=target.id).first()
        if not share:
            share = MindmapShare(mindmap_id=mid, user_id=target.id, shared_by=user.id,
                                 status="pending")
            db.add(share)
            notify_target = target
        elif share.status == "rejected":
            share.status = "pending"
            notify_target = target
    share.can_view = payload.can_view
    share.can_edit = payload.can_edit
    if notify_target:
        notify_user(db, notify_target.id, "收到导图分享",
                    f"{user.username} 把思维导图「{m.title}」分享给你，请确认", link="/tables")
    for uid in notify_members:
        notify_user(db, uid, "收到导图分享",
                    f"{user.username} 把思维导图「{m.title}」分享给你所在的组「{group.name}」，现在可以查看",
                    link="/mindmaps")
    db.commit()
    db.refresh(share)
    return _share_out(db, share)


@router.delete("/{mid}/shares/{share_id}")
def delete_share(mid: int, share_id: int, db: Session = Depends(get_db),
                 ctx: Context = Depends(get_current_context)):
    _get_sharable(db, ctx, mid)
    share = db.get(MindmapShare, share_id)
    if not share or share.mindmap_id != mid:
        raise HTTPException(404, "分享不存在")
    db.delete(share)
    db.commit()
    return {"ok": True}


@router.get("")
def list_mindmaps(db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    """本租户的导图 ∪ 分享给我的（accepted 成员分享，跨租户；标记 shared + can_edit）。"""
    rows = (db.query(Mindmap).filter_by(tenant_id=ctx.tenant.id)
            .order_by(Mindmap.updated_at.desc()).all())
    names = {u.id: u.username for u in db.query(User).filter(
        User.id.in_({m.user_id for m in rows} or [-1]))}
    out = [_out(m, ctx.user, ctx, names.get(m.user_id)) for m in rows]

    shared_rows = (
        db.query(MindmapShare, Mindmap)
        .join(Mindmap, MindmapShare.mindmap_id == Mindmap.id)
        .outerjoin(GroupMember, MindmapShare.group_id == GroupMember.group_id)
        .filter(
            or_(MindmapShare.user_id == ctx.user.id, GroupMember.user_id == ctx.user.id),
            MindmapShare.status == "accepted",
            MindmapShare.can_view == True,  # noqa: E712
            Mindmap.tenant_id != ctx.tenant.id,   # 本租户的已在上面
        )
        .all()
    )
    extra_names = {u.id: u.username for u in db.query(User).filter(
        User.id.in_({m.user_id for _, m in shared_rows} or [-1]))}
    seen = set()
    for s, m in shared_rows:
        if m.id in seen:
            continue
        seen.add(m.id)
        d = _out(m, ctx.user, ctx, extra_names.get(m.user_id))
        d["shared"] = True
        d["can_delete"] = False
        d["can_edit"] = bool(s.can_edit)   # 列表区分只读/可编辑（打开前可见）
        out.append(d)
    return out


@router.post("")
def create_mindmap(body: MindmapIn, db: Session = Depends(get_db),
                   ctx: Context = Depends(get_current_context)):
    entitlement.assert_tenant_writable(db, ctx.tenant.id)
    title = (body.title or "").strip() or "未命名导图"
    if body.data is not None:
        _check_data(body.data)
    m = Mindmap(tenant_id=ctx.tenant.id, user_id=ctx.user.id, title=title[:200],
                data=body.data or DEFAULT_DATA)
    db.add(m)
    db.commit()
    db.refresh(m)
    return _out(m, ctx.user, ctx, ctx.user.username)


@router.get("/{mid}")
def get_mindmap(mid: int, db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    m = _get(db, ctx, mid)
    owner = db.get(User, m.user_id)
    return {**_out(m, ctx.user, ctx, owner.username if owner else None),
            "data": m.data or DEFAULT_DATA}


@router.put("/{mid}")
def update_mindmap(mid: int, body: MindmapIn, db: Session = Depends(get_db),
                   ctx: Context = Depends(get_current_context)):
    """租户成员均可编辑（协作定位）；标题/内容整体保存。"""
    m = _get(db, ctx, mid)
    _check_editable(db, m, ctx)
    entitlement.assert_tenant_writable(db, ctx.tenant.id)
    if body.title is not None:
        t = body.title.strip()
        if t:
            m.title = t[:200]
    if body.data is not None:
        _check_data(body.data)
        m.data = body.data
        m.updated_at = datetime.now()
    db.commit()
    return _out(m, ctx.user, ctx)


@router.delete("/{mid}")
def delete_mindmap(mid: int, db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    m = _get(db, ctx, mid)
    if m.user_id != ctx.user.id and not ctx.is_tenant_admin:
        raise HTTPException(403, "只有创建人或管理员可以删除")
    entitlement.assert_tenant_writable(db, ctx.tenant.id)
    db.delete(m)
    db.commit()
    return {"ok": True}
