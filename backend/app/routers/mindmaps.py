"""思维导图：租户内共享的导图 CRUD。data 为引擎无关纯文本树，引擎切换由前端转换。"""
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
