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


def test_revy_trafego_nao_reintroduz_a_url_do_portal():
    """O que este teste prova, exatamente: `run-revy-trafego.sh` não menciona
    `PORTAL_DATABASE_URL`. Nada além disso.

    O que ele **não** prova: que o processo do Control roda sem a variável. O
    `entrypoint-app.sh` a exporta no processo pai do supervisord (ele precisa
    dela para o `alembic upgrade head` do Portal), e o ambiente exportado é
    herdado por todo filho — o shell do Control inclusive. Um `os.environ` do
    Control ainda enxerga a URL do Portal hoje.

    A garantia real, portanto, é de superfície: `revy-trafego/app` não lê a
    variável, e este teste para quem tentar reintroduzi-la aqui por conta
    própria. Se algum dia o Control precisar de verdade de isolamento de
    ambiente, o lugar do conserto é o `entrypoint-app.sh` (rodar o alembic com
    a variável no escopo do comando em vez de exportá-la), não este arquivo.
    """
    texto = (SCRIPTS / "run-revy-trafego.sh").read_text(encoding="utf-8")
    assert "PORTAL_DATABASE_URL" not in texto
