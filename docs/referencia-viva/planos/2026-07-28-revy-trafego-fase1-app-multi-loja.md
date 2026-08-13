# Revy Tráfego Fase 1 — App multi-loja + slim do portal

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar o app `revy-trafego` para a equipe Revy operar config + campanhas + ROI + auditoria + diagnóstico multi-loja, e retirar do portal da loja os menus/rotas técnicos de tráfego, mantendo resultados de negócio para o dono.

**Architecture:** Strangler com **schema compartilhado** (mesmo `DATABASE_URL`/Postgres do portal na Fase 1). Código de domínio de mídia é copiado/portado para o novo app; o portal deixa de expor UI de escrita técnica. Jobs CAPI/spend podem continuar no portal **ou** ser iniciados só no Revy Tráfego (preferir um único processo worker documentado no README).

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, Jinja2, argon2, cryptography, httpx, pytest — espelhar `portal-gestao`.

**Spec:** `docs/referencia-viva/specs/2026-07-28-revy-trafego-separacao-portal-design.md`
**Roadmap:** `docs/referencia-viva/planos/2026-07-28-plano-revy-trafego-separacao.md`

## Global Constraints

- Multi-loja: toda operação de domínio filtra por `loja_slug` da sessão do gestor (seletor).
- Fase 1: **mesmo banco** do portal (`REVY_TRAFEGO_DATABASE_URL` default = `PORTAL_DATABASE_URL`).
- Tokens CAPI/Ads: ciphertext com a **mesma** `PORTAL_ENCRYPTION_KEY` / `REVY_TRAFEGO_ENCRYPTION_KEY` compatível Fernet (se chaves divergirem, tokens existentes não decriptam).
- Integração Chatbot: só HTTP (`CHATBOT_API_URL` + token), reutilizar padrão de `portal-gestao/app/clients/`.
- Idioma UI: português BR.
- **Não** reescrever fórmula de ROI; portar `roi_calc.py` e testes.
- **Não** criar anúncios na Meta.
- Dono da loja **não** edita mais Pixel/campanhas após slim.
- Commits pequenos por task; stage explícito de arquivos.
- TDD: teste que falha → implementação → passa → commit.

## Mapa de arquivos (Fase 1)

| Path | Responsabilidade |
|---|---|
| `revy-trafego/` (novo) | App completo do gestor |
| `revy-trafego/app/auth.py` | Usuários internos Revy + sessão + CSRF |
| `revy-trafego/app/models.py` | `GestorRevy` + models de mídia/vendas (shared tables) |
| `revy-trafego/app/lojas.py` | Listar slugs conhecidos |
| `revy-trafego/app/main.py` | Rotas HTML + health + public pixel |
| `portal-gestao/app/templates/base.html` | Remover nav técnica de tráfego |
| `portal-gestao/app/main.py` | 403/redirect em rotas de escrita de tráfego; manter GET resultados locais |
| `portal-gestao/app/auth.py` | `pode_gerir_trafego` → sempre False (ou só admin legado se necessário) |
| `portal-gestao/app/resultados_dono.py` | Alertas sem links técnicos; hrefs de negócio |
| `docs/nao-plano/tutoriais/trafego-pago-loja.md` | Guia cliente só resultados |
| `revy-trafego/README.md` | Setup gestor + envs |

---

### Task 1: Scaffold `revy-trafego`

**Files:**
- Create: `revy-trafego/requirements.txt`
- Create: `revy-trafego/pytest.ini`
- Create: `revy-trafego/alembic.ini`
- Create: `revy-trafego/Dockerfile`
- Create: `revy-trafego/README.md`
- Create: `revy-trafego/app/__init__.py`
- Create: `revy-trafego/app/config.py`
- Create: `revy-trafego/app/db.py`
- Create: `revy-trafego/app/main.py` (health only)
- Create: `revy-trafego/tests/conftest.py`
- Create: `revy-trafego/tests/test_health.py`

**Interfaces:**
- Produces: `settings` com `database_url`, `session_secret`, `encryption_key`, `chatbot_url`, `chatbot_token`, `port` default 9010.
- Produces: `GET /health/live` → 200 `{"status":"ok"}`.

- [ ] **Step 1: Criar estrutura mínima e requirements**

`revy-trafego/requirements.txt` (mesmas pins do portal):

```text
fastapi==0.115.*
uvicorn[standard]==0.32.*
jinja2==3.*
sqlalchemy==2.*
psycopg[binary]==3.*
alembic==1.14.*
httpx==0.27.*
python-multipart==0.0.*
itsdangerous==2.*
argon2-cffi==23.*
cryptography==43.*
pytest==8.*
```

`revy-trafego/app/config.py`:

```python
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "REVY_TRAFEGO_DATABASE_URL",
        os.getenv("PORTAL_DATABASE_URL", "sqlite:///./revy_trafego.db"),
    )
    session_secret: str = os.getenv("REVY_TRAFEGO_SESSION_SECRET", "dev-trafego-troque")
    encryption_key: str = (
        os.getenv("REVY_TRAFEGO_ENCRYPTION_KEY")
        or os.getenv("PORTAL_ENCRYPTION_KEY", "")
    )
    secure_cookie: bool = os.getenv("REVY_TRAFEGO_SECURE_COOKIE", "0") == "1"
    chatbot_url: str = os.getenv("CHATBOT_API_URL", "http://chatbot-api:8000")
    chatbot_token: str = os.getenv("CHATBOT_API_TOKEN", "")
    request_timeout: float = float(os.getenv("REVY_TRAFEGO_HTTP_TIMEOUT", "5"))
    timezone: str = os.getenv("REVY_TRAFEGO_TIMEZONE", "America/Sao_Paulo")
    version: str = os.getenv("REVY_TRAFEGO_VERSION", "0.1.0")
    # Bootstrap do primeiro gestor (só se tabela vazia)
    bootstrap_email: str = os.getenv("REVY_TRAFEGO_BOOTSTRAP_EMAIL", "trafego@revy.local")
    bootstrap_senha: str = os.getenv("REVY_TRAFEGO_BOOTSTRAP_SENHA", "troque-isto")
    meta_spend_sync_enabled: bool = (
        os.getenv("REVY_TRAFEGO_META_SPEND_SYNC_ENABLED", "0").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    # Default OFF na Fase 1 se portal ainda roda o job — evitar double-sync.
    run_capi_worker: bool = (
        os.getenv("REVY_TRAFEGO_CAPI_WORKER", "0").strip().lower()
        in {"1", "true", "yes", "on"}
    )

settings = Settings()
```

- [ ] **Step 2: `db.py` + health**

Espelhar `portal-gestao/app/db.py` (engine, `SessionLocal`, `get_db`).
`main.py`:

```python
from fastapi import FastAPI

app = FastAPI(title="Revy Tráfego", version="0.1.0")

@app.get("/health/live")
def health_live():
    return {"status": "ok"}
```

- [ ] **Step 3: Teste health**

```python
# revy-trafego/tests/test_health.py
from fastapi.testclient import TestClient
from app.main import app

def test_health_live():
    client = TestClient(app)
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
```

Run: `cd revy-trafego && python -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 4: Dockerfile + README stub**

Dockerfile: porta **9010**, `uvicorn app.main:app --host 0.0.0.0 --port 9010`.
README: envs, como apontar pro mesmo DB do portal, bootstrap.

- [ ] **Step 5: Commit**

```bash
git add revy-trafego
git commit -m "feat(revy-trafego): scaffold app health e config Fase 1"
```

---

### Task 2: Auth interna (GestorRevy) + login

**Files:**
- Create: `revy-trafego/app/models.py` (mínimo `GestorRevy`)
- Create: `revy-trafego/app/auth.py`
- Create: `revy-trafego/app/cripto.py` (copiar de portal se ainda não)
- Create: `revy-trafego/alembic/versions/0001_gestor_revy.py`
- Create: `revy-trafego/app/templates/base.html`, `login.html`
- Modify: `revy-trafego/app/main.py` (session middleware, login/logout, bootstrap)
- Create: `revy-trafego/tests/test_auth.py`
- Modify: `revy-trafego/tests/conftest.py`

**Interfaces:**
- Produces: tabela `gestores_revy` (`id`, `email`, `nome`, `senha_hash`, `papel` in `gestor|admin`, `ativo`, `criado_em`).
- Produces: `usuario_atual(request, db) -> GestorRevy | None`, `require_gestor` dependency.
- Produces: sessão com `gestor_id`, `csrf`, `loja_slug` (opcional até Task 3).

- [ ] **Step 1: Teste — login falha sem usuário; bootstrap cria admin**

```python
def test_login_bootstrap_e_protege_home(client, db_session):
    # home redireciona para login
    r = client.get("/app", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers["location"]

def test_login_ok(client):
    # conftest faz bootstrap
    r = client.post("/login", data={"email": "trafego@revy.local", "senha": "secret"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] in {"/app", "/app/"}
```

- [ ] **Step 2: Implementar model + migration 0001**

Tabela **nova** (não colide com `usuarios` do portal): `gestores_revy`.

Em shared Postgres, Alembic do revy-trafego só cria esta tabela; **não** recria `campanhas` etc.

- [ ] **Step 3: Auth + SessionMiddleware + templates login**

Padrão argon2 igual portal. Cookie name distinto: `revy_trafego_session` (evitar colisão no mesmo domínio).

- [ ] **Step 4: Bootstrap no startup**

Se `count(gestores_revy)==0` e `bootstrap_email/senha` setados → cria `papel=admin`.

- [ ] **Step 5: pytest PASS + commit**

```bash
git add revy-trafego
git commit -m "feat(revy-trafego): auth gestores_revy e login"
```

---

### Task 3: Seletor de loja (todas as lojas)

**Files:**
- Create: `revy-trafego/app/lojas.py`
- Modify: `revy-trafego/app/main.py` (`POST /app/loja`, middleware de contexto)
- Modify: `revy-trafego/app/templates/base.html` (dropdown)
- Create: `revy-trafego/tests/test_lojas.py`

**Interfaces:**
- Produces: `listar_loja_slugs(db) -> list[str]`
  Fonte Fase 1 (união distinct, ordenada):
  - `campanhas.loja_slug`
  - `meta_pixel_config.loja_slug`
  - `meta_ads_config.loja_slug`
  - `vendas.loja_slug` (se tabela existir no shared DB)
- Produces: sessão `loja_slug`; helper `loja_atual(request) -> str | None`.
- Sem loja selecionada: `/app` mostra “Selecione uma loja” com lista; rotas de domínio redirecionam para seletor.

- [ ] **Step 1: Teste com fixtures de campanha/pixel em duas lojas**

```python
def test_lista_lojas_uniao(db_session):
    # inserir campanha loja-a e pixel loja-b
    assert listar_loja_slugs(db_session) == ["loja-a", "loja-b"]

def test_selecionar_loja_na_sessao(client_logado):
    r = client_logado.post("/app/loja", data={"loja_slug": "loja-a", "csrf": "..."}, follow_redirects=False)
    assert r.status_code == 303
    assert client_logado.get("/app").text  # contém loja-a ativa
```

- [ ] **Step 2: Implementar `lojas.py` + UI seletor**

- [ ] **Step 3: Models de leitura** — copiar de `portal-gestao/app/models.py` as classes necessárias com `__tablename__` idênticos (`Campanha`, `CampanhaGasto`, `MetaPixelConfig`, `MetaAdsConfig`, `MetaCapiOutbox`, `PixelCapiAuditoria`, `Venda` campos usados no ROI). **Não** mapear `Usuario` do portal.

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(revy-trafego): seletor multi-loja e models compartilhados"
```

---

### Task 4: Portar domínio de mídia (módulos puros + testes)

**Files:**
- Create (copy/adapt from portal):
  `meta_pixel.py`, `cripto.py` (se faltou), `campanhas.py`, `roi_calc.py`,
  `meta_capi.py`, `meta_capi_messaging.py`, `meta_ads_spend.py`,
  `pixel_capi_auditoria.py`, `resultados.py` (ex-`resultados_dono.py`)
- Create tests portados: `test_roi.py`, `test_campanhas.py`, `test_meta_ads_spend.py`, `test_pixel_capi_auditoria.py` (ajustar imports)

**Interfaces:**
- Mesmas funções públicas do portal (`totais_roi`, `match` UTM, `normalizar_pixel_id`, etc.).
- `resultados.resumo_periodo` / `alertas_trafego` com `href` apontando para rotas do **revy-trafego** (`/app/trafego`, …).

- [ ] **Step 1: Copiar `roi_calc.py` + `tests/test_roi.py` e fazer passar**

Run: `cd revy-trafego && .venv/bin/pytest tests/test_roi.py -v`

- [ ] **Step 2: Copiar `campanhas.py` + testes de match**

- [ ] **Step 3: Copiar meta_pixel, cripto, ads spend (funções puras), auditoria**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(revy-trafego): portar roi_calc campanhas meta helpers"
```

---

### Task 5: UI Config Tráfego + Pixel público + auditorias

**Files:**
- Create templates: `templates/trafego/form.html`, `pixel_auditoria.html`, `ctwa_auditoria.html`
- Modify: `main.py` rotas espelhando portal `/app/trafego*`, `/public/v1/lojas/{slug}/pixel`
- Create: `tests/test_trafego_ui.py`

**Interfaces:**
- `GET/POST /app/trafego` — Pixel/CAPI/Ads da **loja_slug da sessão**.
- `GET /public/v1/lojas/{loja_slug}/pixel` — **mesmo JSON** do portal (contrato catálogo).
- Auditorias filtradas por loja da sessão.

- [ ] **Step 1: Teste public pixel + dono-gestor salva config**

Portar asserts de `portal-gestao/tests/test_trafego.py` relevantes (sem papéis dono/vendedor).

- [ ] **Step 2: Implementar rotas e templates** (reusar CSS do portal: copiar `static/app.css` ou link compartilhado)

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(revy-trafego): UI config Pixel CAPI Ads e auditorias"
```

---

### Task 6: UI Campanhas + gastos + ROI

**Files:**
- Create: `templates/campanhas/*`, `templates/trafego/roi.html`
- Modify: `main.py` rotas `/app/campanhas`, `/app/trafego/roi`
- Create: `tests/test_campanhas_ui.py`, `tests/test_roi_ui.py`

**Interfaces:**
- CRUD campanha sempre com `loja_slug` da sessão (ignorar slug do form se diferente).
- ROI: mesmos query params de período/modo first|last do portal.

- [ ] **Step 1: Testes CRUD + isolamentoação multi-loja**

```python
def test_campanha_criada_na_loja_da_sessao(client_loja_a):
    # POST nova campanha
    # assert db row.loja_slug == "loja-a"

def test_gestor_nao_ve_campanha_de_outra_loja_sem_trocar_seletor(client_loja_a, campanha_loja_b):
    lista = client_loja_a.get("/app/campanhas")
    assert campanha_loja_b.nome not in lista.text
```

- [ ] **Step 2: Portar handlers do `main.py` do portal (trechos campanhas/roi)** — extrair para `revy-trafego/app/routes_campanhas.py` se `main` ficar grande.

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(revy-trafego): campanhas gastos e ROI multi-loja"
```

---

### Task 7: Jobs (flags) + sync spend manual

**Files:**
- Create: `meta_ads_spend_job.py`, `meta_capi_job.py` (port)
- Modify: `main.py` lifespan start/stop condicional
- Modify: `config.py` (já tem flags)
- Create: `tests/test_jobs_flags.py`

**Interfaces:**
- Default: **workers OFF** no revy-trafego (`REVY_TRAFEGO_META_SPEND_SYNC_ENABLED=0`, `REVY_TRAFEGO_CAPI_WORKER=0`) enquanto portal ainda processa — evita double-send.
- Botão “Sincronizar gastos agora” na UI **sempre** chama sync síncrono/manual (como portal), independente do job 24h.
- Documentar no README: em cutover, ligar workers no revy-trafego e desligar no portal.

- [ ] **Step 1: Teste que lifespan não inicia thread se flag off**

- [ ] **Step 2: Portar botão sync + endpoint interno opcional**
  `POST /internal/jobs/meta-spend-sync` com `X-Job-Token` (env `REVY_TRAFEGO_JOB_SECRET`).

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(revy-trafego): jobs spend/capi opt-in e sync manual"
```

---

### Task 8: Diagnóstico lead/conversa (proxy chatbot)

**Files:**
- Create: `app/clients/chatbot.py` (port reliability do portal)
- Create: `templates/diagnostico/leads.html`, `lead_detalhe.html`, `conversa.html`
- Modify: `main.py` rotas `/app/diagnostico/leads`, `.../{id}`, `.../conversas/{tel}`
- Create: `app/audit.py` + tabela opcional `gestor_audit_log` (recomendado)
- Create: `tests/test_diagnostico.py`

**Interfaces:**
- Lista leads da loja com filtro `utm_campaign` / campanha_id / período (campos que a API chatbot já expõe).
- Detalhe: JSON lead + link conversa.
- **Audit log** (mínimo): `gestor_email`, `loja_slug`, `acao`, `recurso_id`, `em`.

- [ ] **Step 1: Teste com httpx mock — lista leads só da loja da sessão**

- [ ] **Step 2: Implementar client + páginas**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(revy-trafego): diagnostico leads conversas com audit log"
```

---

### Task 9: Slim do portal da loja

**Files:**
- Modify: `portal-gestao/app/auth.py` — separar permissões:
  - `pode_gerir_trafego(usuario) -> bool` default **False** (ou `PORTAL_TRAFEGO_UI_LEGACY=1` restaura True para dono/gerente).
  - **Novo** `pode_ver_resultados_midia(usuario) -> bool` → True para `dono`, `gerente` (e opcionalmente `admin_plataforma`).
- Modify: `portal-gestao/app/templates/partials/resultados_periodo.html` — trocar
  `{% if pode_gerir_trafego and resultados_view %}`
  por
  `{% if pode_ver_resultados_midia and resultados_view %}`.
  **Crítico:** se só zerar `pode_gerir_trafego` sem essa troca, o dono **some** o bloco de resultados.
- Modify: `portal-gestao/app/templates/base.html` — remover links Tráfego, CTWA, Pixel, Campanhas, ROI técnico.
- Modify: `portal-gestao/app/main.py` — rotas `/app/trafego*`, `/app/campanhas*` de **escrita** e GET de config: redirect `/app` se não legacy; dashboard passa `pode_ver_resultados_midia=...` e **continua** calculando `resultados_view` quando essa flag for True.
- **Manter** `GET /public/v1/lojas/{slug}/pixel` no portal na Fase 1 (catálogo continua).
- **Manter** workers CAPI/spend no portal na Fase 1 (default).
- **Manter** cálculo `resultados_dono` no dashboard `/app` (SQL local shared).
- Modify: `resultados_dono.py` — alertas técnicos com texto “A equipe Revy cuida da medição” **sem** href `/app/trafego`; checklist sem passos de token (ou checklist só “resultados ok”).
- Modify: `portal-gestao/app/templates/partials/alertas_trafego.html` / onboarding se linkarem config.
- Modify tests: `test_trafego.py`, `test_campanhas.py`, `test_resultados_dono.py`, nav tests — dono **não** vê links técnicos; **ainda vê** bloco resultados se fixtures existirem.
- Optional: página `/app/resultados` somente leitura reusando partial `resultados_periodo.html`.

**Interfaces:**
- `pode_gerir_trafego(usuario) -> bool` default False.
- `pode_ver_resultados_midia(usuario) -> bool` True para dono/gerente.
- Dono ainda confirma venda (CAPI continua via código portal).

- [ ] **Step 1: Atualizar testes do portal para o novo RBAC de UI**

```python
def test_dono_nao_ve_nav_trafego(client):
    login(client)  # dono
    pagina = client.get("/app")
    assert 'href="/app/trafego"' not in pagina.text
    assert 'href="/app/campanhas"' not in pagina.text

def test_dono_trafego_redirect(client):
    login(client)
    r = client.get("/app/trafego", follow_redirects=False)
    assert r.status_code == 303

def test_dono_ainda_ve_resultados_midia(client, seed_roi_minimo):
    login(client)
    pagina = client.get("/app")
    assert "Tráfego pago" in pagina.text or "Resultados" in pagina.text
    # não depende de href /app/trafego
```

- [ ] **Step 2: Implementar slim + `pode_ver_resultados_midia` + ajustar alertas**

- [ ] **Step 3: Rodar suite portal**

Run: `cd portal-gestao && .venv/bin/pytest tests/test_trafego.py tests/test_campanhas.py tests/test_resultados_dono.py tests/test_roi.py tests/test_vendas.py -v`
Expected: PASS (testes de UI técnica do dono reescritos; public pixel e CAPI venda intactos)

- [ ] **Step 4: Commit**

```bash
git add portal-gestao
git commit -m "feat(portal): remove UI tecnica de trafego do dono (Fase 1 slim)"
```

---

### Task 10: Docs, deploy notes, regressão final

**Files:**
- Modify: `docs/nao-plano/tutoriais/trafego-pago-loja.md` — seção setup vira “Revy configura”; cliente só lê resultados.
- Create: `docs/revy-trafego-interno.md` — guia equipe (login, seletor, Pixel, campanhas, ROI, diagnóstico).
- Modify: `docs/referencia-viva/contexto-compacto.md` — eixo C aponta este plano.
- Modify: `docs/nao-plano/historico/README.md` — entrada 6.4 Revy Tráfego.
- Modify: `README.md` raiz (tabela de apps) se listar serviços.
- Modify: `revy-trafego/README.md` — cutover workers, envs, shared DB.

- [ ] **Step 1: Escrever docs**

- [ ] **Step 2: Checklist manual local**

1. Subir portal + revy-trafego no **mesmo** SQLite/Postgres de dev.
2. Bootstrap gestor; selecionar loja; salvar Pixel de teste.
3. Verificar `GET` public pixel no **portal** ainda reflete o valor (shared DB).
4. Criar campanha no revy-trafego; ver ROI.
5. Login dono no portal: sem menus técnicos; visão geral com resultados se houver dados.
6. Confirmar venda de teste: outbox CAPI no portal ainda processa.

- [ ] **Step 3: Commit docs**

```bash
git add docs revy-trafego/README.md README.md
git commit -m "docs: Revy Trafego Fase 1 guia cliente e interno"
```

---

## Rollback Fase 1

1. `PORTAL_TRAFEGO_UI_LEGACY=1` (se implementado) restaura menus do dono.
2. Parar app `revy-trafego`.
3. Dados intactos (shared DB).

## Definition of Done (Fase 1)

- [ ] Todos os checkboxes das Tasks 1–10
- [ ] Suites `revy-trafego` e subset portal verdes
- [ ] Critérios do roadmap Fase 1 atendidos

**Próximo:** executar [Fase 2 — API + cutover](2026-07-28-revy-trafego-fase2-api-cutover.md).
