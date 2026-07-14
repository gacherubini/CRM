"""Credenciais de portal bancário por cliente+provedor (Plano #1A, Task 11).

Guarda o acesso do lojista ao portal de cada banco com a senha CIFRADA em repouso,
reutilizando ``app.cripto`` (Fernet + ``MOTOR_ENCRYPTION_KEY``) — a mesma camada que
protege o payload pessoal do job. Regras:

- a senha nunca é devolvida em claro (GET só devolve máscara ``****``);
- leitura on-demand: o worker lê e decifra a cada uso, então um PUT de rotação passa
  a valer no próximo job SEM restart (nada é cacheado em memória);
- isolamento por cliente: cada credencial é escopada por ``cliente_id``;
- auditoria registra o ator que alterou, sem logar a senha;
- métrica de falha de autenticação por provedor (contador ``falhas_login``), sem
  jamais expor o segredo.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import cripto
from app.models_db import AuditoriaORM, CredencialProvedorORM
from app.motor.providers import (
    campos_credencial_obrigatorios,
    normalizar_provedor,
)

MASCARA = "****"


class CredencialEntrada(BaseModel):
    # usuario/senha mantêm compatibilidade com portais. ``campos`` permite APIs
    # com mais segredos (PAN: api_key + secret_key + usuário + senha + loja).
    usuario: str | None = None
    senha: str | None = None
    campos: dict[str, str] = Field(default_factory=dict)
    habilitado: bool = True


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _mascarar(cred: CredencialProvedorORM) -> dict:
    """Projeção segura: identifica a credencial sem nunca expor a senha em claro."""
    config = _decifrar_config(cred)
    obrigatorios = campos_credencial_obrigatorios(cred.provedor)
    return {
        "provedor": cred.provedor,
        "usuario": cred.usuario,
        "senha_configurada": True,
        "senha_mascara": MASCARA,
        "habilitado": cred.habilitado,
        "atualizado_em": cred.atualizado_em.isoformat() if cred.atualizado_em else None,
        "ultimo_sucesso_em": (
            cred.ultimo_sucesso_em.isoformat() if cred.ultimo_sucesso_em else None
        ),
        "ultimo_erro_sanitizado": cred.ultimo_erro_sanitizado,
        "falhas_login": cred.falhas_login,
        "campos_configurados": sorted(k for k, v in config.items() if str(v).strip()),
        "configuracao_completa": bool(obrigatorios) and obrigatorios.issubset(
            {k for k, v in config.items() if str(v).strip()}
        ),
    }


def _vazia(provedor: str) -> dict:
    """Projeção de um provedor sem credencial configurada para o cliente."""
    return {
        "provedor": provedor,
        "usuario": None,
        "senha_configurada": False,
        "senha_mascara": None,
        "habilitado": False,
        "atualizado_em": None,
        "ultimo_sucesso_em": None,
        "ultimo_erro_sanitizado": None,
        "falhas_login": 0,
        "campos_configurados": [],
        "configuracao_completa": False,
    }


def _decifrar_config(cred: CredencialProvedorORM) -> dict[str, str]:
    if cred.config_cifrada:
        try:
            bruto = json.loads(cripto.decifrar(cred.config_cifrada))
            if isinstance(bruto, dict):
                return {str(k): str(v) for k, v in bruto.items() if v is not None}
        except (ValueError, TypeError, json.JSONDecodeError):
            return {}
    return {
        "usuario": cred.usuario,
        "senha": cripto.decifrar(cred.senha_cifrada),
    }


def registrar_auditoria(
    db: Session, cliente_id: str, ator: str, acao: str, provedor: str | None = None
) -> None:
    db.add(
        AuditoriaORM(
            cliente_id=cliente_id, ator=ator, acao=acao, provedor=provedor
        )
    )


def upsert_credencial(
    db: Session,
    cliente_id: str,
    provedor: str,
    dados: CredencialEntrada,
    ator: str,
) -> CredencialProvedorORM:
    """Cria ou atualiza a credencial do portal e registra o ator na auditoria.

    A senha é cifrada antes de persistir; nada da senha em claro toca o storage nem
    a auditoria. Um upsert de rotação (mesmo cliente+provedor) sobrescreve o segredo.
    """
    provedor = normalizar_provedor(provedor)
    cred = _buscar_credencial(db, cliente_id, provedor)
    config = _decifrar_config(cred) if cred is not None else {}
    config.update({k: str(v).strip() for k, v in dados.campos.items() if v is not None})
    if dados.usuario is not None:
        config["usuario"] = dados.usuario.strip()
    if dados.senha is not None:
        config["senha"] = dados.senha
    if not config:
        raise ValueError("informe os campos da credencial")
    usuario_storage = config.get("usuario") or provedor
    senha_storage = config.get("senha", "")
    config_cifrada = cripto.cifrar(json.dumps(config, ensure_ascii=False))
    if cred is None:
        cred = CredencialProvedorORM(
            id=str(uuid.uuid4()), cliente_id=cliente_id, provedor=provedor,
            usuario=usuario_storage, senha_cifrada=cripto.cifrar(senha_storage),
            config_cifrada=config_cifrada,
            habilitado=dados.habilitado,
        )
        db.add(cred)
    else:
        cred.provedor = provedor
        cred.usuario = usuario_storage
        cred.senha_cifrada = cripto.cifrar(senha_storage)
        cred.config_cifrada = config_cifrada
        cred.habilitado = dados.habilitado
        cred.atualizado_em = _agora()
    registrar_auditoria(
        db, cliente_id, ator, "credencial_provedor_upsert", provedor
    )
    db.commit()
    db.refresh(cred)
    return cred


def listar_credenciais(db: Session, cliente_id: str, provedores: list[str]) -> list[dict]:
    """Lista, mascarada, a credencial de cada provedor conhecido para o cliente."""
    existentes = {
        normalizar_provedor(cred.provedor): cred
        for cred in db.query(CredencialProvedorORM).filter_by(cliente_id=cliente_id).all()
    }
    saida: list[dict] = []
    for provedor in provedores:
        canonico = normalizar_provedor(provedor)
        cred = existentes.get(canonico)
        saida.append(_mascarar(cred) if cred is not None else _vazia(canonico))
    return saida


def obter_credencial_mascarada(
    db: Session, cliente_id: str, provedor: str
) -> dict | None:
    cred = _buscar_credencial(db, cliente_id, provedor)
    return _mascarar(cred) if cred is not None else None


def _aliases_provedor(provedor: str) -> list[str]:
    """Nomes equivalentes (lista do mock usa 'Santander'; driver usa 'santander')."""
    p = (provedor or "").strip()
    if not p:
        return []
    alts = {p, p.lower(), p.capitalize(), p.title()}
    return list(alts)


def _buscar_credencial(
    db: Session, cliente_id: str, provedor: str, *, habilitado: bool | None = None
) -> CredencialProvedorORM | None:
    query = db.query(CredencialProvedorORM).filter(
        CredencialProvedorORM.cliente_id == cliente_id,
        CredencialProvedorORM.provedor.in_(_aliases_provedor(provedor)),
    )
    if habilitado is not None:
        query = query.filter(CredencialProvedorORM.habilitado == habilitado)
    return query.first()


def obter_configuracao_para_uso(
    db: Session, cliente_id: str, provedor: str
) -> dict[str, str] | None:
    """Retorna a configuração decifrada somente ao worker do driver."""
    cred = _buscar_credencial(db, cliente_id, provedor, habilitado=True)
    return _decifrar_config(cred) if cred is not None else None


def configuracao_completa(
    db: Session, cliente_id: str, provedor: str
) -> bool:
    config = obter_configuracao_para_uso(db, cliente_id, provedor)
    if config is None:
        return False
    obrigatorios = campos_credencial_obrigatorios(provedor)
    return bool(obrigatorios) and all(str(config.get(k, "")).strip() for k in obrigatorios)


def obter_segredo_para_uso(
    db: Session, cliente_id: str, provedor: str
) -> tuple[str, str] | None:
    """Lê e decifra a credencial on-demand para o driver usar (login real).

    Retorna ``(usuario, senha)`` ou ``None`` se não houver credencial habilitada.
    É lida do storage a cada chamada (sem cache em memória), então uma rotação via
    PUT vale no próximo uso sem reiniciar o processo. NÃO expor o retorno em logs.
    """
    config = obter_configuracao_para_uso(db, cliente_id, provedor)
    if config is not None and config.get("usuario") is not None and config.get("senha") is not None:
        return config["usuario"], config["senha"]
    return None


def registrar_sucesso_login(db: Session, cliente_id: str, provedor: str) -> None:
    """Marca autenticação bem-sucedida: zera falhas e atualiza saúde da credencial."""
    cred = _buscar_credencial(db, cliente_id, provedor)
    if cred is None:
        return
    cred.falhas_login = 0
    cred.ultimo_sucesso_em = _agora()
    cred.ultimo_erro_sanitizado = None
    db.commit()


def registrar_falha_login(
    db: Session, cliente_id: str, provedor: str, codigo_erro: str
) -> None:
    """Contabiliza falha de autenticação (código sanitizado, jamais o segredo).

    Alimenta a métrica ``motor_provider_auth_failures``. Este é o ponto que o driver
    real (Task 12) chamará ao falhar o login no portal.
    """
    cred = _buscar_credencial(db, cliente_id, provedor)
    if cred is None:
        return
    cred.falhas_login = (cred.falhas_login or 0) + 1
    cred.ultimo_erro_sanitizado = codigo_erro
    db.commit()


def testar_login(db: Session, cliente_id: str, provedor: str) -> dict | None:
    """PLACEHOLDER de "testar login" (Task 11).

    Ainda NÃO há driver real (Task 12), então esta rota apenas confirma que existe
    uma credencial habilitada e devolve ``status="placeholder"``. Ela deliberadamente
    NÃO finge autenticar num banco real nem fabrica sucesso/falha — quando o driver
    híbrido (API/Playwright) existir, ele chamará ``registrar_sucesso_login`` /
    ``registrar_falha_login`` com o desfecho verdadeiro.

    Retorna ``None`` se não houver credencial habilitada (a rota responde 404).
    """
    if obter_segredo_para_uso(db, cliente_id, provedor) is None:
        return None
    return {
        "provedor": provedor,
        "status": "placeholder",
        "detalhe": "Teste real de login disponível a partir do driver da Task 12.",
    }
