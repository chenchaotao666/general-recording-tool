"""记录变更触发器：dyn_engine 写入后调用（只投递不执行，绝不抛出影响主流程）。"""
from ...database import SessionLocal
from ...models import Workflow
from .template import jsonable


def fire_record_event(table_id: int, kind: str, record: dict, old_record: dict | None = None) -> None:
    """查找订阅了该表 record_created / record_updated 的启用工作流，逐个投递 Run。"""
    from .engine import current_workflow_id, enqueue_run   # 延迟 import 避免环

    db = SessionLocal()
    try:
        workflows = db.query(Workflow).filter_by(enabled=True).all()
        for wf in workflows:
            t = wf.trigger_json or {}
            if t.get("type") != kind or t.get("table_id") != table_id:
                continue
            if wf.id == current_workflow_id():
                continue   # 工作流写表触发的变更不再触发它自己，防自触发死循环
            if kind == "record_updated":
                watch = t.get("watch_fields") or []
                if watch and old_record is not None and not any(
                    record.get(f) != old_record.get(f) for f in watch
                ):
                    continue   # 监听字段未变化
            enqueue_run(db, wf, "record", {
                "record": jsonable(record or {}),
                "old_record": jsonable(old_record or {}),
            })
    except Exception as e:  # noqa: BLE001 — 触发器失败绝不影响写入主流程
        print(f"[workflow] 记录触发器投递失败：{e}", flush=True)
    finally:
        db.close()
