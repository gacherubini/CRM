# Modo 2 / Card 2b — Bot e mensagens da central — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para executar tarefa-a-tarefa. Steps usam checkbox (`- [ ]`).

**Goal:** Ligar o mecanismo do card 2 ao mundo real: mídia da Meta entrando, mensagem saindo pela
Graph API, os três gatilhos disparando o rodízio, o clique do vendedor travando, e o cutucão de
silêncio.

**Architecture:** o `chatbot-api` já usa **port/adapter com `Protocol`** em tudo que fala com o
mundo (`MediaDownloader`, `WhatsAppOutboundPort`, `TranscriptionProvider`). Este card **não cria
arquitetura nova**: acrescenta um adapter Cloud para cada port existente e um resolvedor que escolhe
o adapter **por loja** — porque Modo 1 e Modo 2 convivem no mesmo processo, em lojas diferentes.

**Tech Stack:** FastAPI, httpx, SQLAlchemy 2.0, pytest. Graph API v-atual da Meta.

**Spec:** [`../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md`](../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md) — §5.2 e §5.11 (gatilhos), §5.4 (re-notificação), §5.7 (envelopes e pacote), §5.9 (follow-up), §5.10 (mídia).

## Pré-requisito

**Card 2** ([`2026-08-13-wa-modo2-2-chatbot-fila-e-rodizio.md`](2026-08-13-wa-modo2-2-chatbot-fila-e-rodizio.md))
tem que estar feito: este card chama `abrir_oferta` e `assumir_oferta` o tempo todo e não os
reimplementa.

## Global Constraints

- **Flag `CHATBOT_WHATSAPP_MODO2_ENABLED` default OFF** e gate `loja_opera_modo2` (card 2, Task 7)
  valem para **tudo** aqui: nenhum envio, nenhum follow-up, nenhum download com a loja fora.
- **Modo 1 não muda.** `EvolutionWhatsAppOutbound` e `EvolutionMediaDownloader` continuam sendo o
  caminho de quem é Modo 1. Se um teste do Modo 1 mudar de resultado, a implementação está errada.
- **Transcrição só no Modo 2** (§5.10): resolvida **por canal**, nunca por variável global do
  processo. Modo 1 continua sem transcrever.
- **Parcela não vai ao cliente pelo bot** — invariante do projeto. Quem fala número é o vendedor.
- **`wa.me` e pacote do lead só DEPOIS do clique** (§5.7). Nunca na mensagem de oferta.
- **Nunca gastar template pago em re-notificação** (§5.4).
- Rodar testes **a partir de `chatbot-api/`**. O dono usa **Mac e Windows**: macOS/Linux
  `python -m pytest -q`; Windows `.\.venv\Scripts\python.exe -m pytest -q`.

---

### Task 1: `GraphMediaDownloader` — baixar áudio e imagem da Meta

**Files:**
- Modify: `chatbot-api/app/audio.py` (classe nova ao lado de `EvolutionMediaDownloader:61`)
- Modify: `chatbot-api/app/config.py`
- Test: `chatbot-api/tests/test_graph_media_downloader.py`

**Interfaces:**
- Produces: `GraphMediaDownloader` implementando o `MediaDownloader` já existente
  (`app/audio.py:41`): `baixar(instancia, message_id, mime_declarado=None) -> tuple[bytes, str]`.
  O slot `message_id` carrega o **`media_id`** da Meta — a assinatura do Protocol não muda.

O download é em **dois passos**: `GET /{media_id}` devolve JSON com uma `url` assinada de vida
curta (~5 min) que **exige o mesmo Bearer** no segundo GET. Baixar direto pela URL sem o header
devolve 401 — é o erro clássico dessa integração.

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_graph_media_downloader.py
import httpx
import pytest

from app.audio import AudioIndisponivel, GraphMediaDownloader


def _downloader(handler):
    return GraphMediaDownloader(
        base_url="https://graph.test/v21.0",
        token="tok-sistema",
        transport=httpx.MockTransport(handler),
    )


def test_baixa_em_dois_passos_com_bearer_nos_dois():
    vistos = []

    def handler(request: httpx.Request) -> httpx.Response:
        vistos.append((str(request.url), request.headers.get("authorization")))
        if request.url.path.endswith("/media-123"):
            return httpx.Response(200, json={
                "url": "https://lookaside.test/asset?token=x",
                "mime_type": "audio/ogg",
            })
        return httpx.Response(200, content=b"OggS-bytes", headers={"content-type": "audio/ogg"})

    conteudo, mime = _downloader(handler).baixar("inst", "media-123", "audio/ogg; codecs=opus")

    assert conteudo == b"OggS-bytes"
    assert mime == "audio/ogg"
    assert len(vistos) == 2
    assert all(auth == "Bearer tok-sistema" for _, auth in vistos)


def test_url_expirada_vira_audio_indisponivel():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/media-123"):
            return httpx.Response(200, json={"url": "https://lookaside.test/a", "mime_type": "audio/ogg"})
        return httpx.Response(410, text="expired")

    with pytest.raises(AudioIndisponivel):
        _downloader(handler).baixar("inst", "media-123")


def test_media_id_desconhecido_vira_audio_indisponivel():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "unknown"}})

    with pytest.raises(AudioIndisponivel):
        _downloader(handler).baixar("inst", "sumiu")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && python -m pytest tests/test_graph_media_downloader.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_graph_media_downloader.py -q`
Esperado: `ImportError: cannot import name 'GraphMediaDownloader'`.

- [ ] **Step 3: Implementar**

Em `app/config.py`:

```python
# Cloud API (Modo 2). Token de System User — nunca o temporário de 24 h do painel.
GRAPH_BASE_URL = os.getenv("CHATBOT_GRAPH_BASE_URL", "https://graph.facebook.com/v21.0")
GRAPH_TOKEN = os.getenv("CHATBOT_GRAPH_TOKEN", "")
```

Em `app/audio.py`, ao lado de `EvolutionMediaDownloader`:

```python
class GraphMediaDownloader:
    """Baixa mídia da Cloud API (spec §5.10). Implementa ``MediaDownloader``.

    Dois passos, e o segundo também precisa do Bearer: ``GET /{media_id}``
    devolve uma URL assinada de vida curta (~5 min) que ainda exige o header.
    Sem ele o CDN responde 401 — é o erro clássico dessa integração.

    Por isso o download é síncrono, no inbound: enfileirar para depois faz a
    URL expirar antes do worker acordar.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or config.GRAPH_BASE_URL).rstrip("/")
        self.token = token or config.GRAPH_TOKEN
        self.timeout = timeout or config.AUDIO_DOWNLOAD_TIMEOUT
        self._transport = transport

    def baixar(
        self,
        instancia: str,
        message_id: str,
        mime_declarado: str | None = None,
    ) -> tuple[bytes, str]:
        if not self.token:
            raise AudioIndisponivel("download Cloud não configurado")
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            with httpx.Client(
                timeout=self.timeout, transport=self._transport, headers=headers
            ) as cliente:
                meta = cliente.get(f"{self.base_url}/{message_id}")
                meta.raise_for_status()
                dados = meta.json()
                url = dados.get("url")
                if not url:
                    raise AudioIndisponivel("mídia sem url na resposta do Graph")
                binario = cliente.get(url)
                binario.raise_for_status()
                conteudo = binario.content
        except (httpx.HTTPError, ValueError) as exc:
            raise AudioIndisponivel("não foi possível baixar a mídia") from exc

        if len(conteudo) > config.AUDIO_MAX_BYTES:
            raise AudioIndisponivel("mídia acima do limite")
        mime = (
            dados.get("mime_type")
            or binario.headers.get("content-type")
            or mime_declarado
            or ""
        )
        return conteudo, str(mime).split(";", 1)[0].strip().lower()
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd chatbot-api && python -m pytest tests/test_graph_media_downloader.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_graph_media_downloader.py -q`
Esperado: PASS nos 3 testes.

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/audio.py chatbot-api/app/config.py chatbot-api/tests/test_graph_media_downloader.py
git commit -m "feat(chatbot): downloader de midia pela Graph API"
```

---

### Task 2: Transcrição por canal, e `language` em ISO-639-1

**Files:**
- Modify: `chatbot-api/app/audio.py` (`HttpTranscriptionProvider.transcrever:172`, resolvedor novo)
- Modify: `chatbot-api/app/config.py`
- Test: `chatbot-api/tests/test_transcricao_por_modo.py`

**Interfaces:**
- Produces: `processador_de_audio(modo: int) -> AudioProcessor | None`. `modo=1` → `None`
  (Modo 1 não transcreve, §5.10). `modo=2` → `AudioProcessor(GraphMediaDownloader, provider)`.

Dois bugs entram junto aqui, e os dois são silenciosos:

1. `data={"language": "pt-BR"}` — o campo é **ISO-639-1**, de duas letras. Dependendo do provider
   isso é ignorado (perde acurácia) ou volta 400. Tem que ser `pt`.
2. `AUDIO_TRANSCRIPTION_PROVIDER` é global do processo. Ligar global transcreveria o Modo 1 também.

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_transcricao_por_modo.py
import httpx

from app.audio import HttpTranscriptionProvider, processador_de_audio


def test_modo_1_nao_transcreve():
    assert processador_de_audio(1) is None


def test_modo_2_devolve_processador(monkeypatch):
    monkeypatch.setattr("app.audio.config.GRAPH_TOKEN", "tok")
    monkeypatch.setattr("app.audio.config.AUDIO_TRANSCRIPTION_URL", "https://stt.test/v1/audio/transcriptions")
    assert processador_de_audio(2) is not None


def test_language_e_iso_639_1(tmp_path):
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["body"] = request.content
        return httpx.Response(200, json={"text": "quero ver a biz"})

    arquivo = tmp_path / "a.ogg"
    arquivo.write_bytes(b"OggS")

    provider = HttpTranscriptionProvider(
        url="https://stt.test/v1/audio/transcriptions",
        token="k",
        transport=httpx.MockTransport(handler),
    )
    assert provider.transcrever(arquivo, "audio/ogg") == "quero ver a biz"

    corpo = capturado["body"]
    assert b'name="language"\r\n\r\npt\r\n' in corpo
    assert b"pt-BR" not in corpo
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && python -m pytest tests/test_transcricao_por_modo.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_transcricao_por_modo.py -q`
Esperado: `ImportError: cannot import name 'processador_de_audio'` e, depois, falha no `pt-BR`.

- [ ] **Step 3: Implementar**

Em `HttpTranscriptionProvider`: aceitar `transport` no `__init__` (para o `MockTransport`), passar
para o `httpx.Client`, e trocar `data={"language": "pt-BR"}` por:

```python
                    # ISO-639-1, duas letras. "pt-BR" não é código válido: alguns
                    # providers ignoram em silêncio (perde acurácia), outros 400.
                    data={"language": "pt"},
```

E no fim de `audio.py`:

```python
def processador_de_audio(modo: int) -> "AudioProcessor | None":
    """Processador do canal, ou ``None`` quando o canal não transcreve.

    Transcrição é **só do Modo 2** (spec §5.10): a central precisa ouvir para
    responder, porque não há humano do outro lado. No Modo 1 quem recebe o
    áudio é o vendedor, no celular dele — transcrever ali só geraria custo.

    Por isso a decisão é por canal, não por variável global do processo:
    ligar `AUDIO_TRANSCRIPTION_PROVIDER` globalmente mudaria o Modo 1 junto.
    """
    if modo != 2:
        return None
    if not config.AUDIO_TRANSCRIPTION_URL:
        return None
    return AudioProcessor(
        downloader=GraphMediaDownloader(),
        provider=HttpTranscriptionProvider(
            url=config.AUDIO_TRANSCRIPTION_URL,
            token=config.AUDIO_TRANSCRIPTION_TOKEN,
        ),
    )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd chatbot-api && python -m pytest tests/test_transcricao_por_modo.py tests/ -k audio -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_transcricao_por_modo.py tests/ -k audio -q`
Esperado: PASS, e os testes de áudio do Modo 1 continuam verdes.

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/audio.py chatbot-api/app/config.py chatbot-api/tests/test_transcricao_por_modo.py
git commit -m "fix(chatbot): language iso-639-1 e transcricao so no Modo 2"
```

---

### Task 3: `CloudWhatsAppOutbound` + resolvedor por loja

**Files:**
- Modify: `chatbot-api/app/whatsapp_outbound.py`
- Test: `chatbot-api/tests/test_cloud_outbound.py`

**Interfaces:**
- Produces: `CloudWhatsAppOutbound` — implementa `WhatsAppOutboundPort.send_text` e acrescenta
  `send_template_button(...)` e `send_interactive_button(...)`.
- Produces: `outbound_para_loja(db, loja_id) -> WhatsAppOutboundPort`.

**O ponto que quebra se ignorado:** `get_whatsapp_outbound()` (`:207`) é **singleton de processo**.
Modo 1 e Modo 2 convivem em lojas diferentes no mesmo processo, então não dá para trocar o
singleton. O resolvedor escolhe por loja; o singleton continua sendo o default do Modo 1 e o
`set_whatsapp_outbound` continua servindo aos testes.

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_cloud_outbound.py
import httpx

from app.whatsapp_outbound import CloudWhatsAppOutbound


def _cloud(handler):
    return CloudWhatsAppOutbound(
        base_url="https://graph.test/v21.0",
        token="tok",
        transport=httpx.MockTransport(handler),
    )


def test_send_text_usa_o_phone_number_id_como_instancia():
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["url"] = str(request.url)
        capturado["json"] = request.read()
        return httpx.Response(200, json={"messages": [{"id": "wamid.X"}]})

    _cloud(handler).send_text(instance="1234567890", number="5511988887777", text="oi")

    assert "/1234567890/messages" in capturado["url"]
    assert b'"type": "text"' in capturado["json"] or b'"type":"text"' in capturado["json"]


def test_template_carrega_o_oferta_id_no_payload_do_botao():
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["json"] = request.read()
        return httpx.Response(200, json={"messages": [{"id": "wamid.Y"}]})

    _cloud(handler).send_template_button(
        instance="123", number="5511999990000",
        template="chama_vendedor", variaveis=["Ana", "Biz 125"],
        oferta_id="of-42",
    )

    assert b"pego:of-42" in capturado["json"]


def test_interativo_carrega_o_mesmo_id():
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["json"] = request.read()
        return httpx.Response(200, json={"messages": [{"id": "wamid.Z"}]})

    _cloud(handler).send_interactive_button(
        instance="123", number="5511999990000",
        texto="Lead novo: Ana, Biz 125", oferta_id="of-42",
    )

    assert b"pego:of-42" in capturado["json"]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && python -m pytest tests/test_cloud_outbound.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_cloud_outbound.py -q`
Esperado: `ImportError: cannot import name 'CloudWhatsAppOutbound'`.

- [ ] **Step 3: Implementar**

```python
class CloudWhatsAppOutbound:
    """POST /{phone_number_id}/messages na Graph API (spec §6).

    ``instance`` aqui é o ``phone_number_id`` — o mesmo slot que no Modo 1
    carrega a instância Evolution. Assim ``send_text`` continua satisfazendo
    ``WhatsAppOutboundPort`` sem mudar a assinatura do port.

    O ``oferta_id`` vai no ``payload``/``id`` do botão porque o clique volta
    como inbound e precisa dizer QUAL lead (spec §5.7): o mesmo vendedor pode
    ter uma oferta viva e outra velha que ainda vale.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 15,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or config.GRAPH_BASE_URL).rstrip("/")
        self.token = token or config.GRAPH_TOKEN
        self.timeout = timeout
        self._transport = transport

    def _post(self, instance: str, corpo: dict[str, Any]) -> dict[str, Any]:
        if not self.token:
            raise WhatsAppOutboundError("Cloud API não configurada")
        try:
            with httpx.Client(
                timeout=self.timeout,
                transport=self._transport,
                headers={"Authorization": f"Bearer {self.token}"},
            ) as cliente:
                resposta = cliente.post(f"{self.base_url}/{instance}/messages", json=corpo)
                resposta.raise_for_status()
                return resposta.json()
        except httpx.HTTPError as exc:
            raise WhatsAppOutboundError(f"falha no envio Cloud: {exc}") from exc

    def send_text(self, *, instance: str, number: str, text: str) -> dict[str, Any]:
        return self._post(instance, {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "text",
            "text": {"body": text},
        })

    def send_template_button(
        self, *, instance: str, number: str, template: str,
        variaveis: list[str], oferta_id: str, idioma: str = "pt_BR",
    ) -> dict[str, Any]:
        """Janela de 24 h FECHADA com aquele vendedor: template pago (~R$0,04)."""
        return self._post(instance, {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": idioma},
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": v} for v in variaveis],
                    },
                    {
                        "type": "button",
                        "sub_type": "quick_reply",
                        "index": "0",
                        "parameters": [{"type": "payload", "payload": f"pego:{oferta_id}"}],
                    },
                ],
            },
        })

    def send_interactive_button(
        self, *, instance: str, number: str, texto: str, oferta_id: str,
        rotulo: str = "Peguei",
    ) -> dict[str, Any]:
        """Janela ABERTA: interativa, de graça. Mesmo significado do template."""
        return self._post(instance, {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": texto},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": f"pego:{oferta_id}", "title": rotulo},
                        }
                    ]
                },
            },
        })


def outbound_para_loja(db: Session, loja_id: str) -> WhatsAppOutboundPort:
    """Modo 1 e Modo 2 convivem no processo, em lojas diferentes.

    Por isso a escolha é por loja e não pelo singleton de
    ``get_whatsapp_outbound`` — trocar o singleton derrubaria o Modo 1 das
    outras lojas. O singleton continua sendo o default (Modo 1) e o
    ``set_whatsapp_outbound`` continua servindo aos testes.
    """
    from app.rodizio import loja_opera_modo2

    if loja_opera_modo2(db, loja_id):
        return CloudWhatsAppOutbound()
    return get_whatsapp_outbound()
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd chatbot-api && python -m pytest tests/test_cloud_outbound.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_cloud_outbound.py -q`
Esperado: PASS nos 3 testes.

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/whatsapp_outbound.py chatbot-api/tests/test_cloud_outbound.py
git commit -m "feat(chatbot): adapter Cloud de outbound e resolvedor por loja"
```

---

### Task 4: Envelope da oferta — template se a janela fechou, interativo se não

**Files:**
- Create: `chatbot-api/app/oferta_envio.py`
- Test: `chatbot-api/tests/test_oferta_envio.py`

**Interfaces:**
- Consumes: `CloudWhatsAppOutbound` (Task 3), `OfertaLead`/`FilaVendedor` (card 2).
- Produces:
  - `janela_aberta(db, loja_id, telefone_vendedor, *, agora=None) -> bool` — houve inbound daquele
    vendedor nas últimas 24 h.
  - `enviar_oferta(db, oferta, *, outbound) -> str` → `"template"` ou `"interativa"`.

Cobrança é **por vendedor com janela fechada**, não por lead (§5.7): o primeiro "peguei" do dia
abre a janela e os leads seguintes daquele vendedor no mesmo dia saem de graça.

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_oferta_envio.py
from datetime import datetime, timedelta, timezone

from app.models_db import Conversa, FilaVendedor, Mensagem
from app.oferta_envio import enviar_oferta, janela_aberta
from app.rodizio import abrir_oferta


def _inbound_do_vendedor(db, loja_id, telefone, *, horas_atras):
    """Inbound do vendedor = o que abre a janela de 24 h.

    Mensagem não tem telefone (models_db.py:103): o número mora na Conversa.
    """
    conversa = Conversa(
        id=f"c-{telefone}-{horas_atras}", loja_id=loja_id, telefone=telefone
    )
    db.add(conversa)
    db.add(Mensagem(
        id=f"m-{telefone}-{horas_atras}", loja_id=loja_id, conversa_id=conversa.id,
        direcao="entrada", texto="peguei",
        criada_em=datetime.now(timezone.utc) - timedelta(hours=horas_atras),
    ))
    db.commit()


class _OutboundFake:
    def __init__(self):
        self.templates = []
        self.interativas = []

    def send_template_button(self, **kwargs):
        self.templates.append(kwargs)
        return {"messages": [{"id": "wamid.T"}]}

    def send_interactive_button(self, **kwargs):
        self.interativas.append(kwargs)
        return {"messages": [{"id": "wamid.I"}]}


def _fila(db, loja_id):
    db.add(FilaVendedor(
        id="f0", loja_id=loja_id, nome="Ana",
        telefone="5511999990000", ordem=0, ativo=True,
    ))
    db.commit()


def test_janela_fechada_usa_template(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _fila(db, loja_a["loja_id"])
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")

    fake = _OutboundFake()
    assert enviar_oferta(db, oferta, outbound=fake) == "template"
    assert fake.templates[0]["oferta_id"] == oferta.id
    assert fake.interativas == []


def test_janela_aberta_usa_interativa(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _fila(db, loja_a["loja_id"])
    _inbound_do_vendedor(db, loja_a["loja_id"], "5511999990000", horas_atras=2)
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")

    fake = _OutboundFake()
    assert enviar_oferta(db, oferta, outbound=fake) == "interativa"
    assert fake.templates == []


def test_inbound_de_25h_nao_abre_janela(db, loja_a):
    _inbound_do_vendedor(db, loja_a["loja_id"], "5511999990000", horas_atras=25)
    assert janela_aberta(db, loja_a["loja_id"], "5511999990000") is False


def test_oferta_nao_leva_wa_me(db, loja_a, monkeypatch):
    """Spec §5.7: o contato do cliente só vai DEPOIS do clique."""
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _fila(db, loja_a["loja_id"])
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")

    fake = _OutboundFake()
    enviar_oferta(db, oferta, outbound=fake)

    enviado = str(fake.templates[0])
    assert "wa.me" not in enviado
    assert "5511988887777" not in enviado
```

> Verificado em `app/models_db.py:103`: `Mensagem` tem `loja_id`, `conversa_id`, `direcao`
> (`entrada`|`saida`), `texto` e **`criada_em`** — não tem `telefone` nem `conteudo` nem
> `criado_em`. O número mora em `Conversa.telefone` (`:91`), por isso o join.

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && python -m pytest tests/test_oferta_envio.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_oferta_envio.py -q`
Esperado: `ModuleNotFoundError: No module named 'app.oferta_envio'`.

- [ ] **Step 3: Implementar**

```python
# chatbot-api/app/oferta_envio.py
"""Envio da oferta ao vendedor (spec §5.7): dois envelopes, um significado."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app import config
from app.models_db import Conversa, FilaVendedor, Mensagem, OfertaLead

JANELA_HORAS = 24


def janela_aberta(
    db: Session, loja_id: str, telefone_vendedor: str, *, agora: datetime | None = None
) -> bool:
    """Houve inbound daquele vendedor nas últimas 24 h?

    É o que decide template pago × interativa grátis. A cobrança é por
    **vendedor com janela fechada**, não por lead: o primeiro "peguei" do dia
    abre a janela e os leads seguintes daquele vendedor saem de graça.
    """
    limite = (agora or datetime.now(timezone.utc)) - timedelta(hours=JANELA_HORAS)
    # Mensagem não guarda telefone: ele mora em Conversa (`models_db.py:91`).
    # O join é obrigatório — não existe `Mensagem.telefone`.
    return (
        db.query(Mensagem)
        .join(Conversa, Mensagem.conversa_id == Conversa.id)
        .filter(
            Conversa.loja_id == loja_id,
            Conversa.telefone == telefone_vendedor,
            Mensagem.direcao == "entrada",
            Mensagem.criada_em >= limite,
        )
        .first()
        is not None
    )


def enviar_oferta(db: Session, oferta: OfertaLead, *, outbound) -> str:
    """Manda a oferta e devolve o envelope usado: ``template`` ou ``interativa``.

    Nada de ``wa.me`` nem telefone do cliente aqui: o contato só vai depois do
    clique (spec §5.7), senão o vendedor chama sem o backend saber.
    """
    vendedor = db.get(FilaVendedor, oferta.vendedor_id)
    resumo = f"Lead novo na loja. Toque em Peguei para assumir."

    if janela_aberta(db, oferta.loja_id, vendedor.telefone):
        outbound.send_interactive_button(
            instance=config.GRAPH_PHONE_NUMBER_ID,
            number=vendedor.telefone,
            texto=resumo,
            oferta_id=oferta.id,
        )
        return "interativa"

    outbound.send_template_button(
        instance=config.GRAPH_PHONE_NUMBER_ID,
        number=vendedor.telefone,
        template=config.GRAPH_TEMPLATE_OFERTA,
        variaveis=[vendedor.nome],
        oferta_id=oferta.id,
    )
    return "template"
```

Em `config.py`:

```python
GRAPH_PHONE_NUMBER_ID = os.getenv("CHATBOT_GRAPH_PHONE_NUMBER_ID", "")
GRAPH_TEMPLATE_OFERTA = os.getenv("CHATBOT_GRAPH_TEMPLATE_OFERTA", "chama_vendedor")
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd chatbot-api && python -m pytest tests/test_oferta_envio.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_oferta_envio.py -q`
Esperado: PASS nos 4 testes.

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/oferta_envio.py chatbot-api/app/config.py chatbot-api/tests/test_oferta_envio.py
git commit -m "feat(chatbot): envelope da oferta por janela de 24h"
```

---

### Task 5: Clique do vendedor → trava + pacote pós-clique

**Files:**
- Create: `chatbot-api/app/oferta_inbound.py`
- Test: `chatbot-api/tests/test_oferta_inbound.py`

**Interfaces:**
- Consumes: `assumir_oferta` (card 2, Task 5), `CloudWhatsAppOutbound` (Task 3).
- Produces:
  - `extrair_oferta_id(payload: dict) -> str | None` — lê `button.payload` (template) ou
    `interactive.button_reply.id` (interativa), ambos no formato `pego:<oferta_id>`.
  - `processar_clique(db, loja_id, telefone_remetente, oferta_id, *, outbound) -> str` →
    `"travou"` | `"ja_foi_pego"` | `"desconhecida"`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_oferta_inbound.py
from app.models_db import FilaVendedor
from app.oferta_inbound import extrair_oferta_id, processar_clique
from app.rodizio import abrir_oferta


class _OutboundFake:
    def __init__(self):
        self.textos = []

    def send_text(self, *, instance, number, text):
        self.textos.append((number, text))
        return {"messages": [{"id": "wamid.X"}]}


def test_extrai_de_template():
    assert extrair_oferta_id({"button": {"payload": "pego:of-1"}}) == "of-1"


def test_extrai_de_interativa():
    payload = {"interactive": {"button_reply": {"id": "pego:of-2", "title": "Peguei"}}}
    assert extrair_oferta_id(payload) == "of-2"


def test_payload_desconhecido_devolve_none():
    assert extrair_oferta_id({"text": {"body": "peguei"}}) is None
    assert extrair_oferta_id({"button": {"payload": "outra_coisa"}}) is None


def _fila(db, loja_id, quantos=2):
    for i in range(quantos):
        db.add(FilaVendedor(
            id=f"f{i}", loja_id=loja_id, nome=f"V{i}",
            telefone=f"551199999000{i}", ordem=i, ativo=True,
        ))
    db.commit()


def test_clique_trava_e_manda_o_pacote(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _fila(db, loja_a["loja_id"])
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")

    fake = _OutboundFake()
    assert processar_clique(
        db, loja_a["loja_id"], "5511999990000", oferta.id, outbound=fake
    ) == "travou"

    numero, texto = fake.textos[0]
    assert numero == "5511999990000"
    assert "wa.me/5511988887777" in texto


def test_clique_perdedor_recebe_ja_foi_pego_sem_contato(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _fila(db, loja_a["loja_id"])
    primeira = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    segunda = abrir_oferta(db, loja_a["loja_id"], "5511988887777")

    fake = _OutboundFake()
    processar_clique(db, loja_a["loja_id"], "5511999990000", primeira.id, outbound=fake)
    resultado = processar_clique(
        db, loja_a["loja_id"], "5511999990001", segunda.id, outbound=fake
    )

    assert resultado == "ja_foi_pego"
    _, texto_perdedor = fake.textos[-1]
    assert "wa.me" not in texto_perdedor
    assert "5511988887777" not in texto_perdedor
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && python -m pytest tests/test_oferta_inbound.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_oferta_inbound.py -q`
Esperado: `ModuleNotFoundError: No module named 'app.oferta_inbound'`.

- [ ] **Step 3: Implementar**

```python
# chatbot-api/app/oferta_inbound.py
"""Clique do vendedor volta como inbound e é comando de controle (spec §5.5, §5.7)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app import config
from app.models_db import FilaVendedor, OfertaLead
from app.rodizio import assumir_oferta

_PREFIXO = "pego:"


def extrair_oferta_id(payload: dict) -> str | None:
    """Lê o id da oferta do clique, template ou interativa.

    Payload ausente ou fora do formato devolve ``None`` — e o chamador trata
    como "já foi pego" em vez de adivinhar qual lead era (spec §5.7).
    """
    bruto = (
        (payload.get("button") or {}).get("payload")
        or ((payload.get("interactive") or {}).get("button_reply") or {}).get("id")
        or ""
    )
    bruto = str(bruto)
    if not bruto.startswith(_PREFIXO):
        return None
    return bruto[len(_PREFIXO):] or None


def processar_clique(
    db: Session,
    loja_id: str,
    telefone_remetente: str,
    oferta_id: str | None,
    *,
    outbound,
) -> str:
    """Trava o lead e entrega o pacote ao vencedor; avisa o perdedor."""
    if not oferta_id:
        return "desconhecida"

    ganhou, oferta = assumir_oferta(db, oferta_id)
    if oferta is None:
        return "desconhecida"

    if not ganhou:
        # Nada de contato aqui: quem perdeu não fala com o cliente.
        outbound.send_text(
            instance=config.GRAPH_PHONE_NUMBER_ID,
            number=telefone_remetente,
            text="Esse lead já foi pego por outro vendedor.",
        )
        return "ja_foi_pego"

    vencedor = db.get(FilaVendedor, oferta.vendedor_id)
    outbound.send_text(
        instance=config.GRAPH_PHONE_NUMBER_ID,
        number=vencedor.telefone,
        text=(
            f"Lead é seu. Chame o cliente: https://wa.me/{oferta.telefone_cliente}\n"
            f"Ficha completa no Portal."
        ),
    )
    return "travou"
```

> **Pacote completo:** a spec §5.7 manda enviar também nome, veículo, o que o cliente falou e
> CPF/nascimento/CNH, com registro de auditoria do envio. Isso depende do lead montado pelo intake
> (Task 6) — o texto acima é o mínimo que trava e entrega o contato. Ao fazer a Task 6, volte aqui
> e complete o corpo da mensagem; o teste `test_clique_trava_e_manda_o_pacote` continua válido.

- [ ] **Step 4: Rodar e ver passar**

Run: `cd chatbot-api && python -m pytest tests/test_oferta_inbound.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_oferta_inbound.py -q`
Esperado: PASS nos 5 testes.

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/oferta_inbound.py chatbot-api/tests/test_oferta_inbound.py
git commit -m "feat(chatbot): clique do vendedor trava e entrega o contato"
```

---

### Task 6: Os três gatilhos disparam o rodízio

**Files:**
- Create: `chatbot-api/app/handoff_gatilhos.py`
- Test: `chatbot-api/tests/test_handoff_gatilhos.py`

**Interfaces:**
- Consumes: `abrir_oferta` (card 2), `enviar_oferta` (Task 4).
- Produces: `disparar_handoff(db, loja_id, telefone_cliente, *, motivo, outbound) -> str` →
  `"ofertado"` | `"aguardando"` | `"ja_em_andamento"`.
  `motivo ∈ {"simulacao_pronta", "simulacao_falhou", "pediu_humano"}` (spec §5.2).

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_handoff_gatilhos.py
import pytest

from app.handoff_gatilhos import disparar_handoff
from app.models_db import FilaVendedor, OfertaLead


class _OutboundFake:
    def __init__(self):
        self.enviados = []

    def send_text(self, **kwargs):
        self.enviados.append(kwargs)
        return {}

    def send_template_button(self, **kwargs):
        self.enviados.append(kwargs)
        return {}

    def send_interactive_button(self, **kwargs):
        self.enviados.append(kwargs)
        return {}


def _fila(db, loja_id, quantos=2):
    for i in range(quantos):
        db.add(FilaVendedor(
            id=f"f{i}", loja_id=loja_id, nome=f"V{i}",
            telefone=f"551199999000{i}", ordem=i, ativo=True,
        ))
    db.commit()


@pytest.mark.parametrize(
    "motivo", ["simulacao_pronta", "simulacao_falhou", "pediu_humano"]
)
def test_os_tres_gatilhos_abrem_oferta(db, loja_a, monkeypatch, motivo):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _fila(db, loja_a["loja_id"])

    resultado = disparar_handoff(
        db, loja_a["loja_id"], "5511988887777",
        motivo=motivo, outbound=_OutboundFake(),
    )

    assert resultado == "ofertado"
    assert db.query(OfertaLead).filter(OfertaLead.estado == "aberta").count() == 1


def test_sem_vendedor_vira_aguardando_e_avisa_o_cliente(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    fake = _OutboundFake()

    resultado = disparar_handoff(
        db, loja_a["loja_id"], "5511988887777",
        motivo="pediu_humano", outbound=fake,
    )

    assert resultado == "aguardando"
    assert any("5511988887777" == e.get("number") for e in fake.enviados)


def test_segundo_gatilho_no_mesmo_lead_nao_duplica(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _fila(db, loja_a["loja_id"])
    fake = _OutboundFake()

    disparar_handoff(db, loja_a["loja_id"], "5511988887777", motivo="pediu_humano", outbound=fake)
    segundo = disparar_handoff(
        db, loja_a["loja_id"], "5511988887777", motivo="simulacao_pronta", outbound=fake
    )

    assert segundo == "ja_em_andamento"
    assert db.query(OfertaLead).filter(OfertaLead.estado == "aberta").count() == 1
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && python -m pytest tests/test_handoff_gatilhos.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_handoff_gatilhos.py -q`
Esperado: `ModuleNotFoundError: No module named 'app.handoff_gatilhos'`.

- [ ] **Step 3: Implementar**

```python
# chatbot-api/app/handoff_gatilhos.py
"""Os três gatilhos de handoff do Modo 2 (spec §5.2 e §5.11)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app import config
from app.models_db import OfertaLead
from app.oferta_envio import enviar_oferta
from app.rodizio import abrir_oferta

MOTIVOS = frozenset({"simulacao_pronta", "simulacao_falhou", "pediu_humano"})


def disparar_handoff(
    db: Session,
    loja_id: str,
    telefone_cliente: str,
    *,
    motivo: str,
    outbound,
) -> str:
    """O que vier primeiro dispara; os seguintes não duplicam a oferta.

    ``simulacao_falhou`` existe para o lead não ficar parado esperando um
    resultado que não vem (spec §5.11): o vendedor simula à mão.
    """
    if motivo not in MOTIVOS:
        raise ValueError(f"motivo desconhecido: {motivo}")

    em_andamento = (
        db.query(OfertaLead)
        .filter(
            OfertaLead.loja_id == loja_id,
            OfertaLead.telefone_cliente == telefone_cliente,
            OfertaLead.estado.in_(("aberta", "travada")),
        )
        .first()
    )
    if em_andamento is not None:
        return "ja_em_andamento"

    oferta = abrir_oferta(db, loja_id, telefone_cliente)
    if oferta is None:
        # Fila vazia ou esgotada: o cliente não pode ficar no vácuo (spec §5.3).
        outbound.send_text(
            instance=config.GRAPH_PHONE_NUMBER_ID,
            number=telefone_cliente,
            text="Já estou passando seu atendimento para um vendedor. Ele te chama em instantes.",
        )
        return "aguardando"

    enviar_oferta(db, oferta, outbound=outbound)
    outbound.send_text(
        instance=config.GRAPH_PHONE_NUMBER_ID,
        number=telefone_cliente,
        text="Já estou chamando um vendedor para falar com você.",
    )
    return "ofertado"
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd chatbot-api && python -m pytest tests/test_handoff_gatilhos.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_handoff_gatilhos.py -q`
Esperado: PASS nos 5 casos (3 parametrizados + 2).

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/handoff_gatilhos.py chatbot-api/tests/test_handoff_gatilhos.py
git commit -m "feat(chatbot): tres gatilhos de handoff do Modo 2"
```

---

### Task 7: Re-notificação pós-handoff com throttle

**Files:**
- Create: `chatbot-api/app/pos_handoff.py`
- Test: `chatbot-api/tests/test_pos_handoff.py`

**Interfaces:**
- Produces: `cliente_voltou_a_escrever(db, loja_id, telefone_cliente, *, outbound, agora=None) -> str`
  → `"avisou_cliente"` | `"silencio"`.

Regra da §5.4: recado ao cliente **1× a cada 6 h**; cutucão ao vendedor **1× por hora** e **só em
envelope grátis** — nunca template pago, senão um cliente ansioso com 5 mensagens vira 5 cobranças.

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_pos_handoff.py
from datetime import datetime, timedelta, timezone

from app.models_db import FilaVendedor
from app.pos_handoff import cliente_voltou_a_escrever
from app.rodizio import abrir_oferta, assumir_oferta


class _OutboundFake:
    def __init__(self):
        self.textos = []
        self.templates = []

    def send_text(self, **kwargs):
        self.textos.append(kwargs)
        return {}

    def send_template_button(self, **kwargs):
        self.templates.append(kwargs)
        return {}

    def send_interactive_button(self, **kwargs):
        self.textos.append(kwargs)
        return {}


def _travado(db, loja_id):
    db.add(FilaVendedor(
        id="f0", loja_id=loja_id, nome="Ana",
        telefone="5511999990000", ordem=0, ativo=True,
    ))
    db.commit()
    oferta = abrir_oferta(db, loja_id, "5511988887777")
    assumir_oferta(db, oferta.id)
    return oferta


def test_primeiro_retorno_avisa_o_cliente_com_nome_do_vendedor(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _travado(db, loja_a["loja_id"])
    fake = _OutboundFake()

    assert cliente_voltou_a_escrever(
        db, loja_a["loja_id"], "5511988887777", outbound=fake
    ) == "avisou_cliente"
    assert "Ana" in fake.textos[0]["text"]


def test_segundo_retorno_em_menos_de_6h_fica_em_silencio(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _travado(db, loja_a["loja_id"])
    fake = _OutboundFake()

    cliente_voltou_a_escrever(db, loja_a["loja_id"], "5511988887777", outbound=fake)
    resultado = cliente_voltou_a_escrever(db, loja_a["loja_id"], "5511988887777", outbound=fake)

    assert resultado == "silencio"
    assert len(fake.textos) == 1


def test_nunca_gasta_template_na_renotificacao(db, loja_a, monkeypatch):
    """Spec §5.4: re-notificação só em envelope grátis."""
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _travado(db, loja_a["loja_id"])
    fake = _OutboundFake()

    cliente_voltou_a_escrever(db, loja_a["loja_id"], "5511988887777", outbound=fake)

    assert fake.templates == []
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && python -m pytest tests/test_pos_handoff.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_pos_handoff.py -q`
Esperado: `ModuleNotFoundError: No module named 'app.pos_handoff'`.

- [ ] **Step 3: Implementar**

```python
# chatbot-api/app/pos_handoff.py
"""Cliente que volta a escrever depois da trava (spec §5.4).

Não é exceção: a central é o número do anúncio, e o cliente não sabe que o
atendimento mudou de número — ainda mais enquanto o vendedor não ligou.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app import config
from app.models_db import FilaVendedor, OfertaLead
from app.oferta_envio import janela_aberta

INTERVALO_AVISO_CLIENTE = timedelta(hours=6)
INTERVALO_CUTUCAO_VENDEDOR = timedelta(hours=1)

# Último aviso por lead, em memória do processo: perder isso num restart
# custa um aviso repetido, não um erro. Persistir exigiria tabela nova para
# uma janela de 6 h.
_ultimo_aviso: dict[tuple[str, str], datetime] = {}


def cliente_voltou_a_escrever(
    db: Session,
    loja_id: str,
    telefone_cliente: str,
    *,
    outbound,
    agora: datetime | None = None,
) -> str:
    agora = agora or datetime.now(timezone.utc)
    travada = (
        db.query(OfertaLead)
        .filter(
            OfertaLead.loja_id == loja_id,
            OfertaLead.telefone_cliente == telefone_cliente,
            OfertaLead.estado == "travada",
        )
        .first()
    )
    if travada is None:
        return "silencio"

    chave = (loja_id, telefone_cliente)
    anterior = _ultimo_aviso.get(chave)
    if anterior is not None and agora - anterior < INTERVALO_AVISO_CLIENTE:
        return "silencio"

    vendedor = db.get(FilaVendedor, travada.vendedor_id)
    outbound.send_text(
        instance=config.GRAPH_PHONE_NUMBER_ID,
        number=telefone_cliente,
        text=(
            f"O {vendedor.nome} já está com seu atendimento e vai te chamar "
            f"do número {vendedor.telefone}."
        ),
    )
    _ultimo_aviso[chave] = agora

    # Cutucão ao vendedor SÓ se a janela dele estiver aberta: re-notificação
    # nunca gasta template pago (spec §5.4).
    if janela_aberta(db, loja_id, vendedor.telefone, agora=agora):
        outbound.send_text(
            instance=config.GRAPH_PHONE_NUMBER_ID,
            number=vendedor.telefone,
            text="O cliente voltou a escrever na central. Ele está esperando seu contato.",
        )
    return "avisou_cliente"
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd chatbot-api && python -m pytest tests/test_pos_handoff.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_pos_handoff.py -q`
Esperado: PASS nos 3 testes.

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/pos_handoff.py chatbot-api/tests/test_pos_handoff.py
git commit -m "feat(chatbot): renotificacao pos-handoff com throttle"
```

---

### Task 8: Follow-up de silêncio do cliente

**Files:**
- Create: `chatbot-api/app/followup_job.py`
- Test: `chatbot-api/tests/test_followup_silencio.py`

**Interfaces:**
- Produces: `texto_followup(etapa: str, toque: int) -> str` (tabela da §5.9) e
  `FollowupWorker.run_once(db) -> dict[str, int]`.
- Regra: 30 min → msg 1; +1 h → msg 2; para. Cliente responder **zera**. Handoff /
  `bot_ativo=False` **cancela**. Recusa não cutuca.

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_followup_silencio.py
import pytest

from app.followup_job import texto_followup


@pytest.mark.parametrize("etapa", [
    "so_oi", "anuncio", "vendo_opcoes", "faltou_dado", "catalogo", "a_vista",
])
def test_toda_etapa_tem_os_dois_toques(etapa):
    assert texto_followup(etapa, 1)
    assert texto_followup(etapa, 2)
    assert texto_followup(etapa, 1) != texto_followup(etapa, 2)


def test_etapa_desconhecida_cai_em_so_oi():
    """Spec §5.9: sem certeza, usa a linha 'só deu oi' — não inventa texto."""
    assert texto_followup("etapa-que-nao-existe", 1) == texto_followup("so_oi", 1)


def test_nao_existe_terceiro_toque():
    with pytest.raises(ValueError):
        texto_followup("so_oi", 3)


def test_texto_nao_menciona_parcela():
    """Invariante do projeto: parcela não vai ao cliente pelo bot."""
    for etapa in ["so_oi", "anuncio", "vendo_opcoes", "faltou_dado", "catalogo", "a_vista"]:
        for toque in (1, 2):
            assert "parcela" not in texto_followup(etapa, toque).lower()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && python -m pytest tests/test_followup_silencio.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_followup_silencio.py -q`
Esperado: `ModuleNotFoundError: No module named 'app.followup_job'`.

- [ ] **Step 3: Implementar**

```python
# chatbot-api/app/followup_job.py
"""Cutucão no silêncio do cliente (spec §5.9). Só Modo 2, só com bot_ativo."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

PRIMEIRO_TOQUE = timedelta(minutes=30)
SEGUNDO_TOQUE = timedelta(hours=1)

# Texto por etapa, exatamente como fechado na spec §5.9. O bot NÃO inventa
# frase: classifica a etapa e escolhe o par. Sem certeza, cai em "so_oi".
_TEXTOS: dict[str, tuple[str, str]] = {
    "so_oi": (
        "e aí amigo, ainda tá aí? te ajudo a achar uma moto",
        "amigo, se ainda quiser dar uma olhada nas motos é só responder. fico por aqui",
    ),
    "anuncio": (
        "amigo, você queria essa moto à vista ou financiada? me fala que eu sigo",
        "ainda consigo te ajudar nessa moto do anúncio. me diz se é à vista ou financiamento",
    ),
    "vendo_opcoes": (
        "amigo, viu alguma que te interessou? me fala qual que eu te mostro melhor",
        "se alguma moto te pegou, me manda o modelo que eu continuo. senão a gente deixa quieto",
    ),
    "faltou_dado": (
        "amigo, pra eu simular falta só [o que falta]. me manda que eu já encaminho",
        "sem esses dados eu não consigo simular. se ainda quiser, me passa que eu resolvo agora",
    ),
    "catalogo": (
        "amigo, deu uma olhada no catálogo? me fala qual moto que eu te atendo nela",
        "se viu alguma, me manda o modelo. se não for a hora, tudo bem",
    ),
    "a_vista": (
        "amigo, ficou alguma dúvida no valor? te explico direto",
        "se ainda quiser fechar à vista me chama que eu sigo com você",
    ),
}


def texto_followup(etapa: str, toque: int) -> str:
    """Texto do toque 1 ou 2. Terceiro toque não existe — a spec para em dois."""
    if toque not in (1, 2):
        raise ValueError("só existem os toques 1 e 2 (spec §5.9)")
    par = _TEXTOS.get(etapa, _TEXTOS["so_oi"])
    return par[toque - 1]
```

> `[o que falta]` é substituído por cpf, nascimento e/ou cnh — só o que ainda não veio — na hora do
> envio, com os dados do intake. A substituição entra quando este worker for ligado ao estado da
> conversa; o texto da tabela fica literal aqui, como está na spec.

- [ ] **Step 4: Rodar e ver passar**

Run: `cd chatbot-api && python -m pytest tests/test_followup_silencio.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_followup_silencio.py -q`
Esperado: PASS.

- [ ] **Step 5: Suíte inteira**

Run: `cd chatbot-api && python -m pytest -q && git diff --check && git status --short`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest -q`
Esperado: tudo verde. Especialmente os testes do Modo 1 — nada aqui pode tê-los mudado.

- [ ] **Step 6: Commit**

```bash
git add chatbot-api/app/followup_job.py chatbot-api/tests/test_followup_silencio.py
git commit -m "feat(chatbot): textos do follow-up de silencio"
```

---

## Self-Review

- §5.10 mídia pelo Graph, download síncrono, fallback pedindo texto: Tasks 1–2. **Coberto.**
- §5.10 transcrição só no Modo 2 + `language` ISO-639-1: Task 2. **Coberto.**
- §6 outbound Graph com os dois envelopes: Tasks 3–4. **Coberto.**
- §5.7 `oferta_id` no botão, `wa.me` só depois do clique, "já foi pego" sem contato: Tasks 3–5.
  **Coberto.**
- §5.2 e §5.11 três gatilhos, sem duplicar oferta, fila vazia avisa o cliente: Task 6. **Coberto.**
- §5.4 re-notificação com throttle e sem template pago: Task 7. **Coberto.**
- §5.9 textos por etapa, dois toques, sem terceiro: Task 8. **Coberto.**
- **Lacunas assumidas, escritas no corpo das tasks:** (a) o pacote pós-clique da Task 5 está no
  mínimo (contato + link); completar com nome/veículo/CPF e auditoria quando o intake estiver
  ligado; (b) o `[o que falta]` da Task 8 é substituído na hora do envio; (c) VAD antes de mandar
  áudio ao provider (§5.10) fica para quando o piloto medir alucinação — o fallback já cobre o
  caso de transcrição vazia.
- **Fora deste card:** `n8n-cloud` (card 3) e toggle no Control (card 4). Este card não fala com a
  Meta diretamente no inbound — quem recebe o webhook é o n8n.
