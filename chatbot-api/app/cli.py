"""CLI de operação do Chatbot (onboarding standalone).

Ex.: python -m app.cli criar-loja --nome "Moto Center" --slug moto-center \
        --instance loja1 --whatsapp 5511999999999

O --slug deve ser o MESMO usado no Estoque, para o bot consultar a vitrine certa.

Números autorizados (E5 — cadastro de veículo via WhatsApp):
  python -m app.cli autorizar-numero --slug moto-center --telefone 5511999999999 --papel dono
"""
import argparse

from app import models_db, operacao, servico
from app.db import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(prog="chatbot")
    sub = parser.add_subparsers(dest="comando", required=True)

    c = sub.add_parser("criar-loja", help="cria loja + credencial de serviço")
    c.add_argument("--nome", required=True)
    c.add_argument("--slug", required=True)
    c.add_argument("--instance", required=True, help="nome da instância Evolution")
    c.add_argument("--whatsapp")

    a = sub.add_parser(
        "autorizar-numero",
        help="autoriza telefone a cadastrar veículo via WhatsApp (E5)",
    )
    a.add_argument("--slug", required=True, help="slug da loja no Chatbot")
    a.add_argument("--telefone", required=True, help="DDI+DDD+número (só dígitos ou com formatação)")
    a.add_argument("--papel", default="vendedor", choices=["dono", "vendedor"])
    a.add_argument(
        "--inativo",
        action="store_true",
        help="cadastra/atualiza como inativo",
    )

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

    elif args.comando == "autorizar-numero":
        db = SessionLocal()
        try:
            loja = db.query(models_db.Loja).filter(models_db.Loja.slug == args.slug).first()
            if loja is None:
                raise SystemExit(f"loja não encontrada: {args.slug}")
            row = operacao.adicionar_numero(
                db,
                loja.id,
                args.telefone,
                papel=args.papel,
                ativo=not args.inativo,
            )
        finally:
            db.close()
        print(
            f"Número autorizado: {row['telefone']}  papel={row['papel']}  "
            f"ativo={row['ativo']}  (loja={args.slug})"
        )


if __name__ == "__main__":
    main()
