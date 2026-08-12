from datetime import date
from decimal import Decimal

from app.loja.copiloto.consultas_estoque import (
    RESSALVA_IDADE,
    EstoqueParado,
    VeiculoParado,
)
from app.loja.copiloto.consultas_leads import LeadsStatus
from app.loja.copiloto.consultas_origem import OrigemPeriodo, OrigemVenda
from app.loja.copiloto.consultas_vendas import VendasResumo
from app.loja.copiloto.periodo import Janela, janela_do_periodo
from app.loja.copiloto.sinais import (
    regra_atribuicao_baixa,
    regra_cadastro_incompleto,
    regra_estoque_parado,
    regra_lead_sem_resposta,
    regra_margem_incompleta,
    regra_meta_em_risco,
    regra_preco_fora_da_faixa,
)
from app.loja.copiloto.tipos import Cobertura
from app.loja.estoque_overview import EstoqueOverview, LacunaCadastro

JANELA = janela_do_periodo("2026-08-01", "2026-08-31")


def _parado(itens):
    return EstoqueParado(
        status="ok" if itens else "vazio",
        dias_min=60,
        itens=tuple(itens),
        total=len(itens),
        capital_preso=sum((i.preco or Decimal("0") for i in itens), Decimal("0")),
        cobertura_data=Cobertura(com_dado=len(itens), total=len(itens)),
        ressalva=RESSALVA_IDADE,
    )


def _veiculo(id_, dias, preco):
    return VeiculoParado(
        id=id_,
        descricao=f"Honda CB 500F {id_}",
        placa="ABC1D23",
        preco=Decimal(str(preco)),
        dias_parado=dias,
        status="disponivel",
    )


def _vendas(qtd, com_custo):
    return VendasResumo(
        status="parcial" if com_custo < qtd else "ok",
        janela=JANELA,
        janela_comparacao=JANELA,
        qtd_vendas=qtd,
        receita=Decimal("100000.00"),
        ticket_medio=Decimal("10000.00"),
        margem=Decimal("9000.00"),
        cobertura_margem=Cobertura(com_dado=com_custo, total=qtd),
        qtd_vendas_anterior=0,
        receita_anterior=Decimal("0.00"),
        ticket_medio_anterior=None,
        delta_qtd=qtd,
        delta_receita_pct=None,
        delta_ticket_pct=None,
    )


def test_estoque_parado_gera_um_sinal_por_veiculo():
    sinais = regra_estoque_parado(_parado([_veiculo("v1", 70, 25000), _veiculo("v2", 95, 13400)]))
    assert [s.entidade_ref for s in sinais] == ["v1", "v2"]
    assert all(s.regra == "estoque_parado" for s in sinais)
    assert sinais[0].acao_sugerida["acao"] == "ajustar_preco"
    assert sinais[0].acao_sugerida["veiculo_id"] == "v1"


def test_estoque_parado_escala_severidade_com_o_tempo():
    sinais = regra_estoque_parado(_parado([_veiculo("v1", 65, 25000), _veiculo("v2", 130, 25000)]))
    por_id = {s.entidade_ref: s for s in sinais}
    assert por_id["v1"].severidade == "atencao"
    assert por_id["v2"].severidade == "critico"


def test_estoque_sem_parado_nao_gera_sinal():
    assert regra_estoque_parado(_parado([])) == []


def test_lead_sem_resposta_dispara_e_e_agregado_sem_telefone():
    leads = LeadsStatus(
        status="ok",
        total_leads=10,
        taxa_resposta_pct="80.0",
        tempo_mediano_primeira_resposta_segundos=300,
        sem_resposta=2,
        sem_resposta_status="ok",
        horas_sem_resposta=4,
    )
    sinais = regra_lead_sem_resposta(leads)
    assert len(sinais) == 1
    assert sinais[0].entidade_ref is None
    assert "2" in sinais[0].titulo
    assert sinais[0].acao_sugerida["href"] == "/app/loja/atendimento"


def test_lead_sem_resposta_indisponivel_nao_dispara():
    leads = LeadsStatus(
        status="parcial",
        total_leads=None,
        taxa_resposta_pct=None,
        tempo_mediano_primeira_resposta_segundos=None,
        sem_resposta=None,
        sem_resposta_status="indisponivel",
        horas_sem_resposta=4,
    )
    assert regra_lead_sem_resposta(leads) == []


def test_meta_em_risco_quando_o_ritmo_nao_alcanca():
    metas = [
        {
            "tipo": "faturamento",
            "alvo": Decimal("200000"),
            "realizado": Decimal("50000"),
            "pct": 25.0,
            "indisponivel": False,
        }
    ]
    sinais = regra_meta_em_risco(metas, JANELA, hoje=date(2026, 8, 25))
    assert len(sinais) == 1
    assert sinais[0].regra == "meta_em_risco"
    assert sinais[0].dados["falta"] == "150000.00"
    assert sinais[0].dados["dias_restantes"] == 7


def test_meta_no_ritmo_nao_dispara():
    metas = [
        {
            "tipo": "faturamento",
            "alvo": Decimal("200000"),
            "realizado": Decimal("180000"),
            "pct": 90.0,
            "indisponivel": False,
        }
    ]
    assert regra_meta_em_risco(metas, JANELA, hoje=date(2026, 8, 25)) == []


def test_meta_indisponivel_nao_dispara():
    metas = [
        {
            "tipo": "lucro_bruto",
            "alvo": Decimal("50000"),
            "realizado": Decimal("0"),
            "pct": 0.0,
            "indisponivel": True,
        }
    ]
    assert regra_meta_em_risco(metas, JANELA, hoje=date(2026, 8, 25)) == []


def test_margem_incompleta_conta_as_vendas_sem_custo():
    sinais = regra_margem_incompleta(_vendas(qtd=14, com_custo=8))
    assert len(sinais) == 1
    assert sinais[0].dados["sem_custo"] == 6
    assert "subestimada" in sinais[0].detalhe


def test_margem_completa_nao_dispara():
    assert regra_margem_incompleta(_vendas(qtd=14, com_custo=14)) == []


def test_cadastro_incompleto_usa_as_lacunas_do_overview():
    overview = EstoqueOverview(
        status="ok",
        contagens=None,
        idade=None,
        lacunas=(
            LacunaCadastro(
                id="v1", placa="ABC", marca="Honda", modelo="CB", status="disponivel",
                faltas=("foto", "preco"),
            ),
        ),
        total_lacunas=3,
    )
    sinais = regra_cadastro_incompleto(overview)
    assert len(sinais) == 1
    assert sinais[0].dados["total"] == 3


def test_cadastro_sem_lacuna_nao_dispara():
    overview = EstoqueOverview(
        status="ok", contagens=None, idade=None, lacunas=(), total_lacunas=0
    )
    assert regra_cadastro_incompleto(overview) == []


def _origem(identificadas, total):
    itens = tuple(
        OrigemVenda(
            venda_id=f"v{i}",
            descricao="Moto",
            preco_venda=Decimal("20000"),
            confirmada_em=None,
            identificada=i < identificadas,
            campanha_nome=None,
            campanha_canal=None,
            utm_campaign=None,
            primeiro_clique_nome=None,
        )
        for i in range(total)
    )
    return OrigemPeriodo(
        status="parcial",
        janela=JANELA,
        itens=itens,
        cobertura=Cobertura(com_dado=identificadas, total=total),
    )


def test_atribuicao_baixa_dispara_acima_do_limite():
    sinais = regra_atribuicao_baixa(_origem(identificadas=9, total=14))
    assert len(sinais) == 1
    assert sinais[0].dados["sem_origem"] == 5


def test_atribuicao_boa_nao_dispara():
    assert regra_atribuicao_baixa(_origem(identificadas=13, total=14)) == []


def test_atribuicao_com_poucas_vendas_nao_dispara():
    """1 venda sem origem em 2 é 50%, mas não é sinal — é ruído."""
    assert regra_atribuicao_baixa(_origem(identificadas=1, total=2)) == []


# --- preço fora da faixa da FIPE --------------------------------------------

FOLGAS = dict(folga_alta=0.30, folga_base=0.15, dias_parado_min=60)


def test_preco_muito_acima_da_fipe_dispara_mesmo_recem_cadastrado():
    """Caso 1: destoa sozinho o bastante — não precisa estar parado."""
    veiculo = _veiculo("v1", dias=5, preco=40000)
    sinais = regra_preco_fora_da_faixa([(veiculo, Decimal("25000"))], **FOLGAS)
    assert len(sinais) == 1
    assert sinais[0].regra == "preco_fora_da_faixa"
    assert sinais[0].severidade == "atencao"
    assert sinais[0].entidade_ref == "v1"


def test_preco_dentro_da_tolerancia_nao_dispara():
    veiculo = _veiculo("v1", dias=5, preco=27000)
    assert regra_preco_fora_da_faixa([(veiculo, Decimal("25000"))], **FOLGAS) == []


def test_preco_abaixo_da_fipe_nao_dispara():
    """Pode ser estratégia de giro — não é problema, mesmo parado há tempo."""
    veiculo = _veiculo("v1", dias=200, preco=20000)
    assert regra_preco_fora_da_faixa([(veiculo, Decimal("25000"))], **FOLGAS) == []


def test_preco_abaixo_da_fipe_nao_dispara_mesmo_com_folga_base_negativa():
    """O guard é explícito e incondicional, não um efeito colateral dos
    limiares positivos de hoje: mesmo se ``folga_base`` fosse configurada
    negativa (limite abaixo da própria FIPE), preço abaixo da FIPE nunca
    vira sinal — a regra nesta fase não tem opinião sobre giro."""
    veiculo = _veiculo("v1", dias=200, preco=24000)  # abaixo da FIPE (25000)
    sinais = regra_preco_fora_da_faixa(
        [(veiculo, Decimal("25000"))],
        folga_alta=0.30,
        folga_base=-0.10,  # limite_base = 22500 < preco, se não fosse o guard
        dias_parado_min=60,
    )
    assert sinais == []


def test_sem_valor_fipe_confirmado_nao_dispara():
    """Sem valor resolvido (FIPE indisponível ou matching ambíguo no
    worker), esta função pura não tem o que decidir e pula o veículo."""
    veiculo = _veiculo("v1", dias=5, preco=99999)
    assert regra_preco_fora_da_faixa([(veiculo, None)], **FOLGAS) == []


def test_severidade_sobe_quando_tambem_esta_parado():
    """Caso 2: mesma folga de preço, mas só dispara — e só vira crítico —
    quando o veículo também está encalhado."""
    parado = _veiculo("v1", dias=90, preco=29000)
    recente = _veiculo("v2", dias=5, preco=29000)
    sinais_parado = regra_preco_fora_da_faixa([(parado, Decimal("25000"))], **FOLGAS)
    sinais_recente = regra_preco_fora_da_faixa([(recente, Decimal("25000"))], **FOLGAS)
    assert len(sinais_parado) == 1
    assert sinais_parado[0].severidade == "critico"
    assert sinais_recente == []


def test_entidade_ref_e_o_id_do_veiculo():
    veiculo = _veiculo("v42", dias=90, preco=40000)
    sinais = regra_preco_fora_da_faixa([(veiculo, Decimal("25000"))], **FOLGAS)
    assert sinais[0].entidade_ref == "v42"
    assert sinais[0].dados["veiculo_id"] == "v42"
    assert sinais[0].acao_sugerida == {"acao": "ajustar_preco", "veiculo_id": "v42"}
