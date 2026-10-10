"""数据范围（P1）：角色 × 表 的 scope 解析 → 记录级 owner_id 过滤规则。

产出物是**一条复用现有筛选管线的规则 dict**（{"field":"owner_id","op":"in","value":[...]}），
physical 走 dyn_engine.build_condition，json 走 pyquery.match_rule，报表走 viewer_rules 追加。

判定链（与设计文档 §4.2 一致）：
  viewer None（引擎内部/调度器）→ 不过滤
  套餐未含 feature_data_scope → 不过滤（低档行为=现状）
  via ∈ admin/owner/share → 不过滤（击穿：显式分享=开闸）
  via=member（企业成员默认可见）→ 按角色 scope 过滤

缓存：subtree/dept_tree 的 owner 集合 120s 进程缓存；组织变更（部门/成员挂靠）主动失效。
写校验（assert_record_writable）实时计算不穿缓存——不留"刚调完部门还能越权写"的窗口。
"""
import time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Department, MetaTable, Role, RoleTableScope, TenantMember, User
from . import entitlement
from ..utils import access as access_mod

SCOPE_VALUES = ("all", "dept_tree", "subtree", "own")
SCOPE_LABELS = {"all": "全部", "dept_tree": "本部门及下级", "subtree": "本人及下属", "own": "仅本人"}

MAX_DEPTH = 10   # manager 链 / 部门树 下钻防环上限

# {(tenant_id, user_id, scope): (expire_ts, owner_ids)}
_owner_set_cache: dict[tuple, tuple[float, list[int]]] = {}
_CACHE_TTL = 120


def invalidate_scope_cache(tenant_id: int) -> None:
    """组织变更（部门 CRUD / 成员挂靠 / 成员移除）后调用：清该租户全部 scope 缓存。"""
    for key in [k for k in _owner_set_cache if k[0] == tenant_id]:
        _owner_set_cache.pop(key, None)


def get_scope(db: Session, tenant_id: int, role_code: str, table_id: int) -> str:
    """角色在某表上的数据范围：按表覆盖 → 租户默认（table_id IS NULL）→ 'all'。"""
    from sqlalchemy import or_
    rows = (
        db.query(RoleTableScope)
        .join(Role, RoleTableScope.role_id == Role.id)
        .filter(RoleTableScope.tenant_id == tenant_id, Role.code == role_code,
                or_(RoleTableScope.table_id == table_id, RoleTableScope.table_id.is_(None)))
        .all()
    )
    for r in rows:
        if r.table_id == table_id:
            return r.scope
    for r in rows:
        if r.table_id is None:
            return r.scope
    return "all"


def _tenant_member_users(db: Session, tenant_id: int) -> list[User]:
    """本租户 active 成员的用户对象（subtree/dept_tree 的候选全集，一次查出避免 N+1）。"""
    return (
        db.query(User)
        .join(TenantMember, TenantMember.user_id == User.id)
        .filter(TenantMember.tenant_id == tenant_id, TenantMember.status == "active")
        .all()
    )


def _subtree_owner_ids(db: Session, user: User, tenant_id: int) -> list[int]:
    """本人 + 沿 manager_id 下钻（BFS，visited 防环，限深 10 层；候选=本租户 active 成员）。"""
    members = _tenant_member_users(db, tenant_id)
    children: dict[int, list[int]] = {}
    for m in members:
        if m.manager_id:
            children.setdefault(m.manager_id, []).append(m.id)
    out, queue, visited, depth = [user.id], [user.id], {user.id}, 0
    while queue and depth < MAX_DEPTH:
        nxt = []
        for uid in queue:
            for cid in children.get(uid, []):
                if cid not in visited:
                    visited.add(cid)
                    out.append(cid)
                    nxt.append(cid)
        queue, depth = nxt, depth + 1
    return out


def _dept_tree_owner_ids(db: Session, user: User, tenant_id: int) -> list[int]:
    """本部门及下级部门（子树）的全部 active 成员 + 自己。
    我未分配部门 → 只看自己；停用部门（enabled=False）及其子树视同不存在。"""
    if not user.department_id:
        return [user.id]
    depts = db.query(Department).filter(
        Department.tenant_id == tenant_id, Department.enabled == True).all()  # noqa: E712
    children: dict[int, list[int]] = {}
    dept_ids = set()
    for d in depts:
        dept_ids.add(d.id)
        if d.parent_id:
            children.setdefault(d.parent_id, []).append(d.id)
    if user.department_id not in dept_ids:
        return [user.id]   # 我的部门已停用/删除
    sub_ids, queue, visited, depth = [], [user.department_id], {user.department_id}, 0
    while queue and depth < MAX_DEPTH:
        nxt = []
        for did in queue:
            sub_ids.append(did)
            for cid in children.get(did, []):
                if cid not in visited:
                    visited.add(cid)
                    nxt.append(cid)
        queue, depth = nxt, depth + 1
    owners = [m.id for m in _tenant_member_users(db, tenant_id) if m.department_id in visited]
    if user.id not in owners:
        owners.append(user.id)
    return owners


def resolve_owner_ids(db: Session, user: User, scope: str, tenant_id: int,
                      use_cache: bool = True) -> list[int] | None:
    """scope → owner_id 集合；all → None（不过滤）。空集返回 []（调用方用 [-1] 占位）。"""
    if scope == "all":
        return None
    if scope == "own":
        return [user.id]
    key = (tenant_id, user.id, scope)
    if use_cache:
        hit = _owner_set_cache.get(key)
        if hit and hit[0] > time.time():
            return hit[1]
    ids = _subtree_owner_ids(db, user, tenant_id) if scope == "subtree" \
        else _dept_tree_owner_ids(db, user, tenant_id)
    _owner_set_cache[key] = (time.time() + _CACHE_TTL, ids)
    return ids


def scope_rule(db: Session, mt: MetaTable, viewer: User | None,
               ctx=None, use_cache: bool = True) -> dict | None:
    """当前用户对这张表的记录过滤规则；None=不过滤。供 dyn_engine / 报表 / 工作流统一调用。"""
    if viewer is None or mt.tenant_id is None:
        return None
    if not entitlement.has_feature(db, mt.tenant_id, "feature_data_scope"):
        return None   # 低档套餐/个人版：恒 all，行为=现状
    grant = access_mod._resolve_grant(db, mt.id, viewer, ctx)
    if grant is None or grant.via != "member":
        return None   # admin/owner/share 击穿；无权限者的准入由外层（require_table/404）把守
    scope = get_scope(db, mt.tenant_id,
                      grant.ctx.membership.role if grant.ctx and grant.ctx.membership
                      else _member_role(db, viewer, mt.tenant_id),
                      mt.id)
    owner_ids = resolve_owner_ids(db, viewer, scope, mt.tenant_id, use_cache=use_cache)
    if owner_ids is None:
        return None
    return {"field": "owner_id", "op": "in", "value": owner_ids or [-1]}


def _member_role(db: Session, user: User, tenant_id: int) -> str:
    m = db.query(TenantMember).filter_by(tenant_id=tenant_id, user_id=user.id,
                                         status="active").first()
    return m.role if m else "user"


def assert_record_writable(db: Session, mt: MetaTable, viewer: User | None,
                           record_owner_id: int | None) -> None:
    """写闸（编辑/删除记录）：记录 owner 须在 scope 集合内；实时计算不穿缓存。
    越权抛 404（不泄露记录存在性，与 access.py 风格一致）。"""
    rule = scope_rule(db, mt, viewer, use_cache=False)
    if rule and record_owner_id not in rule["value"]:
        raise HTTPException(404, "记录不存在")


# 读详情场景的同一判定（404 语义相同，别名仅为调用点可读性）
assert_record_visible = assert_record_writable
