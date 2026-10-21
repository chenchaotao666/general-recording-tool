"""APScheduler 调度器：进程内后台运行，按配置注册周期任务（报表推送定时触发），变更时重载。"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..database import SessionLocal

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


def _register_billing_jobs() -> None:
    """计费固定任务（每日）：订阅巡检/配额宽限提醒/用量校准。remove_all_jobs 会清掉，须随重载补回。"""
    from .billing_jobs import calibrate_usage, remind_quota_grace, sweep_subscriptions
    scheduler.add_job(sweep_subscriptions, CronTrigger(hour=3, minute=0),
                      id="billing_sub_sweep", replace_existing=True, misfire_grace_time=3600)
    scheduler.add_job(remind_quota_grace, CronTrigger(hour=3, minute=30),
                      id="billing_quota_remind", replace_existing=True, misfire_grace_time=3600)
    scheduler.add_job(calibrate_usage, CronTrigger(hour=4, minute=0),
                      id="billing_usage_calibrate", replace_existing=True, misfire_grace_time=3600)


def reload_jobs() -> None:
    """全量重载任务（报表模板增删改后调用）。单进程部署下足够简单可靠。"""
    scheduler.remove_all_jobs()
    db = SessionLocal()
    try:
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
        # 智能表自动化：定时重复触发（设计文档 §11.4）
        from .automation_engine import register_jobs
        register_jobs(scheduler, db)
    finally:
        db.close()
    _register_billing_jobs()      # 计费固定任务同理补回


def start() -> None:
    if not scheduler.running:
        scheduler.start()
    reload_jobs()


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
