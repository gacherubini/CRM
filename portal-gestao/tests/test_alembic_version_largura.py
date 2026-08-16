"""O id de revision tem que caber na coluna `alembic_version.version_num`.

Achado no ensaio de 16/08/2026, contra o Postgres de verdade: o alembic cria
`alembic_version` com `version_num VARCHAR(32)` — largura hardcoded no código
dele, sem opção de configuração. O SQLite **não impõe** largura de VARCHAR, então
uma revision de 33+ caracteres funcionou por dois anos; o Postgres impõe, e o
`upgrade head` morre no meio com:

    DataError: value too long for type character varying(32)
    [SQL: UPDATE alembic_version SET version_num='0004_cria_atendimento_atribuicoes']

O DDL da migration já tinha sido aplicado quando isso estoura, então o banco fica
num estado meio-migrado — na janela de corte isso custaria a janela.

A correção é pré-criar `alembic_version` mais larga ANTES do primeiro
`upgrade head`: o alembic só cria a tabela se ela não existir, então ele adota a
nossa. `deploy/migracao-pg/README.md` traz o DDL, e ele é passo obrigatório da
criação do banco.

Este teste é o guarda-corpo do outro lado: se alguém criar uma revision mais
longa que a coluna provisionada, o CI para aqui em vez de a janela parar.
"""
from __future__ import annotations

import re
from pathlib import Path

# A largura que o DDL de `deploy/migracao-pg/README.md` provisiona.
# Mudar aqui sem mudar lá reintroduz o bug, com o agravante de o teste mentir.
LARGURA_PROVISIONADA = 255

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_REVISION = re.compile(r'^revision(?::\s*str)?\s*=\s*["\']([^"\']+)["\']', re.M)


def _revisions() -> list[tuple[str, str]]:
    achadas = []
    for arquivo in sorted(VERSIONS.glob("*.py")):
        encontrado = _REVISION.search(arquivo.read_text(encoding="utf-8"))
        if encontrado:
            achadas.append((arquivo.name, encontrado.group(1)))
    return achadas


def test_existe_migration_para_conferir():
    """Se o glob parar de achar arquivo, o teste abaixo passa sem testar nada."""
    assert len(_revisions()) >= 20


def test_nenhuma_revision_estoura_a_coluna_provisionada():
    estouram = [
        (nome, rev, len(rev))
        for nome, rev in _revisions()
        if len(rev) > LARGURA_PROVISIONADA
    ]
    assert not estouram, (
        "revision maior que a coluna `version_num` provisionada "
        f"({LARGURA_PROVISIONADA}): {estouram}"
    )


def test_registra_quais_revisions_nao_caberiam_no_default_do_alembic():
    """Documenta o tamanho do buraco, e falha se alguém 'consertar' errado.

    Estas revisions NÃO cabem no `VARCHAR(32)` que o alembic cria sozinho. Se
    esta lista ficar vazia um dia, o pré-criar deixou de ser necessário — mas
    não remova o DDL sem conferir o outro produto, que tem mais casos.
    """
    grandes = sorted(rev for _, rev in _revisions() if len(rev) > 32)
    assert grandes == [
        "0004_cria_atendimento_atribuicoes",
        "0022_copiloto_acao_pendente_e_estado_anterior",
    ]
