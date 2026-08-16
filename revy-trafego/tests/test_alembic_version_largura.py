"""O id de revision tem que caber na coluna `version_num`.

Achado no ensaio de 16/08/2026, contra o Postgres de verdade. O alembic cria a
tabela de versão com `version_num VARCHAR(32)` — largura hardcoded no código
dele, sem opção de configuração. O SQLite **não impõe** largura de VARCHAR, então
revisions longas funcionaram por dois anos; o Postgres impõe, e o `upgrade head`
morre no meio, com o DDL da migration já aplicado.

O Control é o lado pior: **7 das 20 revisions** não caberiam, contra 2 de 26 no
Portal. E a tabela aqui não é `alembic_version` e sim
`alembic_version_revy_trafego` (`alembic/env.py`), então o DDL de pré-criação
tem que usar esse nome — pré-criar a tabela errada não protege nada e o erro só
aparece na janela.

A correção é pré-criar a tabela mais larga ANTES do primeiro `upgrade head`: o
alembic só cria se não existir. O DDL está em `deploy/migracao-pg/README.md`.
Este teste é o guarda-corpo do outro lado.
"""
from __future__ import annotations

import re
from pathlib import Path

# A largura que o DDL de `deploy/migracao-pg/README.md` provisiona.
LARGURA_PROVISIONADA = 255

# O Control renomeia a tabela de versão; pré-criar `alembic_version` aqui não
# serviria de nada. Ver `revy-trafego/alembic/env.py`.
TABELA_DE_VERSAO = "alembic_version_revy_trafego"

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
    assert len(_revisions()) >= 15


def test_nenhuma_revision_estoura_a_coluna_provisionada():
    estouram = [
        (nome, rev, len(rev))
        for nome, rev in _revisions()
        if len(rev) > LARGURA_PROVISIONADA
    ]
    assert not estouram, (
        f"revision maior que a coluna `version_num` de `{TABELA_DE_VERSAO}` "
        f"({LARGURA_PROVISIONADA}): {estouram}"
    )


def test_o_env_py_ainda_renomeia_a_tabela_de_versao():
    """Se isto mudar, o DDL de pré-criação passa a proteger a tabela errada."""
    env = (VERSIONS.parent / "env.py").read_text(encoding="utf-8")
    assert TABELA_DE_VERSAO in env


def test_registra_quais_revisions_nao_caberiam_no_default_do_alembic():
    grandes = sorted(rev for _, rev in _revisions() if len(rev) > 32)
    assert grandes == [
        "0004_revy_control_acessos_control",
        "0009_revy_control_provisioning_outbox",
        "0010_revy_control_google_ads_connections",
        "0011_revy_control_google_ads_metrics",
        "0012_revy_control_google_ads_conversions",
        "0013_revy_control_readiness_alert_acceptances",
        "0017_vendas_projetadas_backfill_loja_id",
    ]
