# Provisionamento de loja e entitlements (Control → Portal) — achados 2026-08-02

Doc operacional/runbook nascido de uma investigação real em prod (`app2037`).
Explica **por que uma loja pode aparecer "sem módulo / acesso negado"** mesmo com as
flags ligadas, como o Portal decide os módulos, e como inspecionar/consertar em prod.

## TL;DR

- **Control (`revy-trafego`) é a fonte da verdade** das lojas, contratos e módulos.
  **O Portal guarda só uma cópia** (projeção) que o Control entrega por HTTP.
- Com `REVY_LOJA_ENTITLEMENTS_ENABLED=1`, o Portal **só libera** módulos que existem na
  sua projeção (`loja_operacional_projecao`), **fail-closed**. Sem projeção → tudo bloqueado
  ("módulo indisponível") e o menu do shell fica vazio (cai no menu legado).
- Uma loja que existe **só no Portal** (login) mas **não no Control** nunca recebe projeção.
  Foi o caso da `moto-center` após a migração pro `iad` (bancos nasceram vazios). **Fix:**
  criar a loja no Control (ativa + módulos) → a projeção flui sozinha pro Portal.

## Modelo de duas cópias

```
Revy Control (revy-trafego)                    Portal / Revy Loja
  lojas / loja_modulos / contratos_loja   --->   loja_operacional_projecao
  (fonte da verdade)                             (cópia lida em runtime)
        │                                              ▲
        │ mutação (criar loja, contratar/ativar        │ POST /internal/v1/provisioning/state
        │ módulo, mudar cargo) dispara o hook           │ (X-Service-Token)
        └── safe_enqueue_store_snapshot ──> control_provisioning_outbox ──> worker de entrega
            (provisioning_hooks.py)                     (provisioning_job.py, gated por
                                                         REVY_CONTROL_PROVISIONING_DELIVERY_ENABLED)
```

- Hooks que re-projetam (Control): `portfolio.py`, `roles.py`, `stores.py` chamam
  `safe_enqueue_store_snapshot` (`revy-trafego/app/control/provisioning_hooks.py`).
  Destinos padrão: `chatbot, estoque, portal, motor, catalogo`.
- Ingestão (Portal): `POST /internal/v1/provisioning/state` em
  `portal-gestao/app/web/trafego.py` → `app/provisioning.py::_apply_envelope`
  grava `loja_operacional_projecao`.
- **Não dá pra "ativar loja" com SQL cru** no Portal: fora do fluxo do Control não há
  projeção consistente nem versão. Sempre passar pelo Control.

## Como o Portal decide os módulos

- `portal-gestao/app/loja/entitlements.py::resolve_entitlements`:
  - flag **off** → `fail_open` (tudo liberado pra quem tem cargo — modo legado);
  - flag **on** → `from_db_projection` → `app/provisioning.py::allows_processing`
    (**fail-closed**: exige `(loja_slug,"loja")` = `ativa` e `(loja_slug,<modulo>)` = `ativo`).
- `app/web/loja_shell.py::check_module_access` retorna **None** (não bloqueia) quando a flag
  está off; só devolve 403 "Acesso negado" quando on **e** módulo ausente.
- `app/loja/navigation.py::build_nav` só monta as seções Vendas/Estoque/Ajustes se
  `loja_ativa` + módulo habilitado. Nav vazio → `base.html` cai no **menu legado**.

## Incidente moto-center (o que aconteceu)

- Login `bielcheeeeee@gmail.com` = dono da loja **`moto-center`** no Portal.
- No Control só existiam `sky` (encerrada) e `kk` (ativa) — **`moto-center` não existia**.
- Logo, projeção da `moto-center` no Portal = **vazia** → com entitlements on, "módulo estoque
  indisponível" + menu do shell vazio (só pra essa loja).
- **Fix aplicado pelo dono:** criou `moto-center` no Control (ativa + Vendas + Estoque). O
  outbox entregou aos 5 destinos (`delivered`) e o Portal passou a ter
  `moto-center`: loja=ativa, vendas=ativo, estoque=ativo. Resolvido.

## Estado das flags em prod (`app2037`, 2026-08-02)

Ligadas: `REVY_CONTROL_ENABLED`, `REVY_CONTROL_PROVISIONING_DELIVERY_ENABLED`,
`REVY_CONTROL_RBAC_ENABLED`, `REVY_CONTROL_DASHBOARD_ENABLED`, `MULTI_WHATSAPP_ENABLED`,
`REVY_LOJA_SHELL_ENABLED`, `REVY_LOJA_ENTITLEMENTS_ENABLED`, `REVY_LOJA_ATENDIMENTO_ENABLED`.

Desligadas (default 0): `REVY_LOJA_WHATSAPP_ENABLED` (⇒ opção "Números de WhatsApp" não
aparece), `REVY_LOJA_REDIRECT_LEGACY`, `SELLER_AI_ENABLED`.

> O redirect legado (Fase 8) mapeia `/app/funil`, `/app/financeiro`, `/app/relatorios` →
> `/app/loja/vendas` e `/app/leads`, `/app/conversas` → `/app/loja/atendimento` **só** com
> `REVY_LOJA_SHELL_ENABLED=1` + `REVY_LOJA_REDIRECT_LEGACY=1` (`app/loja/redirects.py`,
> middleware `revy_loja_legacy_redirects` em `main.py`). Em prod está **off**.

## Runbook — inspecionar os bancos em prod

Bancos SQLite ficam no volume do `app2037` (um por serviço):

```
/data/portal/portal.db            # Portal (loja_operacional_projecao, usuarios, …)
/data/revy-trafego/revy_trafego.db  # Control (lojas, loja_modulos, contratos_loja, control_provisioning_outbox)
/data/{catalogo,estoque,motor}/…    # demais serviços
```

Não há `sqlite3` no container; use Python via `fly ssh console` (SELECTs read-only). Base64
é bloqueado pelo classifier — escreva a query de forma legível:

```bash
fly ssh console -a app2037 -C "python3 -c \"import sqlite3; c=sqlite3.connect('/data/portal/portal.db'); [print(r) for r in c.execute('select loja_slug,aggregate,state from loja_operacional_projecao order by 1,2')]\""
```

Checagens úteis: projeção do Portal (acima); `select slug,status from lojas` e
`select * from loja_modulos` no Control; `select destination,status from control_provisioning_outbox`
(status `delivered` = entregou; `pending`/`failed` = worker parado ou token/URL errados).

## Runbook — provisionar/ativar uma loja (jeito certo)

1. Garanta `REVY_CONTROL_ENABLED=1` e `REVY_CONTROL_PROVISIONING_DELIVERY_ENABLED=1`.
2. No **Control**, crie a loja com o **slug idêntico** ao `loja_slug` do dono no Portal
   (ex.: `moto-center`), status **ativa**, e contrate/ative **Vendas** e **Estoque**.
3. Isso dispara o hook → outbox → worker entrega ao Portal (`/internal/v1/provisioning/state`).
4. Confirme a projeção (runbook acima): `loja=ativa`, `vendas=ativo`, `estoque=ativo`.
5. Só então mantenha/ligue `REVY_LOJA_ENTITLEMENTS_ENABLED=1`. (Enquanto não provisionar,
   `=0` = fail-open destrava tudo, mas sem enforcement de contrato.)

## Sintomas → causa

| Sintoma | Causa provável |
|---|---|
| "Acesso negado / módulo indisponível" numa loja | entitlements on + loja/módulo sem projeção no Portal (não provisionada no Control) |
| Menu do shell vazio (cai no legado) | mesmo motivo: `build_nav` sem `loja_ativa`/módulos |
| Funil/Financeiro/Relatórios/Leads caindo em /vendas ou /atendimento | `REVY_LOJA_REDIRECT_LEGACY=1` (+ shell on) — Fase 8; desligar o flag reverte |
| Opção "Números de WhatsApp" não aparece | `REVY_LOJA_WHATSAPP_ENABLED` off |
| Projeção não chega no Portal | worker off (`…DELIVERY_ENABLED=0`), token `PORTAL_SERVICE_TOKEN` divergente, ou `PORTAL_API_URL` errada |
