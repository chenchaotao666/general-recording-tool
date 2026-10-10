"""数据范围配置（角色 × 表 × scope 矩阵）：租户 admin + feature_data_scope 双重闸。
设计文档 §4.2：scope ∈ all / dept_tree / subtree / own；table_id NULL = 租户级默认。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import MetaTable, Role, RoleTableScope
from ..services import entitlement, scope as scope_mod
from ..utils.context import Context, require_tenant_admin

router = APIRouter(prefix="/api/scopes", tags=["scopes"])

# 预设角色模板（设计文档 §5 P1：管理员/经理/员工 = all/dept_tree/own；admin 恒 all 不落行）
PRESETS = {"manager": "dept_tree", "user": "own"}


class ScopeIn(BaseModel):
    role_id: int
    table_id: int | None = None     # None = 租户默认
    scope: str


def _check(db: Session, ctx: Context) -> None:
    entitlement.require_feature(db, ctx.tenant.id, "feature_data_scope")


def _role(db: Session, role_id: int) -> Role:
    r = db.get(Role, role_id)
    if not r:
        raise HTTPException(404, "角色不存在")
    if r.code == "admin":
        raise HTTPException(400, "管理员角色恒为全部数据，无需配置")
    return r


@router.get("")
def get_matrix(db: Session = Depends(get_db), ctx: Context = Depends(require_tenant_admin)):
    """矩阵数据源：全部可配角色 + 租户默认 + 按表覆盖。"""
    _check(db, ctx)
    roles = db.query(Role).filter(Role.code != "admin").order_by(Role.id).all()
    rows = db.query(RoleTableScope).filter_by(tenant_id=ctx.tenant.id).all()
    return {
        "roles": [{"id": r.id, "code": r.code, "name": r.name} for r in roles],
        "default": {r.role_id: r.scope for r in rows if r.table_id is None},
        "overrides": [{"id": r.id, "role_id": r.role_id, "table_id": r.table_id, "scope": r.scope}
                      for r in rows if r.table_id is not None],
    }


@router.put("")
def put_scope(body: ScopeIn, db: Session = Depends(get_db), ctx: Context = Depends(require_tenant_admin)):
    """UPSERT 一条范围配置；scope=all 时删除已有行（保持表干净，all 是默认行为）。"""
    _check(db, ctx)
    _role(db, body.role_id)
    if body.scope not in scope_mod.SCOPE_VALUES:
        raise HTTPException(400, f"scope 必须是 {'/'.join(scope_mod.SCOPE_VALUES)}")
    if body.table_id is not None:
        mt = db.get(MetaTable, body.table_id)
        if not mt or mt.tenant_id != ctx.tenant.id:
            raise HTTPException(404, "数据表不存在")
    q = db.query(RoleTableScope).filter_by(tenant_id=ctx.tenant.id, role_id=body.role_id,
                                           table_id=body.table_id)
    row = q.first()
    if body.scope == "all":
        if row:
            db.delete(row)
    elif row:
        row.scope = body.scope
    else:
        db.add(RoleTableScope(tenant_id=ctx.tenant.id, role_id=body.role_id,
                              table_id=body.table_id, scope=body.scope))
    db.commit()
    scope_mod.invalidate_scope_cache(ctx.tenant.id)
    return {"ok": True}


@router.post("/apply-presets")
def apply_presets(db: Session = Depends(get_db), ctx: Context = Depends(require_tenant_admin)):
    """一键应用预设角色模板（租户级默认行）：经理→dept_tree、员工→own；admin 恒 all 不写。
    幂等（已存在则覆盖）。由租户 admin 显式触发，避免对存量租户静默改行为。"""
    _check(db, ctx)
    applied = {}
    for code, scope in PRESETS.items():
        role = db.query(Role).filter_by(code=code).first()
        if not role:
            continue
        row = db.query(RoleTableScope).filter_by(
            tenant_id=ctx.tenant.id, role_id=role.id, table_id=None).first()
        if row:
            row.scope = scope
        else:
            db.add(RoleTableScope(tenant_id=ctx.tenant.id, role_id=role.id,
                                  table_id=None, scope=scope))
        applied[code] = scope
    db.commit()
    scope_mod.invalidate_scope_cache(ctx.tenant.id)
    return {"ok": True, "applied": applied}
