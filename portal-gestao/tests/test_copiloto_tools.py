from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.loja.copiloto.tipos import CopilotoContexto
from app.loja.copiloto.tools import (
    FerramentaDesconhecida,
    RecursosTools,
    despachar,
    registro_padrao,
    schemas,
)
from app.models import Venda

AGORA = datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc)
CAMPOS_PROIBIDOS = {"loja_slug", "papel", "vendedor_email", "ator_email", "usuario"}


def _ctx():
    return CopilotoContexto(
        loja_slug="loja-teste",
        papel="dono",
        ator_email="dono@loja.test",
        hoje=date(2026, 8, 11),
    )


class EstoqueStub:
    def obter_loja(self):
        return {"slug": "loja-teste"}

    def listar(self, **filtros):
        return [
            {
                "id": "v1",
                "marca": "Honda",
                "modelo": "CB 500F",
                "preco": 25000.0,
                "status": "disponivel",
                "criado_em": (AGORA - timedelta(days=90)).isoformat(),
            }
        ]


class ChatbotStub:
    def listar_conversas(self, busca=None, limit=50, offset=0, *, canal_id=None):
        return []

    def listar_leads(self, etapa=None):
        return []


def _recursos(db):
    return RecursosTools(
        db=db, estoque=EstoqueStub(), chatbot=ChatbotStub(), ctx=_ctx(), agora=AGORA
    )


def test_registro_tem_as_ferramentas_da_v1():
    nomes = {f.nome for f in registro_padrao()}
    assert nomes == {
        "vendas_resumo",
        "ranking_vendedores",
        "venda_origem",
        "estoque_parado",
        "leads_status",
        "roi_canais",
        "consultar_fipe",
        "propor_acao",
    }


def test_nenhum_schema_expoe_identidade():
    """O modelo não pode escolher de qual loja ou papel está falando."""
    for schema in schemas(registro_padrao()):
        propriedades = set(schema["parameters"].get("properties", {}))
        assert not (propriedades & CAMPOS_PROIBIDOS), schema["name"]


def test_schema_tem_descricao_e_tipo_objeto():
    for schema in schemas(registro_padrao()):
        assert schema["description"].strip()
        assert schema["parameters"]["type"] == "object"


def test_data_hoje_nao_e_ferramenta():
    assert "data_hoje" not in {f.nome for f in registro_padrao()}


def test_despacha_vendas_resumo(db):
    db.add(
        Venda(
            loja_slug="loja-teste",
            vendedor_email="ana@loja.test",
            descricao="Moto",
            preco_venda=Decimal("30000"),
            status="confirmada",
            criada_em=AGORA - timedelta(days=2),
        )
    )
    db.commit()
    saida = despachar("vendas_resumo", {}, _recursos(db))
    assert saida["qtd_vendas"] == 1
    assert "cobertura_margem" in saida


def test_despacha_estoque_parado_com_argumento(db):
    saida = despachar("estoque_parado", {"dias_min": 60}, _recursos(db))
    assert saida["total"] == 1
    assert saida["dias_min"] == 60


def test_despacha_venda_origem_ultima_por_padrao(db):
    saida = despachar("venda_origem", {}, _recursos(db))
    assert saida["status"] == "vazio"


def test_despacha_venda_origem_do_periodo(db):
    saida = despachar("venda_origem", {"escopo": "periodo"}, _recursos(db))
    assert "cobertura" in saida


def test_argumento_desconhecido_e_ignorado_nao_explode(db):
    saida = despachar("estoque_parado", {"dias_min": 60, "cor": "azul"}, _recursos(db))
    assert saida["dias_min"] == 60


def test_ferramenta_desconhecida_levanta(db):
    with pytest.raises(FerramentaDesconhecida):
        despachar("apagar_tudo", {}, _recursos(db))


def test_argumento_de_tipo_errado_nao_derruba_o_turno(db):
    """Modelo mandou string onde era int: cai no default, não em 500."""
    saida = despachar("estoque_parado", {"dias_min": "sessenta"}, _recursos(db))
    assert saida["dias_min"] == 30


def test_toda_saida_e_serializavel_em_json(db):
    import json

    for ferramenta in registro_padrao():
        json.dumps(despachar(ferramenta.nome, {}, _recursos(db)))


def _overview_com_aquisicao(**overrides):
    from app.loja import sales_overview as so

    padrao = dict(
        status="ok",
        periodo_inicio=date(2026, 8, 1),
        periodo_fim=date(2026, 8, 11),
        timezone="America/Sao_Paulo",
        escopo="loja",
        aquisicao=so.AquisicaoResumo(status="ok", fonte="local"),
        aquisicao_status="ok",
    )
    padrao.update(overrides)
    return so.SalesOverview(**padrao)


def test_roi_canais_serializa_decimal_das_linhas_de_midia(db, monkeypatch):
    """Quando a API do Revy Tráfego responde, as linhas trazem Decimal cru
    (``_linhas_midia_da_api``); o tool precisa passar pelo mesmo serializador
    que ``SalesOverview.to_dict()`` usa, senão ``json.dumps`` explode."""
    import json

    from app.loja import sales_overview as so
    from app.loja.copiloto.cache import cache_overview

    cache_overview.invalidar()

    overview = _overview_com_aquisicao(
        aquisicao=so.AquisicaoResumo(status="ok", fonte="api"),
        aquisicao_status="ok",
        aquisicao_campanhas=[
            {"nome": "Campanha X", "gasto": Decimal("123.456"), "cpl": Decimal("1.5")}
        ],
        aquisicao_canais=[{"canal": "meta", "gasto": Decimal("999.999")}],
    )
    monkeypatch.setattr(so, "build_sales_overview", lambda *a, **k: overview)

    saida = despachar("roi_canais", {}, _recursos(db))
    json.dumps(saida)  # não pode levantar TypeError (Decimal não é serializável)

    # Mesma conversão que _serializar_linhas_midia/_dec_str fazem: string,
    # quantizada a centavos com ROUND_HALF_UP.
    assert saida["campanhas"][0]["gasto"] == "123.46"
    assert saida["campanhas"][0]["cpl"] == "1.50"
    assert saida["canais"][0]["gasto"] == "1000.00"


def test_roi_canais_encaminha_periodo_e_nao_colide_no_cache(db, monkeypatch):
    """inicio/fim do schema precisam chegar em build_sales_overview e variar
    a chave do cache — senão duas perguntas de períodos diferentes devolvem
    o mesmo número (silenciosamente errado)."""
    from app.loja import sales_overview as so
    from app.loja.copiloto.cache import cache_overview

    cache_overview.invalidar()
    chamadas: list[dict] = []

    def _fake_build(dbx, *, loja_slug, papel, chatbot=None, inicio=None, fim=None, **kw):
        chamadas.append({"inicio": inicio, "fim": fim})
        return _overview_com_aquisicao()

    monkeypatch.setattr(so, "build_sales_overview", _fake_build)

    despachar(
        "roi_canais", {"inicio": "2026-07-01", "fim": "2026-07-31"}, _recursos(db)
    )
    despachar(
        "roi_canais", {"inicio": "2026-08-01", "fim": "2026-08-11"}, _recursos(db)
    )

    # Duas chamadas de verdade: se a chave do cache tivesse colidido, a
    # segunda teria vindo do cache e "chamadas" teria só 1 item.
    assert chamadas == [
        {"inicio": "2026-07-01", "fim": "2026-07-31"},
        {"inicio": "2026-08-01", "fim": "2026-08-11"},
    ]


def test_roi_canais_indisponivel_quando_overview_falha(db, monkeypatch):
    from app.loja import sales_overview as so
    from app.loja.copiloto.cache import cache_overview

    cache_overview.invalidar()

    def _fake_build(*a, **k):
        raise RuntimeError("revy trafego fora do ar")

    monkeypatch.setattr(so, "build_sales_overview", _fake_build)

    saida = despachar(
        "roi_canais", {"inicio": "2026-06-01", "fim": "2026-06-30"}, _recursos(db)
    )
    assert saida == {"status": "indisponivel", "campanhas": [], "canais": []}


def test_leads_status_indisponivel_quando_overview_falha(db, monkeypatch):
    from app.loja import sales_overview as so
    from app.loja.copiloto.cache import cache_overview

    cache_overview.invalidar()

    def _fake_build(*a, **k):
        raise RuntimeError("revy trafego fora do ar")

    monkeypatch.setattr(so, "build_sales_overview", _fake_build)

    saida = despachar("leads_status", {}, _recursos(db))
    assert saida == {"status": "indisponivel", "mensagem": "funil indisponível agora"}
