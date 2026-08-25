"""O fallback do n8n é uma cópia do padrão Revy — e cópia sem guarda apodrece.

O nó `Gate config do agente1` carrega o prompt padrão como constante JS, para o
bot nunca ficar sem prompt quando a rota falhar (spec §9, passo 3). Isso duplica
o texto que `montar_prompt(CAMPOS_PADRAO_REVY)` produz, e as duas cópias só se
mantêm iguais se alguém conferir.

Este teste é a conferência. Ele **lê** um arquivo do `n8n/` — não importa nada
de lá, e nada de lá importa daqui: a fronteira entre produtos continua sendo a
rota HTTP. O que ele guarda é justamente o texto que serve quando essa rota
**não** responde, que é o único ponto em que os dois lados precisam concordar
sem falar entre si.

Mudou o gerador? `python -m scripts.sincronizar_fallback_n8n`, e depois regere os
três workflows derivados (fork do Modo 2, teste e preview) — o fallback viaja
para todos eles.
"""
import json
from pathlib import Path

import pytest

from app.agente_prompt import CAMPOS_PADRAO_REVY, montar_prompt

WORKFLOW = Path(__file__).resolve().parents[2] / "n8n" / "workflow-ai-nao-salvos.json"


def _fallback_do_no() -> str:
    dados = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    no = next(n for n in dados["nodes"] if n["name"] == "Gate config do agente1")
    codigo = no["parameters"]["jsCode"]
    inicio = codigo.index("const PROMPT_PADRAO_REVY = `") + len(
        "const PROMPT_PADRAO_REVY = `"
    )
    return codigo[inicio : codigo.index("`;", inicio)]


@pytest.mark.skipif(not WORKFLOW.exists(), reason="checkout sem a pasta n8n")
def test_fallback_do_n8n_e_o_padrao_revy_deste_gerador():
    assert _fallback_do_no() == montar_prompt(CAMPOS_PADRAO_REVY)
