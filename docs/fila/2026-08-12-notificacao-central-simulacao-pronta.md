# Central de Notificação geral — Implementation Plan

> **Status 2026-08-13:** alinhado ao spec
> [`../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md`](../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md).
> Este card é **só a Fase B1** (sino geral, elegibilidade por tipo). Tipos do Modo 2
> (oferta 1:1 no `oferecido_a`) entram no **plano dos dois modos**, não aqui.
> B2/B9 antigos (blast `simulacao_pronta` + aposentar o grupo) — **não executar**.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans. Steps usam checkbox (`- [ ]`).
> **Refatoração sensível:** B1 mexe nos 4 gates do sino, hoje protegidos por uma **property test de 48 combinações** (`tests/test_copiloto_notificacoes_shell.py:548-602`). Execute tarefa a tarefa, rodando os testes do Copiloto entre elas.

**Goal:** Promover o sino do Copiloto a uma **Central de Notificação geral do Portal**, desacoplada da flag do Copiloto (**Opção A — "sininho geral pra tudo"**), com **elegibilidade por tipo**. Depois desta fase o sino *pode* mostrar tipos que não são Copiloto; o primeiro tipo novo **não** é deste card.

**Architecture:** o model `CopilotoSinal`/`CopilotoSinalVisto`, o store, o sino/painel e as rotas continuam sendo a infra. Muda-se **quem pode ver o quê**: `regras_elegiveis` devolve o conjunto de `regra` da pessoa; o sino aparece se o conjunto não é vazio; a contagem filtra por esse conjunto; o worker avalia cada grupo de regras só para lojas elegíveis àquele grupo. Hoje o conjunto é só as 7 do Copiloto. O plano dos dois modos acrescenta a oferta 1:1 nesse gancho.

**Tech Stack:** FastAPI, SQLAlchemy, `app/loja/copiloto/*`, `app/copiloto_sinais_job.py`.

## Global Constraints

- **Não criar** `simulacao_pronta`, `PAPEIS_NOTIF_SIMULACAO` nem GET de simulações prontas neste card.
- **Não aposentar o grupo de estoque.** Modo 1 mantém foto + aviso de simulação no grupo.
- **Sinais do Copiloto (as 7 regras) continuam gated no Copiloto** — o comportamento delas não muda.
- **Não reimplementar checagem de gate.** Usar `revy_loja_shell_enabled`, `revy_loja_entitlements_enabled`, `module_enabled`/`Module`, papéis. Contrato em `loja_shell.py:106-129`.
- **Contagem por pessoa** (`CopilotoSinalVisto`) e cache TTL 45s (`notificacoes.py:36`) permanecem.
- Rodar testes a partir de `portal-gestao/`: `python -m pytest -q`.

---

## FASE B1 — Generalizar o sino (elegibilidade por tipo)

### Task 1: Elegibilidade por tipo + conjunto de regras elegíveis

**Files:**
- Modify: `portal-gestao/app/web/loja_shell.py` (perto de `copiloto_secao_liberada:98`)
- Test: `portal-gestao/tests/test_central_elegibilidade.py`

**Interfaces:**
- `regras_elegiveis(ents, usuario, *, shell_enabled, copiloto_enabled, entitlements_enabled) -> frozenset[str]` — as 7 do Copiloto se `copiloto_secao_liberada`; senão vazio. Gancho: tipos novos só entram no plano dos dois modos.
- `central_disponivel(...) -> bool` = `bool(regras_elegiveis(...))`.

- [ ] **Step 1: Teste que falha**

```python
# portal-gestao/tests/test_central_elegibilidade.py
from app.web.loja_shell import regras_elegiveis, central_disponivel


class _U:
    def __init__(self, papel):
        self.papel = papel
        self.id = "u1"


def _ents_vazio():
    from app.identity import EntitlementState  # ajuste ao import real
    return EntitlementState(modulos=frozenset())


def test_copiloto_off_nao_libera_regras():
    regras = regras_elegiveis(
        _ents_vazio(), _U("dono"),
        shell_enabled=True, copiloto_enabled=False, entitlements_enabled=False,
    )
    assert regras == frozenset()
    assert central_disponivel(
        _ents_vazio(), _U("dono"),
        shell_enabled=True, copiloto_enabled=False, entitlements_enabled=False,
    ) is False


def test_copiloto_on_devolve_regras_do_copiloto():
    regras = regras_elegiveis(
        _ents_vazio(), _U("dono"),
        shell_enabled=True, copiloto_enabled=True, entitlements_enabled=False,
    )
    assert "estoque_parado" in regras
    assert "simulacao_pronta" not in regras


def test_sem_shell_nao_ve_nada():
    regras = regras_elegiveis(
        _ents_vazio(), _U("dono"),
        shell_enabled=False, copiloto_enabled=True, entitlements_enabled=False,
    )
    assert regras == frozenset()
```

- [ ] **Step 2:** `cd portal-gestao && python -m pytest tests/test_central_elegibilidade.py -q` → ImportError.
- [ ] **Step 3: Implementar** após `copiloto_secao_liberada` (import de `SINAL_REGRAS` no topo):

```python
def regras_elegiveis(
    ents, usuario, *, shell_enabled: bool, copiloto_enabled: bool, entitlements_enabled: bool
) -> frozenset[str]:
    if copiloto_secao_liberada(
        ents, usuario, shell_enabled=shell_enabled,
        copiloto_enabled=copiloto_enabled, entitlements_enabled=entitlements_enabled,
    ):
        return frozenset(SINAL_REGRAS)
    return frozenset()


def central_disponivel(ents, usuario, *, shell_enabled, copiloto_enabled, entitlements_enabled) -> bool:
    return bool(regras_elegiveis(
        ents, usuario, shell_enabled=shell_enabled,
        copiloto_enabled=copiloto_enabled, entitlements_enabled=entitlements_enabled,
    ))
```

- [ ] **Step 4:** testes passam. Commit `feat(portal): elegibilidade de notificacao por tipo (central geral)`.

### Task 2: Contagem filtrada pelos tipos elegíveis

**Files:**
- Modify: `portal-gestao/app/loja/copiloto/sinais_store.py` (`contar_sinais_novos:168`)
- Modify: `portal-gestao/app/loja/copiloto/notificacoes.py` (`contar_nao_vistos:48`)
- Test: `portal-gestao/tests/test_copiloto_sinais_store.py` (novo caso)

**Interfaces:**
- `contar_sinais_novos(..., *, regras: frozenset[str] | None = None) -> int` — se `regras` vier, `CopilotoSinal.regra IN regras`. `None` = tudo (compat).
- `contar_nao_vistos` propaga `regras`. Incluir no `_chave` do cache: `f"{loja_slug}:{usuario_id}:{hash(frozenset(regras)) if regras else 'all'}"`.

- [ ] **Step 1:** cria 2 sinais (`estoque_parado` e `lead_sem_resposta`), conta com `regras={"estoque_parado"}` → 1.
- [ ] **Step 2:** falha. **Step 3:** filtro + cache. **Step 4:** passa. Commit `feat(portal): contar_sinais_novos filtra por regras elegiveis`.

### Task 3: Sino no shell usa elegibilidade da central + contagem filtrada

**Files:**
- Modify: `portal-gestao/app/web/loja_shell.py` (`_copiloto_nao_vistos:191`, `_contar_nao_vistos_com_sessao_propria:141`)
- Test: `portal-gestao/tests/test_copiloto_notificacoes_shell.py` (Task 5)

**Interfaces:**
- `_copiloto_nao_vistos` usa `regras_elegiveis(...)`: vazio → `None`; senão conta com essas `regras`. Contexto continua `copiloto_nao_vistos` (`base.html:161`).

- [ ] **Step 1:** Copiloto OFF → `template_extras(...)["copiloto_nao_vistos"] is None` (igual hoje; o gancho é que o gate passou a ser `regras_elegiveis`, não `copiloto_secao_liberada` direto).
- [ ] **Step 3:**

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

- [ ] **Step 4:** passa. Commit `feat(portal): sino usa regras_elegiveis`.

### Task 4: Worker avalia por elegibilidade; não aborta só porque o Copiloto está off

**Files:**
- Modify: `portal-gestao/app/copiloto_sinais_job.py` (`_copiloto_permitido`, `lojas_ativas`, `avaliar_loja`, `_ligado`, `run_once`)
- Test: `portal-gestao/tests/test_copiloto_sinais_job.py`

**Interfaces:**
- `lojas_ativas` devolve **todas as lojas ativas** (elegibilidade por tipo dentro de `avaliar_loja`).
- `avaliar_loja` roda as 7 do Copiloto **só se** `_loja_permite_copiloto` (o antigo `_copiloto_permitido`). Sem ramo de `simulacao_pronta`.
- `_ligado()` / `run_once`: rodar se o **shell** está ligado. Não abortar só porque `revy_loja_copiloto_enabled()` é falso — senão o plano dos dois modos não tem worker para a oferta 1:1.

- [ ] **Step 1:** loja ativa, Copiloto OFF: `run_once` **não cria** sinal de Copiloto e **não levanta**. Hoje o job some cedo.
- [ ] **Step 3:** implementar. `sincronizar_sinais` fica. **Step 4:** `tests/test_copiloto_sinais_job.py -q`. Commit `feat(portal): worker do sino nao depende so do Copiloto`.

### Task 5: Property test de paridade usa `regras_elegiveis`

**Files:**
- Modify: `portal-gestao/tests/test_copiloto_notificacoes_shell.py` (`test_paridade_sino_x_secao:548-602`)

Invariante:
> `sino_aparece == bool(regras_elegiveis(...))`

Hoje isso coincide com a seção Copiloto. O plano dos dois modos amplia `regras_elegiveis`; este teste já estará no gancho certo.

- [ ] **Step 1:** asserção via `regras_elegiveis` (mesmos flags do combo). Manter as 48 combinações.
- [ ] **Step 2:** `python -m pytest tests/test_copiloto_notificacoes_shell.py tests/test_copiloto_notificacoes_rotas.py -q`. Commit `test(portal): paridade do sino via regras_elegiveis`.

---

## Superado — não executar (B2 / B9 antigos)

O blast `simulacao_pronta` para dono+gerente+vendedor e a flag para desligar o grupo **chocam** o spec dos dois modos:

| Card antigo | Spec fechado |
|---|---|
| Sino da oferta para a loja inteira | Só o vendedor `oferecido_a` |
| Ninguém pegou = mesmo sinal | Faixa + filtro **Aguardando** no Atendimento |
| Aposentar o grupo | Grupo **fica** no Modo 1 |

Esses tipos/avisos saem no **plano de implementação dos dois modos**, em cima de B1. Não reabrir B2/B9 aqui.

---

## Self-Review

- Opção A (sino geral, não depende do Copiloto para *existir*): B1. **Coberto.**
- Primeiro tipo não-Copiloto: **fora deste card** (spec §5.7–5.8).
- Grupo de estoque: **intocado.**
- Risco: gating + property test de 48 combos — Task 5; rodar testes do Copiloto entre as tasks de B1.
