"""Regressão: nenhum script de boot pode inventar um SQLite quando a URL some.

Depois do corte, um secret apagado ou com typo faria o app criar um banco vazio
e subir saudável, com zero dado e sem erro no log. Este teste existe para que
alguém que reintroduza o `:-sqlite:` seja parado pelo CI, não pelo dono olhando
uma tela vazia.
"""
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
SCRIPTS = RAIZ / "deploy" / "fly" / "3vm"

VARIAVEIS = {
    "run-portal.sh": ["PORTAL_DATABASE_URL"],
    "run-revy-trafego.sh": ["REVY_TRAFEGO_DATABASE_URL"],
    "entrypoint-app.sh": ["PORTAL_DATABASE_URL", "REVY_TRAFEGO_DATABASE_URL"],
}


@pytest.mark.parametrize("arquivo", sorted(VARIAVEIS))
def test_nenhum_script_cai_para_sqlite(arquivo):
    texto = (SCRIPTS / arquivo).read_text(encoding="utf-8")
    for variavel in VARIAVEIS[arquivo]:
        assert f"{variavel}:-sqlite" not in texto, (
            f"{arquivo} ainda cai para SQLite se {variavel} sumir"
        )
        assert f"${{{variavel}:?" in texto, (
            f"{arquivo} precisa exigir {variavel} com ${{VAR:?mensagem}}"
        )


def test_revy_trafego_nao_exporta_a_url_do_portal():
    """`PORTAL_DATABASE_URL` não é lida por nenhum arquivo de revy-trafego/app.
    O export era morto — e depois do corte vira arma carregada: bastaria alguém
    passar a ler a variável para existir um segundo escritor no banco do Portal.
    """
    texto = (SCRIPTS / "run-revy-trafego.sh").read_text(encoding="utf-8")
    assert "PORTAL_DATABASE_URL" not in texto
