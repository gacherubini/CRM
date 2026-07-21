"""API do Chatbot (Plano #2A). n8n consome esta API; não escreve no banco direto."""
import csv
import io
import os
import uuid
from datetime import datetime
from typing import Optional
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app import config, models_db, operacao, servico  # noqa: F401 (registra os modelos)
from app.audio import AudioProcessor, get_audio_processor
from app.auth import Contexto, get_contexto, verificar_webhook_token
from app.db import Base, engine, get_db
from app.inventory import (
    InventoryProvider,
    InventoryWriteClient,
    get_inventory_provider,
    get_inventory_write_client,
)
from app.hardening import (
    WebhookPayloadLimitMiddleware,
    logger as webhook_logger,
    normalizar_telefone_webhook,
    validar_identificador,
)
from app.simulation import SimulationProvider, get_simulation_provider
from app.vehicle_photo import VehiclePhotoProcessor, get_vehicle_photo_processor

app = FastAPI(title="Chatbot API")
app.add_middleware(WebhookPayloadLimitMiddleware)

EtapaLead = Literal["novo", "em_atendimento", "qualificado", "convertido", "perdido"]

if os.getenv("CHATBOT_SKIP_INIT") != "1":
    Base.metadata.create_all(bind=engine)


@app.exception_handler(RequestValidationError)
async def erro_validacao_request(request: Request, exc: RequestValidationError):
    """Não devolve valores sensíveis do payload inválido do webhook."""
    if request.url.path.startswith("/webhook/"):
        webhook_logger.warning("webhook rejeitado: payload inválido")
        return JSONResponse(
            status_code=422,
            content={"detail": "payload do webhook inválido"},
        )
    return await request_validation_exception_handler(request, exc)


class MensagemEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instance: str
    telefone: str
    texto: Optional[str] = None
    provider_message_id: Optional[str] = None
    from_me: bool = False
    origem_bot: bool = False
    # Opcional: status|ack|reaction|... — eventos sem conteúdo não pausam o bot (E3).
    tipo: Optional[str] = None

    @field_validator("instance")
    @classmethod
    def validar_instance(cls, value: str) -> str:
        return validar_identificador(
            value,
            nome="instance",
            limite=config.WEBHOOK_MAX_INSTANCE_CHARS,
        )

    @field_validator("telefone")
    @classmethod
    def validar_telefone(cls, value: str) -> str:
        return normalizar_telefone_webhook(value)

    @field_validator("texto")
    @classmethod
    def validar_texto(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if len(value) > max(1, config.WEBHOOK_MAX_TEXT_CHARS):
            raise ValueError("texto excede o limite permitido")
        if "\x00" in value:
            raise ValueError("texto contém caractere inválido")
        return value

    @field_validator("provider_message_id", "tipo")
    @classmethod
    def validar_identificadores_opcionais(
        cls, value: Optional[str], info
    ) -> Optional[str]:
        if value is None or not value.strip():
            return None
        limite = (
            config.WEBHOOK_MAX_PROVIDER_MESSAGE_ID_CHARS
            if info.field_name == "provider_message_id"
            else config.WEBHOOK_MAX_EVENT_TYPE_CHARS
        )
        return validar_identificador(value, nome=info.field_name, limite=limite)


class AudioWebhookInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instance: str
    provider_message_id: str
    mime_type: Optional[str] = Field(default=None, max_length=120)
    duration_seconds: Optional[float] = Field(default=None, ge=0)

    @field_validator("instance")
    @classmethod
    def validar_instance(cls, value: str) -> str:
        return validar_identificador(
            value,
            nome="instance",
            limite=config.WEBHOOK_MAX_INSTANCE_CHARS,
        )

    @field_validator("provider_message_id")
    @classmethod
    def validar_message_id(cls, value: str) -> str:
        return validar_identificador(
            value,
            nome="provider_message_id",
            limite=config.WEBHOOK_MAX_PROVIDER_MESSAGE_ID_CHARS,
        )


class FotoVeiculoWebhookInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instance: str
    telefone_solicitante: str
    provider_message_id: str
    legenda: Optional[str] = Field(default=None, max_length=500)
    mime_type: Optional[str] = Field(default=None, max_length=120)

    @field_validator("instance")
    @classmethod
    def validar_instance(cls, value: str) -> str:
        return validar_identificador(
            value,
            nome="instance",
            limite=config.WEBHOOK_MAX_INSTANCE_CHARS,
        )

    @field_validator("telefone_solicitante")
    @classmethod
    def validar_telefone(cls, value: str) -> str:
        return normalizar_telefone_webhook(value)

    @field_validator("provider_message_id")
    @classmethod
    def validar_message_id(cls, value: str) -> str:
        return validar_identificador(
            value,
            nome="provider_message_id",
            limite=config.WEBHOOK_MAX_PROVIDER_MESSAGE_ID_CHARS,
        )


class EstadoInput(BaseModel):
    bot_ativo: bool


class ConsentimentoInput(BaseModel):
    telefone: str
    versao_texto: str
    finalidade: str = "simulação e contato da loja"
    evidencia: Optional[str] = None


class LeadInput(BaseModel):
    telefone: str
    nome: Optional[str] = None
    interesse: Optional[str] = None
    etapa: Optional[EtapaLead] = None


class EtapaLeadInput(BaseModel):
    etapa: EtapaLead


class CatalogInterestInput(BaseModel):
    event_id: UUID
    event_type: Literal["catalog.interest_clicked"]
    occurred_at: datetime
    loja_slug: str = Field(min_length=1, max_length=120)
    catalog_interest_ref: str = Field(pattern=r"^CAT-[A-Z2-7]{10,16}$")
    veiculo_ref: str = Field(min_length=1, max_length=120)
    origem: Literal["catalogo_publico"]
    canal: Literal["whatsapp"]
    utm_source: Optional[str] = Field(default=None, max_length=120)
    utm_medium: Optional[str] = Field(default=None, max_length=120)
    utm_campaign: Optional[str] = Field(default=None, max_length=120)
    utm_content: Optional[str] = Field(default=None, max_length=120)
    utm_term: Optional[str] = Field(default=None, max_length=120)
    fbclid: Optional[str] = Field(default=None, max_length=255)
    gclid: Optional[str] = Field(default=None, max_length=255)

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at deve conter timezone")
        return value


class SimularInput(BaseModel):
    """Payload do bot/n8n para simulação.

    CRM WhatsApp: preferir placa (+ telefone opcional); valor vem do Estoque.
    Sem renda obrigatória; prazos multi (lista ou padrão 24/36/48/60).
    Compat: valor + prazo_meses únicos ainda aceitos (testes/portal legado).
    """

    cpf: str
    nascimento: str
    valor: Optional[float] = None
    prazo_meses: Optional[int] = None
    prazos_meses: Optional[list[int]] = None
    entrada: float = 0
    renda: Optional[float] = None
    categoria: str = "moto"
    placa: Optional[str] = None
    telefone: Optional[str] = None
    referencia_externa: Optional[str] = None

    @model_validator(mode="after")
    def exige_placa_ou_valor(self):
        if self.valor is None and not (self.placa and self.placa.strip()):
            raise ValueError("informe placa ou valor do veículo")
        return self

    def resolver_prazos(self) -> list[int]:
        if self.prazos_meses:
            return list(self.prazos_meses)
        if self.prazo_meses is not None:
            return [self.prazo_meses]
        return list(config.PRAZOS_PADRAO_MESES)


class NumeroAutorizadoInput(BaseModel):
    telefone: str
    papel: str = "vendedor"
    ativo: bool = True
    nome: Optional[str] = Field(default=None, max_length=120)


class OperacaoVeiculoInput(BaseModel):
    """Cadastro de veículo via WhatsApp (E5). n8n/LLM preenche os campos extraídos."""

    telefone_solicitante: str
    tipo: str = "moto"
    marca: str
    modelo: str
    ano_modelo: int
    preco: float
    km: int = 0
    placa: str
    versao: Optional[str] = None
    cor: Optional[str] = None
    codigo_interno: Optional[str] = None
    foto_url: Optional[str] = None


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"versao": config.VERSAO, "schema": config.SCHEMA_VERSAO}


@app.post("/webhook/mensagem")
def webhook_mensagem(
    msg: MensagemEntrada,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_webhook_token),
):
    """Recebe uma mensagem (loja resolvida pela instância) e persiste idempotente."""
    return servico.registrar_mensagem(
        db,
        msg.instance,
        msg.telefone,
        msg.texto,
        msg.provider_message_id,
        msg.from_me,
        msg.origem_bot,
        msg.tipo,
    )


@app.post("/webhook/audio/transcrever")
def webhook_audio_transcrever(
    dados: AudioWebhookInput,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_webhook_token),
    processor: AudioProcessor = Depends(get_audio_processor),
):
    """Baixa/transcreve áudio server-side e sempre falha com fallback seguro."""
    loja = servico.resolver_loja_por_instancia(db, dados.instance)
    ja_registrada = (
        db.query(models_db.Mensagem)
        .filter(
            models_db.Mensagem.loja_id == loja.id,
            models_db.Mensagem.provider_message_id == dados.provider_message_id,
        )
        .first()
    )
    if ja_registrada:
        return {
            "transcrito": False,
            "texto": None,
            "fallback": config.AUDIO_FALLBACK_TEXT,
            "duplicada": True,
        }
    return processor.processar(
        dados.instance,
        dados.provider_message_id,
        dados.mime_type,
        dados.duration_seconds,
    )


@app.post("/webhook/operacao/veiculos/foto")
def webhook_foto_veiculo(
    dados: FotoVeiculoWebhookInput,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_webhook_token),
    processor: VehiclePhotoProcessor = Depends(get_vehicle_photo_processor),
):
    """Imagem da equipe → Estoque → catálogo, sem binário no n8n/Chatbot."""
    loja = servico.resolver_loja_por_instancia(db, dados.instance)
    return operacao.anexar_foto_whatsapp(
        db,
        loja.id,
        dados.instance,
        dados.telefone_solicitante,
        dados.provider_message_id,
        dados.legenda,
        dados.mime_type,
        processor,
    )


@app.get("/v1/conversas")
def listar_conversas(
    limit: int = 50,
    offset: int = 0,
    busca: Optional[str] = None,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    conversas = servico.listar_conversas(db, ctx.loja_id, limit, offset, busca)
    return {"conversas": conversas, "limit": limit, "offset": offset}


@app.get("/v1/conversas/{telefone}/mensagens")
def listar_mensagens(
    telefone: str,
    limit: int = 100,
    offset: int = 0,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    resultado = servico.listar_mensagens(db, ctx.loja_id, telefone, limit, offset)
    return {**resultado, "limit": limit, "offset": offset}


@app.get("/v1/conversas/{telefone}/estado")
def obter_estado(
    telefone: str, ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)
):
    return servico.obter_estado(db, ctx.loja_id, telefone)


@app.patch("/v1/conversas/{telefone}/estado")
def definir_estado(
    telefone: str,
    dados: EstadoInput,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    return servico.definir_bot_ativo(db, ctx.loja_id, telefone, dados.bot_ativo)


@app.post("/v1/consentimentos", status_code=201)
def registrar_consentimento(
    dados: ConsentimentoInput,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    lead = servico.registrar_consentimento(
        db, ctx.loja_id, dados.telefone, dados.versao_texto, dados.finalidade, dados.evidencia
    )
    return servico.para_saida_lead(lead)


@app.post("/v1/leads", status_code=201)
def registrar_lead(
    dados: LeadInput, ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)
):
    lead = servico.registrar_lead(
        db, ctx.loja_id, dados.telefone, dados.nome, dados.interesse, dados.etapa
    )
    return servico.para_saida_lead(lead)


@app.post("/v1/integracoes/catalogo/interesses", status_code=202)
def ingerir_interesse_catalogo(
    dados: CatalogInterestInput,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    event_id = str(dados.event_id)
    if idempotency_key is not None and idempotency_key != event_id:
        raise HTTPException(status_code=422, detail="Idempotency-Key difere do event_id")
    atribuicao, duplicado = servico.ingerir_interesse_catalogo(
        db,
        ctx.loja_id,
        event_id=event_id,
        loja_slug=dados.loja_slug,
        catalog_interest_ref=dados.catalog_interest_ref,
        veiculo_ref=dados.veiculo_ref,
        origem=dados.origem,
        canal=dados.canal,
        occurred_at=dados.occurred_at,
        utm_source=dados.utm_source,
        utm_medium=dados.utm_medium,
        utm_campaign=dados.utm_campaign,
        utm_content=dados.utm_content,
        utm_term=dados.utm_term,
        fbclid=dados.fbclid,
        gclid=dados.gclid,
    )
    return {"duplicado": duplicado, "atribuicao_id": atribuicao.id}


@app.get("/v1/leads")
def listar_leads(
    etapa: Optional[str] = None,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    leads = servico.listar_leads(db, ctx.loja_id, etapa)
    return {"leads": [servico.para_saida_lead(lead) for lead in leads]}


@app.get("/v1/funil/eventos")
def listar_eventos_funil(
    limit: int = 500,
    offset: int = 0,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    """Projeção analítica sanitizada para o Portal, sem telefone ou texto."""
    limite = max(1, min(limit, 1000))
    deslocamento = max(0, offset)
    eventos = servico.listar_eventos_funil(
        db,
        ctx.loja_id,
        limit=limite,
        offset=deslocamento,
    )
    return {"eventos": eventos, "limit": limite, "offset": deslocamento}


@app.get("/v1/leads.csv")
def exportar_leads_csv(
    etapa: Optional[str] = None,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    leads = servico.listar_leads(db, ctx.loja_id, etapa)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id", "telefone", "nome", "interesse", "etapa", "consentimento_em", "criada_em",
            "origem", "canal", "utm_source", "utm_medium", "utm_campaign", "utm_content",
            "utm_term", "veiculo_ref", "catalog_interest_ref", "atribuida_em",
        ]
    )
    for lead in leads:
        s = servico.para_saida_lead(lead)
        writer.writerow(
            [
                s["id"],
                s["telefone"],
                s["nome"] or "",
                s["interesse"] or "",
                s["etapa"],
                s["consentimento_em"] or "",
                s["criada_em"] or "",
                s["origem"] or "",
                s["canal"] or "",
                s["utm_source"] or "",
                s["utm_medium"] or "",
                s["utm_campaign"] or "",
                s["utm_content"] or "",
                s["utm_term"] or "",
                s["veiculo_ref"] or "",
                s["catalog_interest_ref"] or "",
                s["atribuida_em"] or "",
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )


@app.get("/v1/leads/{lead_id}")
def obter_lead(
    lead_id: str, ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)
):
    return servico.para_saida_lead(servico.obter_lead(db, ctx.loja_id, lead_id))


@app.patch("/v1/leads/{lead_id}/etapa")
def atualizar_etapa_lead(
    lead_id: str,
    dados: EtapaLeadInput,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    """Atualiza o funil de um lead pertencente à loja autenticada."""
    lead = servico.atualizar_etapa_lead(db, ctx.loja_id, lead_id, dados.etapa)
    return servico.para_saida_lead(lead)


@app.get("/v1/estoque/buscar")
def buscar_estoque(
    termo: Optional[str] = None,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
    provider: InventoryProvider = Depends(get_inventory_provider),
):
    """Ferramenta do bot: consulta o Estoque Lite; sem resultado, oferece fallback."""
    loja = db.get(models_db.Loja, ctx.loja_id)
    veiculos = provider.buscar(loja.slug, termo)
    if not veiculos:
        return {
            "veiculos": [],
            "fonte": "fallback",
            "mensagem": "Não encontrei veículos correspondentes no estoque agora; posso chamar um atendente.",
        }
    return {"veiculos": veiculos, "fonte": "estoque"}


@app.get("/v1/estoque/por-placa/{placa}")
def estoque_por_placa(
    placa: str,
    ctx: Contexto = Depends(get_contexto),
    provider: InventoryProvider = Depends(get_inventory_provider),
):
    """Ferramenta do bot: resolve veículo da loja pela placa (Estoque privado)."""
    veiculo = provider.obter_por_placa(placa)
    if not veiculo:
        return {
            "veiculo": None,
            "fonte": "fallback",
            "mensagem": "Não encontrei esse veículo no estoque pela placa; posso chamar um atendente.",
        }
    return {"veiculo": veiculo, "fonte": "estoque"}


@app.get("/v1/estoque/veiculos/{veiculo_id}/midia-principal")
def estoque_midia_principal(
    veiculo_id: str,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
    provider: InventoryProvider = Depends(get_inventory_provider),
):
    """Capa confiável para envio direto no WhatsApp, sem depender do site."""
    loja = db.get(models_db.Loja, ctx.loja_id)
    midia = provider.obter_midia_principal(loja.slug, veiculo_id)
    if not midia:
        return {"veiculo_id": veiculo_id, "midia": None, "tem_foto": False}
    return {
        "veiculo_id": veiculo_id,
        "midia": {
            "tipo": "image",
            "url": midia["url"],
            "content_type": midia["content_type"],
            "tamanho_bytes": midia.get("tamanho_bytes"),
        },
        "tem_foto": True,
    }


def _montar_payload_motor(
    dados: SimularInput, valor: float, categoria: str, prazo: int
) -> dict:
    pessoa: dict = {"cpf": dados.cpf, "nascimento": dados.nascimento}
    if dados.renda is not None:
        pessoa["renda"] = dados.renda
    payload = {
        "referencia_externa": dados.referencia_externa,
        "pessoa": pessoa,
        "veiculo": {"categoria": categoria, "valor": valor},
        "condicoes": {"entrada": dados.entrada, "prazo_meses": prazo},
        "provedores": ["mock"],
    }
    if dados.placa:
        payload["veiculo"]["placa"] = dados.placa.strip()
    if dados.telefone:
        payload["telefone"] = dados.telefone
    return payload


def _resolver_pedido_simulacao(
    dados: SimularInput,
    provider: SimulationProvider,
    inventory: InventoryProvider,
) -> tuple[float, str, list[int]]:
    if not provider.disponivel():
        raise HTTPException(status_code=409, detail="simulação não habilitada nesta instalação")

    valor = dados.valor
    categoria = dados.categoria
    if dados.placa and dados.placa.strip():
        veiculo = inventory.obter_por_placa(dados.placa.strip())
        if not veiculo:
            raise HTTPException(
                status_code=404,
                detail="veículo não encontrado no estoque para esta placa",
            )
        preco = veiculo.get("preco")
        if preco is None:
            raise HTTPException(
                status_code=404,
                detail="veículo sem preço no estoque; posso chamar um atendente.",
            )
        valor = float(preco)
        tipo = veiculo.get("tipo")
        if tipo in {"moto", "carro"}:
            categoria = tipo

    if valor is None:
        raise HTTPException(status_code=422, detail="informe placa ou valor do veículo")

    prazos = dados.resolver_prazos() or list(config.PRAZOS_PADRAO_MESES)
    return valor, categoria, prazos


@app.post("/v1/simulacoes/solicitar", status_code=202)
def solicitar_simulacao(
    dados: SimularInput,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ctx: Contexto = Depends(get_contexto),
    provider: SimulationProvider = Depends(get_simulation_provider),
    inventory: InventoryProvider = Depends(get_inventory_provider),
):
    """Enfileira jobs para o vendedor, sem devolver resultados ao canal do bot."""
    valor, categoria, prazos = _resolver_pedido_simulacao(dados, provider, inventory)

    solicitacoes = []
    for prazo in prazos:
        chave_job = (
            f"{idempotency_key.strip()}:{prazo}"
            if idempotency_key and idempotency_key.strip()
            else str(uuid.uuid4())
        )
        criada = provider.solicitar(
            _montar_payload_motor(dados, valor, categoria, prazo),
            chave_job,
        )
        solicitacoes.append(
            {
                "id": criada.get("id"),
                "status": criada.get("status", "recebida"),
                "prazo_meses": prazo,
            }
        )

    return {
        "status": "recebida",
        "quantidade": len(solicitacoes),
        "solicitacoes": solicitacoes,
    }


@app.post("/v1/simular")
def simular(
    dados: SimularInput,
    ctx: Contexto = Depends(get_contexto),
    provider: SimulationProvider = Depends(get_simulation_provider),
    inventory: InventoryProvider = Depends(get_inventory_provider),
):
    """Ferramenta do bot: delega ao provider configurado (none|mock|http).

    Com placa: valor (e categoria/tipo) vêm do Estoque — nunca digitados pelo cliente.
    Prazos: lista explícita, ou prazo_meses único (compat), ou padrão multi 24/36/48/60.
    Motor aceita um prazo por job; multi-prazo = um job por prazo e resultados mesclados.
    """
    valor, categoria, prazos = _resolver_pedido_simulacao(dados, provider, inventory)

    # Um único prazo (compat com payload legado): resposta idêntica à anterior.
    if len(prazos) == 1:
        payload = _montar_payload_motor(dados, valor, categoria, prazos[0])
        return provider.simular(payload, str(uuid.uuid4()))

    # Multi-prazo: Motor/mock só entendem um prazo por job — agrega resultados.
    todos: list[dict] = []
    status_final = "concluida"
    mensagem = None
    for prazo in prazos:
        out = provider.simular(
            _montar_payload_motor(dados, valor, categoria, prazo),
            str(uuid.uuid4()),
        )
        st = out.get("status")
        if st and st != "concluida":
            status_final = st
        if out.get("mensagem") and not mensagem:
            mensagem = out["mensagem"]
        for item in out.get("resultados") or []:
            if "prazo_meses" not in item:
                item = {**item, "prazo_meses": prazo}
            todos.append(item)

    resposta: dict = {
        "status": status_final,
        "resultados": todos,
        "prazos_meses": prazos,
        "valor": valor,
        "categoria": categoria,
    }
    if mensagem:
        resposta["mensagem"] = mensagem
    if dados.placa:
        resposta["placa"] = dados.placa.strip()
    return resposta


# --- Operação WhatsApp (E5): números autorizados + cadastro de veículo --------


@app.get("/v1/operacao/numeros-autorizados")
def listar_numeros_autorizados(
    ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)
):
    return {"numeros": operacao.listar_numeros(db, ctx.loja_id)}


@app.post("/v1/operacao/numeros-autorizados", status_code=201)
def adicionar_numero_autorizado(
    dados: NumeroAutorizadoInput,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    return operacao.adicionar_numero(
        db, ctx.loja_id, dados.telefone, dados.papel, dados.ativo, dados.nome
    )


@app.delete("/v1/operacao/numeros-autorizados/{telefone}")
def remover_numero_autorizado(
    telefone: str,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    return operacao.remover_numero(db, ctx.loja_id, telefone)


@app.post("/v1/operacao/veiculos", status_code=201)
def criar_veiculo_operacao(
    dados: OperacaoVeiculoInput,
    idempotency_key: Optional[str] = Header(
        default=None, alias="Idempotency-Key", max_length=512
    ),
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
    write_client: InventoryWriteClient = Depends(get_inventory_write_client),
):
    """Ferramenta do bot: cadastro de veículo no Estoque por número autorizado.

    n8n/LLM extrai marca/modelo/ano/valor/km/placa e chama este endpoint com o
    telefone do remetente. Clientes comuns recebem 403; dados incompletos 422.
    """
    body = dados.model_dump(exclude={"telefone_solicitante"})
    return operacao.criar_veiculo_autorizado(
        db,
        ctx.loja_id,
        dados.telefone_solicitante,
        body,
        write_client,
        idempotency_key=idempotency_key,
    )
