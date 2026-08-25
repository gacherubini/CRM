#!/usr/bin/env python3
"""Reescreve o prompt padrão dentro do nó `Gate config do agente1` do n8n.

O nó carrega `montar_prompt(CAMPOS_PADRAO_REVY)` como constante JS, para o bot
nunca ficar sem prompt quando `GET /v1/agente/config` falhar. Isso duplica texto
que este produto gera, e cópia sem sincronizador apodrece — `tests/
test_agente_prompt_fallback_do_n8n.py` reprova a divergência e manda rodar isto.

    cd chatbot-api
    .venv/bin/python -m scripts.sincronizar_fallback_n8n          # macOS
    .\\.venv\\Scripts\\python.exe -m scripts.sincronizar_fallback_n8n

Depois: `python n8n/fork_cloud_workflow.py`, `node n8n/build_test_workflow.js`,
`python n8n/build_preview_workflow.py` e os validadores — o fallback viaja para
os três workflows gerados.

Não é import entre produtos: é edição de um arquivo de dados versionado, no
único ponto em que os dois lados precisam concordar sem falar entre si (que é
justamente quando a rota não responde).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from app.agente_prompt import CAMPOS_PADRAO_REVY, montar_prompt

WORKFLOW = Path(__file__).resolve().parents[2] / "n8n" / "workflow-ai-nao-salvos.json"
ABERTURA = "const PROMPT_PADRAO_REVY = `"


def main() -> int:
    if not WORKFLOW.exists():
        print(f"não achei {WORKFLOW}", file=sys.stderr)
        return 1
    dados = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    no = next(
        (n for n in dados["nodes"] if n["name"] == "Gate config do agente1"), None
    )
    if no is None:
        print("nó `Gate config do agente1` não existe no workflow", file=sys.stderr)
        return 1

    codigo = no["parameters"]["jsCode"]
    inicio = codigo.find(ABERTURA)
    if inicio == -1:
        print("constante PROMPT_PADRAO_REVY não encontrada no nó", file=sys.stderr)
        return 1
    inicio += len(ABERTURA)
    fim = codigo.index("`;", inicio)

    novo = montar_prompt(CAMPOS_PADRAO_REVY)
    if "`" in novo or "${" in novo:
        # O fallback mora dentro de uma template string JS: crase ou `${` no
        # texto gerado quebrariam o nó em runtime, e o sintoma seria o bot mudo.
        print("prompt padrão tem crase ou ${ e não cabe no template JS", file=sys.stderr)
        return 1
    if codigo[inicio:fim] == novo:
        print("fallback já está em dia")
        return 0

    no["parameters"]["jsCode"] = codigo[:inicio] + novo + codigo[fim:]
    WORKFLOW.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\r\n",
    )
    print("fallback do n8n atualizado — regere o fork, o teste e o preview")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
