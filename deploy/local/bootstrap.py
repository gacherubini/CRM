"""Bootstrap idempotente da stack local.

Este arquivo roda dentro de cada contêiner Python. Cada processo importa somente o
próprio pacote ``app`` e cadastra a mesma loja/token local, sem conhecer o banco
interno dos outros produtos.
"""

from __future__ import annotations

import hashlib
import os
import sys
import uuid

# O script é montado em /opt, enquanto cada imagem mantém seu pacote em /srv.
# Preservar o diretório de trabalho no import permite reutilizar o mesmo bootstrap.
sys.path.insert(0, os.getcwd())


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"variável obrigatória ausente: {name}")
    return value


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def bootstrap_estoque() -> None:
    from app import models_db, servico
    from app.db import SessionLocal

    slug = required("LOCAL_STORE_SLUG")
    token = required("ESTOQUE_API_TOKEN")
    email = required("LOCAL_ADMIN_EMAIL").lower()

    with SessionLocal() as db:
        loja = db.query(models_db.Loja).filter(models_db.Loja.slug == slug).first()
        if loja is None:
            loja, _token_descartado = servico.criar_loja(
                db,
                required("LOCAL_STORE_NAME"),
                slug,
                os.getenv("LOCAL_STORE_WHATSAPP") or None,
            )

        digest = token_hash(token)
        if db.get(models_db.CredencialServico, digest) is None:
            db.add(
                models_db.CredencialServico(
                    token_hash=digest,
                    loja_id=loja.id,
                    papel="dono",
                )
            )
            db.commit()

        usuario = (
            db.query(models_db.UsuarioEstoque)
            .filter(
                models_db.UsuarioEstoque.loja_id == loja.id,
                models_db.UsuarioEstoque.email == email,
            )
            .first()
        )
        if usuario is None:
            servico.criar_usuario_estoque(
                db,
                slug,
                email,
                required("LOCAL_ADMIN_NAME"),
                required("LOCAL_ADMIN_PASSWORD"),
                "dono",
            )

    print(f"estoque preparado: loja={slug} usuário={email}")


def bootstrap_chatbot() -> None:
    from app import models_db, servico
    from app.db import SessionLocal

    slug = required("LOCAL_STORE_SLUG")
    token = required("CHATBOT_API_TOKEN")
    instance = required("LOCAL_EVOLUTION_INSTANCE")

    with SessionLocal() as db:
        loja = db.query(models_db.Loja).filter(models_db.Loja.slug == slug).first()
        if loja is None:
            loja, _token_descartado = servico.criar_loja(
                db,
                required("LOCAL_STORE_NAME"),
                slug,
                instance,
                os.getenv("LOCAL_STORE_WHATSAPP") or None,
            )

        digest = token_hash(token)
        if db.get(models_db.CredencialServico, digest) is None:
            db.add(
                models_db.CredencialServico(
                    token_hash=digest,
                    loja_id=loja.id,
                    papel="dono",
                )
            )
            db.commit()

    print(f"chatbot preparado: loja={slug} instância={instance}")


def bootstrap_motor() -> None:
    from app.db import SessionLocal
    from app.models_db import ClienteApiORM, CredencialApiORM

    nome = required("LOCAL_STORE_NAME")
    token = required("MOTOR_TOKEN")
    digest = token_hash(token)

    with SessionLocal() as db:
        cliente = db.query(ClienteApiORM).filter(ClienteApiORM.nome == nome).first()
        if cliente is None:
            cliente = ClienteApiORM(id=str(uuid.uuid4()), nome=nome)
            db.add(cliente)
            db.flush()

        credencial = (
            db.query(CredencialApiORM)
            .filter(CredencialApiORM.token_hash == digest)
            .first()
        )
        if credencial is None:
            db.add(
                CredencialApiORM(
                    id=str(uuid.uuid4()),
                    cliente_id=cliente.id,
                    nome="integração local",
                    token_hash=digest,
                )
            )
        db.commit()

    print(f"motor preparado: cliente={nome}")


def bootstrap_portal() -> None:
    from app.auth import hash_senha
    from app.db import SessionLocal
    from app.models import Usuario

    email = required("LOCAL_ADMIN_EMAIL").lower()

    with SessionLocal() as db:
        usuario = db.query(Usuario).filter(Usuario.email == email).first()
        if usuario is None:
            db.add(
                Usuario(
                    email=email,
                    nome=required("LOCAL_ADMIN_NAME"),
                    senha_hash=hash_senha(required("LOCAL_ADMIN_PASSWORD")),
                    papel="dono",
                    loja_slug=required("LOCAL_STORE_SLUG"),
                )
            )
            db.commit()

    print(f"portal preparado: usuário={email}")


BOOTSTRAPS = {
    "estoque": bootstrap_estoque,
    "chatbot": bootstrap_chatbot,
    "motor": bootstrap_motor,
    "portal": bootstrap_portal,
}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in BOOTSTRAPS:
        opções = ", ".join(BOOTSTRAPS)
        raise SystemExit(f"uso: bootstrap.py <{opções}>")
    BOOTSTRAPS[sys.argv[1]]()


if __name__ == "__main__":
    main()
