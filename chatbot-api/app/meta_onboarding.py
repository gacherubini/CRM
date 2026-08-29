"""Os quatro elos do embedded signup que falam com a Graph API (spec §7).

Cliente HTTP puro: não conhece banco, não decide retomada, não cifra nada.
Quem faz isso é ``app/onboarding_cloud.py``. A separação é o que permite testar
a cadeia sem HTTP e o HTTP sem banco.

Erro daqui é sempre ``OnboardingErro`` com o número do elo, porque a tela do
lojista precisa nomear **qual** passo parou e de quem é a vez (spec §6).

Nada do corpo de erro da Meta entra na mensagem: ele ecoa os parâmetros
enviados, e um deles é o App Secret.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any

import httpx

from app import config

# Erros da Meta que significam "já estava feito". Repetir um elo idempotente é
# o caminho normal da retomada — tratar isto como falha vira laço.
_JA_FEITO = {
    "already subscribed",
    "template name already exists",
}
# error_subcode de template com nome repetido.
_SUBCODE_TEMPLATE_EXISTE = 2388023
# Teto de registros por número numa janela móvel de 72 h estourado.
_CODIGO_TETO_REGISTRO = 133016

TEXTO_TEMPLATE = (
    "Oi {{1}}, chegou um lead novo pra você. Toque em Peguei para assumir."
)


class _SemSegredoNoLog(logging.Filter):
    """Descarta o registro de log que contiver um dos segredos dados.

    Existe por causa do ``httpx``: ele loga ``request.url`` inteira em INFO, e
    a URL do elo 1 leva ``client_secret`` e ``code`` na query string. Isso sai
    no caminho **feliz**, sem erro nenhum.

    Hoje não aparece em produção por acaso — nada em ``app/`` chama
    ``basicConfig`` e o dictConfig padrão do uvicorn deixa o root em WARNING.
    Um ``--log-level debug`` para depurar outra coisa poria o App Secret no
    stdout do Fly. O invariante do repo (AGENTS.md §5) não admite esse acaso.

    Descarta a linha inteira em vez de redigir: a única linha atingida é a que
    contém o segredo, e ela não tem valor de diagnóstico sem ele.
    """

    def __init__(self, *segredos: str) -> None:
        super().__init__()
        self._segredos = tuple(s for s in segredos if s)

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._segredos:
            return True
        try:
            texto = record.getMessage()
        except Exception:  # noqa: BLE001 - log quebrado não pode derrubar o elo
            return True
        return not any(segredo in texto for segredo in self._segredos)


@contextmanager
def _log_sem(*segredos: str):
    """Silencia, só durante a chamada, a linha de log que carregaria o segredo."""
    filtro = _SemSegredoNoLog(*segredos)
    log = logging.getLogger("httpx")
    log.addFilter(filtro)
    try:
        yield
    finally:
        log.removeFilter(filtro)


class OnboardingErro(RuntimeError):
    """Falha num elo nomeado da cadeia."""

    def __init__(self, mensagem: str, *, elo: int) -> None:
        super().__init__(mensagem)
        self.elo = elo


class MetaOnboarding:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        app_id: str | None = None,
        app_secret: str | None = None,
        timeout: float = 15,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or config.GRAPH_BASE_URL).rstrip("/")
        self.app_id = app_id or config.META_APP_ID
        self.app_secret = app_secret or config.META_APP_SECRET
        self.timeout = timeout
        self._transport = transport

    def _cliente(self, token: str | None = None) -> httpx.Client:
        cabecalhos = {"Authorization": f"Bearer {token}"} if token else {}
        return httpx.Client(
            timeout=self.timeout, transport=self._transport, headers=cabecalhos
        )

    @staticmethod
    def _erro_da_meta(resposta: httpx.Response) -> dict[str, Any]:
        try:
            return resposta.json().get("error") or {}
        except ValueError:
            return {}

    def _ja_estava_feito(self, erro: dict[str, Any]) -> bool:
        if erro.get("error_subcode") == _SUBCODE_TEMPLATE_EXISTE:
            return True
        mensagem = str(erro.get("message") or "").lower()
        return any(marca in mensagem for marca in _JA_FEITO)

    # --- elo 1 ------------------------------------------------------------
    def trocar_code_por_token(self, code: str) -> str:
        """``code`` tem TTL de 30 s e **não** é retomável: falhou, volta ao popup."""
        try:
            with self._cliente() as cliente, _log_sem(self.app_secret, code):
                resposta = cliente.get(
                    f"{self.base_url}/oauth/access_token",
                    params={
                        "client_id": self.app_id,
                        "client_secret": self.app_secret,
                        "code": code,
                    },
                )
        except httpx.HTTPError as exc:
            raise OnboardingErro("não deu para falar com a Meta", elo=1) from exc

        token = ""
        if resposta.status_code == 200:
            try:
                token = str(resposta.json().get("access_token") or "")
            except ValueError:
                token = ""
        if not token:
            raise OnboardingErro(
                "a autorização expirou antes de chegar aqui; refaça a conexão", elo=1
            )
        return token

    # --- elo 2 ------------------------------------------------------------
    def inscrever_app(self, *, waba_id: str, token: str) -> None:
        """Idempotente. Falhou calado uma vez (23/08): sem isto o painel testa
        bem e mensagem real nunca chega."""
        self._post_idempotente(
            f"{self.base_url}/{waba_id}/subscribed_apps", token=token, corpo=None, elo=2,
            mensagem="não deu para inscrever o Revy na conta do WhatsApp",
        )

    # --- elo 3 ------------------------------------------------------------
    def registrar_numero(self, *, phone_number_id: str, pin: str, token: str) -> None:
        """Teto de 10 por número em 72 h móveis. Estourar trava o número por
        três dias — quem chama conta as tentativas e para bem antes."""
        try:
            with self._cliente(token) as cliente:
                resposta = cliente.post(
                    f"{self.base_url}/{phone_number_id}/register",
                    json={"messaging_product": "whatsapp", "pin": pin},
                )
        except httpx.HTTPError as exc:
            raise OnboardingErro("não deu para falar com a Meta", elo=3) from exc

        if resposta.status_code == 200:
            return
        erro = self._erro_da_meta(resposta)
        if erro.get("code") == _CODIGO_TETO_REGISTRO:
            raise OnboardingErro(
                "a Meta bloqueou novos registros deste número por 72 horas; "
                "fale com a Revy",
                elo=3,
            )
        raise OnboardingErro("não deu para registrar o número", elo=3)

    # --- elo 4 ------------------------------------------------------------
    def criar_template(
        self, *, waba_id: str, token: str, nome: str = "chama_vendedor"
    ) -> None:
        """Formato travado por ``send_template_button``: uma variável e um
        QUICK_REPLY no índice 0. Divergiu, o envio da oferta falha."""
        self._post_idempotente(
            f"{self.base_url}/{waba_id}/message_templates",
            token=token,
            corpo={
                "name": nome,
                "language": "pt_BR",
                "category": "UTILITY",
                "components": [
                    {"type": "BODY", "text": TEXTO_TEMPLATE},
                    {
                        "type": "BUTTONS",
                        "buttons": [{"type": "QUICK_REPLY", "text": "Peguei"}],
                    },
                ],
            },
            elo=4,
            mensagem="não deu para criar o modelo de mensagem",
        )

    def _post_idempotente(
        self, url: str, *, token: str, corpo: dict[str, Any] | None, elo: int,
        mensagem: str,
    ) -> None:
        try:
            with self._cliente(token) as cliente:
                resposta = cliente.post(url, json=corpo) if corpo else cliente.post(url)
        except httpx.HTTPError as exc:
            raise OnboardingErro("não deu para falar com a Meta", elo=elo) from exc

        if resposta.status_code == 200:
            return
        if self._ja_estava_feito(self._erro_da_meta(resposta)):
            return
        raise OnboardingErro(mensagem, elo=elo)
