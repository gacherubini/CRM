from decimal import Decimal

from conftest import criar_usuario, login

from app.db import SessionLocal
from app.main import identidade_telefone
from app.models import AtendimentoAtribuicao, FunilEvento, Venda


def criar_venda_vinculada(lead_ref, vendedor_email="dono@loja.test", loja_slug="loja-teste"):
    db = SessionLocal()
    db.add(
        Venda(
            loja_slug=loja_slug,
            lead_ref=lead_ref,
            vendedor_email=vendedor_email,
            descricao="Venda vinculada",
            preco_venda=Decimal("50000"),
            custo_veiculo=Decimal("40000"),
            status="confirmada",
        )
    )
    db.commit()
    db.close()


def criar_atribuicao(telefone, vendedor_email="dono@loja.test", loja_slug="loja-teste"):
    db = SessionLocal()
    db.add(
        AtendimentoAtribuicao(
            loja_slug=loja_slug,
            telefone_hmac=identidade_telefone(telefone),
            vendedor_email=vendedor_email,
            ativa=True,
        )
    )
    db.commit()
    db.close()


def test_funil_reconcilia_leads_handoffs_e_venda_vinculada(client, chatbot_fake):
    criar_atribuicao("5511987654321")
    criar_venda_vinculada("l1")
    login(client)
    resposta = client.get("/app/financeiro")
    assert resposta.status_code == 200
    assert "Leads elegíveis" in resposta.text
    assert "<strong>2</strong><small>leads criados" in resposta.text
    assert "<strong>1</strong><small>leads elegíveis com handoff" in resposta.text
    assert "<strong>1</strong><small>vendas confirmadas" in resposta.text
    assert "não prova causalidade" in resposta.text


def test_funil_filtra_origem_declarada_sem_inferir_ausentes(client, chatbot_fake):
    criar_venda_vinculada("l1")
    login(client)
    resposta = client.get("/app/financeiro", params={"origem": "catalogo"})
    assert resposta.status_code == 200
    assert "<strong>1</strong><small>leads criados" in resposta.text
    assert "origem declarada" in resposta.text


def test_funil_filtra_vendedor_por_handoff_confiavel(client, chatbot_fake):
    criar_usuario(papel="vendedor", email="vendedor@loja.test")
    criar_atribuicao("5511987654321", vendedor_email="vendedor@loja.test")
    criar_venda_vinculada("l1", vendedor_email="vendedor@loja.test")
    login(client)
    resposta = client.get("/app/financeiro", params={"vendedor": "vendedor@loja.test"})
    assert resposta.status_code == 200
    assert "<strong>1</strong><small>leads criados" in resposta.text
    assert "<strong>1</strong><small>leads elegíveis com handoff" in resposta.text
    assert "<strong>1</strong><small>vendas confirmadas" in resposta.text


def test_funil_indisponivel_sem_chatbot_mantem_financeiro_local(client, chatbot_fake):
    chatbot_fake.indisponivel = True
    criar_venda_vinculada("l1")
    login(client)
    resposta = client.get("/app/financeiro")
    assert resposta.status_code == 200
    assert "R$ 50.000,00" in resposta.text
    assert "Funil indisponível" in resposta.text
    assert "Não foi possível acessar os leads agora" in resposta.text


def test_funil_indisponivel_quando_lead_nao_tem_data_confiavel(client, chatbot_fake):
    chatbot_fake.leads[0].pop("criada_em")
    login(client)
    resposta = client.get("/app/financeiro")
    assert resposta.status_code == 200
    assert "Funil indisponível" in resposta.text
    assert "sem data de criação confiável" in resposta.text


def test_funil_ignora_venda_e_handoff_de_outra_loja(client, chatbot_fake):
    criar_atribuicao("5511987654321", loja_slug="outra-loja")
    criar_venda_vinculada("l1", loja_slug="outra-loja")
    login(client)
    resposta = client.get("/app/financeiro")
    assert resposta.status_code == 200
    assert "<strong>0</strong><small>leads elegíveis com handoff" in resposta.text
    assert "<strong>0</strong><small>vendas confirmadas" in resposta.text


def test_financeiro_materializa_eventos_sanitizados_do_chatbot(client, chatbot_fake):
    chatbot_fake.eventos_funil = [
        {
            "lead_ref": "l1",
            "tipo": "lead_criado",
            "ocorrido_em": "2026-07-09T09:00:00+00:00",
            "idempotency_key": "chatbot:lead:l1:criado",
            "payload": {"origem": "catalogo", "canal": "site"},
        }
    ]
    login(client)

    assert client.get("/app/financeiro").status_code == 200
    assert client.get("/app/financeiro").status_code == 200

    db = SessionLocal()
    eventos = db.query(FunilEvento).filter_by(loja_slug="loja-teste").all()
    assert len(eventos) == 1
    assert eventos[0].lead_ref == "l1"
    assert "telefone" not in (eventos[0].payload_json or "")
    db.close()


def test_sincronizacao_avanca_pelo_numero_de_leads_nao_de_eventos(client, chatbot_fake):
    chamadas: list[tuple[int, int]] = []

    def listar_eventos_funil(limit=500, offset=0):
        chamadas.append((limit, offset))
        if offset:
            return []
        # 500 leads podem produzir 1.000 eventos. Um cursor baseado na quantidade
        # de eventos avançaria para 1.000 e pularia a página de leads em 500.
        return [
            {
                "lead_ref": f"lead-{indice}",
                "tipo": tipo,
                "ocorrido_em": "2026-07-09T09:00:00+00:00",
                "idempotency_key": f"chatbot:lead:{indice}:{tipo}",
                "payload": None,
            }
            for indice in range(500)
            for tipo in ("lead_criado", "primeira_resposta")
        ]

    chatbot_fake.listar_eventos_funil = listar_eventos_funil
    login(client)

    resposta = client.get(
        "/app/funil/dados",
        params={"inicio": "2026-07-09", "fim": "2026-07-09"},
    )

    assert resposta.status_code == 200
    assert chamadas == [(500, 0), (500, 500)]


def test_backend_funil_retorna_tempos_da_loja_sem_ui_manual(client, chatbot_fake):
    chatbot_fake.eventos_funil = [
        {
            "lead_ref": "lead-tempo",
            "tipo": "lead_criado",
            "ocorrido_em": "2026-07-09T12:00:00+00:00",
            "idempotency_key": "chatbot:lead:lead-tempo:criado",
            "payload": None,
        },
        {
            "lead_ref": "lead-tempo",
            "tipo": "primeira_resposta",
            "ocorrido_em": "2026-07-09T12:03:00+00:00",
            "idempotency_key": "chatbot:mensagem:lead-tempo:resposta",
            "payload": None,
        },
    ]
    login(client)

    resposta = client.get(
        "/app/funil/dados",
        params={"inicio": "2026-07-09", "fim": "2026-07-09"},
    )

    assert resposta.status_code == 200
    funil = resposta.json()["funil"]
    assert funil["total_leads"] == 1
    assert funil["etapas"]["primeira_resposta"] == 1
    assert funil["tempo_medio_primeira_resposta_segundos"] == 180


def test_backend_funil_nao_expoe_metricas_ao_vendedor(client, chatbot_fake):
    login(client, papel="vendedor")

    resposta = client.get("/app/funil/dados", follow_redirects=False)

    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app"
