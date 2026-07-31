from email.message import EmailMessage as MimeMessage
import logging
from dataclasses import replace

from app.email.sender import (
    ConsoleEmailBackend,
    EmailMessage,
    build_mime,
    send_email,
    set_email_backend,
)
from app.config import settings as app_settings
from app.email.sender import SmtpEmailBackend, build_email_backend


class _Capturing:
    def __init__(self):
        self.sent = []

    def send(self, message):
        self.sent.append(message)


def test_build_mime_sets_headers_and_bodies():
    msg = EmailMessage(
        to="gestora@example.com",
        subject="Convite Revy",
        text_body="Acesse: https://x/y",
        html_body="<p>Acesse: <a href='https://x/y'>link</a></p>",
    )
    mime = build_mime(msg, from_addr="no-reply@revy.local", from_name="Revy Control")
    assert isinstance(mime, MimeMessage)
    assert mime["To"] == "gestora@example.com"
    assert mime["Subject"] == "Convite Revy"
    assert mime["From"] == "Revy Control <no-reply@revy.local>"
    assert "https://x/y" in mime.get_body(("plain",)).get_content()
    assert "link" in mime.get_body(("html",)).get_content()


def test_send_email_dispatches_to_installed_backend():
    fake = _Capturing()
    set_email_backend(fake)
    try:
        send_email(EmailMessage(to="a@b.c", subject="s", text_body="t"))
        assert len(fake.sent) == 1
        assert fake.sent[0].to == "a@b.c"
    finally:
        set_email_backend(None)


def test_console_backend_does_not_raise(caplog):
    caplog.set_level(logging.INFO)
    backend = ConsoleEmailBackend(from_addr="no-reply@revy.local", from_name="Revy")
    backend.send(EmailMessage(to="a@b.c", subject="s", text_body="corpo"))
    assert any("a@b.c" in record.getMessage() for record in caplog.records)


class _FakeSmtp:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.started_tls = False
        self.logged_in = None
        self.sent = []
        _FakeSmtp.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, mime):
        self.sent.append(mime)


def test_smtp_backend_starts_tls_logs_in_and_sends():
    _FakeSmtp.instances.clear()
    backend = SmtpEmailBackend(
        host="smtp.example.com", port=587, username="u", password="p",
        use_tls=True, from_addr="no-reply@revy.local", from_name="Revy",
        client_factory=_FakeSmtp,
    )
    backend.send(EmailMessage(to="a@b.c", subject="s", text_body="t"))
    assert len(_FakeSmtp.instances) == 1
    inst = _FakeSmtp.instances[0]
    assert inst.started_tls is True
    assert inst.logged_in == ("u", "p")
    assert inst.sent[0]["To"] == "a@b.c"


def test_factory_picks_smtp_when_configured():
    cfg = replace(
        app_settings, email_backend="smtp", smtp_host="smtp.example.com",
    )
    assert isinstance(build_email_backend(cfg), SmtpEmailBackend)


def test_factory_defaults_to_console():
    cfg = replace(app_settings, email_backend="console")
    assert type(build_email_backend(cfg)).__name__ == "ConsoleEmailBackend"
