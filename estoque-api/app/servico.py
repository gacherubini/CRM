"""Regras do Estoque: validação, CRUD escopado por loja e transições de estado."""
import hashlib
import json
import re
import secrets
import uuid
import csv
import io
import ipaddress
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import quote, urlparse

from fastapi import HTTPException
from sqlalchemy import and_, case, exists, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import config, media
from app.auth import hash_token
from app.models_db import (
    Auditoria, CredencialServico, EntregaEvento, EventoSaida,
    IdempotenciaCriacaoVeiculo, Importacao, Loja, UsuarioEstoque, Veiculo,
    VeiculoFoto, WebhookDestino,
)


def _json_seguro(valor):
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, datetime):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {k: _json_seguro(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_json_seguro(v) for v in valor]
    return valor


def _registrar_operacao(
    db: Session,
    veiculo: Veiculo,
    acao: str,
    ator_papel: str,
    dados: dict | None = None,
    evento: str | None = None,
) -> None:
    dados_seguros = _json_seguro(dados or {})
    db.add(
        Auditoria(
            loja_id=veiculo.loja_id,
            recurso="veiculo",
            recurso_id=veiculo.id,
            acao=acao,
            ator_papel=ator_papel,
            dados=dados_seguros,
        )
    )
    if evento:
        db.add(
            EventoSaida(
                loja_id=veiculo.loja_id,
                tipo=evento,
                agregado_id=veiculo.id,
                payload={
                    "evento": evento,
                    "veiculo_id": veiculo.id,
                    "loja_id": veiculo.loja_id,
                    "status": veiculo.status,
                    "publicado": veiculo.publicado,
                },
            )
        )


def criar_loja(
    db: Session, nome: str, slug: str, whatsapp: str | None = None, papel: str = "dono"
) -> tuple[Loja, str]:
    """Cria a loja + uma credencial de serviço. Retorna (loja, token em claro)."""
    if db.query(Loja).filter(Loja.slug == slug).first():
        raise HTTPException(status_code=409, detail="slug já existe")
    if papel not in config.PAPEIS:
        raise HTTPException(status_code=422, detail="papel inválido")
    loja = Loja(id=str(uuid.uuid4()), nome=nome, slug=slug, whatsapp=whatsapp)
    db.add(loja)
    db.flush()
    token = secrets.token_urlsafe(24)
    db.add(CredencialServico(token_hash=hash_token(token), loja_id=loja.id, papel=papel))
    db.commit()
    db.refresh(loja)
    return loja, token


def criar_credencial(db: Session, slug: str, papel: str) -> tuple[Loja, str]:
    """Emite uma credencial adicional sem recriar ou expor segredos anteriores."""
    if papel not in config.PAPEIS:
        raise HTTPException(status_code=422, detail="papel inválido")
    loja = db.query(Loja).filter(Loja.slug == slug).first()
    if loja is None:
        raise HTTPException(status_code=404, detail="loja não encontrada")
    token = secrets.token_urlsafe(32)
    db.add(CredencialServico(token_hash=hash_token(token), loja_id=loja.id, papel=papel))
    db.commit()
    db.refresh(loja)
    return loja, token


def criar_usuario_estoque(
    db: Session, slug: str, email: str, nome: str, senha: str, papel: str
) -> UsuarioEstoque:
    from app.admin_auth import hash_senha

    if papel not in config.PAPEIS:
        raise HTTPException(status_code=422, detail="papel inválido")
    loja = db.query(Loja).filter(Loja.slug == slug).first()
    if loja is None:
        raise HTTPException(status_code=404, detail="loja não encontrada")
    email = email.strip().lower()
    if db.query(UsuarioEstoque).filter(
        UsuarioEstoque.loja_id == loja.id, UsuarioEstoque.email == email
    ).first():
        raise HTTPException(status_code=409, detail="e-mail já cadastrado nesta loja")
    usuario = UsuarioEstoque(
        loja_id=loja.id,
        email=email,
        nome=nome.strip(),
        senha_hash=hash_senha(senha),
        papel=papel,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


# Placa Mercosul (ABC1D23) e formato antigo (ABC1234) compartilham o mesmo molde:
# 3 letras, 1 dígito, 1 letra-ou-dígito, 2 dígitos.
_PLACA_RE = re.compile(r"^[A-Z]{3}[0-9][0-9A-Z][0-9]{2}$")
_STORAGE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,500}$")


def _validar_url_midia_publica(valor: str) -> str:
    """Aceita somente HTTPS público e estável; nunca paths/base64/hosts internos."""
    url = str(valor or "").strip()
    if not url or len(url) > config.MEDIA_URL_MAX_CHARS:
        raise HTTPException(status_code=422, detail="URL de foto inválida")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or host == "localhost"
        or host.endswith((".localhost", ".local", ".internal"))
    ):
        raise HTTPException(
            status_code=422,
            detail="foto deve usar URL HTTPS pública e estável, sem credenciais ou query",
        )
    try:
        endereco = ipaddress.ip_address(host)
    except ValueError:
        endereco = None
    if endereco is not None and not endereco.is_global:
        raise HTTPException(status_code=422, detail="host privado não é permitido para foto")
    if config.MEDIA_ALLOWED_HOSTS and host not in config.MEDIA_ALLOWED_HOSTS:
        raise HTTPException(status_code=422, detail="host de foto não autorizado")
    return url


def _url_por_storage_key(storage_key: str) -> str:
    chave = str(storage_key or "").strip()
    if (
        not config.MEDIA_PUBLIC_BASE_URL
        or not _STORAGE_KEY_RE.fullmatch(chave)
        or ".." in chave.split("/")
        or "//" in chave
    ):
        raise HTTPException(
            status_code=422,
            detail="storage_key inválida ou ESTOQUE_MEDIA_PUBLIC_BASE_URL não configurada",
        )
    base = _validar_url_midia_publica(config.MEDIA_PUBLIC_BASE_URL)
    caminho = "/".join(quote(parte, safe="._-") for parte in chave.split("/"))
    return _validar_url_midia_publica(f"{base}/{caminho}")


def _content_type_legado(url: str) -> str | None:
    path = urlparse(url).path.lower()
    if path.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if path.endswith(".png"):
        return "image/png"
    if path.endswith(".webp"):
        return "image/webp"
    return None


def _normalizar_fotos(fotos: list[dict], *, legado: bool = False) -> list[dict]:
    if len(fotos) > config.MEDIA_MAX_FOTOS:
        raise HTTPException(
            status_code=422,
            detail=f"limite de {config.MEDIA_MAX_FOTOS} fotos por veículo",
        )
    normalizadas: list[dict] = []
    urls: set[str] = set()
    ordens: set[int] = set()
    capas = 0
    capa_declarada = any("capa" in item for item in fotos)
    for indice, item in enumerate(fotos):
        url_recebida = item.get("url")
        storage_key = item.get("storage_key")
        if bool(url_recebida) == bool(storage_key):
            raise HTTPException(
                status_code=422, detail="informe exatamente url ou storage_key para cada foto"
            )
        url = (
            _validar_url_midia_publica(url_recebida)
            if url_recebida
            else _url_por_storage_key(storage_key)
        )
        if url in urls:
            raise HTTPException(status_code=422, detail="foto duplicada")
        urls.add(url)

        content_type = item.get("content_type") or (_content_type_legado(url) if legado else None)
        if content_type not in config.MEDIA_CONTENT_TYPES:
            raise HTTPException(
                status_code=422,
                detail="content_type inválido (use image/jpeg, image/png ou image/webp)",
            )
        tamanho = item.get("tamanho_bytes")
        if not legado and tamanho is None:
            raise HTTPException(status_code=422, detail="tamanho_bytes é obrigatório")
        if tamanho is not None and not (1 <= int(tamanho) <= config.MEDIA_MAX_BYTES):
            raise HTTPException(
                status_code=422,
                detail=f"foto excede o limite de {config.MEDIA_MAX_BYTES} bytes",
            )
        ordem = indice if item.get("ordem") is None else int(item["ordem"])
        if ordem < 0 or ordem in ordens:
            raise HTTPException(status_code=422, detail="ordem de foto inválida ou duplicada")
        ordens.add(ordem)
        capa = bool(item.get("capa")) if capa_declarada else indice == 0
        capas += int(capa)
        normalizadas.append(
            {
                "url": url,
                "content_type": content_type,
                "tamanho_bytes": int(tamanho) if tamanho is not None else None,
                "ordem": ordem,
                "capa": capa,
            }
        )
    if normalizadas and capas != 1:
        raise HTTPException(status_code=422, detail="defina exatamente uma foto como capa")
    return sorted(normalizadas, key=lambda foto: foto["ordem"])


def normalizar_placa(valor: str | None) -> str | None:
    """MAIÚSCULAS, sem hífen/espaços. Vazio vira None (placa é opcional)."""
    if valor is None:
        return None
    limpa = re.sub(r"[\s\-]", "", str(valor)).upper()
    return limpa or None


def validar_placa(valor: str | None) -> str | None:
    placa = normalizar_placa(valor)
    if placa is None:
        return None
    if not _PLACA_RE.match(placa):
        raise HTTPException(
            status_code=422, detail="placa inválida (use Mercosul ABC1D23 ou antigo ABC1234)"
        )
    return placa


def _placa_em_uso(
    db: Session, loja_id: str, placa: str, ignorar_id: str | None = None
) -> bool:
    q = db.query(Veiculo).filter(Veiculo.loja_id == loja_id, Veiculo.placa == placa)
    if ignorar_id:
        q = q.filter(Veiculo.id != ignorar_id)
    return db.query(q.exists()).scalar()


def _validar(dados: dict) -> None:
    if dados.get("tipo") not in config.TIPOS:
        raise HTTPException(status_code=422, detail="tipo inválido (moto|carro)")
    preco = dados.get("preco")
    if preco is None or float(preco) <= 0:
        raise HTTPException(status_code=422, detail="preço deve ser > 0")
    ano = dados.get("ano_modelo")
    if ano is None or not (1900 <= int(ano) <= 2100):
        raise HTTPException(status_code=422, detail="ano_modelo fora do intervalo")
    if dados.get("km") is not None and int(dados["km"]) < 0:
        raise HTTPException(status_code=422, detail="km não pode ser negativo")
    if dados.get("custo") is not None and float(dados["custo"]) < 0:
        raise HTTPException(status_code=422, detail="custo não pode ser negativo")


def _hash_idempotencia(valor: str) -> str:
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()


def _hash_requisicao(dados: dict) -> str:
    serializado = json.dumps(
        _json_seguro(dados),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


def _idempotencia_existente(
    db: Session,
    loja_id: str,
    chave_hash: str,
    requisicao_hash: str,
) -> Veiculo | None:
    registro = (
        db.query(IdempotenciaCriacaoVeiculo)
        .filter(
            IdempotenciaCriacaoVeiculo.loja_id == loja_id,
            IdempotenciaCriacaoVeiculo.chave_hash == chave_hash,
        )
        .first()
    )
    if registro is None:
        return None
    if registro.requisicao_hash != requisicao_hash:
        raise HTTPException(
            status_code=409,
            detail="Idempotency-Key já utilizada com outro cadastro",
        )
    return obter_veiculo(db, loja_id, registro.veiculo_id)


def criar_veiculo(
    db: Session,
    loja_id: str,
    dados: dict,
    ator_papel: str = "sistema",
    idempotency_key: str | None = None,
) -> Veiculo:
    dados = dict(dados)
    _validar(dados)
    if dados.get("foto_url"):
        dados["foto_url"] = _validar_url_midia_publica(dados["foto_url"])
    if "placa" in dados:
        placa = validar_placa(dados["placa"])
        if placa is None:
            dados.pop("placa")
        else:
            dados["placa"] = placa
    chave = str(idempotency_key or "").strip()
    if len(chave) > 512:
        raise HTTPException(status_code=422, detail="Idempotency-Key acima do limite")
    chave_hash = _hash_idempotencia(chave) if chave else None
    requisicao_hash = _hash_requisicao(dados) if chave_hash else None
    if chave_hash and requisicao_hash:
        existente = _idempotencia_existente(
            db, loja_id, chave_hash, requisicao_hash
        )
        if existente is not None:
            return existente

    placa = dados.get("placa")
    if placa and _placa_em_uso(db, loja_id, placa):
        raise HTTPException(status_code=409, detail="placa já cadastrada nesta loja")
    codigo = dados.get("codigo_interno")
    if codigo and db.query(Veiculo).filter(
        Veiculo.loja_id == loja_id, Veiculo.codigo_interno == codigo
    ).first():
        raise HTTPException(status_code=409, detail="código interno já existe nesta loja")
    v = Veiculo(id=str(uuid.uuid4()), loja_id=loja_id, **dados)
    db.add(v)
    try:
        db.flush()
        if chave_hash and requisicao_hash:
            db.add(
                IdempotenciaCriacaoVeiculo(
                    loja_id=loja_id,
                    chave_hash=chave_hash,
                    requisicao_hash=requisicao_hash,
                    veiculo_id=v.id,
                )
            )
        _registrar_operacao(db, v, "criado", ator_papel, dados, "vehicle.created")
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if chave_hash and requisicao_hash:
            existente = _idempotencia_existente(
                db, loja_id, chave_hash, requisicao_hash
            )
            if existente is not None:
                return existente
        raise HTTPException(
            status_code=409,
            detail="placa, código ou chave idempotente já cadastrada",
        ) from exc
    db.refresh(v)
    return v


def listar_veiculos(
    db: Session,
    loja_id: str,
    tipo: str | None = None,
    status: str | None = None,
    publicado: bool | None = None,
    busca: str | None = None,
    placa: str | None = None,
) -> list[Veiculo]:
    # Eager-load das fotos: evita N+1 (1 query/veículo em _midias_saida) na listagem,
    # que sobre Postgres remoto (suite-pg) vira segundos de round-trips sequenciais.
    q = db.query(Veiculo).options(selectinload(Veiculo.fotos)).filter(Veiculo.loja_id == loja_id)
    if tipo:
        q = q.filter(Veiculo.tipo == tipo)
    if status:
        q = q.filter(Veiculo.status == status)
    if publicado is not None:
        q = q.filter(Veiculo.publicado == publicado)
    placa_norm = normalizar_placa(placa)
    if placa_norm:
        q = q.filter(Veiculo.placa == placa_norm)
    if busca:
        termo = f"%{busca}%"
        q = q.filter((Veiculo.modelo.ilike(termo)) | (Veiculo.marca.ilike(termo)))
    return q.order_by(Veiculo.criado_em.desc()).all()


def obter_veiculo(db: Session, loja_id: str, veiculo_id: str) -> Veiculo:
    """404 se não existir OU pertencer a outra loja (não vaza existência)."""
    v = (
        db.query(Veiculo)
        .filter(Veiculo.id == veiculo_id, Veiculo.loja_id == loja_id)
        .first()
    )
    if v is None:
        raise HTTPException(status_code=404, detail="veículo não encontrado")
    return v


def obter_veiculo_por_placa(db: Session, loja_id: str, placa: str) -> Veiculo:
    """Resolve a unidade da loja autenticada pela placa. 404 se inexistente/outra loja."""
    placa_norm = normalizar_placa(placa)
    v = None
    if placa_norm:
        v = (
            db.query(Veiculo)
            .filter(Veiculo.loja_id == loja_id, Veiculo.placa == placa_norm)
            .first()
        )
    if v is None:
        raise HTTPException(status_code=404, detail="veículo não encontrado")
    return v


def atualizar_veiculo(
    db: Session, loja_id: str, veiculo_id: str, dados: dict, ator_papel: str = "sistema"
) -> Veiculo:
    v = obter_veiculo(db, loja_id, veiculo_id)
    campos = {k: val for k, val in dados.items() if val is not None}
    if "placa" in campos:
        placa = validar_placa(campos["placa"])
        campos["placa"] = placa  # None limpa a placa (opcional)
        if placa is not None and _placa_em_uso(db, loja_id, placa, ignorar_id=veiculo_id):
            raise HTTPException(status_code=409, detail="placa já cadastrada nesta loja")
    if campos.get("foto_url"):
        campos["foto_url"] = _validar_url_midia_publica(campos["foto_url"])
    # Revalida somente os campos afetados, reaproveitando os valores atuais.
    _validar(
        {
            "tipo": campos.get("tipo", v.tipo),
            "preco": campos.get("preco", v.preco),
            "ano_modelo": campos.get("ano_modelo", v.ano_modelo),
            "km": campos.get("km", v.km),
            "custo": campos.get("custo", v.custo),
        }
    )
    for k, val in campos.items():
        setattr(v, k, val)
    v.atualizado_em = datetime.now(timezone.utc)
    _registrar_operacao(db, v, "atualizado", ator_papel, {"campos": campos}, "vehicle.updated")
    db.commit()
    db.refresh(v)
    return v


def definir_publicado(
    db: Session,
    loja_id: str,
    veiculo_id: str,
    publicado: bool,
    ator_papel: str = "sistema",
) -> Veiculo:
    v = obter_veiculo(db, loja_id, veiculo_id)
    if publicado and v.status != "disponivel":
        raise HTTPException(status_code=409, detail="só veículo disponível pode ser publicado")
    v.publicado = publicado
    v.atualizado_em = datetime.now(timezone.utc)
    _registrar_operacao(
        db,
        v,
        "publicado" if publicado else "despublicado",
        ator_papel,
        {"publicado": publicado},
        "vehicle.published" if publicado else "vehicle.updated",
    )
    db.commit()
    db.refresh(v)
    return v


def reservar(db: Session, loja_id: str, veiculo_id: str, ator_papel: str = "sistema") -> Veiculo:
    agora = datetime.now(timezone.utc)
    resultado = db.execute(
        update(Veiculo)
        .where(
            Veiculo.id == veiculo_id,
            Veiculo.loja_id == loja_id,
            Veiculo.status == "disponivel",
        )
        .values(status="reservado", publicado=False, atualizado_em=agora)
        .execution_options(synchronize_session=False)
    )
    if resultado.rowcount != 1:
        obter_veiculo(db, loja_id, veiculo_id)
        raise HTTPException(status_code=409, detail="só veículo disponível pode ser reservado")
    v = obter_veiculo(db, loja_id, veiculo_id)
    db.refresh(v)
    _registrar_operacao(db, v, "reservado", ator_papel, evento="vehicle.reserved")
    db.commit()
    db.refresh(v)
    return v


def vender(db: Session, loja_id: str, veiculo_id: str, ator_papel: str = "sistema") -> Veiculo:
    agora = datetime.now(timezone.utc)
    resultado = db.execute(
        update(Veiculo)
        .where(
            Veiculo.id == veiculo_id,
            Veiculo.loja_id == loja_id,
            Veiculo.status.in_(("disponivel", "reservado")),
        )
        .values(status="vendido", publicado=False, atualizado_em=agora)
        .execution_options(synchronize_session=False)
    )
    if resultado.rowcount != 1:
        obter_veiculo(db, loja_id, veiculo_id)
        raise HTTPException(status_code=409, detail="veículo não pode ser vendido neste estado")
    v = obter_veiculo(db, loja_id, veiculo_id)
    db.refresh(v)
    _registrar_operacao(db, v, "vendido", ator_papel, evento="vehicle.sold")
    db.commit()
    db.refresh(v)
    return v


def substituir_fotos(
    db: Session,
    loja_id: str,
    veiculo_id: str,
    fotos: list[dict],
    ator_papel: str = "sistema",
    legado: bool = False,
) -> Veiculo:
    v = obter_veiculo(db, loja_id, veiculo_id)
    urls_anteriores = {item.url for item in v.fotos}
    if v.foto_url:
        urls_anteriores.add(v.foto_url)
    normalizadas = _normalizar_fotos(fotos, legado=legado)
    v.fotos.clear()
    db.flush()
    for foto in normalizadas:
        v.fotos.append(VeiculoFoto(loja_id=loja_id, **foto))
    capa = next((foto for foto in normalizadas if foto["capa"]), None)
    v.foto_url = capa["url"] if capa else None
    v.atualizado_em = datetime.now(timezone.utc)
    _registrar_operacao(
        db,
        v,
        "fotos_atualizadas",
        ator_papel,
        {"quantidade": len(normalizadas), "capa_definida": capa is not None},
        "vehicle.updated",
    )
    db.commit()
    db.refresh(v)
    urls_atuais = {item.url for item in v.fotos}
    if v.foto_url:
        urls_atuais.add(v.foto_url)
    for url in urls_anteriores - urls_atuais:
        _remover_midia_local_se_orfa(db, url)
    return v


def _remover_midia_local_se_orfa(db: Session, url: str) -> bool:
    if media.storage_key_da_url(url) is None:
        return False
    em_galeria = db.query(VeiculoFoto.id).filter(VeiculoFoto.url == url).first()
    em_legado = db.query(Veiculo.id).filter(Veiculo.foto_url == url).first()
    if em_galeria or em_legado:
        return False
    return media.remover_por_url(url)


def chaves_midia_referenciadas(db: Session) -> set[str]:
    urls = {url for (url,) in db.query(VeiculoFoto.url).all() if url}
    urls.update(url for (url,) in db.query(Veiculo.foto_url).all() if url)
    return {
        chave
        for url in urls
        if (chave := media.storage_key_da_url(url)) is not None
    }


def limpar_midias_orfas(db: Session, *, aplicar: bool = False) -> dict:
    """Varredura administrativa; por padrão apenas informa, sem apagar."""
    return media.limpar_orfas(chaves_midia_referenciadas(db), aplicar=aplicar)


def adicionar_foto(
    db: Session,
    loja_id: str,
    veiculo_id: str,
    foto: dict,
    ator_papel: str = "sistema",
    publicar: bool = False,
) -> Veiculo:
    """Anexa uma mídia idempotente sem apagar a galeria existente."""
    v = obter_veiculo(db, loja_id, veiculo_id)
    normalizada = _normalizar_fotos([foto])[0]
    existente = next((item for item in v.fotos if item.url == normalizada["url"]), None)
    if existente is not None:
        if publicar and not v.publicado:
            if v.status != "disponivel":
                raise HTTPException(status_code=409, detail="veículo indisponível não pode ser publicado")
            v.publicado = True
            _registrar_operacao(db, v, "publicado", ator_papel, evento="vehicle.published")
            db.commit()
            db.refresh(v)
        return v
    tipo_legado = _content_type_legado(v.foto_url) if not v.fotos and v.foto_url else None
    quantidade_existente = len(v.fotos) + int(tipo_legado is not None)
    if quantidade_existente >= config.MEDIA_MAX_FOTOS:
        raise HTTPException(status_code=422, detail=f"limite de {config.MEDIA_MAX_FOTOS} fotos por veículo")
    if publicar and v.status != "disponivel":
        raise HTTPException(status_code=409, detail="veículo indisponível não pode ser publicado")

    # Preserva uma foto legada quando ela tem tipo reconhecível.
    if tipo_legado:
        v.fotos.append(
            VeiculoFoto(
                loja_id=loja_id,
                url=v.foto_url,
                content_type=tipo_legado,
                tamanho_bytes=None,
                ordem=0,
                capa=True,
            )
        )
        db.flush()

    ordem = max((item.ordem for item in v.fotos), default=-1) + 1
    tem_capa = any(item.capa for item in v.fotos)
    normalizada["ordem"] = ordem
    normalizada["capa"] = not tem_capa
    v.fotos.append(VeiculoFoto(loja_id=loja_id, **normalizada))
    if normalizada["capa"]:
        v.foto_url = normalizada["url"]
    if publicar and not v.publicado:
        v.publicado = True
        _registrar_operacao(db, v, "publicado", ator_papel, evento="vehicle.published")
    v.atualizado_em = datetime.now(timezone.utc)
    _registrar_operacao(
        db,
        v,
        "foto_adicionada",
        ator_papel,
        {"quantidade": len(v.fotos), "capa": normalizada["capa"]},
        "vehicle.updated",
    )
    db.commit()
    db.refresh(v)
    return v


def listar_auditoria(db: Session, loja_id: str, limit: int = 100) -> list[Auditoria]:
    return (
        db.query(Auditoria)
        .filter(Auditoria.loja_id == loja_id)
        .order_by(Auditoria.criada_em.desc())
        .limit(min(max(limit, 1), 500))
        .all()
    )


def listar_eventos(db: Session, loja_id: str, status: str | None = None) -> list[EventoSaida]:
    q = db.query(EventoSaida).filter(EventoSaida.loja_id == loja_id)
    if status:
        q = q.filter(EventoSaida.status == status)
    return q.order_by(EventoSaida.criada_em.desc()).limit(500).all()


def configurar_webhook_destino(
    db: Session, slug: str, url: str, segredo: str, ativo: bool = True
) -> WebhookDestino:
    """Cria/atualiza o destino de entrega da outbox de uma loja. Segredo fica cifrado."""
    from app.cripto import cifrar

    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="url do webhook deve ser http(s)")
    if len(segredo) < 16:
        raise HTTPException(status_code=422, detail="segredo do webhook deve ter >= 16 caracteres")
    loja = db.query(Loja).filter(Loja.slug == slug).first()
    if loja is None:
        raise HTTPException(status_code=404, detail="loja não encontrada")
    destino = db.get(WebhookDestino, loja.id)
    if destino is None:
        destino = WebhookDestino(loja_id=loja.id)
        db.add(destino)
    destino.url = url
    destino.segredo_cifrado = cifrar(segredo)
    destino.ativo = ativo
    db.commit()
    db.refresh(destino)
    return destino


def obter_webhook_destino(db: Session, loja_id: str) -> WebhookDestino | None:
    return db.get(WebhookDestino, loja_id)


def listar_entregas(db: Session, loja_id: str, limit: int = 100) -> list[EntregaEvento]:
    return (
        db.query(EntregaEvento)
        .filter(EntregaEvento.loja_id == loja_id)
        .order_by(EntregaEvento.criada_em.desc())
        .limit(limit)
        .all()
    )


COLUNAS_CSV_OBRIGATORIAS = {"tipo", "marca", "modelo", "ano_modelo", "preco"}
COLUNAS_CSV = [
    "codigo_interno", "placa", "tipo", "marca", "modelo", "versao", "ano_modelo", "cor",
    "km", "preco", "custo", "foto_url", "status", "publicado",
]


def _ler_csv(conteudo: bytes) -> tuple[list[str], list[dict[str, str]]]:
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="CSV deve estar em UTF-8") from exc
    try:
        dialect = csv.Sniffer().sniff(texto[:4096], delimiters=",;")
    except csv.Error:
        dialect = csv.excel
    leitor = csv.DictReader(io.StringIO(texto), dialect=dialect)
    colunas = [str(c).strip() for c in (leitor.fieldnames or []) if c]
    faltantes = COLUNAS_CSV_OBRIGATORIAS - set(colunas)
    if faltantes:
        raise HTTPException(
            status_code=422, detail=f"colunas obrigatórias ausentes: {', '.join(sorted(faltantes))}"
        )
    linhas = [
        {str(k).strip(): (v or "").strip() for k, v in linha.items() if k}
        for linha in leitor
        if any((v or "").strip() for v in linha.values())
    ]
    if len(linhas) > 5000:
        raise HTTPException(status_code=422, detail="limite de 5000 linhas por importação")
    return colunas, linhas


def _numero_csv(valor: str, inteiro: bool = False):
    valor = valor.strip().replace("R$", "").replace(" ", "")
    if not valor:
        return 0 if inteiro else None
    if "," in valor:
        valor = valor.replace(".", "").replace(",", ".")
    numero = float(valor)
    return int(numero) if inteiro else numero


def _dados_linha_csv(linha: dict[str, str]) -> dict:
    dados = {
        "tipo": linha.get("tipo", "").lower(),
        "marca": linha.get("marca", "").strip(),
        "modelo": linha.get("modelo", "").strip(),
        "ano_modelo": _numero_csv(linha.get("ano_modelo", ""), inteiro=True),
        "preco": _numero_csv(linha.get("preco", "")),
        "km": _numero_csv(linha.get("km", ""), inteiro=True),
    }
    for campo in ("codigo_interno", "versao", "cor", "foto_url"):
        if linha.get(campo, "").strip():
            dados[campo] = linha[campo].strip()
    if linha.get("placa", "").strip():
        dados["placa"] = validar_placa(linha["placa"])
    if linha.get("custo", "").strip():
        dados["custo"] = _numero_csv(linha["custo"])
    if not dados["marca"] or not dados["modelo"]:
        raise HTTPException(status_code=422, detail="marca e modelo são obrigatórios")
    _validar(dados)
    return dados


def previsualizar_csv(conteudo: bytes) -> dict:
    colunas, linhas = _ler_csv(conteudo)
    erros = []
    for numero, linha in enumerate(linhas, start=2):
        try:
            _dados_linha_csv(linha)
        except (HTTPException, ValueError) as exc:
            detalhe = exc.detail if isinstance(exc, HTTPException) else "valor numérico inválido"
            erros.append({"linha": numero, "erro": str(detalhe)})
    return {
        "colunas": colunas,
        "total_linhas": len(linhas),
        "amostra": linhas[:20],
        "erros": erros[:100],
        "valido": not erros,
    }


def importar_csv(
    db: Session,
    loja_id: str,
    conteudo: bytes,
    nome_arquivo: str,
    ator_papel: str,
    permitir_custo: bool,
) -> Importacao:
    _, linhas = _ler_csv(conteudo)
    registro = Importacao(
        loja_id=loja_id,
        nome_arquivo=nome_arquivo[:255],
        status="processando",
        total_linhas=len(linhas),
    )
    db.add(registro)
    db.commit()
    erros: list[dict] = []
    importadas = atualizadas = 0
    for numero, linha in enumerate(linhas, start=2):
        try:
            dados = _dados_linha_csv(linha)
            if "custo" in dados and not permitir_custo:
                raise HTTPException(status_code=403, detail="papel sem permissão para importar custo")
            codigo = dados.get("codigo_interno")
            existente = None
            if codigo:
                existente = db.query(Veiculo).filter(
                    Veiculo.loja_id == loja_id, Veiculo.codigo_interno == codigo
                ).first()
            if existente:
                atualizar_veiculo(db, loja_id, existente.id, dados, ator_papel)
                atualizadas += 1
            else:
                criar_veiculo(db, loja_id, dados, ator_papel)
                importadas += 1
        except (HTTPException, ValueError) as exc:
            db.rollback()
            detalhe = exc.detail if isinstance(exc, HTTPException) else "valor numérico inválido"
            erros.append({"linha": numero, "erro": str(detalhe)})
    registro = db.get(Importacao, registro.id)
    registro.importadas = importadas
    registro.atualizadas = atualizadas
    registro.erros = erros
    registro.status = "concluida_com_erros" if erros else "concluida"
    db.commit()
    db.refresh(registro)
    return registro


def exportar_csv(db: Session, loja_id: str, incluir_custo: bool) -> str:
    buffer = io.StringIO()
    campos = COLUNAS_CSV if incluir_custo else [c for c in COLUNAS_CSV if c != "custo"]
    writer = csv.DictWriter(buffer, fieldnames=campos, delimiter=";", lineterminator="\n")
    writer.writeheader()
    for v in listar_veiculos(db, loja_id):
        linha = {
            "codigo_interno": v.codigo_interno or "", "placa": v.placa or "",
            "tipo": v.tipo, "marca": v.marca,
            "modelo": v.modelo, "versao": v.versao or "", "ano_modelo": v.ano_modelo,
            "cor": v.cor or "", "km": v.km, "preco": f"{float(v.preco):.2f}",
            "foto_url": v.foto_url or "", "status": v.status,
            "publicado": "sim" if v.publicado else "nao",
        }
        if incluir_custo:
            linha["custo"] = f"{float(v.custo):.2f}" if v.custo is not None else ""
        writer.writerow(linha)
    return buffer.getvalue()


# --- API pública (read-only, por slug) ---------------------------------------


def obter_loja_por_slug(db: Session, slug: str) -> Loja:
    loja = db.query(Loja).filter(Loja.slug == slug).first()
    if loja is None:
        raise HTTPException(status_code=404, detail="loja não encontrada")
    return loja


def _expressao_tem_foto():
    """1 se há capa legada ou galeria; 0 caso contrário (ordenação da vitrine)."""
    tem_capa = and_(Veiculo.foto_url.isnot(None), Veiculo.foto_url != "")
    tem_galeria = exists().where(VeiculoFoto.veiculo_id == Veiculo.id)
    return case((or_(tem_capa, tem_galeria), 1), else_=0)


def listar_veiculos_publicos(
    db: Session,
    slug: str,
    tipo: str | None = None,
    marca: str | None = None,
    preco_min: float | None = None,
    preco_max: float | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[Loja, list[Veiculo], int]:
    loja = obter_loja_por_slug(db, slug)
    # Eager-load das fotos: mesma correção de N+1 aplicada à vitrine pública.
    q = db.query(Veiculo).options(selectinload(Veiculo.fotos)).filter(
        Veiculo.loja_id == loja.id,
        Veiculo.status == "disponivel",
        Veiculo.publicado.is_(True),
    )
    if tipo:
        q = q.filter(Veiculo.tipo == tipo)
    if marca:
        q = q.filter(Veiculo.marca.ilike(marca.strip()))
    if preco_min is not None:
        q = q.filter(Veiculo.preco >= preco_min)
    if preco_max is not None:
        q = q.filter(Veiculo.preco <= preco_max)
    total = q.count()
    # Com foto primeiro (vitrine); dentro do grupo, mais recentes.
    veiculos = (
        q.order_by(_expressao_tem_foto().desc(), Veiculo.criado_em.desc())
        .offset(offset)
        .limit(min(limit, 100))
        .all()
    )
    return loja, veiculos, total


def normalizar_whatsapp_loja(valor: str | None) -> str | None:
    """Normaliza telefone do CTA do catálogo (E.164 digits, BR com DDI 55).

    String vazia / None limpa o campo. Inválido → 422.
    """
    if valor is None:
        return None
    bruto = str(valor).strip()
    if not bruto:
        return None
    digitos = re.sub(r"\D", "", bruto)
    if len(digitos) in {10, 11}:
        digitos = f"55{digitos}"
    if not 10 <= len(digitos) <= 15:
        raise HTTPException(status_code=422, detail="WhatsApp inválido")
    return digitos


def atualizar_whatsapp_loja(db: Session, loja_id: str, whatsapp: str | None) -> Loja:
    loja = db.get(Loja, loja_id)
    if loja is None:
        raise HTTPException(status_code=404, detail="loja não encontrada")
    loja.whatsapp = normalizar_whatsapp_loja(whatsapp)
    db.commit()
    db.refresh(loja)
    return loja


def obter_veiculo_publico(db: Session, slug: str, veiculo_id: str) -> Veiculo:
    loja = obter_loja_por_slug(db, slug)
    v = (
        db.query(Veiculo)
        .filter(
            Veiculo.id == veiculo_id,
            Veiculo.loja_id == loja.id,
            Veiculo.status == "disponivel",
            Veiculo.publicado.is_(True),
        )
        .first()
    )
    if v is None:
        raise HTTPException(status_code=404, detail="veículo não encontrado")
    return v


def para_saida_publica(v: Veiculo) -> dict:
    """Saída da API pública — NUNCA inclui custo, código interno ou dados internos."""
    midias = _midias_saida(v)
    return {
        "id": v.id,
        "tipo": v.tipo,
        "marca": v.marca,
        "modelo": v.modelo,
        "versao": v.versao,
        "ano_modelo": v.ano_modelo,
        "cor": v.cor,
        "km": v.km,
        "preco": float(v.preco),
        "foto_url": _url_capa(v, midias),
        "fotos": [foto["url"] for foto in midias],
        "midias": midias,
        "midia_principal": _midia_principal(v, midias),
        "tem_foto": bool(midias),
    }


def para_saida_privada(v: Veiculo, incluir_custo: bool = True) -> dict:
    """Saída da API privada — inclui custo/código interno."""
    midias = _midias_saida(v)
    return {
        "id": v.id,
        "loja_id": v.loja_id,
        "tipo": v.tipo,
        "marca": v.marca,
        "modelo": v.modelo,
        "versao": v.versao,
        "ano_modelo": v.ano_modelo,
        "cor": v.cor,
        "km": v.km,
        "preco": float(v.preco),
        "status": v.status,
        "publicado": v.publicado,
        "placa": v.placa,
        "codigo_interno": v.codigo_interno,
        "foto_url": _url_capa(v, midias),
        "fotos": [foto["url"] for foto in midias],
        "midias": midias,
        "midia_principal": _midia_principal(v, midias),
        "tem_foto": bool(midias),
        "criado_em": v.criado_em.isoformat() if v.criado_em else None,
        "atualizado_em": v.atualizado_em.isoformat() if v.atualizado_em else None,
    } | ({"custo": float(v.custo) if v.custo is not None else None} if incluir_custo else {})


def _midias_saida(v: Veiculo) -> list[dict]:
    if v.fotos:
        return [
            {
                "id": foto.id,
                "url": foto.url,
                "content_type": foto.content_type,
                "tamanho_bytes": foto.tamanho_bytes,
                "ordem": foto.ordem,
                "capa": foto.capa,
            }
            for foto in sorted(v.fotos, key=lambda item: item.ordem)
        ]
    if v.foto_url:
        return [
            {
                "id": None,
                "url": v.foto_url,
                "content_type": _content_type_legado(v.foto_url),
                "tamanho_bytes": None,
                "ordem": 0,
                "capa": True,
            }
        ]
    return []


def _midia_principal(v: Veiculo, midias: list[dict]) -> dict | None:
    return next((foto for foto in midias if foto["capa"]), midias[0] if midias else None)


def _url_capa(v: Veiculo, midias: list[dict]) -> str | None:
    principal = _midia_principal(v, midias)
    return principal["url"] if principal else None
