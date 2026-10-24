"""智能表变更事件总线（设计文档 §11.4）：写路径发出 recordCreated / recordUpdated，
自动化引擎与 AI 字段自动重算共同订阅。

执行模型：事件在请求提交后投递到单线程后台执行器（新开 Session，保证有序且不拖慢请求）；
环境变量 GRT_SMART_SYNC=1 时同步执行（冒烟测试用，便于断言结果）。
防循环：depth 随自动化动作链递增，超过 MAX_DEPTH 不再派发。
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from ..database import SessionLocal

log = logging.getLogger(__name__)
MAX_DEPTH = 3
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="smart-events")


def is_sync() -> bool:
    return os.environ.get("GRT_SMART_SYNC") == "1"


def submit(fn, *args, **kwargs) -> None:
    """后台执行 fn(db, *args)；fn 自带的异常在此吞掉并记日志（事件处理失败不影响写路径）。"""
    def run():
        db = SessionLocal()
        try:
            fn(db, *args, **kwargs)
        except Exception:  # noqa: BLE001
            log.exception("smart event handler failed: %s", getattr(fn, "__name__", fn))
            db.rollback()
        finally:
            db.close()
    if is_sync():
        run()
    else:
        _executor.submit(run)


def record_created(db: Session, mt, record: dict, actor_id: int | None = None,
                   actor_type: str = "user", depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        return
    from . import ai_field_service, automation_engine
    event = {"type": "recordCreated", "table_id": mt.id, "record_id": record.get("id"),
             "after": record, "before": None, "changed": None,
             "actor_id": actor_id, "actor_type": actor_type, "depth": depth}
    submit(ai_field_service.handle_event, event)
    submit(automation_engine.handle_event, event)
    table_changed(db, mt)


def table_changed(db: Session, mt) -> None:
    """表数据变化（增/改/删）→ 刷新整表引用了它的公式（后台执行）。"""
    from . import formula_tables
    submit(formula_tables.refresh_dependents, mt.id)


def records_deleted(db: Session, mt) -> None:
    """Recompute whole-table AI aggregates after a deletion, without regenerating row templates."""
    from . import ai_field_service
    submit(ai_field_service.handle_event, {"type": "recordDeleted", "table_id": mt.id})


def record_updated(db: Session, mt, before: dict, after: dict, changed: list[str] | None,
                   actor_id: int | None = None, actor_type: str = "user", depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        return
    # 实际发生变化的字段（提交相同值不算变更）
    keys = changed if changed is not None else list(after)
    real = [k for k in keys if (before or {}).get(k) != (after or {}).get(k)]
    if not real:
        return
    from . import ai_field_service, automation_engine
    event = {"type": "recordUpdated", "table_id": mt.id, "record_id": after.get("id"),
             "after": after, "before": before, "changed": real,
             "actor_id": actor_id, "actor_type": actor_type, "depth": depth}
    if actor_type != "ai":   # AI 自己回写不再触发 AI 重算（防自激）
        submit(ai_field_service.handle_event, event)
    submit(automation_engine.handle_event, event)
    table_changed(db, mt)
