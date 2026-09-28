"""通知渠道公共件：渠道设置读写 + SMTP 发送（工作流/报表推送共用）。"""
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from sqlalchemy.orm import Session

from ..models import AppSetting


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
