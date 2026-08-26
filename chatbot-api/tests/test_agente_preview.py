"""Preview do agente (spec §6.1). O risco nº 1 é ele **agir**.

As ferramentas do agente criam lead, avisam a equipe no WhatsApp, pausam o bot e
gravam a moto escolhida numa conversa real. Um preview sem freio faz tudo isso
quando o lojista digita um CPF para ver como o agente responde. O freio de modo
seco mora no workflow (`n8n/validate_preview_workflow.py` prova a
alcançabilidade); o que se prova aqui é o lado do backend: o telefone nunca é o
de quem testa, e o prompt é o do rascunho, não o publicado.
"""
import pytest

from app import agente_config, agente_preview, config, servico
from app.agente_prompt import NUCLEO_REVY, CamposAgente


@pytest.fixture
def preview_ligado(monkeypatch):
    monkeypatch.setattr(config, "AGENTE_PREVIEW_URL", "http://n8n:5678/webhook/preview")
    yield


class _Espiao:
    """Fica no lugar do n8n e guarda o que o chatbot mandou."""

    def __init__(self, resposta="oi, tudo bem?"):
        self.chamadas: list[dict] = []
        self.resposta = resposta

    def __call__(self, *, instance, loja_id, texto, prompt, historico, minusculas,
                 sem_emoji, turno, primeira_mensagem):
        self.chamadas.append(
            {
                "instance": instance,
                "loja_id": loja_id,
                "texto": texto,
                "prompt": prompt,
                "telefone": agente_preview.telefone_sintetico(loja_id),
                "minusculas": minusculas,
                "sem_emoji": sem_emoji,
                "turno": turno,
            }
        )
        return self.resposta


def _espiar(monkeypatch, resposta="oi, tudo bem?") -> _Espiao:
    espiao = _Espiao(resposta)
    monkeypatch.setattr(agente_preview, "conversar", espiao)
    return espiao


# --- o telefone nunca é o de quem testa --------------------------------------


def test_telefone_sintetico_nao_e_msisdn():
    """Começa em 0: nenhum número real começa com zero, então ele não colide com
    telefone de cliente nem depois do replace(/\\D/g,'') das ferramentas."""
    tel = agente_preview.telefone_sintetico("loja-1")
    assert tel.startswith("0")
    assert tel.isdigit()


def test_telefone_sintetico_e_estavel_e_por_loja():
    """Estável para o preview ter memória entre turnos; por loja para o estado de
    uma não vazar na outra."""
    assert agente_preview.telefone_sintetico("loja-1") == agente_preview.telefone_sintetico("loja-1")
    assert agente_preview.telefone_sintetico("loja-1") != agente_preview.telefone_sintetico("loja-2")


def test_a_rota_nao_aceita_telefone_da_tela(client, loja_a, preview_ligado, monkeypatch):
    """Se a tela pudesse mandar o telefone, o lojista testaria com o próprio
    número — e `consultar_estoque` sobrescreveria a conversa real dele."""
    _espiar(monkeypatch)
    r = client.post(
        "/v1/agente/preview",
        json={"texto": "oi", "telefone": "5519999999999"},
        headers=loja_a["headers"],
    )
    assert r.status_code == 422


def test_preview_usa_o_telefone_sintetico_da_loja(client, db, loja_a, preview_ligado, monkeypatch):
    espiao = _espiar(monkeypatch)
    r = client.post("/v1/agente/preview", json={"texto": "oi"}, headers=loja_a["headers"])
    assert r.status_code == 200
    assert espiao.chamadas[0]["telefone"] == agente_preview.telefone_sintetico(
        loja_a["loja_id"]
    )


# --- o prompt é o do rascunho ------------------------------------------------


def test_preview_conversa_com_o_rascunho_e_nao_com_o_publicado(
    client, db, loja_a, preview_ligado, monkeypatch
):
    """Testar o publicado não serviria para nada: o lojista está justamente
    decidindo se publica."""
    agente_config.salvar_rascunho(
        db, loja_a["loja_id"], CamposAgente(nome_loja="Publicada", cidade="X", uf="SP"), autor="t"
    )
    agente_config.publicar(db, loja_a["loja_id"], autor="t")
    agente_config.salvar_rascunho(
        db, loja_a["loja_id"], CamposAgente(nome_loja="Rascunho", cidade="X", uf="SP"), autor="t"
    )

    espiao = _espiar(monkeypatch)
    client.post("/v1/agente/preview", json={"texto": "oi"}, headers=loja_a["headers"])
    prompt = espiao.chamadas[0]["prompt"].lower()
    assert "rascunho" in prompt
    assert "publicada" not in prompt


def test_prompt_do_preview_termina_no_nucleo(client, db, loja_a, preview_ligado, monkeypatch):
    """Mesma garantia do bot real: o que vem depois do núcleo o vence."""
    espiao = _espiar(monkeypatch)
    client.post("/v1/agente/preview", json={"texto": "oi"}, headers=loja_a["headers"])
    assert espiao.chamadas[0]["prompt"].rstrip().endswith(NUCLEO_REVY.rstrip())


def test_preview_leva_a_higienizacao_da_loja(client, db, loja_a, preview_ligado, monkeypatch):
    """O lojista tem que ler o que o cliente leria — inclusive o efeito das
    escolhas de escrita e emoji."""
    agente_config.salvar_rascunho(
        db,
        loja_a["loja_id"],
        CamposAgente(nome_loja="X", cidade="Y", uf="SP", escrita="normal", emoji="a_vontade"),
        autor="t",
    )
    espiao = _espiar(monkeypatch)
    client.post("/v1/agente/preview", json={"texto": "oi"}, headers=loja_a["headers"])
    assert espiao.chamadas[0]["minusculas"] is False
    assert espiao.chamadas[0]["sem_emoji"] is False


# --- isolamento e gates ------------------------------------------------------


def test_integracao_com_instance_testa_a_loja_daquela_instancia(
    client, db, loja_a, loja_b, preview_ligado, monkeypatch
):
    agente_config.salvar_rascunho(
        db, loja_b["loja_id"], CamposAgente(nome_loja="Loja B", cidade="X", uf="SP"), autor="t"
    )
    token = servico.criar_credencial_integracao(db)
    db.commit()
    espiao = _espiar(monkeypatch)
    r = client.post(
        f"/v1/agente/preview?instance={loja_b['instance']}",
        json={"texto": "oi"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert "loja b" in espiao.chamadas[0]["prompt"].lower()
    assert espiao.chamadas[0]["loja_id"] == loja_b["loja_id"]


def test_loja_suspensa_nao_testa(client, db, loja_sem_projecao, preview_ligado, monkeypatch):
    _espiar(monkeypatch)
    r = client.post(
        "/v1/agente/preview", json={"texto": "oi"}, headers=loja_sem_projecao["headers"]
    )
    assert r.status_code == 423


def test_sem_workflow_de_preview_a_rota_diz_503(client, loja_a, monkeypatch):
    """Default seguro: sem o workflow importado não há o que chamar, e a tela
    esconde o botão em vez de oferecer um teste que sempre falha."""
    monkeypatch.setattr(config, "AGENTE_PREVIEW_URL", "")
    r = client.post("/v1/agente/preview", json={"texto": "oi"}, headers=loja_a["headers"])
    assert r.status_code == 503


def test_n8n_fora_do_ar_vira_503_e_nao_500(client, loja_a, preview_ligado, monkeypatch):
    def _cai(**_kwargs):
        raise agente_preview.PreviewIndisponivel("o preview não respondeu agora")

    monkeypatch.setattr(agente_preview, "conversar", _cai)
    r = client.post("/v1/agente/preview", json={"texto": "oi"}, headers=loja_a["headers"])
    assert r.status_code == 503


# --- o canal do preview é o que está no ar, não o campo legado ---------------


def test_preview_usa_o_canal_ativo_e_nao_o_campo_legado_da_loja(
    client, db, loja_a, preview_ligado, monkeypatch
):
    """`Loja.evolution_instance` envelhece; o canal conectado é a verdade.

    Em produção, em 25/08, a moto-center tinha `evolution_instance` apontando
    para `moto-center-48a9` — canal inativo desde 06/08 — enquanto quem atendia
    era `moto-center-f447`, com 485 conversas. Cada novo pareamento cria
    instância nova (o QR não fecha por passkey e a pessoa tenta de novo), então
    o campo legado drifta por construção: são 8 instâncias na Evolution, uma só
    aberta. O preview mandaria o lojista testar contra um canal morto.

    O resto do produto já resolve isso com `resolve_evolution_instance_for_loja`
    (principal de estoque → conectado ativo → ativo → legado). O preview era o
    único que lia o campo cru.
    """
    from app import channels, models_db

    espiao = _espiar(monkeypatch)
    loja = db.get(models_db.Loja, loja_a["loja_id"])
    canal = channels.register_channel(db, loja.id, "viva-1", "atendimento")
    db.query(models_db.WhatsAppCanal).filter(
        models_db.WhatsAppCanal.id == canal["id"]
    ).update({"estado": channels.ESTADO_CONECTADO, "ativo": True})
    db.commit()

    client.post("/v1/agente/preview", json={"texto": "oi"}, headers=loja_a["headers"])

    assert espiao.chamadas[-1]["instance"] == "viva-1"
    assert espiao.chamadas[-1]["instance"] != loja.evolution_instance
