"""O Portal fala com o chatbot pela credencial da loja da SESSÃO, não por uma só.

O bug que originou estes testes: com a loja `teste` selecionada, a página do
Agente mostrava 1104 atendimentos — os da `moto-center`, número a número. A
causa não era a tela: ``get_chatbot_client`` montava o cliente com
``settings.chatbot_token``, um token global, e **o chatbot resolve a loja pelo
token**. A dependência nem recebia o ``Request``, então não tinha como saber
qual loja estava selecionada.

A premissa expirou, e estava escrita em ``config.py``: "vazio (hoje, deploy de
uma loja só) preserva o comportamento atual". O seletor de lojas transformou
uma loja por deploy em três lojas num deploy só.
"""
import json

from app.config import Settings


def _settings(**kwargs) -> Settings:
    base = dict(chatbot_token="TOKEN-GLOBAL")
    base.update(kwargs)
    return Settings(**base)


class TestTokenPorLoja:
    def test_mapa_escolhe_o_token_da_loja(self):
        s = _settings(
            chatbot_tokens_json=json.dumps(
                {"teste": "TOKEN-TESTE", "moto-center": "TOKEN-MOTO"}
            )
        )
        assert s.chatbot_token_para("teste") == "TOKEN-TESTE"
        assert s.chatbot_token_para("moto-center") == "TOKEN-MOTO"

    def test_loja_fora_do_mapa_falha_fechado(self):
        """Devolver o token global aqui é exatamente o bug: a loja veria a outra."""
        s = _settings(chatbot_tokens_json=json.dumps({"moto-center": "TOKEN-MOTO"}))
        assert s.chatbot_token_para("teste") == ""

    def test_mapa_corrompido_falha_fechado(self):
        s = _settings(chatbot_tokens_json="{isto nao e json")
        assert s.chatbot_token_para("moto-center") == ""

    def test_sem_mapa_e_sem_declaracao_mantem_o_token_global(self):
        """Contrato de deploy de uma loja só: não quebrar quem não configurou.

        É o que impede este conserto de derrubar o Portal no deploy — e é o
        motivo de ele não bastar sozinho: sem o mapa, o vazamento continua.
        """
        assert _settings().chatbot_token_para("qualquer") == "TOKEN-GLOBAL"

    def test_declaracao_de_loja_sozinha_ja_protege(self):
        """``CHATBOT_API_LOJA_SLUG`` é o meio-termo de quem tem um token só."""
        s = _settings(chatbot_loja_slug="moto-center")
        assert s.chatbot_token_para("moto-center") == "TOKEN-GLOBAL"
        assert s.chatbot_token_para("teste") == ""

    def test_slug_vazio_nao_pesca_token_no_mapa(self):
        s = _settings(chatbot_tokens_json=json.dumps({"": "TOKEN-VAZIO"}))
        assert s.chatbot_token_para("") == ""
        assert s.chatbot_token_para(None) == ""


class TestDependencia:
    """O ponto exato do bug: a dependência não recebia o Request."""

    @staticmethod
    def _request(session: dict):
        class _Req:
            def __init__(self, s):
                self.session = s
        return _Req(session)

    def test_cliente_usa_o_token_da_loja_da_sessao(self, monkeypatch):
        from app import main as main_mod

        cfg = _settings(
            chatbot_tokens_json=json.dumps(
                {"teste": "TOKEN-TESTE", "moto-center": "TOKEN-MOTO"}
            )
        )
        monkeypatch.setattr(main_mod, "settings", cfg)

        cliente = main_mod.get_chatbot_client(self._request({"loja_slug": "teste"}))
        assert cliente.token == "TOKEN-TESTE"

        outro = main_mod.get_chatbot_client(self._request({"loja_slug": "moto-center"}))
        assert outro.token == "TOKEN-MOTO"

    def test_sessao_sem_loja_fica_indisponivel_em_vez_de_vazar(self, monkeypatch):
        """A regressão de 1104 atendimentos: melhor mudo que mostrando a outra loja."""
        from app import main as main_mod
        from app.clients.chatbot import ChatbotIndisponivel

        cfg = _settings(chatbot_tokens_json=json.dumps({"moto-center": "TOKEN-MOTO"}))
        monkeypatch.setattr(main_mod, "settings", cfg)

        cliente = main_mod.get_chatbot_client(self._request({}))
        assert cliente.configurado is False
        try:
            cliente.resumo_atendimento()
        except ChatbotIndisponivel:
            pass
        else:  # pragma: no cover
            raise AssertionError("deveria levantar ChatbotIndisponivel, nao chamar a API")


def test_login_ja_deixa_a_loja_na_sessao():
    """Sem isto, o primeiro request após o login cai em "indisponível".

    A loja era preenchida por ``ensure_session_loja``, que roda dentro de
    ``contexto()`` — depois do handler já ter chamado o chatbot.
    """
    from types import SimpleNamespace

    from app.auth import iniciar_sessao

    req = SimpleNamespace(session={})
    iniciar_sessao(req, SimpleNamespace(id="u1", loja_slug="teste"))

    assert req.session["loja_slug"] == "teste"
    assert req.session["usuario_id"] == "u1"


def test_login_sem_loja_no_usuario_nao_inventa():
    from types import SimpleNamespace

    from app.auth import iniciar_sessao

    req = SimpleNamespace(session={})
    iniciar_sessao(req, SimpleNamespace(id="u2", loja_slug=""))

    assert "loja_slug" not in req.session
