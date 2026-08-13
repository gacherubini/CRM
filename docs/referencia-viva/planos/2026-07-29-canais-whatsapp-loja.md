# Canais WhatsApp na Loja — Implementation Plan (Parte A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O dono/gerente da loja cadastra, pareia (QR real) e reconecta números de WhatsApp por tela própria, sem `curl` e sem admin Revy no meio.

**Architecture:** `register_channel` no Chatbot continua puramente de banco (persiste `estado=pendente`); toda I/O com a Evolution vive em `connect`, que faz *ensure instance* antes de pedir o QR. Isso elimina instância órfã, torna o retry idempotente (é só reclicar) e preserva os testes atuais de `register_channel`. A Loja consome os endpoints já existentes `/v1/whatsapp/canais*` com o token da própria loja.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, Alembic, Jinja2, httpx, pytest.

**Spec:** `docs/referencia-viva/specs/2026-07-29-telas-canais-wa-google-design.md` (Parte A)

## Global Constraints

- Flags novas nascem **OFF**: `CHATBOT_WHATSAPP_PROVIDER=stub`, `REVY_LOJA_WHATSAPP_ENABLED=0`.
- **QR nunca vai para log nem para auditoria.** Nem `apikey` da Evolution. Nem em mensagem de exceção.
- Instância Evolution é única globalmente; `loja_id` é imutável após o registro; remoção é lógica (`ativo=False`, `estado=inativo`), nunca `DELETE`.
- `evolution_instance` sanitizada para `[a-z0-9-]` — vira segmento de URL.
- Mudanças de contrato HTTP são **expand-only**: campo obrigatório pode virar opcional, nunca o contrário.
- Rodar testes do serviço a partir do diretório do serviço (`chatbot-api/`, `portal-gestao/`).
- A regra de autorização da Loja é cargo em `{"dono", "gerente"}` (equivalente a `ROLES_GESTAO`).

## File Structure

**chatbot-api**
| Arquivo | Responsabilidade |
|---|---|
| `app/config.py` (modificar) | envs `CHATBOT_WHATSAPP_PROVIDER`, `CHATBOT_EVOLUTION_WEBHOOK_URL` |
| `app/whatsapp_provider.py` (modificar) | `EvolutionWhatsAppProvider`, `WhatsAppProvisionError`, `EVOLUTION_WEBHOOK_EVENTS`, seleção por config |
| `app/channels.py` (modificar) | nome de instância gerado; `connect` faz ensure |
| `app/main.py` (modificar) | `CanalWhatsAppInput.evolution_instance` opcional |
| `tests/test_whatsapp_provider_evolution.py` (criar) | provider contra `httpx.MockTransport` |
| `tests/test_channels.py` (modificar) | geração de nome, ensure no connect |

**portal-gestao**
| Arquivo | Responsabilidade |
|---|---|
| `app/models.py` (modificar) | `CheckConstraint` de `dominio` aceita `canal` |
| `alembic/versions/0015_auditoria_dominio_canal.py` (criar) | recria a check constraint |
| `app/loja_operacao_auditoria.py` (modificar) | `DOMINIO_CANAL`, `ACOES_CANAL`, `registrar_auditoria_canal` |
| `app/config.py` (modificar) | `revy_loja_whatsapp_enabled` |
| `app/clients/chatbot.py` (modificar) | 4 métodos de escrita de canal |
| `app/loja/whatsapp_canais.py` (criar) | read-model: estado → rótulo humano |
| `app/web/loja_whatsapp.py` (criar) | rotas GET/POST + rota fina de status |
| `app/templates/loja/whatsapp_canais.html` (criar) | tela |
| `app/loja/navigation.py` (modificar) | item em Ajustes |
| `app/main.py` (modificar) | `include_router` no fim do arquivo |
| `tests/conftest.py` (modificar) | `ChatbotFake` ganha canais |
| `tests/test_loja_whatsapp_canais.py` (criar) | rotas, gates, banner, QR fora de log |

---

### Task 1: Seam de seleção do provider (Chatbot)

Hoje `get_whatsapp_provider()` devolve sempre o stub. Esta task cria a chave de configuração sem ainda escrever o adapter real, para que todo o resto possa ser testado com o default seguro.

**Files:**
- Modify: `chatbot-api/app/config.py:100-106` (depois do bloco `MULTI_WHATSAPP_ENABLED`)
- Modify: `chatbot-api/app/whatsapp_provider.py:110-123`
- Test: `chatbot-api/tests/test_whatsapp_provider_evolution.py` (criar)

**Interfaces:**
- Consumes: nada.
- Produces: `config.WHATSAPP_PROVIDER: str`, `config.EVOLUTION_WEBHOOK_URL: str`, `whatsapp_provider.get_whatsapp_provider() -> WhatsAppProvider`.

- [ ] **Step 1: Write the failing test**

Criar `chatbot-api/tests/test_whatsapp_provider_evolution.py`:

```python
"""EvolutionWhatsAppProvider: seleção por config e chamadas HTTP (MockTransport)."""
import httpx
import pytest

from app import config, whatsapp_provider
from app.whatsapp_provider import (
    EvolutionStubWhatsAppProvider,
    EvolutionWhatsAppProvider,
    get_whatsapp_provider,
    set_whatsapp_provider,
)


@pytest.fixture(autouse=True)
def _reset_provider():
    set_whatsapp_provider(None)
    yield
    set_whatsapp_provider(None)


def test_default_e_stub(monkeypatch):
    monkeypatch.setattr(config, "WHATSAPP_PROVIDER", "stub")
    assert isinstance(get_whatsapp_provider(), EvolutionStubWhatsAppProvider)


def test_config_evolution_seleciona_adapter_real(monkeypatch):
    monkeypatch.setattr(config, "WHATSAPP_PROVIDER", "evolution")
    assert isinstance(get_whatsapp_provider(), EvolutionWhatsAppProvider)
```

- [ ] **Step 2: Run test to verify it fails**

Run (de `chatbot-api/`): `python -m pytest tests/test_whatsapp_provider_evolution.py -v`
Expected: FAIL com `ImportError: cannot import name 'EvolutionWhatsAppProvider'`

- [ ] **Step 3: Add the config envs**

Em `chatbot-api/app/config.py`, após o bloco `MULTI_WHATSAPP_ENABLED`:

```python
# Provider de conexão de canal: stub (default, sem rede) | evolution (real).
WHATSAPP_PROVIDER = os.getenv("CHATBOT_WHATSAPP_PROVIDER", "stub").strip().lower()
# URL do webhook n8n gravada em instância nova. Um workflow serve N instâncias.
EVOLUTION_WEBHOOK_URL = os.getenv("CHATBOT_EVOLUTION_WEBHOOK_URL", "").strip()
```

- [ ] **Step 4: Add a minimal EvolutionWhatsAppProvider and wire the selection**

Em `chatbot-api/app/whatsapp_provider.py`, adicionar a classe (implementação real vem nas Tasks 2 e 3) e trocar a seleção:

```python
class WhatsAppProvisionError(RuntimeError):
    """Falha ao provisionar/parear canal no provedor. Nunca carrega QR nem apikey."""

    def __init__(self, message: str, *, code: str = "evolution_provision_failed"):
        super().__init__(message)
        self.code = code


class EvolutionWhatsAppProvider:
    """Adapter real da Evolution API. Implementado nas Tasks 2 e 3."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        webhook_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = (
            base_url if base_url is not None else config.EVOLUTION_URL
        ).rstrip("/")
        self.api_key = (
            api_key if api_key is not None else config.EVOLUTION_API_KEY
        ) or ""
        self.webhook_url = (
            webhook_url if webhook_url is not None else config.EVOLUTION_WEBHOOK_URL
        )
        self.timeout = timeout if timeout is not None else config.EVOLUTION_SEND_TIMEOUT
        self.transport = transport
```

Imports novos no topo do arquivo: `import httpx` e `from app import config`.

Substituir `get_whatsapp_provider`:

```python
def get_whatsapp_provider() -> WhatsAppProvider:
    global _provider
    if _provider is None:
        if config.WHATSAPP_PROVIDER == "evolution":
            _provider = EvolutionWhatsAppProvider()
        else:
            _provider = EvolutionStubWhatsAppProvider()
    return _provider
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_whatsapp_provider_evolution.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Run the full chatbot suite (nada deve regredir)**

Run: `python -m pytest -q`
Expected: mesma contagem de passes de antes desta task, 0 falhas.

- [ ] **Step 7: Commit**

```bash
git add chatbot-api/app/config.py chatbot-api/app/whatsapp_provider.py chatbot-api/tests/test_whatsapp_provider_evolution.py
git commit -m "feat(chatbot): seam de selecao do provider WhatsApp por config"
```

---

### Task 2: Provider real — status, connect e disconnect

**Files:**
- Modify: `chatbot-api/app/whatsapp_provider.py`
- Test: `chatbot-api/tests/test_whatsapp_provider_evolution.py`

**Interfaces:**
- Consumes: `EvolutionWhatsAppProvider.__init__` (Task 1), `ConnectResult`, `StatusResult`, `ESTADO_*`.
- Produces: `EvolutionWhatsAppProvider.status(canal) -> StatusResult`, `.connect(canal) -> ConnectResult`, `.disconnect(canal) -> StatusResult`; `WhatsAppProvisionError(message, code=...)`.

Mapeamento de estado da Evolution (`GET /instance/connectionState/{i}` → `{"instance": {"state": "open"}}`):

| `state` da Evolution | estado do canal |
|---|---|
| `open` | `conectado` |
| `connecting` | `pendente` |
| `close` (ou desconhecido) | `desconectado` |

- [ ] **Step 1: Write the failing tests**

Adicionar a `chatbot-api/tests/test_whatsapp_provider_evolution.py`:

```python
from app.models_db import WhatsAppCanal
from app.whatsapp_provider import (
    ESTADO_CONECTADO,
    ESTADO_DESCONECTADO,
    ESTADO_PENDENTE,
    WhatsAppProvisionError,
)


def _canal(instance="loja1-ab12", estado=ESTADO_PENDENTE):
    return WhatsAppCanal(
        id="c1",
        loja_id="l1",
        e164_or_label="linha 2",
        evolution_instance=instance,
        ativo=True,
        estado=estado,
    )


def _provider(handler):
    return EvolutionWhatsAppProvider(
        base_url="http://evo.local",
        api_key="k",
        webhook_url="http://n8n.local/webhook/whatsapp-ai",
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.parametrize(
    "state,esperado",
    [
        ("open", ESTADO_CONECTADO),
        ("connecting", ESTADO_PENDENTE),
        ("close", ESTADO_DESCONECTADO),
        ("qualquer-coisa", ESTADO_DESCONECTADO),
    ],
)
def test_status_mapeia_estados(state, esperado):
    def handler(request):
        assert request.url.path == "/instance/connectionState/loja1-ab12"
        assert request.headers["apikey"] == "k"
        return httpx.Response(200, json={"instance": {"state": state}})

    got = _provider(handler).status(_canal())
    assert got.estado == esperado
    assert got.evolution_instance == "loja1-ab12"


def test_connect_devolve_qr_e_nao_vaza_em_excecao():
    def handler(request):
        if request.url.path == "/instance/fetchInstances":
            return httpx.Response(200, json=[{"name": "loja1-ab12"}])
        assert request.url.path == "/instance/connect/loja1-ab12"
        return httpx.Response(
            200, json={"base64": "QR-SECRETO", "pairingCode": "ABCD-1234", "count": 1}
        )

    got = _provider(handler).connect(_canal())
    assert got.qr_payload == "QR-SECRETO"
    assert got.pairing_code == "ABCD-1234"
    assert got.estado == ESTADO_PENDENTE


def test_disconnect_faz_logout():
    chamadas = []

    def handler(request):
        chamadas.append((request.method, request.url.path))
        return httpx.Response(200, json={"status": "SUCCESS"})

    got = _provider(handler).disconnect(_canal(estado=ESTADO_CONECTADO))
    assert got.estado == ESTADO_DESCONECTADO
    assert ("DELETE", "/instance/logout/loja1-ab12") in chamadas


def test_erro_de_rede_vira_provision_error_sem_expor_url():
    def handler(request):
        raise httpx.ConnectError("boom")

    with pytest.raises(WhatsAppProvisionError) as exc:
        _provider(handler).status(_canal())
    assert exc.value.code == "evolution_unreachable"
    assert "evo.local" not in str(exc.value)


def test_sem_credencial_falha_explicito():
    prov = EvolutionWhatsAppProvider(base_url="", api_key="", webhook_url="")
    with pytest.raises(WhatsAppProvisionError) as exc:
        prov.status(_canal())
    assert exc.value.code == "evolution_not_configured"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_whatsapp_provider_evolution.py -v`
Expected: FAIL — `EvolutionWhatsAppProvider` não tem `status`/`connect`/`disconnect`.

- [ ] **Step 3: Implement the three methods**

Em `EvolutionWhatsAppProvider`, adicionar:

```python
    def _client(self) -> httpx.Client:
        if not self.base_url or not self.api_key:
            raise WhatsAppProvisionError(
                "Evolution não configurada",
                code="evolution_not_configured",
            )
        return httpx.Client(
            base_url=self.base_url,
            headers={"apikey": self.api_key},
            timeout=self.timeout,
            transport=self.transport,
        )

    def _request(self, client: httpx.Client, method: str, path: str, **kwargs):
        try:
            resposta = client.request(method, path, **kwargs)
        except (httpx.HTTPError, OSError) as exc:
            logger.warning(
                "Evolution %s falhou err=%s", path, type(exc).__name__
            )
            raise WhatsAppProvisionError(
                "não foi possível contatar a Evolution",
                code="evolution_unreachable",
            ) from exc
        if resposta.status_code >= 400:
            logger.warning(
                "Evolution %s status=%s", path, resposta.status_code
            )
            raise WhatsAppProvisionError(
                f"Evolution recusou a operação (HTTP {resposta.status_code})",
                code="evolution_provision_failed",
            )
        if not resposta.content:
            return {}
        try:
            return resposta.json()
        except ValueError:
            return {}

    def status(self, canal: WhatsAppCanal) -> StatusResult:
        inst = quote(canal.evolution_instance, safe="")
        with self._client() as client:
            dados = self._request(
                client, "GET", f"/instance/connectionState/{inst}"
            )
        estado = _map_evolution_state(dados)
        return StatusResult(
            estado=estado,
            ativo=bool(canal.ativo),
            evolution_instance=canal.evolution_instance,
        )

    def connect(self, canal: WhatsAppCanal) -> ConnectResult:
        if not canal.ativo or canal.estado == ESTADO_INATIVO:
            return ConnectResult(estado=ESTADO_INATIVO)
        self.ensure_instance(canal)
        inst = quote(canal.evolution_instance, safe="")
        with self._client() as client:
            dados = self._request(client, "GET", f"/instance/connect/{inst}")
        qr = dados.get("base64") or dados.get("code")
        if not qr:
            # Já pareado: a Evolution não devolve QR quando o estado é open.
            canal.estado = ESTADO_CONECTADO
            return ConnectResult(estado=ESTADO_CONECTADO)
        canal.estado = ESTADO_PENDENTE
        return ConnectResult(
            estado=ESTADO_PENDENTE,
            qr_payload=qr,
            expires_in_seconds=60,
            pairing_code=dados.get("pairingCode"),
        )

    def disconnect(self, canal: WhatsAppCanal) -> StatusResult:
        inst = quote(canal.evolution_instance, safe="")
        with self._client() as client:
            self._request(client, "DELETE", f"/instance/logout/{inst}")
        canal.estado = ESTADO_DESCONECTADO
        return StatusResult(
            estado=ESTADO_DESCONECTADO,
            ativo=bool(canal.ativo),
            evolution_instance=canal.evolution_instance,
        )
```

No topo do módulo adicionar `import logging`, `from urllib.parse import quote`, `logger = logging.getLogger("chatbot.whatsapp_provider")`, e o helper:

```python
def _map_evolution_state(dados: object) -> str:
    """Traduz o payload de connectionState para os estados canônicos."""
    bruto = ""
    if isinstance(dados, dict):
        instancia = dados.get("instance")
        if isinstance(instancia, dict):
            bruto = str(instancia.get("state") or "")
        if not bruto:
            bruto = str(dados.get("state") or "")
    if bruto == "open":
        return ESTADO_CONECTADO
    if bruto == "connecting":
        return ESTADO_PENDENTE
    return ESTADO_DESCONECTADO
```

`ensure_instance` é escrito na Task 3. Para esta task passar, adicionar o stub temporário `def ensure_instance(self, canal): return None` — a Task 3 o substitui.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_whatsapp_provider_evolution.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/whatsapp_provider.py chatbot-api/tests/test_whatsapp_provider_evolution.py
git commit -m "feat(chatbot): provider Evolution real para status/connect/disconnect"
```

---

### Task 3: `ensure_instance` — criar instância com webhook

**PASSO MANUAL OBRIGATÓRIO ANTES DE CODAR:** rodar no lab, contra a instância legado que já funciona:

```bash
curl -s -H "apikey: $EVOLUTION_KEY" "$EVOLUTION_URL/webhook/find/<instancia-legado>"
```

Copiar a lista de `events` do resultado para a constante `EVOLUTION_WEBHOOK_EVENTS` abaixo, e citar em comentário de onde veio. **Não adivinhar eventos** — instância com evento errado recebe silêncio, e o sintoma aparece só em produção. Se o lab estiver indisponível, parar e pedir ajuda ao autor do plano em vez de inventar a lista.

**Files:**
- Modify: `chatbot-api/app/whatsapp_provider.py`
- Test: `chatbot-api/tests/test_whatsapp_provider_evolution.py`

**Interfaces:**
- Consumes: `_client`, `_request` (Task 2).
- Produces: `EvolutionWhatsAppProvider.ensure_instance(canal) -> None`, `EVOLUTION_WEBHOOK_EVENTS: tuple[str, ...]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_ensure_instance_cria_com_webhook_quando_nao_existe():
    chamadas = []

    def handler(request):
        chamadas.append((request.method, request.url.path))
        if request.url.path == "/instance/fetchInstances":
            return httpx.Response(200, json=[])
        if request.url.path == "/instance/create":
            corpo = json_module.loads(request.content)
            assert corpo["instanceName"] == "loja1-ab12"
            assert corpo["webhook"]["url"] == "http://n8n.local/webhook/whatsapp-ai"
            assert corpo["webhook"]["events"]
            return httpx.Response(201, json={"instance": {"instanceName": "loja1-ab12"}})
        return httpx.Response(200, json={})

    _provider(handler).ensure_instance(_canal())
    assert ("POST", "/instance/create") in chamadas


def test_ensure_instance_e_idempotente_quando_ja_existe():
    chamadas = []

    def handler(request):
        chamadas.append((request.method, request.url.path))
        if request.url.path == "/instance/fetchInstances":
            return httpx.Response(200, json=[{"name": "loja1-ab12"}])
        return httpx.Response(200, json={})

    _provider(handler).ensure_instance(_canal())
    assert ("POST", "/instance/create") not in chamadas


def test_ensure_instance_sem_webhook_url_falha_explicito():
    prov = EvolutionWhatsAppProvider(
        base_url="http://evo.local",
        api_key="k",
        webhook_url="",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[])),
    )
    with pytest.raises(WhatsAppProvisionError) as exc:
        prov.ensure_instance(_canal())
    assert exc.value.code == "evolution_webhook_not_configured"
```

Adicionar `import json as json_module` no topo do arquivo de teste.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_whatsapp_provider_evolution.py -k ensure -v`
Expected: FAIL — `ensure_instance` é o stub da Task 2 e não chama nada.

- [ ] **Step 3: Implement `ensure_instance`**

Substituir o stub em `EvolutionWhatsAppProvider`:

```python
    def ensure_instance(self, canal: WhatsAppCanal) -> None:
        """Garante que a instância existe na Evolution, com webhook configurado.

        Idempotente: instância já existente não é erro e não é reconfigurada.
        """
        if not self.webhook_url:
            raise WhatsAppProvisionError(
                "CHATBOT_EVOLUTION_WEBHOOK_URL não configurado",
                code="evolution_webhook_not_configured",
            )
        nome = canal.evolution_instance
        with self._client() as client:
            existentes = self._request(client, "GET", "/instance/fetchInstances")
            if _instancia_existe(existentes, nome):
                return
            self._request(
                client,
                "POST",
                "/instance/create",
                json={
                    "instanceName": nome,
                    "integration": "WHATSAPP-BAILEYS",
                    "qrcode": False,
                    "webhook": {
                        "url": self.webhook_url,
                        "byEvents": False,
                        "events": list(EVOLUTION_WEBHOOK_EVENTS),
                    },
                },
            )
```

E o módulo ganha:

```python
# Eventos do webhook. Copiados de GET /webhook/find/{instancia-legado} no lab
# (instância em operação) — ver Task 3 do plano. Não editar por palpite: evento
# faltando faz a instância nova receber silêncio.
EVOLUTION_WEBHOOK_EVENTS: tuple[str, ...] = (
    "MESSAGES_UPSERT",
)


def _instancia_existe(payload: object, nome: str) -> bool:
    """fetchInstances varia de formato entre versões da Evolution."""
    itens: list = []
    if isinstance(payload, list):
        itens = payload
    elif isinstance(payload, dict):
        bruto = payload.get("instances") or payload.get("data")
        if isinstance(bruto, list):
            itens = bruto
    for item in itens:
        if not isinstance(item, dict):
            continue
        interno = item.get("instance") if isinstance(item.get("instance"), dict) else item
        if nome in {interno.get("name"), interno.get("instanceName")}:
            return True
    return False
```

> Ao concluir o passo manual do topo desta task, ajustar `EVOLUTION_WEBHOOK_EVENTS` para a lista real e manter o comentário.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_whatsapp_provider_evolution.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/whatsapp_provider.py chatbot-api/tests/test_whatsapp_provider_evolution.py
git commit -m "feat(chatbot): ensure_instance cria instancia Evolution com webhook"
```

---

### Task 4: `register_channel` gera o nome da instância

**Files:**
- Modify: `chatbot-api/app/channels.py:48-107`
- Modify: `chatbot-api/app/main.py:1015-1048`
- Test: `chatbot-api/tests/test_channels.py`

**Interfaces:**
- Consumes: `Loja.slug`, `WhatsAppCanal`.
- Produces: `channels.register_channel(db, loja_id, instance, label)` aceitando `instance=None`; `channels.gerar_nome_instancia(db, loja) -> str`.

- [ ] **Step 1: Write the failing tests**

Adicionar a `chatbot-api/tests/test_channels.py`:

```python
import re

from app import channels, config


def test_register_sem_instance_gera_nome_do_slug(db, loja_a, monkeypatch):
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", True)
    canal = channels.register_channel(db, loja_a["loja_id"], None, "linha 2")
    inst = canal["evolution_instance"]
    assert inst.startswith(loja_a["slug"] + "-")
    assert re.fullmatch(r"[a-z0-9-]+", inst)


def test_register_sem_instance_duas_vezes_gera_nomes_distintos(db, loja_a, monkeypatch):
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", True)
    a = channels.register_channel(db, loja_a["loja_id"], None, "linha 2")
    b = channels.register_channel(db, loja_a["loja_id"], None, "linha 3")
    assert a["evolution_instance"] != b["evolution_instance"]


def test_register_com_instance_continua_idempotente(db, loja_a, monkeypatch):
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", True)
    a = channels.register_channel(db, loja_a["loja_id"], "fixa-1", "linha 2")
    b = channels.register_channel(db, loja_a["loja_id"], "fixa-1", "outro label")
    assert a["id"] == b["id"]


def test_http_post_canal_sem_instance(client, loja_a, monkeypatch):
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", True)
    r = client.post(
        "/v1/whatsapp/canais",
        headers=loja_a["headers"],
        json={"e164_or_label": "linha 2"},
    )
    assert r.status_code == 201
    assert r.json()["evolution_instance"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_channels.py -k "sem_instance or idempotente" -v`
Expected: FAIL — 422 "evolution_instance é obrigatório" / erro de validação Pydantic.

- [ ] **Step 3: Implement name generation**

Em `chatbot-api/app/channels.py`, adicionar antes de `register_channel`:

```python
def _sanitizar_nome(bruto: str) -> str:
    """Reduz a [a-z0-9-]: o nome vira segmento de URL na Evolution."""
    limpo = re.sub(r"[^a-z0-9-]+", "-", (bruto or "").strip().lower())
    return re.sub(r"-{2,}", "-", limpo).strip("-")


def gerar_nome_instancia(db: Session, loja: Loja) -> str:
    """Nome novo e livre: {slug}-{4 hex}. Colisão é improvável mas tratada."""
    base = _sanitizar_nome(loja.slug) or "loja"
    for _ in range(10):
        candidato = f"{base}-{uuid.uuid4().hex[:4]}"
        ja_existe = (
            db.query(WhatsAppCanal)
            .filter(WhatsAppCanal.evolution_instance == candidato)
            .first()
        )
        if ja_existe is None:
            return candidato
    raise HTTPException(
        status_code=503,
        detail="não foi possível gerar nome de instância; tente novamente",
    )
```

Adicionar `import re` no topo.

Trocar a validação inicial de `register_channel`:

```python
def register_channel(
    db: Session,
    loja_id: str,
    instance: str | None,
    label: str,
) -> dict[str, Any]:
    """Registra um canal na loja. Não toca a Evolution — só persiste.

    ``instance`` ausente faz o Chatbot gerar o nome (a Loja nunca escolhe).
    Com MULTI_WHATSAPP desligado, só permite 1 canal ativo por loja.
    Instância já existente em qualquer loja → 409.
    """
    instance = (instance or "").strip()
    label = (label or "").strip()
    if not label:
        raise HTTPException(status_code=422, detail="e164_or_label é obrigatório")

    loja = db.get(Loja, loja_id)
    if loja is None:
        raise HTTPException(status_code=404, detail="loja não encontrada")

    if not instance:
        instance = gerar_nome_instancia(db, loja)
```

O resto do corpo (busca de existente, gate de multi, criação) fica **inalterado**, e a checagem `if not instance: raise 422` original é removida.

- [ ] **Step 4: Make the HTTP field optional**

Em `chatbot-api/app/main.py`, no `CanalWhatsAppInput`:

```python
class CanalWhatsAppInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Opcional: ausente, o Chatbot gera o nome. Expand-only — o proxy do
    # Control continua enviando o campo e segue funcionando.
    evolution_instance: str | None = Field(default=None, max_length=120)
    e164_or_label: str = Field(min_length=1, max_length=80)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_channels.py tests/test_multi_whatsapp_routing.py -v`
Expected: PASS (incluindo os testes multi-WA já existentes, que passam `instance` explícito)

- [ ] **Step 6: Commit**

```bash
git add chatbot-api/app/channels.py chatbot-api/app/main.py chatbot-api/tests/test_channels.py
git commit -m "feat(chatbot): Chatbot gera nome da instancia quando nao informado"
```

---

### Task 5: `connect_channel` faz ensure antes do QR

**Files:**
- Modify: `chatbot-api/app/channels.py:133-157`
- Test: `chatbot-api/tests/test_channels.py`

**Interfaces:**
- Consumes: `EvolutionWhatsAppProvider.ensure_instance` (Task 3), `WhatsAppProvisionError` (Task 2).
- Produces: `channels.connect_channel` que propaga `WhatsAppProvisionError` como HTTP 502 sem alterar o estado persistido.

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from app import whatsapp_provider
from app.whatsapp_provider import WhatsAppProvisionError


class _ProviderQueFalha:
    def __init__(self):
        self.ensure_chamado = 0

    def ensure_instance(self, canal):
        self.ensure_chamado += 1
        raise WhatsAppProvisionError("evolution fora", code="evolution_unreachable")

    def connect(self, canal):
        raise AssertionError("connect não deve ser chamado se o ensure falhou")

    def status(self, canal):
        raise NotImplementedError

    def disconnect(self, canal):
        raise NotImplementedError


def test_connect_chama_ensure_e_502_quando_evolution_fora(db, loja_a, monkeypatch):
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", True)
    canal = channels.register_channel(db, loja_a["loja_id"], None, "linha 2")
    prov = _ProviderQueFalha()

    with pytest.raises(Exception) as exc:
        channels.connect_channel(db, loja_a["loja_id"], canal["id"], provider=prov)

    assert getattr(exc.value, "status_code", None) == 502
    assert prov.ensure_chamado == 1
    atual = channels.list_channels(db, loja_a["loja_id"])
    alvo = [c for c in atual if c["id"] == canal["id"]][0]
    assert alvo["estado"] == "pendente"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_channels.py -k ensure_e_502 -v`
Expected: FAIL — `WhatsAppProvisionError` escapa como 500, não 502.

- [ ] **Step 3: Implement**

Em `connect_channel`, envolver a chamada ao provider:

```python
    prov = provider or get_whatsapp_provider()
    ensure = getattr(prov, "ensure_instance", None)
    try:
        if callable(ensure):
            ensure(canal)
        result = prov.connect(canal)
    except WhatsAppProvisionError as exc:
        # Estado persistido não muda: o canal segue pendente e o botão
        # "conectar" é o retry natural.
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    db.commit()
```

Import: `from app.whatsapp_provider import WhatsAppProvisionError` (somar ao import já existente do módulo).

> `getattr` porque `MemoryWhatsAppProvider` e o stub não têm `ensure_instance` — e não devem ganhar.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_channels.py tests/test_multi_whatsapp_routing.py -v`
Expected: PASS

- [ ] **Step 5: Run the full chatbot suite**

Run: `python -m pytest -q`
Expected: 0 falhas.

- [ ] **Step 6: Commit**

```bash
git add chatbot-api/app/channels.py chatbot-api/tests/test_channels.py
git commit -m "feat(chatbot): connect garante instancia e devolve 502 sem sujar estado"
```

---

### Task 6: Auditoria ganha o domínio `canal` (Loja)

O banco tem `CheckConstraint("dominio IN ('atendimento', 'financeira')")`, então auditar canal exige migration **e** mudança no modelo.

**Files:**
- Modify: `portal-gestao/app/models.py:148-159`
- Create: `portal-gestao/alembic/versions/0015_auditoria_dominio_canal.py`
- Modify: `portal-gestao/app/loja_operacao_auditoria.py:18-51`
- Test: `portal-gestao/tests/test_loja_operacao_auditoria.py`

**Interfaces:**
- Consumes: `registrar_auditoria_operacao` (existente).
- Produces: `DOMINIO_CANAL = "canal"`, `ACOES_CANAL = frozenset({"criar","conectar","desconectar","inativar"})`, `registrar_auditoria_canal(db, *, loja_slug, acao, ator_email, provedor=None, success=None, error_code=None, commit=False) -> LojaOperacaoAuditoria`.

- [ ] **Step 1: Write the failing test**

Adicionar a `portal-gestao/tests/test_loja_operacao_auditoria.py`:

```python
import pytest

from app.loja_operacao_auditoria import (
    DOMINIO_CANAL,
    registrar_auditoria_canal,
)


def test_auditoria_canal_persiste(db):
    row = registrar_auditoria_canal(
        db,
        loja_slug="loja-teste",
        acao="conectar",
        ator_email="dono@loja.test",
        success=True,
        commit=True,
    )
    assert row.dominio == DOMINIO_CANAL
    assert row.acao == "conectar"
    assert row.telefone_hmac is None


def test_auditoria_canal_recusa_acao_invalida(db):
    with pytest.raises(ValueError):
        registrar_auditoria_canal(
            db, loja_slug="loja-teste", acao="explodir", ator_email="a@b.c"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run (de `portal-gestao/`): `python -m pytest tests/test_loja_operacao_auditoria.py -k canal -v`
Expected: FAIL com `ImportError: cannot import name 'DOMINIO_CANAL'`

- [ ] **Step 3: Update the model constraint**

Em `portal-gestao/app/models.py`, na classe `LojaOperacaoAuditoria`:

```python
        CheckConstraint(
            "dominio IN ('atendimento', 'financeira', 'canal')",
            name="ck_loja_operacao_auditoria_dominio",
        ),
```

E o comentário das ações (linha ~164) passa a incluir `# canal: criar|conectar|desconectar|inativar`.

- [ ] **Step 4: Write the migration**

Criar `portal-gestao/alembic/versions/0015_auditoria_dominio_canal.py`:

```python
"""auditoria de operacao aceita dominio canal

Revision ID: 0015
Revises: 0014
"""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

_NOME = "ck_loja_operacao_auditoria_dominio"
_TABELA = "loja_operacao_auditoria"


def upgrade() -> None:
    with op.batch_alter_table(_TABELA) as batch:
        batch.drop_constraint(_NOME, type_="check")
        batch.create_check_constraint(
            _NOME, "dominio IN ('atendimento', 'financeira', 'canal')"
        )


def downgrade() -> None:
    # Linhas de canal impediriam a volta da constraint antiga.
    op.execute(f"DELETE FROM {_TABELA} WHERE dominio = 'canal'")
    with op.batch_alter_table(_TABELA) as batch:
        batch.drop_constraint(_NOME, type_="check")
        batch.create_check_constraint(
            _NOME, "dominio IN ('atendimento', 'financeira')"
        )
```

> Confirmar o valor exato de `revision` do arquivo `0014_loja_operacao_auditoria.py` e usá-lo em `down_revision` (o arquivo acima assume `"0014"`).

- [ ] **Step 5: Implement the audit helper**

Em `portal-gestao/app/loja_operacao_auditoria.py`:

```python
DOMINIO_CANAL = "canal"

ACOES_CANAL = frozenset({"criar", "conectar", "desconectar", "inativar"})
```

Na validação de `registrar_auditoria_operacao`:

```python
    if dominio not in {DOMINIO_ATENDIMENTO, DOMINIO_FINANCEIRA, DOMINIO_CANAL}:
        raise ValueError(f"dominio inválido: {dominio}")
    if dominio == DOMINIO_ATENDIMENTO and acao not in ACOES_ATENDIMENTO:
        raise ValueError(f"acao de atendimento inválida: {acao}")
    if dominio == DOMINIO_FINANCEIRA and acao not in ACOES_FINANCEIRA:
        raise ValueError(f"acao financeira inválida: {acao}")
    if dominio == DOMINIO_CANAL and acao not in ACOES_CANAL:
        raise ValueError(f"acao de canal inválida: {acao}")
```

E o wrapper, ao lado de `registrar_auditoria_financeira`:

```python
def registrar_auditoria_canal(
    db: Session,
    *,
    loja_slug: str,
    acao: str,
    ator_email: str,
    provedor: Optional[str] = None,
    success: Optional[bool] = None,
    error_code: Optional[str] = None,
    commit: bool = False,
) -> LojaOperacaoAuditoria:
    """Canal WhatsApp: criar|conectar|desconectar|inativar. Nunca grava QR."""
    return registrar_auditoria_operacao(
        db,
        loja_slug=loja_slug,
        dominio=DOMINIO_CANAL,
        acao=acao,
        ator_email=ator_email,
        provedor=provedor,
        success=success,
        error_code=error_code,
        commit=commit,
    )
```

O docstring do módulo (linhas 3-5) ganha a linha `- canal: criar | conectar | desconectar | inativar (nunca grava QR)`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_loja_operacao_auditoria.py -v`
Expected: PASS (novos + existentes)

- [ ] **Step 7: Commit**

```bash
git add portal-gestao/app/models.py portal-gestao/app/loja_operacao_auditoria.py portal-gestao/alembic/versions/0015_auditoria_dominio_canal.py portal-gestao/tests/test_loja_operacao_auditoria.py
git commit -m "feat(loja): auditoria de operacao aceita dominio canal"
```

---

### Task 7: `ChatbotClient` ganha escrita de canal (Loja)

**Files:**
- Modify: `portal-gestao/app/clients/chatbot.py:204-207`
- Modify: `portal-gestao/tests/conftest.py` (`ChatbotFake`)
- Test: `portal-gestao/tests/test_loja_whatsapp_canais.py` (criar)

**Interfaces:**
- Consumes: `ChatbotClient._request` (existente).
- Produces: `registrar_canal_whatsapp(label) -> dict`, `conectar_canal_whatsapp(canal_id) -> dict`, `desconectar_canal_whatsapp(canal_id) -> dict`, `inativar_canal_whatsapp(canal_id) -> dict`, `obter_status_canal_whatsapp(canal_id) -> dict`.

- [ ] **Step 1: Write the failing test**

Criar `portal-gestao/tests/test_loja_whatsapp_canais.py`:

```python
"""Tela de canais WhatsApp da Loja (Ajustes) e client de escrita."""
from app.clients.chatbot import ChatbotClient


def test_client_registrar_canal_manda_so_label(respx_like_monkeypatch=None):
    chamadas = []

    class _Fake(ChatbotClient):
        def _request(self, method, path, erro_404=None, erro_409=None, **kwargs):
            chamadas.append((method, path, kwargs.get("json")))
            return {"id": "c1", "e164_or_label": "linha 2"}

    cliente = _Fake("http://chatbot", "tok")
    canal = cliente.registrar_canal_whatsapp("linha 2")

    assert canal["id"] == "c1"
    assert chamadas == [("POST", "/v1/whatsapp/canais", {"e164_or_label": "linha 2"})]


def test_client_conectar_usa_endpoint_do_canal():
    chamadas = []

    class _Fake(ChatbotClient):
        def _request(self, method, path, erro_404=None, erro_409=None, **kwargs):
            chamadas.append((method, path))
            return {"id": "c1", "qr_payload": "QR", "estado": "pendente"}

    cliente = _Fake("http://chatbot", "tok")
    out = cliente.conectar_canal_whatsapp("c1")

    assert out["qr_payload"] == "QR"
    assert chamadas == [("POST", "/v1/whatsapp/canais/c1/connect")]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_loja_whatsapp_canais.py -v`
Expected: FAIL — `ChatbotClient` não tem `registrar_canal_whatsapp`.

- [ ] **Step 3: Implement the client methods**

Em `portal-gestao/app/clients/chatbot.py`, substituir o docstring de `listar_canais_whatsapp` e adicionar os métodos:

```python
    def listar_canais_whatsapp(self) -> list[dict]:
        """Lista canais da loja. A Loja também opera canais (ver métodos abaixo)."""
        dados = self._request("GET", "/v1/whatsapp/canais")
        return list(dados.get("canais") or [])

    def registrar_canal_whatsapp(self, label: str) -> dict:
        """Cadastra canal. Não envia ``evolution_instance``: o Chatbot gera o nome."""
        return self._request(
            "POST",
            "/v1/whatsapp/canais",
            json={"e164_or_label": label},
        )

    def conectar_canal_whatsapp(self, canal_id: str) -> dict:
        """Inicia pareamento. A resposta traz ``qr_payload`` efêmero — nunca logar."""
        return self._request(
            "POST", f"/v1/whatsapp/canais/{canal_id}/connect"
        )

    def desconectar_canal_whatsapp(self, canal_id: str) -> dict:
        return self._request(
            "POST", f"/v1/whatsapp/canais/{canal_id}/disconnect"
        )

    def inativar_canal_whatsapp(self, canal_id: str) -> dict:
        return self._request(
            "POST", f"/v1/whatsapp/canais/{canal_id}/inativar"
        )

    def obter_status_canal_whatsapp(self, canal_id: str) -> dict:
        return self._request(
            "GET", f"/v1/whatsapp/canais/{canal_id}/status"
        )
```

- [ ] **Step 4: Extend `ChatbotFake` in conftest**

Em `portal-gestao/tests/conftest.py`, na classe `ChatbotFake`, adicionar ao `__init__` (ou como atributos de classe, seguindo o estilo já usado no arquivo) `self.canais: list[dict] = []` e os métodos:

```python
    def listar_canais_whatsapp(self):
        if self.indisponivel:
            raise ChatbotIndisponivel("Não foi possível acessar o chatbot agora")
        return [dict(c) for c in self.canais]

    def registrar_canal_whatsapp(self, label):
        if self.indisponivel:
            raise ChatbotIndisponivel("Não foi possível acessar o chatbot agora")
        canal = {
            "id": f"c{len(self.canais) + 1}",
            "e164_or_label": label,
            "evolution_instance": f"loja-teste-{len(self.canais) + 1}",
            "ativo": True,
            "estado": "pendente",
        }
        self.canais.append(canal)
        return dict(canal)

    def conectar_canal_whatsapp(self, canal_id):
        if self.indisponivel:
            raise ChatbotIndisponivel("Não foi possível acessar o chatbot agora")
        canal = self._canal(canal_id)
        canal["estado"] = "pendente"
        return {**canal, "qr_payload": "QR-FAKE", "expires_in_seconds": 60}

    def desconectar_canal_whatsapp(self, canal_id):
        canal = self._canal(canal_id)
        canal["estado"] = "desconectado"
        return dict(canal)

    def inativar_canal_whatsapp(self, canal_id):
        canal = self._canal(canal_id)
        canal["ativo"] = False
        canal["estado"] = "inativo"
        return dict(canal)

    def obter_status_canal_whatsapp(self, canal_id):
        return dict(self._canal(canal_id))

    def _canal(self, canal_id):
        return next(c for c in self.canais if c["id"] == canal_id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_loja_whatsapp_canais.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add portal-gestao/app/clients/chatbot.py portal-gestao/tests/conftest.py portal-gestao/tests/test_loja_whatsapp_canais.py
git commit -m "feat(loja): ChatbotClient opera canais WhatsApp"
```

---

### Task 8: Read-model dos canais (Loja)

**Files:**
- Create: `portal-gestao/app/loja/whatsapp_canais.py`
- Test: `portal-gestao/tests/test_loja_whatsapp_canais.py`

**Interfaces:**
- Consumes: dicts crus de `listar_canais_whatsapp`.
- Produces: `montar_canais_view(canais, *, erro=None, multi_habilitado=True) -> CanaisView` com `CanaisView(canais: tuple[CanalView, ...], erro: str | None, pode_adicionar: bool)` e `CanalView(id, label, instancia, estado, rotulo, ativo, pode_conectar, pode_desconectar)`.

- [ ] **Step 1: Write the failing test**

```python
from app.loja.whatsapp_canais import montar_canais_view


def test_view_traduz_estados_para_linguagem_de_loja():
    view = montar_canais_view(
        [
            {"id": "c1", "e164_or_label": "linha 1", "evolution_instance": "i1",
             "ativo": True, "estado": "conectado"},
            {"id": "c2", "e164_or_label": "linha 2", "evolution_instance": "i2",
             "ativo": True, "estado": "pendente"},
            {"id": "c3", "e164_or_label": "linha 3", "evolution_instance": "i3",
             "ativo": True, "estado": "desconectado"},
            {"id": "c4", "e164_or_label": "linha 4", "evolution_instance": "i4",
             "ativo": False, "estado": "inativo"},
        ]
    )
    rotulos = [c.rotulo for c in view.canais]
    assert rotulos == [
        "Conectado",
        "Aguardando leitura do QR",
        "Caiu — reconectar",
        "Desativado",
    ]


def test_view_com_erro_nao_inventa_canais():
    view = montar_canais_view(None, erro="Chatbot indisponível")
    assert view.canais == ()
    assert view.erro == "Chatbot indisponível"
    assert view.pode_adicionar is False


def test_canal_inativo_nao_pode_conectar():
    view = montar_canais_view(
        [{"id": "c4", "e164_or_label": "x", "evolution_instance": "i4",
          "ativo": False, "estado": "inativo"}]
    )
    assert view.canais[0].pode_conectar is False
    assert view.canais[0].pode_desconectar is False


def test_multi_desabilitado_impede_adicionar():
    view = montar_canais_view([], multi_habilitado=False)
    assert view.pode_adicionar is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_loja_whatsapp_canais.py -k view -v`
Expected: FAIL — módulo não existe.

- [ ] **Step 3: Implement**

Criar `portal-gestao/app/loja/whatsapp_canais.py`:

```python
"""Read-model dos canais WhatsApp para a tela de Ajustes da Loja.

Traduz o estado técnico do Chatbot para linguagem de dono de loja. Nunca
carrega QR: o QR vive só no ciclo de request/response da ação de conectar.
"""
from __future__ import annotations

from dataclasses import dataclass

ROTULOS = {
    "conectado": "Conectado",
    "pendente": "Aguardando leitura do QR",
    "desconectado": "Caiu — reconectar",
    "inativo": "Desativado",
}


@dataclass(frozen=True)
class CanalView:
    id: str
    label: str
    instancia: str
    estado: str
    rotulo: str
    ativo: bool
    pode_conectar: bool
    pode_desconectar: bool


@dataclass(frozen=True)
class CanaisView:
    canais: tuple[CanalView, ...]
    erro: str | None
    pode_adicionar: bool


def montar_canais_view(
    canais: list[dict] | None,
    *,
    erro: str | None = None,
    multi_habilitado: bool = True,
) -> CanaisView:
    """Monta a view. ``canais=None`` significa falha de leitura, não lista vazia."""
    if canais is None:
        return CanaisView(canais=(), erro=erro, pode_adicionar=False)

    itens: list[CanalView] = []
    for bruto in canais:
        estado = str(bruto.get("estado") or "pendente")
        ativo = bool(bruto.get("ativo", True))
        operavel = ativo and estado != "inativo"
        itens.append(
            CanalView(
                id=str(bruto.get("id") or ""),
                label=str(bruto.get("e164_or_label") or "—"),
                instancia=str(bruto.get("evolution_instance") or ""),
                estado=estado,
                rotulo=ROTULOS.get(estado, estado),
                ativo=ativo,
                pode_conectar=operavel and estado != "conectado",
                pode_desconectar=operavel and estado == "conectado",
            )
        )
    return CanaisView(
        canais=tuple(itens),
        erro=erro,
        pode_adicionar=bool(multi_habilitado),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_loja_whatsapp_canais.py -k view -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/loja/whatsapp_canais.py portal-gestao/tests/test_loja_whatsapp_canais.py
git commit -m "feat(loja): read-model de canais WhatsApp"
```

---

### Task 9: Tela, rotas, flag e navegação (Loja)

Entrega a tela inteira: flag, rotas GET/POST, template, item de nav e auditoria.

**Files:**
- Modify: `portal-gestao/app/config.py`
- Create: `portal-gestao/app/web/loja_whatsapp.py`
- Create: `portal-gestao/app/templates/loja/whatsapp_canais.html`
- Modify: `portal-gestao/app/loja/navigation.py:15-106`
- Modify: `portal-gestao/app/main.py:4619-4627`
- Test: `portal-gestao/tests/test_loja_whatsapp_canais.py`

**Interfaces:**
- Consumes: `montar_canais_view` (Task 8), métodos de canal do `ChatbotClient` (Task 7), `registrar_auditoria_canal` (Task 6), `csrf_valido`/`usuario_atual` de `app.auth`, `contexto`/`templates`/`redirecionar_login`/`get_chatbot_client` de `app.main`.
- Produces: rotas `GET /app/loja/whatsapp`, `POST /app/loja/whatsapp/canais`, `POST /app/loja/whatsapp/canais/{canal_id}/conectar|desconectar|inativar`.

- [ ] **Step 1: Write the failing tests**

```python
from app import config as app_config
from app.loja_operacao_auditoria import DOMINIO_CANAL
from app.models import LojaOperacaoAuditoria


def _login(client, papel="dono"):
    criar_usuario(papel=papel)
    client.post(
        "/login", data={"email": "dono@loja.test", "senha": "senha-segura"}
    )


def test_flag_off_esconde_tela(client, monkeypatch):
    monkeypatch.setattr(
        app_config.settings, "revy_loja_whatsapp_enabled", False, raising=False
    )
    _login(client)
    r = client.get("/app/loja/whatsapp", follow_redirects=False)
    assert r.status_code == 303


def test_vendedor_nao_acessa(client, monkeypatch):
    monkeypatch.setattr(
        app_config.settings, "revy_loja_whatsapp_enabled", True, raising=False
    )
    criar_usuario(papel="vendedor", email="v@loja.test")
    client.post("/login", data={"email": "v@loja.test", "senha": "senha-segura"})
    r = client.get("/app/loja/whatsapp", follow_redirects=False)
    assert r.status_code == 303


def test_dono_ve_canais_e_adiciona(client, chatbot_fake, monkeypatch):
    monkeypatch.setattr(
        app_config.settings, "revy_loja_whatsapp_enabled", True, raising=False
    )
    _login(client)
    r = client.post(
        "/app/loja/whatsapp/canais",
        data={"csrf": _csrf(client), "label": "linha 2"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert [c["e164_or_label"] for c in chatbot_fake.canais] == ["linha 2"]


def test_conectar_mostra_qr_e_nao_grava_em_auditoria(
    client, chatbot_fake, db, monkeypatch
):
    monkeypatch.setattr(
        app_config.settings, "revy_loja_whatsapp_enabled", True, raising=False
    )
    _login(client)
    chatbot_fake.registrar_canal_whatsapp("linha 2")
    r = client.post(
        "/app/loja/whatsapp/canais/c1/conectar",
        data={"csrf": _csrf(client)},
        follow_redirects=True,
    )
    assert "QR-FAKE" in r.text
    linhas = db.query(LojaOperacaoAuditoria).filter_by(dominio=DOMINIO_CANAL).all()
    assert [l.acao for l in linhas] == ["conectar"]
    assert all("QR-FAKE" not in (l.error_code or "") for l in linhas)


def test_chatbot_indisponivel_mostra_banner(client, chatbot_fake, monkeypatch):
    monkeypatch.setattr(
        app_config.settings, "revy_loja_whatsapp_enabled", True, raising=False
    )
    chatbot_fake.indisponivel = True
    _login(client)
    r = client.get("/app/loja/whatsapp")
    assert "não foi possível" in r.text.lower()
```

Adicionar no topo do arquivo de teste o helper de CSRF e o import de `criar_usuario`:

```python
import re

from tests.conftest import criar_usuario


def _csrf(client):
    pagina = client.get("/app/loja/whatsapp").text
    achado = re.search(r'name="csrf" value="([^"]+)"', pagina)
    assert achado, "csrf não encontrado na página"
    return achado.group(1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_loja_whatsapp_canais.py -v`
Expected: FAIL — 404 nas rotas.

- [ ] **Step 3: Add the flag**

Em `portal-gestao/app/config.py`, junto às outras flags `revy_loja_*`:

```python
    revy_loja_whatsapp_enabled: bool = _flag("REVY_LOJA_WHATSAPP_ENABLED")
```

> Usar exatamente o mesmo helper/estilo das flags `revy_loja_*` vizinhas (ler as linhas ao redor antes de escrever; se elas usam `os.getenv(...) == "1"` direto, seguir isso).

- [ ] **Step 4: Write the routes**

Criar `portal-gestao/app/web/loja_whatsapp.py`:

```python
"""Canais WhatsApp na Loja (Ajustes) — dono/gerente cadastram e pareiam números.

QR nunca vai a log nem a auditoria: vive só no request/response do conectar.
Gated por REVY_LOJA_SHELL_ENABLED + REVY_LOJA_WHATSAPP_ENABLED (default off).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import csrf_valido, usuario_atual
from app.clients.chatbot import ChatbotClient, ChatbotIndisponivel
from app.config import settings
from app.db import get_db
from app.loja.whatsapp_canais import ROTULOS, montar_canais_view
from app.loja_operacao_auditoria import registrar_auditoria_canal

router = APIRouter()

from app.main import (  # noqa: E402
    contexto,
    get_chatbot_client,
    redirecionar_login,
    templates,
)

CARGOS = {"dono", "gerente"}
_TELA = "/app/loja/whatsapp"


def _habilitado() -> bool:
    return bool(
        settings.revy_loja_shell_enabled and settings.revy_loja_whatsapp_enabled
    )


@router.get(_TELA, response_class=HTMLResponse)
def loja_whatsapp_canais(
    request: Request,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not _habilitado() or usuario.papel not in CARGOS:
        return RedirectResponse("/app", status_code=303)

    canais, erro = None, None
    try:
        canais = chatbot.listar_canais_whatsapp()
    except ChatbotIndisponivel as exc:
        erro = str(exc)

    view = montar_canais_view(canais, erro=erro)
    return templates.TemplateResponse(
        "loja/whatsapp_canais.html",
        contexto(
            request,
            usuario,
            view=view,
            qr=request.session.pop("canal_qr", None),
            acao_erro=request.session.pop("canal_erro", None),
        ),
        headers={"Cache-Control": "no-store"},
    )


async def _guarda(request: Request, db: Session):
    """Devolve (usuario, form, resposta_de_erro)."""
    usuario = usuario_atual(request, db)
    if not usuario:
        return None, None, redirecionar_login()
    form = await request.form()
    if (
        not _habilitado()
        or usuario.papel not in CARGOS
        or not csrf_valido(request, form.get("csrf"))
    ):
        return None, None, RedirectResponse("/app", status_code=303)
    return usuario, form, None


def _auditar(db, usuario, acao, *, success, error_code=None):
    registrar_auditoria_canal(
        db,
        loja_slug=usuario.loja_slug,
        acao=acao,
        ator_email=usuario.email,
        provedor="evolution",
        success=success,
        error_code=error_code,
        commit=True,
    )


@router.post("/app/loja/whatsapp/canais")
async def loja_whatsapp_criar(
    request: Request,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario, form, erro = await _guarda(request, db)
    if erro is not None:
        return erro
    label = (form.get("label") or "").strip()
    if not label:
        request.session["canal_erro"] = "Informe um nome para o número."
        return RedirectResponse(_TELA, status_code=303)
    try:
        chatbot.registrar_canal_whatsapp(label)
        _auditar(db, usuario, "criar", success=True)
    except ChatbotIndisponivel as exc:
        request.session["canal_erro"] = str(exc)
        _auditar(db, usuario, "criar", success=False, error_code="chatbot_indisponivel")
    return RedirectResponse(_TELA, status_code=303)


@router.post("/app/loja/whatsapp/canais/{canal_id}/conectar")
async def loja_whatsapp_conectar(
    canal_id: str,
    request: Request,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario, _form, erro = await _guarda(request, db)
    if erro is not None:
        return erro
    try:
        resultado = chatbot.conectar_canal_whatsapp(canal_id)
        # QR só na sessão do navegador, consumido no próximo GET. Nunca em log.
        if resultado.get("qr_payload"):
            request.session["canal_qr"] = {
                "canal_id": canal_id,
                "payload": resultado["qr_payload"],
            }
        _auditar(db, usuario, "conectar", success=True)
    except ChatbotIndisponivel as exc:
        request.session["canal_erro"] = str(exc)
        _auditar(
            db, usuario, "conectar", success=False, error_code="chatbot_indisponivel"
        )
    return RedirectResponse(_TELA, status_code=303)


@router.post("/app/loja/whatsapp/canais/{canal_id}/desconectar")
async def loja_whatsapp_desconectar(
    canal_id: str,
    request: Request,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario, _form, erro = await _guarda(request, db)
    if erro is not None:
        return erro
    try:
        chatbot.desconectar_canal_whatsapp(canal_id)
        _auditar(db, usuario, "desconectar", success=True)
    except ChatbotIndisponivel as exc:
        request.session["canal_erro"] = str(exc)
        _auditar(
            db, usuario, "desconectar", success=False, error_code="chatbot_indisponivel"
        )
    return RedirectResponse(_TELA, status_code=303)


@router.post("/app/loja/whatsapp/canais/{canal_id}/inativar")
async def loja_whatsapp_inativar(
    canal_id: str,
    request: Request,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario, _form, erro = await _guarda(request, db)
    if erro is not None:
        return erro
    try:
        chatbot.inativar_canal_whatsapp(canal_id)
        _auditar(db, usuario, "inativar", success=True)
    except ChatbotIndisponivel as exc:
        request.session["canal_erro"] = str(exc)
        _auditar(
            db, usuario, "inativar", success=False, error_code="chatbot_indisponivel"
        )
    return RedirectResponse(_TELA, status_code=303)


@router.get("/app/loja/whatsapp/canais/{canal_id}/status")
def loja_whatsapp_status(
    canal_id: str,
    request: Request,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    """Rota fina para o polling enquanto há QR na tela."""
    usuario = usuario_atual(request, db)
    if not usuario or not _habilitado() or usuario.papel not in CARGOS:
        return JSONResponse({"erro": "nao_autorizado"}, status_code=403)
    try:
        dados = chatbot.obter_status_canal_whatsapp(canal_id)
    except ChatbotIndisponivel:
        return JSONResponse({"erro": "indisponivel"}, status_code=503)
    estado = str(dados.get("estado") or "pendente")
    return JSONResponse(
        {"estado": estado, "rotulo": ROTULOS.get(estado, estado)},
        headers={"Cache-Control": "no-store"},
    )
```

- [ ] **Step 5: Write the template**

Criar `portal-gestao/app/templates/loja/whatsapp_canais.html`, seguindo as classes de `operacao/numeros.html`:

```html
{% extends "base.html" %}
{% block title %}Números de WhatsApp — Revy{% endblock %}
{% block page_title %}Números de WhatsApp{% endblock %}
{% block content %}
<section class="page-head">
  <h1>Números de WhatsApp</h1>
  <p class="muted">
    Cada número atende conversas separadamente. Ao conectar, leia o QR no
    celular do número — ele expira em cerca de 1 minuto.
  </p>
</section>

{% if view.erro %}
<div class="alert warning">{{ view.erro }}</div>
{% endif %}
{% if acao_erro %}
<div class="alert warning">{{ acao_erro }}</div>
{% endif %}

{% if qr %}
<div class="card" id="qr-card" data-canal="{{ qr.canal_id }}">
  <h2>Leia o QR no celular</h2>
  <p class="muted">
    WhatsApp → Aparelhos conectados → Conectar aparelho. Se expirar, clique em
    <strong>Conectar</strong> outra vez.
  </p>
  <img alt="QR de conexão" src="data:image/png;base64,{{ qr.payload }}">
  <p class="muted" id="qr-estado">Aguardando leitura do QR…</p>
</div>
<script>
  (function () {
    var card = document.getElementById("qr-card");
    if (!card) return;
    var canal = card.dataset.canal;
    var alvo = document.getElementById("qr-estado");
    var tentativas = 0;
    var timer = setInterval(function () {
      tentativas += 1;
      if (tentativas > 40) { clearInterval(timer); return; }
      fetch("/app/loja/whatsapp/canais/" + canal + "/status")
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) {
          if (!d) return;
          alvo.textContent = d.rotulo;
          if (d.estado === "conectado") {
            clearInterval(timer);
            window.location.reload();
          }
        })
        .catch(function () {});
    }, 3000);
  })();
</script>
{% endif %}

{% if view.pode_adicionar %}
<form class="card form-inline" method="post" action="/app/loja/whatsapp/canais">
  <input type="hidden" name="csrf" value="{{ csrf }}">
  <label>Nome do número
    <input name="label" maxlength="80" placeholder="Linha 2 — vendas" required>
  </label>
  <button class="button primary" type="submit">Adicionar número</button>
</form>
{% endif %}

<div class="card">
  <table class="table">
    <thead>
      <tr><th>Número</th><th>Situação</th><th></th></tr>
    </thead>
    <tbody>
      {% for canal in view.canais %}
      <tr>
        <td>{{ canal.label }}</td>
        <td>{{ canal.rotulo }}</td>
        <td>
          {% if canal.pode_conectar %}
          <form method="post" action="/app/loja/whatsapp/canais/{{ canal.id }}/conectar">
            <input type="hidden" name="csrf" value="{{ csrf }}">
            <button class="button primary" type="submit">Conectar</button>
          </form>
          {% endif %}
          {% if canal.pode_desconectar %}
          <form method="post" action="/app/loja/whatsapp/canais/{{ canal.id }}/desconectar">
            <input type="hidden" name="csrf" value="{{ csrf }}">
            <button class="button" type="submit">Desconectar</button>
          </form>
          {% endif %}
          {% if canal.ativo %}
          <form method="post" action="/app/loja/whatsapp/canais/{{ canal.id }}/inativar"
                onsubmit="return confirm('Desativar este número? O histórico é preservado.')">
            <input type="hidden" name="csrf" value="{{ csrf }}">
            <button class="button danger" type="submit">Desativar</button>
          </form>
          {% endif %}
        </td>
      </tr>
      {% else %}
      <tr><td colspan="3" class="muted">Nenhum número cadastrado.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 6: Register the router**

Em `portal-gestao/app/main.py`, junto aos imports tardios (linha ~4619) e includes (linha ~4627):

```python
from app.web import loja_whatsapp  # noqa: E402
```
```python
app.include_router(loja_whatsapp.router)
```

- [ ] **Step 7: Add the nav item**

Em `portal-gestao/app/loja/navigation.py`, corrigir o docstring da linha 24 e adicionar o item no bloco `ROLES_GESTAO`, depois de "Acessos bancários":

```python
    Inclui WhatsApp (canais) em Ajustes para dono/gerente. Não inclui Meta nem
    Google — configuração de tráfego é do Control.
```

```python
        if settings.revy_loja_whatsapp_enabled:
            ajustes.append(
                NavItem(
                    label="Números de WhatsApp",
                    href="/app/loja/whatsapp",
                    section="Ajustes",
                    module=None,
                    active_prefix="/app/loja/whatsapp",
                )
            )
```

Import necessário no módulo: `from app.config import settings`.

> `build_nav` hoje não importa `settings`. Se a suíte de navegação testar pureza da função, passar a flag como parâmetro `whatsapp_enabled: bool = False` em vez de importar settings — verificar `tests/test_loja_navigation.py` antes de escolher.

- [ ] **Step 8: Run the new tests**

Run: `python -m pytest tests/test_loja_whatsapp_canais.py -v`
Expected: PASS (todos)

- [ ] **Step 9: Run the full portal suite**

Run: `python -m pytest -q`
Expected: 0 falhas. `test_loja_navigation.py` e `test_loja_entitlements.py` são os mais prováveis de reagir — se falharem, ajustar conforme a nota do Step 7.

- [ ] **Step 10: Commit**

```bash
git add portal-gestao/app/config.py portal-gestao/app/web/loja_whatsapp.py portal-gestao/app/templates/loja/whatsapp_canais.html portal-gestao/app/loja/navigation.py portal-gestao/app/main.py portal-gestao/tests/test_loja_whatsapp_canais.py
git commit -m "feat(loja): tela de numeros de WhatsApp em Ajustes"
```

---

### Task 10: Documentação e envs de deploy

**Files:**
- Modify: `docs/referencia-viva/design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md:126`
- Modify: `revy-trafego/README.md:196`
- Modify: `deploy/fly/3vm/env.example`
- Modify: `portal-gestao/README.md` (seção de flags), `chatbot-api` README/env se houver tabela de flags

- [ ] **Step 1: Corrigir a matriz de donos do as-built**

Na linha 126, a coluna "Quem comanda UI" de "Canais WhatsApp / conexões" passa de **Control** para **Loja**, e "Quem só consome" passa a incluir Control (saúde no dashboard). Acrescentar nota de uma linha explicando o motivo (QR é lido pelo celular da loja).

- [ ] **Step 2: Corrigir o README do Control**

`revy-trafego/README.md:196` diz que `MULTI_WHATSAPP_ENABLED` está "ainda sem efeito operacional". Passa a: libera os endpoints proxy de canais e faz a prontidão contar canais ativos.

- [ ] **Step 3: Documentar as envs novas**

Em `deploy/fly/3vm/env.example`, junto ao `MULTI_WHATSAPP_ENABLED` já comentado:

```bash
# Provider de conexão de canal: stub (default) | evolution (real)
# CHATBOT_WHATSAPP_PROVIDER=stub
# Webhook n8n gravado em instância Evolution nova (um workflow serve N números)
# CHATBOT_EVOLUTION_WEBHOOK_URL=https://n8n2037.fly.dev/webhook/whatsapp-ai
# Tela de números de WhatsApp na Loja (Ajustes)
# REVY_LOJA_WHATSAPP_ENABLED=0
```

- [ ] **Step 4: Commit**

```bash
git add docs/referencia-viva/design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md revy-trafego/README.md deploy/fly/3vm/env.example portal-gestao/README.md
git commit -m "docs: canais WhatsApp passam a ser operados na Loja"
```

---

### Task 11: Validação em lab (manual, não automatizável)

Esta task não tem teste automatizado — é a única forma de saber que o adapter real funciona. **Memória do projeto: `fly deploy` usa a árvore local, então commitar tudo antes de deployar.**

- [ ] **Step 1: Deploy com as flags ligadas no lab**

```bash
fly secrets set -a <chatbot-app> \
  MULTI_WHATSAPP_ENABLED=1 \
  CHATBOT_WHATSAPP_PROVIDER=evolution \
  CHATBOT_EVOLUTION_WEBHOOK_URL=https://<n8n>/webhook/whatsapp-ai
fly secrets set -a <portal-app> REVY_LOJA_WHATSAPP_ENABLED=1
```

- [ ] **Step 2: Cadastrar e conectar um segundo número pela tela**

Abrir `/app/loja/whatsapp` como dono, adicionar "Linha 2", clicar Conectar, ler o QR num celular real.
Expected: estado vira "Conectado" sozinho (polling) em até ~2 min.

- [ ] **Step 3: Verificar que o webhook do número novo chega**

Mandar mensagem de um contato novo para a Linha 2.
Expected: resposta da IA. No log do Chatbot, `registrar_mensagem` resolve o canal novo; a conversa aparece em `/v1/conversas` com o `canal_id` da Linha 2 e **separada** da conversa do mesmo telefone na Linha 1.

- [ ] **Step 4: Verificar isolamento de handoff**

Responder manualmente pelo celular da Linha 1.
Expected: só a conversa da Linha 1 vai para `handoff`; a da Linha 2 segue com bot ativo.

- [ ] **Step 5: Confirmar que QR não vazou**

```bash
fly logs -a <chatbot-app> | grep -i -E "base64|qr" || echo "limpo"
fly logs -a <portal-app> | grep -i -E "base64|qr" || echo "limpo"
```
Expected: `limpo` nos dois.

- [ ] **Step 6: Registrar o resultado**

Atualizar a seção 3 (gaps) do as-built marcando o residual "Multi-WA E2E" como fechado, com a data.

---

## Notas de execução

- **Tasks 1-5** são o Chatbot e podem ser feitas sem tocar no Portal.
- **Tasks 6-9** são a Loja; a Task 9 é a maior e depende de 6, 7 e 8.
- **Task 3** tem um passo manual bloqueante (ler `webhook/find` no lab). Se o lab não estiver disponível, fazer as Tasks 1-2 e 4-9 e deixar a 3 por último — o default `stub` mantém tudo funcionando enquanto isso.
- **Task 11** só faz sentido depois da 3 concluída de verdade.
