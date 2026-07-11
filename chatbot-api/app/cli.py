"""CLI de operação do Chatbot (onboarding standalone).

Ex.: python -m app.cli criar-loja --nome "Moto Center" --slug moto-center \
        --instance loja1 --whatsapp 5511999999999

O --slug deve ser o MESMO usado no Estoque, para o bot consultar a vitrine certa.
"""
import argparse

from app import servico
from app.db import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(prog="chatbot")
    sub = parser.add_subparsers(dest="comando", required=True)

    c = sub.add_parser("criar-loja", help="cria loja + credencial de serviço")
    c.add_argument("--nome", required=True)
    c.add_argument("--slug", required=True)
    c.add_argument("--instance", required=True, help="nome da instância Evolution")
    c.add_argument("--whatsapp")

    args = parser.parse_args()

    if args.comando == "criar-loja":
        db = SessionLocal()
        try:
            loja, token = servico.criar_loja(
                db, args.nome, args.slug, args.instance, args.whatsapp
            )
        finally:
            db.close()
        print(f"Loja criada: {loja.nome}  (slug={loja.slug}  instance={loja.evolution_instance})")
        print(f"TOKEN (guarde agora, não será mostrado de novo): {token}")


if __name__ == "__main__":
    main()
