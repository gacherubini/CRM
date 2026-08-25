"""As frases que saíram do `systemMessage` do n8n têm destino aqui (spec §7.2).

`n8n/validate_workflow.py` afirmava ~40 frases literais do prompt. As que
descrevem **comportamento genérico** (jornada, tools, anti-alucinação)
continuam lá, contra o template. As que descrevem **esta loja** viraram texto
gerado a partir dos campos — e a garantia veio junto para cá.

Assertiva sem destino é regressão silenciosa de prompt: é exatamente o que esse
validador já pegou antes. Cada teste deste arquivo é o outro lado de uma
assertiva que mudou de lugar.
"""
from app.agente_prompt import montar_prompt, saida_do_agente
from scripts.semear_config_agente import CAMPOS_VITOR_MOTOS


def _prompt_vitor() -> str:
    return montar_prompt(CAMPOS_VITOR_MOTOS).lower()


def test_apresentacao_da_loja_veio_do_campo_nome_loja():
    """Era `assert "vitor motos" in system_message_lower` no validador."""
    assert "você atende os clientes da vitor motos pelo whatsapp" in _prompt_vitor()


def test_tom_minimalista_e_expressoes_da_casa():
    """Era `assert "certinho" ... and "minimalista" ...` no validador."""
    prompt = _prompt_vitor()
    assert "minimalista" in prompt
    assert '"certinho"' in prompt and '"beleza"' in prompt


def test_minusculas_e_sem_emoji():
    """Era `assert "letras minúsculas" ... and "não use emojis" ...`."""
    prompt = _prompt_vitor()
    assert "letras minúsculas" in prompt
    assert "não use emojis" in prompt


def test_nao_diz_que_e_ia():
    """Trava aberta pelo dono (spec §2): virou campo, não sumiu."""
    assert "não diga que é ia" in _prompt_vitor()


def test_localizacao_e_so_a_cidade_mais_a_entrega():
    """A seção "localização da loja" do prompt antigo trazia limeira-sp e a
    cortesia de entrega escritas à mão no JSON."""
    prompt = _prompt_vitor()
    assert "a loja fica em limeira-sp" in prompt
    assert "não informe rua, número, bairro nem ponto de referência" in prompt
    assert "cortesia para todo o estado de são paulo" in prompt


def test_linguagem_proibida_com_o_cliente():
    """A seção "linguagem proibida" virou o campo `cita_vendedor` (spec §2)."""
    prompt = _prompt_vitor()
    assert '"atendente"' in prompt and '"vendedor"' in prompt
    assert '"transferir"' in prompt


def test_trata_o_cliente_pelo_primeiro_nome():
    assert "chame o cliente pelo primeiro nome" in _prompt_vitor()


def test_nao_manda_foto_por_conta_propria():
    """Vinha da seção de anúncio: "não mande foto automaticamente"."""
    assert "não mande fotos por conta própria" in _prompt_vitor()


def test_segura_a_moto_do_anuncio():
    assert "mantenha o foco nela" in _prompt_vitor()


def test_higienizacao_da_saida_acompanha_a_escolha_da_loja():
    """O `Responder WhatsApp1` higieniza a resposta. Se ele higienizasse igual
    para todo mundo, `escrita` e `emoji` seriam campos decorativos — o lojista
    escolheria "pontuação normal" e o WhatsApp continuaria em minúsculas."""
    assert saida_do_agente(CAMPOS_VITOR_MOTOS) == {
        "minusculas": True,
        "sem_emoji": True,
    }
    solto = CAMPOS_VITOR_MOTOS.model_copy(
        update={"escrita": "normal", "emoji": "a_vontade"}
    )
    assert saida_do_agente(solto) == {"minusculas": False, "sem_emoji": False}


def test_config_da_vitor_motos_nao_promete_consignacao():
    """O prompt de hoje não fala em consignação; o gerador lista o que a loja
    não faz, e uma promessa a mais aqui é uma promessa a mais no WhatsApp."""
    prompt = _prompt_vitor()
    assert "a loja não trabalha com consignação" in prompt
    assert "a loja trabalha com financiamento, venda à vista, moto na troca." in prompt
