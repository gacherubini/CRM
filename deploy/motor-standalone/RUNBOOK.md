# Runbook operacional — Motor standalone

Todos os comandos partem de `deploy/motor-standalone`. Não imprima `.env`, chaves, senhas ou
payloads em chamados e logs. O arquivo de backup contém dados pessoais cifrados e deve receber o
mesmo controle de acesso e retenção do banco.

## Métricas e alertas

`GET /metrics` expõe o formato Prometheus. Configure `MOTOR_METRICS_TOKEN` com um valor aleatório
longo e envie `Authorization: Bearer <token>`. Se o token estiver vazio, restrinja `/metrics` na
rede; o endpoint não inclui CPF, payload, referência externa nem ID de simulação.

Métricas disponíveis:

- `motor_simulations{status}`: quantidade persistida por estado;
- `motor_queue_jobs{status}` e `motor_queue_oldest_age_seconds`: tamanho e idade da fila;
- `motor_provider_results{provider,status}`: resultado final por provedor;
- `motor_provider_attempts{provider,status}`: tentativas por desfecho;
- `motor_provider_retries{provider}`: tentativas posteriores à primeira;
- `motor_provider_attempt_duration_seconds_count|sum`: contagem e latência acumulada.

Alertas iniciais recomendados: fila mais antiga acima do SLO; jobs presos em `processando`;
crescimento de retries; ausência de resultados concluídos; aumento da latência média
(`sum / count`). Defina os limiares depois de medir a carga real.

## Backup

Use o formato custom do PostgreSQL e gere o arquivo dentro do container para evitar conversão de
bytes por shells do Windows:

```powershell
New-Item -ItemType Directory -Force backups
docker compose exec postgres sh -c 'pg_dump -U motor -d motor -Fc -f /tmp/motor.dump'
docker compose exec postgres pg_restore -l /tmp/motor.dump
docker compose cp postgres:/tmp/motor.dump ./backups/motor.dump
docker compose exec postgres rm -f /tmp/motor.dump
```

O último comando é apenas uma checagem estrutural. Copie o backup para armazenamento cifrado fora
do host e registre a versão da aplicação (`GET /version`) e da migration
(`docker compose exec motor-api alembic current`). Teste restauração periodicamente.

## Restore

Restore é destrutivo para o banco de destino. Confirme o ambiente, preserve um backup do estado
atual e pare os consumidores antes de prosseguir:

```powershell
docker compose stop motor-api motor-worker
docker compose cp ./backups/motor.dump postgres:/tmp/motor.dump
docker compose exec postgres dropdb -U motor --if-exists motor
docker compose exec postgres createdb -U motor motor
docker compose exec postgres pg_restore -U motor -d motor --clean --if-exists /tmp/motor.dump
docker compose up -d motor-api motor-worker
docker compose exec postgres rm -f /tmp/motor.dump
```

Valide `/health/ready`, `/version`, `/metrics`, um job mock e a ausência de jobs presos. Não rode
`alembic downgrade` automaticamente sobre um backup de versão diferente; use a imagem compatível
com o schema restaurado e depois faça o upgrade normal.

## Upgrade

1. Leia notas da versão e confirme compatibilidade de schema/configuração.
2. Faça e valide um backup.
3. Construa a nova imagem sem remover o volume: `docker compose build --pull`.
4. Pare API e worker: `docker compose stop motor-api motor-worker`.
5. Migre uma única vez: `docker compose run --rm motor-api alembic upgrade head`.
6. Suba e valide: `docker compose up -d motor-api motor-worker`.
7. Confira health, versão, logs, fila e um job mock.

Se a nova aplicação falhar, pare os serviços. Volte à imagem anterior somente quando ela aceitar o
schema atual; caso contrário, restaure o backup em vez de improvisar downgrade.

## Rotação de segredos e credenciais

### Token de métricas

Substitua `MOTOR_METRICS_TOKEN` no `.env`, atualize primeiro o scraper e recrie somente a API:

```powershell
docker compose up -d --force-recreate motor-api
```

Não há janela com dois tokens nesta versão; coordene a troca para evitar perda temporária de coleta.

### Senha do PostgreSQL

Trocar apenas `POSTGRES_PASSWORD` não altera a senha de um volume já inicializado. Altere a role no
banco por um canal seguro, atualize o secret no `.env` e recrie API e worker. Não coloque a senha na
linha de comando nem no histórico do shell.

### Chave de cifra

`MOTOR_ENCRYPTION_KEY` cifra payloads e deriva o índice cego. A implementação atual aceita uma única
chave e não possui recriptografia online. Trocar a variável diretamente torna jobs existentes
indecifráveis. Até existir keyring/recriptografia, faça a rotação somente em uma janela planejada,
com expurgo/encerramento dos jobs pessoais conforme a retenção e backup validado.

### Credenciais de clientes da API

A camada de autenticação/tenancy do Motor ainda não está implementada no estado atual do
repositório. Portanto não existe procedimento real de rotação de Bearer de cliente a executar ou
homologar. Isso bloqueia declarar o pacote revendível concluído e deve ser resolvido antes da Task
10; não simule rotação editando registros inexistentes.

## Diagnóstico

```powershell
docker compose ps
docker compose logs --since 15m motor-api
docker compose logs --since 15m motor-worker
docker compose exec postgres pg_isready -U motor -d motor
curl.exe -fsS http://localhost:8000/health/live
curl.exe -fsS http://localhost:8000/health/ready
curl.exe -fsS http://localhost:8000/version
```

- Fila crescendo: verifique o worker, conexão com Postgres, retries e idade da fila em `/metrics`.
- `processando` sem avançar: preserve evidências e confirme se houve reinício durante execução. O
  mecanismo atual não possui lease/requeue de job abandonado; intervenção manual sem análise pode
  duplicar chamadas ao provedor.
- Muitos erros de provedor: use apenas `provider`, `status` e códigos sanitizados; não registre
  payload, páginas externas ou mensagens que possam conter CPF.
- API pronta, worker parado: a criação continuará respondendo `202`, mas a fila não será drenada.
- Falha após restore/upgrade: compare versão da imagem, `alembic current`, logs e schema do backup.
