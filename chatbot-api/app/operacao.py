"""Operação via WhatsApp (E5): números autorizados + cadastro de veículo no Estoque.

O n8n/LLM extrai campos e chama esta API. O Chatbot valida autorização e
delega a gravação ao Estoque (HTTP privado). Nunca grava veículo localmente
como fonte de verdade.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app import config
from app.inventory import InventoryWriteClient, get_inventory_write_client
from app.models_db import GrupoEstoque, NumeroAutorizado
from app.vehicle_photo import VehiclePhotoProcessor

AtorOperacao = NumeroAutorizado | GrupoEstoque

# Alinhado ao Estoque: Mercosul ABC1D23 ou antigo ABC1234.
_PLACA_RE = re.compile(r"^[A-Z]{3}[0-9][0-9A-Z][0-9]{2}$")
_PAPEIS = frozenset({"dono", "vendedor"})
_TIPOS = frozenset({"moto", "carro"})
_GATILHO_MENU = frozenset({"cadastro", "menu", "estoque", "operacao", "operação"})
_ENCERRAR = frozenset({"fim", "sair", "0", "cancelar", "menu"})
_CONFIRMAR = frozenset({"sim", "s", "yes", "confirmo", "confirma"})
_NEGAR = frozenset({"nao", "não", "n", "no", "cancelar"})
_CAMPOS_EDIT = frozenset({"preco", "preço", "km", "cor"})
_MODOS = frozenset(
    {"menu", "cadastrar", "listar", "editar", "despublicar", "vender"}
)
_PLACA_NA_LEGENDA_RE = re.compile(r"\b([A-Z]{3})[-\s]?([0-9][A-Z0-9][0-9]{2})\b", re.I)
logger = logging.getLogger("chatbot.operacao")

_TEXTO_MENU = (
    "Menu de estoque 🛠️\n"
    "1 - Cadastrar veículo\n"
    "2 - Ver veículos\n"
    "3 - Editar veículo\n"
    "4 - Despublicar (sumir do catálogo)\n"
    "5 - Marcar como vendido\n"
    "0 - Sair\n\n"
    "Responda com o número ou o nome da opção."
)

_TEXTO_MODO_CADASTRAR = (
    "Modo *cadastrar* 📝\n"
    "Envie os dados em *uma mensagem*:\n"
    "tipo (moto/carro), marca, modelo, ano, preço, km e placa.\n"
    "Ex.: Honda CG 160 2018 21900 18mil km ABC1D23\n\n"
    "Depois envie as *fotos com a placa na legenda* "
    "(ex.: legenda `ABC1D23`). A 1ª foto precisa da placa; "
    "as seguintes por 10 min podem ir sem repetir.\n\n"
    "Digite *menu* para voltar ou *fim* para sair."
)


def normalizar_telefone(valor: str | None) -> str:
    """Mantém só dígitos (DDI/DDD/número). Vazio vira string vazia."""
    if not valor:
        return ""
    return re.sub(r"\D", "", str(valor))


def variantes_telefone(valor: str | None) -> set[str]:
    """Gera formas equivalentes (com/sem 55 e com/sem 9º dígito BR) para match de autorizado."""
    base = normalizar_telefone(valor)
    if not base:
        return set()
    out: set[str] = {base}

    def _add(t: str) -> None:
        if t and t not in out:
            out.add(t)

    # com / sem DDI 55
    if base.startswith("55") and len(base) >= 12:
        _add(base[2:])
    elif not base.startswith("55") and 10 <= len(base) <= 11:
        _add("55" + base)

    # 9º dígito móvel BR: 55 + DDD(2) + [9] + 8 dígitos
    for cand in list(out):
        if cand.startswith("55") and len(cand) == 12:
            # 55 + DDD + 8 dígitos → inserir 9
            _add(cand[:4] + "9" + cand[4:])
        if cand.startswith("55") and len(cand) == 13 and cand[4] == "9":
            _add(cand[:4] + cand[5:])
        if not cand.startswith("55") and len(cand) == 10:
            _add(cand[:2] + "9" + cand[2:])
        if not cand.startswith("55") and len(cand) == 11 and cand[2] == "9":
            _add(cand[:2] + cand[3:])
    return out


def normalizar_placa(valor: str | None) -> str | None:
    if valor is None:
        return None
    limpa = re.sub(r"[\s\-]", "", str(valor)).upper()
    return limpa or None


def validar_placa(valor: str | None) -> str:
    placa = normalizar_placa(valor)
    if not placa:
        raise HTTPException(status_code=422, detail="faltou placa")
    if not _PLACA_RE.match(placa):
        raise HTTPException(
            status_code=422,
            detail="placa inválida (use Mercosul ABC1D23 ou antigo ABC1234)",
        )
    return placa


def _para_saida_numero(n: NumeroAutorizado) -> dict:
    return {
        "id": n.id,
        "telefone": n.telefone,
        "nome": n.nome,
        "papel": n.papel,
        "ativo": n.ativo,
        "criado_em": n.criado_em.isoformat() if n.criado_em else None,
    }


def listar_numeros(db: Session, loja_id: str) -> list[dict]:
    rows = (
        db.query(NumeroAutorizado)
        .filter(NumeroAutorizado.loja_id == loja_id)
        .order_by(NumeroAutorizado.criado_em.desc())
        .all()
    )
    return [_para_saida_numero(r) for r in rows]


def adicionar_numero(
    db: Session,
    loja_id: str,
    telefone: str,
    papel: str = "vendedor",
    ativo: bool = True,
    nome: str | None = None,
) -> dict:
    tel = normalizar_telefone(telefone)
    if len(tel) < 10:
        raise HTTPException(status_code=422, detail="telefone inválido")
    papel_norm = (papel or "vendedor").strip().lower()
    if papel_norm not in _PAPEIS:
        raise HTTPException(status_code=422, detail="papel inválido (dono|vendedor)")
    nome_norm = (nome or "").strip() or None

    existente = (
        db.query(NumeroAutorizado)
        .filter(NumeroAutorizado.loja_id == loja_id, NumeroAutorizado.telefone == tel)
        .first()
    )
    if existente:
        existente.papel = papel_norm
        existente.ativo = ativo
        if nome is not None:
            existente.nome = nome_norm
        if not ativo:
            existente.foto_placa_atual = None
            existente.foto_sessao_expira_em = None
        db.commit()
        db.refresh(existente)
        return _para_saida_numero(existente)

    row = NumeroAutorizado(
        id=str(uuid.uuid4()),
        loja_id=loja_id,
        telefone=tel,
        papel=papel_norm,
        ativo=ativo,
        nome=nome_norm,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="número já cadastrado") from exc
    db.refresh(row)
    return _para_saida_numero(row)


def remover_numero(db: Session, loja_id: str, telefone: str) -> dict:
    tel = normalizar_telefone(telefone)
    row = (
        db.query(NumeroAutorizado)
        .filter(NumeroAutorizado.loja_id == loja_id, NumeroAutorizado.telefone == tel)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="número não encontrado")
    db.delete(row)
    db.commit()
    return {"removido": True, "telefone": tel}


def normalizar_grupo_jid(valor: str | None) -> str:
    jid = str(valor or "").strip().lower()
    if (
        not jid
        or not jid.endswith("@g.us")
        or len(jid) > 120
        or any(char.isspace() or ord(char) < 32 for char in jid)
    ):
        raise HTTPException(status_code=422, detail="grupo de WhatsApp invalido")
    return jid


def obter_grupo_estoque(db: Session, loja_id: str) -> GrupoEstoque | None:
    return db.get(GrupoEstoque, loja_id)


def _para_saida_grupo(grupo: GrupoEstoque | None) -> dict | None:
    if grupo is None:
        return None
    return {
        "jid": grupo.grupo_jid,
        "nome": grupo.grupo_nome or grupo.grupo_jid,
        "atualizado_em": grupo.atualizado_em.isoformat() if grupo.atualizado_em else None,
    }


def salvar_grupo_estoque(
    db: Session,
    loja_id: str,
    grupo_jid: str,
    grupo_nome: str | None = None,
) -> dict:
    jid = normalizar_grupo_jid(grupo_jid)
    nome = str(grupo_nome or "").strip()[:160] or None
    grupo = obter_grupo_estoque(db, loja_id)
    if grupo is None:
        grupo = GrupoEstoque(loja_id=loja_id, grupo_jid=jid, grupo_nome=nome)
        db.add(grupo)
    else:
        mudou = grupo.grupo_jid != jid
        grupo.grupo_jid = jid
        grupo.grupo_nome = nome
        if mudou:
            grupo.foto_placa_atual = None
            grupo.foto_sessao_expira_em = None
            grupo.cadastro_expira_em = None
            grupo.operacao_modo = None
            grupo.operacao_ctx = None
    db.commit()
    db.refresh(grupo)
    return _para_saida_grupo(grupo) or {}


def remover_grupo_estoque(db: Session, loja_id: str) -> dict:
    grupo = obter_grupo_estoque(db, loja_id)
    if grupo is None:
        return {"removido": False}
    jid = grupo.grupo_jid
    db.delete(grupo)
    db.commit()
    return {"removido": True, "jid": jid}


def grupo_estoque_selecionado(db: Session, loja_id: str) -> dict | None:
    return _para_saida_grupo(obter_grupo_estoque(db, loja_id))


def _grupo_estoque_corresponde(
    grupo: GrupoEstoque | None, grupo_jid: str | None
) -> bool:
    if grupo is None or not grupo_jid:
        return False
    try:
        return grupo.grupo_jid == normalizar_grupo_jid(grupo_jid)
    except HTTPException:
        return False


def esta_autorizado(db: Session, loja_id: str, telefone: str) -> bool:
    return _numero_autorizado_ativo(db, loja_id, telefone) is not None


def _rows_autorizados_variantes(
    db: Session, loja_id: str, telefone: str, *, so_ativos: bool = True
) -> list[NumeroAutorizado]:
    """Todas as linhas do mesmo número (com/sem 55, com/sem 9º dígito)."""
    cands = variantes_telefone(telefone)
    if not cands:
        return []
    q = db.query(NumeroAutorizado).filter(
        NumeroAutorizado.loja_id == loja_id,
        NumeroAutorizado.telefone.in_(cands),
    )
    if so_ativos:
        q = q.filter(NumeroAutorizado.ativo.is_(True))
    # Preferir forma canônica (mais longa, tipicamente 55+DDD+9+8) e estável.
    return q.order_by(NumeroAutorizado.telefone.desc()).all()


def _escolher_row_autorizado(rows: list[NumeroAutorizado]) -> NumeroAutorizado | None:
    """Escolhe a linha com sessão mais útil; evita .first() aleatório entre duplicatas."""
    if not rows:
        return None

    def _score(r: NumeroAutorizado) -> tuple:
        sessao = 1 if _sessao_cadastro_aberta(r) else 0
        modo = 1 if (r.operacao_modo or "").strip() else 0
        foto = 1 if r.foto_placa_atual else 0
        return (sessao, modo, foto, len(r.telefone or ""), r.telefone or "")

    return max(rows, key=_score)


def _numero_autorizado_ativo(
    db: Session, loja_id: str, telefone: str
) -> NumeroAutorizado | None:
    return _escolher_row_autorizado(_rows_autorizados_variantes(db, loja_id, telefone))


def _siblings_autorizados(
    db: Session, numero: NumeroAutorizado
) -> list[NumeroAutorizado]:
    rows = _rows_autorizados_variantes(db, numero.loja_id, numero.telefone)
    if not rows:
        return [numero]
    # Garante que a instância atual está na lista (mesmo objeto de sessão).
    ids = {r.id for r in rows}
    if numero.id not in ids:
        rows.append(numero)
    return rows


def _alvos_sessao(db: Session, ator: AtorOperacao) -> list[AtorOperacao]:
    if isinstance(ator, NumeroAutorizado):
        return list(_siblings_autorizados(db, ator))
    return [ator]


def _ativar_sessao_fotos(
    db: Session, ator: AtorOperacao, placa: str
) -> bool:
    ttl = config.IMAGE_SESSION_TTL_SECONDS
    rows = _alvos_sessao(db, ator)
    if not rows or ttl <= 0:
        return False
    placa_ok = validar_placa(placa)
    expira = datetime.now(timezone.utc) + timedelta(seconds=ttl)
    for row in rows:
        row.foto_placa_atual = placa_ok
        row.foto_sessao_expira_em = expira
    db.commit()
    return True


def _placa_da_sessao_fotos(
    db: Session, ator: AtorOperacao
) -> str | None:
    rows = _alvos_sessao(db, ator)
    if not rows:
        return None
    agora = datetime.now(timezone.utc)
    placa_valida: str | None = None
    for numero in rows:
        if not numero.foto_placa_atual or not numero.foto_sessao_expira_em:
            continue
        expira = numero.foto_sessao_expira_em
        if expira.tzinfo is None:
            expira = expira.replace(tzinfo=timezone.utc)
        if expira <= agora:
            numero.foto_placa_atual = None
            numero.foto_sessao_expira_em = None
            continue
        placa_valida = validar_placa(numero.foto_placa_atual)
        break
    if placa_valida is None:
        db.commit()
        return None
    # Espelha a sessão válida em todas as variantes (evita sumir se o próximo
    # webhook vier com outro formato de telefone).
    for numero in rows:
        numero.foto_placa_atual = placa_valida
        if not numero.foto_sessao_expira_em or (
            (numero.foto_sessao_expira_em.replace(tzinfo=timezone.utc)
             if numero.foto_sessao_expira_em.tzinfo is None
             else numero.foto_sessao_expira_em)
            <= agora
        ):
            numero.foto_sessao_expira_em = agora + timedelta(
                seconds=max(1, config.IMAGE_SESSION_TTL_SECONDS)
            )
    db.commit()
    return placa_valida


def _tentar_ativar_sessao_fotos(
    db: Session, ator: AtorOperacao, placa: str
) -> bool:
    try:
        return _ativar_sessao_fotos(db, ator, placa)
    except SQLAlchemyError:
        db.rollback()
        logger.warning("sessão de fotos não persistida")
        return False


def _minutos_sessao_fotos() -> int:
    return max(1, (config.IMAGE_SESSION_TTL_SECONDS + 59) // 60)


def _sessao_cadastro_aberta(ator: AtorOperacao) -> bool:
    expira = ator.cadastro_expira_em
    if expira is None:
        return False
    if expira.tzinfo is None:
        expira = expira.replace(tzinfo=timezone.utc)
    return expira > datetime.now(timezone.utc)


def _abrir_ou_renovar_cadastro(db: Session, ator: AtorOperacao) -> None:
    ttl = max(1, config.CADASTRO_SESSION_TTL_SECONDS)
    expira = datetime.now(timezone.utc) + timedelta(seconds=ttl)
    for row in _alvos_sessao(db, ator):
        row.cadastro_expira_em = expira
    db.commit()


def _fechar_cadastro(db: Session, ator: AtorOperacao) -> None:
    for row in _alvos_sessao(db, ator):
        row.cadastro_expira_em = None
        row.operacao_modo = None
        row.operacao_ctx = None
    db.commit()


def _ctx_get(ator: AtorOperacao) -> dict[str, Any]:
    raw = ator.operacao_ctx
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _ctx_set(db: Session, ator: AtorOperacao, ctx: dict[str, Any] | None) -> None:
    payload = None if not ctx else json.dumps(ctx, ensure_ascii=False)
    for row in _alvos_sessao(db, ator):
        row.operacao_ctx = payload
    db.commit()


def _set_modo(
    db: Session,
    ator: AtorOperacao,
    modo: str | None,
    ctx: dict[str, Any] | None = None,
) -> None:
    ttl = max(1, config.CADASTRO_SESSION_TTL_SECONDS)
    expira = datetime.now(timezone.utc) + timedelta(seconds=ttl)
    payload = json.dumps(ctx, ensure_ascii=False) if ctx else None
    for row in _alvos_sessao(db, ator):
        row.cadastro_expira_em = expira
        row.operacao_modo = modo
        row.operacao_ctx = payload
    db.commit()


def _controle(resposta: str) -> dict:
    """Resposta fixa para o n8n enviar sem LLM."""
    return {"acao": "operacao_controle", "resposta": resposta}


def _fmt_preco(valor: Any) -> str:
    try:
        return (
            f"R$ {float(valor):,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )
    except (TypeError, ValueError):
        return str(valor)


def _fmt_linha_veiculo(v: dict, idx: int | None = None) -> str:
    placa = v.get("placa") or "s/placa"
    marca = v.get("marca") or ""
    modelo = v.get("modelo") or ""
    ano = v.get("ano_modelo") or ""
    preco = _fmt_preco(v.get("preco"))
    status = v.get("status") or ""
    pub = "pub" if v.get("publicado") else "off"
    prefix = f"{idx}. " if idx is not None else ""
    return f"{prefix}{marca} {modelo} {ano} | {preco} | {placa} | {status}/{pub}".strip()


def _formatar_lista(veiculos: list[dict], busca: str | None = None) -> str:
    if not veiculos:
        titulo = "Nenhum veículo encontrado"
        if busca:
            titulo += f" para «{busca}»"
        return titulo + ".\n\n" + _TEXTO_MENU
    cab = f"Veículos ({len(veiculos)})"
    if busca:
        cab += f" — busca «{busca}»"
    linhas = [cab, ""]
    for i, v in enumerate(veiculos, start=1):
        linhas.append(_fmt_linha_veiculo(v, i))
    linhas.extend(["", "Digite *menu* para voltar."])
    return "\n".join(linhas)


def _resolver_opcao_menu(normal: str) -> str | None:
    """Mapeia texto do usuário para modo interno."""
    if normal in {"1", "cadastrar", "cadastro", "novo", "criar"}:
        return "cadastrar"
    if normal in {"2", "ver", "listar", "lista", "veiculos", "veículos", "estoque"}:
        return "listar"
    if normal.startswith("2 ") or normal.startswith("listar ") or normal.startswith("ver "):
        return "listar"
    if normal in {"3", "editar", "edit", "alterar", "atualizar"}:
        return "editar"
    if normal in {"4", "despublicar", "apagar", "remover", "tirar", "ocultar"}:
        return "despublicar"
    if normal in {"5", "vender", "vendido", "venda"}:
        return "vender"
    return None


def _extrair_busca_listar(normal: str) -> str | None:
    for prefix in ("2 ", "listar ", "ver ", "busca ", "buscar "):
        if normal.startswith(prefix):
            termo = normal[len(prefix) :].strip()
            return termo or None
    return None


def _pedir_placa(acao_label: str) -> str:
    return (
        f"{acao_label}\n"
        "Envie a *placa* do veículo (ex.: ABC1D23).\n"
        "Ou digite *menu* para voltar."
    )


def _listar_estoque(busca: str | None = None) -> str:
    try:
        client = get_inventory_write_client()
        veiculos = client.listar_veiculos(busca=busca, limit=10)
    except HTTPException as exc:
        return f"Não consegui listar o estoque agora ({exc.detail}).\n\n{_TEXTO_MENU}"
    except Exception:
        logger.exception("falha ao listar estoque no menu WA")
        return f"Não consegui listar o estoque agora.\n\n{_TEXTO_MENU}"
    return _formatar_lista(veiculos, busca)


def _resolver_veiculo_por_texto(texto: str) -> tuple[dict | None, str | None]:
    """Retorna (veiculo, erro_msg)."""
    try:
        placa = validar_placa(texto)
    except HTTPException:
        return None, "Placa inválida. Use o formato ABC1D23 ou ABC1234."
    try:
        client = get_inventory_write_client()
        v = client.obter_por_placa(placa)
    except HTTPException as exc:
        return None, f"Erro ao buscar placa: {exc.detail}"
    if not v:
        return None, f"Não encontrei veículo com a placa {placa}."
    return v, None


def _handle_modo_editar(
    db: Session, numero: AtorOperacao, normal: str, texto: str
) -> dict:
    ctx = _ctx_get(numero)
    step = ctx.get("step") or "placa"

    if normal in _GATILHO_MENU or normal == "menu":
        _set_modo(db, numero, "menu", {})
        return _controle(_TEXTO_MENU)

    if step == "placa":
        v, err = _resolver_veiculo_por_texto(texto)
        if err:
            return _controle(err + "\nEnvie a placa ou *menu*.")
        _set_modo(
            db,
            numero,
            "editar",
            {"step": "campo", "placa": v.get("placa"), "veiculo_id": v.get("id")},
        )
        return _controle(
            f"Veículo: {_fmt_linha_veiculo(v)}\n\n"
            "O que deseja alterar?\n"
            "• preco\n• km\n• cor\n\n"
            "Ou *menu* para voltar."
        )

    if step == "campo":
        campo = normal.replace("ç", "c").replace("preço", "preco")
        if campo not in {"preco", "km", "cor"}:
            return _controle("Campo inválido. Use: preco, km ou cor.")
        ctx["step"] = "valor"
        ctx["campo"] = campo
        _set_modo(db, numero, "editar", ctx)
        return _controle(f"Envie o novo valor de *{campo}*.")

    if step == "valor":
        campo = ctx.get("campo")
        if campo not in {"preco", "km", "cor"}:
            _set_modo(db, numero, "menu", {})
            return _controle("Sessão de edição inconsistente.\n\n" + _TEXTO_MENU)
        valor_raw = (texto or "").strip()
        campos: dict[str, Any] = {}
        if campo == "preco":
            limpo = (
                valor_raw.lower()
                .replace("r$", "")
                .replace(".", "")
                .replace(",", ".")
                .strip()
            )
            try:
                campos["preco"] = float(limpo)
            except ValueError:
                return _controle("Preço inválido. Ex.: 21900 ou 21.900,00")
            if campos["preco"] <= 0:
                return _controle("Preço deve ser maior que zero.")
        elif campo == "km":
            dig = re.sub(r"\D", "", valor_raw)
            if not dig:
                return _controle("KM inválido. Ex.: 18000")
            campos["km"] = int(dig)
        else:
            campos["cor"] = valor_raw[:40]
        ctx["step"] = "confirma"
        ctx["campos"] = campos
        ctx["valor_txt"] = valor_raw
        _set_modo(db, numero, "editar", ctx)
        return _controle(
            f"Confirma alterar *{campo}* de {ctx.get('placa')} para *{valor_raw}*?\n"
            "Responda *SIM* ou *NÃO*."
        )

    if step == "confirma":
        if normal in _NEGAR:
            _set_modo(db, numero, "menu", {})
            return _controle("Edição cancelada.\n\n" + _TEXTO_MENU)
        if normal not in _CONFIRMAR:
            return _controle("Responda *SIM* para confirmar ou *NÃO* para cancelar.")
        veiculo_id = ctx.get("veiculo_id")
        campos = ctx.get("campos") or {}
        try:
            client = get_inventory_write_client()
            atualizado = client.atualizar_veiculo(str(veiculo_id), campos)
        except HTTPException as exc:
            _set_modo(db, numero, "menu", {})
            return _controle(f"Não consegui editar: {exc.detail}\n\n{_TEXTO_MENU}")
        _set_modo(db, numero, "menu", {})
        return _controle(
            f"Atualizado: {_fmt_linha_veiculo(atualizado)}\n\n{_TEXTO_MENU}"
        )

    _set_modo(db, numero, "menu", {})
    return _controle(_TEXTO_MENU)


def _handle_modo_acao(
    db: Session,
    numero: AtorOperacao,
    normal: str,
    texto: str,
    acao_estoque: str,
) -> dict:
    """despublicar ou vender com confirmação."""
    label = "Despublicar" if acao_estoque == "despublicar" else "Marcar como vendido"
    ctx = _ctx_get(numero)
    step = ctx.get("step") or "placa"

    if normal in _GATILHO_MENU or normal == "menu":
        _set_modo(db, numero, "menu", {})
        return _controle(_TEXTO_MENU)

    if step == "placa":
        v, err = _resolver_veiculo_por_texto(texto)
        if err:
            return _controle(err + "\nEnvie a placa ou *menu*.")
        _set_modo(
            db,
            numero,
            acao_estoque,
            {
                "step": "confirma",
                "placa": v.get("placa"),
                "veiculo_id": v.get("id"),
            },
        )
        return _controle(
            f"{label} o veículo?\n{_fmt_linha_veiculo(v)}\n\n"
            "Responda *SIM* ou *NÃO*."
        )

    if step == "confirma":
        if normal in _NEGAR:
            _set_modo(db, numero, "menu", {})
            return _controle(f"{label} cancelado.\n\n{_TEXTO_MENU}")
        if normal not in _CONFIRMAR:
            return _controle("Responda *SIM* para confirmar ou *NÃO* para cancelar.")
        veiculo_id = ctx.get("veiculo_id")
        try:
            client = get_inventory_write_client()
            atualizado = client.acao_veiculo(str(veiculo_id), acao_estoque)
        except HTTPException as exc:
            _set_modo(db, numero, "menu", {})
            return _controle(f"Não consegui concluir: {exc.detail}\n\n{_TEXTO_MENU}")
        _set_modo(db, numero, "menu", {})
        verbo = "despublicado" if acao_estoque == "despublicar" else "marcado como vendido"
        return _controle(
            f"Veículo {verbo}: {_fmt_linha_veiculo(atualizado)}\n\n{_TEXTO_MENU}"
        )

    _set_modo(db, numero, "menu", {})
    return _controle(_TEXTO_MENU)


def decidir_roteamento(
    db: Session,
    loja_id: str,
    telefone: str,
    texto: str | None,
    is_saved: bool | None,
    grupo_jid: str | None = None,
) -> dict:
    """Decide como o n8n trata a mensagem.

    Retorna acao em {cliente, ignorar, cadastro, operacao_controle, cadastro_controle}.

    Quando existe um grupo de estoque configurado, somente esse JID pode abrir
    o menu. O telefone do participante nao concede acesso fora do grupo.

    ``is_saved``: só ``False`` explícito conta como contato novo.

    Gate operacional (ADR 0001):
    - Loja não operacional → ``ignorar`` com captura passiva (sem atendimento).
    - Caminho de estoque (grupo_jid / cadastro / operação) exige módulo estoque ativo.
    - Caminho ``cliente`` exige apenas Loja operacional.
    """
    from app import provisioning

    if not provisioning.is_store_operational(db, loja_id):
        return {
            "acao": "ignorar",
            "resposta": None,
            "captura_passiva": True,
            "loja_operacional": False,
        }

    def _ignorar_estoque_inoperante() -> dict:
        return {
            "acao": "ignorar",
            "resposta": None,
            "captura_passiva": True,
            "loja_operacional": True,
        }

    grupo = obter_grupo_estoque(db, loja_id)
    numero: AtorOperacao | None
    if grupo_jid is not None:
        # Grupo de estoque: precisa do módulo estoque operacional.
        if not provisioning.is_module_operational(db, loja_id, "estoque"):
            return _ignorar_estoque_inoperante()
        if not _grupo_estoque_corresponde(grupo, grupo_jid):
            return {"acao": "ignorar", "resposta": None}
        numero = grupo
    elif grupo is not None:
        # Com grupo selecionado, o menu nunca opera no privado, nem para numeros
        # que continuam cadastrados na lista legada da equipe.
        if _numero_autorizado_ativo(db, loja_id, telefone) is not None:
            return {"acao": "ignorar", "resposta": None}
        if is_saved is False:
            return {"acao": "cliente", "resposta": None}
        return {"acao": "ignorar", "resposta": None}
    else:
        # Compatibilidade de implantacao: ate o grupo ser escolhido, o menu
        # textual antigo ainda funciona para numeros autorizados.
        numero = _numero_autorizado_ativo(db, loja_id, telefone)

    if numero is None:
        if is_saved is False:
            return {"acao": "cliente", "resposta": None}
        return {"acao": "ignorar", "resposta": None}

    # A partir daqui: menu/cadastro/operação de estoque.
    if not provisioning.is_module_operational(db, loja_id, "estoque"):
        return _ignorar_estoque_inoperante()

    normal = (texto or "").strip().casefold()
    # Compat: cadastro_controle ainda aceito no n8n (= operacao_controle)
    def _ctrl(msg: str) -> dict:
        r = _controle(msg)
        # alias legado para o gate do n8n atual
        r["acao"] = "cadastro_controle"
        return r

    # Gatilho abre (ou reabre) o menu
    if normal in _GATILHO_MENU:
        _set_modo(db, numero, "menu", {})
        return _ctrl(_TEXTO_MENU)

    if not _sessao_cadastro_aberta(numero):
        return {"acao": "ignorar", "resposta": None}

    # Encerrar sessão
    if normal in {"fim", "sair", "0"}:
        _fechar_cadastro(db, numero)
        return _ctrl("Menu encerrado. Envie *cadastro* ou *menu* quando quiser voltar.")

    modo = (numero.operacao_modo or "menu").strip().lower()
    if modo not in _MODOS:
        modo = "menu"

    # Voltar ao menu de qualquer subfluxo
    if normal == "menu" and modo != "menu":
        _set_modo(db, numero, "menu", {})
        return _ctrl(_TEXTO_MENU)

    if modo == "menu":
        opcao = _resolver_opcao_menu(normal)
        if opcao == "cadastrar":
            _set_modo(db, numero, "cadastrar", {})
            return _ctrl(_TEXTO_MODO_CADASTRAR)
        if opcao == "listar":
            busca = _extrair_busca_listar(normal)
            _set_modo(db, numero, "menu", {})
            return _ctrl(_listar_estoque(busca))
        if opcao == "editar":
            _set_modo(db, numero, "editar", {"step": "placa"})
            return _ctrl(_pedir_placa("Editar veículo ✏️"))
        if opcao == "despublicar":
            _set_modo(db, numero, "despublicar", {"step": "placa"})
            return _ctrl(_pedir_placa("Despublicar (some do catálogo) 🙈"))
        if opcao == "vender":
            _set_modo(db, numero, "vender", {"step": "placa"})
            return _ctrl(_pedir_placa("Marcar como vendido ✅"))
        # texto livre no menu: reexibe opções
        _abrir_ou_renovar_cadastro(db, numero)
        return _ctrl(
            "Não entendi essa opção.\n\n" + _TEXTO_MENU
        )

    if modo == "cadastrar":
        if normal in _GATILHO_MENU or normal == "menu":
            _set_modo(db, numero, "menu", {})
            return _ctrl(_TEXTO_MENU)
        # Se mandar "1"/"cadastrar" de novo, reexplica em vez de ir pro LLM.
        if _resolver_opcao_menu(normal) == "cadastrar":
            _abrir_ou_renovar_cadastro(db, numero)
            return _ctrl(_TEXTO_MODO_CADASTRAR)
        # Texto livre → LLM extrai e chama cadastrar_veiculo
        _abrir_ou_renovar_cadastro(db, numero)
        return {"acao": "cadastro", "resposta": None}

    if modo == "editar":
        return _handle_modo_editar(db, numero, normal, texto or "")

    if modo == "despublicar":
        return _handle_modo_acao(db, numero, normal, texto or "", "despublicar")

    if modo == "vender":
        return _handle_modo_acao(db, numero, normal, texto or "", "vender")

    _set_modo(db, numero, "menu", {})
    return _ctrl(_TEXTO_MENU)


def _exigir_autorizado(db: Session, loja_id: str, telefone: str) -> str:
    tel = normalizar_telefone(telefone)
    if not tel:
        raise HTTPException(status_code=422, detail="faltou telefone do solicitante")
    if not esta_autorizado(db, loja_id, tel):
        raise HTTPException(status_code=403, detail="não autorizado")
    return tel


def _validar_campos_veiculo(dados: dict[str, Any]) -> dict[str, Any]:
    """Validação orientada a WhatsApp — mensagens curtas e legíveis."""
    faltas: list[str] = []

    tipo = (dados.get("tipo") or "").strip().lower()
    if not tipo:
        faltas.append("tipo")
    elif tipo not in _TIPOS:
        raise HTTPException(status_code=422, detail="tipo inválido (moto|carro)")

    marca = (dados.get("marca") or "").strip()
    if not marca:
        faltas.append("marca")

    modelo = (dados.get("modelo") or "").strip()
    if not modelo:
        faltas.append("modelo")

    ano = dados.get("ano_modelo")
    if ano is None:
        faltas.append("ano")
    else:
        try:
            ano = int(ano)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="ano inválido") from exc
        if not (1900 <= ano <= 2100):
            raise HTTPException(status_code=422, detail="ano inválido")

    preco = dados.get("preco")
    if preco is None:
        faltas.append("valor")
    else:
        try:
            preco = float(preco)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="valor inválido") from exc
        if preco <= 0:
            raise HTTPException(status_code=422, detail="valor deve ser > 0")

    if faltas:
        # Uma falta → mensagem singular; várias → lista.
        if faltas == ["valor"]:
            raise HTTPException(status_code=422, detail="faltou valor")
        if len(faltas) == 1:
            raise HTTPException(status_code=422, detail=f"faltou {faltas[0]}")
        raise HTTPException(
            status_code=422, detail="faltou " + ", ".join(faltas)
        )

    placa = validar_placa(dados.get("placa"))

    km = dados.get("km", 0)
    try:
        km = int(km if km is not None else 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="km inválido") from exc
    if km < 0:
        raise HTTPException(status_code=422, detail="km não pode ser negativo")

    payload: dict[str, Any] = {
        "tipo": tipo,
        "marca": marca,
        "modelo": modelo,
        "ano_modelo": ano,
        "preco": preco,
        "km": km,
        "placa": placa,
        # Cadastro operacional pelo WhatsApp deve chegar até a vitrine.
        "publicado": True,
    }
    for opcional in ("versao", "cor", "codigo_interno", "foto_url"):
        val = dados.get(opcional)
        if val is not None and str(val).strip():
            payload[opcional] = str(val).strip()
    return payload


def _resumo_veiculo(v: dict) -> str:
    marca = v.get("marca") or ""
    modelo = v.get("modelo") or ""
    ano = v.get("ano_modelo") or ""
    preco = v.get("preco")
    placa = v.get("placa") or ""
    try:
        preco_fmt = f"R$ {float(preco):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        preco_fmt = str(preco)
    return f"{marca} {modelo} {ano} — {preco_fmt} — placa {placa}".strip()


def _saida_veiculo_cadastro(
    db: Session,
    ator: AtorOperacao,
    solicitante: str,
    veiculo: dict[str, Any],
    *,
    ja_existia: bool,
) -> dict:
    placa = str(veiculo.get("placa") or "")
    sessao_ativa = _tentar_ativar_sessao_fotos(db, ator, placa) if placa else False
    resumo = _resumo_veiculo(veiculo)
    if ja_existia:
        mensagem = f"Veículo já estava no estoque: {resumo}."
    else:
        mensagem = f"Veículo cadastrado e publicado no catálogo: {resumo}."
    if sessao_ativa:
        mensagem += (
            f" Agora envie as *fotos com a placa `{placa}` na legenda* "
            f"(a 1ª precisa da placa; nas próximas {_minutos_sessao_fotos()} min "
            "pode mandar sem repetir)."
        )
    elif placa:
        mensagem += (
            f" Agora envie as *fotos com a placa `{placa}` na legenda* da imagem."
        )
    return {
        "ok": True,
        "mensagem": mensagem,
        "ja_existia": ja_existia,
        "veiculo": {
            "id": veiculo.get("id"),
            "tipo": veiculo.get("tipo"),
            "marca": veiculo.get("marca"),
            "modelo": veiculo.get("modelo"),
            "ano_modelo": veiculo.get("ano_modelo"),
            "preco": veiculo.get("preco"),
            "km": veiculo.get("km"),
            "placa": veiculo.get("placa"),
            "status": veiculo.get("status"),
            "publicado": veiculo.get("publicado"),
            "foto_url": veiculo.get("foto_url"),
        },
        "solicitante": solicitante,
    }


def criar_veiculo_autorizado(
    db: Session,
    loja_id: str,
    telefone_solicitante: str,
    dados_veiculo: dict[str, Any],
    write_client: InventoryWriteClient,
    idempotency_key: str | None = None,
    grupo_jid: str | None = None,
) -> dict:
    """Autoriza o telefone, valida campos e cria no Estoque via HTTP."""
    grupo = obter_grupo_estoque(db, loja_id)
    tel = normalizar_telefone(telefone_solicitante)
    if grupo is not None:
        if not _grupo_estoque_corresponde(grupo, grupo_jid):
            raise HTTPException(
                status_code=403,
                detail="cadastro permitido somente no grupo de estoque configurado",
            )
        ator: AtorOperacao = grupo
    else:
        tel = _exigir_autorizado(db, loja_id, telefone_solicitante)
        ator_numero = _numero_autorizado_ativo(db, loja_id, tel)
        if ator_numero is None:
            raise HTTPException(status_code=403, detail="nao autorizado")
        ator = ator_numero
    payload = _validar_campos_veiculo(dados_veiculo)

    # Idempotency-Key: se o caller não mandar, deriva de loja+placa+campos estáveis
    # para reenvios do mesmo cadastro no WhatsApp não duplicarem quando o Estoque suportar.
    key = idempotency_key or f"wa-veiculo:{loja_id}:{payload['placa']}:{payload['marca']}:{payload['modelo']}:{payload['ano_modelo']}"

    try:
        criado = write_client.criar_veiculo(payload, idempotency_key=key)
    except HTTPException as exc:
        # Placa já cadastrada: reabre sessão de fotos em vez de falhar o fluxo WA.
        if exc.status_code == 409:
            existente = write_client.obter_por_placa(payload["placa"])
            if existente:
                return _saida_veiculo_cadastro(
                    db, ator, tel, existente, ja_existia=True
                )
        raise
    return _saida_veiculo_cadastro(db, ator, tel, criado, ja_existia=False)


def anexar_foto_whatsapp(
    db: Session,
    loja_id: str,
    instancia: str,
    telefone_solicitante: str,
    provider_message_id: str,
    legenda: str | None,
    mime_type: str | None,
    processor: VehiclePhotoProcessor,
    grupo_jid: str | None = None,
) -> dict:
    """Vincula imagem somente quando veio do grupo de estoque selecionado."""
    grupo = obter_grupo_estoque(db, loja_id)
    if not _grupo_estoque_corresponde(grupo, grupo_jid):
        return {
            "ok": False,
            "ignorar": True,
            "mensagem": None,
        }
    encontrada = _PLACA_NA_LEGENDA_RE.search(str(legenda or "").upper())
    placa_explicita = bool(encontrada)
    placa = (
        validar_placa("".join(encontrada.groups()))
        if encontrada
        else _placa_da_sessao_fotos(db, grupo)
    )
    if not placa:
        return {
            "ok": False,
            "mensagem": "Envie a primeira foto com a placa na legenda, por exemplo: ABC1D23. As próximas podem ser enviadas sem repetir a placa.",
        }
    resultado = processor.processar(
        instancia,
        provider_message_id,
        placa,
        mime_type,
    )
    if resultado.get("ok"):
        sessao_ativa = _tentar_ativar_sessao_fotos(
            db, grupo, placa
        )
        if placa_explicita and sessao_ativa:
            resultado["mensagem"] = str(
                resultado.get("mensagem") or "Foto adicionada ao estoque e ao catálogo."
            ) + (
                " As próximas fotos podem ser enviadas sem repetir a placa por "
                f"{_minutos_sessao_fotos()} min."
            )
    return resultado
