"""Isolamento das credenciais bancárias por loja (Portal -> Motor).

O bug: a tela Acessos dos bancos (`/app/financeiras`) auditava com
`loja_slug`, mas a credencial em si era global — `get_motor_client` montava
o cliente com `settings.motor_token`, um token só para o deploy inteiro. O
Motor resolve o tenant (cliente_id) **pelo token**, então toda loja listava
e alterava as credenciais bancárias da mesma conta — o mesmo vazamento já
visto no chatbot (a `teste` exibiu os 1104 atendimentos da `moto-center`).

O conserto segue o precedente multiloja do próprio Portal
(`CHATBOT_API_TOKENS_JSON`): `MOTOR_TOKENS_JSON`, mapa `loja_slug -> token`,
resolvido pela loja da SESSÃO. Loja fora do mapa falha fechado — nunca cai
no token global como fallback silencioso. Sem mapa, o token global vale: é
o contrato de "deploy de uma loja só".
"""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.clients import motor as motor_mod
from app.config import Settings
from conftest import csrf_da_resposta, login


def _settings(**kwargs) -> Settings:
    base = dict(motor_token="TOKEN-GLOBAL")
    base.update(kwargs)
    return Settings(**base)


class TestMotorTokenPorLoja:
    def test_mapa_escolhe_o_token_da_loja(self):
        s = _settings(
            motor_tokens_json=json.dumps({"loja-a": "TOK-A", "loja-b": "TOK-B"})
        )
        assert s.motor_token_para("loja-a") == "TOK-A"
        assert s.motor_token_para("loja-b") == "TOK-B"

    def test_loja_fora_do_mapa_falha_fechado(self):
        """Devolver o token global aqui é exatamente o bug: a loja operaria
        sobre a conta bancária da outra."""
        s = _settings(motor_tokens_json=json.dumps({"loja-a": "TOK-A"}))
        assert s.motor_token_para("loja-b") == ""

    def test_mapa_corrompido_falha_fechado(self):
        s = _settings(motor_tokens_json="{isto nao e json")
        assert s.motor_token_para("loja-a") == ""

    def test_mapa_nao_dict_falha_fechado(self):
        s = _settings(motor_tokens_json='["TOK-A"]')
        assert s.motor_token_para("loja-a") == ""

    def test_sem_mapa_mantem_o_token_global(self):
        """Contrato de deploy de uma loja só: não quebrar quem não configurou."""
        assert _settings().motor_token_para("qualquer") == "TOKEN-GLOBAL"
        assert _settings(motor_tokens_json="").motor_token_para("loja-a") == "TOKEN-GLOBAL"

    def test_slug_vazio_nao_pesca_token_no_mapa(self):
        s = _settings(motor_tokens_json=json.dumps({"": "TOK-VAZIO", "loja-a": "TOK-A"}))
        assert s.motor_token_para("") == ""
        assert s.motor_token_para(None) == ""


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
            motor_tokens_json=json.dumps({"loja-a": "TOK-A", "loja-b": "TOK-B"})
        )
        monkeypatch.setattr(main_mod, "settings", cfg)

        cliente = main_mod.get_motor_client(self._request({"loja_slug": "loja-a"}))
        assert cliente.token == "TOK-A"

        outro = main_mod.get_motor_client(self._request({"loja_slug": "loja-b"}))
        assert outro.token == "TOK-B"

    def test_sessao_sem_loja_fica_indisponivel_em_vez_de_vazar(self, monkeypatch):
        """Melhor mudo que operando sobre a conta de outra loja — e nunca o global."""
        from app import main as main_mod
        from app.clients.motor import MotorIndisponivel

        cfg = _settings(motor_tokens_json=json.dumps({"loja-a": "TOK-A"}))
        monkeypatch.setattr(main_mod, "settings", cfg)

        cliente = main_mod.get_motor_client(self._request({}))
        assert cliente.token == ""
        assert cliente.configurado is False
        try:
            cliente.listar_credenciais(ator="dono@loja.test")
        except MotorIndisponivel:
            pass
        else:  # pragma: no cover
            raise AssertionError("deveria levantar MotorIndisponivel, nao chamar a API")

    def test_sem_mapa_sessao_qualquer_usa_global(self, monkeypatch):
        """Com mapa vazio, o comportamento atual é preservado (loja única)."""
        from app import main as main_mod

        monkeypatch.setattr(main_mod, "settings", _settings())

        cliente = main_mod.get_motor_client(self._request({"loja_slug": "loja-a"}))
        assert cliente.token == "TOKEN-GLOBAL"
        assert cliente.configurado is True


# --- Isolamento ponta a ponta (rotas reais + HTTP do Motor emulado por token) ---


class _RespostaFake:
    def __init__(self, status=200, carga=None):
        self.status_code = status
        self._carga = carga if carga is not None else {}
        self.content = b"{}" if status != 204 else b""
        self.headers = {}

    def json(self):
        return self._carga

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPError(f"motor emulado: http {self.status_code}")


def _cred(provedor, usuario):
    return {
        "provedor": provedor,
        "usuario": usuario,
        "senha_configurada": True,
        "senha_mascara": "****",
        "habilitado": True,
        "atualizado_em": "2026-07-10T12:00:00+00:00",
        "ultimo_sucesso_em": None,
        "ultimo_erro_sanitizado": None,
        "falhas_login": 0,
    }


def _prov(nome, rotulo):
    return {
        "nome": nome,
        "rotulo": rotulo,
        "habilitado": True,
        "real": True,
        "modo": "playwright",
        "campos_credencial": [
            {"nome": "usuario", "rotulo": "Usuário", "secreto": False},
            {"nome": "senha", "rotulo": "Senha", "secreto": True},
        ],
    }


class _MundoMotor:
    """Motor emulado com tenancy por Bearer: cada token enxerga só a própria conta."""

    def __init__(self):
        self.chamadas: list[dict] = []
        self.simulacoes: list[dict] = []
        self.contas = {
            "TOK-A": {
                "creds": [_cred("pan", "LOJA-A-USER")],
                "provs": [_prov("pan", "Banco PAN")],
            },
            "TOK-B": {
                "creds": [_cred("pan", "LOJA-B-USER")],
                "provs": [_prov("pan", "Banco PAN")],
            },
        }

    def rotear(self, method, path, token, corpo):
        self.chamadas.append(
            {"method": method, "path": path, "token": token, "corpo": corpo}
        )
        conta = self.contas.get(token)
        if conta is None:
            return _RespostaFake(401, {"erro": {"message": "não autorizado"}})
        if method == "GET" and path == "/v1/provedores/credenciais":
            return _RespostaFake(200, {"credenciais": [dict(c) for c in conta["creds"]]})
        if method == "GET" and path == "/v1/provedores":
            return _RespostaFake(200, {"provedores": list(conta["provs"])})
        if method == "PUT" and path.startswith("/v1/provedores/"):
            nome = path.split("/")[3]
            for item in conta["creds"]:
                if item["provedor"] == nome:
                    item["usuario"] = (corpo or {}).get("usuario")
                    return _RespostaFake(200, dict(item))
            novo = _cred(nome, (corpo or {}).get("usuario"))
            conta["creds"].append(novo)
            return _RespostaFake(200, dict(novo))
        if method == "POST" and path == "/v1/simulacoes":
            self.simulacoes.append({"token": token, "payload": corpo})
            return _RespostaFake(
                200,
                {"id": "sim-1", "status": "recebida", "criada_em": "2026-07-13T12:00:00+00:00"},
            )
        return _RespostaFake(404, {"erro": {"message": "rota desconhecida"}})


@pytest.fixture
def mundo_motor(monkeypatch):
    from types import SimpleNamespace

    from app import main as main_mod

    mundo = _MundoMotor()

    def _fabrica_cliente(base_url="", headers=None, timeout=None):
        auth = (headers or {}).get("Authorization", "")

        class _Cliente:
            token = auth[7:] if auth.startswith("Bearer ") else ""

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def request(self, method, path, **kwargs):
                return mundo.rotear(method, path, self.token, kwargs.get("json"))

            def get(self, path, **kwargs):
                return mundo.rotear("GET", path, self.token, None)

        return _Cliente()

    monkeypatch.setattr(
        motor_mod, "httpx", SimpleNamespace(Client=_fabrica_cliente, HTTPError=httpx.HTTPError)
    )
    monkeypatch.setattr(
        main_mod,
        "settings",
        _settings(
            motor_url="http://motor-emulado",
            motor_tokens_json=json.dumps({"loja-a": "TOK-A", "loja-b": "TOK-B"}),
        ),
    )
    return mundo


@pytest.fixture
def client_motor_real(estoque_fake, chatbot_fake):
    """TestClient sem o override do Motor: vale a resolução por loja de verdade."""
    from app.main import app

    with TestClient(app) as cliente:
        yield cliente


def _login_loja(client, loja, email=None):
    email = email or f"dono@{loja}.test"
    login(client, papel="dono", email=email, loja_slug=loja)


class TestIsolamentoEntreLojas:
    def test_loja_a_nao_lista_credencial_da_loja_b(self, client_motor_real, mundo_motor):
        _login_loja(client_motor_real, "loja-a")
        resposta = client_motor_real.get("/app/financeiras")
        assert resposta.status_code == 200
        assert "LOJA-A-USER" in resposta.text
        assert "LOJA-B-USER" not in resposta.text

        _login_loja(client_motor_real, "loja-b")
        resposta = client_motor_real.get("/app/financeiras")
        assert resposta.status_code == 200
        assert "LOJA-B-USER" in resposta.text
        assert "LOJA-A-USER" not in resposta.text

        tokens = {c["token"] for c in mundo_motor.chamadas}
        assert tokens <= {"TOK-A", "TOK-B"}
        assert "TOKEN-GLOBAL" not in tokens

    def test_loja_fora_do_mapa_nao_lista_nada_e_nem_chama_o_motor(
        self, client_motor_real, mundo_motor, monkeypatch
    ):
        from app import main as main_mod

        monkeypatch.setattr(
            main_mod,
            "settings",
            _settings(
                motor_url="http://motor-emulado",
                motor_tokens_json=json.dumps({"loja-a": "TOK-A"}),
            ),
        )
        _login_loja(client_motor_real, "loja-c")
        resposta = client_motor_real.get("/app/financeiras")
        assert resposta.status_code == 200
        assert "LOJA-A-USER" not in resposta.text
        assert "desligada para esta loja" in resposta.text
        # Fail-closed: o Motor nem foi chamado — e nunca com o token global.
        assert mundo_motor.chamadas == []

    def test_upsert_da_loja_a_nao_toca_conta_da_loja_b(
        self, client_motor_real, mundo_motor, db
    ):
        from app.models import LojaOperacaoAuditoria

        _login_loja(client_motor_real, "loja-a")
        pagina = client_motor_real.get("/app/financeiras")
        csrf = csrf_da_resposta(pagina)
        resposta = client_motor_real.post(
            "/app/financeiras/pan",
            data={"csrf": csrf, "usuario": "LOJA-A-NOVO", "senha": "segredo-a"},
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        assert "ok=salvo" in resposta.headers["location"]

        puts = [c for c in mundo_motor.chamadas if c["method"] == "PUT"]
        assert len(puts) == 1
        assert puts[0]["token"] == "TOK-A"
        assert puts[0]["corpo"]["usuario"] == "LOJA-A-NOVO"
        # A senha viajou só no corpo servidor -> Motor, nunca na auditoria.
        assert mundo_motor.contas["TOK-B"]["creds"][0]["usuario"] == "LOJA-B-USER"

        linha = (
            db.query(LojaOperacaoAuditoria)
            .filter(
                LojaOperacaoAuditoria.dominio == "financeira",
                LojaOperacaoAuditoria.acao == "upsert",
                LojaOperacaoAuditoria.success.is_(True),
            )
            .one()
        )
        assert linha.loja_slug == "loja-a"
        assert linha.provedor == "pan"

    def test_loja_fora_do_mapa_nao_faz_upsert(self, client_motor_real, mundo_motor, monkeypatch):
        from app import main as main_mod

        monkeypatch.setattr(
            main_mod,
            "settings",
            _settings(
                motor_url="http://motor-emulado",
                motor_tokens_json=json.dumps({"loja-a": "TOK-A"}),
            ),
        )
        _login_loja(client_motor_real, "loja-c")
        app_pagina = client_motor_real.get("/app")
        csrf = csrf_da_resposta(app_pagina)
        resposta = client_motor_real.post(
            "/app/financeiras/pan",
            data={"csrf": csrf, "usuario": "INVASOR", "senha": "x"},
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        assert "erro=motor" in resposta.headers["location"]
        assert mundo_motor.chamadas == []
        assert mundo_motor.contas["TOK-A"]["creds"][0]["usuario"] == "LOJA-A-USER"

    def test_simulacao_usa_o_token_da_propria_loja(self, client_motor_real, mundo_motor):
        _login_loja(client_motor_real, "loja-b")
        pagina = client_motor_real.get("/app/simulacoes")
        assert pagina.status_code == 200
        csrf = csrf_da_resposta(pagina)
        resposta = client_motor_real.post(
            "/app/simulacoes",
            data={
                "csrf": csrf,
                "provedores": "pan",
                "cpf": "52998224725",
                "nascimento": "1990-05-01",
                "celular": "11987654321",
                "cnh": "sim",
                "valor": "25000",
                "prazos_meses": "24,36",
                "entrada": "5000",
                "categoria": "moto",
                "uf_licenciamento": "SP",
            },
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        assert "/app/simulacoes/job/" in resposta.headers["location"]

        posts = [
            c for c in mundo_motor.chamadas if c["method"] == "POST" and c["path"] == "/v1/simulacoes"
        ]
        assert len(posts) == 1
        assert posts[0]["token"] == "TOK-B"

    def test_simulacao_da_loja_sem_token_nao_chama_o_motor(
        self, client_motor_real, mundo_motor, monkeypatch
    ):
        from app import main as main_mod

        monkeypatch.setattr(
            main_mod,
            "settings",
            _settings(
                motor_url="http://motor-emulado",
                motor_tokens_json=json.dumps({"loja-a": "TOK-A"}),
            ),
        )
        _login_loja(client_motor_real, "loja-c")
        pagina = client_motor_real.get("/app/simulacoes")
        csrf = csrf_da_resposta(pagina)
        resposta = client_motor_real.post(
            "/app/simulacoes",
            data={
                "csrf": csrf,
                "provedores": "pan",
                "cpf": "52998224725",
                "nascimento": "1990-05-01",
                "celular": "11987654321",
                "cnh": "sim",
                "valor": "25000",
                "prazos_meses": "24,36",
                "entrada": "5000",
                "categoria": "moto",
                "uf_licenciamento": "SP",
            },
            follow_redirects=False,
        )
        assert resposta.status_code == 422
        assert "Nenhum banco com acesso configurado" in resposta.text
        assert mundo_motor.chamadas == []


class TestOrdemCofrePrimeiro:
    """O cofre do Control resolve antes do mapa; o mapa é fallback legado.

    Loja nova funciona sem editar secret no Portal: com o cofre no ar, nem
    precisa existir entrada em ``MOTOR_TOKENS_JSON``.
    """

    @staticmethod
    def _request(session: dict):
        class _Req:
            def __init__(self, s):
                self.session = s

        return _Req(session)

    def _fixar(self, monkeypatch, mapa=None, cofre=None, explode=False):
        """Mapa em ``main.settings``; cofre como fake que registra chamadas."""
        from app import main as main_mod

        chamadas: list = []
        if mapa is None:
            cfg = _settings(motor_token="", motor_tokens_json="")
        else:
            cfg = _settings(motor_tokens_json=json.dumps(mapa))
        monkeypatch.setattr(main_mod, "settings", cfg)

        def _cofre_fake(slug):
            chamadas.append(slug)
            if explode:
                raise RuntimeError("control fora do ar")
            return cofre

        monkeypatch.setattr(main_mod, "buscar_motor_token_no_control", _cofre_fake)
        return chamadas

    def test_control_ganha_do_mapa(self, monkeypatch):
        from app import main as main_mod

        chamadas = self._fixar(
            monkeypatch, mapa={"loja-a": "TOK-MAPA"}, cofre="TOK-COFRE"
        )
        cliente = main_mod.get_motor_client(self._request({"loja_slug": "loja-a"}))
        assert cliente.token == "TOK-COFRE"
        # O cofre é consultado mesmo quando o mapa resolveria sozinho.
        assert chamadas == ["loja-a"]

    def test_control_vazio_cai_no_mapa(self, monkeypatch):
        from app import main as main_mod

        chamadas = self._fixar(monkeypatch, mapa={"loja-a": "TOK-MAPA"}, cofre="")
        cliente = main_mod.get_motor_client(self._request({"loja_slug": "loja-a"}))
        assert cliente.token == "TOK-MAPA"
        assert chamadas == ["loja-a"]

    def test_control_quebrado_nao_quebra_a_tela_e_cai_no_mapa(self, monkeypatch):
        """O fake do cofre nunca explode (fail-soft), mas a dependência não
        pode confiar nisso: exceção vira fallback, nunca 500."""
        from app import main as main_mod

        self._fixar(monkeypatch, mapa={"loja-a": "TOK-MAPA"}, explode=True)
        cliente = main_mod.get_motor_client(self._request({"loja_slug": "loja-a"}))
        assert cliente.token == "TOK-MAPA"
        assert cliente.configurado is True

    def test_ambos_vazios_fica_desligado(self, monkeypatch):
        from app import main as main_mod
        from app.clients.motor import MotorIndisponivel

        self._fixar(monkeypatch, mapa={"loja-a": "TOK-A"}, cofre="")
        cliente = main_mod.get_motor_client(self._request({"loja_slug": "loja-c"}))
        assert cliente.token == ""
        assert cliente.configurado is False
        try:
            cliente.listar_credenciais(ator="dono@loja.test")
        except MotorIndisponivel:
            pass
        else:  # pragma: no cover
            raise AssertionError("deveria levantar MotorIndisponivel, nao chamar a API")

    def test_loja_nova_sem_mapa_nem_global_usa_so_o_cofre(self, monkeypatch):
        from app import main as main_mod

        chamadas = self._fixar(monkeypatch, mapa=None, cofre="TOK-COFRE")
        cliente = main_mod.get_motor_client(self._request({"loja_slug": "loja-nova"}))
        assert cliente.token == "TOK-COFRE"
        assert chamadas == ["loja-nova"]


class _RespostaControlFake:
    def __init__(self, status=200, carga=None, json_erro=False):
        self.status_code = status
        self._carga = carga if carga is not None else {}
        self._json_erro = json_erro

    def json(self):
        if self._json_erro:
            raise ValueError("corpo inválido")
        return self._carga


def _control_http_fake(monkeypatch, resposta_ou_erro, chamadas: list):
    """Troca o httpx do cliente do cofre; registra base_url/timeout/headers."""
    from types import SimpleNamespace

    from app.clients import control as control_mod

    def _fabrica(base_url="", headers=None, timeout=None):
        chamadas.append({"base_url": base_url, "headers": headers, "timeout": timeout})

        class _Cliente:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, path, **kwargs):
                chamadas.append({"path": path, "headers": kwargs.get("headers")})
                if isinstance(resposta_ou_erro, Exception):
                    raise resposta_ou_erro
                return resposta_ou_erro

        return _Cliente()

    monkeypatch.setattr(
        control_mod,
        "httpx",
        SimpleNamespace(Client=_fabrica, HTTPError=httpx.HTTPError),
    )


class TestBuscarMotorTokenNoControl:
    COFRE = dict(
        base_url="http://control-emulado",
        service_token="SEGREDO-SERVICO",
        timeout=2.0,
    )

    def test_200_devolve_o_token_com_bearer(self, monkeypatch):
        from app.clients import control as control_mod

        chamadas: list = []
        _control_http_fake(
            monkeypatch, _RespostaControlFake(200, {"token": "TOK-COFRE"}), chamadas
        )
        assert control_mod.buscar_motor_token_no_control("loja-a", **self.COFRE) == (
            "TOK-COFRE"
        )
        assert chamadas[0]["base_url"] == "http://control-emulado"
        assert chamadas[0]["timeout"] == 2.0
        assert chamadas[1]["path"] == "/internal/motor-tokens/loja-a"
        assert chamadas[1]["headers"] == {"Authorization": "Bearer SEGREDO-SERVICO"}

    def test_404_devolve_vazio(self, monkeypatch):
        from app.clients import control as control_mod

        chamadas: list = []
        _control_http_fake(
            monkeypatch,
            _RespostaControlFake(404, {"erro": {"code": "sem_token"}}),
            chamadas,
        )
        assert control_mod.buscar_motor_token_no_control("loja-c", **self.COFRE) == ""

    def test_500_devolve_vazio_e_nao_vaza_token_no_log(self, monkeypatch, caplog):
        from app.clients import control as control_mod

        chamadas: list = []
        _control_http_fake(monkeypatch, _RespostaControlFake(503, {"erro": {}}), chamadas)
        with caplog.at_level("WARNING", logger="app.clients.control"):
            assert control_mod.buscar_motor_token_no_control("loja-a", **self.COFRE) == ""
        assert "SEGREDO-SERVICO" not in caplog.text
        assert "TOK-COFRE" not in caplog.text

    def test_timeout_devolve_vazio(self, monkeypatch):
        from app.clients import control as control_mod

        chamadas: list = []
        _control_http_fake(monkeypatch, httpx.HTTPError("tempo esgotado"), chamadas)
        assert control_mod.buscar_motor_token_no_control("loja-a", **self.COFRE) == ""

    def test_sem_config_nao_chama_http(self, monkeypatch):
        from app.clients import control as control_mod

        chamadas: list = []
        _control_http_fake(
            monkeypatch, _RespostaControlFake(200, {"token": "TOK-X"}), chamadas
        )
        sem_url = dict(self.COFRE, base_url="")
        assert control_mod.buscar_motor_token_no_control("loja-a", **sem_url) == ""
        sem_segredo = dict(self.COFRE, service_token="  ")
        assert control_mod.buscar_motor_token_no_control("loja-a", **sem_segredo) == ""
        assert control_mod.buscar_motor_token_no_control("", **self.COFRE) == ""
        assert control_mod.buscar_motor_token_no_control(None, **self.COFRE) == ""
        assert chamadas == []

    def test_200_sem_token_devolve_vazio(self, monkeypatch):
        from app.clients import control as control_mod

        chamadas: list = []
        _control_http_fake(monkeypatch, _RespostaControlFake(200, {}), chamadas)
        assert control_mod.buscar_motor_token_no_control("loja-a", **self.COFRE) == ""
        _control_http_fake(
            monkeypatch, _RespostaControlFake(200, {"token": "   "}), chamadas
        )
        assert control_mod.buscar_motor_token_no_control("loja-a", **self.COFRE) == ""
        _control_http_fake(
            monkeypatch,
            _RespostaControlFake(200, {"token": "x"}, json_erro=True),
            chamadas,
        )
        assert control_mod.buscar_motor_token_no_control("loja-a", **self.COFRE) == ""


class TestCofrePontaAPonta:
    """O token do cofre chega ao Motor sem passar pelo mapa."""

    def test_loja_nova_sem_mapa_lista_pelo_cofre(
        self, client_motor_real, mundo_motor, monkeypatch
    ):
        from types import SimpleNamespace

        from app import main as main_mod
        from app.clients import control as control_mod

        monkeypatch.setattr(
            main_mod,
            "settings",
            _settings(motor_url="http://motor-emulado", motor_token=""),
        )
        monkeypatch.setattr(
            control_mod,
            "settings",
            SimpleNamespace(
                revy_trafego_url="http://control-emulado",
                service_token="SEGREDO-SERVICO",
                control_motor_token_timeout=2.0,
            ),
        )
        chamadas: list = []
        _control_http_fake(
            monkeypatch, _RespostaControlFake(200, {"token": "TOK-A"}), chamadas
        )
        _login_loja(client_motor_real, "loja-nova")
        resposta = client_motor_real.get("/app/financeiras")
        assert resposta.status_code == 200
        assert "LOJA-A-USER" in resposta.text
        assert "desligada" not in resposta.text
        assert chamadas[1]["headers"] == {"Authorization": "Bearer SEGREDO-SERVICO"}
        assert chamadas[0]["timeout"] == 2.0
        so_motor = [c for c in mundo_motor.chamadas if c["token"] == "TOK-A"]
        assert so_motor, "o Motor deveria ter sido chamado com o token do cofre"

    def test_cofre_404_cai_no_mapa_na_tela(
        self, client_motor_real, mundo_motor, monkeypatch
    ):
        from types import SimpleNamespace

        from app import main as main_mod
        from app.clients import control as control_mod

        monkeypatch.setattr(
            main_mod,
            "settings",
            _settings(
                motor_url="http://motor-emulado",
                motor_tokens_json=json.dumps({"loja-a": "TOK-A"}),
            ),
        )
        monkeypatch.setattr(
            control_mod,
            "settings",
            SimpleNamespace(
                revy_trafego_url="http://control-emulado",
                service_token="SEGREDO-SERVICO",
                control_motor_token_timeout=2.0,
            ),
        )
        chamadas: list = []
        _control_http_fake(
            monkeypatch,
            _RespostaControlFake(404, {"erro": {"code": "sem_token"}}),
            chamadas,
        )
        _login_loja(client_motor_real, "loja-a")
        resposta = client_motor_real.get("/app/financeiras")
        assert resposta.status_code == 200
        assert "LOJA-A-USER" in resposta.text
        assert chamadas[1]["path"] == "/internal/motor-tokens/loja-a"
