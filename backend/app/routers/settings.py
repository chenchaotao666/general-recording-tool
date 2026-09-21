"""LLM 供应商配置管理 + 通用通知渠道设置。"""
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import LLMProvider
from ..schemas import ProviderIn
from ..services.llm import LLMError, build_provider
from ..utils.security import encrypt

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _out(row: LLMProvider) -> dict:
    return {
        "id": row.id, "name": row.name, "type": row.type,
        "base_url": row.base_url, "model": row.model, "vision_model": row.vision_model,
        "is_default": row.is_default, "enabled": row.enabled,
        "has_api_key": bool(row.api_key_enc),   # 密钥永不回传明文
        "created_at": row.created_at.isoformat(sep=" ") if row.created_at else None,
    }


@router.get("/llm")
def list_providers(db: Session = Depends(get_db)):
    return [_out(r) for r in db.query(LLMProvider).order_by(LLMProvider.id).all()]


@router.post("/llm")
def create_provider(payload: ProviderIn, db: Session = Depends(get_db)):
    if not payload.api_key:
        raise HTTPException(400, "请填写 API Key")
    row = LLMProvider(
        name=payload.name, type=payload.type, base_url=payload.base_url,
        api_key_enc=encrypt(payload.api_key), model=payload.model,
        vision_model=payload.vision_model, is_default=payload.is_default,
        enabled=payload.enabled,
    )
    if payload.is_default:
        db.query(LLMProvider).update({LLMProvider.is_default: False})
    db.add(row)
    db.commit()
    return _out(row)


@router.put("/llm/{provider_id}")
def update_provider(provider_id: int, payload: ProviderIn, db: Session = Depends(get_db)):
    row = db.get(LLMProvider, provider_id)
    if not row:
        raise HTTPException(404, "配置不存在")
    row.name, row.type, row.base_url = payload.name, payload.type, payload.base_url
    row.model, row.vision_model = payload.model, payload.vision_model
    row.enabled = payload.enabled
    if payload.api_key:   # 留空表示不修改密钥
        row.api_key_enc = encrypt(payload.api_key)
    if payload.is_default:
        db.query(LLMProvider).filter(LLMProvider.id != provider_id).update({LLMProvider.is_default: False})
        row.is_default = True
    db.commit()
    return _out(row)


@router.delete("/llm/{provider_id}")
def delete_provider(provider_id: int, db: Session = Depends(get_db)):
    row = db.get(LLMProvider, provider_id)
    if not row:
        raise HTTPException(404, "配置不存在")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/llm/{provider_id}/default")
def set_default(provider_id: int, db: Session = Depends(get_db)):
    row = db.get(LLMProvider, provider_id)
    if not row:
        raise HTTPException(404, "配置不存在")
    db.query(LLMProvider).update({LLMProvider.is_default: False})
    row.is_default = True
    db.commit()
    return _out(row)


@router.post("/llm/{provider_id}/test")
def test_provider(provider_id: int, db: Session = Depends(get_db)):
    row = db.get(LLMProvider, provider_id)
    if not row:
        raise HTTPException(404, "配置不存在")
    provider = build_provider(row)
    start = time.time()
    try:
        reply = provider.complete("只回复两个字：正常")
    except LLMError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "elapsed": round(time.time() - start, 1), "reply": reply[:100]}


# ---------- 通用设置：SMTP / 短信网关 ----------

GENERAL_KEYS = ("smtp", "sms_gateway")


@router.get("/general")
def get_general(db: Session = Depends(get_db)):
    from ..services.actions import get_setting
    out = {k: get_setting(db, k) for k in GENERAL_KEYS}
    # 密码不回传明文，只告知是否已配置
    if out["smtp"].get("password"):
        out["smtp"] = {**out["smtp"], "password": None, "has_password": True}
    return out


@router.put("/general")
def put_general(payload: dict, db: Session = Depends(get_db)):
    from ..services.actions import get_setting, set_setting
    for key in GENERAL_KEYS:
        if key not in payload or not isinstance(payload[key], dict):
            continue
        value = dict(payload[key])
        if key == "smtp" and not value.get("password"):
            # 留空表示保留原密码
            old = get_setting(db, "smtp").get("password")
            value.pop("password", None)
            if old:
                value["password"] = old
        value.pop("has_password", None)
        set_setting(db, key, value)
    db.commit()
    return {"ok": True}


class TestEmailIn(BaseModel):
    to: str


@router.post("/general/test-email")
def test_email(payload: TestEmailIn, db: Session = Depends(get_db)):
    from ..services.actions import ActionError, get_setting, send_smtp
    try:
        send_smtp(get_setting(db, "smtp"), [payload.to], "通用记录工具测试邮件", "这是一封测试邮件，SMTP 配置正常。")
    except ActionError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"发送失败：{e}")
    return {"ok": True}
