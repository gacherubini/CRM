#!/usr/bin/env python3
"""Valida invariantes do workflow Cloud (Modo 2). Roda da raiz do repo.

A versão anterior deste arquivo cravava o formato de **4 nós** — inbound e
verificação repassados ao chatbot e mais nada. Ela passava, e passava justamente
porque descrevia o produto errado: a spec §5.9 pede *cópia do fluxo atual*, com
IA, debounce e ferramentas, e o que existia era um transporte. Um validador que
sanciona o stub é pior que nenhum, porque dá aval.

Agora ele afere o que a spec pede de fato.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
WORKFLOW = RAIZ / "workflow-cloud.json"
GERADOR = RAIZ / "fork_cloud_workflow.py"
CHATBOT = "http://chatbot-api:8000"

# §6.2: um workflow serve N lojas, então cada chamada carrega a instância
# (o `phone_number_id`, que o Extrair1 já publica). `config/catalogo-bot` não
# está aqui: ela é cega para loja por outro motivo — o contrato com o Estoque.
ROTAS_QUE_EXIGEM_INSTANCE = (
    "/v1/operacao/responder",
    "/v1/operacao/handoff-humano",
    "/v1/operacao/moto-escolhida",
    "/v1/operacao/solicitacoes-simulacao-humana",
    "/v1/simulacoes/solicitar",
    "/v1/estoque/buscar",
)

# Quantos caracteres depois da URL ainda contam como "o corpo desta chamada".
# Folgado de proposito: erra para o lado de reprovar, que e o lado barato.
JANELA_CORPO = 400

# §5.9: herdados "sem discutir de novo" do Modo 1.
FERRAMENTAS_ESPERADAS = {
    "consultar_estoque1",
    "simular1",
    "solicitar_handoff1",
    "TEMP continuar sem estoque1",
    "enviar_link_catalogo1",
}


def main() -> None:
    dados = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    serializado = json.dumps(dados, ensure_ascii=False)
    nos = dados.get("nodes", [])
    por_tipo: dict[str, list] = {}
    for n in nos:
        por_tipo.setdefault(n.get("type", ""), []).append(n)

    # --- segredos ------------------------------------------------------------
    # §6.2: o segredo da Meta mora no chatbot. Nem o App Secret nem o token do
    # Graph podem transitar por aqui — é o que permite versionar este arquivo.
    for proibido in ("META_APP_SECRET", "META_VERIFY_TOKEN", "GRAPH_TOKEN", "EAA"):
        assert proibido not in serializado, f"workflow contém segredo da Meta: {proibido}"

    # Sobra de Evolution significa fork malfeito: o Modo 2 não tem Evolution.
    for sobra in ("evolution:8080", "__EVOLUTION_KEY__", "evolution2037"):
        assert sobra not in serializado, f"resíduo do Modo 1 no workflow cloud: {sobra}"

    # --- webhooks da Meta (§6.1) --------------------------------------------
    webhooks = por_tipo.get("n8n-nodes-base.webhook", [])
    metodos = {n["parameters"].get("httpMethod") for n in webhooks}
    assert metodos == {"GET", "POST"}, "faltam os dois webhooks (GET verificação, POST inbound)"

    post = next(n for n in webhooks if n["parameters"].get("httpMethod") == "POST")
    assert post["parameters"].get("options", {}).get("rawBody") is True, (
        "webhook POST sem rawBody: o corpo reserializado invalida a assinatura da Meta"
    )
    assert post["parameters"].get("responseMode") == "onReceived", (
        "webhook POST tem que responder 200 na hora, senão a Meta reentrega"
    )

    # Capturar o corpo cru não basta — o nó que repassa tem de mandar os **bytes**.
    # `$json.body` é o corpo já parseado, e o `JSON.stringify` do n8n não escapa
    # barra; a Meta assina o que o `json_encode` do PHP produz, que escapa
    # (`"audio\/ogg"`). Toda mídia carrega `mime_type` e a URL do lookaside, então
    # mídia dava 401 sempre — e calada, porque `registrar_evento_falho` só roda
    # depois da assinatura passar e o repasse tem `neverError`.
    # Ancorado na conexão, não na URL: o repasse da verificação (GET) aponta para
    # a mesma rota e casaria primeiro numa busca por URL.
    destinos = dados["connections"][post["name"]]["main"][0]
    repasse = next(n for n in nos if n["name"] == destinos[0]["node"])["parameters"]
    assert "$json.body" not in json.dumps(repasse, ensure_ascii=False), (
        "o repasse manda o corpo parseado: o n8n re-serializa e a assinatura da "
        "Meta não bate para nada que tenha barra (toda mídia)"
    )
    assert repasse.get("contentType") == "binaryData", (
        "o repasse tem que mandar o binário do webhook, não JSON remontado"
    )
    assert repasse.get("inputDataFieldName") == "data", (
        "o corpo cru do webhook chega em `binary.data`; é esse campo que viaja"
    )

    get = next(n for n in webhooks if n["parameters"].get("httpMethod") == "GET")
    # `lastNode` devolveria {"data":"<challenge>"}: a Meta compara o corpo
    # inteiro e reprova. O challenge tem que voltar cru, em texto.
    assert get["parameters"].get("responseMode") == "responseNode", (
        "webhook GET com lastNode envelopa o challenge em JSON e a Meta reprova"
    )
    respostas = por_tipo.get("n8n-nodes-base.respondToWebhook", [])
    assert respostas, "sem nó de resposta: o challenge da Meta não volta em texto puro"
    resposta = respostas[0]
    assert resposta["parameters"].get("respondWith") == "text", (
        "resposta da verificação tem que ser texto puro, não JSON"
    )
    assert "$json.data" in resposta["parameters"].get("responseBody", ""), (
        "a resposta tem que ecoar o corpo que o chatbot devolveu (challenge)"
    )

    # --- o bot existe (§5.9) -------------------------------------------------
    # O buraco que passou batido: sem estas quatro asserções, um transporte de
    # 4 nós é aprovado como se fosse o bot.
    assert por_tipo.get("@n8n/n8n-nodes-langchain.agent"), (
        "sem AI Agent: a §5.9 pede cópia do fluxo atual, não um repassador"
    )
    assert por_tipo.get("@n8n/n8n-nodes-langchain.lmChatGoogleGemini"), (
        "sem modelo de linguagem: o agente não responde nada"
    )
    assert por_tipo.get("@n8n/n8n-nodes-langchain.memoryBufferWindow"), (
        "sem memória de conversa: o bot esquece o cliente a cada mensagem"
    )

    ferramentas = {n["name"] for n in por_tipo.get("@n8n/n8n-nodes-langchain.toolCode", [])}
    faltando = FERRAMENTAS_ESPERADAS - ferramentas
    assert not faltando, f"ferramentas do agente que a §5.9 herda estão faltando: {sorted(faltando)}"

    # solicitar_handoff é o elo que abre o rodízio (§5.2). Se ele não chamar o
    # gatilho, o bot atende e nenhum vendedor é chamado, nunca.
    handoff = next(n for n in nos if n["name"] == "solicitar_handoff1")
    assert "/v1/operacao/handoff-humano" in handoff["parameters"].get("jsCode", ""), (
        "solicitar_handoff não aciona o rodízio: o lead morreria atendido e sem vendedor"
    )

    # --- debounce herdado (§5.9) --------------------------------------------
    espera = por_tipo.get("n8n-nodes-base.wait", [])
    assert espera, "sem debounce: a §5.9 herda os 40s de espera pela última mensagem"
    assert any(
        str(n["parameters"].get("amount")) == "40" for n in espera
    ), "o debounce não é de 40s"

    # --- tudo fala com o chatbot, nada fala com a Meta (§6.2) ---------------
    # A URL pode ser expressão do n8n (`={{ '...' + telefone }}`), então a
    # asserção é sobre o host que aparece nela, não sobre o começo da string.
    for n in por_tipo.get("n8n-nodes-base.httpRequest", []):
        url = str(n["parameters"].get("url", ""))
        assert CHATBOT in url, (
            f"{n['name']} não fala com o chatbot ({url}): no Modo 2 quem fala com "
            "a Meta é o chatbot, senão o token do Graph teria que morar aqui"
        )
        for host_proibido in ("graph.facebook.com", "evolution"):
            assert host_proibido not in url, (
                f"{n['name']} fala direto com {host_proibido} — §6.2 põe esse "
                "segredo no chatbot"
            )

    # --- toda chamada ao chatbot diz de qual loja fala (§6.2) ---------------
    # Sem isto o workflow volta a servir uma loja só — e o sintoma é silêncio,
    # não erro: o chatbot procura a conversa na loja errada e o agente para.
    # `catalogo-bot` fica de fora de propósito: ela não lê loja nenhuma, e
    # mandar `instance` ali só fingiria conserto (ver o card, Fora de escopo).
    # Nó HTTP Request tem UMA url, então a pergunta é do nó inteiro. Nó de
    # código faz várias chamadas — `solicitar_handoff1` manda `instance` no
    # PATCH /estado e é o POST seguinte que falta — então ali a busca é por
    # ocorrência, dentro de uma janela a partir da url.
    sem_instance = []
    for n in nos:
        parametros = json.dumps(n.get("parameters") or {}, ensure_ascii=False)
        e_codigo = "jsCode" in (n.get("parameters") or {})
        for rota in ROTAS_QUE_EXIGEM_INSTANCE:
            if rota not in parametros:
                continue
            if not e_codigo:
                if "instance" not in parametros:
                    sem_instance.append(f"{n.get('name', '?')} → {rota}")
                continue
            inicio = 0
            while (achado := parametros.find(rota, inicio)) != -1:
                inicio = achado + len(rota)
                if "instance" not in parametros[achado : achado + JANELA_CORPO]:
                    sem_instance.append(f"{n.get('name', '?')} → {rota}")
    assert not sem_instance, (
        f"chamada ao chatbot sem `instance`: {sorted(sem_instance)} — com N lojas "
        "no Modo 2 isso procura a conversa na loja errada e o bot cala"
    )

    # --- referências órfãs ---------------------------------------------------
    nomes = {n["name"] for n in nos}
    orfaos = sorted(set(re.findall(r"\$\('([^']+)'\)", serializado)) - nomes)
    assert not orfaos, f"referência a nó inexistente (fork por recorte): {orfaos}"

    # --- o arquivo é o que o gerador produz ---------------------------------
    # Sem isto o fork some por edição manual e volta a divergir do Modo 1.
    antes = WORKFLOW.read_bytes()
    subprocess.run(
        [sys.executable, str(GERADOR)], check=True, capture_output=True, cwd=RAIZ.parent
    )
    depois = WORKFLOW.read_bytes()
    if antes != depois:
        WORKFLOW.write_bytes(antes)
        sys.exit(
            "workflow-cloud.json foi editado à mão: rode `python n8n/fork_cloud_workflow.py` "
            "e commite o resultado (ou ajuste o gerador)"
        )

    print(
        f"workflow-cloud.json OK: {len(nos)} nós, agente com {len(ferramentas)} ferramentas, "
        "debounce 40s, assinatura no corpo cru, sem segredo da Meta"
    )


if __name__ == "__main__":
    main()
