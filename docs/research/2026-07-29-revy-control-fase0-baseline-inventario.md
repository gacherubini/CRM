# Revy Control — Fase 0: baseline e estado do inventário

**Data:** 2026-07-29  
**Commit auditado:** `f422edd47bbe537d404f5ae4cdb1860bd58e639b`  
**Escopo:** Revy Tráfego, Portal, Chatbot, Estoque e Catálogo  
**Plano:** [`2026-07-29-plano-revy-control.md`](../plans/2026-07-29-plano-revy-control.md)

Este documento registra somente evidências verificadas no repositório. Ele ainda não é o
inventário final de dados do lab e não autoriza iniciar backfill ou migration da Fase 1.

## Baseline reproduzível

As cinco suítes passaram no commit auditado:

| Serviço | Resultado | Observação |
|---|---:|---|
| Revy Tráfego | 95 passed | 34 warnings de depreciação do `TemplateResponse` |
| Portal | 293 passed | 444 warnings de depreciação do `TemplateResponse` |
| Chatbot | 170 passed | — |
| Estoque | 87 passed | — |
| Catálogo | 37 passed | — |
| **Total** | **682 passed** | Motor não pertence a este baseline do Control |

Comando exato usado em cada diretório de serviço, reutilizando o ambiente Python 3.12
local do Revy e sem gravar cache do pytest ou bytecode:

```bash
env PYTHONDONTWRITEBYTECODE=1 ../revy-trafego/.venv/bin/python \
  -m pytest -q -p no:cacheprovider
```

Para repetir as cinco execuções a partir da raiz:

```bash
for service in revy-trafego portal-gestao chatbot-api estoque-api catalogo-publico
do
  (
    cd "$service"
    env PYTHONDONTWRITEBYTECODE=1 ../revy-trafego/.venv/bin/python \
      -m pytest -q -p no:cacheprovider
  )
done
```

O baseline de 809 testes citado pelo plano Revy Loja inclui também 222 testes do Motor
de Simulação. Ele não deve ser confundido com os 682 testes dos cinco serviços exigidos
pela Fase 0 do Control.

## Estado das migrations

`python -m alembic heads` confirmou um único head por serviço:

| Serviço | Head do código |
|---|---|
| Revy Tráfego | `0001_revy_trafego_baseline` |
| Portal | `0012_revy_trafego_event_outbox` |
| Chatbot | `0013_tracking_pendente_conversa` |
| Estoque | `0007` |
| Catálogo | Não usa Alembic; evolui o SQLite em `InterestStore.initialize()` |

Comandos de conferência, executados dentro de cada serviço que possui Alembic:

```bash
python -m alembic heads
python -m alembic current
```

Achados que precisam permanecer visíveis antes da Fase 1:

- o arquivo local `portal-gestao/portal.db` está em `0008_funil_eventos`, embora o
  código esteja no head `0012`; as tabelas principais desse arquivo local estão vazias;
- Chatbot e Estoque leem a variável genérica `DATABASE_URL`; qualquer comando manual
  deve receber explicitamente a URL correta para não consultar ou migrar o banco errado;
- o downgrade de `0001_revy_trafego_baseline` é deliberadamente indisponível e exige
  restauração de backup;
- o Catálogo possui evolução de schema fora do Alembic e precisa ser verificado
  separadamente em qualquer ensaio de restauração.

## Flags do rollout

As flags planejadas abaixo não existem no código nem no deploy no commit auditado.
Quando implementadas, devem ter default **off**:

- `REVY_CONTROL_ENABLED`;
- `REVY_CONTROL_RBAC_ENABLED`;
- `GOOGLE_ADS_SYNC_ENABLED`;
- `GOOGLE_CONVERSIONS_ENABLED`;
- `MULTI_WHATSAPP_ENABLED`;
- `REVY_CONTROL_DASHBOARD_ENABLED`.

As flags atuais de cutover continuam fazendo parte do rollback:

| Flag | Default no código | Lab 3-VM |
|---|---:|---:|
| `REVY_TRAFEGO_CAPI_WORKER` | off | on |
| `REVY_TRAFEGO_META_SPEND_SYNC_ENABLED` | off | on |
| `PORTAL_REVY_TRAFEGO_RESULTADOS` | off | on |
| `PORTAL_REVY_TRAFEGO_VENDA_EVENTS` | off | on |
| `PORTAL_TRAFEGO_UI_LEGACY` | off | off |
| `PORTAL_CAPI_RETRY_ENABLED` | on no legado | off no Portal |
| `PORTAL_META_SPEND_SYNC_ENABLED` | on no legado | off no Portal |

O processo do Revy força os dois workers legados `PORTAL_*` somente dentro do seu
próprio processo. Ligar os workers de CAPI ou spend simultaneamente no Portal e no
Revy cria risco de processamento duplicado.

## Fontes já disponíveis para o inventário

- [`revy-trafego/app/lojas.py`](../../revy-trafego/app/lojas.py) reúne slugs encontrados
  nas tabelas locais de mídia/vendas e em `REVY_TRAFEGO_LOJAS`.
- [`deploy/fly/3vm/fly.app.toml`](../../deploy/fly/3vm/fly.app.toml) usa
  `moto-center` como slug canônico do lab e `loja1` somente como nome legado da
  instância Evolution.
- [`docs/handoff-contexto.md`](../handoff-contexto.md) registra que o inventário do
  cutover anterior encontrou uma loja e nenhum dado de usuário, venda ou mídia a
  migrar naquele momento. Essa evidência histórica não substitui uma consulta atual.
- [`catalogo-publico/tests/fixtures/estoque_publico.json`](../../catalogo-publico/tests/fixtures/estoque_publico.json)
  é uma fixture versionada do contrato Estoque → Catálogo.
- Há testes de webhook e outbox, mas os exemplos de inbound, `fromMe`, mídia e CTWA
  ainda não formam um conjunto de fixtures sanitizadas reutilizáveis.

Ainda faltam, portanto:

- relatório atual do lab mapeando IDs e slugs em todos os bancos e envs;
- comparação por `lower(trim(slug))` entre serviços;
- colisões de e-mail normalizado e telefone brasileiro normalizado;
- inventário sanitizado de instâncias Evolution e números;
- fixtures sanitizadas dos quatro tipos exigidos;
- snapshot versionado dos contratos HTTP que não podem quebrar.

Tokens e segredos nunca devem entrar no relatório. Para
`REVY_TRAFEGO_CHATBOT_TOKENS_JSON`, registrar apenas as chaves de loja.

## Backup, restore e rollback

Os documentos operacionais citam o snapshot `vs_K1n4oBDw96vHZngBNaNy`, criado antes
do cutover com retenção de cinco dias. Esta auditoria não verificou o snapshot na
plataforma nem comprovou restauração.

O volume `app_data` contém Portal, Revy, Catálogo e mídia do Estoque. Chatbot e o
banco do Estoque usam o PostgreSQL `suite-pg` e exigem confirmação de backup
separada. O runbook de Estoque standalone não comprova restore do ambiente 3-VM.

Antes da primeira migration da Fase 1 ainda é obrigatório:

1. criar ou confirmar backups atuais dos dois conjuntos de dados;
2. registrar versões/heads junto aos backups;
3. restaurá-los em destino descartável;
4. validar heads, contagens, leitura histórica e mídia do Catálogo;
5. documentar a matriz de suspensão e o rollback por flags.

## Gate

O baseline de testes está comprovado. Inventário de dados, colisões, fixtures,
contratos HTTP, matriz de suspensão e restore drill continuam abertos; nenhum deles
deve ser inferido como concluído a partir deste documento.
