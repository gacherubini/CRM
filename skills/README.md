# `skills/` — ferramenta de agente, não produto Revy

Nada aqui é produto. Não tem banco, não tem migration, não entra no deploy do
Fly e não é consumido por HTTP por nenhum dos seis produtos. É ferramenta que o
agente usa **sobre** o repo.

Por isso as regras do `AGENTS.md` sobre produto não valem: não há README de
produto para ler antes, não há `.venv` por produto, e mudar coisa aqui não
pede regeração do mapa do `revy-research`.

| Skill | O que faz | Estado |
|---|---|---|
| `prod-readonly-db/` | Consulta PostgreSQL de produção por aliases locais, com role read-only, preflight que audita a role e gate de `SELECT` único | Código pronto e testado; **nenhum alias real configurado** |

## Rodar os testes

Da raiz do repo, com o Python do sistema (a skill é standard library pura,
não usa `.venv` de produto nenhum):

```bash
python3 -m unittest discover -s skills/prod-readonly-db/tests -v   # macOS
python -m unittest discover -s skills/prod-readonly-db/tests -v    # Windows
```

São 66 testes. Três deles falam com um PostgreSQL de verdade e ficam em skip
até você subir a fixture e pedir:

```bash
docker compose -f skills/prod-readonly-db/tests/docker-compose.yml up -d --wait
RUN_POSTGRES_INTEGRATION=1 python3 -m unittest discover -s skills/prod-readonly-db/tests -v
docker compose -f skills/prod-readonly-db/tests/docker-compose.yml down -v
```

A fixture é `postgres:17-alpine` na porta 55432, senha falsa, só loopback.
O `down -v` apaga container, rede e volume dela — e nada mais.

**Rode a integração antes de dizer que mudou algo.** Os unitários usam um
runner falso no lugar do `psql`, e o runner falso não imita o `psql`: três
defeitos passaram por 63 testes verdes e só apareceram contra o servidor de
verdade (o modo URL não chegava na libpq, o `ROLLBACK` virava alias de coluna,
e as linhas de status do psql quebravam os parsers).

## Onde essa pasta mora de verdade

A cópia canônica da `prod-readonly-db` é o kit pessoal
(`github.com/gacherubini/gabriel-kit`, `skills/prod-readonly-db`), que é de onde
ela se instala nos harnesses. Esta cópia é onde ela nasceu.

Duas cópias divergem. Se você mexer aqui, leve a mudança para o kit no mesmo
dia — ou apague esta pasta e deixe só o kit.

## Instalar

Não é automático e não deve ser. O caminho, e o gate de segurança que vem
antes do primeiro banco real, estão em
[`../docs/referencia-viva/planos/2026-09-08-skill-acesso-readonly-prod-db.md`](../docs/referencia-viva/planos/2026-09-08-skill-acesso-readonly-prod-db.md),
seção "Gate operacional posterior". Provisionar a role é trabalho de DBA; o
modelo da SQL está em `prod-readonly-db/references/postgresql.md`.
