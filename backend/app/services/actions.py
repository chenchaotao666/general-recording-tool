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


def resolve_recipients_multi(action: dict, records: list[dict]) -> list[str]:
    """批量场景的收件人：固定列表，或汇总所有命中记录字段值并去重。"""
    r = action.get("recipients") or {}
    if r.get("type") == "field":
        raw = ",".join(str(rec.get(r.get("field") or "") or "") for rec in records)
    else:
        raw = r.get("value") or ""
    seen, out = set(), []
    for s in str(raw).replace("，", ",").split(","):
        s = s.strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def render_batch_body(action: dict, records: list[dict]) -> str:
    """批量正文：每条记录按模板渲染一行，多条时编号汇总。"""
    lines = [render_template(action.get("template", ""), rec) for rec in records]
    if len(lines) == 1:
        return lines[0]
    return f"共 {len(lines)} 条记录：\n" + "\n".join(f"{i}. {line}" for i, line in enumerate(lines, 1))


def _open_smtp(cfg: dict):
    """按配置建立 SMTP 连接（465 隐式 SSL / 587 STARTTLS 按端口推断）并完成登录。"""
    host = cfg.get("host")
    if not host:
        raise ActionError("未配置 SMTP 服务，请到「模型设置-通知渠道」中配置")
    port = int(cfg.get("port") or (465 if cfg.get("use_ssl") else 25))
    # use_ssl 未显式设置时按端口推断：465 隐式 SSL，587 走 STARTTLS
    use_ssl = cfg.get("use_ssl")
    if use_ssl is None:
        use_ssl = port == 465
    use_tls = cfg.get("use_tls")
    if use_tls is None:
        use_tls = not use_ssl and port == 587
    cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    server = cls(host, port, timeout=15)
    if not use_ssl and use_tls:
        server.starttls()
    if cfg.get("username"):
        server.login(cfg["username"], cfg.get("password") or "")
    return server


def _smtp_errors(fn):
    """把 smtplib 异常翻译成用户可读的 ActionError。"""
    try:
        return fn()
    except smtplib.SMTPAuthenticationError as e:
        detail = e.smtp_error.decode(errors="replace") if isinstance(e.smtp_error, bytes) else e.smtp_error
        raise ActionError(f"SMTP 登录认证失败：{detail}（QQ/163 等邮箱请使用「授权码」而非登录密码）")
    except smtplib.SMTPServerDisconnected as e:
        raise ActionError(f"SMTP 服务器断开了连接：{e}（多为授权码错误或短时间内登录过于频繁被限制，请稍后重试）")
    except (OSError, smtplib.SMTPException) as e:
        raise ActionError(f"SMTP 发送失败：{e}")


def send_smtp(cfg: dict, recipients: list[str], subject: str, content: str) -> None:
    if not cfg.get("host"):
        raise ActionError("未配置 SMTP 服务，请到「模型设置-通知渠道」中配置")
    if not recipients:
        raise ActionError("没有可用的收件人")
    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = cfg.get("from_addr") or cfg.get("username") or ""
    msg["To"] = ", ".join(recipients)

    def do_send():
        with _open_smtp(cfg) as server:
            server.sendmail(msg["From"], recipients, msg.as_string())
    _smtp_errors(do_send)


def send_smtp_html(cfg: dict, recipients: list[str], subject: str, html: str,
                   attachments: list[tuple[str, bytes, str]] | None = None) -> None:
    """HTML 邮件 + 可选附件（filename, content_bytes, mime_maintype/subtype）。供报表推送使用。"""
    from email.mime.application import MIMEApplication
    from email.mime.multipart import MIMEMultipart

    if not cfg.get("host"):
        raise ActionError("未配置 SMTP 服务，请到「模型设置-通知渠道」中配置")
    if not recipients:
        raise ActionError("没有可用的收件人")
    msg = MIMEMultipart("mixed")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = cfg.get("from_addr") or cfg.get("username") or ""
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html, "html", "utf-8"))
    for filename, data, mime in attachments or []:
        subtype = (mime or "").split("/", 1)[-1] or "octet-stream"
        part = MIMEApplication(data, _subtype=subtype)
        part.add_header("Content-Disposition", "attachment", filename=Header(filename, "utf-8").encode())
        msg.attach(part)

    def do_send():
        with _open_smtp(cfg) as server:
            server.sendmail(msg["From"], recipients, msg.as_string())
    _smtp_errors(do_send)


def act_notify(db: Session, rule, record: dict, content: str) -> None:
    db.add(Notification(title=f"【{rule.name}】", content=content, link=f"/t/{rule.table_id}",
                        user_id=rule.user_id))  # 接收人 = 规则归属人


def act_email(db: Session, rule, record: dict, content: str) -> None:
    cfg = get_setting(db, "smtp")
    send_smtp(cfg, resolve_recipients(rule.action_json, record), f"【{rule.name}】提醒", content)


def act_email_batch(db: Session, rule, records: list[dict]) -> None:
    """批量邮件：每次执行只发一封，汇总所有命中记录。"""
    cfg = get_setting(db, "smtp")
    action = rule.action_json or {}
    send_smtp(cfg, resolve_recipients_multi(action, records),
              f"【{rule.name}】提醒（{len(records)} 条）", render_batch_body(action, records))


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


def act_sms_batch(db: Session, rule, records: list[dict]) -> None:
    """批量短信：每个手机号只发一条，正文汇总所有命中记录。"""
    tpl = get_setting(db, "sms_gateway").get("url_template")
    if not tpl:
        raise ActionError("未配置短信网关，请到「模型设置-通知渠道」中配置 URL 模板")
    action = rule.action_json or {}
    phones = resolve_recipients_multi(action, records)
    if not phones:
        raise ActionError("没有可用的手机号")
    content = render_batch_body(action, records)
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

# 每次执行只发一次、汇总所有命中记录的动作（邮件/短信）；通知/Webhook 保持逐条触发
BATCH_ACTION_FUNCS = {
    "email": act_email_batch,
    "sms": act_sms_batch,
}

ACTION_LABELS = {"notify": "站内通知", "email": "邮件", "sms": "短信", "webhook": "Webhook"}
