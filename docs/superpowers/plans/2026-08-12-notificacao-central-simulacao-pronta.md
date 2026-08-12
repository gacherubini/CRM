# Central de Notificação geral + sinal "simulação pronta" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans. Steps usam checkbox (`- [ ]`).
> **Refatoração sensível:** a Fase B1 mexe nos 4 gates do sino, hoje protegidos por uma **property test de 48 combinações** (`tests/test_copiloto_notificacoes_shell.py:548-602`). Essa paridade **evolui** (não é mais igualdade estrita) — cada Task de B1 diz como. Execute B1 tarefa a tarefa, rodando os testes do Copiloto entre elas.

**Goal:** Promover o sino do Copiloto a uma **Central de Notificação geral do Portal**, desacoplada da flag do Copiloto (**decisão do dono: Opção A — "sininho geral pra tudo"**), com **elegibilidade por tipo**; e adicionar o primeiro tipo não-Copiloto — **"simulação pronta / lead qualificado aguardando"** — alimentado pelo chatbot-api. Isso substitui o aviso no grupo de estoque (§6.2 do design do híbrido) e vale para os **dois canais** (Baileys e Cloud), sem depender do Copiloto estar ligado.

**Architecture:** o model `CopilotoSinal`/`CopilotoSinalVisto`, o store, o sino/painel e as rotas continuam sendo a infra. Muda-se **quem pode ver o quê**: cada `regra` declara sua elegibilidade; o sino aparece se o usuário é elegível a **qualquer** tipo; a contagem filtra pelos tipos elegíveis; o worker avalia cada grupo de regras só para lojas elegíveis àquele grupo. O tipo `simulacao_pronta` é uma regra pura que **puxa** simulações prontas do chatbot-api (fit do worker, que já é pull).

**Tech Stack:** FastAPI, SQLAlchemy, o subsistema de sinais do Copiloto (`app/loja/copiloto/*`, `app/copiloto_sinais_job.py`), `ChatbotClient`, chatbot-api.

## Global Constraints

- **A "simulação pronta" NÃO pode depender de `REVY_LOJA_COPILOTO_ENABLED`.** É o requisito central. Ela é elegível quando a loja tem o **bot/estoque**, não o Copiloto.
- **Sinais do Copiloto (as 7 regras atuais) continuam gated no Copiloto** — o comportamento delas não muda.
- **Não reimplementar checagem de gate.** Usar os primitivos existentes (`revy_loja_shell_enabled`, `revy_loja_entitlements_enabled`, `module_enabled`/`Module`, papéis). Ver o contrato cruzado documentado em `loja_shell.py:106-129` e `loja_copiloto.py`.
- **Contagem por pessoa** (`CopilotoSinalVisto`) e cache TTL 45s (`notificacoes.py:36`) permanecem.
- **Papéis do aviso de simulação:** default `{"dono","gerente","vendedor"}` (o vendedor precisa ver o lead pronto). Registrar como constante `PAPEIS_NOTIF_SIMULACAO`. *(Decisão pequena; se o dono quiser só gestão, trocar o set.)*
- Rodar testes a partir de `portal-gestao/` e `chatbot-api/`: `.\.venv\Scripts\python.exe -m pytest -q`.

---

## FASE B1 — Generalizar o sino (elegibilidade por tipo)

### Task 1: Elegibilidade por tipo + conjunto de regras elegíveis

**Files:**
- Modify: `portal-gestao/app/web/loja_shell.py` (novas funções perto de `copiloto_secao_liberada:98`)
- Test: `portal-gestao/tests/test_central_elegibilidade.py`

**Interfaces:**
- Produces:
  - `simulacao_disponivel(ents, usuario, *, shell_enabled, entitlements_enabled) -> bool`
  - `regras_elegiveis(ents, usuario, *, shell_enabled, copiloto_enabled, entitlements_enabled) -> frozenset[str]` — devolve o conjunto de `regra` que essa pessoa pode ver (as 7 do Copiloto se `copiloto_secao_liberada`; `"simulacao_pronta"` se `simulacao_disponivel`).
  - `central_disponivel(...) -> bool` = `bool(regras_elegiveis(...))`.
- Consumes: `copiloto_secao_liberada` (existente), `SINAL_REGRAS`/nova constante `REGRAS_COPILOTO`, `PAPEIS_NOTIF_SIMULACAO`.

- [ ] **Step 1: Teste que falha**

```python
# portal-gestao/tests/test_central_elegibilidade.py
from app.web.loja_shell import regras_elegiveis, simulacao_disponivel


class _U:  # usuário mínimo
    def __init__(self, papel): self.papel = papel; self.id = "u1"


def _ents_vazio():
    from app.identity import EntitlementState  # ajuste ao import real do projeto
    return EntitlementState(modulos=frozenset())


def test_simulacao_disponivel_ignora_flag_do_copiloto():
    # simulação depende de shell + papel + (entitlements off => fail-open), NAO do Copiloto
    assert simulacao_disponivel(
        _ents_vazio(), _U("vendedor"),
        shell_enabled=True, entitlements_enabled=False,
    ) is True


def test_vendedor_ve_simulacao_mas_nao_copiloto():
    regras = regras_elegiveis(
        _ents_vazio(), _U("vendedor"),
        shell_enabled=True, copiloto_enabled=False, entitlements_enabled=False,
    )
    assert "simulacao_pronta" in regras
    assert not (regras & {"estoque_parado"})  # nenhuma regra do Copiloto


def test_sem_shell_nao_ve_nada():
    regras = regras_elegiveis(
        _ents_vazio(), _U("dono"),
        shell_enabled=False, copiloto_enabled=True, entitlements_enabled=False,
    )
    assert regras == frozenset()
```

- [ ] **Step 2: Rodar e ver falhar** — `cd portal-gestao && .\.venv\Scripts\python.exe -m pytest tests/test_central_elegibilidade.py -q` → ImportError.

- [ ] **Step 3: Implementar** em `loja_shell.py` (após `copiloto_secao_liberada`)

```python
PAPEIS_NOTIF_SIMULACAO = frozenset({"dono", "gerente", "vendedor"})
# As 7 regras do Copiloto (fonte: SINAL_REGRAS - "simulacao_pronta").
from app.models import SINAL_REGRAS  # no topo do arquivo


def simulacao_disponivel(
    ents, usuario, *, shell_enabled: bool, entitlements_enabled: bool
) -> bool:
    """Elegibilidade do aviso 'simulação pronta' — depende do bot/estoque, NÃO do Copiloto."""
    if not shell_enabled:
        return False
    papel = (getattr(usuario, "papel", "") or "").strip().casefold()
    if papel not in PAPEIS_NOTIF_SIMULACAO:
        return False
    if not entitlements_enabled:
        return True  # fail-open single-tenant, igual aos outros gates
    return module_enabled(ents, Module.ESTOQUE)


def regras_elegiveis(
    ents, usuario, *, shell_enabled: bool, copiloto_enabled: bool, entitlements_enabled: bool
) -> frozenset[str]:
    regras: set[str] = set()
    if copiloto_secao_liberada(
        ents, usuario, shell_enabled=shell_enabled,
        copiloto_enabled=copiloto_enabled, entitlements_enabled=entitlements_enabled,
    ):
        regras.update(r for r in SINAL_REGRAS if r != "simulacao_pronta")
    if simulacao_disponivel(
        ents, usuario, shell_enabled=shell_enabled, entitlements_enabled=entitlements_enabled,
    ):
        regras.add("simulacao_pronta")
    return frozenset(regras)


def central_disponivel(ents, usuario, *, shell_enabled, copiloto_enabled, entitlements_enabled) -> bool:
    return bool(regras_elegiveis(
        ents, usuario, shell_enabled=shell_enabled,
        copiloto_enabled=copiloto_enabled, entitlements_enabled=entitlements_enabled,
    ))
```
(Confirmar o import real de `EntitlementState`/`module_enabled`/`Module` — já usados no arquivo.)

- [ ] **Step 4: Rodar e ver passar.** Commit:
```bash
git add portal-gestao/app/web/loja_shell.py portal-gestao/tests/test_central_elegibilidade.py
git commit -m "feat(portal): elegibilidade de notificacao por tipo (central geral)"
```

### Task 2: Contagem filtrada pelos tipos elegíveis

**Files:**
- Modify: `portal-gestao/app/loja/copiloto/sinais_store.py` (`contar_sinais_novos:168`)
- Modify: `portal-gestao/app/loja/copiloto/notificacoes.py` (`contar_nao_vistos:48`)
- Test: `portal-gestao/tests/test_copiloto_sinais_store.py` (novo caso)

**Interfaces:**
- Muda: `contar_sinais_novos(db, loja_slug, usuario_id, *, regras: frozenset[str] | None = None) -> int` — se `regras` vier, conta só sinais com `CopilotoSinal.regra IN regras`. `None` = tudo (compat).
- Muda: `contar_nao_vistos(db, loja_slug, usuario_id, *, regras=None)`.

- [ ] **Step 1: Teste que falha** — cria 2 sinais (`estoque_parado` e `simulacao_pronta`), conta com `regras={"simulacao_pronta"}` → espera 1.
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar** — adicionar `if regras is not None: query = query.filter(CopilotoSinal.regra.in_(regras))` em `contar_sinais_novos`; propagar `regras` em `contar_nao_vistos` (e incluir no `_chave` do cache para não misturar contagens de escopos diferentes: `f"{loja_slug}:{usuario_id}:{hash(frozenset(regras)) if regras else 'all'}"`).
- [ ] **Step 4: Rodar e ver passar.** Commit `feat(portal): contar_sinais_novos filtra por regras elegiveis`.

### Task 3: Sino no shell usa elegibilidade da central + contagem filtrada

**Files:**
- Modify: `portal-gestao/app/web/loja_shell.py` (`_copiloto_nao_vistos:191`, `_contar_nao_vistos_com_sessao_propria:141`)
- Test: `portal-gestao/tests/test_copiloto_notificacoes_shell.py` (novos casos + evoluir paridade — Task 5)

**Interfaces:**
- `_copiloto_nao_vistos` passa a usar `regras_elegiveis(...)`: se vazio → `None` (sem sino); senão conta com essas `regras`. O contexto continua exposto como `copiloto_nao_vistos` (nome mantido para não quebrar o template `base.html:161`).

- [ ] **Step 1: Teste que falha** — loja com `REVY_LOJA_COPILOTO_ENABLED=0`, papel vendedor, 1 sinal `simulacao_pronta` → `template_extras(...)["copiloto_nao_vistos"] == 1` (hoje daria `None`).
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar** — em `_copiloto_nao_vistos`, trocar o gate `copiloto_secao_liberada(...)` por:
```python
    regras = regras_elegiveis(
        ents, usuario,
        shell_enabled=revy_loja_shell_enabled(),
        copiloto_enabled=revy_loja_copiloto_enabled(),
        entitlements_enabled=revy_loja_entitlements_enabled(),
    )
    if not regras:
        return None
    usuario_id = getattr(usuario, "id", None)
    if not usuario_id:
        return None
    return _contar_nao_vistos_com_sessao_propria(store.loja_slug, usuario_id, db, regras=regras)
```
e passar `regras` adiante em `_contar_nao_vistos_com_sessao_propria` → `contar_nao_vistos(..., regras=regras)`.
- [ ] **Step 4: Rodar e ver passar.** Commit `feat(portal): sino reflete qualquer tipo elegivel (central geral)`.

### Task 4: Worker avalia cada grupo de regras por elegibilidade da loja

**Files:**
- Modify: `portal-gestao/app/copiloto_sinais_job.py` (`_copiloto_permitido:62`, `lojas_ativas:75`, `avaliar_loja:175`, `_ligado:402`, `run_once:407`)
- Test: `portal-gestao/tests/test_copiloto_sinais_job.py`

**Interfaces:**
- `lojas_ativas` deixa de filtrar por Copiloto — devolve **todas as lojas ativas** (a elegibilidade vai por-tipo dentro de `avaliar_loja`). Adicionar helpers `_loja_permite_copiloto(db, slug)` (o antigo `_copiloto_permitido`) e `_loja_permite_simulacao(db, slug)` (Module.ESTOQUE / fail-open).
- `avaliar_loja` roda as 7 regras do Copiloto **só se** `_loja_permite_copiloto`, e a regra `simulacao_pronta` **só se** `_loja_permite_simulacao`.
- `_ligado()`/`run_once`: rodar se o shell está ligado (a simulação é core); não abortar só porque `revy_loja_copiloto_enabled()` é falso.

- [ ] **Step 1: Teste que falha** — loja ativa com Copiloto OFF + estoque ON: `run_once` cria sinal `simulacao_pronta` (mock do chatbot devolvendo 1 simulação pronta) e **nenhum** sinal de Copiloto.
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar** os gates por-tipo (renomear/duplicar `_copiloto_permitido`; ajustar `lojas_ativas`, `avaliar_loja`, `_ligado`, `run_once`). Manter o `sincronizar_sinais` como está (dedupe por `(regra, entidade_ref)` já isola os tipos).
- [ ] **Step 4: Rodar e ver passar.** Rodar `tests/test_copiloto_sinais_job.py -q`. Commit `feat(portal): worker avalia sinais por elegibilidade de tipo`.

### Task 5: Evoluir a property test de paridade

**Files:**
- Modify: `portal-gestao/tests/test_copiloto_notificacoes_shell.py` (`test_paridade_sino_x_secao:548-602`)

A invariante muda: o sino **não** é mais igual à seção Copiloto. Agora:
> `sino_aparece == (secao_copiloto_permite OR simulacao_elegivel)`

- [ ] **Step 1: Reescrever a asserção** para computar `simulacao_elegivel` (via `simulacao_disponivel(...)` com os mesmos flags do combo) e assertar:
```python
    esperado = secao_permite or simulacao_disponivel(
        ents, usuario, shell_enabled=shell_on, entitlements_enabled=entitlements_on,
    )
    assert sino_aparece == esperado, (...)
```
(obter `ents` do mesmo jeito que `template_extras` monta; ver `_copiloto_nao_vistos`.) Manter as 48 combinações — agora com `papel` incluindo `vendedor`, que passa a ver o sino via simulação mesmo sem Copiloto.
- [ ] **Step 2: Rodar toda a suíte de notificações** — `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_notificacoes_shell.py tests/test_copiloto_notificacoes_rotas.py -q`. Corrigir divergências (é o objetivo do teste). Commit `test(portal): paridade sino evolui para OR de tipos elegiveis`.

---

## FASE B2 — Sinal "simulação pronta" alimentado pelo chatbot-api

### Task 6: chatbot-api — GET de simulações prontas/pendentes

**Files:**
- Modify: `chatbot-api/app/main.py` (novo GET perto de `:1147/1342`)
- Modify: `chatbot-api/app/solicitacoes_simulacao.py` (função de leitura)
- Test: `chatbot-api/tests/test_solicitacoes_simulacao.py` (novo caso)

**Interfaces:**
- Produces: `GET /v1/operacao/simulacoes-prontas?instance=<opt>` → `{"itens": [{"telefone": str, "vendedor": str, "interesse": str, "criado_em": iso, "notificacao_id": str}]}` — deriva de `NotificacaoOperacional` com `status in ('pending','sent')` e `tipo='simulacao_humana'` na loja resolvida pelo token/instância, **sem CPF** (só o `payload_resumo` já mascarado).
- Consumes: `NotificacaoOperacional` (`models_db.py:295`), `resolver_loja_e_canal_por_instancia`.

- [ ] Steps TDD: teste que lista as notificações abertas da loja (mascaradas) → falha → implementar leitura (`SELECT ... WHERE loja_id AND status IN (...) ORDER BY created_at DESC LIMIT 50`) + rota autenticada (`verificar_webhook_token` ou o auth de serviço já usado nas rotas de operação) → passa → commit `feat(chatbot): GET de simulacoes prontas para a central de notificacao`.

### Task 7: `ChatbotClient.listar_simulacoes_prontas`

**Files:**
- Modify: `portal-gestao/app/clients/chatbot.py` (perto de `listar_leads:90`)
- Test: `portal-gestao/tests/test_chatbot_client_simulacoes.py` (espelha o padrão MockTransport de `test_estoque_client_atualizar.py`)

**Interfaces:**
- Produces: `ChatbotClient.listar_simulacoes_prontas(loja_slug: str | None = None) -> list[dict]` → GET `/v1/operacao/simulacoes-prontas`, devolve `["itens"]`; falha → devolve `[]` ou levanta `ChatbotIndisponivel` conforme o padrão dos outros métodos do client (seguir `listar_leads`).

- [ ] Steps TDD → commit `feat(portal): ChatbotClient.listar_simulacoes_prontas`.

### Task 8: Regra `simulacao_pronta` + catálogo + SINAL_REGRAS + wiring

**Files:**
- Modify: `portal-gestao/app/models.py` (`SINAL_REGRAS:515`)
- Modify: `portal-gestao/app/loja/copiloto/notificacoes.py` (`CATALOGO_REGRAS:106`)
- Modify: `portal-gestao/app/loja/copiloto/sinais.py` (nova `regra_simulacao_pronta`)
- Modify: `portal-gestao/app/copiloto_sinais_job.py` (`avaliar_loja` — wiring por-tipo da Task 4)
- Test: `portal-gestao/tests/test_copiloto_sinais_regras.py` (nova regra) + os testes AST já existentes travam a consistência.

**Interfaces:**
- Produces: `regra_simulacao_pronta(simulacoes: list[dict]) -> list[SinalCandidato]` — um candidato por simulação pronta; `entidade_ref = item["notificacao_id"]` (dedupe estável); `regra="simulacao_pronta"`; `severidade="atencao"`; `titulo=f"Simulação pronta — {vendedor}"`; `detalhe` com interesse; `acao_sugerida={"acao":"abrir","href":f"/app/loja/atendimento/{telefone}"}`. Modelo: `regra_lead_sem_resposta` (`sinais.py:71-91`).

- [ ] **Step 1:** adicionar `"simulacao_pronta"` a `SINAL_REGRAS` (`models.py:515`) — sozinho já faz o teste AST `test_copiloto_sinal_model.py:82` exigir a regra em `sinais.py`.
- [ ] **Step 2:** adicionar entrada em `CATALOGO_REGRAS` (`notificacoes.py:106`): `"simulacao_pronta": EntradaCatalogo(rotulo="Simulação pronta", icone="check", severidade_padrao="atencao")` — exigido por `test_copiloto_notificacoes_shell.py:822`.
- [ ] **Step 3:** escrever a regra pura + teste (candidatos a partir de uma lista fake) → falha → implementar.
- [ ] **Step 4:** wiring em `avaliar_loja` (dentro do ramo `_loja_permite_simulacao` da Task 4): `candidatos.extend(regra_simulacao_pronta(chatbot_ok(lambda: chatbot.listar_simulacoes_prontas(loja_slug)) or []))`.
- [ ] **Step 5:** rodar toda a suíte do Copiloto (`.\.venv\Scripts\python.exe -m pytest tests/ -q -k copiloto`) — os testes AST + paridade têm que passar. Commit `feat(portal): sinal simulacao_pronta na central de notificacao`.

### Task 9: Aposentar o aviso no grupo (do chatbot-api) — opcional nesta fase

**Files:** `chatbot-api/app/solicitacoes_simulacao.py` (`_despachar_alerta:113`)

Quando a central estiver validada, `_despachar_alerta` pode deixar de postar no grupo (a notificação já aparece no Portal). Fazer isso **atrás de flag** (`CHATBOT_ALERTA_GRUPO_ENABLED`, default ligado) para permitir rollback. **Não** remover o código do grupo antes de a central estar em produção.

- [ ] Steps: adicionar a flag; `_despachar_alerta` retorna cedo (marca `sent`) quando desligada; teste; commit `feat(chatbot): flag para aposentar aviso no grupo em favor da central`.

---

## Self-Review (cobertura vs §6.2 do design + decisão A)

- Opção A (central geral, não dependente do Copiloto): Fase B1 (Tasks 1-5) desacopla por tipo. **Coberto.**
- Aviso "simulação pronta" no sino, para os dois canais: Fase B2 (Tasks 6-8). **Coberto.**
- Aposentar o grupo: Task 9 (atrás de flag). **Coberto, reversível.**
- **Risco registrado:** B1 mexe em gating com property test de 48 combos — Task 5 evolui a invariante explicitamente; rodar os testes do Copiloto entre cada task de B1.
- **Decisões pequenas adiadas:** papéis que veem o aviso (`PAPEIS_NOTIF_SIMULACAO`, default dono/gerente/vendedor); pull-interval do worker (latência do aviso). Ajustáveis sem redesenho.
- **Não faz parte:** SMS/WhatsApp central como canal externo do aviso (a central in-app cobre a decisão do dono; SMS fica como canal plugável futuro do design §6.2).
