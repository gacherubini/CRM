"""O carimbo e a peca que sustenta a skill inteira: sem ele nao ha como saber
o que esta em prod, e 'deployar so o que mudou' vira chute.

Este teste sobe o healthz.py de verdade e le a resposta pela rede. Se alguem
tirar o ARG GIT_SHA do Dockerfile.app ou o REVY_GIT_SHA do healthz, e aqui que
aparece — e nao seis meses depois, com prod e repo ja divergidos.
"""

import os
import re
import subprocess
import sys
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import preflight

RAIZ = preflight.raiz_repo()
HEALTHZ = RAIZ / "deploy" / "fly" / "3vm" / "healthz.py"
DOCKERFILE = RAIZ / "deploy" / "fly" / "3vm" / "Dockerfile.app"


class _SempreOk(BaseHTTPRequestHandler):
    """Faz o papel dos quatro servicos do bundle."""

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *a):  # noqa: A003
        return


def _porta_livre() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _esperar(url: str, tentativas: int = 60) -> str:
    ultimo = None
    for _ in range(tentativas):
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                return r.read().decode()
        except Exception as erro:  # noqa: BLE001
            ultimo = erro
            time.sleep(0.1)
    raise AssertionError(f"{url} nunca respondeu: {ultimo}")


class TestCarimboNoDockerfile(unittest.TestCase):
    def test_dockerfile_recebe_e_exporta_o_sha(self):
        texto = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("ARG GIT_SHA", texto)
        self.assertIn("ENV REVY_GIT_SHA=$GIT_SHA", texto)

    def test_carimbo_fica_depois_das_camadas_caras(self):
        """No topo, cada SHA novo invalidaria o cache do apt-get e do pip e
        todo deploy viraria build do zero."""
        linhas = DOCKERFILE.read_text(encoding="utf-8").splitlines()
        pos_arg = next(i for i, l in enumerate(linhas) if l.startswith("ARG GIT_SHA"))
        pos_pip = max(
            (i for i, l in enumerate(linhas) if "requirements-app.txt" in l), default=-1
        )
        self.assertGreater(pos_arg, pos_pip, "ARG GIT_SHA antes do pip invalida o cache")


class TestHealthzDeVerdade(unittest.TestCase):
    """Sobe o healthz.py como processo e le a resposta pela rede."""

    @classmethod
    def setUpClass(cls):
        cls.porta_stub = _porta_livre()
        cls.stub = HTTPServer(("127.0.0.1", cls.porta_stub), _SempreOk)
        threading.Thread(target=cls.stub.serve_forever, daemon=True).start()

        cls.porta = _porta_livre()
        alvo = f"http://127.0.0.1:{cls.porta_stub}/"
        ambiente = {
            **os.environ,
            "REVY_GIT_SHA": "abc1234",
            "HEALTHZ_PORT": str(cls.porta),
            "HEALTH_CHATBOT_URL": alvo,
            "HEALTH_ESTOQUE_URL": alvo,
            "HEALTH_PORTAL_URL": alvo,
            "HEALTH_REVY_TRAFEGO_URL": alvo,
        }
        cls.proc = subprocess.Popen(
            [sys.executable, str(HEALTHZ)],
            env=ambiente,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        cls.corpo = _esperar(f"http://127.0.0.1:{cls.porta}/healthz")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=10)
        cls.stub.shutdown()

    def test_responde_ok_com_o_sha(self):
        self.assertTrue(self.corpo.startswith("ok"), self.corpo)
        self.assertIn("sha:abc1234", self.corpo)

    def test_o_preflight_consegue_ler_o_que_o_healthz_escreve(self):
        """O contrato entre os dois lados. Se um mudar o formato, quebra aqui."""
        self.assertEqual(preflight.sha_do_healthz(self.corpo), "abc1234")

    def test_continua_sendo_2xx_de_texto_simples(self):
        """O health check do Fly so quer 2xx. O carimbo nao pode ter mudado isso."""
        self.assertNotIn("\n\n", self.corpo)
        self.assertTrue(re.fullmatch(r"ok sha:[\w.\-]+\s*", self.corpo), self.corpo)


if __name__ == "__main__":
    unittest.main()
