# CTWA/ROI: a venda herda a campanha do lead — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Leia a seção "O que foi descartado" antes de propor qualquer coisa nova.** Uma versão anterior deste plano tinha três tasks construídas sobre um diagnóstico falso. Elas estão documentadas lá com o motivo.

**Goal:** vendas confirmadas de leads que vieram de anúncio passam a aparecer na linha da campanha certa na tabela de aquisição da Loja — **inclusive as já confirmadas**, sem backfill nem UPDATE em produção. As campanhas ganham uma rota de atribuição que não depende de a Meta informar o anúncio. E a Loja passa a mostrar **por onde as pessoas chegam de fato** — anúncio, link direto ou busca no WhatsApp — parando de chamar de "anúncio" quem não veio de anúncio.

## O que está medido (produção, 2026-08-08, app2037 v117)

Números lidos direto do banco. **Não re-investigar; partir daqui.**

| Fato | Número | Consequência |
|---|---|---|
| Leads **de anúncio** com `meta_ad_id` | **212 de 220 (96,4%)** | a entrega do anúncio ao lead **funciona** |
| Leads de anúncio sem identificador | 8 (3,6%) | a Meta disse "é anúncio" e omitiu qual — perda real, irrecuperável |
| Leads no balde CTWA que **não** vieram de anúncio | 10 | link direto e busca dentro do WhatsApp, carimbados `origem=meta_ctwa` (Task 8) |
| Eventos com ad_id (semana 03/08) | 263 de 307 | idem, no nível de mensagem |
| Eventos com `meta_campaign_id` | **0, sempre** | a Meta nunca manda a campanha → o Graph é caminho único |
| Eventos com `ctwa_codigo` | **0, sempre** | a rota por código nunca funcionou (ver Task 4) |
| Cache `meta_ad_campanha` | 13 ads, 3 resolvidos | os 10 não resolvidos são de **outra loja** — esperado, não é bug |
| `vendas_projetadas` | 1 linha, `lead_ref` **preenchido**, sem campanha e sem utm | o elo que falta é ler o lead |
| Canais / conversas / identidades | 7 / 492 / 243 | conversa espalhada é o normal aqui (relevante na Task 6) |

### Por onde as pessoas chegam de fato (`leads.ctwa_source_type`, 08/08)

O balde "CTWA" não é só anúncio. Agrupado por `source_type` (`leads` = total, `cegos` = sem
`meta_ad_id`, `meta_campaign_id`, `ctwa_clid` e `ctwa_codigo`):

| `source_type` | leads | cegos | É anúncio? |
|---|---|---|---|
| `FB_Ads` | 205 | 7 | sim |
| `ctwa_ad` | 10 | 1 | sim |
| `ad` | 5 | 0 | sim |
| `click_to_chat_link` | 5 | 4 | **não** — link `wa.me` (site, catálogo, bio) |
| `message_short_link` | 3 | 3 | **não** — link curto |
| `global_search_new_chat` | 2 | 2 | **não** — digitou o número dentro do WhatsApp |

Duas conclusões que mudam tasks:

1. Os 17 "cegos" são **8 + 9**, não 17 da mesma coisa. 8 são anúncio que a Meta entregou sem
   identificador (perda real, só a Task 4 alcança). Os outros 9 **nunca foram anúncio** — "Sem
   campanha" é o resultado certo e não há nada a consertar neles.
2. Esses 10 leads não-anúncio estão com `origem = 'meta_ctwa'` (Task 8), e o dado que os
   descreve corretamente já existe e já viaja até a Loja (Task 9).

Query que reproduz a tabela: `chatbot-api/scripts/diagnose_ctwa_sinais.py`.

**O buraco:** `venda_casa_campanha` (`revy-trafego/app/roi_calc.py:76-87`) compara apenas `campanha_id_*` e `utm_campaign_*` gravados **na própria venda**. Nunca consulta o lead. Enquanto isso, na mesma função, a contagem de **leads** usa `lead_casa_campanha(..., mapa_ad_campaign=mapa)` e casa por ad_id sem problema. É por isso que a linha da campanha mostra leads e não mostra vendas: são dois caminhos de código diferentes, e só um deles enxerga o anúncio.

## Architecture

O conserto fica **na leitura do ROI, não na escrita da projeção**. Tudo o que é preciso já está carregado no mesmo request:

- `revy-trafego/app/api_v1.py:106-128` — o endpoint de resultados já faz `leads = get_chatbot(slug).listar_leads()` e `mapa_ad = mapa_ad_campaign_loja(db, slug)`;
- `app/financeiro_calc.py:48-57` — `VendaRoi` já declara `lead_ref`;
- `portal-gestao/app/revy_trafego_outbox.py:31` — o outbox do Portal já envia `lead_ref`, e ele chega preenchido (verificado).

Resolver na leitura:

- conserta **retroativamente** toda venda já projetada, sem reescrever `vendas_projetadas` e sem reenviar evento;
- não põe chamada HTTP ao Chatbot dentro de `POST /eventos/venda-confirmada`, que é o mesmo caminho que enfileira o Purchase CAPI;
- é uma função nova, em vez de mudanças no Portal + na projeção + script de ops.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Postgres (Chatbot), SQLite (Revy — `sqlite:////data/revy-trafego/revy_trafego.db` em prod), pytest.

## Global Constraints

- **NUNCA casar lead↔auditoria por telefone mascarado.** `ctwa_auditoria.telefone_mascarado` são `***` + 4 dígitos. A colisão é real e já aconteceu em produção (08/08): casou o lead de uma venda com o anúncio de outro cliente. Qualquer atribuição saída daí é receita inventada.
- **Não inventar campanha a partir de `ctwa_source_type`.** Lead sem identificador pertence a "Sem campanha", e está certo assim. `source_type` diz **por onde** a pessoa entrou (Task 9), nunca **qual campanha** pagou.
- **Comparar `source_type` em `casefold()`.** O valor real em produção é `FB_Ads`, com maiúsculas; comparação sensível a caixa classifica 205 leads errado.
- Atribuição explícita **vence** herança: `campanha_id_*` ou `utm_campaign_*` já gravados na venda mandam.
- Uma venda **não pode contar em duas campanhas**. A herança resolve uma campanha por venda, determinística.
- `venda_casa_campanha` compara com **`campanhas.id` do Revy** — nunca com UUID de campanha do Portal.
- **Sem import Python entre produtos.** Chatbot ↔ Revy ↔ Portal só por HTTP / outbox.
- Testes de dentro da pasta do produto: `.\.venv\Scripts\python.exe -m pytest -q`.
- Não logar telefone completo, `ctwa_clid` completo nem tokens.
- Commits pequenos por task. Não commitar segredos.

## File map

| Arquivo | Papel |
|---|---|
| `revy-trafego/app/roi_calc.py` | Task 1: `herdar_campanhas_de_leads` + uso em `calcular_roi_loja` |
| `revy-trafego/app/main.py:1110-1114` | Task 1: detalhe da campanha usa a mesma herança |
| `revy-trafego/tests/test_roi_heranca_lead.py` | Task 1: unit |
| `revy-trafego/app/vendas_projection.py:97-98` | Task 2: descartar `campanha_id_*` desconhecido |
| `revy-trafego/tests/test_roi_venda_com_ad_id.py` | Task 3: teste de ponta pelo endpoint |
| Painel de campanhas do Revy (UI) | Task 4: `codigo_ctwa` correto + código na mensagem do anúncio |
| `revy-trafego/app/meta_ad_resolver_job.py:140-142` | Task 5: destravar ad que estourou `max_tentativas` |
| `chatbot-api/app/servico.py:1921-1925` e `:1013-1015` | Task 6: entrega do tracking pendente |
| `docs/plans/README.md`, `docs/handoff-contexto.md` | Task 7 |
| `chatbot-api/app/servico.py:104` e `:133-143` | Task 8: `origem=meta_ctwa` só para quem veio de anúncio |
| `portal-gestao/app/loja/sales_overview.py` | Task 9: resumo de origem dos leads |
| `portal-gestao/app/templates/loja/vendas_visao.html:209-253` | Task 9: bloco novo no painel "De onde veio o resultado" |

**Fora de escopo:** sync bidirecional de cadastro de campanhas Portal↔Revy; UI de reatribuição manual; reescrever `vendas_projetadas`; recuperar atribuição de leads que nunca tiveram sinal forte (não existe dado).

---

### Task 1: Revy — a venda herda a campanha do lead no cálculo do ROI

**É o conserto principal.** Destrava os 212 leads que já têm ad_id.

**Files:**
- Modify: `revy-trafego/app/roi_calc.py`
- Modify: `revy-trafego/app/main.py:1110-1114`
- Test: `revy-trafego/tests/test_roi_heranca_lead.py` (criar)

**Interfaces:**

```python
def herdar_campanhas_de_leads(
    *,
    campanhas: list[Campanha],
    vendas: list[VendaRoi],
    leads: list[dict],
    modo: str = "last",
    mapa_ad_campaign: dict[str, str] | None = None,
) -> dict[str, str]:
    """venda.id -> campanha.id herdada do lead que originou a venda.

    Só entra venda SEM atribuição própria (sem campanha_id e sem utm no modo).
    Determinístico: primeira campanha da lista ordenada que casa com o lead —
    mesma regra de resolver_campanhas_do_lead, para a venda nunca contar duas vezes.
    """
```

- `calcular_roi_loja` chama isso **uma vez**, antes do laço de campanhas.
- `venda_casa_campanha` **não muda de assinatura** (é usada direto em `main.py:1113`).

**Quatro detalhes que mudam o resultado:**

1. O índice de leads sai da lista **completa** de `leads`, não de `leads_periodo` (`roi_calc.py:102`). A venda é de agosto e o lead pode ser de julho — filtrar por período aqui zera a herança.
2. Chave do índice: `str(lead["id"])` ↔ `str(venda.lead_ref)`. `lead_ref` é `String(120)` (`app/models.py:523`).
3. Guarda de precedência: herda só se `not venda.campanha_id_<modo>` **e** `not normalizar_utm(venda.utm_campaign_<modo>)`.
4. Chatbot offline → `leads=[]` → herança vazia → comportamento idêntico ao de hoje. Degradação correta.

- [ ] **Step 1: Write the failing tests**

```python
# revy-trafego/tests/test_roi_heranca_lead.py
from datetime import date
from decimal import Decimal

from app.roi_calc import calcular_roi_loja, herdar_campanhas_de_leads


def test_venda_sem_campanha_herda_do_lead_por_ad_id():
    """O caso dos 212 leads: lead com meta_ad_id, cache Graph ad->campanha, venda crua."""
    campanha = _campanha(id="c-caua", nome="CAUA", meta_campaign_id="120249613359800224")
    lead = {"id": "lead-1", "meta_ad_id": "120249613359810224",
            "criada_em": "2026-07-30T10:00:00+00:00"}
    venda = _venda(id="v-1", lead_ref="lead-1", preco_venda=Decimal("32.00"),
                   campanha_id_last=None, utm_campaign_last=None)

    linhas = calcular_roi_loja(
        campanhas=[campanha], gastos=[_gasto("c-caua", "50.00")],
        leads=[lead], vendas_confirmadas=[venda],
        d_inicio=date(2026, 8, 1), d_fim=date(2026, 8, 31),
        mapa_ad_campaign={"120249613359810224": "120249613359800224"},
    )
    linha = next(l for l in linhas if l.campanha_id == "c-caua")
    assert linha.vendas == 1
    assert linha.faturamento == Decimal("32.00")
    assert linha.roas is not None


def test_lead_fora_do_periodo_ainda_atribui_a_venda():
    """Lead de julho, venda de agosto: o indice nao pode ser filtrado por periodo."""
    ...  # linha.vendas == 1 e linha.leads == 0


def test_atribuicao_explicita_vence_heranca():
    """utm ja gravado no snapshot manda, mesmo que o lead case outra campanha."""
    ...  # venda.utm_campaign_last="MT03AGOSTO" -> conta na campanha do utm


def test_venda_nao_conta_em_duas_campanhas():
    """Duas campanhas casam o mesmo lead -> faturamento nao dobra."""
    ...  # soma de linha.vendas sobre todas as linhas com campanha == 1


def test_lead_sem_ad_id_cai_em_sem_campanha():
    """Os 8 leads de anuncio sem identificador: nao inventar campanha."""
    lead = {"id": "lead-2", "ctwa_source_type": "ctwa_ad", "meta_ad_id": None}
    ...  # venda entra na linha "Sem campanha"


def test_sem_lead_ref_cai_em_sem_campanha():
    ...


def test_chatbot_offline_nao_quebra():
    ...  # leads=[] -> nenhuma heranca, nenhuma excecao
```

- [ ] **Step 2: Run — expect FAIL**

```powershell
cd revy-trafego
.\.venv\Scripts\python.exe -m pytest tests/test_roi_heranca_lead.py -q --tb=short
```

- [ ] **Step 3: Implementar**

```python
def herdar_campanhas_de_leads(*, campanhas, vendas, leads, modo="last", mapa_ad_campaign=None):
    if not campanhas or not vendas or not leads:
        return {}
    por_ref = {str(l["id"]): l for l in leads if l.get("id")}
    if not por_ref:
        return {}
    ordenadas = sorted(campanhas, key=lambda c: c.nome.casefold())

    heranca: dict[str, str] = {}
    for venda in vendas:
        if modo == "first":
            proprio = venda.campanha_id_first or normalizar_utm(venda.utm_campaign_first)
        else:
            proprio = venda.campanha_id_last or normalizar_utm(venda.utm_campaign_last)
        if proprio:
            continue
        lead = por_ref.get(str(venda.lead_ref or ""))
        if not lead:
            continue
        for c in ordenadas:
            if lead_casa_campanha(lead, c, modo=modo, mapa_ad_campaign=mapa_ad_campaign):
                heranca[venda.id] = c.id
                break
    return heranca
```

Em `calcular_roi_loja`, logo depois de `mapa = mapa_ad_campaign or None` (`roi_calc.py:103`):

```python
heranca = herdar_campanhas_de_leads(
    campanhas=campanhas,
    vendas=vendas_confirmadas,
    leads=leads,          # lista COMPLETA, não leads_periodo
    modo=modo,
    mapa_ad_campaign=mapa,
)
```

e no laço (`roi_calc.py:120-123`):

```python
for v in vendas_confirmadas:
    if venda_casa_campanha(v, campanha, modo=modo) or heranca.get(v.id) == campanha.id:
        vendas_c.append(v)
```

`vendas_sem` (`roi_calc.py:181`) já usa `vendas_matched_ids`, então a linha "Sem campanha" se ajusta sozinha.

- [ ] **Step 4: Alinhar a página de detalhe da campanha**

`revy-trafego/app/main.py:1110-1114` monta `vendas_atribuidas` chamando `venda_casa_campanha` direto. Sem isto, a linha do ROI diz "1 venda" e a lista da página fica vazia. Os `leads` e o `mapa_ad` já estão carregados nas linhas 1087-1095 — chamar `herdar_campanhas_de_leads` ali e aplicar o mesmo `or heranca.get(...)`.

- [ ] **Step 5: Run**

```powershell
cd revy-trafego
.\.venv\Scripts\python.exe -m pytest tests/test_roi_heranca_lead.py tests/test_roi_calc.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest -q
```

- [ ] **Step 6: Commit**

```powershell
git add revy-trafego/app/roi_calc.py revy-trafego/app/main.py revy-trafego/tests/test_roi_heranca_lead.py
git commit -m "fix(revy): venda sem campanha herda atribuicao do lead no ROI"
```

---

### Task 2: Revy — descartar `campanha_id_*` que não existe no Revy

**Files:**
- Modify: `revy-trafego/app/vendas_projection.py:97-98`
- Test: `revy-trafego/tests/test_vendas_projection.py` (estender)

**Por quê:** o outbox do Portal envia `campanha_id_first/last` (`portal-gestao/app/revy_trafego_outbox.py:44-45`) com **UUID do Portal**. `Campanha.id` no Revy é gerado local (`revy-trafego/app/models.py:652`, `default=novo_id`) e nunca importado — então esse id é lixo aqui. Hoje chega nulo porque o Portal não tem campanhas cadastradas. No dia em que tiver, o UUID grava na venda e o `not venda.campanha_id_last` (`roi_calc.py:85`) desliga o casamento por UTM **e** a herança da Task 1. A venda some do ROI sem ninguém mexer em código.

Validar na fronteira é mais barato que mudar o contrato do Portal: aceita o id só se existir em `campanhas` da mesma loja; senão descarta. As UTMs continuam passando.

- [ ] **Step 1: Test**

```python
def test_projecao_descarta_campanha_id_desconhecido(db):
    snap = _snapshot(loja_slug="moto-center", campanha_id_last="uuid-do-portal",
                     utm_campaign_last="MT03AGOSTO")
    r = projetar_venda(db, snap)
    assert r.venda.campanha_id_last is None
    assert r.venda.utm_campaign_last == "MT03AGOSTO"


def test_projecao_mantem_campanha_id_conhecido(db):
    ...  # id existente em campanhas da loja passa intacto
```

- [ ] **Step 2: Implementar** — em `projetar_venda`, antes de gravar `campanha_id_first/last`, checar existência com uma query só (`select id from campanhas where loja_slug=? and id in (...)`).

- [ ] **Step 3: Run + Commit**

```powershell
cd revy-trafego
.\.venv\Scripts\python.exe -m pytest tests/test_vendas_projection.py -q
git commit -m "fix(revy): ignora campanha_id do Portal na projecao da venda"
```

---

### Task 3: Teste de ponta pelo endpoint de resultados

**Files:**
- Test: `revy-trafego/tests/test_roi_venda_com_ad_id.py` (criar)

**Goal:** provar o caminho inteiro in-process, não só a função pura — porque é o endpoint que a Loja consome.

- [ ] **Step 1: Write test**

```python
def test_resultados_conta_venda_atribuida_por_ad_id(client, db, monkeypatch):
    # 1. Campanha com meta_campaign_id
    # 2. MetaAdCampanha: ad -> campanha
    # 3. VendaProjetada confirmada, lead_ref="lead-1", sem campanha/utm
    # 4. monkeypatch de ChatbotClient.listar_leads -> [{"id": "lead-1", "meta_ad_id": ...}]
    # 5. GET /api/v1/lojas/moto-center/resultados?... com service token
    # 6. campanhas[0]["vendas"] == 1 e faturamento correto
```

- [ ] **Step 2: Run — PASS**
- [ ] **Step 3: Commit**

```powershell
git commit -m "test(revy): resultados atribui venda CTWA por ad_id do lead"
```

---

### Task 4: Rota que não depende da Meta — código na mensagem do anúncio

**Não é task de código.** É configuração, e é a **única** rota que alcança os 8 leads de anúncio que a Meta entregou sem identificador (3,6%) — como o lead da venda de 06/08, que por isso é inatribuível. Nenhuma outra task deste plano chega neles.

**Estado atual (verificado):** `ctwa_codigo` nunca foi extraído (0 em todas as semanas), e das 3 campanhas cadastradas, 2 têm a **frase-convite inteira** colada no campo `codigo_ctwa`, truncada nos 40 caracteres do campo:

| Campanha | `codigo_ctwa` hoje | |
|---|---|---|
| MT03 - CAUA VENDAS | `MT03-AGO26` | ✅ é um código |
| MT03 - PEDRO VENDAS | `Fiquei interessado na MT-03, Mais inform` | ❌ frase |
| xre pedro | `Oi! Como podemos ajudar? XRE 300 COD` | ❌ frase |

**Por que frase nunca casa:** o extrator (`chatbot-api/app/servico.py:38-44`) reconhece três formatos e só esses — `Cód: X`, `codigo: X`/`ref: X` e `utm_campaign=X`, onde X é `[A-Za-z0-9][A-Za-z0-9_-]{1,39}`. Texto livre não gera código nenhum.

**O contrato que funciona, sem mudar código:**

1. Na mensagem pré-preenchida do anúncio, terminar com o código: `Quero saber da MT-03 — Cód: CAUA08`.
2. No cadastro da campanha no Revy, `codigo_ctwa` = exatamente `CAUA08`.
3. `lead_casa_campanha` casa por `normalizar_utm(codigo_ctwa)` (`revy-trafego/app/campanhas.py:268-271`), e `aplicar_touch_ctwa` ainda preenche `utm_campaign` do lead com o código quando está vazio (`servico.py:124-130`) — o que dá uma segunda rota de casamento de graça.

- [ ] **Step 1:** definir um código curto por campanha (só letras, números, `-` e `_`; até 40 chars)
- [ ] **Step 2:** editar a mensagem pré-preenchida de cada anúncio ativo incluindo `Cód: <código>`
- [ ] **Step 3:** corrigir `codigo_ctwa` das 3 campanhas no formulário do Revy
- [ ] **Step 4: Verificar com dado real** — depois do primeiro clique novo, conferir que a auditoria CTWA (`/app/trafego/ctwa-auditoria`) mostra a coluna "Código" preenchida. Enquanto ficar vazia, o formato está errado e nada mais adianta.

---

### Task 5: Robustez — ad travado no teto de tentativas nunca mais é tentado

**Files:**
- Modify: `revy-trafego/app/meta_ad_resolver_job.py`
- Test: `revy-trafego/tests/` (estender o teste do resolver)

**Por quê:** `_deve_pular` (`meta_ad_resolver_job.py:140-142`) descarta qualquer linha com `tentativas >= max_tentativas`, **sem prazo e sem caminho de reset**. Em produção 10 ads pararam nesse estado no mesmo lote (07/08 02:20:06). Quando a configuração da Meta é corrigida, eles continuam mortos — e nada na tela mostra "N anúncios sem campanha", que foi o que deixou a falha invisível.

Neste caso os 10 são de outra loja e o resultado até estava correto — mas o mecanismo é cego para a diferença entre "não tenho acesso" e "não devo ter acesso".

**Ponto de enganche (verificado):** `IntegrationsControl.upsert_meta_ads`
(`revy-trafego/app/control/integrations.py:209`) já chama `invalidar(store.id)` em `:261-263`.
É onde o reset entra.

⚠️ **Chave diferente nos dois lados.** `invalidar` usa `store.id`; `MetaAdCampanha` é indexada
por **`loja_slug`** (`revy-trafego/app/models.py:705`, `:709`). Reusar `store.id` no `WHERE`
não zera nada e o teste passa se olhar só "não quebrou". Traduzir id → slug antes, e o teste
tem que **contar linhas com `tentativas` zerado**, não só verificar ausência de exceção.

- [ ] **Step 1:** teste — mudar a config de Ads da loja zera `tentativas`/`erro` dos ads não resolvidos **daquela loja** (e não mexe nos de outra loja)
- [ ] **Step 2:** implementar o reset em `upsert_meta_ads`, junto do `invalidar`, resolvendo `store.id` → `loja_slug`
- [ ] **Step 3:** teste + implementação de um contador de ads não resolvidos exposto na tela de tráfego
- [ ] **Step 4: Commit**

---

### Task 6: Chatbot — entrega do tracking pendente (robustez, sem urgência)

**Files:**
- Modify: `chatbot-api/app/servico.py:1905-1927` e `:1013-1015`
- Test: `chatbot-api/tests/test_ctwa_tracking_pendente.py` (criar)

**Dois defeitos reais, nenhum deles comprovado como causa de algo observado.** Entram por correção, não por urgência — mas a loja tem 7 canais, 492 conversas para 243 identidades, e um mesmo cliente apareceu em 3 canais em 2 dias. Isso vai acontecer.

1. `_vincular_tracking_pendente_ao_lead` procura a conversa por `loja_id + telefone` com `.first()` (`servico.py:1921-1925`), sem filtrar canal e sem ordenar — mas `Conversa` é única por `(canal_id, telefone)` com `canal_id` nullable (`models_db.py:80-90`). Com duas linhas para o mesmo telefone, o `.first()` pode pegar a que não tem `tracking_pendente_json`.
2. Em `servico.py:1013-1015`, quando há pendente e o lead **já existe**, o código só lê o id e nunca consome o pendente.

**Conserto:** varrer **todas** as conversas de `loja_id + telefone` com `tracking_pendente_json`, em `ORDER BY criada_em ASC` — ascendente é obrigatório, porque `aplicar_touch_ctwa` só grava os campos `_first` quando estão nulos (`servico.py:109-127`). E chamar o vínculo também no ramo do lead existente.

- [ ] **Step 1:** testes (duas conversas no mesmo telefone; lead que já existia; first vem da conversa mais antiga; sem pendente é no-op)
- [ ] **Step 2:** run — expect FAIL. Se algum passar por acaso (a ordem do banco às vezes devolve a linha certa por sorte), **inverter a ordem de criação das conversas no teste até falhar**. Teste que não falha não prova nada.
- [ ] **Step 3:** implementar a varredura
- [ ] **Step 4:** consumir o pendente no ramo do lead existente
- [ ] **Step 5:** rodar a suíte inteira do chatbot — `_vincular_tracking_pendente_ao_lead` também é chamada por `registrar_lead` (`servico.py:1939`), então todo teste de lead passa por ali
- [ ] **Step 6: Commit**

---

### Task 8: Chatbot — `origem = meta_ctwa` só para quem veio de anúncio

**Files:**
- Modify: `chatbot-api/app/servico.py` (`aplicar_touch_ctwa`, `:104` e `:133-143`)
- Test: `chatbot-api/tests/test_ctwa_origem_por_source_type.py` (criar)

**Por quê:** `tem_sinal` (`:104`) é `clid or ad_id or camp_id or adset or source or codigo`, e o bloco
`if tem_sinal:` (`:133`) carimba `origem`, `origem_first`, `origem_last` = `"meta_ctwa"` e
`ctwa_atribuido_em`. **`source_type` sozinho já basta** — então `global_search_new_chat`, que é
alguém digitando o número dentro do WhatsApp, entra como lead de anúncio da Meta. Em produção
são 10 leads assim.

Isso **não** infla campanha no ROI (lead sem identificador não casa em `lead_casa_campanha`),
mas mente na origem do CRM e no denominador de qualquer contagem de "leads de anúncio" —
inclusive no painel da Task 9, se ele fosse agrupar por `origem`.

**O conserto separa dois conceitos que hoje são um só:**

- **gravar o sinal** — continua igual, **sempre**. `ctwa_source_type`, `clid`, `ad_id`, `codigo`
  seguem salvos como hoje. Nada se perde, e a Task 9 depende exatamente disso.
- **carimbar a origem** — só quando houver identificador de anúncio **ou** `source_type` de
  família de anúncio.

```python
# casefold obrigatório: o valor real em produção é "FB_Ads"
FAMILIA_ANUNCIO = {"fb_ads", "ctwa_ad", "ad"}

def _e_anuncio(source: str | None) -> bool:
    return (source or "").strip().casefold() in FAMILIA_ANUNCIO
```

`tem_anuncio = bool(clid or ad_id or camp_id or adset or codigo or _e_anuncio(source))`, e o
`if tem_sinal:` de `:133` passa a ser `if tem_anuncio:`.

**Três detalhes que decidem se a mudança está certa:**

1. **`canal` sai do guard.** As linhas `canal_first/canal_last/canal = "whatsapp"` (`:138-141`)
   valem para qualquer sinal — quem chegou por link direto **também** chegou pelo WhatsApp.
   Só `origem*` e `ctwa_atribuido_em` ficam atrás de `tem_anuncio`.
2. **`source_type` desconhecido não carimba.** Um valor novo que não está na lista, sem nenhum
   identificador junto, é quase certamente não-anúncio — e anúncio de verdade quase sempre traz
   `clid` ou `ad_id`, que já passam pelo guard. Falso negativo aqui é barato; falso positivo é o
   defeito que estamos consertando. Logar o valor desconhecido uma vez (é enum, não é PII) para
   a lista poder crescer com evidência.
3. **Não rebaixar origem já carimbada.** Lead que veio de anúncio e depois manda mensagem por
   link direto continua `meta_ctwa` — o guard só decide se **escreve**, nunca apaga.

- [ ] **Step 1: Testes**

```python
def test_fb_ads_sozinho_carimba_origem():
    ...  # ctwa_source_type="FB_Ads" (maiúsculas) -> origem == "meta_ctwa"

def test_link_direto_nao_carimba_origem_mas_grava_source_type():
    ...  # "click_to_chat_link" -> origem intacta, lead.ctwa_source_type preenchido

def test_busca_no_whatsapp_nao_carimba_origem():
    ...  # "global_search_new_chat" -> origem intacta

def test_identificador_vence_source_type_nao_anuncio():
    ...  # "global_search_new_chat" + ctwa_clid -> origem == "meta_ctwa"

def test_source_type_desconhecido_nao_carimba():
    ...  # "algo_novo_da_meta" sozinho -> origem intacta

def test_canal_whatsapp_vale_para_qualquer_sinal():
    ...  # "click_to_chat_link" -> lead.canal == "whatsapp"

def test_origem_de_anuncio_nao_e_rebaixada():
    ...  # touch com FB_Ads, depois touch com click_to_chat_link -> segue "meta_ctwa"
```

- [ ] **Step 2: Run — expect FAIL**

```powershell
cd chatbot-api
.\.venv\Scripts\python.exe -m pytest tests/test_ctwa_origem_por_source_type.py -q --tb=short
```

- [ ] **Step 3: Implementar** `_e_anuncio` + `tem_anuncio`, mover `canal*` para fora do guard
- [ ] **Step 4: Rodar a suíte inteira do chatbot** — `aplicar_touch_ctwa` é chamada em três
      pontos (`:961`, `registrar_lead`, vínculo do pendente); testes de lead passam por ali
- [ ] **Step 5: Commit**

```powershell
git commit -m "fix(chatbot): origem meta_ctwa so para source_type de anuncio"
```

**Sem backfill.** Os 10 leads já carimbados ficam como estão — ver "O que foi descartado".

---

### Task 9: Loja — "Por onde as pessoas chegam" no painel de aquisição

**Files:**
- Modify: `portal-gestao/app/loja/sales_overview.py`
- Modify: `portal-gestao/app/templates/loja/vendas_visao.html:209-253`
- Test: `portal-gestao/tests/test_loja_sales_overview.py` (estender)

**Onde entra, e por quê ali:** a Loja já tem a seção **"De onde veio o resultado"**
(`vendas_visao.html:213`, `mono-label` "Aquisição"). O bloco novo é o segundo pedaço da mesma
pergunta: a tabela de campanhas responde *quanto cada campanha custou e rendeu*; este responde
*por onde as pessoas entraram*. Mesma seção, dois blocos.

**Nada disso conflita com a triagem de UX de 07/08.** O `C9` removido era "Aquisição Google
(7 dias)" na visão de **rede do Control** — outro shell, outro escopo. E o `L2` **recusado**
(manter o card "Google Ads — Indisponível" na visão de Vendas da Loja) mostra que canal de
aquisição visível na Loja é decisão de produto já tomada, a favor.

**Custo de integração: zero.** `ctwa_source_type` já é serializado no lead
(`chatbot-api/app/servico.py:2141`) e o `sales_overview` já chama `chatbot.listar_leads()`
(`:490`, `:612`, `:822`). Sem campo novo, sem endpoint novo, sem mudança de contrato.

**Decisão de guard — a que mais importa.** O painel de campanhas está atrás de
`{% if overview.aquisicao_campanhas %}` (`:210`), e `aquisicao_campanhas` **só existe quando a
API do Revy responde** (`_linhas_midia_da_api`, `sales_overview.py:189-214`; o fallback local
deixa vazio de propósito, comentário em `:122-124`). O bloco novo **não pode herdar esse
guard**: a fonte dele é o lead do Chatbot, não o gasto da Meta. Se a Meta ou o Revy caírem,
"por onde as pessoas chegam" continua sendo respondível — e é justamente quando o lojista mais
quer saber. Guard próprio, e a `<section>` passa a abrir se **qualquer um** dos dois blocos
tiver conteúdo.

**Agrupar por `ctwa_source_type`, não por `origem`.** Dois motivos: `origem` está errada em 10
leads e não será corrigida retroativamente (Task 8); e `source_type` é o dado cru da Meta, que
está certo.

**Cobrir todos os leads do período, não só os de anúncio.** Um painel chamado "por onde as
pessoas chegam" que só conta os 230 com sinal da Meta mente por omissão — a loja também tem
lead de catálogo e de WhatsApp direto. Classificação, na ordem:

| Ordem | Condição (`casefold`) | Rótulo na Loja |
|---|---|---|
| 1 | `source_type` ∈ `fb_ads`, `ctwa_ad`, `ad` | **Anúncio** |
| 2 | `source_type` ∈ `click_to_chat_link`, `message_short_link` | **Link direto** (site, catálogo, bio) |
| 3 | `source_type` = `global_search_new_chat` | **Procurou no WhatsApp** |
| 4 | `source_type` presente, fora da lista | **Outro (WhatsApp)** |
| 5 | sem `source_type`, com `origem` | rótulo da origem |
| 6 | nada | **Não identificado** |

**Dentro de "Anúncio", um número a mais:** quantos estão **sem identificação de campanha** (sem
`meta_ad_id`, `meta_campaign_id`, `ctwa_clid` e `ctwa_codigo`) — hoje 8. É o que explica, na
própria tela, por que a soma das campanhas não bate com "Anúncio". Sem esse número o lojista vê
a diferença e não tem como descobrir a causa.

**Período:** `listar_leads()` volta sem filtro; recortar por `criada_em` na mesma janela do
resto do painel. Lead sem `criada_em` fica **fora** — não pode virar "Não identificado", senão
o balde incha com lead antigo e o total mente.

**Rótulos, não enum cru.** `FB_Ads` e `global_search_new_chat` não chegam na tela. Mapa no
módulo da Loja — não dá para reusar `revy-trafego/app/rotulos.py` (produto diferente, sem
import entre produtos). É duplicação consciente com a lista da Task 8: anotar nos dois lados
que andam juntas, como já acontece com `aplicar_snapshot_venda`.

**Interface:**

```python
@dataclass
class OrigemLinha:
    chave: str            # "anuncio" | "link_direto" | "busca_whatsapp" | "outro" | ...
    rotulo: str           # "Anúncio"
    leads: int
    share: Decimal        # % do total do período
    nota: str | None      # "8 sem identificação de campanha"
```

e `aquisicao_origens: list[dict[str, Any]] = field(default_factory=list)` no overview,
serializado como os outros em `to_dict` (`sales_overview.py:154-157`).

- [ ] **Step 1: Testes**

```python
def test_classifica_fb_ads_como_anuncio():
    ...  # "FB_Ads" com maiúsculas -> chave "anuncio"

def test_link_direto_e_busca_nao_entram_em_anuncio():
    ...  # click_to_chat_link + message_short_link -> "link_direto"; global_search -> "busca_whatsapp"

def test_lead_fora_do_periodo_nao_conta():
    ...

def test_lead_sem_criada_em_fica_de_fora():
    ...  # nao vira "Não identificado"

def test_sem_source_type_usa_origem():
    ...

def test_nota_conta_anuncios_sem_identificacao():
    ...  # 3 leads de anúncio, 1 sem nenhum identificador -> nota menciona 1

def test_share_soma_100_no_periodo():
    ...

def test_chatbot_offline_devolve_lista_vazia():
    ...  # listar_leads levanta -> aquisicao_origens == [] e nenhuma excecao sobe
```

- [ ] **Step 2: Run — expect FAIL**

```powershell
cd portal-gestao
.\.venv\Scripts\python.exe -m pytest tests/test_loja_sales_overview.py -q --tb=short
```

- [ ] **Step 3: Implementar** `classificar_origem_lead` + `resumir_origens` em
      `sales_overview.py`, com o `try/except` de chatbot offline no mesmo padrão de `:611-614`
- [ ] **Step 4: Template** — bloco novo dentro da `<section>` de `:211`, com guard próprio; a
      condição de `:210` passa a `{% if overview.aquisicao_campanhas or overview.aquisicao_origens %}`
- [ ] **Step 5: Run** — suíte do Portal inteira (`sales_overview` alimenta Vendas e Control)
- [ ] **Step 6: Commit**

```powershell
git commit -m "feat(loja): painel de por onde os leads chegam na aquisicao"
```

**Permissão:** a seção inteira está dentro do gate `pode_ver_aquisicao`
(`portal-gestao/app/web/loja_vendas.py:175`). **Manter.** Quem vê resultado de mídia é decisão
de produto já tomada; não abrir para outros papéis sem o dono pedir.

---

### Task 7: Docs, deploy e verificação

- [ ] **Step 1: Suites**

```powershell
cd revy-trafego
.\.venv\Scripts\python.exe -m pytest -q

cd ..\chatbot-api
.\.venv\Scripts\python.exe -m pytest -q --ignore=test-tmp-run4 --ignore=test-tmp-run5

cd ..\portal-gestao
.\.venv\Scripts\python.exe -m pytest -q
```

- [ ] **Step 2: Commitar antes de deployar** — `fly deploy` empacota a árvore local, não o commit; já houve drift prod↔repo por causa disso.

- [ ] **Step 3: Deploy** (quando o dono pedir)

```powershell
fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false
```

Nenhuma task adiciona migration.

- [ ] **Step 4: Verificação — leia isto antes de concluir que falhou**

⚠️ **A Task 1 não muda nada visível no dia do deploy.** Hoje existe **uma** venda projetada, e o lead dela não tem `meta_ad_id` — ela continua, corretamente, em "Sem campanha". O conserto só aparece na tela quando entrar uma venda de um dos 212 leads que têm ad_id.

A **Task 9 é o oposto**: muda a tela no mesmo dia, com dado que já existe. Se ela subir junto, é ela que dá o sinal visual de que o deploy funcionou — não confundir uma coisa com a outra.

Então a verificação é, nesta ordem:

1. Testes das Tasks 1, 3, 8 e 9 verdes — é a prova real do comportamento.
2. Tabela de aquisição da Loja continua carregando, com os mesmos números de leads de antes (nenhuma regressão).
3. **Task 9, no dia:** o bloco "Por onde as pessoas chegam" aparece e os números batem com a tabela de evidência deste plano (~220 Anúncio, 8 link direto, 2 procurou no WhatsApp, no acumulado). Se "Anúncio" vier com 230, a classificação por `casefold` está errada.
4. **Task 8, no dia:** derrubar a fonte de mídia (ou olhar uma loja sem campanha cadastrada) e confirmar que o bloco da Task 9 **continua renderizando** — é o guard próprio funcionando.
5. Na **próxima venda** de lead com ad_id: a linha da campanha mostra a venda, e o detalhe da campanha lista ela.
6. Depois da Task 4: na primeira conversa nova vinda de anúncio, a coluna "Código" da auditoria CTWA aparece preenchida.
7. Depois da Task 8: o **próximo** lead que chegar por `click_to_chat_link` não sai como `meta_ctwa` no CRM. Os 10 antigos continuam errados de propósito (sem backfill).

- [ ] **Step 5:** atualizar `docs/plans/README.md` e `docs/handoff-contexto.md`

```markdown
- **CTWA/ROI herança venda→lead:** plano
  [`../superpowers/plans/2026-08-08-ctwa-lead-ad-id-e-roi-venda.md`](../superpowers/plans/2026-08-08-ctwa-lead-ad-id-e-roi-venda.md)
  — a venda herda a campanha do lead no cálculo do ROI (retroativo); código no anúncio
  como rota independente da Meta; painel "por onde as pessoas chegam" na Loja e fim do
  carimbo `meta_ctwa` em quem chegou por link direto.
```

- [ ] **Step 6: Commit**

---

## O que foi descartado — e não deve voltar

Três tasks de uma versão anterior deste plano foram removidas depois da verificação em produção de 08/08. Elas pareciam razoáveis e estavam erradas.

**"Lead herda ad_id da `ctwa_auditoria`" (rede de segurança) — REMOVIDA.** A auditoria guarda o telefone só mascarado (`***` + 4 dígitos). Essa heurística foi testada contra o dado real e **casou o lead de uma venda com o anúncio de outro cliente**: `55+DDD` diferente, 8 últimos diferentes, 6 últimos diferentes, só os 4 finais iguais. Implementar isso significa pôr receita na campanha errada, sem nenhum erro visível. Não é risco teórico — é o caso observado.

**"Backfill dos leads cegos" — REMOVIDA.** Dependia do casamento acima, aplicado em massa. E o alvo é menor do que parecia: dos 17 sem identificador, **9 nunca foram anúncio** e 8 estão assim porque a Meta mandou só `ctwa_source_type`. Não há dado perdido para recuperar em nenhum dos dois grupos.

**"O ad_id se perdeu na entrega ao lead" (premissa original do plano) — FALSA.** 212 de 220 leads de anúncio têm ad_id (96,4%). A entrega funciona. O diagnóstico que dizia o contrário vinha da mesma colisão de 4 dígitos.

**"Backfill da `origem` dos 10 leads não-anúncio" — DESNECESSÁRIO, não fazer.** O carimbo da Task 8 **sobrescreveu** a origem anterior; não dá para saber qual era. E não precisa: a Task 9 agrupa por `ctwa_source_type`, que está correto nos 10, e não por `origem`. O painel nasce certo sem tocar em uma linha do banco.

**Sobre a venda `3eae3efb-…` (moto vendida em 06/08):** o lead dela nunca teve `meta_ad_id` em registro nenhum — só `origem=meta_ctwa` e `ctwa_source_type='ctwa_ad'`. É **inatribuível a partir dos dados**, e "Sem campanha" é o resultado correto. A Task 4 é o que teria evitado isso, e é o que evita o próximo.

## Self-review

| Requisito | Task |
|---|---|
| Venda já confirmada aparece no ROI sem reprojetar nem UPDATE | Task 1 |
| Venda não conta em duas campanhas | Task 1 (herança determinística + teste) |
| Atribuição explícita vence herança | Task 1 (guarda de precedência) |
| Lead sem sinal forte não ganha campanha inventada | Task 1 (teste dedicado) + Global |
| Detalhe da campanha bate com a linha do ROI | Task 1 step 4 |
| UUID de campanha do Portal não envenena a venda | Task 2 |
| Caminho de atribuição que não depende da Meta | Task 4 |
| Ad travado volta a ser tentado quando a config muda | Task 5 |
| Tracking pendente sobrevive a múltiplas conversas | Task 6 |
| Quem não veio de anúncio não é contado como anúncio | Task 8 |
| A Loja mostra por onde as pessoas chegam de fato | Task 9 |
| Esse painel sobrevive à fonte de mídia offline | Task 9 (guard próprio) |
| O painel não depende de backfill para nascer correto | Task 9 (agrupa por `source_type`, não por `origem`) |
| Ninguém casa por telefone mascarado | Global + "O que foi descartado" |

## Ordem

| Task | Produto | Dependência |
|---|---|---|
| 1 | revy-trafego | — (é o conserto) |
| 2 | revy-trafego | independente |
| 3 | revy-trafego | depois de 1 |
| 4 | operação (anúncios + UI) | independente, paralelo |
| 8 | chatbot-api | independente |
| 9 | portal-gestao (Loja) | ler depois da 8; código não depende |
| 5 | revy-trafego | independente |
| 6 | chatbot-api | independente |
| 7 | ops/docs | final |

**Caminho mínimo:** Task 1 + Task 3. Tasks 2, 5 e 6 são proteção contra regressão.

**As três que valem por si:**

- **Task 1** conserta a atribuição de 96,4% dos leads de anúncio — retroativo, sem backfill.
- **Task 4** é a única que alcança os 3,6% restantes, e não é código.
- **Task 9** é a única com efeito visível no dia, e é quase de graça: o dado já existe, já viaja e já tem painel para morar.

A Task 8 é pré-requisito de honestidade da Task 9, não de funcionamento — o painel sai certo mesmo sem ela, porque agrupa pelo campo cru. Fazer as duas juntas evita que o CRM e o painel contem histórias diferentes.
