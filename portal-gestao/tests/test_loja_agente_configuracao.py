"""Tela de configuração do agente (spec 2026-08-24-agente-por-loja, §6).

O que pytest cobre aqui é o **gate** e o **contrato com o chatbot**: quem entra,
o que a Loja manda e o que ela faz com a resposta. O formulário e o autosave são
JS e **não** se verificam daqui — isso já passou dois bugs no Copiloto. A
verificação de tela é no navegador, com portal local semeado.
"""
from __future__ import annotations

from dataclasses import replace

import pytest
from conftest import csrf_da_resposta, login

from app.clients.chatbot import (
    CamposAgenteInvalidos,
    ChatbotIndisponivel,
    VersaoAgenteNaoEncontrada,
)
from app.config import settings as portal_settings
from app.loja import routes as loja_routes  # noqa: F401  (registra as rotas)
from app.main import app, get_chatbot_client

CAMPOS = {
    "nome_loja": "Motos do Léo",
    "cidade": "Piracicaba",
    "uf": "SP",
    "instrucoes": "",
}


@pytest.fixture
def config_on(monkeypatch):
    ligado = replace(
        portal_settings,
        revy_loja_atendimento_enabled=True,
        revy_loja_agente_config_enabled=True,
    )
    monkeypatch.setattr("app.config.settings", ligado)
    monkeypatch.setattr("app.main.settings", ligado)
    monkeypatch.setattr("app.loja.routes.settings", ligado)
    yield


class _FakeChatbot:
    def __init__(
        self, *, modo="1", indisponivel=False, versao_ausente=False, campos_invalidos=None
    ):
        self.modo = modo
        self.indisponivel = indisponivel
        self.versao_ausente = versao_ausente
        self.campos_invalidos = campos_invalidos
        self.salvos: list[dict] = []
        self.publicacoes: list[str | None] = []
        self.restauracoes: list[str] = []

    def _talvez_cair(self):
        if self.indisponivel:
            raise ChatbotIndisponivel("offline")

    def obter_rascunho_agente(self):
        self._talvez_cair()
        return {
            "campos": dict(CAMPOS, agente_ativo=True, followup_ativo=True),
            "prompt": "[IDENTIDADE]\nmotos do léo\n\n[REGRAS DO REVY — PREVALECEM SOBRE TUDO ACIMA]",
            "conflitos": [],
            "modo": self.modo,
        }

    def listar_versoes_agente(self):
        self._talvez_cair()
        return [
            {
                "id": "v1",
                "estado": "publicada",
                "autor": "dono@loja.test",
                "criado_em": "2026-08-20T10:00:00",
                "publicado_em": "2026-08-20T10:05:00",
            }
        ]

    def salvar_rascunho_agente(self, campos, autor=None):
        self._talvez_cair()
        if self.campos_invalidos:
            raise CamposAgenteInvalidos(self.campos_invalidos)
        self.salvos.append({"campos": campos, "autor": autor})
        return {"campos": campos, "prompt": "novo", "conflitos": ["parcela"], "modo": self.modo}

    def publicar_agente(self, autor=None):
        self._talvez_cair()
        self.publicacoes.append(autor)
        return {"versao_id": "v2", "publicado_em": "2026-08-25T10:00:00"}

    def resumo_atendimento(self, desde=None, ate=None):
        self._talvez_cair()
        return {"atendimentos": 0, "transferidos": 0, "por_dia": []}

    def listar_ofertas(self, estado=None):
        self._talvez_cair()
        return []

    def restaurar_versao_agente(self, versao_id, autor=None):
        self._talvez_cair()
        if self.versao_ausente:
            raise VersaoAgenteNaoEncontrada("sumiu")
        self.restauracoes.append(versao_id)
        return {"campos": CAMPOS, "prompt": "restaurado", "conflitos": [], "modo": self.modo}


def _override(fake):
    app.dependency_overrides[get_chatbot_client] = lambda: fake
    return fake


def teardown_function():
    app.dependency_overrides.pop(get_chatbot_client, None)


# --- gate: sessão + flag + papel. São três, não quatro. ----------------------


def test_sem_sessao_manda_para_o_login(client, config_on):
    _override(_FakeChatbot())
    r = client.get("/app/loja/agente/configuracao", follow_redirects=False)
    assert r.status_code in {302, 303, 307}


def test_flag_off_da_404(client):
    login(client)
    _override(_FakeChatbot())
    r = client.get("/app/loja/agente/configuracao")
    assert r.status_code == 404


def test_vendedor_nao_configura_o_agente(client, config_on):
    """Quem atende usa o agente; quem configura é dono ou gerente."""
    login(client, papel="vendedor", email="vendedor@loja.test")
    _override(_FakeChatbot())
    r = client.get("/app/loja/agente/configuracao")
    assert r.status_code == 403


def test_dono_abre_a_tela(client, config_on):
    login(client)
    _override(_FakeChatbot())
    r = client.get("/app/loja/agente/configuracao")
    assert r.status_code == 200
    assert "Configuração do agente" in r.text


# --- formulário consciente do modo (spec §4.4.1) -----------------------------


def test_modo_1_nao_mostra_o_interruptor_de_followup(client, config_on):
    """Não existe worker de follow-up no Modo 1: o campo não pode aparecer."""
    login(client)
    _override(_FakeChatbot(modo="1"))
    r = client.get("/app/loja/agente/configuracao")
    assert "followup_ativo" not in r.text


def test_modo_2_mostra_followup_e_desabilita_fotos(client, config_on):
    """No Modo 2 não há tool de foto — o campo aparece desabilitado, com a razão
    à vista, em vez de configurar algo que não acontece."""
    login(client)
    _override(_FakeChatbot(modo="2"))
    r = client.get("/app/loja/agente/configuracao")
    assert "followup_ativo" in r.text
    assert 'name="fotos" disabled' in r.text
    assert "a central ainda não envia imagem" in r.text


# --- chatbot fora do ar não vira tela quebrada -------------------------------


def test_chatbot_fora_do_ar_mostra_estado_vazio(client, config_on):
    login(client)
    _override(_FakeChatbot(indisponivel=True))
    r = client.get("/app/loja/agente/configuracao")
    assert r.status_code == 200
    assert "indisponível" in r.text


# --- autosave ----------------------------------------------------------------


def test_autosave_manda_os_campos_e_devolve_conflitos(client, config_on):
    login(client)
    fake = _override(_FakeChatbot())
    pagina = client.get("/app/loja/agente/configuracao")
    r = client.put(
        "/app/loja/agente/configuracao.json",
        json={"csrf": csrf_da_resposta(pagina), "campos": CAMPOS},
    )
    assert r.status_code == 200
    assert r.json()["conflitos"] == ["parcela"]
    assert fake.salvos[0]["campos"] == CAMPOS
    assert fake.salvos[0]["autor"] == "dono@loja.test"


def test_autosave_sem_csrf_e_recusado(client, config_on):
    login(client)
    fake = _override(_FakeChatbot())
    r = client.put(
        "/app/loja/agente/configuracao.json", json={"csrf": "errado", "campos": CAMPOS}
    )
    assert r.status_code == 403
    assert fake.salvos == []


def test_autosave_sem_flag_nao_existe(client):
    login(client)
    _override(_FakeChatbot())
    r = client.put("/app/loja/agente/configuracao.json", json={"campos": CAMPOS})
    assert r.status_code == 404


# --- publicar e restaurar ----------------------------------------------------


def test_publicar_registra_quem_publicou(client, config_on):
    login(client)
    fake = _override(_FakeChatbot())
    pagina = client.get("/app/loja/agente/configuracao")
    r = client.post(
        "/app/loja/agente/configuracao/publicar",
        data={"csrf": csrf_da_resposta(pagina)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "ok=publicado" in r.headers["location"]
    assert fake.publicacoes == ["dono@loja.test"]


def test_publicar_sem_csrf_nao_publica(client, config_on):
    login(client)
    fake = _override(_FakeChatbot())
    r = client.post(
        "/app/loja/agente/configuracao/publicar",
        data={"csrf": "errado"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "erro=sessao" in r.headers["location"]
    assert fake.publicacoes == []


def test_restaurar_leva_a_versao_pedida(client, config_on):
    login(client)
    fake = _override(_FakeChatbot())
    pagina = client.get("/app/loja/agente/configuracao")
    r = client.post(
        "/app/loja/agente/configuracao/restaurar",
        data={"csrf": csrf_da_resposta(pagina), "versao_id": "v1"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "ok=restaurado" in r.headers["location"]
    assert fake.restauracoes == ["v1"]


def test_restaurar_versao_de_outra_loja_nao_vaza(client, config_on):
    """O 404 do chatbot é o isolamento por loja chegando à tela — e a tela diz
    'não existe mais', não 'sem permissão': quem pergunta não fica sabendo que a
    versão existe em outro lugar."""
    login(client)
    _override(_FakeChatbot(versao_ausente=True))
    pagina = client.get("/app/loja/agente/configuracao")
    r = client.post(
        "/app/loja/agente/configuracao/restaurar",
        data={"csrf": csrf_da_resposta(pagina), "versao_id": "de-outra-loja"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "erro=versao" in r.headers["location"]


def test_link_reciproco_aparece_na_tela_vizinha(client, config_on):
    """Rota irmã + link no cabeçalho é o padrão da casa; não existe componente
    de abas no app.css e inventar um é decisão de design, não implementação."""
    login(client)
    _override(_FakeChatbot())
    r = client.get("/app/loja/agente")
    assert "/app/loja/agente/configuracao" in r.text


def test_campo_invalido_e_422_com_o_nome_do_campo(client, config_on):
    """Sem isto o 422 do chatbot virava `ChatbotIndisponivel` e a tela dizia
    "não foi possível salvar agora" — culpando a conexão por um campo errado e
    sem dizer qual. Achado no navegador, com horário sem zero à esquerda."""
    login(client)
    _override(_FakeChatbot(campos_invalidos=["horario"]))
    pagina = client.get("/app/loja/agente/configuracao")
    r = client.put(
        "/app/loja/agente/configuracao.json",
        json={"csrf": csrf_da_resposta(pagina), "campos": CAMPOS},
    )
    assert r.status_code == 422
    assert r.json()["campos"] == ["horario"]
