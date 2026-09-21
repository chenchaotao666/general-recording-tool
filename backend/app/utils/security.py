"""Fernet 对称加密：用于 LLM API Key 等敏感配置的落库加密。密钥存于 backend/.secret_key。"""
from cryptography.fernet import Fernet

from ..config import settings


def _fernet() -> Fernet:
    f = settings.secret_key_file
    if not f.exists():
        f.write_bytes(Fernet.generate_key())
    return Fernet(f.read_bytes().strip())


def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
