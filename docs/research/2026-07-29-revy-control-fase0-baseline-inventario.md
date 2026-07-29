# Revy Control — Fase 0: baseline e estado do inventário

**Data:** 2026-07-29  
**Commit auditado:** `f422edd47bbe537d404f5ae4cdb1860bd58e639b`  
**Escopo:** Revy Tráfego, Portal, Chatbot, Estoque e Catálogo  
**Plano:** [`2026-07-29-plano-revy-control.md`](../plans/2026-07-29-plano-revy-control.md)

Este documento registra somente evidências verificadas no repositório. Ele ainda não é o
inventário final de dados do lab e não autoriza iniciar backfill ou migration da Fase 1.

## Atualização local do Revy Control

Após o baseline fixado acima, o corte local do Control avançou para o head Alembic
`0008_revy_control_loja_versao`, com **207 testes passando**. As seis flags planejadas
já existem com default off. O snapshot operacional versionado cobre Loja, Vendas e
Estoque, inclusive Loja legada sem evento de auditoria. Isso não equivale a migration
ou rollout no lab, nem implementa ainda o transporte Control → serviços.

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

No corte local atual, todas já existem com default off. O inventário remoto continua
necessário antes de alterar os valores do lab.

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

## Inventário local de identidade de Loja

| Superfície | Identidade atual | Compatibilidade e risco |
|---|---|---|
| Revy Control/Tráfego | `Loja.id` + slug canônico; sete tabelas legadas mantêm `loja_slug` e `loja_id` opcional | o backfill local é idempotente, mas não reconcilia outros bancos |
| Portal | `loja_slug` em toda a operação | maior fonte sem `loja_id`; importar usuários/dados sem renomear slugs ou filas |
| Chatbot | UUID local + slug; credencial e instância Evolution resolvem `loja_id` | o UUID ainda não é o ID do Control; mapear ambos durante o cutover |
| Estoque | UUID local + slug; credencial resolve `loja_id` | unicidade é apenas local e o slug não é canonicalizado no banco |
| Catálogo | `loja_slug` em rota, configuração e eventos | manter slug público e adicionar ID de forma compatível |
| Motor | `cliente_id`, sem Loja canônica | vincular Cliente, Simulação e Tarefa a `loja_id` antes do gate |
| n8n/deploy | instância, token e defaults por slug | configuração manual pode divergir dos bancos |

Não existe detector federado de colisão. O Control detecta slug canônico e colisão de
e-mail apenas no próprio banco; Portal, Chatbot e Estoque têm regras locais diferentes.
Telefones também divergem: variações `55`/nono dígito e HMAC dos dígitos exatos podem
representar a mesma pessoa de maneiras distintas. O gate remoto continua exigindo um
relatório `origem → valor bruto → valor normalizado → loja_id`.

## Contratos vivos que o cutover deve preservar

| Fluxo | Contrato atual | Regra de compatibilidade |
|---|---|---|
| Portal/Tráfego → Chatbot | `/v1/leads`, conversas, funil, simulação e operação; Bearer define a Loja | não exigir novo `loja_id` no body/path no primeiro deploy |
| Portal/Chatbot → Estoque privado | `/v1/veiculos...`; Bearer tenant-scoped e `Idempotency-Key` | preservar 401/404/409, payloads e dedupe |
| Chatbot/Catálogo → Estoque público | `/public/v1/lojas/{slug}...` | manter slug e response shape; suspensão coordenada pode responder 404 |
| Catálogo → Chatbot | `POST /v1/integracoes/catalogo/interesses` | preservar `event_id`, `Idempotency-Key`, retries e `loja_slug` durante o cutover |
| Portal → Control/Tráfego | resultados e eventos de venda por slug + `X-Service-Token` | não reescrever itens pendentes nem IDs idempotentes que contêm slug |
| Portal/Chatbot → Motor | simulações e credenciais por Bearer/`ClienteApi` | adicionar `loja_id` sem invalidar token, histórico ou idempotência |
| Catálogo → Pixel | `/public/v1/lojas/{slug}/pixel`, com Portal e Tráfego compatíveis | manter ambos os owners até o cutover conjunto |
| Estoque → webhook | HMAC e `X-Evento-Id`, `X-Evento-Tipo`, `X-Entrega-Id` | preservar bytes e IDs de entregas estacionadas |

O contrato novo Control → serviços ainda não existe. `ProvisioningControl.snapshot`
é somente o seam de domínio. A entrega deverá coexistir com slugs, tokens e chaves
idempotentes atuais até que consumidores e filas pendentes tenham migrado.

## Evolution, WhatsApp e fixtures

- O Chatbot modela uma `evolution_instance` única e um `whatsapp` opcional na Loja.
  Ainda não existe entidade first-class de canal, provedor, estado ou múltiplos números.
- `numeros_autorizados` é allowlist da equipe para operar Estoque; não representa o
  número comercial conectado.
- O inbound resolve a Loja pela instância e o webhook usa segredo global.
- O workflow n8n canônico ainda possui cinco saídas diretas para a Evolution: duas
  respostas de texto, avisos de simulação/handoff e envio de mídia. O gate final deve
  ficar no port do Chatbot antes do side effect.
- Testes já contêm payloads normalizados sanitizáveis de inbound, `fromMe`, CTWA,
  áudio e imagem. Ainda faltam arquivos de fixture raw Evolution sanitizados e
  reutilizáveis.

Ainda faltam, portanto:

- relatório atual do lab mapeando IDs e slugs em todos os bancos e envs;
- comparação por `lower(trim(slug))` entre serviços;
- colisões de e-mail normalizado e telefone brasileiro normalizado;
- confirmação sanitizada das instâncias Evolution e números reais do lab;
- fixtures raw sanitizadas dos quatro tipos exigidos;
- contrato e transporte versionados Control → serviços.

Tokens e segredos nunca devem entrar no relatório. Para
`REVY_TRAFEGO_CHATBOT_TOKENS_JSON`, registrar apenas as chaves de loja.

## Consulta read-only do lab Fly 3-VM

Uma consulta real à plataforma Fly foi executada em 2026-07-29 sem iniciar máquinas,
fazer deploy ou montar volumes em processos temporários.

Comandos read-only usados:

```bash
flyctl status -a <app>
flyctl machine list -a <app>
flyctl volumes list -a <app>
flyctl secrets list -a <app>
flyctl volumes snapshots list <volume-id> -a <app>
```

Os valores e digests dos secrets não foram copiados para este relatório. A evidência
operacional sanitizada foi:

| App | Máquinas | Volume persistente | Estado comprovado |
|---|---:|---|---|
| `app2037` | 0 | `app_data`, 1 GB, cifrado, desanexado | sem processo disponível para consultar Portal, Revy ou Catálogo |
| `suite-pg` | 1 | `pg_data`, 1 GB, cifrado, anexado | máquina parada; bancos PostgreSQL indisponíveis para consulta sem start |
| `evolution2037` | 0 | `evolution_instances`, 1 GB, cifrado, desanexado | API e banco da Evolution indisponíveis |
| `n8n2037` | 0 | `n8n_data`, 1 GB, cifrado, desanexado | sem processo ativo |

Os secrets relevantes encontrados por **nome**, todos com status `Staged`, foram:

- `app2037`: `CHATBOT_API_TOKEN`, `CHATBOT_DATABASE_URL`,
  `CHATBOT_WEBHOOK_TOKEN`, `ESTOQUE_API_TOKEN`, `ESTOQUE_DATABASE_URL`,
  `ESTOQUE_PUBLIC_API_TOKEN`, `PORTAL_ENCRYPTION_KEY`,
  `PORTAL_IDENTITY_HMAC_SECRET`, `PORTAL_SESSION_SECRET`,
  `CHATBOT_AUDIO_EVOLUTION_API_KEY`, `CHATBOT_IMAGE_EVOLUTION_API_KEY`,
  `CHATBOT_AUDIO_EVOLUTION_URL`, `CHATBOT_IMAGE_EVOLUTION_URL`,
  `REVY_TRAFEGO_BOOTSTRAP_EMAIL`, `REVY_TRAFEGO_BOOTSTRAP_NOME`,
  `REVY_TRAFEGO_BOOTSTRAP_SENHA`, `REVY_TRAFEGO_SERVICE_TOKEN` e
  `REVY_TRAFEGO_SESSION_SECRET`;
- `evolution2037`: `DATABASE_CONNECTION_URI`, `AUTHENTICATION_API_KEY` e
  `CACHE_REDIS_URI`.

`Staged` não comprova que esses valores estejam aplicados a uma máquina. Como não há
máquina em `app2037` ou `evolution2037`, não foi possível consultar:

- slugs persistidos por banco e colisões por `lower(trim(slug))`;
- contagens ou colisões normalizadas de e-mail e telefone;
- heads Alembic efetivamente gravados no lab;
- nomes/quantidade das instâncias Evolution e números mascarados;
- chaves efetivas de env dentro dos processos.

A configuração versionada continua apontando para o slug canônico `moto-center` e
para a instância Evolution legada `loja1`, mas isso não prova o conteúdo atual dos
volumes. “Sem máquina consultável” também não significa “sem dados persistidos”.
Obter esses dados exigiria iniciar ou recriar infraestrutura, o que é mutação e ficou
fora desta auditoria.

## Backup, restore e rollback

O snapshot `vs_K1n4oBDw96vHZngBNaNy` do volume `app_data` foi verificado diretamente
na plataforma: status `created`, 37 MiB armazenados para um volume de 1 GB e retenção
de cinco dias. Isso comprova somente a existência do snapshot, não sua restauração.

O volume `app_data` contém Portal, Revy, Catálogo e mídia do Estoque. Chatbot e o
banco do Estoque usam o PostgreSQL `suite-pg` e exigem confirmação de backup
separada. O volume `pg_data` existe, mas snapshots dele não foram validados nesta
consulta. O runbook de Estoque standalone não comprova restore do ambiente 3-VM.

Antes da primeira migration da Fase 1 ainda é obrigatório:

1. criar ou confirmar backups atuais dos dois conjuntos de dados;
2. registrar versões/heads junto aos backups;
3. restaurá-los em destino descartável;
4. validar heads, contagens, leitura histórica e mídia do Catálogo;
5. documentar a matriz de suspensão e o rollback por flags.

## Gate

O baseline, o inventário estrutural local, os contratos vivos e a matriz de suspensão
estão comprovados. Valores reais do lab, colisões federadas, fixtures raw e restore
drill continuam abertos; nenhum deles deve ser inferido como concluído a partir deste
documento.
