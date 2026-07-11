"""CLI de operação do Estoque (onboarding standalone).

Ex.: python -m app.cli criar-loja --nome "Moto Center" --slug moto-center --whatsapp 5511999999999
"""
import argparse

from app import servico
from app.db import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(prog="estoque")
    sub = parser.add_subparsers(dest="comando", required=True)

    c = sub.add_parser("criar-loja", help="cria loja + credencial de serviço")
    c.add_argument("--nome", required=True)
    c.add_argument("--slug", required=True)
    c.add_argument("--whatsapp")
    c.add_argument("--papel", default="dono")

    args = parser.parse_args()

    if args.comando == "criar-loja":
        db = SessionLocal()
        try:
            loja, token = servico.criar_loja(
                db, args.nome, args.slug, args.whatsapp, args.papel
            )
        finally:
            db.close()
        print(f"Loja criada: {loja.nome}  (slug={loja.slug}  id={loja.id})")
        print(f"TOKEN (guarde agora, não será mostrado de novo): {token}")


if __name__ == "__main__":
    main()
