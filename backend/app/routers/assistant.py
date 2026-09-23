"""AI 助手：对话（回复 + 动作预览）+ 动作执行（唯一写入口）+ 生成文件下载。"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..services.assistant_engine import execute_action
from ..services.llm import LLMError
from ..services.llm.gateway import assist_chat
from ..services.uploads import UploadNotFound, get_upload_filename, get_upload_path
from ..utils.auth import get_current_user

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class ChatIn(BaseModel):
    message: str
    history: list[dict] = []
    context: dict = {}


@router.post("/chat")
def chat(payload: ChatIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """对话：返回 {reply, action_card}，除只读问答外不写库。"""
    if not payload.message.strip():
        raise HTTPException(400, "请输入内容")
    try:
        return assist_chat(db, user, payload.message.strip(), payload.history, payload.context)
    except LLMError as e:
        raise HTTPException(400, str(e))


class ExecuteIn(BaseModel):
    type: str
    payload: dict


@router.post("/execute")
def execute(payload: ExecuteIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """执行动作卡片（填表/建表/生成 Excel）；执行前重新鉴权与校验。"""
    return execute_action(db, user, payload.type, payload.payload or {})


@router.get("/download/{file_id}")
def download(file_id: str):
    """下载 AI 生成的文件（<a>/window.open 场景走 ?token= 鉴权）。"""
    try:
        path = get_upload_path(file_id)
        filename = get_upload_filename(file_id) or "assistant.xlsx"
    except UploadNotFound as e:
        raise HTTPException(404, str(e))
    return FileResponse(
        path, filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
