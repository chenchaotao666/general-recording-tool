"""MCP 接入：token 管理（登录）+ MCP JSON-RPC 端点（公开，URL 即凭证）。"""
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Workflow
from ..services.actions import get_setting, set_setting
from ..utils.auth import get_current_user

router = APIRouter(prefix="/api/mcp", tags=["mcp"])
public_router = APIRouter(tags=["mcp-public"])

SETTING_KEY = "mcp_tokens"   # AppSetting: {token: {user_id, created_at}}


def _user_token(db: Session, user_id: int) -> str | None:
    for tok, info in get_setting(db, SETTING_KEY).items():
        if (info or {}).get("user_id") == user_id:
            return tok
    return None


@router.get("/config")
def mcp_config(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tok = _user_token(db, user.id)
    wf_count = db.query(Workflow).filter(Workflow.user_id == user.id, Workflow.enabled.is_(True)).count()
    return {
        "has_token": bool(tok),
        "token": tok or "",
        "url_path": f"/mcp/{tok}" if tok else "",
        "workflow_count": wf_count,
    }


@router.post("/token")
def create_token(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """生成/轮换 token（一人一个，轮换即作废旧 token）。"""
    tokens = {t: v for t, v in get_setting(db, SETTING_KEY).items()
              if (v or {}).get("user_id") != user.id}
    tok = secrets.token_hex(16)
    tokens[tok] = {"user_id": user.id, "created_at": datetime.now().isoformat(sep=" ")}
    set_setting(db, SETTING_KEY, tokens)
    db.commit()   # set_setting 本身不提交
    return {"token": tok, "url_path": f"/mcp/{tok}"}


@router.delete("/token")
def revoke_token(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tokens = {t: v for t, v in get_setting(db, SETTING_KEY).items()
              if (v or {}).get("user_id") != user.id}
    set_setting(db, SETTING_KEY, tokens)
    db.commit()   # set_setting 本身不提交
    return {"ok": True}


@public_router.post("/mcp/{token}")
async def mcp_endpoint(token: str, request: Request, db: Session = Depends(get_db)):
    """MCP Streamable HTTP 端点：URL 路径 token 即凭证，免登录。"""
    from ..services.workflow import mcp_server

    info = get_setting(db, SETTING_KEY).get(token)
    user = db.get(User, (info or {}).get("user_id") or 0)
    if not user:
        raise HTTPException(404, "Not found")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "请求体必须是 JSON-RPC 消息")

    if isinstance(body, list):
        responses = [r for r in (mcp_server.handle_message(db, user, m) for m in body) if r is not None]
        return responses if responses else Response(status_code=202)
    resp = mcp_server.handle_message(db, user, body)
    return resp if resp is not None else Response(status_code=202)
