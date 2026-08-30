# Embedded Signup — Card 4: a tela na Revy Loja

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development`
> (recomendado) ou `superpowers:executing-plans` para executar task a task. Os passos usam
> checkbox (`- [ ]`).

**Goal:** o dono da loja conecta o WhatsApp dele sozinho, por um botão na Revy Loja — e a
tela de canais para de mentir sobre canal Cloud.

**Architecture:** só `portal-gestao`. A tela que já existe
(`/app/loja/whatsapp`, `app/web/loja_whatsapp.py:109`) ganha o vocabulário do Modo 2 na
view (`app/loja/whatsapp_canais.py`), uma tela de decisão nova, o popup do SDK da Meta e o
POST que repassa os quatro campos ao `chatbot-api`. **Nenhuma regra de negócio nova aqui:**
a cadeia inteira já está no chatbot (Card 3), e este card é a superfície dela.

**Tech Stack:** FastAPI, Jinja2, JS sem framework (o padrão da Loja), pytest.

**Spec:** [`../referencia-viva/specs/2026-08-29-embedded-signup-tech-provider-design.md`](../referencia-viva/specs/2026-08-29-embedded-signup-tech-provider-design.md) — §6 é a seção desta tela.

**Depende de:** Card 3 (feito e no ar, `ecc58c4`). O `config_id` do popup **depende do App
Review**, e por isso a Task 4 é a única que não pode ser concluída hoje — as outras quatro
não dependem dele.

## Global Constraints

- **Testes a partir de `portal-gestao/`:** `.venv/bin/python -m pytest -q` (macOS) e
  `.\.venv\Scripts\python.exe -m pytest -q` (Windows).
- **Decisão 9 do dono:** gerente **vê** a tela; só o **dono** conecta. O gate de hoje
  (`_autorizado`, `ROLES_GESTAO` = dono + gerente, `app/loja/types.py:33`) serve para ver,
  **não** para conectar.
- **Decisão 10:** o conserto dos rótulos Cloud vai neste card, não depois.
- **Mudou `app.css`? Suba o `?v=` no `base.html`** — senão prod serve o CSS velho. Telas de
  auth têm `?v=` próprio.
- **JS só se verifica no navegador.** `pytest` não roda o popup. A Task 4 tem passo de
  navegador obrigatório, com portal local semeado.
- **13 itens de UI foram recusados pelo dono em 07/08** e não voltam como proposta. Antes de
  inventar elemento de tela, leia
  `docs/referencia-viva/2026-08-07-triagem-revisao-ux-loja-control.md`.
- Ao terminar: `git diff --check`, `git status --short`, e regerar o mapa.

## O que já está errado hoje, e este card conserta

Com `estado = "cloud_pendente"`, `montar_canais_view`
(`portal-gestao/app/loja/whatsapp_canais.py:39`) faz duas coisas erradas:

1. `rotulo = ROTULOS.get(estado, estado)` — e `ROTULOS` (linha 10) só tem o vocabulário do
   **Modo 1** (`conectado`, `pendente`, `desconectado`, `inativo`). O canal Cloud aparece com
   o nome técnico cru na tela do lojista.
2. `pode_conectar = estado != "conectado"` — dá **`True`** para todo canal Cloud, e a tela
   oferece o botão Conectar do Modo 1. Esse botão chama
   `chatbot.conectar_canal_whatsapp` (`app/web/loja_whatsapp.py:241`), que **pede QR na
   Evolution** — para um número que é da Cloud API.

Já existe canal Cloud em produção. Isto não é hipótese.

---

### Task 0: o chatbot precisa DEVOLVER o estado do onboarding

**Files:**
- Modify: `chatbot-api/app/channels.py` (`_canal_dict`, linha 27)
- Test: `chatbot-api/tests/test_canal_dict_expoe_onboarding.py`

**Este é o único ponto deste card fora do `portal-gestao`** — e é contrato HTTP, não import
cruzado.

**Por que existe, e é urgente:** a Task 1 decide se um canal é Cloud lendo `waba_id` do
payload. `_canal_dict` **não devolve `waba_id`**. Os testes da Task 1 usam dicionários
sintéticos, então passam — e em produção `cloud` seria `False` para todo canal, o botão
errado continuaria na tela, e a Task 1 inteira seria **teste verde sem feature**: o mesmo
defeito que já entregou o Modo 2 sem bot uma vez.

O serializer passa a devolver `waba_id`, `template_oferta`, `onboarding_elo` e
`onboarding_erro`. **Nada além disso:** `token_cifrado` e `pin_cifrado` continuam fora, e
`tests/test_canal_nao_vaza_segredo.py` já guarda essa porta — rode-o junto.

- [x] **Passo 1: o teste que falha**

```python
# chatbot-api/tests/test_canal_dict_expoe_onboarding.py
"""A Loja desenha a tela lendo ESTE dicionario (spec §6).

Sem `waba_id` aqui a Loja nao distingue canal Cloud de canal Modo 1, e oferece
nele o botao que pede QR na Evolution. Sem `onboarding_elo` e `onboarding_erro`
a tela nao sabe dizer qual passo parou, e manda o lojista abrir o painel da
Meta — que e o que este projeto existe para acabar.
"""
import uuid

from app.channels import _canal_dict
from app.models_db import WhatsAppCanal

PROIBIDOS = {"token_cifrado", "pin_cifrado", "token", "pin", "access_token"}


def _canal(**campos):
    base = dict(
        id=str(uuid.uuid4()),
        loja_id="l1",
        e164_or_label="linha-cloud",
        evolution_instance="1227059273831620",
        estado="cloud_pendente",
    )
    base.update(campos)
    return WhatsAppCanal(**base)


def test_expoe_o_que_a_tela_da_loja_precisa():
    dados = _canal_dict(
        _canal(waba_id="waba-1", template_oferta="chama_vendedor",
               onboarding_elo=3, onboarding_erro="parou ao registrar")
    )

    assert dados["waba_id"] == "waba-1"
    assert dados["template_oferta"] == "chama_vendedor"
    assert dados["onboarding_elo"] == 3
    assert dados["onboarding_erro"] == "parou ao registrar"


def test_canal_do_modo_1_traz_os_campos_nulos():
    """Modo 1 nao tem nada disso, e `None` e a resposta certa — nao ausencia,
    que obrigaria a Loja a usar `.get` com default em toda leitura."""
    dados = _canal_dict(_canal(estado="conectado"))

    assert dados["waba_id"] is None
    assert dados["onboarding_elo"] is None


def test_continua_sem_devolver_segredo():
    dados = _canal_dict(
        _canal(waba_id="waba-1", token_cifrado="gAAAA-x", pin_cifrado="gAAAA-y")
    )

    assert PROIBIDOS.isdisjoint(dados.keys())
    assert "gAAAA" not in str(dados)
```

- [x] **Passo 2:** rodar e ver falhar (`KeyError: 'waba_id'`).
- [x] **Passo 3:** acrescentar os quatro campos ao `_canal_dict`, **listando-os um a um** —
      nunca devolvendo o modelo inteiro nem usando `exclude`, que volta a vazar na próxima
      coluna.
- [x] **Passo 4:** rodar, ver passar, e rodar junto `tests/test_canal_nao_vaza_segredo.py`.
- [x] **Passo 5:** commitar.

---

### Task 1: o vocabulário do Modo 2 na view

**Files:**
- Modify: `portal-gestao/app/loja/whatsapp_canais.py`
- Test: `portal-gestao/tests/test_canais_view_modo2.py`

**Interfaces:**
- Produces: `CanalView` ganha `cloud: bool`. `ROTULOS` ganha os quatro estados Cloud.
  `pode_conectar` e `pode_desconectar` passam a ser `False` em canal Cloud — as ações do
  Modo 1 não se aplicam a ele.

- [x] **Passo 1: escrever o teste que falha**

```python
# portal-gestao/tests/test_canais_view_modo2.py
"""A tela de canais tem de falar do canal Cloud sem mentir.

Hoje ela mostra o nome tecnico cru como rotulo e oferece o botao Conectar do
Modo 1 — que pede QR na Evolution — para um numero que e da Cloud API.
"""
from app.loja.whatsapp_canais import montar_canais_view


def _bruto(estado, **extra):
    base = {
        "id": "c1",
        "e164_or_label": "linha-cloud",
        "evolution_instance": "1227059273831581",
        "estado": estado,
        "ativo": True,
        "principal_estoque": False,
    }
    base.update(extra)
    return base


def test_canal_cloud_nao_mostra_o_nome_tecnico():
    view = montar_canais_view([_bruto("cloud_pendente", waba_id="waba-1")])

    canal = view.canais[0]
    assert canal.rotulo != "cloud_pendente"
    assert "cloud_" not in canal.rotulo


def test_canal_cloud_nao_oferece_o_botao_do_modo_1():
    """O botao chama conectar_canal_whatsapp, que pede QR na Evolution."""
    view = montar_canais_view([_bruto("cloud_pendente", waba_id="waba-1")])

    canal = view.canais[0]
    assert canal.pode_conectar is False
    assert canal.pode_desconectar is False
    assert canal.cloud is True


def test_canal_cloud_ativo_tambem_nao_oferece():
    view = montar_canais_view([_bruto("cloud_ativo", waba_id="waba-1")])

    assert view.canais[0].pode_desconectar is False


def test_os_quatro_estados_cloud_tem_rotulo_proprio():
    """Restrito e banido vem da Meta e nao se conserta clicando: o rotulo tem
    de dizer isso, senao o lojista fica tentando."""
    estados = ["cloud_pendente", "cloud_ativo", "cloud_restrito", "cloud_banido"]
    view = montar_canais_view(
        [_bruto(e, id=f"c{i}", evolution_instance=f"12270592738315{80 + i}",
                waba_id="waba-1")
         for i, e in enumerate(estados)]
    )

    rotulos = [c.rotulo for c in view.canais]
    assert len(set(rotulos)) == 4, f"estados diferentes com o mesmo rotulo: {rotulos}"
    for rotulo in rotulos:
        assert "cloud_" not in rotulo


def test_canal_do_modo_1_nao_muda():
    """Regressao: a loja piloto opera no Modo 1 e nada aqui pode mexer nela."""
    view = montar_canais_view([_bruto("conectado")])

    canal = view.canais[0]
    assert canal.rotulo == "Conectado"
    assert canal.pode_conectar is False
    assert canal.pode_desconectar is True
    assert canal.cloud is False
```

- [x] **Passo 2: rodar e ver falhar**

Rode: `.\.venv\Scripts\python.exe -m pytest tests/test_canais_view_modo2.py -q`
Esperado: FAIL — `AttributeError: 'CanalView' object has no attribute 'cloud'` e
`assert 'cloud_pendente' != 'cloud_pendente'`.

- [x] **Passo 3: implementar**

Em `app/loja/whatsapp_canais.py`, acrescente os rótulos do Modo 2 ao dicionário `ROTULOS`:

```python
    # Modo 2 (Cloud API). O vocabulário técnico mora em
    # ``whatsapp_provider.ESTADOS_VALIDOS``, no chatbot; aqui ele vira frase de
    # dono de loja. Restrito e banido vêm da Meta e NÃO se consertam clicando —
    # o rótulo precisa dizer isso, senão o lojista fica tentando.
    "cloud_pendente": "Conectado — aguardando liberação da Revy",
    "cloud_ativo": "No ar",
    "cloud_restrito": "Limitado pela Meta — falar com a Revy",
    "cloud_banido": "Bloqueado pela Meta — falar com a Revy",
```

Acrescente `cloud: bool` ao `CanalView` e, na montagem:

```python
        # Canal Cloud se reconhece pelo waba_id, que é o que o Modo 2 grava e o
        # Modo 1 deixa nulo — mesma regra do ``cloud_canal.py`` no chatbot.
        cloud = bool(bruto.get("waba_id"))
```

e troque os dois cálculos de ação:

```python
                # Conectar/desconectar são ações da Evolution (QR). Num canal
                # Cloud o botão chamaria ``conectar_canal_whatsapp``, que pede
                # QR para um número que é da Cloud API.
                pode_conectar=not cloud and estado != "conectado",
                pode_desconectar=not cloud and estado == "conectado",
```

**Atenção ao bloco do `principal_estoque` no fim da função:** ele reconstrói cada `CanalView`
campo a campo, em duas reconstruções (a do `primeiro` e a do loop) além da construção
original. Todo campo novo tem de ser repassado nas três, senão o canal volta com
`cloud=False` e o defeito ressuscita só quando a loja tem mais de um canal — o caso que
ninguém testa à mão. Ali o campo se repassa como `cloud=primeiro.cloud` / `cloud=c.cloud`;
`cloud` é variável do loop de montagem e não está em escopo.

**Confirmado ao executar, e não era hipótese:** trocar um deles por `cloud=False` — que é o
defeito real — passa pelos cinco testes acima sem nenhum vermelho. Por isso o sexto teste,
com dois canais Cloud, é obrigatório. (Apagar a linha inteira explode com `TypeError`, porque
o campo não tem default; isso protege contra o esquecimento literal, não contra o valor
errado.)

- [x] **Passo 4: rodar e ver passar**

Rode: `.\.venv\Scripts\python.exe -m pytest tests/test_canais_view_modo2.py -q`
Esperado: 5 passed.

- [x] **Passo 5: provar por mutação**

Volte `pode_conectar` para `estado != "conectado"` e confirme que
`test_canal_cloud_nao_oferece_o_botao_do_modo_1` fica vermelho. Depois apague um `cloud=cloud`
de uma das reconstruções do `principal_estoque` e confirme que algum teste pega — **se
nenhum pegar, acrescente o teste com dois canais**, porque é exatamente esse o caminho que
some sem aviso.

- [x] **Passo 6: suíte e commit**

```bash
.\.venv\Scripts\python.exe -m pytest -q
git add portal-gestao/app/loja/whatsapp_canais.py portal-gestao/tests/test_canais_view_modo2.py
git commit -m "fix(loja): a tela oferecia o botao do Modo 1 para canal Cloud"
```

---

### Task 2: o erro do chatbot chega com o elo, não como "indisponível"

**Files:**
- Modify: `portal-gestao/app/clients/chatbot.py`
- Test: `portal-gestao/tests/test_chatbot_client_onboarding.py`

**Interfaces:**
- Produces: exceção `OnboardingFalhou(mensagem, *, elo)` e
  `conectar_whatsapp_cloud(code, waba_id, phone_number_id, business_id) -> dict` no
  `ChatbotClient`.

**Por que esta task existe, e por que ela vem antes da tela:** `_request`
(`app/clients/chatbot.py:86`) termina em `resposta.raise_for_status()` dentro de um
`except (httpx.HTTPError, ValueError)` que levanta `ChatbotIndisponivel`. `HTTPStatusError`
**é** `HTTPError` — então o `502` que o Card 3 devolve com `{"elo": 3, "mensagem": ...}`
chega à tela como *"não foi possível acessar o chatbot agora"*. O lojista veria "erro de
conexão" quando o que houve foi a Meta recusar o registro do número.

É o mesmo defeito do learning
[`2026-08-25-o-422-do-chatbot-chega-como-indisponivel.md`](../../.claude/skills/revy-research/learnings/2026-08-25-o-422-do-chatbot-chega-como-indisponivel.md),
que já custou uma tela culpando a conexão por um erro de digitação. Só `404`, `409` e `422`
têm escape hoje; **o default do cliente é engolir**.

- [x] **Passo 1: escrever o teste que falha**

```python
# portal-gestao/tests/test_chatbot_client_onboarding.py
"""O erro de elo tem de sobreviver a viagem ate a tela.

`_request` engole todo HTTPStatusError em ChatbotIndisponivel. Sem escape, o
502 com o elo vira "nao foi possivel acessar o chatbot agora", e o lojista le
"erro de conexao" quando a Meta e que recusou o registro do numero.
"""
import httpx
import pytest

from app.clients.chatbot import ChatbotClient, ChatbotIndisponivel, OnboardingFalhou


def _cliente(handler):
    return ChatbotClient(
        base_url="http://chatbot.test",
        token="tok",
        transport=httpx.MockTransport(handler),
        retries=0,
    )


def test_erro_de_elo_chega_com_o_numero_do_elo():
    def handler(pedido):
        return httpx.Response(
            502,
            json={"detail": {"elo": 3, "mensagem": "a Meta bloqueou por 72 horas"}},
        )

    with pytest.raises(OnboardingFalhou) as erro:
        _cliente(handler).conectar_whatsapp_cloud(
            code="c", waba_id="w", phone_number_id="p", business_id="b"
        )

    assert erro.value.elo == 3
    assert "72 horas" in str(erro.value)


def test_chatbot_fora_do_ar_continua_indisponivel():
    """Regressao: falha de REDE nao pode virar erro de elo — sao coisas
    diferentes para quem le a tela."""
    def handler(pedido):
        raise httpx.ConnectError("sem rota")

    with pytest.raises(ChatbotIndisponivel):
        _cliente(handler).conectar_whatsapp_cloud(
            code="c", waba_id="w", phone_number_id="p", business_id="b"
        )


def test_sucesso_devolve_o_estado_do_canal():
    def handler(pedido):
        return httpx.Response(
            200, json={"canal_id": "c1", "estado": "cloud_pendente", "onboarding_elo": 5}
        )

    resposta = _cliente(handler).conectar_whatsapp_cloud(
        code="c", waba_id="w", phone_number_id="p", business_id="b"
    )

    assert resposta["estado"] == "cloud_pendente"
```

**Conferido no código, e o padrão existente NÃO serve aqui.** `ChatbotClient.__init__`
(`app/clients/chatbot.py:61`) não aceita `transport=`, e o jeito que
`tests/test_chatbot_client_ofertas.py:7` isola o HTTP é **sobrescrevendo `_request`** numa
subclasse — o que funciona para testar *qual rota foi chamada*, mas é inútil aqui: o objeto
desta task **é o `_request` real**, e um teste que o substitui provaria só que a subclasse do
teste funciona.

Então esta task acrescenta `transport: httpx.BaseTransport | None = None` como parâmetro
keyword-only do construtor, usado em `_request`. Não é invenção: é exatamente o que
`CloudWhatsAppOutbound` (`chatbot-api/app/whatsapp_outbound.py:238`) já faz no outro produto.
Comente no construtor por que ele existe, senão o próximo leitor o remove por parecer morto.

- [x] **Passo 2: rodar e ver falhar**

Esperado: `ImportError` em `OnboardingFalhou`.

- [x] **Passo 3: implementar**

```python
class OnboardingFalhou(Exception):
    """Um elo da cadeia do embedded signup parou, e sabemos qual.

    Separado de ``ChatbotIndisponivel`` de propósito: "a Meta recusou o registro
    do número" e "o chatbot está fora do ar" pedem frases diferentes na tela e
    ações diferentes do lojista.
    """

    def __init__(self, mensagem: str, *, elo: int | None = None) -> None:
        super().__init__(mensagem)
        self.elo = elo
```

e o método, seguindo o padrão de `erro_422` que já existe no `_request` — um escape
explícito, **nunca** um `except` genérico a mais:

```python
    def conectar_whatsapp_cloud(
        self, *, code: str, waba_id: str, phone_number_id: str, business_id: str
    ) -> dict:
        """Repassa ao Chatbot o que o popup da Meta devolveu (spec §4).

        O portal não vê segredo da Meta: quem troca o ``code`` por token é o
        Chatbot, porque a troca exige o App Secret e ele não ganha segunda cópia.
        """
        return self._request(
            "POST",
            "/v1/whatsapp/canais/cloud/onboarding",
            erro_502=True,
            json={
                "code": code,
                "waba_id": waba_id,
                "phone_number_id": phone_number_id,
                "business_id": business_id,
            },
        )
```

No `_request`, o escape:

```python
                if resposta.status_code == 502 and erro_502:
                    detalhe = _detalhe_do_502(resposta)
                    raise OnboardingFalhou(
                        detalhe.get("mensagem") or "não deu para conectar agora",
                        elo=detalhe.get("elo"),
                    )
```

com um `_detalhe_do_502` que devolve `{}` quando o corpo não é o JSON esperado — 502 também
vem de proxy, e proxy não manda `detail`.

**Correção, verificada ao executar:** este card afirmava que `OnboardingFalhou` *precisa*
entrar no `except` que re-levanta `CamposAgenteInvalidos`, senão seria reengolida. **Não
precisa.** `CamposAgenteInvalidos` herda de `ValueError` e por isso é capturada por
`except (httpx.HTTPError, ValueError)`; `OnboardingFalhou` herda de `Exception` e não é
capturada por nenhum dos dois. Pô-la lá é redundante — vale só como proteção se alguém trocar
a base da exceção depois.

- [x] **Passo 4: rodar, ver passar, e provar por mutação**

Apague o bloco do `erro_502` e confirme que `test_erro_de_elo_chega_com_o_numero_do_elo` fica
vermelho — e que `test_chatbot_fora_do_ar_continua_indisponivel` **continua verde**, que é o
que separa as duas situações.

- [x] **Passo 5: commit**

```bash
git commit -m "fix(loja): o erro de elo chegava como 'chatbot indisponivel'"
```

---

### Task 3: a tela `decidindo` — a escolha que não volta atrás

**Files:**
- Create: `portal-gestao/app/templates/loja/whatsapp_decidir.html`
- Modify: `portal-gestao/app/web/loja_whatsapp.py`
- Test: `portal-gestao/tests/test_tela_decidir_whatsapp.py`

**Por que esta tela é requisito e não enfeite (spec §6):** é o único momento do fluxo em que
o lojista toma decisão **irreversível**. Usar o número que ele já anuncia significa perder o
histórico do celular e virar bot-only para sempre. A escolha **é** o aceite — não há "li e
concordo" separado.

Três linhas de trade-off, e a lista do que ele precisa ter em mãos **antes** de abrir o
popup: ser admin do portfólio empresarial na Meta, cartão para a WABA, e o chip. Descobrir
que não é admin dentro do popup é o pior lugar possível.

- [x] **Passo 1: escrever o teste que falha**

**As fixtures de papel já existem:** `conftest.py:903` tem
`login(client, papel="dono"|"gerente"|"vendedor", email=...)`, e
`tests/test_atendimento.py:89` mostra o uso. **Não crie fixture nova** — use `login`.

```python
# portal-gestao/tests/test_tela_decidir_whatsapp.py
"""A tela de decisao do §16.4.

Ela existe para que ninguem perca o historico do WhatsApp sem ter entendido.
"""


def test_gerente_ve_a_tela(client_loja_gerente):
    resposta = client_loja_gerente.get("/app/loja/whatsapp/conectar")

    assert resposta.status_code == 200


def test_gerente_nao_ve_o_botao_de_conectar(client_loja_gerente):
    """Decisao 9: gerente ve o estado, so o dono conecta. Quem clica precisa ser
    admin do portfolio empresarial na Meta, e gerente normalmente nao e."""
    resposta = client_loja_gerente.get("/app/loja/whatsapp/conectar")

    assert "id=\"conectar-whatsapp\"" not in resposta.text


def test_dono_ve_o_botao(client_loja_dono):
    resposta = client_loja_dono.get("/app/loja/whatsapp/conectar")

    assert "id=\"conectar-whatsapp\"" in resposta.text


def test_a_tela_diz_o_que_se_perde(client_loja_dono):
    """As tres linhas do trade-off do §6. Sem elas a decisao nao e informada."""
    texto = client_loja_dono.get("/app/loja/whatsapp/conectar").text.lower()

    assert "histórico" in texto or "historico" in texto
    assert "admin" in texto, "precisa avisar que tem de ser admin do portfolio"


def test_vendedor_nao_entra(client_loja_vendedor):
    resposta = client_loja_vendedor.get(
        "/app/loja/whatsapp/conectar", follow_redirects=False
    )

    assert resposta.status_code in (302, 303, 307)
```

Os nomes `client_loja_dono` / `client_loja_gerente` / `client_loja_vendedor` acima são
ilustrativos: monte cada um com `login(client, papel=...)` do `conftest`, no próprio arquivo
do teste.

- [x] **Passo 2 a 4:** ver falhar, implementar a rota `GET /app/loja/whatsapp/conectar` e o
      template, ver passar. A rota reusa `_habilitado()` e `_autorizado()` para **ver**, e
      calcula `pode_conectar_cloud = papel == DONO` para o botão.

- [x] **Passo 5: commit**

---

### Task 4: o popup do SDK — a única task que depende do App Review

**Files:**
- Modify: `portal-gestao/app/templates/loja/whatsapp_decidir.html`
- Modify: `portal-gestao/app/web/loja_whatsapp.py`
- Modify: `portal-gestao/app/config.py`

**BLOQUEADA até o App Review sair.** O popup precisa do `config_id` da configuração v4 do
Facebook Login for Business, e essa configuração só oferece a variação de Embedded Signup
depois de o app ter Advanced Access. As Tasks 1, 2, 3 e 5 **não** dependem dela.

Quando destravar:

- [x] `PORTAL_META_APP_ID` e `PORTAL_META_CONFIG_ID` no `[env]` do `fly.app.toml` — nenhum
      dos dois é segredo, os dois vão para o navegador. O App ID já está no `app2037` como
      `CHATBOT_META_APP_ID = "1370395535203964"`; **é o mesmo app**, e o valor não se
      duplica à toa: se divergirem, o popup abre com um app e o `code` é trocado com outro,
      e a Meta recusa sem dizer por quê.
- [x] O JS do popup, com `FB.login` e `config_id`, escutando a mensagem de retorno com
      `waba_id`, `phone_number_id` e `business_id`.
- [x] **Saída explícita de "não deu certo".** O caso mais comum — número ainda ativo no
      aplicativo — falha **dentro** do popup e pode não gerar evento nenhum. A tela não pode
      ficar em espera infinita.
- [x] `POST /app/loja/whatsapp/conectar` chamando `conectar_whatsapp_cloud` (Task 2).
- [x] **Verificação no navegador, obrigatória.** `pytest` não roda o popup, e dois bugs já
      passaram por isso (15-16/08). Receita do portal local semeado no learning
      `2026-08-23-copiloto-so-se-verifica-no-navegador.md`.

---

### Task 5: `conectando`, `pendente` e `falhou` na tela

**Primeiro, o que a Task 3 deixou pendente por estar fora dos arquivos dela: a tela de
decisão não está ligada a lugar nenhum.** `GET /app/loja/whatsapp/conectar` existe, é
testada e ninguém a alcança clicando. Ligue-a a partir da tela de canais que já existe
(`/app/loja/whatsapp`), que é onde o lojista já vai — **não** como item de menu novo, que
seria uma segunda porta para a mesma coisa. O link só aparece quando a loja **não** tem
canal Cloud; com canal Cloud, o lugar do estado é a própria tela de canais.

**Files:**
- Modify: `portal-gestao/app/loja/whatsapp_canais.py`, o template
- Test: `portal-gestao/tests/test_canais_view_modo2.py`

A tela lê `onboarding_elo` e `onboarding_erro` do canal (Card 3) e:

- [x] **nomeia o elo e o dono da vez.** "Parou ao registrar o número" é útil; "erro" não é.
- [x] **`falhou` é estado de tela, não de banco.** O canal continua `cloud_pendente`; quem
      diz que falhou é `onboarding_erro` preenchido.
- [x] **em `pendente`, mostra o que falta e de quem é:** template em análise (Meta), meio de
      pagamento (lojista), fila de vendedores (lojista, autoatendida) — e empurra para a
      fila, a única acionável na hora.
- [x] **não oferece "tentar de novo" depois do teto do elo 3.** O chatbot para em 5
      tentativas; a tela a partir daí diz para falar com a Revy, em vez de oferecer um clique
      que vai recusar.
- [x] Não repetir os 13 itens de UI recusados em 07/08.

---

### Task 6: fechamento

- [ ] Suíte do `portal-gestao` verde a partir da pasta do produto.
- [ ] Mexeu em `app.css`? `?v=` no `base.html` — e lembre das telas de auth, que têm o seu.
- [ ] Deploy pela skill `revy-deploy`, e `/healthz` provando o SHA.
- [ ] **Conectar DUAS lojas pelo fluxo** é a primeira prova real do multi-loja, consertado em
      24/08 e nunca exercitado com mais de uma loja (spec §11).

## Como saber que acabou

Um dono de loja abre a Revy Loja, entende o que vai perder, clica um botão, passa pelo popup
da Meta e volta para uma tela que diz em que pé está — sem nunca abrir o painel da Meta, e
sem ninguém da Revy escrever no banco.

---

## Executado em 29/08/2026

Commits: `1859e94`, `2dcf2f2`, `be3ade0`, `9aca30e`, `3a1133d`, `e9d39c4`.
Suítes: `portal-gestao` **1412 passed**, `chatbot-api` **667 passed**.

### O defeito que o card não previu, e era o mais grave

A Task 1 decide se um canal é Cloud lendo `waba_id`, e `_canal_dict` não devolvia `waba_id`.
Os testes usavam dicionários sintéticos e ficavam verdes; em produção a feature seria
**inerte** — todo canal viria como Modo 1 e o botão errado continuaria na tela. Virou a
Task 0 e o learning `2026-08-29-dicionario-sintetico-no-teste-esconde-contrato.md`.

### Três erros do próprio card, corrigidos ao executar

1. **A afirmação sobre `OnboardingFalhou` estava errada.** Ela não precisa do re-raise:
   `CamposAgenteInvalidos` herda de `ValueError` e por isso é capturada; a outra herda de
   `Exception`.
2. **As asserções da tela eram frouxas.** `"anuncia"` casava com um comentário de
   acessibilidade no `base.html`, `"dono"` com a barra do topo. Quatro mutações sobreviviam;
   viraram frases inteiras.
3. **A hipótese do campo esquecido era fato.** Trocar `cloud=` por `False` numa reconstrução
   do `principal_estoque` passava pelos cinco primeiros testes. Resolvido de vez trocando as
   reconstruções manuais por `dataclasses.replace` — a armadilha deixa de existir por
   construção.

### Duas melhorias além do plano

- Dois testes de template eram **grep no arquivo `.html`** e não pegavam mutação nenhuma.
  Viraram render Jinja de verdade, com um `base.html` de mentira. É o que fecha, para esta
  tela, o buraco conhecido de "pytest não roda a tela".
- O botão do popup acende sozinho: basta preencher `PORTAL_META_APP_ID` e
  `PORTAL_META_CONFIG_ID` no `[env]`. **Nenhum código muda no dia em que a Meta liberar.**

### O que NÃO foi verificado

**O JS do popup não rodou em navegador nenhum.** `pytest` renderiza o template como texto e
prova só que os ids saem no HTML e que o `disabled` some. O `FB.login`, o listener de
`message` e os três caminhos de desistência não foram exercitados. É exatamente o buraco que
deixou passar os dois bugs de 15-16/08. Falta clicar:

1. botão aceso e popup abrindo (só isto depende do App Review);
2. fluxo até o fim — `code` e os três ids se encontrando, form postando **uma vez só**;
3. fechar o popup no meio — o `desistir()` pelo callback sem `authResponse`;
4. número ainda ativo no aparelho — o teto de 8 s, o botão virando "Tentar de novo";
5. segunda tentativa depois de desistir;
6. console limpo e `connect.facebook.net` carregando em produção.

### Pendências registradas, fora do escopo deste card

- O cabeçalho da tela de canais e o texto de "Adicionar número" ainda falam de QR mesmo para
  loja que só tem canal Cloud. É linguagem de Modo 1 aparecendo para Modo 2, e mexe no que a
  loja piloto vê.
- "Tentar de novo" leva à tela de decisão, porque não existe rota de retry dedicada.
- `version: "v21.0"` está fixo no template do popup e **não** é o mesmo lugar onde o chatbot
  fixa a versão da Graph. Se divergirem, ninguém percebe até quebrar.
- A auditoria do POST usa `acao="conectar", provedor="cloud"`: `ACOES_CANAL` não tem ação
  própria para o embedded signup.
