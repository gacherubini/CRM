# Handoff — Status das integrações + fixes (2026-08-02)

Contexto pra continuar em outra sessão. Tudo que segue já está em `main` e deployado, exceto a **Fase 4** (não iniciada).

## O que foi entregue e está no ar

### 1. Autogestão de senha do lojista (feature completa)
- Lojista redefine a própria senha: `/senha/esqueci` (fluxo de recuperação) e `/conta/senha` (troca logado).
- Tabela `RedefinicaoSenha` — migration `revy-trafego/alembic/versions/0018_redefinicoes_senha.py`.
- **Merged em main, deployado v58, verificado live** (`/senha/esqueci` → 200, `/conta/senha` → 303).
- Specs/plans: `docs/superpowers/specs/2026-08-01-autogestao-senha-lojista-design.md`, `docs/superpowers/plans/2026-08-01-autogestao-senha-lojista.md`.

### 2. Fix — email do convite de dono não enviava
- Adicionado `logging` + `logger.exception(...)` no `except` que engolia o erro, em `portal-gestao/app/web/owner_invitations.py`.
- Adicionado **erro visível pro usuário** quando o email não é mandado (fluxo `dono_email_pendente`).
- Em `revy-trafego/app/web/control_ui.py`: `logger`, `_OK_TO_TAB["dono_email_pendente"]="pessoas"`, redirect corrigido, `logger.exception` no convite de gestor.
- Warning branch `dono_email_pendente` em `revy-trafego/app/templates/control/loja_detail.html`.
- **Causa raiz do 535 BadCredentials era Gmail-side** (App Password), o usuário arrumou por conta. Não era flag/commit.

### 3. Fix — "convite inválido ou expirado" no link do mesmo dia (bug multiloja)
- `portal-gestao/app/owner_invitations.py`: `activate_owner_invitation` reestruturado — valida token ANTES de pedir senha. Novos helpers `_find_active_invitation(...)` e `owner_invitation_needs_password(db, *, token) -> bool`.
- Regra: se `not user.ativo` pede senha (12-256); **dono já ativo convidado pra nova loja pula a senha** e só confirma o vínculo.
- GET `/convite/aceitar` redireciona dono já ativo: `if token and not owner_invitation_needs_password(...): RedirectResponse("/login?ativado=1", 303)`.

### 4. Status das integrações (Meta/Google/WhatsApp) — Fases 1-3 COMPLETAS
Painel no **detalhe da Loja no Revy Control** mostrando se Pixel/CAPI/Meta Ads/Google Ads/WhatsApp estão realmente conectados. Verde=conectado / vermelho=erro / cinza=não configurado. Checagem LIVE, cache 10min + invalidação por evento, botão "Testar agora".

**Backend (Fase 1):**
- `revy-trafego/app/control/integrations_health.py` — `HealthStatus(CONNECTED/ERROR/MISSING)`, `ItemHealth`, `GroupHealth`, `check_meta`, `check_google`, `check_whatsapp`, `health_da_loja(db, store, *, probe, exchanger, whatsapp_port, forcar=False, cache=None, clock=None) -> dict`, `invalidar(store_id)`, `WhatsappPort`, `ChatbotWhatsappPort`. WhatsApp verde SÓ se TODOS os números conectados; sem números = cinza.
- `revy-trafego/app/control/graph_probe.py` — `HttpGraphProbe.validar_token(...)` nunca vaza token, `transport` injetável.
- `revy-trafego/app/control/health_cache.py` — `TTLCache(ttl_seg, clock)`.
- `revy-trafego/app/config.py` — `integracoes_health_ttl_seg` (600), `integracoes_health_timeout_seg` (5.0).
- `revy-trafego/app/clients/chatbot.py` — `listar_canais_whatsapp() -> list[dict]` (GET /v1/whatsapp/canais).

**Endpoint (Fase 2):**
- `GET /control/v1/lojas/{loja_id}/integracoes/health?forcar=0|1` em `control_ui.py` (auth `gestor_atual`, factories `_build_probe()`/`_build_exchanger()`/`_build_whatsapp_port()`).

**UI (Fase 3):**
- Card `#integracoes-health` no topo de `#panel-visao` (aba "Visão geral" — NÃO em `#panel-integracoes`, que é gated por `google_ads_enabled`, off em prod).
- `revy-trafego/app/static/js/integracoes_health.js` — vanilla JS, XSS-safe (createElement/textContent).
- `revy-trafego/app/static/css/app.css` — classes `.integ-*` (light+dark, prefers-reduced-motion).
- Specs/plans: `docs/superpowers/specs/2026-08-01-status-integracoes-design.md`, `docs/superpowers/plans/2026-08-01-status-integracoes.md`.

## Bug crítico corrigido por último (v60) — por que "não achei o status"
Atrás do nginx edge o Control vive sob `/trafego/`, mas o JS buscava `/control/v1/...` SEM o prefixo → 404 → card ficava vazio.
**Fix:** template passa `data-integ-endpoint="{{ public_path('/control/v1/lojas/' ~ store.id ~ '/integracoes/health') }}"`; JS lê `section.getAttribute("data-integ-endpoint")` (fallback relativo só pra dev). Commit `46953c2`, deployado **v60**, verificado (JS deployado usa o atributo; endpoint sob `/trafego` retorna 401 = existe).

**Onde ver:** `https://app2037.fly.dev/trafego/app` → login gestor → abrir uma loja → aba "Visão geral" → card "Status das integrações" no topo. Hard refresh (Cmd+Shift+R) pra furar cache do JS antigo.

## PENDENTE — Fase 4: mesmo painel no shell da Loja (visão do lojista)
Não iniciada. Autorizada pelo usuário ("manda tudo e deploya"), mas deployei Fases 1-3 primeiro. Cross-app (~3 tasks):
1. **Control service endpoint** `GET /control/v1/servico/lojas/{slug}/integracoes/health` (auth `exigir_service_token`, resolve store por slug, reusa `health_da_loja`) — seguir padrão "Contrato read-only para Revy Loja" em `revy-trafego/app/web/control.py`.
2. **Portal proxy** `GET /app/loja/integracoes/health` (`RevyTrafegoClient.fetch_integracoes_health` + header `X-Service-Token` = `settings.revy_trafego_service_token`).
3. **Página Loja** `/app/loja/integracoes` em Ajustes (nav item em `portal-gestao/app/loja/navigation.py`) + copiar CSS `.integ-*` e JS (parametrizado via `data-integ-endpoint` apontando pro proxy) pro static do Portal.
- Branch `feat/integracoes-health` e ledger SDD `.superpowers/sdd/2026-08-01-status-integracoes/progress.md` prontos pra retomar. (Nota: as Fases e o fix /trafego foram commitados DIRETO em `main`; main está em `46953c2`.)

## Ambiente / gotchas
- **Fly lab está UP** (suite-pg, evolution2037, app2037, n8n2037). Derrubar: `bash deploy/fly/down-all.sh --3vm --yes` (usar bash do brew).
- **`up-all.sh --3vm` quebra no bash 3.2 do macOS** (`declare -A`): usar `/opt/homebrew/bin/bash` ou `fly machine start` direto. Ações Fly são bloqueadas pelo classificador desta sessão — o usuário roda no terminal dele.
- **Deploy:** `fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false`.
- **Testes falhando PRÉ-EXISTENTES (não são meus, confirmado via git stash):** portal-gestao 3× `test_funil.py`; revy-trafego 1× `test_control_provisioning_outbox.py::test_process_pending_falha_marca_failed_e_incrementa_attempts`.
- Warning de deploy "not listening on 0.0.0.0:8080" é timing benigno do smoke-check; health confirma 200.

## Testes do painel
`revy-trafego/tests/test_control_integracoes_health_ui.py` — 3 passando (inclui asserção do `data-integ-endpoint`).
