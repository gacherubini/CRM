# Ferramenta do corte SQLite → Postgres

Move `portal.db` e `revy_trafego.db` para o banco `revy` no `suite-pg`, com um
schema por produto, sem perder linha e sem alterar centavo.

Plano completo: [`docs/fila/2026-08-16-postgres-2-corte.md`](../../docs/fila/2026-08-16-postgres-2-corte.md).
Design: [`docs/referencia-viva/specs/2026-08-16-portal-control-para-postgres-design.md`](../../docs/referencia-viva/specs/2026-08-16-portal-control-para-postgres-design.md).

## A ordem é obrigatória

```
verificar  →  alembic upgrade head  →  copiar  →  validar
```

1. **`verificar.py`** — pré-voo. Acha tudo que o Postgres vai recusar e o SQLite
   deixou passar: órfão de FK, string maior que a coluna, NULL em `NOT NULL`,
   booleano fora de 0/1, decimal com mais casas que a escala. Roda contra a
   **cópia** do SQLite e contra o Postgres **já migrado e vazio**. Sai 1 se achar
   qualquer coisa.
2. **`alembic upgrade head`** de cada produto, contra o banco de destino. As
   tabelas vêm daí — **nunca** de `create_all`, nunca de DDL à mão, senão o
   schema de produção passa a divergir da cadeia de migrations em silêncio.
3. **`copiar.py`** — carga em ordem topológica de FK, lotes de 500, conversão
   dirigida pelo tipo de destino. **Recusa carregar se o destino já tiver linha**:
   carregar duas vezes duplica tudo, e depois do fato é indistinguível de dado
   legítimo.
4. **`validar.py`** — o portão. Compara os dois lados linha a linha e soma a
   soma. **Saída zero libera o corte; qualquer divergência aborta.** Enquanto
   esta lista não estiver vazia, produção continua nos `.db` e nada foi perdido.

## Nenhuma senha entra em comando

As URLs vêm das variáveis `REVY_PG_PORTAL_URL` e `REVY_PG_CONTROL_URL`,
definidas como secret do Fly no `app2037`. Elas **não são lidas por código
nenhum** — são só o cofre de onde os comandos da janela puxam a URL.

```sh
python verificar.py --origem sqlite:////data/migracao/portal-corte.db \
                    --destino "$REVY_PG_PORTAL_URL" --schema portal
```

Nunca `echo` de URL completa, nunca senha em `--destino` literal, nunca arquivo
com senha dentro da árvore do repo. `fly secrets list` mostra o **nome**; é por
ele que se confere.

## Por que as ferramentas não importam `app`

O Portal e o Control têm ambos um pacote chamado `app`, e nenhum processo pode
importar os dois. Por isso tudo aqui **reflete** o schema do banco em vez de
importar modelo: os tipos, as FKs e os `NOT NULL` de verdade vêm do banco que o
alembic acabou de criar, que é a única fonte que não mente.

O `conftest.py` na raiz desta pasta existe só para o pytest achar os módulos: no
modo de import default ele insere no `sys.path` o diretório do arquivo de teste
(`tests/`), não o pai.

## Rodar os testes

Não precisam de Postgres — a suíte monta pares SQLite→SQLite que formam as
mesmas restrições que o Postgres formaria.

Use o venv do Portal (as ferramentas não importam `app`, então não há conflito):

- macOS: `cd deploy/migracao-pg && ../../portal-gestao/.venv/bin/python -m pytest -q`
- Windows: `cd deploy/migracao-pg; ..\..\portal-gestao\.venv\Scripts\python.exe -m pytest -q`

## Dentro da imagem

O `Dockerfile.app` copia esta pasta para `/srv/migracao-pg`. A ferramenta roda de
dentro do `app2037`: o `suite-pg` só responde em flycast, os `.db` estão no
volume, e a imagem já tem `sqlalchemy`, `psycopg` e `alembic`. Nenhum dado sai do
Fly e nenhum túnel é aberto.

## O perigo que mata, em uma frase

`run-portal.sh` e `run-revy-trafego.sh` hoje exigem a URL com `${VAR:?}`. Se
alguém reintroduzir o `${VAR:-sqlite:...}`, um secret apagado ou com typo faz o
app **criar um SQLite vazio e subir saudável, com zero dado e sem erro no log**.
`tests/test_scripts_de_boot.py` existe para que o CI pare essa pessoa, e não o
dono olhando uma tela vazia.

## Cópia é sempre `sqlite3.backup`, nunca `cp`

`sqlite3.backup` dá uma cópia consistente **com o app escrevendo** — é para isso
que ele existe. E toda a carga lê do snapshot, nunca do arquivo vivo: assim, se o
Fly reiniciar a máquina no meio e o supervisord religar o Portal, a fonte da
carga não muda debaixo dos pés.
