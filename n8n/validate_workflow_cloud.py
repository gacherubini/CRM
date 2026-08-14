#!/usr/bin/env python3
"""Valida invariantes do workflow Cloud (Modo 2). Roda da raiz do repo."""

from __future__ import annotations

import json
from pathlib import Path

WORKFLOW = Path(__file__).with_name("workflow-cloud.json")
DESTINO = "http://chatbot-api:8000/webhook/cloud"


def main() -> None:
    dados = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    serializado = json.dumps(dados, ensure_ascii=False)
    nos = dados.get("nodes", [])

    # Segredo da Meta nunca entra no workflow: mora no chatbot (decisão do
    # card 3). Placeholder do webhook token é o único aceito.
    for proibido in ("META_APP_SECRET", "META_VERIFY_TOKEN", "GRAPH_TOKEN", "EAA"):
        assert proibido not in serializado, f"workflow contém segredo da Meta: {proibido}"

    webhooks = [n for n in nos if n.get("type") == "n8n-nodes-base.webhook"]
    metodos = {n["parameters"].get("httpMethod") for n in webhooks}
    assert metodos == {"GET", "POST"}, "faltam os dois webhooks (GET verificação, POST inbound)"

    post = next(n for n in webhooks if n["parameters"].get("httpMethod") == "POST")
    assert post["parameters"].get("options", {}).get("rawBody") is True, (
        "webhook POST sem rawBody: o corpo reserializado invalida a assinatura da Meta"
    )
    assert post["parameters"].get("responseMode") == "onReceived", (
        "webhook POST tem que responder 200 na hora, senão a Meta reentrega"
    )

    get = next(n for n in webhooks if n["parameters"].get("httpMethod") == "GET")
    assert get["parameters"].get("responseMode") == "lastNode", (
        "webhook GET precisa devolver o challenge do chatbot"
    )

    http = [n for n in nos if n.get("type") == "n8n-nodes-base.httpRequest"]
    assert http, "nenhum HTTP Request: o workflow não encaminha nada"
    assert all(n["parameters"].get("url") == DESTINO for n in http), (
        f"todo encaminhamento tem que ir para {DESTINO}"
    )

    encaminhador = next(n for n in http if n["parameters"].get("method") == "POST")
    cabecalhos = {
        p["name"]
        for p in encaminhador["parameters"]["headerParameters"]["parameters"]
    }
    assert "X-Hub-Signature-256" in cabecalhos, (
        "assinatura não é repassada: o chatbot não tem como validar"
    )
    assert "__CHATBOT_WEBHOOK_TOKEN__" in serializado, (
        "webhook token tem que ser placeholder, substituído na publicação"
    )
    assert dados.get("active") is not True, (
        "workflow versionado não nasce ativo; ativar é pelo Publish na UI"
    )

    print("workflow-cloud.json OK")


if __name__ == "__main__":
    main()
