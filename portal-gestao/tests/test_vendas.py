from decimal import Decimal

from conftest import csrf_da_resposta, login

from app.db import SessionLocal
from app.main import lucro_bruto_venda
from app.models import FunilEvento, Venda, VendaCustoDireto, agora


def criar_venda(
    loja_slug="loja-teste",
    status="registrada",
    vendedor_email="dono@loja.test",
    custo=None,
    lead_ref=None,
    veiculo_ref=None,
):
    db = SessionLocal()
    venda = Venda(
        loja_slug=loja_slug,
        vendedor_email=vendedor_email,
        descricao="Honda Civic 2022",
        preco_venda=Decimal("100000.00"),
        custo_veiculo=Decimal(custo) if custo is not None else None,
        status=status,
        lead_ref=lead_ref,
        veiculo_ref=veiculo_ref,
        confirmada_em=agora() if status == "confirmada" else None,
    )
    db.add(venda)
    db.commit()
    venda_id = venda.id
    db.close()
    return venda_id


def csrf_das_vendas(client):
    return csrf_da_resposta(client.get("/app/vendas"))


def test_dono_registra_venda(client):
    login(client)
    pagina = client.get("/app/vendas/nova")
    resposta = client.post(
        "/app/vendas/nova",
        data={"csrf": csrf_da_resposta(pagina), "descricao": "Corolla 2023", "preco_venda": "120000.50", "custo_veiculo": "100000"},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/vendas?ok=registrada"
    db = SessionLocal()
    venda = db.query(Venda).first()
    assert venda.descricao == "Corolla 2023"
    assert venda.preco_venda == Decimal("120000.50")
    assert venda.custo_veiculo == Decimal("100000.00")
    assert venda.status == "registrada"
    db.close()


def test_formulario_oferece_selecao_de_lead_e_veiculo(client):
    login(client)

    pagina = client.get("/app/vendas/nova")

    assert pagina.status_code == 200
    assert '<select name="veiculo_ref">' in pagina.text
    assert "Honda Civic 2022" in pagina.text
    assert '<select name="lead_ref">' in pagina.text
    assert "Maria Silva" in pagina.text
    assert 'placeholder="ID do estoque"' not in pagina.text


def test_registro_valida_e_persiste_referencias_da_loja(client):
    login(client)
    pagina = client.get("/app/vendas/nova")

    resposta = client.post(
        "/app/vendas/nova",
        data={
            "csrf": csrf_da_resposta(pagina),
            "descricao": "Honda Civic 2022",
            "preco_venda": "118900",
            "lead_ref": "l1",
            "veiculo_ref": "v1",
        },
        follow_redirects=False,
    )

    assert resposta.headers["location"] == "/app/vendas?ok=registrada"
    db = SessionLocal()
    venda = db.query(Venda).one()
    assert venda.lead_ref == "l1"
    assert venda.veiculo_ref == "v1"
    evento = db.query(FunilEvento).filter_by(lead_ref="l1", tipo="venda_registrada").one()
    assert evento.idempotency_key == f"portal:venda:{venda.id}:registrada"
    db.close()


def test_registro_rejeita_referencia_de_lead_que_nao_pertence_a_loja(client):
    login(client)
    pagina = client.get("/app/vendas/nova")

    resposta = client.post(
        "/app/vendas/nova",
        data={
            "csrf": csrf_da_resposta(pagina),
            "descricao": "Venda inválida",
            "preco_venda": "10000",
            "lead_ref": "lead-de-outra-loja",
        },
    )

    assert resposta.status_code == 422
    assert "lead selecionado não existe nesta loja" in resposta.text
    db = SessionLocal()
    assert db.query(Venda).count() == 0
    db.close()


def test_registro_rejeita_referencia_de_veiculo_que_nao_pertence_a_loja(client):
    login(client)
    pagina = client.get("/app/vendas/nova")

    resposta = client.post(
        "/app/vendas/nova",
        data={
            "csrf": csrf_da_resposta(pagina),
            "descricao": "Venda inválida",
            "preco_venda": "10000",
            "veiculo_ref": "veiculo-de-outra-loja",
        },
    )

    assert resposta.status_code == 422
    assert "veículo selecionado não existe nesta loja" in resposta.text
    db = SessionLocal()
    assert db.query(Venda).count() == 0
    db.close()


def test_formulario_preserva_fallback_quando_integracoes_estao_indisponiveis(
    client, chatbot_fake, estoque_fake
):
    chatbot_fake.indisponivel = True
    estoque_fake.indisponivel = True
    login(client)

    pagina = client.get("/app/vendas/nova")

    assert pagina.status_code == 200
    assert 'name="lead_ref"' in pagina.text
    assert 'name="veiculo_ref"' in pagina.text
    assert "Será validada antes da confirmação" in pagina.text


def test_fallback_registra_referencias_para_validacao_posterior(
    client, chatbot_fake, estoque_fake
):
    chatbot_fake.indisponivel = True
    estoque_fake.indisponivel = True
    login(client)
    pagina = client.get("/app/vendas/nova")

    resposta = client.post(
        "/app/vendas/nova",
        data={
            "csrf": csrf_da_resposta(pagina),
            "descricao": "Venda em contingência",
            "preco_venda": "10000",
            "lead_ref": "lead-manual",
            "veiculo_ref": "veiculo-manual",
        },
        follow_redirects=False,
    )

    assert resposta.headers["location"] == (
        "/app/vendas?ok=registrada&aviso=referencias-pendentes"
    )
    db = SessionLocal()
    venda = db.query(Venda).one()
    assert venda.status == "registrada"
    assert venda.lead_ref == "lead-manual"
    assert venda.veiculo_ref == "veiculo-manual"
    db.close()


def test_vendedor_registra_sem_custo(client):
    login(client, papel="vendedor")
    pagina = client.get("/app/vendas/nova")
    resposta = client.post(
        "/app/vendas/nova",
        data={"csrf": csrf_da_resposta(pagina), "descricao": "MT-03", "preco_venda": "31900", "custo_veiculo": "25000"},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    db = SessionLocal()
    venda = db.query(Venda).first()
    assert venda.status == "registrada"
    assert venda.custo_veiculo is None
    db.close()


def test_vendedor_confirma_venda(client):
    """Decisão do dono: quem fecha a venda a confirma, sem esperar gestão.

    É a confirmação que dispara estoque, funil, Control e Meta — deixá-la só com
    dono/gerente atrasava o sinal de conversão do anúncio.
    """
    venda_id = criar_venda(vendedor_email="vendedor@loja.test")
    login(client, papel="vendedor", email="vendedor@loja.test")
    csrf = csrf_das_vendas(client)

    resposta = client.post(
        f"/app/vendas/{venda_id}/confirmar",
        data={"csrf": csrf},
        follow_redirects=False,
    )

    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/vendas?ok=confirmada"
    db = SessionLocal()
    venda = db.get(Venda, venda_id)
    assert venda.status == "confirmada"
    assert venda.confirmada_por == "vendedor@loja.test"
    db.close()


def test_vendedor_nao_confirma_venda_de_outra_loja(client):
    """Confirmar deixou de ser privilégio de cargo, mas segue preso à loja."""
    venda_id = criar_venda(loja_slug="outra-loja")
    login(client, papel="vendedor", email="vendedor@loja.test")
    csrf = csrf_das_vendas(client)

    resposta = client.post(
        f"/app/vendas/{venda_id}/confirmar",
        data={"csrf": csrf},
        follow_redirects=False,
    )

    assert resposta.headers["location"] == "/app/vendas?erro=acao"
    db = SessionLocal()
    assert db.get(Venda, venda_id).status == "registrada"
    db.close()


def test_dono_confirma_venda(client):
    venda_id = criar_venda()
    login(client)
    csrf = csrf_das_vendas(client)
    resposta = client.post(f"/app/vendas/{venda_id}/confirmar", data={"csrf": csrf}, follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/vendas?ok=confirmada"
    db = SessionLocal()
    venda = db.get(Venda, venda_id)
    assert venda.status == "confirmada"
    assert venda.confirmada_por == "dono@loja.test"
    assert venda.confirmada_em is not None
    db.close()


def test_confirmacao_publica_purchase_no_event_bus(client, monkeypatch):
    venda_id = criar_venda(lead_ref="l1")
    publicados = []

    def publicar(kind, payload, db):
        publicados.append((kind, payload, db))

    monkeypatch.setattr("app.main.publish_conversion", publicar)
    login(client)

    resposta = client.post(
        f"/app/vendas/{venda_id}/confirmar",
        data={"csrf": csrf_das_vendas(client)},
        follow_redirects=False,
    )

    assert resposta.headers["location"] == "/app/vendas?ok=confirmada"
    assert len(publicados) == 1
    kind, payload, _ = publicados[0]
    assert kind.value == "purchase"
    assert payload.venda_id == venda_id
    assert payload.event_id == f"purchase-{venda_id}"
    assert payload.lead_ref == "l1"
    assert payload.phone == "5511987654321"
    db = SessionLocal()
    evento = db.query(FunilEvento).filter_by(
        lead_ref="l1", tipo="venda_confirmada"
    ).one()
    assert evento.idempotency_key == f"portal:venda:{venda_id}:confirmada"
    db.close()


def test_confirmacao_baixa_veiculo_no_estoque(client, estoque_fake):
    venda_id = criar_venda(lead_ref="l1", veiculo_ref="v1")
    login(client)

    resposta = client.post(
        f"/app/vendas/{venda_id}/confirmar",
        data={"csrf": csrf_das_vendas(client)},
        follow_redirects=False,
    )

    assert resposta.headers["location"] == "/app/vendas?ok=confirmada"
    assert estoque_fake.acoes == [("v1", "vender")]
    assert estoque_fake.obter("v1")["status"] == "vendido"
    db = SessionLocal()
    assert db.get(Venda, venda_id).status == "confirmada"
    db.close()


def test_confirmacao_mantem_registrada_quando_estoque_indisponivel(
    client, estoque_fake
):
    venda_id = criar_venda(veiculo_ref="v1")
    estoque_fake.indisponivel = True
    login(client)

    resposta = client.post(
        f"/app/vendas/{venda_id}/confirmar",
        data={"csrf": csrf_das_vendas(client)},
        follow_redirects=False,
    )

    assert resposta.headers["location"] == "/app/vendas?erro=estoque-indisponivel"
    pagina_erro = client.get(resposta.headers["location"])
    assert "confira o estado do veículo antes de tentar novamente" in pagina_erro.text
    db = SessionLocal()
    assert db.get(Venda, venda_id).status == "registrada"
    db.close()


def test_confirmacao_mantem_registrada_em_conflito_de_estoque(
    client, estoque_fake
):
    venda_id = criar_venda(veiculo_ref="v1")
    estoque_fake.conflito_ao_vender = True
    login(client)

    resposta = client.post(
        f"/app/vendas/{venda_id}/confirmar",
        data={"csrf": csrf_das_vendas(client)},
        follow_redirects=False,
    )

    assert resposta.headers["location"] == "/app/vendas?erro=conflito-estoque"
    assert estoque_fake.acoes == []
    db = SessionLocal()
    assert db.get(Venda, venda_id).status == "registrada"
    db.close()


def test_confirmacao_rejeita_veiculo_manual_invalido_quando_integracao_volta(client):
    venda_id = criar_venda(veiculo_ref="veiculo-de-outra-loja")
    login(client)

    resposta = client.post(
        f"/app/vendas/{venda_id}/confirmar",
        data={"csrf": csrf_das_vendas(client)},
        follow_redirects=False,
    )

    assert resposta.headers["location"] == "/app/vendas?erro=veiculo"
    db = SessionLocal()
    assert db.get(Venda, venda_id).status == "registrada"
    db.close()


def test_cancelar_exige_motivo(client):
    venda_id = criar_venda()
    login(client)
    csrf = csrf_das_vendas(client)
    sem_motivo = client.post(f"/app/vendas/{venda_id}/cancelar", data={"csrf": csrf}, follow_redirects=False)
    assert sem_motivo.headers["location"] == "/app/vendas?erro=motivo"
    db = SessionLocal()
    assert db.get(Venda, venda_id).status == "registrada"
    db.close()
    com_motivo = client.post(f"/app/vendas/{venda_id}/cancelar", data={"csrf": csrf, "motivo": "desistência"}, follow_redirects=False)
    assert com_motivo.headers["location"] == "/app/vendas?ok=cancelada"
    db = SessionLocal()
    venda = db.get(Venda, venda_id)
    assert venda.status == "cancelada"
    assert venda.motivo_cancelamento == "desistência"
    db.close()


def test_cancelar_confirmada_nao_reabre_veiculo_vendido(client, estoque_fake):
    venda_id = criar_venda(status="confirmada", veiculo_ref="v1")
    estoque_fake.veiculos[0]["status"] = "vendido"
    login(client)

    resposta = client.post(
        f"/app/vendas/{venda_id}/cancelar",
        data={"csrf": csrf_das_vendas(client), "motivo": "distrato"},
        follow_redirects=False,
    )

    assert resposta.headers["location"] == "/app/vendas?ok=cancelada-estoque-mantido"
    assert estoque_fake.acoes == []
    assert estoque_fake.veiculos[0]["status"] == "vendido"
    db = SessionLocal()
    assert db.get(Venda, venda_id).status == "cancelada"
    db.close()


def test_nao_cruza_loja(client):
    venda_id = criar_venda(loja_slug="outra-loja")
    login(client)
    csrf = csrf_das_vendas(client)
    resposta = client.post(f"/app/vendas/{venda_id}/confirmar", data={"csrf": csrf}, follow_redirects=False)
    assert resposta.headers["location"] == "/app/vendas?erro=acao"
    db = SessionLocal()
    assert db.get(Venda, venda_id).status == "registrada"
    db.close()


def test_venda_confirmada_nao_pode_ser_apagada(client):
    venda_id = criar_venda(status="confirmada")
    login(client)
    resposta = client.delete(f"/app/vendas/{venda_id}", follow_redirects=False)
    assert resposta.status_code in (404, 405)
    db = SessionLocal()
    venda = db.get(Venda, venda_id)
    assert venda is not None
    assert venda.status == "confirmada"
    db.close()


def test_lucro_bruto_em_decimal_com_arredondamento():
    venda = Venda(descricao="x", preco_venda=Decimal("100000.00"), custo_veiculo=Decimal("80000.00"))
    venda.custos_diretos.append(VendaCustoDireto(categoria="documentacao", valor=Decimal("1500.00")))
    venda.custos_diretos.append(VendaCustoDireto(categoria="comissao", valor=Decimal("2000.50")))
    lucro = lucro_bruto_venda(venda)
    assert lucro == Decimal("16499.50")
    assert str(lucro) == "16499.50"


def test_lucro_bruto_indisponivel_sem_custo_do_veiculo():
    venda = Venda(descricao="x", preco_venda=Decimal("100000.00"), custo_veiculo=None)
    assert lucro_bruto_venda(venda) is None
