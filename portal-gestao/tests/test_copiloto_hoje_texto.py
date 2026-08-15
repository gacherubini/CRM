"""Plural real e severidade que se vê."""
import re
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "app/templates/loja/copiloto_hoje.html"
CSS = Path(__file__).resolve().parents[1] / "app/static/css/app.css"


def test_template_nao_usa_plural_entre_parenteses():
    texto = TEMPLATE.read_text(encoding="utf-8")
    assert "(s)" not in texto


def test_severidade_do_sinal_tem_regra_de_css():
    """A classe existe no template desde a F4; sem regra, critico e info sao
    visualmente identicos."""
    css = CSS.read_text(encoding="utf-8")
    assert re.search(r"\.copiloto-sinal\.severidade-critico", css)
