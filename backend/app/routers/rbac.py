"""角色与权限管理：内置角色/权限为全局配置（平台超管维护，所有租户可用）；
租户 admin 可创建/维护本租户的自定义角色（roles.tenant_id=本租户，需套餐含 feature_custom_roles），
读取角色/权限列表对租户 admin 开放（成员角色分配、数据范围矩阵用）。

code 唯一性按 (tenant_id, code)：不同租户可有同名自定义角色；租户角色 code 不得与全局角色重名
（tenant_members.role 存 code、scope 按 code 解析，重名会让两角色配置互相串扰）。
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (MetaTable, Permission, Role, RolePermission, RoleTablePerm,
                      RoleTableScope, Tenant, TenantMember, TenantRolePerm)
from ..services import entitlement
from ..utils.context import Context, require_tenant_admin

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
    tenant_id: int | None = None   # 仅平台超管可用（指定为某租户建角色）；租户 admin 强制本租户


class RoleUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None


class GrantIn(BaseModel):
    permission_id: int
    value: int | None = None


class GrantsIn(BaseModel):
    grants: list[GrantIn]


def _role_out(db: Session, r: Role, tenant_id: int | None = None) -> dict:
    """tenant_id 提供时 permissions 返回该租户内的生效授权（全局授权 ∪ 租户覆盖）；
    否则返回全局授权（平台超管视角）。"""
    rows = (
        db.query(RolePermission, Permission)
        .join(Permission, RolePermission.permission_id == Permission.id)
        .filter(RolePermission.role_id == r.id)
        .all()
    )
    grants = {p.id: {"id": p.id, "code": p.code, "name": p.name, "value": rp.value}
              for rp, p in rows}
    overridden = []
    if tenant_id is not None:
        ovs = (db.query(TenantRolePerm, Permission)
               .join(Permission, TenantRolePerm.permission_id == Permission.id)
               .filter(TenantRolePerm.tenant_id == tenant_id,
                       TenantRolePerm.role_id == r.id).all())
        for ov, p in ovs:
            if ov.granted:
                grants[p.id] = {"id": p.id, "code": p.code, "name": p.name, "value": None}
            else:
                grants.pop(p.id, None)
            overridden.append(p.id)
    tenant = db.get(Tenant, r.tenant_id) if r.tenant_id else None
    # 该角色在查看者租户内的成员数（删除角色前的影响范围提示用）
    from ..models import TenantMember
    member_count = 0
    if tenant_id is not None:
        member_count = (db.query(TenantMember)
                        .filter(TenantMember.tenant_id == tenant_id, TenantMember.role == r.code).count())
    return {
        "id": r.id, "code": r.code, "name": r.name,
        "description": r.description, "is_system": r.is_system,
        "tenant_id": r.tenant_id, "tenant_name": tenant.name if tenant else None,
        "permissions": sorted(grants.values(), key=lambda x: x["id"]),
        "overridden_permission_ids": overridden,   # 本租户有覆盖的权限点（前端可标记「已自定义」）
        "member_count": member_count,
    }


def _get_manageable(db: Session, role_id: int, ctx: Context) -> Role:
    """编辑闸门：平台超管可管任何角色；租户 admin 只能管本租户的自定义角色。"""
    r = db.get(Role, role_id)
    if not r:
        raise HTTPException(404, "角色不存在")
    if ctx.is_platform_admin:
        return r
    if r.tenant_id is None or r.tenant_id != ctx.tenant.id:
        raise HTTPException(403, "全局内置角色由平台管理员维护")
    if r.is_system:
        raise HTTPException(400, "内置角色不可修改")
    return r


@router.get("/roles")
def list_roles(db: Session = Depends(get_db), admin: Context = Depends(require_tenant_admin)):
    """平台超管看全部；租户 admin 看全局内置角色 + 本租户自定义角色。"""
    q = db.query(Role)
    if not admin.is_platform_admin:
        q = q.filter((Role.tenant_id.is_(None)) | (Role.tenant_id == admin.tenant.id))
    tid = None if admin.is_platform_admin else admin.tenant.id
    return [_role_out(db, r, tid) for r in q.order_by(Role.id).all()]


@router.post("/roles")
def create_role(payload: RoleIn, db: Session = Depends(get_db), admin: Context = Depends(require_tenant_admin)):
    code = payload.code.strip()
    if len(code) < ROLE_CODE_MIN or not code.replace("_", "").isalnum() or not code[0].isalpha():
        raise HTTPException(400, "角色标识必须是小写字母开头的 snake_case")
    if admin.is_platform_admin:
        tenant_id = payload.tenant_id
        if tenant_id is not None and not db.get(Tenant, tenant_id):
            raise HTTPException(404, "租户不存在")
    else:
        if payload.tenant_id is not None and payload.tenant_id != admin.tenant.id:
            raise HTTPException(403, "只能为本工作空间创建角色")
        entitlement.require_feature(db, admin.tenant.id, "feature_custom_roles")
        tenant_id = admin.tenant.id
    # 同作用域内 code 唯一；租户角色另不得与全局角色重名（code 是成员角色/数据范围的解析键）
    q = db.query(Role).filter(Role.code == code)
    q = q.filter(Role.tenant_id.is_(None) if tenant_id is None else Role.tenant_id == tenant_id)
    if q.first():
        raise HTTPException(400, "角色标识已存在")
    if tenant_id is not None and db.query(Role).filter(
            Role.code == code, Role.tenant_id.is_(None)).first():
        raise HTTPException(400, "角色标识与内置角色冲突，请换一个")
    r = Role(code=code, name=payload.name.strip(), description=payload.description,
             tenant_id=tenant_id)
    db.add(r)
    db.commit()
    db.refresh(r)
    return _role_out(db, r)


@router.put("/roles/{role_id}")
def update_role(role_id: int, payload: RoleUpdateIn, db: Session = Depends(get_db), admin: Context = Depends(require_tenant_admin)):
    r = _get_manageable(db, role_id, admin)
    if payload.name is not None:
        r.name = payload.name.strip()
    if payload.description is not None:
        r.description = payload.description
    db.commit()
    return _role_out(db, r)


@router.delete("/roles/{role_id}")
def delete_role(role_id: int, db: Session = Depends(get_db), admin: Context = Depends(require_tenant_admin)):
    r = _get_manageable(db, role_id, admin)
    if r.is_system:
        raise HTTPException(400, "内置角色不可删除")
    in_use = db.query(TenantMember).filter(TenantMember.role == r.code)
    if r.tenant_id is not None:
        in_use = in_use.filter(TenantMember.tenant_id == r.tenant_id)
    if in_use.first():
        raise HTTPException(400, "仍有用户使用该角色，请先调整这些用户的角色")
    db.query(RolePermission).filter_by(role_id=r.id).delete()
    db.query(RoleTableScope).filter_by(role_id=r.id).delete()
    db.delete(r)
    db.commit()
    return {"ok": True}


@router.put("/roles/{role_id}/permissions")
def set_role_permissions(role_id: int, payload: GrantsIn, db: Session = Depends(get_db), admin: Context = Depends(require_tenant_admin)):
    """整体替换角色的功能权限授权（grants 全量覆盖）。
    平台超管 / 本租户自定义角色 → 直接改 role_permissions；
    租户 admin 改全局内置角色 → 写入 tenant_role_perms 覆盖（只影响本租户，不动全局默认）。"""
    r = db.get(Role, role_id)
    if not r:
        raise HTTPException(404, "角色不存在")
    direct = admin.is_platform_admin or (r.tenant_id is not None and r.tenant_id == admin.tenant.id)
    if not direct and r.tenant_id is not None:
        raise HTTPException(403, "只能管理本工作空间的角色")

    desired: dict[int, int | None] = {}
    for g in payload.grants:
        p = db.get(Permission, g.permission_id)
        if not p:
            raise HTTPException(400, f"权限不存在：{g.permission_id}")
        desired[p.id] = g.value

    if direct:
        db.query(RolePermission).filter_by(role_id=r.id).delete()
        for pid, value in desired.items():
            db.add(RolePermission(role_id=r.id, permission_id=pid, value=value))
        db.commit()
        return _role_out(db, r)

    # 覆盖路径：与全局授权比对，差异写覆盖行、一致则清掉覆盖行
    global_granted = {rp.permission_id for rp in db.query(RolePermission).filter_by(role_id=r.id)}
    existing = {ov.permission_id: ov for ov in db.query(TenantRolePerm).filter_by(
        tenant_id=admin.tenant.id, role_id=r.id)}
    for pid in set(desired) | set(global_granted):
        want = pid in desired
        glob = pid in global_granted
        ov = existing.get(pid)
        if want == glob:
            if ov:
                db.delete(ov)
        elif ov:
            ov.granted = want
        else:
            db.add(TenantRolePerm(tenant_id=admin.tenant.id, role_id=r.id,
                                  permission_id=pid, granted=want))
    db.commit()
    return _role_out(db, r, admin.tenant.id)


# ---------- 角色 × 数据表 操作权限（P2 矩阵：查看/新增/修改/删除） ----------

TABLE_OPS = ("can_view", "can_create", "can_edit", "can_delete")


class TablePermIn(BaseModel):
    table_id: int
    can_view: bool = True
    can_create: bool = True
    can_edit: bool = True
    can_delete: bool = True


def _check_matrix_role(db: Session, role_id: int, ctx: Context) -> Role:
    """矩阵配置闸门：角色须为全局内置或本租户角色；admin 恒全权无需配置。"""
    r = db.get(Role, role_id)
    if not r or (r.tenant_id is not None and r.tenant_id != ctx.tenant.id):
        raise HTTPException(404, "角色不存在")
    if r.code == "admin":
        raise HTTPException(400, "管理员角色恒为全部权限，无需配置")
    return r


@router.get("/roles/{role_id}/table-perms")
def get_table_perms(role_id: int, db: Session = Depends(get_db), ctx: Context = Depends(require_tenant_admin)):
    """角色在本租户各表上的操作权限（无行=全允许）+ 本租户表清单。"""
    r = _check_matrix_role(db, role_id, ctx)
    tables = (db.query(MetaTable).filter_by(tenant_id=ctx.tenant.id)
              .order_by(MetaTable.id).all())
    rows = db.query(RoleTablePerm).filter_by(tenant_id=ctx.tenant.id, role_id=r.id).all()
    return {
        "tables": [{"id": t.id, "label": t.label} for t in tables],
        "perms": {str(x.table_id): {op: getattr(x, op) for op in TABLE_OPS} for x in rows},
    }


@router.put("/roles/{role_id}/table-perms")
def put_table_perm(role_id: int, body: TablePermIn, db: Session = Depends(get_db),
                   ctx: Context = Depends(require_tenant_admin)):
    """UPSERT 一条角色×表权限；四项全允许时删除已有行（无行=默认全允许，保持表干净）。"""
    r = _check_matrix_role(db, role_id, ctx)
    mt = db.get(MetaTable, body.table_id)
    if not mt or mt.tenant_id != ctx.tenant.id:
        raise HTTPException(404, "数据表不存在")
    q = db.query(RoleTablePerm).filter_by(tenant_id=ctx.tenant.id, role_id=r.id,
                                          table_id=body.table_id)
    row = q.first()
    all_allowed = all(getattr(body, op) for op in TABLE_OPS)
    if all_allowed:
        if row:
            db.delete(row)
    elif row:
        for op in TABLE_OPS:
            setattr(row, op, getattr(body, op))
    else:
        db.add(RoleTablePerm(tenant_id=ctx.tenant.id, role_id=r.id, table_id=body.table_id,
                             **{op: getattr(body, op) for op in TABLE_OPS}))
    db.commit()
    return {"ok": True}
