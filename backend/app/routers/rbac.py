"""角色与权限管理：角色/权限为全局配置——读取对租户 admin 开放（成员角色分配用），
增删改为平台超管专属。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Permission, Role, RolePermission, TenantMember
from ..utils.context import Context, require_platform_admin, require_tenant_admin

router = APIRouter(prefix="/api", tags=["rbac"])

ROLE_CODE_MIN = 2


# ---------- 权限 ----------

def _perm_out(p: Permission) -> dict:
    return {
        "id": p.id, "code": p.code, "name": p.name,
        "description": p.description, "is_system": p.is_system,
    }


@router.get("/permissions")
def list_permissions(db: Session = Depends(get_db), admin: Context = Depends(require_tenant_admin)):
    return [_perm_out(p) for p in db.query(Permission).order_by(Permission.id).all()]




# ---------- 角色 ----------

class RoleIn(BaseModel):
    code: str
    name: str
    description: str | None = None


class RoleUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None


class GrantIn(BaseModel):
    permission_id: int
    value: int | None = None


class GrantsIn(BaseModel):
    grants: list[GrantIn]


def _role_out(db: Session, r: Role) -> dict:
    rows = (
        db.query(RolePermission, Permission)
        .join(Permission, RolePermission.permission_id == Permission.id)
        .filter(RolePermission.role_id == r.id)
        .all()
    )
    return {
        "id": r.id, "code": r.code, "name": r.name,
        "description": r.description, "is_system": r.is_system,
        "permissions": [{"id": p.id, "code": p.code, "name": p.name, "value": rp.value} for rp, p in rows],
    }


@router.get("/roles")
def list_roles(db: Session = Depends(get_db), admin: Context = Depends(require_tenant_admin)):
    return [_role_out(db, r) for r in db.query(Role).order_by(Role.id).all()]


@router.post("/roles")
def create_role(payload: RoleIn, db: Session = Depends(get_db), admin: Context = Depends(require_platform_admin)):
    code = payload.code.strip()
    if len(code) < ROLE_CODE_MIN or not code.replace("_", "").isalnum() or not code[0].isalpha():
        raise HTTPException(400, "角色标识必须是小写字母开头的 snake_case")
    if db.query(Role).filter_by(code=code).first():
        raise HTTPException(400, "角色标识已存在")
    r = Role(code=code, name=payload.name.strip(), description=payload.description)
    db.add(r)
    db.commit()
    db.refresh(r)
    return _role_out(db, r)


@router.put("/roles/{role_id}")
def update_role(role_id: int, payload: RoleUpdateIn, db: Session = Depends(get_db), admin: Context = Depends(require_platform_admin)):
    r = db.get(Role, role_id)
    if not r:
        raise HTTPException(404, "角色不存在")
    if payload.name is not None:
        r.name = payload.name.strip()
    if payload.description is not None:
        r.description = payload.description
    db.commit()
    return _role_out(db, r)


@router.delete("/roles/{role_id}")
def delete_role(role_id: int, db: Session = Depends(get_db), admin: Context = Depends(require_platform_admin)):
    r = db.get(Role, role_id)
    if not r:
        raise HTTPException(404, "角色不存在")
    if r.is_system:
        raise HTTPException(400, "内置角色不可删除")
    if db.query(TenantMember).filter(TenantMember.role == r.code).first():
        raise HTTPException(400, "仍有用户使用该角色，请先调整这些用户的角色")
    db.query(RolePermission).filter_by(role_id=r.id).delete()
    db.delete(r)
    db.commit()
    return {"ok": True}


@router.put("/roles/{role_id}/permissions")
def set_role_permissions(role_id: int, payload: GrantsIn, db: Session = Depends(get_db), admin: Context = Depends(require_platform_admin)):
    """整体替换角色的权限授权（grants 全量覆盖）。"""
    r = db.get(Role, role_id)
    if not r:
        raise HTTPException(404, "角色不存在")
    db.query(RolePermission).filter_by(role_id=r.id).delete()
    for g in payload.grants:
        p = db.get(Permission, g.permission_id)
        if not p:
            raise HTTPException(400, f"权限不存在：{g.permission_id}")
        db.add(RolePermission(role_id=r.id, permission_id=p.id, value=g.value))
    db.commit()
    return _role_out(db, r)
