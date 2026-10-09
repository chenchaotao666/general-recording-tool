"""首页工作台布局（每用户一份；无记录时返回系统默认布局）。"""
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import HomeDefaultLayout, HomeLayout, User
from ..utils.auth import get_current_user

router = APIRouter(prefix="/api/home-layout", tags=["home"])

# 系统默认布局：待办 + 通知 + 数据表三块，新用户开箱即用（栅格 36 列 × 36px 行）
DEFAULT_LAYOUT = {
    "version": 1,
    "grid": {"cols": 36, "row": 36},
    "sections": [
        {
            "id": "sec_todo", "title": "待办中心", "x": 0, "y": 0, "w": 21, "h": 8,
            "cards": [
                {"id": "card_todos", "type": "todos", "config": {"limit": 5}},
                {"id": "card_notifications", "type": "notifications", "config": {"limit": 5}},
            ],
        },
        {
            "id": "sec_tables", "title": "我的数据表", "x": 21, "y": 0, "w": 15, "h": 8,
            "cards": [{"id": "card_tables", "type": "table-list", "config": {"limit": 6}}],
        },
    ],
}


class LayoutIn(BaseModel):
    layout: dict


@router.get("")
def get_layout(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """回退链：用户自己的布局 → 管理员预设的全员默认 → 系统内置默认。"""
    row = db.query(HomeLayout).filter_by(user_id=user.id).first()
    if row and row.layout_json:
        return {"layout": row.layout_json, "source": "mine"}
    preset = db.query(HomeDefaultLayout).order_by(HomeDefaultLayout.id).first()
    if preset and preset.layout_json:
        return {"layout": preset.layout_json, "source": "preset"}
    return {"layout": DEFAULT_LAYOUT, "source": "builtin"}


@router.put("")
def save_layout(payload: LayoutIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    import json
    if len(json.dumps(payload.layout, ensure_ascii=False)) > 256 * 1024:
        from fastapi import HTTPException
        raise HTTPException(400, "布局数据过大")
    layout = dict(payload.layout)
    layout["version"] = 1
    row = db.query(HomeLayout).filter_by(user_id=user.id).first()
    if not row:
        row = HomeLayout(user_id=user.id)
        db.add(row)
    row.layout_json = layout
    row.updated_at = datetime.now()
    db.commit()
    return {"ok": True}


@router.delete("")
def reset_layout(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """删除用户布局记录 → 下次 GET 回退到全员默认/内置默认。"""
    db.query(HomeLayout).filter_by(user_id=user.id).delete()
    db.commit()
    return {"ok": True}


def _require_admin(user: User) -> None:
    from fastapi import HTTPException
    if user.role != "admin":
        raise HTTPException(403, "仅管理员可设置全员默认布局")


@router.put("/default")
def save_default_layout(payload: LayoutIn, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    """管理员：把给定布局设为全员默认（对没有自己布局的用户生效）。"""
    _require_admin(user)
    layout = dict(payload.layout)
    layout["version"] = 1
    row = db.query(HomeDefaultLayout).order_by(HomeDefaultLayout.id).first()
    if not row:
        row = HomeDefaultLayout()
        db.add(row)
    row.layout_json = layout
    row.updated_by = user.id
    row.updated_at = datetime.now()
    db.commit()
    return {"ok": True}


@router.delete("/default")
def clear_default_layout(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """管理员：清除全员默认（回退到系统内置默认）。"""
    _require_admin(user)
    db.query(HomeDefaultLayout).delete()
    db.commit()
    return {"ok": True}
