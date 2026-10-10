"""登录注册：账号密码换取 token；token 校验见 utils/auth.get_current_user。
注册 = 开个人版租户 + 免费档订阅（多租户 SaaS 形态，见 docs/用户与权限体系设计.md §0）。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Plan, Subscription, Tenant, TenantMember, User
from ..services.tenancy import create_tenant, default_tenant_id, my_tenants
from ..utils.auth import create_token, get_current_user, hash_password, verify_password
from ..utils.rbac import role_perms

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class PasswordIn(BaseModel):
    old_password: str
    new_password: str


def _tenant_brief(db: Session, tenant_id: int | None) -> dict | None:
    if not tenant_id:
        return None
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        return None
    sub = db.query(Subscription).filter_by(tenant_id=tenant.id).first()
    plan = db.get(Plan, sub.plan_id) if sub else None
    return {
        "id": tenant.id, "name": tenant.name, "type": tenant.type,
        "plan_code": plan.code if plan else None, "plan_name": plan.name if plan else None,
        "status": sub.status if sub else "active",
    }


def _user_payload(db: Session, user: User, tenant_id: int = 0) -> dict:
    """登录/切换租户返回的用户信息。
    role 填当前租户 membership.role（前端三处权限入口语义不变：admin=当前租户管理员）。"""
    tid = tenant_id or default_tenant_id(db, user)
    role = None
    if tid:
        m = db.query(TenantMember).filter_by(tenant_id=tid, user_id=user.id, status="active").first()
        role = m.role if m else ("admin" if user.is_platform_admin else None)
    if role is None and user.is_platform_admin:
        role = "admin"
    return {
        "id": user.id,
        "username": user.username,
        "role": role or "user",
        "perms": role_perms(db, role),
        "is_platform_admin": bool(user.is_platform_admin),
        "tenant": _tenant_brief(db, tid),
        "tenants": my_tenants(db, user),
    }


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    return {"token": create_token(user.id), "user": _user_payload(db, user)}


@router.post("/register")
def register(body: LoginIn, db: Session = Depends(get_db)):
    username = body.username.strip()
    if len(username) < 2:
        raise HTTPException(400, "用户名至少 2 个字符")
    if len(body.password) < 6:
        raise HTTPException(400, "密码至少 6 位")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(400, "用户名已被注册")
    user = User(username=username, password_hash=hash_password(body.password), role="user")
    db.add(user)
    db.flush()
    # 注册即开个人版租户 + 免费档订阅（同一事务）
    create_tenant(db, user, name=f"{username}的空间", type="personal", plan_code="free")
    db.commit()
    db.refresh(user)
    # 注册成功直接登录
    return {"token": create_token(user.id), "user": _user_payload(db, user)}


@router.get("/me")
def me(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _user_payload(db, user)


@router.put("/password")
def change_password(body: PasswordIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(400, "原密码错误")
    if len(body.new_password) < 6:
        raise HTTPException(400, "新密码至少 6 位")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}
