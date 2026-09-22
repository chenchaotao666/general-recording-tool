"""登录鉴权：pbkdf2 密码散列 + JWT token 签发/校验"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import User

_PBKDF2_ITERATIONS = 200_000


def hash_password(plain: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", plain.encode(), bytes.fromhex(salt), _PBKDF2_ITERATIONS).hex()
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(plain: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
        candidate = hashlib.pbkdf2_hmac("sha256", plain.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(candidate, digest)
    except (ValueError, AttributeError):
        return False


def _secret() -> str:
    if settings.token_secret:
        return settings.token_secret
    # 复用 Fernet 密钥文件，保证零配置可用
    from .security import _fernet

    _fernet()  # 文件不存在时会生成
    return settings.secret_key_file.read_bytes().strip().decode()


def create_token(user_id: int) -> str:
    payload = {
        "uid": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.token_ttl_hours),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_token(token: str) -> int:
    try:
        return jwt.decode(token, _secret(), algorithms=["HS256"])["uid"]
    except (jwt.InvalidTokenError, KeyError):
        raise HTTPException(401, "未登录或登录已过期")


def get_current_user(
    authorization: str = Header(default=""),
    token: str = "",  # 导出下载等 <a>/<window.open> 场景无法带请求头，允许 ?token=
    db: Session = Depends(get_db),
) -> User:
    raw = token
    if authorization.lower().startswith("bearer "):
        raw = authorization[7:]
    if not raw:
        raise HTTPException(401, "未登录或登录已过期")
    user = db.get(User, decode_token(raw))
    if not user:
        raise HTTPException(401, "用户不存在")
    return user
