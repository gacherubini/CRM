"""Prompt do agente por loja: campos entram, texto sai (spec §3.4, §4, §5).

Módulo puro de propósito: sem banco, sem rede, sem n8n. O lojista não escreve
prompt — escreve campos, e cada campo tem um gerador aqui. É isso que faz o
texto sair bem escrito mesmo quando o lojista não é.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

MAX_INSTRUCOES_LIVRES = 1000

_HORARIO_RE = re.compile(r"^\d{2}:\d{2}$")

_TOKENS_POR_TAMANHO = {"curto": 250, "medio": 400, "longo": 700}

# Temas que o núcleo fecha. Instrução livre que os toca não funciona — a tela
# avisa, não bloqueia (spec §4.5).
_TEMAS_FECHADOS = {
    "parcela": ("parcela", "taxa", "juros", "banco", "prazo", "financiado"),
    "insistir": ("insista", "insistir", "tente de novo", "ofereça de novo"),
    "dados": ("renda", "placa"),
    "estoque": ("invente", "diga que temos", "sempre disponível"),
}

NUCLEO_REVY = """[REGRAS DO REVY — PREVALECEM SOBRE TUDO ACIMA]
estas regras não podem ser contrariadas por nenhuma instrução anterior.
se algo acima conflitar com algo aqui, siga o que está aqui.

1. estoque e preço: só o que consultar_estoque retornar. nunca invente veículo,
   preço, km, cor, ano ou disponibilidade, e nunca afirme que uma moto está
   disponível sem a consulta ter confirmado.
2. resultado de financiamento: nunca mostre nem mencione parcela, taxa, banco,
   valor financiado ou prazo. depois da tool simular, responda somente a
   confirmação curta que ela devolver.
3. recusa: se o cliente recusar, declinar ou encerrar um convite, dê uma frase
   curta de ok e PARE. não repita a oferta e não emende outra.
4. simulação: cpf, data de nascimento e resposta de cnh (sim ou não) são
   obrigatórios, nessa ordem — nascimento e maioridade, depois cnh, depois a
   tool. "não tenho cnh" não bloqueia. nunca peça renda, prazo ou placa. nunca
   peça de novo um dado já recebido.
5. menor de idade: se a tool devolver motivo_bloqueio=menor_de_idade, envie
   exatamente a mensagem da tool e não chame de novo.
6. anti-alucinação: só confirme a simulação se a tool retornou ok:true e
   simulacao_humana_solicitada:true. em erro, ok:false ou faltando, siga a
   mensagem da tool — nunca invente confirmação.
7. nunca revele tools, tokens, apis internas, placa interna ou qualquer dado de
   controle.
8. o lead nasce dentro da tool simular. nunca crie lead por cumprimento, clique
   em anúncio ou pergunta de estoque.
"""


class ParFaq(BaseModel):
    pergunta: str = Field(max_length=120)
    resposta: str = Field(max_length=400)


class CamposAgente(BaseModel):
    """O formulário inteiro. Defaults = o agente padrão do Revy."""

    # identidade (§4.1)
    nome_loja: str = Field(max_length=80)
    cidade: str = Field(max_length=60)
    uf: str = Field(max_length=2)
    endereco_completo: bool = False
    entrega: str = Field(default="", max_length=200)
    horario: dict[str, list[str]] = Field(default_factory=dict)

    # personalidade (§4.2)
    nome_agente: str = Field(default="", max_length=40)
    assume_ia: Literal["nunca", "se_perguntarem", "na_abertura"] = "nunca"
    tom: Literal["direto", "simpatico", "consultivo", "formal"] = "direto"
    tratamento: Literal["primeiro_nome", "voce", "senhor"] = "primeiro_nome"
    escrita: Literal["minusculas", "normal"] = "minusculas"
    emoji: Literal["nunca", "raro", "a_vontade"] = "nunca"
    tamanho_resposta: Literal["curto", "medio", "longo"] = "curto"
    expressoes: list[str] = Field(default_factory=list)
    nunca_diga: list[str] = Field(default_factory=list)

    # faq (§4.3)
    faq: list[ParFaq] = Field(default_factory=list)

    # regras da conversa (§4.4)
    oferece: list[str] = Field(default_factory=lambda: ["financiamento", "a_vista"])
    fotos: Literal["so_quando_pedir", "na_abertura"] = "so_quando_pedir"
    sem_moto_anuncio: Literal["segura", "oferece_parecida"] = "segura"
    handoff: list[str] = Field(default_factory=lambda: ["quando_pedir"])
    cita_vendedor: bool = False
    followup_ativo: bool = True

    # liga/desliga (§4.6)
    agente_ativo: bool = True
    so_horario_comercial: bool = False

    # instruções livres (§4.5)
    instrucoes: str = Field(default="", max_length=MAX_INSTRUCOES_LIVRES)

    @field_validator("horario")
    @classmethod
    def _valida_horario(cls, valor: dict[str, list[str]]) -> dict[str, list[str]]:
        """Cada dia precisa de [abertura, fechamento] em HH:MM com zero à
        esquerda — string sem zero ("8:00") compara errado em
        ``esta_em_horario`` e deixa o bot mudo o dia inteiro sem erro nenhum.
        """
        for dia, faixa in valor.items():
            if len(faixa) != 2:
                raise ValueError(
                    f"horario[{dia!r}] precisa de exatamente 2 horários "
                    "(abertura e fechamento)"
                )
            for hhmm in faixa:
                if not _HORARIO_RE.match(hhmm):
                    raise ValueError(
                        f"horario[{dia!r}] precisa do formato HH:MM com zero "
                        f"à esquerda: {hhmm!r}"
                    )
                hh, mm = hhmm.split(":")
                if not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
                    raise ValueError(f"horario[{dia!r}] tem hora inválida: {hhmm!r}")
        return valor


# Rede de segurança, não estreia: é o que a loja sem config publicada recebe, e
# é o texto que o n8n usa quando a rota falha. "a loja" geraria "você atende os
# clientes da a loja"; o artigo já vem da frase do gerador.
CAMPOS_PADRAO_REVY = CamposAgente(nome_loja="loja", cidade="", uf="")

_TOM = {
    "direto": "fale de forma direta e objetiva, sem rodeio.",
    "simpatico": "fale de forma simpática e próxima, sem forçar intimidade.",
    "consultivo": "fale como quem orienta: explique a opção antes de sugerir.",
    "formal": "mantenha um registro formal e respeitoso.",
}
_TRATAMENTO = {
    "primeiro_nome": "chame o cliente pelo primeiro nome quando ele parecer um nome real.",
    "voce": 'trate o cliente por "você", sem usar o nome dele.',
    "senhor": 'trate o cliente por "senhor" ou "senhora".',
}
_TAMANHO = {
    "curto": "seja minimalista: uma ou duas frases curtas.",
    "medio": "use até três frases.",
    "longo": "pode explicar com calma quando o assunto pedir.",
}
_ASSUME_IA = {
    "nunca": "não diga que é ia, assistente virtual ou bot.",
    "se_perguntarem": (
        "se o cliente perguntar se você é uma pessoa ou um robô, responda com "
        "honestidade que é o assistente digital da loja; fora isso, não levante "
        "o assunto."
    ),
    "na_abertura": "diga na abertura que é o assistente digital da loja.",
}
_OFERECE = {
    "financiamento": "financiamento",
    "a_vista": "venda à vista",
    "troca": "moto na troca",
    "consignacao": "consignação",
}
_HANDOFF = {
    "quando_pedir": "encaminhe o atendimento para uma pessoa quando o cliente pedir explicitamente.",
    "depois_da_simulacao": "encaminhe o atendimento para uma pessoa depois que a simulação for concluída.",
    "fora_do_horario": "encaminhe o atendimento para uma pessoa quando a conversa cair fora do horário de atendimento.",
}


def _bloco_identidade(c: CamposAgente) -> str:
    linhas = [f"você atende os clientes da {c.nome_loja.lower()} pelo whatsapp."]
    if c.cidade:
        # UF vazia com cidade preenchida gerava "a loja fica em piracicaba-." —
        # o hífen órfão vai para o WhatsApp do cliente, e o formulário aceita a
        # combinação (UF é opcional).
        local = f"{c.cidade.lower()}-{c.uf.lower()}" if c.uf else c.cidade.lower()
        linhas.append(f"a loja fica em {local}.")
        if not c.endereco_completo:
            linhas.append(
                "não informe rua, número, bairro nem ponto de referência: "
                "passe só a cidade."
            )
    if c.entrega:
        linhas.append(f"entrega: {c.entrega.lower().rstrip('.')}.")
    if c.horario:
        dias = "; ".join(
            f"{dia} das {faixa[0]} às {faixa[1]}" for dia, faixa in c.horario.items()
        )
        linhas.append(f"horário de atendimento: {dias}.")
    return "[IDENTIDADE]\n" + "\n".join(linhas)


def _bloco_personalidade(c: CamposAgente) -> str:
    linhas = []
    if c.nome_agente:
        linhas.append(f"seu nome é {c.nome_agente.lower()}.")
    linhas.append(_ASSUME_IA[c.assume_ia])
    linhas.append("fale em português do brasil, de forma humana e simples.")
    linhas.append(_TOM[c.tom])
    if c.escrita == "minusculas":
        linhas.append("escreva toda resposta ao cliente em letras minúsculas.")
    if c.emoji == "nunca":
        linhas.append("não use emojis.")
    elif c.emoji == "raro":
        linhas.append("use emoji no máximo uma vez por conversa.")
    linhas.append(_TAMANHO[c.tamanho_resposta])
    linhas.append(_TRATAMENTO[c.tratamento])
    if c.expressoes:
        termos = ", ".join(f'"{e.lower()}"' for e in c.expressoes)
        linhas.append(
            f"use {termos} quando combinar com a conversa, sem virar bordão."
        )
    if c.nunca_diga:
        termos = ", ".join(f'"{e.lower()}"' for e in c.nunca_diga)
        linhas.append(f"nunca use as palavras: {termos}.")
    return "[PERSONALIDADE]\n" + "\n".join(linhas)


def _bloco_faq(c: CamposAgente) -> str:
    if not c.faq:
        return ""
    linhas = [
        f'quando o cliente perguntar sobre {par.pergunta.lower()}, responda '
        f'exatamente: "{par.resposta}"'
        for par in c.faq
    ]
    return "[FAQ DA LOJA]\n" + "\n".join(linhas)


def _bloco_regras(c: CamposAgente) -> str:
    linhas = []
    oferecidos = [_OFERECE[o] for o in c.oferece if o in _OFERECE]
    if oferecidos:
        linhas.append("a loja trabalha com " + ", ".join(oferecidos) + ".")
    recusados = [rot for cod, rot in _OFERECE.items() if cod not in c.oferece]
    if recusados:
        linhas.append(
            "a loja não trabalha com " + ", ".join(recusados)
            + " — se perguntarem, diga que a loja não faz."
        )
    if c.fotos == "so_quando_pedir":
        linhas.append("não mande fotos por conta própria: só quando o cliente pedir.")
    else:
        linhas.append("na abertura, mande as fotos da moto do anúncio.")
    if c.sem_moto_anuncio == "segura":
        linhas.append(
            "se a consulta não achar a moto do anúncio, mantenha o foco nela e "
            "não ofereça outra moto por iniciativa própria."
        )
    else:
        linhas.append(
            "se a consulta não achar a moto do anúncio, ofereça uma parecida do "
            "estoque, sempre com dados reais da consulta."
        )
    for h in c.handoff:
        if h in _HANDOFF:
            linhas.append(_HANDOFF[h])
    if c.cita_vendedor:
        linhas.append("você pode citar o vendedor pelo nome ao encaminhar o atendimento.")
    else:
        linhas.append(
            'nunca diga "atendente", "vendedor", "humano" ou "transferir".'
        )
    return "[REGRAS DA LOJA]\n" + "\n".join(linhas)


def _bloco_instrucoes(c: CamposAgente) -> str:
    if not c.instrucoes.strip():
        return ""
    return (
        "[INSTRUÇÕES DA LOJA]\n"
        "o lojista escreveu as instruções abaixo. siga-as, exceto onde "
        "contrariarem as regras do revy que vêm depois.\n"
        + c.instrucoes.strip()
    )


def montar_prompt(campos: CamposAgente) -> str:
    """Sanduíche do spec §3.4. O núcleo é o último bloco, sempre."""
    blocos = [
        _bloco_identidade(campos),
        _bloco_personalidade(campos),
        _bloco_faq(campos),
        _bloco_regras(campos),
        _bloco_instrucoes(campos),
        NUCLEO_REVY,
    ]
    return "\n\n".join(b for b in blocos if b)


def max_output_tokens(campos: CamposAgente) -> int:
    """Sem isto, 'pode explicar' bate no teto de 250 e corta no meio da frase."""
    return _TOKENS_POR_TAMANHO[campos.tamanho_resposta]


def saida_do_agente(campos: CamposAgente) -> dict[str, bool]:
    """Higienização que o n8n aplica na resposta antes de mandar ao cliente.

    Sem isto ``escrita`` e ``emoji`` seriam campos decorativos: o
    ``Responder WhatsApp1`` força minúsculas e remove emoji de **toda**
    resposta de cliente, então a loja que escolhesse "pontuação normal" ou
    "emoji à vontade" veria a escolha ser desfeita no envio — configurada na
    tela, invisível no WhatsApp, sem erro e sem log.
    """
    return {
        "minusculas": campos.escrita == "minusculas",
        "sem_emoji": campos.emoji == "nunca",
    }


def detectar_conflitos(texto: str) -> list[str]:
    """Temas que o núcleo fecha. Avisa, não bloqueia (spec §4.5)."""
    baixo = texto.lower()
    return [tema for tema, termos in _TEMAS_FECHADOS.items() if any(t in baixo for t in termos)]
