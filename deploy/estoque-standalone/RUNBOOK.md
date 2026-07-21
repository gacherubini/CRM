# Runbook operacional — Estoque standalone

Execute os comandos a partir de `deploy/estoque-standalone`. O backup precisa
preservar **juntos** o PostgreSQL e o volume `estoque_media`; o banco guarda as
referências e o volume contém as fotos. Proteja ambos fora do host com cifra,
controle de acesso e retenção adequada.

## Backup consistente

Use uma janela curta sem escrita para evitar que banco e galeria fiquem em
instantes diferentes:

```bash
mkdir -p backups
docker compose stop estoque-api estoque-outbox
docker compose exec -T postgres sh -c 'pg_dump -U estoque -d estoque -Fc -f /tmp/estoque.dump'
docker compose exec -T postgres pg_restore -l /tmp/estoque.dump
docker compose cp postgres:/tmp/estoque.dump ./backups/estoque.dump
docker compose exec -T postgres rm -f /tmp/estoque.dump
docker compose run --name estoque-backup-media --no-deps estoque-api tar -C /data -czf /tmp/estoque-media.tgz media
docker cp estoque-backup-media:/tmp/estoque-media.tgz ./backups/estoque-media.tgz
docker rm estoque-backup-media
docker compose up -d estoque-api estoque-outbox
```

Registre junto ao backup a saída de `GET /version` e `docker compose exec
estoque-api alembic current`. Guarde uma cópia cifrada fora do host e teste a
restauração periodicamente.

## Restore

O restore substitui dados e fotos. Confirme o ambiente, preserve um backup do
estado atual e só então execute:

```bash
docker compose stop estoque-api estoque-outbox
docker compose cp ./backups/estoque.dump postgres:/tmp/estoque.dump
docker compose exec -T postgres pg_restore -U estoque -d estoque --clean --if-exists /tmp/estoque.dump
docker compose exec -T postgres rm -f /tmp/estoque.dump
docker compose run -d --name estoque-restore-media --no-deps estoque-api sleep infinity
docker cp ./backups/estoque-media.tgz estoque-restore-media:/tmp/estoque-media.tgz
docker exec estoque-restore-media sh -c 'find /data/media -mindepth 1 -maxdepth 1 -exec rm -rf {} + && tar -C /data -xzf /tmp/estoque-media.tgz'
docker rm -f estoque-restore-media
docker compose run --rm estoque-api alembic upgrade head
docker compose up -d estoque-api estoque-outbox
```

Valide `GET /health/ready`, `GET /version`, uma listagem privada, uma listagem
pública e a abertura de pelo menos uma foto. Depois rode
`python -m app.cli limpar-midias-orfas` somente em modo de prévia.

## Upgrade

1. Faça e valide um backup de banco e fotos.
2. Construa a imagem nova sem remover volumes: `docker compose build --pull`.
3. Pare API e worker.
4. Aplique `docker compose run --rm estoque-api alembic upgrade head` uma vez.
5. Suba os serviços e confira health, versão, logs, fotos e outbox.

Não use `docker compose down -v`: essa opção remove os volumes persistentes.
Não improvise `alembic downgrade` sobre dados de outra versão; restaure o par de
backups com a imagem compatível e faça o upgrade normal.

## Manutenção de fotos

O worker aplica a limpeza a cada
`ESTOQUE_MEDIA_CLEANUP_INTERVAL_SECONDS` (padrão 21600 segundos), preservando
arquivos mais novos que `ESTOQUE_MEDIA_ORPHAN_GRACE_SECONDS` (padrão 3600).
Sem `ESTOQUE_MEDIA_PUBLIC_BASE_URL`, a rotina falha fechada e não apaga nada.

Para auditar manualmente:

```bash
docker compose exec estoque-api python -m app.cli limpar-midias-orfas
```

Use `--aplicar` manualmente apenas com backup validado. O cliente e o modelo não
possuem endpoint para disparar ou parametrizar essa exclusão.
