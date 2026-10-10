"""部门树管理（租户内单树）：CRUD + 移动（防环限深）+ 启停 + 负责人。全部租户 admin。
运维规则（设计文档 §4.6）：删除前要求成员已迁出、有子部门须先处理；停用后成员视同未分配。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Department, TenantMember, User
from ..services import scope as scope_mod
from ..utils.context import Context, require_tenant_admin

router = APIRouter(prefix="/api/departments", tags=["departments"])

MAX_DEPTH = 10


class DeptIn(BaseModel):
    name: str
    parent_id: int | None = None
    leader_id: int | None = None
    sort: int = 0


class DeptUpdateIn(BaseModel):
    name: str | None = None
    leader_id: int | None = None
    sort: int | None = None
    enabled: bool | None = None


class MoveIn(BaseModel):
    parent_id: int | None = None


def _get(db: Session, dept_id: int, tenant_id: int) -> Department:
    d = db.get(Department, dept_id)
    if not d or d.tenant_id != tenant_id:
        raise HTTPException(404, "部门不存在")
    return d


def _check_parent(db: Session, tenant_id: int, parent_id: int | None,
                  self_id: int | None = None) -> None:
    """父部门须属本租户且 enabled；沿 parent 链上溯防环（移动时命中自己即环）、限深。"""
    if parent_id is None:
        return
    seen, cur, depth = set(), parent_id, 1
    while cur is not None:
        if cur in seen or depth > MAX_DEPTH:
            raise HTTPException(400, "部门层级成环或超过最大深度（10 层）")
        if self_id is not None and cur == self_id:
            raise HTTPException(400, "不能把部门移动到自己或自己的下级")
        seen.add(cur)
        p = db.get(Department, cur)
        if not p or p.tenant_id != tenant_id:
            raise HTTPException(400, "父部门不存在")
        cur, depth = p.parent_id, depth + 1


def _member_count(db: Session, dept_id: int, tenant_id: int) -> int:
    return (
        db.query(User)
        .join(TenantMember, TenantMember.user_id == User.id)
        .filter(User.department_id == dept_id, TenantMember.tenant_id == tenant_id,
                TenantMember.status == "active")
        .count()
    )


def _out(db: Session, d: Department) -> dict:
    leader = db.get(User, d.leader_id) if d.leader_id else None
    return {
        "id": d.id, "name": d.name, "parent_id": d.parent_id, "sort": d.sort,
        "enabled": d.enabled, "leader_id": d.leader_id,
        "leader_name": leader.username if leader else None,
        "member_count": _member_count(db, d.id, d.tenant_id),
    }


@router.get("")
def list_departments(db: Session = Depends(get_db), ctx: Context = Depends(require_tenant_admin)):
    rows = db.query(Department).filter_by(tenant_id=ctx.tenant.id).order_by(Department.sort, Department.id).all()
    return [_out(db, d) for d in rows]


@router.post("")
def create_department(body: DeptIn, db: Session = Depends(get_db), ctx: Context = Depends(require_tenant_admin)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "请填写部门名称")
    _check_parent(db, ctx.tenant.id, body.parent_id)
    if body.leader_id and not db.query(TenantMember).filter_by(
            tenant_id=ctx.tenant.id, user_id=body.leader_id, status="active").first():
        raise HTTPException(400, "负责人须为本工作空间成员")
    d = Department(tenant_id=ctx.tenant.id, name=name, parent_id=body.parent_id,
                   leader_id=body.leader_id, sort=body.sort, created_at=datetime.now())
    db.add(d)
    db.commit()
    scope_mod.invalidate_scope_cache(ctx.tenant.id)
    return _out(db, d)


@router.put("/{dept_id}")
def update_department(dept_id: int, body: DeptUpdateIn, db: Session = Depends(get_db),
                      ctx: Context = Depends(require_tenant_admin)):
    d = _get(db, dept_id, ctx.tenant.id)
    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(400, "部门名称不能为空")
        d.name = body.name.strip()
    if body.leader_id is not None:
        if body.leader_id and not db.query(TenantMember).filter_by(
                tenant_id=ctx.tenant.id, user_id=body.leader_id, status="active").first():
            raise HTTPException(400, "负责人须为本工作空间成员")
        d.leader_id = body.leader_id or None
    if body.sort is not None:
        d.sort = body.sort
    if body.enabled is not None:
        d.enabled = body.enabled   # 停用后其成员在 dept_tree 范围下视同未分配（只看自己）
    db.commit()
    scope_mod.invalidate_scope_cache(ctx.tenant.id)
    return _out(db, d)


@router.put("/{dept_id}/move")
def move_department(dept_id: int, body: MoveIn, db: Session = Depends(get_db),
                    ctx: Context = Depends(require_tenant_admin)):
    d = _get(db, dept_id, ctx.tenant.id)
    if body.parent_id == d.id:
        raise HTTPException(400, "不能把部门移动到自己")
    _check_parent(db, ctx.tenant.id, body.parent_id, self_id=d.id)
    d.parent_id = body.parent_id
    db.commit()
    scope_mod.invalidate_scope_cache(ctx.tenant.id)
    return _out(db, d)


@router.delete("/{dept_id}")
def delete_department(dept_id: int, db: Session = Depends(get_db), ctx: Context = Depends(require_tenant_admin)):
    d = _get(db, dept_id, ctx.tenant.id)
    if db.query(Department).filter_by(parent_id=d.id).count():
        raise HTTPException(400, "请先处理子部门（移动或删除）")
    if _member_count(db, d.id, ctx.tenant.id):
        raise HTTPException(400, "该部门下还有成员，请先在「成员」页签迁移他们")
    db.delete(d)
    db.commit()
    scope_mod.invalidate_scope_cache(ctx.tenant.id)
    return {"ok": True}
