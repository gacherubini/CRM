"""Orquestração da simulação: valida, enfileira o job, persiste e aplica idempotência.

Plano #1A, Tasks 4-6: a criação apenas valida e enfileira (status ``recebida``); a
execução dos provedores, com timeout/retry e resultados parciais, fica a cargo do
worker (``app.processamento``). Nada de provedor roda de forma síncrona no POST.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import config, cripto
from app.models_db import IdempotenciaORM, SimulacaoORM
from app.motor.base import ResultadoProvedor, Simulacao, SolicitacaoSimulacao
from app.validadores import idade, parse_nascimento, valida_cpf

ESTADOS_CANCELAVEIS = {"recebida", "processando"}


class ErroValidacao(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class ErroIdempotencia(Exception):
    code = "idempotency_key_conflito"
    message = "Idempotency-Key já usada com um payload diferente"


def _hash_payload(sol: SolicitacaoSimulacao) -> str:
    dados = json.dumps(sol.model_dump(), sort_keys=True, default=str)
    return hashlib.sha256(dados.encode()).hexdigest()


def _validar(sol: SolicitacaoSimulacao) -> None:
    if not valida_cpf(sol.pessoa.cpf):
        raise ErroValidacao("cpf_invalido", "CPF inválido")
    nasc = parse_nascimento(sol.pessoa.nascimento)
    if nasc is None:
        raise ErroValidacao("nascimento_invalido", "Data de nascimento inválida")
    if idade(nasc) < config.IDADE_MINIMA:
        raise ErroValidacao("idade_minima", f"Idade mínima é {config.IDADE_MINIMA} anos")
    if sol.veiculo.categoria not in config.CATEGORIAS:
        raise ErroValidacao("categoria_invalida", "Categoria de veículo não suportada")
    # Driver real: valor pode vir do portal pela placa; mock/HTTP ainda usam valor.
    if sol.veiculo.valor is None and not sol.veiculo.placa:
        raise ErroValidacao(
            "valor_ou_placa", "Informe o valor do veículo ou a placa para cotação"
        )
    if sol.condicoes.entrada < 0:
        raise ErroValidacao("entrada_invalida", "Entrada deve ser >= 0")
    if sol.veiculo.valor is not None and sol.condicoes.entrada > sol.veiculo.valor:
        raise ErroValidacao("entrada_invalida", "Entrada deve estar entre 0 e o valor do veículo")
    prazos = list(sol.condicoes.prazos_meses or [])
    if not prazos and sol.condicoes.prazo_meses is not None:
        prazos = [sol.condicoes.prazo_meses]
    if not prazos:
        raise ErroValidacao(
            "prazo_invalido",
            f"Informe prazo_meses ou prazos_meses entre {config.PRAZO_MIN} e {config.PRAZO_MAX}",
        )
    for prazo in prazos:
        if not (config.PRAZO_MIN <= prazo <= config.PRAZO_MAX):
            raise ErroValidacao(
                "prazo_invalido",
                f"Prazo deve estar entre {config.PRAZO_MIN} e {config.PRAZO_MAX} meses",
            )


def criar_simulacao(
    db: Session,
    sol: SolicitacaoSimulacao,
    cliente_id: str,
    idempotency_key: str | None = None,
    solicitado_por: str | None = None,
) -> tuple[SimulacaoORM, bool]:
    """Retorna (simulacao, criada). `criada=False` quando reusa por idempotência."""
    _validar(sol)
    payload_hash = _hash_payload(sol)

    if idempotency_key:
        existente = db.get(IdempotenciaORM, (cliente_id, idempotency_key))
        if existente is not None:
            if existente.request_hash != payload_hash:
                raise ErroIdempotencia()
            return db.get(SimulacaoORM, existente.simulacao_id), False

    payload_pessoal = json.dumps(
        {
            "cpf": sol.pessoa.cpf,
            "nascimento": sol.pessoa.nascimento,
            "renda": sol.pessoa.renda,
        }
    )
    # Enfileira: status 'recebida'. O worker executa os provedores depois.
    prazos = list(sol.condicoes.prazos_meses or [])
    if not prazos and sol.condicoes.prazo_meses is not None:
        prazos = [sol.condicoes.prazo_meses]
    sim = SimulacaoORM(
        id=str(uuid.uuid4()),
        cliente_id=cliente_id,
        referencia_externa=sol.referencia_externa,
        solicitado_por=solicitado_por,
        status="recebida",
        payload_cifrado=cripto.cifrar(payload_pessoal),
        cpf_indice_cego=cripto.indice_cego(sol.pessoa.cpf),
        categoria=sol.veiculo.categoria,
        valor=sol.veiculo.valor,
        entrada=sol.condicoes.entrada,
        prazo_meses=sol.condicoes.prazo_meses or (prazos[0] if prazos else None),
        provedores=sol.provedores,
        cnh=sol.pessoa.cnh,
        placa=sol.veiculo.placa,
        uf_licenciamento=sol.veiculo.uf_licenciamento,
        finalidade=sol.veiculo.finalidade,
        prazos_meses=prazos or None,
    )
    db.add(sim)
    db.flush()

    if idempotency_key:
        db.add(
            IdempotenciaORM(
                cliente_id=cliente_id,
                chave=idempotency_key,
                request_hash=payload_hash,
                simulacao_id=sim.id,
            )
        )
    db.commit()
    db.refresh(sim)
    return sim, True


def obter_simulacao(db: Session, sim_id: str, cliente_id: str) -> SimulacaoORM | None:
    return db.query(SimulacaoORM).filter_by(id=sim_id, cliente_id=cliente_id).one_or_none()


# Paginação da listagem de simulações (histórico). Teto defensivo para não
# devolver a base inteira num pedido só.
LISTAGEM_LIMITE_PADRAO = 20
LISTAGEM_LIMITE_MAX = 100


def _parse_dt(valor):
    """Aceita datetime, date ISO ('2026-07-01') ou datetime ISO. Retorna aware/naive."""
    if valor is None or isinstance(valor, datetime):
        return valor
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None


def listar_simulacoes(
    db: Session,
    cliente_id: str,
    *,
    status: str | None = None,
    solicitado_por: str | None = None,
    desde=None,
    ate=None,
    limite: int = LISTAGEM_LIMITE_PADRAO,
    offset: int = 0,
) -> tuple[list[SimulacaoORM], int, int, int]:
    """Histórico de simulações do cliente (tenancy), ordenado por criada_em desc.

    Retorna (itens, total, limite_aplicado, offset_aplicado). Não decifra payload
    pessoal — os campos sensíveis (cpf/nascimento/renda) ficam no blob cifrado.
    """
    try:
        limite = int(limite)
    except (TypeError, ValueError):
        limite = LISTAGEM_LIMITE_PADRAO
    try:
        offset = int(offset)
    except (TypeError, ValueError):
        offset = 0
    limite = max(1, min(limite, LISTAGEM_LIMITE_MAX))
    offset = max(0, offset)

    consulta = db.query(SimulacaoORM).filter(SimulacaoORM.cliente_id == cliente_id)
    if status:
        consulta = consulta.filter(SimulacaoORM.status == status)
    if solicitado_por:
        consulta = consulta.filter(SimulacaoORM.solicitado_por == solicitado_por)
    d_desde = _parse_dt(desde)
    if d_desde is not None:
        consulta = consulta.filter(SimulacaoORM.criada_em >= d_desde)
    d_ate = _parse_dt(ate)
    if d_ate is not None:
        consulta = consulta.filter(SimulacaoORM.criada_em <= d_ate)

    total = consulta.count()
    itens = (
        consulta.order_by(SimulacaoORM.criada_em.desc(), SimulacaoORM.id.desc())
        .limit(limite)
        .offset(offset)
        .all()
    )
    return itens, total, limite, offset


def simulacao_resumo(sim: SimulacaoORM) -> dict:
    """Projeção não sensível de uma simulação para a listagem/histórico.

    Nunca inclui CPF em claro nem payload cifrado: o CPF fica cifrado em repouso
    e o índice cego não é reversível para os últimos dígitos, então é omitido.
    """
    return {
        "id": sim.id,
        "status": sim.status,
        "criada_em": sim.criada_em.isoformat() if sim.criada_em else None,
        "atualizada_em": sim.atualizada_em.isoformat() if sim.atualizada_em else None,
        "solicitado_por": sim.solicitado_por,
        "referencia_externa": sim.referencia_externa,
        "placa": sim.placa,
        "categoria": sim.categoria,
        "provedores": sim.provedores or [],
        "prazos_meses": sim.prazos_meses or (
            [sim.prazo_meses] if sim.prazo_meses is not None else []
        ),
        "num_resultados": len(sim.resultados),
    }


def cancelar_simulacao(db: Session, sim_id: str, cliente_id: str) -> SimulacaoORM | None:
    """Cancela um job ainda não terminal. Jobs já concluídos/falhos ficam inalterados."""
    sim = obter_simulacao(db, sim_id, cliente_id)
    if sim is None:
        return None
    if sim.status in ESTADOS_CANCELAVEIS:
        sim.status = "cancelada"
        sim.atualizada_em = datetime.now(timezone.utc)
        db.commit()
        db.refresh(sim)
    return sim


def _num(valor) -> float | None:
    return float(valor) if valor is not None else None


def para_pydantic(sim: SimulacaoORM) -> Simulacao:
    return Simulacao(
        id=sim.id,
        status=sim.status,
        criada_em=sim.criada_em.isoformat(),
        resultados=[
            ResultadoProvedor(
                provedor=r.provedor,
                status=r.status,
                valor_parcela=_num(r.valor_parcela),
                taxa_am=_num(r.taxa_am),
                prazo_meses=r.prazo_meses,
                valor_financiado=_num(r.valor_financiado),
                entrada=_num(r.entrada),
                codigo_erro=r.codigo_erro,
            )
            for r in sim.resultados
        ],
    )
