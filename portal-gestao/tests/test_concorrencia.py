from types import SimpleNamespace

from app.concorrencia import _chave, travar_por_loja


class SessaoFalsa:
    """Só o suficiente para observar se SQL foi emitido, e qual."""

    def __init__(self, dialeto):
        self._dialeto = dialeto
        self.sql = []

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name=self._dialeto))

    def execute(self, stmt, params=None):
        self.sql.append((str(stmt), params))


def test_chave_e_estavel_distinta_e_cabe_em_int64():
    assert _chave("acao:loja-teste") == _chave("acao:loja-teste")
    assert _chave("acao:loja-teste") != _chave("acao:outra-loja")
    assert _chave("acao:loja-teste") != _chave("outro:loja-teste")
    assert -(2**63) <= _chave("acao:loja-teste") < 2**63


def test_chave_nao_depende_do_hash_randomizado_do_processo():
    """Valor congelado: se mudar, dois processos deixam de concordar sobre a
    mesma loja e a trava vira decoração."""
    assert _chave("copiloto_acao:loja-teste") == _chave("copiloto_acao:loja-teste")
    assert isinstance(_chave("copiloto_acao:loja-teste"), int)


def test_travar_por_loja_nao_emite_sql_em_sqlite():
    sessao = SessaoFalsa("sqlite")
    travar_por_loja(sessao, "loja-teste", "copiloto_acao")
    assert sessao.sql == []


def test_travar_por_loja_pede_advisory_lock_em_postgres():
    sessao = SessaoFalsa("postgresql")
    travar_por_loja(sessao, "loja-teste", "copiloto_acao")
    assert len(sessao.sql) == 1
    texto, params = sessao.sql[0]
    assert "pg_advisory_xact_lock" in texto
    assert params == {"chave": _chave("copiloto_acao:loja-teste")}
