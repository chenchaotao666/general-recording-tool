"""APScheduler 调度器：进程内后台运行，按规则配置注册周期任务，规则变更时重载。"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..database import SessionLocal
from ..models import TaskRule, Workflow
from .task_engine import execute_rule

scheduler = BackgroundScheduler()


def trigger_of(schedule: dict):
    """把 schedule_json 转成 APScheduler trigger，非法配置返回 None。"""
    if not isinstance(schedule, dict):
        return None
    if schedule.get("type") == "interval":
        try:
            minutes = max(int(schedule.get("minutes") or 60), 1)
        except (TypeError, ValueError):
            return None
        return IntervalTrigger(minutes=minutes)
    if schedule.get("type") == "cron":
        try:
            return CronTrigger.from_crontab(schedule.get("expr") or "")
        except (ValueError, KeyError):
            return None
    return None


def _register_workflow_poller() -> None:
    """工作流任务队列轮询（5s）：延迟/重试/审批恢复/异步触发的统一出口。"""
    from .workflow.engine import process_due_jobs
    scheduler.add_job(
        process_due_jobs, IntervalTrigger(seconds=5),
        id="workflow_poller", replace_existing=True, max_instances=1,
    )


def reload_jobs() -> None:
    """全量重载任务（规则/报表模板/工作流增删改后调用）。单进程部署下足够简单可靠。"""
    scheduler.remove_all_jobs()
    db = SessionLocal()
    try:
        rules = db.query(TaskRule).filter_by(enabled=True).all()
        for rule in rules:
            trigger = trigger_of(rule.schedule_json or {})
            if trigger is not None:
                scheduler.add_job(
                    execute_rule, trigger, args=[rule.id, "schedule"],
                    id=f"rule_{rule.id}", replace_existing=True, misfire_grace_time=300,
                )
        # 报表定时推送
        from ..models import ReportTemplate
        from .report_engine import push_template
        templates = db.query(ReportTemplate).filter_by(enabled=True).all()
        for tpl in templates:
            trigger = trigger_of(tpl.schedule_json or {})
            if trigger is not None:
                scheduler.add_job(
                    push_template, trigger, args=[tpl.id, "schedule"],
                    id=f"report_{tpl.id}", replace_existing=True, misfire_grace_time=300,
                )
        # 工作流定时触发（trigger_json 与任务模块 schedule_json 同格式：{type: interval|cron, ...}）
        from .workflow.engine import run_scheduled
        workflows = db.query(Workflow).filter_by(enabled=True).all()
        for wf in workflows:
            t = wf.trigger_json or {}
            if t.get("type") not in ("interval", "cron"):
                continue
            trigger = trigger_of(t)
            if trigger is not None:
                scheduler.add_job(
                    run_scheduled, trigger, args=[wf.id],
                    id=f"wf_{wf.id}", replace_existing=True, misfire_grace_time=300,
                )
    finally:
        db.close()
    _register_workflow_poller()   # remove_all_jobs 会清掉 poller，每次重载后补回


def start() -> None:
    if not scheduler.running:
        scheduler.start()
    reload_jobs()


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
