"""任务动作：站内通知 / 邮件(SMTP) / 短信网关(HTTP 模板) / Webhook。插件化注册。"""
import re
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from ..models import AppSetting, Notification


class ActionError(Exception):
    pass


def get_setting(db: Session, key: str) -> dict:
    row = db.get(AppSetting, key)
    return dict(row.value) if row and isinstance(row.value, dict) else {}


def set_setting(db: Session, key: str, value: dict) -> None:
    row = db.get(AppSetting, key)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


def render_template(template: str, record: dict) -> str:
    """{field_name} 占位符替换为记录值。"""
    def repl(m):
        v = record.get(m.group(1))
        return "" if v is None else str(v)
    return re.sub(r"\{([a-zA-Z0-9_]+)\}", repl, template or "")


def resolve_recipients(action: dict, record: dict) -> list[str]:
    """收件人：固定列表（逗号分隔）或取自记录字段。"""
    r = action.get("recipients") or {}
    if r.get("type") == "field":
        raw = record.get(r.get("field") or "")
    else:
        raw = r.get("value") or ""
    return [s.strip() for s in str(raw).replace("，", ",").split(",") if s.strip()]


def send_smtp(cfg: dict, recipients: list[str], subject: str, content: str) -> None:
    host = cfg.get("host")
    if not host:
        raise ActionError("未配置 SMTP 服务，请到「模型设置-通知渠道」中配置")
    if not recipients:
        raise ActionError("没有可用的收件人")
    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = cfg.get("from_addr") or cfg.get("username") or ""
    msg["To"] = ", ".join(recipients)
    port = int(cfg.get("port") or (465 if cfg.get("use_ssl") else 25))
    cls = smtplib.SMTP_SSL if cfg.get("use_ssl") else smtplib.SMTP
    with cls(host, port, timeout=15) as server:
        if not cfg.get("use_ssl") and cfg.get("use_tls"):
            server.starttls()
        if cfg.get("username"):
            server.login(cfg["username"], cfg.get("password") or "")
        server.sendmail(msg["From"], recipients, msg.as_string())


def act_notify(db: Session, rule, record: dict, content: str) -> None:
    db.add(Notification(title=f"【{rule.name}】", content=content, link=f"/t/{rule.table_id}"))


def act_email(db: Session, rule, record: dict, content: str) -> None:
    cfg = get_setting(db, "smtp")
    send_smtp(cfg, resolve_recipients(rule.action_json, record), f"【{rule.name}】提醒", content)


def act_webhook(db: Session, rule, record: dict, content: str) -> None:
    url = (rule.action_json or {}).get("webhook_url") or get_setting(db, "webhook").get("url")
    if not url:
        raise ActionError("未配置 Webhook 地址")
    try:
        resp = httpx.post(url, json={"rule": rule.name, "content": content, "record": record}, timeout=15)
        if resp.status_code >= 400:
            raise ActionError(f"Webhook 返回 {resp.status_code}")
    except httpx.HTTPError as e:
        raise ActionError(f"Webhook 请求失败：{e}")


def act_sms(db: Session, rule, record: dict, content: str) -> None:
    """短信：HTTP 网关模板。URL 中 {phone}/{content} 会被替换，适配大多数国内短信 HTTP 接口。"""
    tpl = get_setting(db, "sms_gateway").get("url_template")
    if not tpl:
        raise ActionError("未配置短信网关，请到「模型设置-通知渠道」中配置 URL 模板")
    phones = resolve_recipients(rule.action_json, record)
    if not phones:
        raise ActionError("没有可用的手机号")
    for phone in phones:
        url = tpl.replace("{phone}", quote(phone)).replace("{content}", quote(content))
        try:
            resp = httpx.get(url, timeout=15)
            if resp.status_code >= 400:
                raise ActionError(f"短信网关返回 {resp.status_code}")
        except httpx.HTTPError as e:
            raise ActionError(f"短信网关请求失败：{e}")


ACTION_FUNCS = {
    "notify": act_notify,
    "email": act_email,
    "sms": act_sms,
    "webhook": act_webhook,
}

ACTION_LABELS = {"notify": "站内通知", "email": "邮件", "sms": "短信", "webhook": "Webhook"}
