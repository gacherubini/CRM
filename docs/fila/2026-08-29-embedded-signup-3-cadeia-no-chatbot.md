# Embedded Signup — Card 3: a cadeia no chatbot-api

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development`
> (recomendado) ou `superpowers:executing-plans` para executar task a task. Os passos usam
> checkbox (`- [ ]`).

**Goal:** o `chatbot-api` ganha a cadeia que transforma o `code` devolvido pelo popup da
Meta num canal Cloud `cloud_pendente` da loja, com token cifrado, número registrado e
template submetido — retomando de onde parou quando um elo falha.

**Architecture:** dois módulos novos e uma rota. `app/meta_onboarding.py` é cliente HTTP
puro (fala com a Graph, não conhece banco); `app/onboarding_cloud.py` é o orquestrador (fala
com o banco, não monta URL). A rota `POST /v1/whatsapp/canais/cloud/onboarding` é fina.
A separação existe para que a suíte teste a cadeia inteira com `httpx.MockTransport`, sem
tocar a Meta.

**Tech Stack:** FastAPI, SQLAlchemy 2, httpx, pytest, `app/segredo_canal.py` (Card 2).

**Spec:** [`../referencia-viva/specs/2026-08-29-embedded-signup-tech-provider-design.md`](../referencia-viva/specs/2026-08-29-embedded-signup-tech-provider-design.md)

**Depende de:** Card 2 (feito — `dadb6be`…`ffc51e7`). **Não** depende do Card 1 nem do
resultado do App Review: tudo aqui é testado com transporte falso.

## Global Constraints

- **Testes a partir de `chatbot-api/`**, senão importa o `app` errado:
  `.venv/bin/python -m pytest -q` (macOS) e `.\.venv\Scripts\python.exe -m pytest -q` (Windows).
- **Nenhuma chamada real à Meta em teste.** Todo teste injeta `transport=httpx.MockTransport(...)`,
  como `CloudWhatsAppOutbound` já faz (`app/whatsapp_outbound.py:238`).
- **Nenhum segredo em log, em `onboarding_erro` ou em rota de leitura.** Corpo de erro da
  Meta pode carregar identificador de token: guarda-se mensagem nossa, não o corpo dela.
- **`evolution_instance` guarda o `phone_number_id`.** Não renomear, não criar coluna nova.
- **O elo 3 tem teto duro.** `POST /{phone_number_id}/register` aceita 10 chamadas por número
  em 72 h móveis; estourar devolve `133016` e trava o número por três dias. Teto do código é
  **5**, e não existe retry automático neste elo.
- A loja sai de `ctx.loja_id`, **nunca do corpo**.
- Ao terminar: `git diff --check`, `git status --short`, e regerar o mapa
  (`cd .claude/skills/revy-research && python gerar_mapa.py`) — este card mexe em rota.

## Divergência deliberada do spec §7

O §7 lista "gravar o canal `cloud_pendente`" como **elo 5**, e no mesmo parágrafo afirma que
"depois do elo 1 o popup nunca mais é necessário — o token já está guardado". As duas coisas
não cabem juntas: se o canal só nasce no fim, uma falha no elo 2 perde o token do elo 1, que
tem TTL de 30 s e **não é retomável** — o lojista volta ao popup, que é exatamente o que o
spec quer evitar.

Neste card **o canal nasce logo depois do elo 1**, já com o token cifrado, e os elos
seguintes avançam `onboarding_elo` nele. A numeração dos elos continua a do spec; o que muda
é quando a linha aparece no banco. `onboarding_elo` passa a significar:

| valor | significa |
|---|---|
| `1` | token do cliente guardado, cifrado — daqui em diante retoma sem popup |
| `2` | app inscrito na WABA |
| `3` | número registrado com PIN |
| `4` | template submetido |
| `5` | cadeia completa; falta só a liberação do Control |

---

### Task 1: cliente HTTP dos quatro elos

**Files:**
- Create: `chatbot-api/app/meta_onboarding.py`
- Modify: `chatbot-api/app/config.py` (só uma leitura de ambiente)
- Test: `chatbot-api/tests/test_meta_onboarding.py`

**Interfaces:**
- Produces:
  ```python
  class OnboardingErro(RuntimeError):
      def __init__(self, mensagem: str, *, elo: int) -> None: ...
      elo: int

  class MetaOnboarding:
      def __init__(self, *, base_url: str | None = None, app_id: str | None = None,
                   app_secret: str | None = None, timeout: float = 15,
                   transport: httpx.BaseTransport | None = None) -> None: ...
      def trocar_code_por_token(self, code: str) -> str: ...                     # elo 1
      def inscrever_app(self, *, waba_id: str, token: str) -> None: ...          # elo 2
      def registrar_numero(self, *, phone_number_id: str, pin: str, token: str) -> None: ...  # elo 3
      def criar_template(self, *, waba_id: str, token: str, nome: str = "chama_vendedor") -> None: ...  # elo 4
  ```
  A Task 4 (orquestrador) chama exatamente estes quatro métodos e trata `OnboardingErro`.

**Por que este módulo não conhece banco:** é o que deixa a Task 4 testar a cadeia inteira
com um duplo em memória, sem HTTP nenhum, e este aqui testar HTTP sem banco nenhum.

- [ ] **Passo 1: escrever o teste que falha**

```python
# chatbot-api/tests/test_meta_onboarding.py
"""Os quatro elos que falam com a Graph (spec §7).

Nenhum teste toca a rede: httpx.MockTransport, mesmo padrao de
CloudWhatsAppOutbound (app/whatsapp_outbound.py:238).

Os elos 2 e 4 sao IDEMPOTENTES de proposito. `subscribed_apps` repetido nao doi
e template ja existente e SUCESSO, nao erro: tratar isso como falha transforma
retry inofensivo em laco.
"""
import json

import httpx
import pytest

from app.meta_onboarding import MetaOnboarding, OnboardingErro


def _cliente(handler):
    return MetaOnboarding(
        base_url="https://graph.test/v21.0",
        app_id="app-1",
        app_secret="segredo-do-revy",
        transport=httpx.MockTransport(handler),
    )


def test_elo_1_troca_code_por_token():
    visto = {}

    def handler(pedido: httpx.Request) -> httpx.Response:
        visto["url"] = str(pedido.url)
        return httpx.Response(200, json={"access_token": "EAAG-token-da-loja"})

    assert _cliente(handler).trocar_code_por_token("code-do-popup") == "EAAG-token-da-loja"
    assert "/oauth/access_token" in visto["url"]
    assert "client_id=app-1" in visto["url"]
    assert "code=code-do-popup" in visto["url"]


def test_elo_1_sem_token_na_resposta_e_erro_do_elo_1():
    """Resposta 200 sem access_token existe: o code expirou (TTL 30 s)."""
    handler = lambda pedido: httpx.Response(200, json={})

    with pytest.raises(OnboardingErro) as erro:
        _cliente(handler).trocar_code_por_token("code-velho")
    assert erro.value.elo == 1


def test_elo_1_nao_vaza_o_app_secret_na_mensagem_de_erro():
    """Corpo de erro da Meta ecoa parametros. A mensagem e nossa, nao a dela."""
    handler = lambda pedido: httpx.Response(
        400, json={"error": {"message": "invalid client_secret segredo-do-revy"}}
    )

    with pytest.raises(OnboardingErro) as erro:
        _cliente(handler).trocar_code_por_token("code-do-popup")
    assert "segredo-do-revy" not in str(erro.value)


def test_elo_2_inscreve_o_app_na_waba():
    visto = {}

    def handler(pedido: httpx.Request) -> httpx.Response:
        visto["url"] = str(pedido.url)
        visto["auth"] = pedido.headers.get("authorization")
        return httpx.Response(200, json={"success": True})

    _cliente(handler).inscrever_app(waba_id="waba-1", token="EAAG-token-da-loja")

    assert visto["url"].endswith("/waba-1/subscribed_apps")
    # O token e o DA LOJA, nao o global do Revy: e o que da escopo na WABA dela.
    assert visto["auth"] == "Bearer EAAG-token-da-loja"


def test_elo_2_ja_inscrito_nao_e_erro():
    """Idempotente: repetir nao doi. Foi este elo que falhou calado em 23/08."""
    handler = lambda pedido: httpx.Response(
        400, json={"error": {"code": 100, "message": "already subscribed"}}
    )

    _cliente(handler).inscrever_app(waba_id="waba-1", token="tok")


def test_elo_3_registra_com_pin():
    visto = {}

    def handler(pedido: httpx.Request) -> httpx.Response:
        visto["url"] = str(pedido.url)
        visto["corpo"] = json.loads(pedido.content)
        return httpx.Response(200, json={"success": True})

    _cliente(handler).registrar_numero(
        phone_number_id="123", pin="048512", token="tok"
    )

    assert visto["url"].endswith("/123/register")
    assert visto["corpo"] == {"messaging_product": "whatsapp", "pin": "048512"}


def test_elo_3_teto_da_meta_vira_erro_nomeado():
    """133016 = teto de 10/72h estourado. O numero fica travado por tres dias,
    entao quem chama precisa distinguir isto de uma falha qualquer."""
    handler = lambda pedido: httpx.Response(
        400, json={"error": {"code": 133016, "message": "rate limit"}}
    )

    with pytest.raises(OnboardingErro) as erro:
        _cliente(handler).registrar_numero(phone_number_id="123", pin="048512", token="tok")
    assert erro.value.elo == 3
    assert "72" in str(erro.value), "a mensagem tem de dizer ao lojista quanto tempo"


def test_elo_4_cria_o_template_no_formato_do_envio():
    """Tem de casar com send_template_button (whatsapp_outbound.py:289): uma
    variavel no corpo e um QUICK_REPLY no indice 0. Divergiu, o envio falha."""
    visto = {}

    def handler(pedido: httpx.Request) -> httpx.Response:
        visto["url"] = str(pedido.url)
        visto["corpo"] = json.loads(pedido.content)
        return httpx.Response(200, json={"id": "tpl-1", "status": "PENDING"})

    _cliente(handler).criar_template(waba_id="waba-1", token="tok")

    assert visto["url"].endswith("/waba-1/message_templates")
    corpo = visto["corpo"]
    assert corpo["name"] == "chama_vendedor"
    assert corpo["language"] == "pt_BR"
    # UTILITY e o que segura o custo: como MARKETING cada oferta custa ~10x.
    assert corpo["category"] == "UTILITY"
    tipos = [c["type"] for c in corpo["components"]]
    assert "BODY" in tipos and "BUTTONS" in tipos
    corpo_txt = next(c for c in corpo["components"] if c["type"] == "BODY")["text"]
    assert "{{1}}" in corpo_txt
    botoes = next(c for c in corpo["components"] if c["type"] == "BUTTONS")["buttons"]
    assert botoes == [{"type": "QUICK_REPLY", "text": "Peguei"}]


def test_elo_4_template_ja_existente_e_sucesso():
    handler = lambda pedido: httpx.Response(
        400, json={"error": {"code": 100, "error_subcode": 2388023,
                             "message": "template name already exists"}}
    )

    _cliente(handler).criar_template(waba_id="waba-1", token="tok")
```

- [ ] **Passo 2: rodar e ver falhar**

Rode: `.\.venv\Scripts\python.exe -m pytest tests/test_meta_onboarding.py -q`
Esperado: erro de coleta — `ModuleNotFoundError` / `ImportError` em `app.meta_onboarding`.

- [ ] **Passo 3: acrescentar o App ID ao config**

Em `chatbot-api/app/config.py`, junto de `META_APP_SECRET` (hoje linha 78):

```python
# App ID do app da Revy na Meta. Não é segredo (vai no popup do lado do
# navegador), mas o elo 1 do onboarding precisa dele como ``client_id``.
META_APP_ID = os.getenv("CHATBOT_META_APP_ID", "")
```

- [ ] **Passo 4: escrever o módulo**

```python
# chatbot-api/app/meta_onboarding.py
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
            with self._cliente() as cliente:
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
```

- [ ] **Passo 5: rodar e ver passar**

Rode: `.\.venv\Scripts\python.exe -m pytest tests/test_meta_onboarding.py -q`
Esperado: 9 passed.

- [ ] **Passo 6: commitar**

```bash
git add chatbot-api/app/meta_onboarding.py chatbot-api/app/config.py chatbot-api/tests/test_meta_onboarding.py
git commit -m "feat(onboarding): os quatro elos que falam com a Graph, sem tocar banco"
```

---

### Task 2: o orquestrador, com retomada e teto

**Files:**
- Create: `chatbot-api/app/onboarding_cloud.py`
- Test: `chatbot-api/tests/test_onboarding_cloud.py`

**Interfaces:**
- Consumes: `MetaOnboarding` e `OnboardingErro` (Task 1), `segredo_canal.cifrar` (Card 2),
  as colunas `onboarding_elo` / `onboarding_erro` / `token_cifrado` / `pin_cifrado` /
  `registro_tentativas` / `business_id` (Card 2).
- Produces:
  ```python
  TETO_REGISTRO: int = 5

  def conectar(db: Session, loja_id: str, *, code: str, waba_id: str,
               phone_number_id: str, business_id: str,
               meta: MetaOnboarding | None = None) -> WhatsAppCanal: ...
  ```
  A Task 3 (rota) chama só `conectar` e transforma `OnboardingErro` em resposta HTTP.

**Regras que o teste trava:**
1. O canal nasce logo depois do elo 1, com o token cifrado (ver a divergência do §7 no topo
   deste card). Sem isso não há retomada.
2. Retomada: chamar de novo com o canal em `onboarding_elo=2` **não** repete o elo 1 — não
   há como, o `code` já morreu.
3. O PIN é gerado uma vez e reusado na retomada. PIN novo a cada tentativa é PIN perdido, e
   PIN perdido trava o re-registro do número para sempre.
4. `registro_tentativas` incrementa **antes** da chamada do elo 3, e em `TETO_REGISTRO` a
   cadeia para sem chamar a Meta.
5. Nada do corpo da Meta em `onboarding_erro`.

- [ ] **Passo 1: escrever o teste que falha**

```python
# chatbot-api/tests/test_onboarding_cloud.py
"""A cadeia do embedded signup, sem HTTP (spec §7).

O cliente da Meta e um duplo em memoria: aqui se testa ORDEM, RETOMADA e TETO,
nao formato de corpo — isso e do test_meta_onboarding.py.
"""
import pytest

from app import onboarding_cloud, segredo_canal
from app.meta_onboarding import OnboardingErro
from app.models_db import WhatsAppCanal

CHAVE = "LvALLRsc3ZykD4ZrrFrm25elgLGhYThKQ7Z2ili9KYw="


@pytest.fixture(autouse=True)
def _chave(monkeypatch):
    monkeypatch.setattr(segredo_canal.config, "CANAL_SECRET_KEY", CHAVE)


class _MetaFalsa:
    """Registra a ordem das chamadas. `falhar_em` para no elo pedido."""

    def __init__(self, falhar_em: int | None = None):
        self.chamadas: list[str] = []
        self.falhar_em = falhar_em
        self.pins: list[str] = []

    def _talvez_falhar(self, elo: int):
        if self.falhar_em == elo:
            raise OnboardingErro(f"falhou no elo {elo}", elo=elo)

    def trocar_code_por_token(self, code):
        self.chamadas.append("elo1")
        self._talvez_falhar(1)
        return "EAAG-token-da-loja"

    def inscrever_app(self, *, waba_id, token):
        self.chamadas.append("elo2")
        self._talvez_falhar(2)

    def registrar_numero(self, *, phone_number_id, pin, token):
        self.chamadas.append("elo3")
        self.pins.append(pin)
        self._talvez_falhar(3)

    def criar_template(self, *, waba_id, token, nome="chama_vendedor"):
        self.chamadas.append("elo4")
        self._talvez_falhar(4)


def _conectar(db, loja_id, meta, **troca):
    dados = dict(
        code="code-do-popup",
        waba_id="waba-1",
        phone_number_id="1227059273831590",
        business_id="biz-1",
    )
    dados.update(troca)
    return onboarding_cloud.conectar(db, loja_id, meta=meta, **dados)


def test_cadeia_completa_deixa_o_canal_pendente(db, loja_a):
    meta = _MetaFalsa()

    canal = _conectar(db, loja_a["loja_id"], meta)

    assert meta.chamadas == ["elo1", "elo2", "elo3", "elo4"]
    # `evolution_instance` guarda o phone_number_id no Modo 2 (spec §16.3).
    assert canal.evolution_instance == "1227059273831590"
    assert canal.waba_id == "waba-1"
    assert canal.business_id == "biz-1"
    assert canal.onboarding_elo == 5
    assert canal.onboarding_erro is None
    # Pendente, nao ativo: quem ativa e a projecao do Control (Card 2, spec §9).
    assert canal.estado == "cloud_pendente"


def test_o_token_fica_cifrado_e_abre():
    """Sanidade do contrato com o Card 2: nao adianta cifrar e nao conseguir ler."""
    assert segredo_canal.decifrar(segredo_canal.cifrar("EAAG-x")) == "EAAG-x"


def test_token_nao_fica_em_claro_no_banco(db, loja_a):
    canal = _conectar(db, loja_a["loja_id"], _MetaFalsa())

    assert canal.token_cifrado
    assert "EAAG-token-da-loja" not in canal.token_cifrado
    assert segredo_canal.decifrar(canal.token_cifrado) == "EAAG-token-da-loja"


def test_falha_no_elo_2_guarda_onde_parou_e_o_token(db, loja_a):
    """O ponto da divergencia do §7: o elo 1 nao e retomavel, entao o canal tem
    de existir com o token ANTES do elo 2."""
    canal = None
    with pytest.raises(OnboardingErro):
        _conectar(db, loja_a["loja_id"], _MetaFalsa(falhar_em=2))

    canal = db.query(WhatsAppCanal).filter_by(loja_id=loja_a["loja_id"],
                                              waba_id="waba-1").one()
    assert canal.onboarding_elo == 1
    assert canal.onboarding_erro
    assert canal.token_cifrado, "sem isto a retomada exigiria o popup de novo"
    assert canal.estado == "cloud_pendente"


def test_retomada_nao_repete_o_elo_1(db, loja_a):
    with pytest.raises(OnboardingErro):
        _conectar(db, loja_a["loja_id"], _MetaFalsa(falhar_em=2))

    segunda = _MetaFalsa()
    canal = _conectar(db, loja_a["loja_id"], segunda, code="code-ja-morto")

    assert segunda.chamadas == ["elo2", "elo3", "elo4"]
    assert canal.onboarding_elo == 5
    assert canal.onboarding_erro is None


def test_retomada_reusa_o_mesmo_pin(db, loja_a):
    """PIN novo a cada tentativa e PIN perdido, e PIN perdido trava o
    re-registro do numero para sempre."""
    primeira = _MetaFalsa(falhar_em=3)
    with pytest.raises(OnboardingErro):
        _conectar(db, loja_a["loja_id"], primeira)

    segunda = _MetaFalsa()
    _conectar(db, loja_a["loja_id"], segunda, code="code-ja-morto")

    assert primeira.pins == segunda.pins
    assert len(primeira.pins[0]) == 6 and primeira.pins[0].isdigit()


def test_o_teto_do_elo_3_para_antes_de_chamar_a_meta(db, loja_a):
    """133016 trava o numero por 72 h. O teto e do NOSSO lado, bem abaixo de 10."""
    for _ in range(onboarding_cloud.TETO_REGISTRO):
        with pytest.raises(OnboardingErro):
            _conectar(db, loja_a["loja_id"], _MetaFalsa(falhar_em=3))

    ultima = _MetaFalsa()
    with pytest.raises(OnboardingErro) as erro:
        _conectar(db, loja_a["loja_id"], ultima, code="code-ja-morto")

    assert "elo3" not in ultima.chamadas, "estourou o teto e chamou a Meta assim mesmo"
    assert erro.value.elo == 3

    canal = db.query(WhatsAppCanal).filter_by(loja_id=loja_a["loja_id"],
                                              waba_id="waba-1").one()
    assert canal.registro_tentativas == onboarding_cloud.TETO_REGISTRO


def test_numero_de_outra_loja_nao_e_sequestrado(db, loja_a, loja_b):
    """`evolution_instance` e UNIQUE de proposito: um numero, uma loja."""
    _conectar(db, loja_a["loja_id"], _MetaFalsa())

    with pytest.raises(OnboardingErro):
        _conectar(db, loja_b["loja_id"], _MetaFalsa())
```

- [ ] **Passo 2: rodar e ver falhar**

Rode: `.\.venv\Scripts\python.exe -m pytest tests/test_onboarding_cloud.py -q`
Esperado: erro de coleta — `ImportError` em `app.onboarding_cloud`.

- [ ] **Passo 3: escrever o orquestrador**

```python
# chatbot-api/app/onboarding_cloud.py
"""A cadeia do embedded signup, do lado do banco (spec §7).

Não monta URL e não conhece httpx: quem fala com a Graph é
``app/meta_onboarding.py``. Aqui moram a ordem dos elos, a retomada e o teto.

**O canal nasce depois do elo 1, não no fim.** O ``code`` do popup tem TTL de
30 s e não é retomável; se o canal só aparecesse no fim, uma falha no elo 2
perderia o token e mandaria o lojista de volta ao popup — o oposto do que o
spec §7 promete ("depois do elo 1 o popup nunca mais é necessário").
"""
from __future__ import annotations

import secrets
import uuid

from sqlalchemy.orm import Session

from app import segredo_canal
from app.meta_onboarding import MetaOnboarding, OnboardingErro
from app.models_db import WhatsAppCanal

# A Meta aceita 10 registros por número em 72 h móveis e trava o número por três
# dias ao estourar (133016). Paramos em 5: o custo do erro é do lojista, em dias
# sem WhatsApp, e nenhuma tentativa nossa vale isso.
TETO_REGISTRO = 5


def _pin_novo() -> str:
    """Seis dígitos. ``secrets``, não ``random``: é credencial."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _canal_da_waba(db: Session, loja_id: str, waba_id: str) -> WhatsAppCanal | None:
    return (
        db.query(WhatsAppCanal)
        .filter(WhatsAppCanal.loja_id == loja_id, WhatsAppCanal.waba_id == waba_id)
        .first()
    )


def _parar(db: Session, canal: WhatsAppCanal, erro: OnboardingErro) -> None:
    """Grava onde parou. A mensagem é NOSSA — corpo de erro da Meta ecoa os
    parâmetros enviados, e um deles é o App Secret."""
    canal.onboarding_erro = str(erro)[:200]
    db.commit()
    raise erro


def conectar(
    db: Session,
    loja_id: str,
    *,
    code: str,
    waba_id: str,
    phone_number_id: str,
    business_id: str,
    meta: MetaOnboarding | None = None,
) -> WhatsAppCanal:
    meta = meta or MetaOnboarding()
    canal = _canal_da_waba(db, loja_id, waba_id)

    # --- elo 1: só na primeira vez. Depois dele o popup não é mais necessário.
    if canal is None:
        dono = (
            db.query(WhatsAppCanal)
            .filter(WhatsAppCanal.evolution_instance == phone_number_id)
            .first()
        )
        if dono is not None:
            raise OnboardingErro(
                "este número já está conectado a outra loja", elo=1
            )
        token = meta.trocar_code_por_token(code)
        canal = WhatsAppCanal(
            id=str(uuid.uuid4()),
            loja_id=loja_id,
            e164_or_label=phone_number_id,
            evolution_instance=phone_number_id,
            waba_id=waba_id,
            business_id=business_id,
            estado="cloud_pendente",
            onboarding_elo=1,
            token_cifrado=segredo_canal.cifrar(token),
            pin_cifrado=segredo_canal.cifrar(_pin_novo()),
        )
        db.add(canal)
        db.commit()

    token = segredo_canal.decifrar(canal.token_cifrado)
    pin = segredo_canal.decifrar(canal.pin_cifrado)
    canal.onboarding_erro = None

    # --- elo 2: idempotente, repetir não dói.
    if (canal.onboarding_elo or 0) < 2:
        try:
            meta.inscrever_app(waba_id=waba_id, token=token)
        except OnboardingErro as erro:
            _parar(db, canal, erro)
        canal.onboarding_elo = 2
        db.commit()

    # --- elo 3: teto nosso, bem abaixo do da Meta. Sem retry automático.
    if (canal.onboarding_elo or 0) < 3:
        if canal.registro_tentativas >= TETO_REGISTRO:
            _parar(
                db,
                canal,
                OnboardingErro(
                    "já tentamos registrar este número vezes demais; fale com a "
                    "Revy antes de tentar de novo",
                    elo=3,
                ),
            )
        canal.registro_tentativas += 1
        db.commit()
        try:
            meta.registrar_numero(
                phone_number_id=phone_number_id, pin=pin, token=token
            )
        except OnboardingErro as erro:
            _parar(db, canal, erro)
        canal.onboarding_elo = 3
        db.commit()

    # --- elo 4: template já existente é sucesso, não erro.
    if (canal.onboarding_elo or 0) < 4:
        try:
            meta.criar_template(waba_id=waba_id, token=token)
        except OnboardingErro as erro:
            _parar(db, canal, erro)
        canal.onboarding_elo = 4
        canal.template_oferta = "chama_vendedor"
        db.commit()

    canal.onboarding_elo = 5
    db.commit()
    return canal
```

- [ ] **Passo 4: rodar e ver passar**

Rode: `.\.venv\Scripts\python.exe -m pytest tests/test_onboarding_cloud.py -q`
Esperado: 8 passed.

- [ ] **Passo 5: provar que os testes de retomada testam o que dizem**

Comente o `if (canal.onboarding_elo or 0) < 2:` e rode de novo. `test_retomada_nao_repete_o_elo_1`
tem de ficar vermelho. Restaure. **Isto não é zelo:** no Card 2 quatro testes passaram com
metade de um gancho apagada, e é como o learning
`2026-08-29-o-conftest-do-chatbot-nao-semeia-todo-aggregate.md` nasceu.

- [ ] **Passo 6: commitar**

```bash
git add chatbot-api/app/onboarding_cloud.py chatbot-api/tests/test_onboarding_cloud.py
git commit -m "feat(onboarding): a cadeia retoma de onde parou, e o elo 3 tem teto"
```

---

### Task 3: a rota, e o webhook do status do template

**Files:**
- Modify: `chatbot-api/app/main.py`
- Test: `chatbot-api/tests/test_rota_onboarding_cloud.py`

**Interfaces:**
- Consumes: `onboarding_cloud.conectar` (Task 2).
- Produces: `POST /v1/whatsapp/canais/cloud/onboarding` e o tratamento de
  `message_template_status_update` no webhook que já existe (`main.py:554`).

**Invariantes:**
- **A loja sai de `ctx.loja_id`, nunca do corpo.** Credencial de integração tem
  `loja_id = None`: responda **400 dizendo o quê**, antes de qualquer gate operacional —
  senão o 423 do gate engole o erro de verdade (learning
  `2026-08-24-instance-nao-conserta-toda-rota.md`).
- **Nenhum segredo na resposta.** Ela devolve estado e elo, nunca token nem PIN.
- O webhook **não ganha rota nova**: `message_template_status_update` entra no
  `POST /webhook/cloud` que já existe e já valida a assinatura.

- [ ] **Passo 1: escrever o teste que falha**

```python
# chatbot-api/tests/test_rota_onboarding_cloud.py
"""POST /v1/whatsapp/canais/cloud/onboarding (spec §4).

A loja sai da CREDENCIAL, nunca do corpo. E a resposta nao carrega segredo: a
tela de numeros da Loja mostra este JSON.
"""
import uuid

from app import main, onboarding_cloud, segredo_canal
from app.meta_onboarding import OnboardingErro
from app.models_db import WhatsAppCanal

CHAVE = "LvALLRsc3ZykD4ZrrFrm25elgLGhYThKQ7Z2ili9KYw="

CORPO = {
    "code": "code-do-popup",
    "waba_id": "waba-1",
    "phone_number_id": "1227059273831591",
    "business_id": "biz-1",
}


def test_rota_conecta_e_devolve_o_estado(client, db, loja_a, monkeypatch):
    def _falso(db_, loja_id, **kwargs):
        assert loja_id == loja_a["loja_id"], "a loja tem de vir da credencial"
        canal = WhatsAppCanal(
            id=str(uuid.uuid4()), loja_id=loja_id, e164_or_label="linha-cloud",
            evolution_instance=kwargs["phone_number_id"], waba_id=kwargs["waba_id"],
            estado="cloud_pendente", onboarding_elo=5,
        )
        db_.add(canal)
        db_.commit()
        return canal

    monkeypatch.setattr(main.onboarding_cloud, "conectar", _falso)

    resposta = client.post(
        "/v1/whatsapp/canais/cloud/onboarding", json=CORPO, headers=loja_a["headers"]
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["estado"] == "cloud_pendente"
    assert corpo["onboarding_elo"] == 5
    for proibido in ("token", "pin", "token_cifrado", "pin_cifrado", "code"):
        assert proibido not in corpo


def test_falha_de_elo_vira_erro_com_o_elo_nomeado(client, loja_a, monkeypatch):
    """A tela precisa dizer QUAL passo parou e de quem e a vez (spec §6)."""
    def _falso(db_, loja_id, **kwargs):
        raise OnboardingErro("nao deu para registrar o numero", elo=3)

    monkeypatch.setattr(main.onboarding_cloud, "conectar", _falso)

    resposta = client.post(
        "/v1/whatsapp/canais/cloud/onboarding", json=CORPO, headers=loja_a["headers"]
    )

    assert resposta.status_code == 502
    assert resposta.json()["detail"]["elo"] == 3


def test_corpo_incompleto_nao_chega_no_orquestrador(client, loja_a):
    resposta = client.post(
        "/v1/whatsapp/canais/cloud/onboarding",
        json={"code": "x"},
        headers=loja_a["headers"],
    )
    assert resposta.status_code == 422
```

Se o `conftest` tiver fixture de credencial de integração (`ctx.loja_id is None`), acrescente
também um teste de que a rota responde **400** — e não 423 — nesse caso. Se não tiver, **não
invente fixture**: registre no relatório que esse caminho ficou sem teste.

- [ ] **Passo 2: rodar e ver falhar**

Rode: `.\.venv\Scripts\python.exe -m pytest tests/test_rota_onboarding_cloud.py -q`
Esperado: FAIL — `AttributeError: module 'app.main' has no attribute 'onboarding_cloud'`,
ou 404 na rota.

- [ ] **Passo 3: escrever a rota**

Em `app/main.py`, junto das outras rotas de `/v1/whatsapp/canais` (hoje a partir da linha
1772), com o import de `onboarding_cloud` no topo:

```python
class OnboardingCloudInput(BaseModel):
    """O que o popup da Meta devolve ao navegador. A loja NÃO vem aqui."""

    code: str = Field(min_length=1, max_length=512)
    waba_id: str = Field(min_length=1, max_length=60)
    phone_number_id: str = Field(min_length=1, max_length=60)
    business_id: str = Field(min_length=1, max_length=60)


@app.post("/v1/whatsapp/canais/cloud/onboarding")
def conectar_canal_cloud(
    dados: OnboardingCloudInput,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    """Roda a cadeia do embedded signup para a loja da credencial (spec §7).

    O 400 vem antes de qualquer gate operacional de propósito: com credencial
    de integração ``ctx.loja_id`` é ``None`` e o gate responderia 423,
    engolindo o erro que diz o que de fato falta.
    """
    if not ctx.loja_id:
        raise HTTPException(
            status_code=400,
            detail="esta rota exige credencial de loja, não de integração",
        )
    try:
        canal = onboarding_cloud.conectar(
            db,
            ctx.loja_id,
            code=dados.code,
            waba_id=dados.waba_id,
            phone_number_id=dados.phone_number_id,
            business_id=dados.business_id,
        )
    except OnboardingErro as erro:
        # 502: quem falhou foi a Meta, não o pedido do lojista.
        raise HTTPException(
            status_code=502, detail={"elo": erro.elo, "mensagem": str(erro)}
        ) from erro
    return {
        "canal_id": canal.id,
        "estado": canal.estado,
        "onboarding_elo": canal.onboarding_elo,
        "onboarding_erro": canal.onboarding_erro,
        "template_oferta": canal.template_oferta,
    }
```

- [ ] **Passo 4: rodar e ver passar**

Rode: `.\.venv\Scripts\python.exe -m pytest tests/test_rota_onboarding_cloud.py -q`
Esperado: 3 passed (4 se você acrescentou o da credencial de integração).

- [ ] **Passo 5: o status do template no webhook**

Acrescente ao teste:

```python
def test_webhook_aprova_o_template_do_canal(client, db, loja_a, monkeypatch):
    """A aprovacao chega por webhook, no /webhook/cloud que ja existe.

    Sem isto a tela `pendente` manda o lojista olhar o painel da Meta — que e
    exatamente o que este projeto existe para acabar.
    """
    canal = WhatsAppCanal(
        id=str(uuid.uuid4()), loja_id=loja_a["loja_id"], e164_or_label="linha-cloud",
        evolution_instance="1227059273831592", waba_id="waba-1",
        estado="cloud_pendente", onboarding_elo=5,
    )
    db.add(canal)
    db.commit()

    main.aplicar_status_de_template(
        db,
        {
            "field": "message_template_status_update",
            "value": {"event": "APPROVED", "message_template_name": "chama_vendedor"},
        },
        waba_id="waba-1",
    )
    db.refresh(canal)

    assert canal.template_oferta == "chama_vendedor"
```

E implemente `aplicar_status_de_template` em `main.py`, chamada de dentro do
`POST /webhook/cloud` que já existe (linha 554) quando o `field` do change for
`message_template_status_update`. **Não crie rota nova** — a assinatura da Meta já é
validada lá, e uma segunda porta seria uma segunda superfície para autenticar.

**Conferido no código em 29/08, não adivinhe:** `parse_inbound` (`app/meta_webhook.py:50`)
percorre `entry[].changes[]` e lê **só** `value.messages` e `value.statuses` — ele **ignora
`field` por completo**. Um evento de template hoje entra pelo webhook, não vira evento
nenhum e o handler responde `200` calado. E o `waba_id` desses eventos vem em **`entry[].id`**,
não no `value` (que só tem `metadata.phone_number_id`, ausente aqui).

Então o gancho vai **no `webhook_cloud` (`main.py:554`), antes do laço de `parse_inbound`**,
varrendo `payload["entry"]` e casando `mudanca.get("field") == "message_template_status_update"`
com `entrada.get("id")` como `waba_id`. Não mexa em `parse_inbound`: ele devolve `EventoCloud`,
que é vocabulário de mensagem de cliente, e status de template não é mensagem — foi assim que
`statuses` quase virou lead fantasma.

- [ ] **Passo 6: suíte inteira**

Rode: `.\.venv\Scripts\python.exe -m pytest -q`
Esperado: verde.

- [ ] **Passo 7: commitar**

```bash
git add chatbot-api/app/main.py chatbot-api/tests/test_rota_onboarding_cloud.py
git commit -m "feat(onboarding): a rota do embedded signup, e o webhook conta do template"
```

---

### Task 4: fechamento

- [ ] **Passo 1:** suíte do `chatbot-api` verde a partir da pasta do produto.
- [ ] **Passo 2:** `CHATBOT_META_APP_ID` como `[env]` (não é segredo) e
      **`CHATBOT_CANAL_SECRET_KEY` como secret** no `app2037` — esta é a pendência herdada
      do Card 2. Gerar com
      `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
      `fly secrets set` reinicia a máquina: agrupe as duas.
- [ ] **Passo 3:** deploy do `app2037` pela skill `revy-deploy` (o boot roda a `0028` em
      fail-fast). Confirmar o SHA no `/healthz`.
- [ ] **Passo 4:** `git diff --check`, `git status --short`, e regerar o mapa.

## Como saber que acabou

Suíte verde, e a cadeia inteira exercitável sem rede: um teste manda `code`/`waba_id`/
`phone_number_id`/`business_id` e o canal aparece `cloud_pendente` com `onboarding_elo=5`,
token cifrado no banco e nenhum segredo na resposta.

**O que este card NÃO prova:** que a sequência de chamadas está certa contra a Meta de
verdade. Isso é o Card 1 (spike), que depende do App Review sair. Até lá o risco vive nos
formatos de corpo do `test_meta_onboarding.py` — é o arquivo que o spike vai corrigir, e é
por isso que o cliente HTTP está isolado num módulo só dele.
