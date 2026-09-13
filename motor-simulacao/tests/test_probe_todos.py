"""montar_solicitacao repassa sexo (PROBE_SEXO, com override BRADESCO_SEXO).

Puro: nao abre browser nem gasta login no portal.
"""

import importlib.util
import sys
from pathlib import Path

import pytest


def _carregar():
    caminho = Path(__file__).resolve().parent.parent / "scripts" / "probe_todos.py"
    spec = importlib.util.spec_from_file_location("probe_todos_under_test", caminho)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["probe_todos_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def probe():
    return _carregar()


def _base_limpa(monkeypatch):
    for var in (
        "BRADESCO_SEXO",
        "PROBE_SEXO",
        "BRADESCO_CPF",
        "BRADESCO_NASC",
        "BRADESCO_CELULAR",
        "BRADESCO_PLACA",
        "BRADESCO_VALOR",
        "BRADESCO_UF",
        "BRADESCO_CATEGORIA",
        "BRADESCO_ENTRADA",
        "BRADESCO_PRAZOS",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("PROBE_CPF", "52998224725")
    monkeypatch.setenv("PROBE_NASC", "2002-12-13")
    monkeypatch.setenv("PROBE_CELULAR", "51980336365")
    monkeypatch.setenv("PROBE_PLACA", "FUV7G58")
    monkeypatch.setenv("PROBE_VALOR", "21900")
    monkeypatch.setenv("PROBE_UF", "SP")


def test_probe_sexo_vai_na_solicitacao(probe, monkeypatch):
    _base_limpa(monkeypatch)
    monkeypatch.setenv("PROBE_SEXO", "Feminino")
    sol = probe.montar_solicitacao("bradesco")
    assert sol.pessoa.sexo == "Feminino"


def test_bradesco_sexo_sobrescreve_probe(probe, monkeypatch):
    _base_limpa(monkeypatch)
    monkeypatch.setenv("PROBE_SEXO", "Feminino")
    monkeypatch.setenv("BRADESCO_SEXO", "M")
    sol = probe.montar_solicitacao("bradesco")
    assert sol.pessoa.sexo == "M"


def test_sem_sexo_vai_nulo(probe, monkeypatch):
    _base_limpa(monkeypatch)
    sol = probe.montar_solicitacao("bradesco")
    assert sol.pessoa.sexo is None


def test_carregar_env_local_nao_sobrescreve_shell(probe, monkeypatch, tmp_path):
    """Loader é fallback: shell vence arquivo; entre arquivos, o local vence."""
    arq = tmp_path / "teste.env"
    arq.write_text("K_ARQ=do_arquivo\nK_SHELL=do_arquivo\n", encoding="utf-8")
    monkeypatch.delenv("K_ARQ", raising=False)
    monkeypatch.setenv("K_SHELL", "do_shell")
    assert probe.carregar_env_local(arq) == 1
    assert probe.os.environ["K_ARQ"] == "do_arquivo"
    assert probe.os.environ["K_SHELL"] == "do_shell"


def test_carregar_env_local_ignora_comentario_fim_de_linha(
    probe, monkeypatch, tmp_path
):
    """`PROBE_VALOR=  # ex.: 21900` é vazio, não o texto do comentário."""
    arq = tmp_path / "coment.env"
    arq.write_text("K_NUM=  # ex.: 21900\nK_OK=42 # resposta\n", encoding="utf-8")
    monkeypatch.delenv("K_NUM", raising=False)
    monkeypatch.delenv("K_OK", raising=False)
    assert probe.carregar_env_local(arq) == 2
    assert probe.os.environ["K_NUM"] == ""
    assert probe.os.environ["K_OK"] == "42"
