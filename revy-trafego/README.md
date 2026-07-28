# Revy Tráfego

Cockpit multi-loja da **equipe Revy** para operação de mídia paga (Pixel, CAPI, Ads spend, campanhas, ROI, auditorias e diagnóstico de leads).

O **portal da loja** (`portal-gestao`) mostra só resultados de negócio ao dono; a config técnica fica aqui.

## Fase 1

- Mesmo banco do portal (`REVY_TRAFEGO_DATABASE_URL` ou `PORTAL_DATABASE_URL`).
- Mesma chave Fernet dos tokens: `PORTAL_ENCRYPTION_KEY` (ou `REVY_TRAFEGO_ENCRYPTION_KEY`).
- Workers CAPI/spend **desligados por padrão** (continuam no portal até o cutover da Fase 2).

## Local

```bash
cd revy-trafego
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export REVY_TRAFEGO_DATABASE_URL="${PORTAL_DATABASE_URL:-sqlite:///./revy_trafego.db}"
export REVY_TRAFEGO_BOOTSTRAP_EMAIL=trafego@revy.local
export REVY_TRAFEGO_BOOTSTRAP_SENHA='troque-isto'
uvicorn app.main:app --reload --port 9010
```

Login: bootstrap cria o primeiro gestor se a tabela `gestores_revy` estiver vazia.

## Envs principais

| Env | Default | Notas |
|---|---|---|
| `REVY_TRAFEGO_DATABASE_URL` | = `PORTAL_DATABASE_URL` | Shared DB Fase 1 |
| `REVY_TRAFEGO_SESSION_SECRET` | dev | Cookie `revy_trafego_session` |
| `REVY_TRAFEGO_ENCRYPTION_KEY` | = `PORTAL_ENCRYPTION_KEY` | Tokens CAPI/Ads |
| `CHATBOT_API_URL` / `CHATBOT_API_TOKEN` | — | Diagnóstico leads |
| `REVY_TRAFEGO_META_SPEND_SYNC_ENABLED` | `0` | Job 24h |
| `REVY_TRAFEGO_CAPI_WORKER` | `0` | Retry outbox |
| `REVY_TRAFEGO_JOB_SECRET` | vazio | `POST /internal/jobs/meta-spend-sync` |

## Testes

```bash
pytest -q
```

## Deploy

Porta **9010**. Apontar para o mesmo Postgres do portal. Não ligar workers CAPI/spend enquanto o portal ainda os processa.
