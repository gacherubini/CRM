"""Snapshot do gerador em sete combinações, incluindo as feias (spec §10).

Os outros testes afirmam frases uma a uma; este guarda o **texto inteiro**. É a
diferença entre "a frase X está lá" e "o prompt continua sendo este" — e é a
única forma de perceber que um campo novo entrou no meio de um bloco, que uma
linha virou órfã, ou que uma combinação improvável passou a gerar contradição.

As feias são de propósito: formal + minúsculas (registro formal escrito em caixa
baixa), emoji à vontade + tom direto (dois eixos que puxam para lados opostos),
loja de um produto só e loja sem cidade. Se o texto dessas ficar estranho, o
lugar de descobrir é aqui, não no WhatsApp de um cliente.

Mudou o gerador de propósito? confira o diff linha a linha e regenere:

    .venv/bin/python -m tests.test_agente_prompt_snapshot          # macOS
    .\\.venv\\Scripts\\python.exe -m tests.test_agente_prompt_snapshot
"""
from pathlib import Path

import pytest

from app.agente_prompt import CamposAgente, montar_prompt

GOLDEN = Path(__file__).with_name("snapshots") / "agente_prompt.txt"

CASOS: dict[str, CamposAgente] = {
    "padrao-simples": CamposAgente(nome_loja="Motos do Léo", cidade="Piracicaba", uf="SP"),
    "feia-formal-em-minusculas": CamposAgente(
        nome_loja="Auto Center Silva",
        cidade="Campinas",
        uf="SP",
        tom="formal",
        tratamento="senhor",
        escrita="minusculas",
        tamanho_resposta="longo",
    ),
    "feia-emoji-a-vontade-e-tom-direto": CamposAgente(
        nome_loja="Zé Motos",
        cidade="Sorocaba",
        uf="SP",
        tom="direto",
        escrita="normal",
        emoji="a_vontade",
        nome_agente="Zé",
        assume_ia="na_abertura",
        expressoes=["fechou", "bora"],
        nunca_diga=["parceiro"],
    ),
    "loja-de-um-produto-so": CamposAgente(
        nome_loja="Só Consignação",
        cidade="Jundiaí",
        uf="SP",
        oferece=["consignacao"],
        handoff=[],
        cita_vendedor=True,
    ),
    "endereco-liberado-e-vazio": CamposAgente(
        # Marcar "pode passar o endereço" sem preencher o campo não pode desligar
        # a trava: sem dado, o agente inventaria rua e número.
        nome_loja="Motos do Léo",
        cidade="Piracicaba",
        uf="SP",
        endereco_completo=True,
        endereco="",
    ),
    "loja-sem-cidade-com-grade-cheia": CamposAgente(
        nome_loja="Moto Web",
        cidade="",
        uf="",
        entrega="entregamos em todo o brasil",
        horario={"seg": ["08:00", "18:00"], "sab": ["08:00", "12:00"]},
        so_horario_comercial=True,
    ),
    "completa-com-faq-e-instrucoes": CamposAgente(
        nome_loja="Motos do Léo",
        cidade="Piracicaba",
        uf="SP",
        endereco_completo=True,
        endereco="Rua das Flores, 120 — Centro",
        entrega="cortesia no estado de são paulo",
        faq=[
            {"pergunta": "garantia", "resposta": "3 meses de motor e câmbio"},
            {"pergunta": "aceita cartão", "resposta": "sim, em até 12x"},
        ],
        oferece=["financiamento", "a_vista", "troca", "consignacao"],
        fotos="na_abertura",
        sem_moto_anuncio="oferece_parecida",
        handoff=["quando_pedir", "depois_da_simulacao", "fora_do_horario"],
        instrucoes="não financiamos quem tem cnh suspensa.\naos sábados só com hora marcada.",
    ),
}


def _render() -> str:
    partes = []
    for nome, campos in CASOS.items():
        partes.append(f"===== {nome} =====\n{montar_prompt(campos)}")
    return "\n\n".join(partes) + "\n"


def test_prompt_gerado_nao_mudou_sem_querer():
    if not GOLDEN.exists():
        pytest.fail(
            f"{GOLDEN.name} não existe. Gere com "
            "`python -m tests.test_agente_prompt_snapshot`."
        )
    assert _render() == GOLDEN.read_text(encoding="utf-8"), (
        "o texto gerado mudou. Confira o diff: se foi de propósito, regenere com "
        "`python -m tests.test_agente_prompt_snapshot`"
    )


def test_o_nucleo_fecha_todos_os_casos():
    """Vale para toda combinação, inclusive as que geram bloco vazio."""
    for nome, campos in CASOS.items():
        prompt = montar_prompt(campos).rstrip()
        corte = prompt.index("[REGRAS DO REVY")
        assert "[" not in prompt[corte + 1 :].replace("[REGRAS DO REVY", ""), (
            f"{nome}: há bloco depois do núcleo — ele para de prevalecer"
        )


if __name__ == "__main__":  # pragma: no cover
    GOLDEN.parent.mkdir(exist_ok=True)
    GOLDEN.write_text(_render(), encoding="utf-8")
    print(f"snapshot regravado: {GOLDEN}")
