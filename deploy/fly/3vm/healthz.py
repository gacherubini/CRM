#!/usr/bin/env python3
"""Health agregado da VM app.

Fly check aponta aqui via nginx :8080/healthz.
Por default exige chatbot+estoque (path do bot). n8n é opcional
(HEALTH_REQUIRE_N8N=1) porque sobe mais devagar e a grace do Fly é ~60s.
"""
from __future__ import annotations

import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

CHECKS = [
    ("chatbot", os.getenv("HEALTH_CHATBOT_URL", "http://127.0.0.1:8001/health/ready")),
    ("estoque", os.getenv("HEALTH_ESTOQUE_URL", "http://127.0.0.1:8002/health/ready")),
    ("portal", os.getenv("HEALTH_PORTAL_URL", "http://127.0.0.1:9000/health/ready")),
    ("revy-trafego", os.getenv("HEALTH_REVY_TRAFEGO_URL", "http://127.0.0.1:9010/health/ready")),
]
if os.getenv("HEALTH_REQUIRE_N8N", "0").strip() in {"1", "true", "yes", "on"}:
    CHECKS.append(
        ("n8n", os.getenv("HEALTH_N8N_URL", "http://127.0.0.1:5678/healthz"))
    )

PORT = int(os.getenv("HEALTHZ_PORT", "8099"))

# Carimbo do Dockerfile.app (ARG GIT_SHA). Sem ele nao ha como perguntar a prod
# qual commit ela roda — foi assim que prod e repo divergiram sem ninguem ver.
GIT_SHA = os.getenv("REVY_GIT_SHA", "desconhecido")


def _ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2.5) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path not in ("/healthz", "/"):
            self.send_response(404)
            self.end_headers()
            return
        bad = [name for name, url in CHECKS if not _ok(url)]
        if bad:
            body = ("fail:" + ",".join(bad) + "\n").encode()
            self.send_response(503)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = f"ok sha:{GIT_SHA}\n".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return


def main() -> None:
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
