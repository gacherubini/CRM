#!/usr/bin/env python3
"""Protege o preview da config do agente (`workflow-preview.json`).

O risco nº 1 desta feature não é o preview ficar feio — é ele **agir**. As
ferramentas do agente criam lead no portal, avisam a equipe no WhatsApp, pausam o
bot de uma conversa e cadastram veículo no Estoque. Um preview sem freio faz tudo
isso quando o lojista digita um CPF numa tela para ver como o agente responde.

Então a checagem central aqui é de **alcançabilidade**: em cada ferramenta que
age, o `return` do modo seco tem de vir **antes** de toda chamada que causa
efeito. Conferir que a string "MODO SECO" existe não bastaria — ela pode estar
num comentário no fim do arquivo, depois do estrago.

**O que este arquivo NÃO cobre, e por isso existe `test_modo_seco.js`:** ordem no
texto não é o mesmo que execução. Um `return` embrulhado num `if` continua vindo
antes da chamada e passa aqui — conferido por mutação: com o freio do `simular1`
virando condicional no gerador, este validador aprova e o teste de execução
reprova. Rode os dois.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
WORKFLOW = RAIZ / "workflow-preview.json"
GERADOR = RAIZ / "build_preview_workflow.py"

MARCA_SECA = "// MODO SECO (preview)"

# Ferramenta → chamadas que causam efeito no mundo real. Todas têm de ficar
# depois do return do modo seco.
EFEITOS_POR_RETURN = {
    "simular1": [
        "/v1/simulacoes/solicitar",
        "/v1/operacao/solicitacoes-simulacao-humana",
    ],
    "TEMP continuar sem estoque1": ["/v1/operacao/solicitacoes-simulacao-humana"],
    "solicitar_handoff1": [
        "/estado",
        "/v1/operacao/numeros-autorizados",
        "/message/sendText/",
    ],
    "enviar_foto_veiculo1": ["/message/sendMedia/"],
    "cadastrar_veiculo1": ["/v1/operacao/veiculos"],
}

# `consultar_estoque1` é o caso sutil: a BUSCA roda de verdade — é ela que faz o
# teste valer — e a GRAVAÇÃO não pode rodar, porque `POST /v1/operacao/moto-escolhida`
# cria `Conversa` e o preview apareceria em Conversas com o telefone sintético.
# Aqui o freio não é um return no meio da tool: é a chamada sair do código.
EFEITOS_POR_REMOCAO = {
    "consultar_estoque1": ["/v1/operacao/moto-escolhida"],
}

# O que tem de continuar acontecendo. Sem isto, "modo seco" degenera para "tool
# que não faz nada", e aí o preview não prova coisa alguma.
EXECUTAM = {
    "consultar_estoque1": "/v1/estoque/buscar",
    "enviar_link_catalogo1": "/v1/config/catalogo-bot",
}


def main() -> None:
    dados = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    nos = dados.get("nodes", [])
    por_nome = {n.get("name"): n for n in nos}
    serializado = json.dumps(dados, ensure_ascii=False)

    # --- modo seco: o freio vem antes do efeito -----------------------------
    for tool, efeitos in EFEITOS_POR_RETURN.items():
        no = por_nome.get(tool)
        assert no is not None, f"ferramenta {tool} sumiu do preview"
        codigo = no.get("parameters", {}).get("jsCode", "")
        corte = codigo.find(MARCA_SECA)
        assert corte != -1, (
            f"{tool} está sem o freio do modo seco: o preview criaria lead, "
            "avisaria a equipe ou mexeria no estoque de verdade"
        )
        # O return tem de estar logo depois do comentário, não em qualquer lugar.
        depois = codigo[corte : corte + 600]
        assert "return JSON.stringify(" in depois, (
            f"{tool}: a marca do modo seco existe mas não há return — o código "
            "continua caindo na chamada que age"
        )
        for efeito in efeitos:
            pos = codigo.find(efeito)
            if pos == -1:
                continue
            assert pos > corte, (
                f"{tool}: {efeito} é alcançável antes do freio do modo seco"
            )

    for tool, efeitos in EFEITOS_POR_REMOCAO.items():
        no = por_nome.get(tool)
        assert no is not None, f"ferramenta {tool} sumiu do preview"
        codigo = no.get("parameters", {}).get("jsCode", "")
        for efeito in efeitos:
            assert efeito not in codigo, (
                f"{tool}: {efeito} voltou ao preview — ela cria Conversa, e a "
                "conversa de teste apareceria em Conversas"
            )

    for tool, url_viva in EXECUTAM.items():
        no = por_nome.get(tool)
        assert no is not None, f"ferramenta {tool} sumiu do preview"
        codigo = no.get("parameters", {}).get("jsCode", "")
        assert url_viva in codigo, (
            f"{tool} parou de chamar {url_viva}: sem isso o preview não roda o "
            "agente de verdade e o teste não prova nada"
        )
        corte = codigo.find(MARCA_SECA)
        if corte != -1:
            assert codigo.find(url_viva) < corte, (
                f"{tool}: {url_viva} ficou depois do freio e não roda mais"
            )

    # --- telefone: quem escolhe é o chatbot, não este arquivo ---------------
    # Telefone real no workflow seria o preview escrevendo `moto-escolhida` numa
    # conversa de verdade — o motivo do telefone sintético existir.
    telefones = re.findall(r"\b55\d{9,11}\b", serializado)
    assert not telefones, (
        f"telefone escrito à mão no preview: {sorted(set(telefones))} — o "
        "sintético vem do chatbot, no corpo do webhook"
    )

    # --- pontes de nome ------------------------------------------------------
    extrair = por_nome.get("Extrair1")
    assert extrair is not None, (
        "sem o nó-ponte `Extrair1` toda ferramenta falha: elas leem "
        "$('Extrair1').first().json para achar instance e telefone"
    )
    extrair_code = extrair.get("parameters", {}).get("jsCode", "")
    assert "MAX_MESSAGE_AGE_SECONDS" not in extrair_code, (
        "a ponte não pode replicar a trava de 300 s do Extrair1 real: ela "
        "descartaria toda mensagem de teste"
    )
    assert "if (!telefone || !instance) return []" in extrair_code, (
        "ponte deve falhar fechado sem loja: sem instance não há estoque nem prompt"
    )

    config = por_nome.get("Gate config do agente1")
    assert config is not None, "sem o gate de config o AI Agent1 fica sem prompt"
    config_code = config.get("parameters", {}).get("jsCode", "")
    assert "b.prompt" in config_code, (
        "o preview tem que usar o prompt do RASCUNHO, que vem no corpo — é a "
        "razão de ele existir (testar antes de publicar)"
    )
    assert "throw new Error" in config_code, (
        "preview sem prompt tem que falhar alto: cair no padrão mostraria ao "
        "lojista um agente que não é o dele"
    )
    for bloco in ("[IDENTIDADE]", "[PERSONALIDADE]", "[REGRAS DO REVY"):
        assert bloco not in config_code, (
            f"o gate está montando prompt ({bloco}): o texto chega pronto do "
            "chatbot, e um segundo gerador aqui diverge do primeiro na primeira "
            "mudança de campo"
        )

    # --- o preview não fala com o WhatsApp ----------------------------------
    for proibido in ("evolution:8080", "graph.facebook.com", "sendText", "sendMedia"):
        alcancavel = [
            n.get("name")
            for n in nos
            if proibido in json.dumps(n.get("parameters", {}), ensure_ascii=False)
            and n.get("name") not in EFEITOS_POR_RETURN
        ]
        assert not alcancavel, (
            f"preview fala com WhatsApp fora de ferramenta travada: {alcancavel}"
        )

    responder = por_nome.get("Responder preview")
    assert responder is not None, "a resposta precisa voltar pelo próprio webhook"
    assert responder.get("type") == "n8n-nodes-base.respondToWebhook"

    # --- o agente é o mesmo do bot real -------------------------------------
    agente = por_nome.get("AI Agent1")
    assert agente is not None, "sem AI Agent1 o preview não é preview"
    sm = agente["parameters"]["options"]["systemMessage"]
    assert sm.rstrip().endswith(
        "{{ $('Gate config do agente1').first().json.promptAgente }}"
    ), "no preview o prompt da loja deixou de ser o último bloco (o núcleo para de vencer)"
    modelo = por_nome.get("Google Gemini Chat Model1")
    assert modelo is not None and modelo["parameters"]["options"]["maxOutputTokens"] == 250, (
        "o preview tem que usar o mesmo modelo e o mesmo teto do bot real"
    )

    # --- referências órfãs ---------------------------------------------------
    nomes = set(por_nome)
    orfaos = sorted(set(re.findall(r"\$\('([^']+)'\)", serializado)) - nomes)
    assert not orfaos, f"referência a nó inexistente (recorte): {orfaos}"

    # --- o arquivo é o que o gerador produz ---------------------------------
    antes = WORKFLOW.read_bytes()
    subprocess.run(
        [sys.executable, str(GERADOR)], check=True, capture_output=True, cwd=RAIZ.parent
    )
    depois = WORKFLOW.read_bytes()
    if antes != depois:
        WORKFLOW.write_bytes(antes)
        sys.exit(
            "workflow-preview.json foi editado à mão: rode "
            "`python n8n/build_preview_workflow.py` e commite o resultado "
            "(ou ajuste o gerador)"
        )

    print(
        f"workflow-preview.json OK: {len(nos)} nós, "
        f"{len(EFEITOS_POR_RETURN) + len(EFEITOS_POR_REMOCAO)} ferramentas em modo "
        "seco com o freio antes do efeito, telefone sintético, prompt do rascunho"
    )


if __name__ == "__main__":
    main()
