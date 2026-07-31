from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text_body: str
    html_body: str | None = None


class EmailBackend(Protocol):
    def send(self, message: EmailMessage) -> None: ...


def build_mime(message: EmailMessage, from_addr: str, from_name: str) -> MimeMessage:
    mime = MimeMessage()
    mime["To"] = message.to
    mime["Subject"] = message.subject
    mime["From"] = f"{from_name} <{from_addr}>" if from_name else from_addr
    mime.set_content(message.text_body)
    if message.html_body:
        mime.add_alternative(message.html_body, subtype="html")
    return mime


@dataclass(frozen=True)
class ConsoleEmailBackend:
    from_addr: str
    from_name: str = ""

    def send(self, message: EmailMessage) -> None:
        logger.info(
            "email(console) para=%s assunto=%s corpo=%s",
            message.to,
            message.subject,
            message.text_body,
        )


_backend: EmailBackend | None = None
@dataclass(frozen=True)
class SmtpEmailBackend:
    host: str
    port: int
    username: str
    password: str
    use_tls: bool
    from_addr: str
    from_name: str = ""
    client_factory: type = smtplib.SMTP

    def send(self, message: EmailMessage) -> None:
        mime = build_mime(message, self.from_addr, self.from_name)
        with self.client_factory(self.host, self.port, timeout=10) as client:
            if self.use_tls:
                client.starttls()
            if self.username:
                client.login(self.username, self.password)
            client.send_message(mime)




def set_email_backend(backend: EmailBackend | None) -> None:
    global _backend
    _backend = backend


def get_email_backend() -> EmailBackend:
    global _backend
    if _backend is None:
        from app.config import settings

        _backend = build_email_backend(settings)
    return _backend


def send_email(message: EmailMessage) -> None:
    get_email_backend().send(message)


def build_email_backend(settings) -> EmailBackend:
    if settings.email_backend == "smtp":
        return SmtpEmailBackend(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            from_addr=settings.email_from,
            from_name=settings.email_from_name,
        )

    return ConsoleEmailBackend(
        from_addr=settings.email_from,
        from_name=settings.email_from_name,
    )
