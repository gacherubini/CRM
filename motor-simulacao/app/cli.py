"""CLI administrativa para clientes e credenciais do Motor.

O token é sempre gerado localmente, exibido uma única vez e nunca persistido em claro.
"""
import argparse
import secrets
import uuid

from app.auth import hash_token
from app.db import SessionLocal
from app.models_db import ClienteApiORM, CredencialApiORM


def criar_cliente(nome: str) -> str:
    with SessionLocal() as db:
        cliente = ClienteApiORM(id=str(uuid.uuid4()), nome=nome.strip())
        db.add(cliente)
        db.commit()
        return cliente.id


def criar_credencial(cliente_id: str, nome: str) -> str:
    token = secrets.token_urlsafe(32)
    with SessionLocal() as db:
        if db.get(ClienteApiORM, cliente_id) is None:
            raise SystemExit("Cliente não encontrado")
        db.add(
            CredencialApiORM(
                id=str(uuid.uuid4()),
                cliente_id=cliente_id,
                nome=nome.strip(),
                token_hash=hash_token(token),
            )
        )
        db.commit()
    return token


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    comandos = parser.add_subparsers(dest="comando", required=True)
    p_cliente = comandos.add_parser("criar-cliente")
    p_cliente.add_argument("--nome", required=True)
    p_cred = comandos.add_parser("criar-credencial")
    p_cred.add_argument("--cliente-id", required=True)
    p_cred.add_argument("--nome", required=True)
    args = parser.parse_args()

    if args.comando == "criar-cliente":
        print(f"cliente_id={criar_cliente(args.nome)}")
    else:
        print("Guarde o token agora; ele não poderá ser consultado novamente.")
        print(f"token={criar_credencial(args.cliente_id, args.nome)}")


if __name__ == "__main__":
    main()
