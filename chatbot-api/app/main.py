"""API do Chatbot (Plano #2A). n8n consome esta API; não escreve no banco direto."""
import csv
import io
import os
import uuid
from datetime import datetime
from typing import Optional
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app import config, models_db, servico  # noqa: F401 (registra os modelos)
from app.auth import Contexto, get_contexto, verificar_webhook_token
from app.db import Base, engine, get_db
from app.inventory import InventoryProvider, get_inventory_provider
from app.simulation import SimulationProvider, get_simulation_provider

app = FastAPI(title="Chatbot API")

if os.getenv("CHATBOT_SKIP_INIT") != "1":
    Base.metadata.create_all(bind=engine)


class MensagemEntrada(BaseModel):
    instance: str
    telefone: str
    texto: Optional[str] = None
    provider_message_id: Optional[str] = None
    from_me: bool = False
    origem_bot: bool = False


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
    etapa: Optional[str] = None


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

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at deve conter timezone")
        return value


class SimularInput(BaseModel):
    cpf: str
    nascimento: str
    valor: float
    prazo_meses: int
    entrada: float = 0
    renda: Optional[float] = None
    categoria: str = "moto"
    referencia_externa: Optional[str] = None


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


@app.post("/v1/simular")
def simular(
    dados: SimularInput,
    ctx: Contexto = Depends(get_contexto),
    provider: SimulationProvider = Depends(get_simulation_provider),
):
    """Ferramenta do bot: delega ao provider configurado (none|mock|http)."""
    if not provider.disponivel():
        raise HTTPException(status_code=409, detail="simulação não habilitada nesta instalação")
    payload = {
        "referencia_externa": dados.referencia_externa,
        "pessoa": {"cpf": dados.cpf, "nascimento": dados.nascimento, "renda": dados.renda},
        "veiculo": {"categoria": dados.categoria, "valor": dados.valor},
        "condicoes": {"entrada": dados.entrada, "prazo_meses": dados.prazo_meses},
        "provedores": ["mock"],
    }
    return provider.simular(payload, str(uuid.uuid4()))
