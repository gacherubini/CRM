import argparse

from app.auth import hash_senha
from app.cripto import gerar_chave
from app.db import SessionLocal
from app.models import Usuario


def criar_dono(email: str, nome: str, senha: str, loja_slug: str) -> None:
    db = SessionLocal()
    try:
        email = email.strip().lower()
        if db.query(Usuario).filter(Usuario.email == email).first():
            raise SystemExit("email já cadastrado")
        db.add(
            Usuario(
                email=email,
                nome=nome,
                senha_hash=hash_senha(senha),
                papel="dono",
                loja_slug=loja_slug,
            )
        )
        db.commit()
        print("Usuário dono criado.")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("criar-dono")
    p.add_argument("--email", required=True)
    p.add_argument("--nome", required=True)
    p.add_argument("--senha", required=True)
    p.add_argument("--loja-slug", required=True)
    sub.add_parser(
        "gerar-chave-cifragem",
        help="Gera PORTAL_ENCRYPTION_KEY (Fernet) para cifrar token CAPI em repouso",
    )
    args = parser.parse_args()
    if args.comando == "criar-dono":
        criar_dono(args.email, args.nome, args.senha, args.loja_slug)
    elif args.comando == "gerar-chave-cifragem":
        print(gerar_chave())


if __name__ == "__main__":
    main()
