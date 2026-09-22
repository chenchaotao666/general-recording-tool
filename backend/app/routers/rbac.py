"""角色与权限管理（仅 admin）：角色 CRUD、权限 CRUD、角色授权。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Permission, Role, RolePermission, User
from ..utils.auth import get_current_user

router = APIRouter(prefix="/api", tags=["rbac"])

ROLE_CODE_MIN = 2


def _require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "仅管理员可操作")
    return user


# ---------- 权限 ----------

class PermissionIn(BaseModel):
    code: str
    name: str
    description: str | None = None


def _perm_out(p: Permission) -> dict:
    return {
        "id": p.id, "code": p.code, "name": p.name,
        "description": p.description, "is_system": p.is_system,
    }


@router.get("/permissions")
def list_permissions(db: Session = Depends(get_db), admin: User = Depends(_require_admin)):
    return [_perm_out(p) for p in db.query(Permission).order_by(Permission.id).all()]


@router.post("/permissions")
def create_permission(payload: PermissionIn, db: Session = Depends(get_db), admin: User = Depends(_require_admin)):
    code = payload.code.strip()
    if not code.replace("_", "").isalnum() or not code[0].isalpha():
        raise HTTPException(400, "权限标识必须是小写字母开头的 snake_case")
    if db.query(Permission).filter_by(code=code).first():
        raise HTTPException(400, "权限标识已存在")
    p = Permission(code=code, name=payload.name.strip(), description=payload.description)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _perm_out(p)


@router.delete("/permissions/{perm_id}")
def delete_permission(perm_id: int, db: Session = Depends(get_db), admin: User = Depends(_require_admin)):
    p = db.get(Permission, perm_id)
    if not p:
        raise HTTPException(404, "权限不存在")
    if p.is_system:
        raise HTTPException(400, "内置权限不可删除")
    db.query(RolePermission).filter_by(permission_id=p.id).delete()
    db.delete(p)
    db.commit()
    return {"ok": True}


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
def list_roles(db: Session = Depends(get_db), admin: User = Depends(_require_admin)):
    return [_role_out(db, r) for r in db.query(Role).order_by(Role.id).all()]


@router.post("/roles")
def create_role(payload: RoleIn, db: Session = Depends(get_db), admin: User = Depends(_require_admin)):
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
def update_role(role_id: int, payload: RoleUpdateIn, db: Session = Depends(get_db), admin: User = Depends(_require_admin)):
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
def delete_role(role_id: int, db: Session = Depends(get_db), admin: User = Depends(_require_admin)):
    r = db.get(Role, role_id)
    if not r:
        raise HTTPException(404, "角色不存在")
    if r.is_system:
        raise HTTPException(400, "内置角色不可删除")
    if db.query(User).filter(User.role == r.code).first():
        raise HTTPException(400, "仍有用户使用该角色，请先调整这些用户的角色")
    db.query(RolePermission).filter_by(role_id=r.id).delete()
    db.delete(r)
    db.commit()
    return {"ok": True}


@router.put("/roles/{role_id}/permissions")
def set_role_permissions(role_id: int, payload: GrantsIn, db: Session = Depends(get_db), admin: User = Depends(_require_admin)):
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
