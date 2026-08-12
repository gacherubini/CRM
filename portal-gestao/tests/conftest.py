import os
import re

import pytest
from fastapi.testclient import TestClient

os.environ["PORTAL_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["PORTAL_SESSION_SECRET"] = "segredo-de-teste"
os.environ["ESTOQUE_API_TOKEN"] = "token-de-teste"

os.environ["CHATBOT_API_TOKEN"] = "token-chatbot-teste"
# Job de spend Meta não deve rodar em background nos testes.
os.environ["PORTAL_META_SPEND_SYNC_ENABLED"] = "0"
os.environ["PORTAL_CAPI_RETRY_ENABLED"] = "0"
# Motor proativo do Copiloto não deve rodar em background nos testes.
os.environ["PORTAL_COPILOTO_SINAIS_ENABLED"] = "0"
# Worker de turnos do chat também não deve rodar sozinho em background: os
# testes chamam processar_turno/run_once diretamente, de forma determinística.
os.environ["PORTAL_COPILOTO_TURNOS_ENABLED"] = "0"
# Idem para o purge de retenção: os testes chamam run_once diretamente.
os.environ["PORTAL_COPILOTO_PURGE_ENABLED"] = "0"
# Mantém UI técnica de tráfego nos testes de regressão (CAPI/campanhas ainda no código).
# Testes do slim do portal (cliente sem menus técnicos) desligam com monkeypatch.
os.environ["PORTAL_TRAFEGO_UI_LEGACY"] = "1"

from app.auth import hash_senha  # noqa: E402
from app.clients.chatbot import (  # noqa: E402
    ChatbotIndisponivel,
    ConversaNaoEncontrada,
    LeadNaoEncontrado,
    SimulacaoIndisponivel,
)
from app.clients.estoque import (  # noqa: E402
    ConflitoEstoque,
    EstoqueIndisponivel,
    VeiculoNaoEncontrado,
)
from app.clients.motor import CredencialNaoEncontrada, MotorIndisponivel  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.loja.copiloto import notificacoes as copiloto_notificacoes  # noqa: E402
from app.loja.copiloto.cache import cache_overview  # noqa: E402
from app.main import app, get_chatbot_client, get_estoque_client, get_motor_client  # noqa: E402
from app.models import LojaOperacionalProjecao, Usuario  # noqa: E402


class EstoqueFake:
    def __init__(self):
        self.veiculos = [
            {
                "id": "v1", "tipo": "carro", "marca": "Honda", "modelo": "Civic",
                "versao": "EX", "ano_modelo": 2022, "cor": "Preto", "km": 22000,
                "preco": 118900.0, "custo": 102000.0, "codigo_interno": "H01",
                "foto_url": None, "status": "disponivel", "publicado": True,
            },
            {
                "id": "v2", "tipo": "moto", "marca": "Yamaha", "modelo": "MT-03",
                "versao": None, "ano_modelo": 2024, "cor": "Azul", "km": 800,
                "preco": 31900.0, "custo": None, "codigo_interno": None,
                "foto_url": None, "status": "reservado", "publicado": False,
            },
        ]
        self.criados = []
        self.acoes = []
        self.indisponivel = False
        self.conflito_ao_vender = False
        self.atualizar_nao_encontrado = False
        self.atualizar_conflito = False
        self.loja_slug = "loja-teste"

    def obter_loja(self):
        if self.indisponivel:
            raise EstoqueIndisponivel("Não foi possível acessar o estoque agora")
        return {"slug": self.loja_slug, "nome": "Loja Teste"}

    def listar(self, **filtros):
        if self.indisponivel:
            raise EstoqueIndisponivel("Não foi possível acessar o estoque agora")
        itens = self.veiculos
        for campo in ("tipo", "status"):
            if filtros.get(campo):
                itens = [v for v in itens if v[campo] == filtros[campo]]
        if filtros.get("publicado") is not None:
            itens = [v for v in itens if v["publicado"] == filtros["publicado"]]
        if filtros.get("busca"):
            termo = filtros["busca"].lower()
            itens = [v for v in itens if termo in f"{v['marca']} {v['modelo']}".lower()]
        return itens

    def obter(self, veiculo_id):
        if self.indisponivel:
            raise EstoqueIndisponivel("Não foi possível acessar o estoque agora")
        try:
            return next(v for v in self.veiculos if v["id"] == veiculo_id)
        except StopIteration as exc:
            raise VeiculoNaoEncontrado("veículo não encontrado") from exc

    def criar(self, dados):
        self.criados.append(dados)
        return {"id": "novo", **dados}

    def atualizar(self, veiculo_id, dados):
        if self.indisponivel:
            raise EstoqueIndisponivel("Não foi possível acessar o estoque agora")
        if self.atualizar_nao_encontrado:
            raise VeiculoNaoEncontrado("veículo não encontrado")
        if self.atualizar_conflito:
            raise ConflitoEstoque("veículo em estado incompatível")
        return {"id": veiculo_id, **dados}

    def acao(self, veiculo_id, acao):
        if self.indisponivel:
            raise EstoqueIndisponivel("Não foi possível acessar o estoque agora")
        veiculo = self.obter(veiculo_id)
        if acao == "vender" and (self.conflito_ao_vender or veiculo["status"] == "vendido"):
            raise ConflitoEstoque("veículo em estado incompatível")
        self.acoes.append((veiculo_id, acao))
        if acao == "vender":
            veiculo["status"] = "vendido"
            veiculo["publicado"] = False
        return {"ok": True}


class ChatbotFake:
    def __init__(self):
        self.leads = [
            {
                "id": "l1", "telefone": "5511987654321", "nome": "Maria Silva",
                "interesse": "Honda Civic 2022", "etapa": "novo",
                "consentimento_em": "2026-07-10T12:00:00", "criada_em": "2026-07-09T09:00:00",
                "origem": "catalogo", "canal": "site", "utm_source": "google",
                "utm_medium": "cpc", "utm_campaign": "seminovos-julho",
                "utm_content": "civic", "utm_term": "honda usado",
                "veiculo_ref": "v1", "catalog_interest_ref": "CAT-ABC123",
            },
            {
                "id": "l2", "telefone": "5511911112222", "nome": "Joao Oculto",
                "interesse": None, "etapa": "em_atendimento",
                "consentimento_em": None, "criada_em": "2026-07-11T10:00:00",
            },
        ]
        self.indisponivel = False
        self.conversas = [
            {
                "id": "c1", "telefone": "5511987654321", "bot_ativo": True,
                "status": "aberta", "atualizada_em": "2026-07-12T14:00:00+00:00",
                "ultima_mensagem": {"texto": "Tem Civic disponível?", "criada_em": "2026-07-12T14:00:00+00:00", "direcao": "entrada"},
                "canal_id": "canal-principal",
                "evolution_instance": "loja-teste-wa",
                "canal_label": "***0001",
                "numero_mascarado": "***0001",
                "canal_ativo": True,
                "canal_estado": "conectado",
            },
            {
                "id": "c2", "telefone": "5511911112222", "bot_ativo": False,
                "status": "handoff", "atualizada_em": "2026-07-12T13:00:00+00:00",
                "ultima_mensagem": None,
                "canal_id": "canal-principal",
                "evolution_instance": "loja-teste-wa",
                "canal_label": "***0001",
                "numero_mascarado": "***0001",
                "canal_ativo": True,
                "canal_estado": "conectado",
            },
        ]
        self.canais = [
            {
                "id": "canal-principal",
                "e164_or_label": "5511999990001",
                "evolution_instance": "loja-teste-wa",
                "ativo": True,
                "estado": "conectado",
            },
            {
                "id": "canal-secundario",
                "e164_or_label": "linha-2",
                "evolution_instance": "loja-teste-wa-2",
                "ativo": True,
                "estado": "conectado",
            },
        ]
        self.mensagens = {
            "5511987654321": [
                {
                    "id": "msg-m1",
                    "direcao": "entrada",
                    "texto": "Tem Civic disponível?",
                    "criada_em": "2026-07-12T14:00:00+00:00",
                },
                {
                    "id": "msg-m2",
                    "direcao": "saida",
                    "texto": "Temos sim!",
                    "criada_em": "2026-07-12T14:01:00+00:00",
                },
            ],
        }
        self.estados = {
            "5511987654321": {"bot_ativo": True, "status": "aberta"},
            "5511911112222": {"bot_ativo": False, "status": "handoff"},
        }
        self.handoffs = []
        self.last_handoff_instance = None
        self.simulacao_indisponivel = False
        self.simulacoes = []
        self.etapas_atualizadas = []
        self.eventos_funil = []
        self.numeros_cadastro = []
        self.grupo_estoque = {
            "selecionado": None,
            "grupos": [
                {"jid": "120363001@g.us", "nome": "Equipe Estoque"},
                {"jid": "120363002@g.us", "nome": "Vendas"},
            ],
            "aviso": None,
        }

    def listar_leads(self, etapa=None):
        if self.indisponivel:
            raise ChatbotIndisponivel("Não foi possível acessar os leads agora")
        itens = self.leads
        if etapa:
            itens = [lead for lead in itens if lead["etapa"] == etapa]
        return itens

    def obter_lead(self, lead_id):
        if self.indisponivel:
            raise ChatbotIndisponivel("Não foi possível acessar os leads agora")
        for lead in self.leads:
            if lead["id"] == lead_id:
                return lead
        raise LeadNaoEncontrado("Lead não encontrado")

    def atualizar_etapa_lead(self, lead_id, etapa):
        if self.indisponivel:
            raise ChatbotIndisponivel("Não foi possível acessar os leads agora")
        lead = self.obter_lead(lead_id)
        lead["etapa"] = etapa
        self.etapas_atualizadas.append((lead_id, etapa))
        return lead

    def listar_eventos_funil(self, limit=500, offset=0):
        if self.indisponivel:
            raise ChatbotIndisponivel("Não foi possível acessar o chatbot agora")
        return self.eventos_funil[offset : offset + limit]

    def listar_conversas(self, busca=None, limit=50, offset=0, *, canal_id=None):
        if self.indisponivel:
            raise ChatbotIndisponivel("Não foi possível acessar o chatbot agora")
        itens = self.conversas
        if busca:
            itens = [c for c in itens if busca in c["telefone"]]
        if canal_id:
            itens = [c for c in itens if c.get("canal_id") == canal_id]
        return itens

    def listar_canais_whatsapp(self):
        if self.indisponivel:
            raise ChatbotIndisponivel("Não foi possível acessar o chatbot agora")
        return list(self.canais)

    def registrar_canal_whatsapp(self, label):
        if self.indisponivel:
            raise ChatbotIndisponivel("Não foi possível acessar o chatbot agora")
        canal = {
            "id": f"c{len(self.canais) + 1}",
            "e164_or_label": label,
            "evolution_instance": f"loja-teste-{len(self.canais) + 1}",
            "ativo": True,
            "estado": "pendente",
        }
        self.canais.append(canal)
        return dict(canal)

    def conectar_canal_whatsapp(self, canal_id):
        if self.indisponivel:
            raise ChatbotIndisponivel("Não foi possível acessar o chatbot agora")
        canal = self._canal(canal_id)
        canal["estado"] = "pendente"
        return {**canal, "qr_payload": "QR-FAKE", "expires_in_seconds": 60}

    def desconectar_canal_whatsapp(self, canal_id):
        canal = self._canal(canal_id)
        canal["estado"] = "desconectado"
        return dict(canal)

    def inativar_canal_whatsapp(self, canal_id):
        canal = self._canal(canal_id)
        canal["ativo"] = False
        canal["estado"] = "inativo"
        return dict(canal)

    def obter_status_canal_whatsapp(self, canal_id):
        return dict(self._canal(canal_id))

    def _canal(self, canal_id):
        return next(c for c in self.canais if c["id"] == canal_id)

    def _mensagens_da_conversa(self, telefone, *, canal_id=None, instance=None):
        # Multi-WA: chave opcional (telefone, canal_id) se o fake tiver dict aninhado.
        msgs = self.mensagens.get(telefone)
        if isinstance(msgs, dict) and not isinstance(msgs, list):
            chave = canal_id or instance or next(iter(msgs), None)
            if chave is None or chave not in msgs:
                raise ConversaNaoEncontrada("conversa não encontrada")
            return list(msgs[chave])
        if msgs is None:
            raise ConversaNaoEncontrada("conversa não encontrada")
        return list(msgs)

    def listar_mensagens(
        self,
        telefone,
        limit=200,
        offset=0,
        *,
        canal_id=None,
        instance=None,
        after_id=None,
        after_criada_em=None,
    ):
        if self.indisponivel:
            raise ChatbotIndisponivel("Não foi possível acessar o chatbot agora")
        msgs = self._mensagens_da_conversa(
            telefone, canal_id=canal_id, instance=instance
        )
        if after_id:
            idx = next(
                (i for i, m in enumerate(msgs) if m.get("id") == after_id), None
            )
            if idx is None:
                raise ConversaNaoEncontrada("cursor after_id não encontrado")
            msgs = msgs[idx + 1 :]
        elif after_criada_em:
            msgs = [
                m
                for m in msgs
                if (m.get("criada_em") or "") > after_criada_em
            ]
        else:
            msgs = msgs[offset : offset + limit]
            return msgs
        return msgs[:limit]

    def listar_mensagens_envelope(
        self,
        telefone,
        limit=200,
        offset=0,
        *,
        canal_id=None,
        instance=None,
        after_id=None,
        after_criada_em=None,
    ):
        msgs = self.listar_mensagens(
            telefone,
            limit=limit,
            offset=offset,
            canal_id=canal_id,
            instance=instance,
            after_id=after_id,
            after_criada_em=after_criada_em,
        )
        last_id = msgs[-1].get("id") if msgs else after_id
        return {
            "telefone": telefone,
            "canal_id": canal_id,
            "mensagens": msgs,
            "after_id": after_id,
            "after_criada_em": after_criada_em if not after_id else None,
            "last_id": last_id,
            "limit": limit,
            "offset": offset,
        }

    def obter_estado(self, telefone, *, canal_id=None, instance=None):
        return self.estados.get(telefone, {"bot_ativo": True, "status": "aberta"})

    def definir_bot_ativo(self, telefone, bot_ativo, *, instance=None):
        if self.indisponivel:
            raise ChatbotIndisponivel("Não foi possível acessar o chatbot agora")
        self.handoffs.append((telefone, bot_ativo))
        self.last_handoff_instance = instance
        self.estados[telefone] = {"bot_ativo": bot_ativo, "status": "aberta" if bot_ativo else "handoff"}
        # Mantém resumo da conversa alinhado com o estado (workspace UI).
        for conv in self.conversas:
            if conv.get("telefone") == telefone:
                if instance and conv.get("evolution_instance") not in (None, instance):
                    continue
                conv["bot_ativo"] = bot_ativo
                conv["status"] = "aberta" if bot_ativo else "handoff"
        return self.estados[telefone]

    def listar_numeros_cadastro(self):
        if self.indisponivel:
            raise ChatbotIndisponivel("Não foi possível acessar o chatbot agora")
        return self.numeros_cadastro

    def obter_grupo_estoque(self):
        if self.indisponivel:
            raise ChatbotIndisponivel("Não foi possível acessar o chatbot agora")
        return self.grupo_estoque

    def definir_grupo_estoque(self, grupo_jid):
        grupo = next(
            item for item in self.grupo_estoque["grupos"] if item["jid"] == grupo_jid
        )
        self.grupo_estoque["selecionado"] = dict(grupo)
        return grupo

    def remover_grupo_estoque(self):
        self.grupo_estoque["selecionado"] = None
        return {"removido": True}

    def adicionar_numero_cadastro(self, telefone, nome=None):
        if self.indisponivel:
            raise ChatbotIndisponivel("Não foi possível acessar o chatbot agora")
        registro = {"telefone": telefone, "nome": nome, "ativo": True}
        self.numeros_cadastro.append(registro)
        return registro

    def remover_numero_cadastro(self, telefone):
        if self.indisponivel:
            raise ChatbotIndisponivel("Não foi possível acessar o chatbot agora")
        self.numeros_cadastro = [
            n for n in self.numeros_cadastro if n["telefone"] != telefone
        ]
        return {"removido": True, "telefone": telefone}

    def simular(self, payload):
        if self.simulacao_indisponivel:
            raise SimulacaoIndisponivel("simulação não habilitada nesta instalação")
        self.simulacoes.append(payload)
        # Campos sensíveis (custo/lucro/tokens/métricas) que um driver real
        # poderia devolver: o Portal deve escondê-los do vendedor.
        return {
            "id": "sim-1",
            "status": "concluida",
            "custo_veiculo": 98888.0,
            "lucro": 12345.0,
            "margem": 0.27,
            "motor_token": "tok-motor-SEGREDO",
            "metricas": {"spread": 0.11},
            "resultados": [
                {
                    "provedor": "Banco Teste", "status": "concluida",
                    "valor_parcela": 796.91, "taxa_am": 1.89, "prazo_meses": 48,
                    "valor_financiado": 25000.0, "codigo_erro": None,
                    "custo": 77777.0, "margem": 0.19, "comissao": 6543.0,
                    "token": "res-tok-SEGREDO",
                },
            ],
        }


@pytest.fixture
def chatbot_fake():
    fake = ChatbotFake()
    app.dependency_overrides[get_chatbot_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_chatbot_client, None)


class MotorFake:
    """Motor de simulação fake: credenciais mascaradas, sem senha em claro."""

    def __init__(self, configurado=True):
        self._configurado = configurado
        self.indisponivel = False
        self.upserts = []
        self.testes = []
        self.atores = []
        self.credenciais = [
            {
                "provedor": "pan",
                "usuario": "loja42",
                "senha_configurada": True,
                "senha_mascara": "****",
                "habilitado": True,
                "atualizado_em": "2026-07-10T12:00:00+00:00",
                "ultimo_sucesso_em": "2026-07-11T09:00:00+00:00",
                "ultimo_erro_sanitizado": None,
                "falhas_login": 0,
                # Campo malicioso: se o Motor um dia vazar, a UI não deve ecoar.
                "senha": "SENHA-SECRETA-NUNCA-NO-HTML",
            },
            {
                "provedor": "santander",
                "usuario": None,
                "senha_configurada": False,
                "senha_mascara": None,
                "habilitado": False,
                "atualizado_em": None,
                "ultimo_sucesso_em": None,
                "ultimo_erro_sanitizado": None,
                "falhas_login": 0,
            },
        ]
        self.provedores = [
            {
                "nome": "pan", "rotulo": "Banco PAN", "habilitado": True,
                "real": True, "modo": "playwright",
                "campos_credencial": [
                    {"nome": "usuario", "rotulo": "Usuário/CPF do portal go!PAN", "secreto": False},
                    {"nome": "senha", "rotulo": "Senha do portal", "secreto": True},
                ],
            },
            {
                "nome": "santander", "rotulo": "Santander", "habilitado": True,
                "real": True, "modo": "playwright",
                "campos_credencial": [
                    {"nome": "usuario", "rotulo": "CPF/usuário", "secreto": False},
                    {"nome": "senha", "rotulo": "Senha", "secreto": True},
                ],
            },
        ]
        # Histórico de simulações (projeção não sensível do Motor — sem CPF/valores).
        self.listagens = []
        self.historico = [
            {
                "id": "sim-dono-1", "status": "concluida",
                "criada_em": "2026-07-13T10:00:00+00:00",
                "atualizada_em": "2026-07-13T10:02:00+00:00",
                "solicitado_por": "dono@loja.test", "referencia_externa": None,
                "placa": "ABC1D23", "categoria": "moto",
                "provedores": ["Santander"], "prazos_meses": [24, 48],
                "num_resultados": 2,
            },
            {
                "id": "sim-dono-2", "status": "falhou",
                "criada_em": "2026-07-12T09:00:00+00:00",
                "atualizada_em": "2026-07-12T09:01:00+00:00",
                "solicitado_por": "dono@loja.test", "referencia_externa": "lead-9",
                "placa": None, "categoria": "carro",
                "provedores": ["Pan"], "prazos_meses": [36],
                "num_resultados": 1,
            },
            {
                "id": "sim-outro-1", "status": "concluida",
                "criada_em": "2026-07-11T08:00:00+00:00",
                "atualizada_em": "2026-07-11T08:03:00+00:00",
                "solicitado_por": "outro@loja.test", "referencia_externa": None,
                "placa": "ZZZ9Z99", "categoria": "moto",
                "provedores": ["Santander"], "prazos_meses": [48],
                "num_resultados": 2,
            },
        ]

    def listar_simulacoes(
        self, ator=None, status=None, solicitado_por=None,
        desde=None, ate=None, limite=20, offset=0,
    ):
        if self.indisponivel:
            raise MotorIndisponivel("Não foi possível acessar o Motor de Simulação agora")
        self.listagens.append(
            {
                "ator": ator, "status": status, "solicitado_por": solicitado_por,
                "desde": desde, "ate": ate, "limite": limite, "offset": offset,
            }
        )
        itens = list(self.historico)
        if solicitado_por:
            itens = [i for i in itens if i["solicitado_por"] == solicitado_por]
        if status:
            itens = [i for i in itens if i["status"] == status]
        total = len(itens)
        recorte = itens[offset:offset + limite]
        return {
            "itens": recorte, "total": total, "limite": limite, "offset": offset,
            "resumo": {"total": total, "retornados": len(recorte)},
        }

    @property
    def configurado(self) -> bool:
        return self._configurado

    def listar_provedores(self, ator=None):
        if self.indisponivel:
            raise MotorIndisponivel("Não foi possível acessar o Motor de Simulação agora")
        if ator:
            self.atores.append(("listar_provedores", ator))
        return list(self.provedores)

    def listar_credenciais(self, ator=None):
        if self.indisponivel:
            raise MotorIndisponivel("Não foi possível acessar o Motor de Simulação agora")
        if ator:
            self.atores.append(("listar_credenciais", ator))
        return [dict(c) for c in self.credenciais]

    def upsert_credencial(
        self, nome, usuario, senha, ator, habilitado=True, campos=None
    ):
        if self.indisponivel:
            raise MotorIndisponivel("Não foi possível acessar o Motor de Simulação agora")
        self.upserts.append(
            {
                "nome": nome,
                "usuario": usuario,
                "senha": senha,
                "ator": ator,
                "habilitado": habilitado,
                "campos": campos,
            }
        )
        self.atores.append(("upsert", ator))
        for item in self.credenciais:
            if item["provedor"] == nome:
                item.update(
                    {
                        "usuario": usuario,
                        "senha_configurada": True,
                        "senha_mascara": "****",
                        "habilitado": habilitado,
                        "atualizado_em": "2026-07-13T15:00:00+00:00",
                    }
                )
                return {
                    "provedor": nome,
                    "usuario": usuario,
                    "senha_configurada": True,
                    "senha_mascara": "****",
                    "habilitado": habilitado,
                    "atualizado_em": item["atualizado_em"],
                    "ultimo_sucesso_em": item.get("ultimo_sucesso_em"),
                    "ultimo_erro_sanitizado": item.get("ultimo_erro_sanitizado"),
                    "falhas_login": item.get("falhas_login", 0),
                }
        novo = {
            "provedor": nome,
            "usuario": usuario,
            "senha_configurada": True,
            "senha_mascara": "****",
            "habilitado": habilitado,
            "atualizado_em": "2026-07-13T15:00:00+00:00",
            "ultimo_sucesso_em": None,
            "ultimo_erro_sanitizado": None,
            "falhas_login": 0,
        }
        self.credenciais.append(novo)
        return dict(novo)

    def testar_login(self, nome, ator):
        if self.indisponivel:
            raise MotorIndisponivel("Não foi possível acessar o Motor de Simulação agora")
        self.testes.append({"nome": nome, "ator": ator})
        self.atores.append(("testar", ator))
        for item in self.credenciais:
            if item["provedor"].lower() == nome.lower() and item.get("senha_configurada"):
                return {
                    "provedor": nome,
                    "status": "placeholder",
                    "detalhe": "Teste real de login disponível a partir do driver da Task 12.",
                }
        raise CredencialNaoEncontrada("credencial não configurada")

    def criar_simulacao(self, payload, ator=None, idempotency_key=None):
        if self.indisponivel:
            raise MotorIndisponivel("Não foi possível acessar o Motor de Simulação agora")
        if not hasattr(self, "simulacoes"):
            self.simulacoes = []
        self.simulacoes.append(payload)
        if ator:
            self.atores.append(("criar_simulacao", ator))
        return {
            "id": "sim-motor-1",
            "status": "recebida",
            "criada_em": "2026-07-13T12:00:00+00:00",
        }

    def obter_simulacao(self, sim_id, ator=None):
        if self.indisponivel:
            raise MotorIndisponivel("Não foi possível acessar o Motor de Simulação agora")
        # status_retorno: "concluida" (padrão) | "recebida" | "processando" | "falhou"
        status = getattr(self, "status_retorno", "concluida")
        ultimo = (self.simulacoes[-1] if getattr(self, "simulacoes", None) else {}) or {}
        provedores = list(ultimo.get("provedores") or ["santander"])
        resultados = []
        if status in ("concluida", "parcial", "falhou"):
            for prov in provedores:
                resultados.append(
                    {
                        "provedor": prov,
                        "status": "concluida" if status != "falhou" else "erro",
                        "valor_parcela": 946.28 if status != "falhou" else None,
                        "taxa_am": None,
                        "prazo_meses": 48,
                        "valor_financiado": 20776.80 if status != "falhou" else None,
                        "codigo_erro": None if status != "falhou" else "sem_driver_ou_credencial",
                    }
                )
                resultados.append(
                    {
                        "provedor": prov,
                        "status": "concluida" if status != "falhou" else "erro",
                        "valor_parcela": 1097.45 if status != "falhou" else None,
                        "taxa_am": None,
                        "prazo_meses": 36,
                        "valor_financiado": 20776.80 if status != "falhou" else None,
                        "codigo_erro": None if status != "falhou" else "sem_driver_ou_credencial",
                    }
                )
        return {
            "id": sim_id,
            "status": status,
            "criada_em": "2026-07-13T12:00:00+00:00",
            "provedores": provedores,
            "tarefas": [
                {
                    "id": f"t-{p}",
                    "provedor": p,
                    "tipo_driver": "api",
                    "status": "processando" if status == "processando" else status,
                    "tentativa": 1,
                    "codigo_erro": None,
                }
                for p in provedores
            ],
            "resultados": resultados,
        }

    def listar_eventos(self, sim_id, ator=None):
        if self.indisponivel:
            raise MotorIndisponivel("Não foi possível acessar o Motor de Simulação agora")
        return {
            "simulacao_id": sim_id,
            "status": getattr(self, "status_retorno", "processando"),
            "eventos": [
                {
                    "id": 1,
                    "provedor": "santander",
                    "etapa": "browser_iniciando",
                    "nivel": "info",
                    "mensagem": "Preparando o navegador do Santander.",
                    "criada_em": "2026-07-14T15:00:00+00:00",
                    "tem_print": False,
                },
                {
                    "id": 2,
                    "provedor": "santander",
                    "etapa": "login_confirmado",
                    "nivel": "sucesso",
                    "mensagem": "Login confirmado pelo portal.",
                    "criada_em": "2026-07-14T15:00:10+00:00",
                    "tem_print": True,
                },
                {
                    "id": 3,
                    "provedor": "bradesco",
                    "etapa": "driver_iniciado",
                    "nivel": "info",
                    "mensagem": "Conector bradesco iniciado.",
                    "criada_em": "2026-07-14T15:00:05+00:00",
                    "tem_print": False,
                },
            ],
        }

    def obter_print_evento(self, sim_id, evento_id, ator=None):
        if self.indisponivel:
            raise MotorIndisponivel("Não foi possível carregar o print")
        return b"PNG-FAKE", "image/png"

    def simular_e_aguardar(self, payload, ator=None, poll_timeout=90.0, poll_interval=1.0):
        criada = self.criar_simulacao(payload, ator=ator)
        return self.obter_simulacao(criada["id"], ator=ator)


@pytest.fixture
def motor_fake():
    fake = MotorFake(configurado=True)
    app.dependency_overrides[get_motor_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_motor_client, None)


@pytest.fixture(autouse=True)
def banco_limpo():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(autouse=True)
def _cache_overview_isolado():
    """cache_overview é TTL global por processo (90s de relógio real): sem
    isolar, um teste que rodou antes com o mesmo loja_slug/papel deixa um
    SalesOverview de sobra — inclusive construído em cima de uma sessão de
    banco já fechada. Autouse em TODO teste, não só nos da rota do Copiloto:
    qualquer arquivo que chame montar_resumo_hoje/build_sales_overview
    repetidamente dentro do TTL pode reusar esse resíduo."""
    cache_overview.invalidar()
    yield
    cache_overview.invalidar()


@pytest.fixture(autouse=True)
def _cache_copiloto_nao_vistos_isolado():
    """Mesmo risco do ``cache_overview`` acima, para o cache de
    ``contar_nao_vistos`` (``app/loja/copiloto/notificacoes.py``): TTL de
    relógio real, por processo. ``login()``/``client`` reusam
    "dono@loja.test"/"loja-teste" em muitos arquivos de teste — sem isolar,
    um teste anterior deixa a contagem cacheada para o próximo dentro do TTL."""
    copiloto_notificacoes.cache_nao_vistos.invalidar()
    yield
    copiloto_notificacoes.cache_nao_vistos.invalidar()


@pytest.fixture
def estoque_fake():
    fake = EstoqueFake()
    app.dependency_overrides[get_estoque_client] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


@pytest.fixture
def client(estoque_fake, chatbot_fake, motor_fake):
    with TestClient(app) as cliente:
        yield cliente


def seed_loja_operacional(db, loja_slug="loja-teste", state="ativa", version=1):
    """Suite de regressão assume loja operacional; testes do gate sobrescrevem."""
    existente = db.get(LojaOperacionalProjecao, (loja_slug, "loja"))
    if existente is not None:
        existente.state = state
        existente.version = version
        existente.event_id = f"seed-{state}"
        return
    db.add(
        LojaOperacionalProjecao(
            loja_slug=loja_slug,
            aggregate="loja",
            version=version,
            state=state,
            event_id=f"seed-{state}",
        )
    )


def criar_usuario(papel="dono", email="dono@loja.test", loja_slug="loja-teste"):
    db = SessionLocal()
    usuario = Usuario(
        email=email,
        nome="Ana Loja",
        senha_hash=hash_senha("senha-segura"),
        papel=papel,
        loja_slug=loja_slug,
    )
    db.add(usuario)
    # Gate fail-closed: sem projeção, POST /app/vendas/nova bloqueia.
    seed_loja_operacional(db, loja_slug=loja_slug)
    db.commit()
    db.close()


def csrf_da_resposta(resposta):
    return re.search(r'name="csrf" value="([^"]+)"', resposta.text).group(1)


def login(client, papel="dono", email="dono@loja.test", loja_slug="loja-teste"):
    criar_usuario(papel=papel, email=email, loja_slug=loja_slug)
    pagina = client.get("/login")
    return client.post(
        "/login",
        data={"email": email, "senha": "senha-segura", "csrf": csrf_da_resposta(pagina)},
        follow_redirects=False,
    )


@pytest.fixture
def db():
    sessao = SessionLocal()
    try:
        yield sessao
    finally:
        sessao.close()
