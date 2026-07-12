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

    cred = sub.add_parser("criar-credencial", help="cria credencial adicional para uma loja")
    cred.add_argument("--slug", required=True)
    cred.add_argument("--papel", default="operador")

    usuario = sub.add_parser("criar-usuario", help="cria usuário da administração web")
    usuario.add_argument("--slug", required=True)
    usuario.add_argument("--email", required=True)
    usuario.add_argument("--nome", required=True)
    usuario.add_argument("--senha", required=True)
    usuario.add_argument("--papel", default="dono")

    sub.add_parser("gerar-chave-outbox", help="gera uma chave Fernet para ESTOQUE_OUTBOX_KEY")

    webhook = sub.add_parser("configurar-webhook", help="define destino de entrega da outbox")
    webhook.add_argument("--slug", required=True)
    webhook.add_argument("--url", required=True)
    webhook.add_argument("--segredo", required=True, help="segredo HMAC (>= 16 chars)")

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
    elif args.comando == "criar-credencial":
        db = SessionLocal()
        try:
            loja, token = servico.criar_credencial(db, args.slug, args.papel)
        finally:
            db.close()
        print(f"Credencial criada para: {loja.nome} (slug={loja.slug}, papel={args.papel})")
        print(f"TOKEN (guarde agora, não será mostrado de novo): {token}")
    elif args.comando == "criar-usuario":
        db = SessionLocal()
        try:
            usuario_criado = servico.criar_usuario_estoque(
                db, args.slug, args.email, args.nome, args.senha, args.papel
            )
            identificacao = (usuario_criado.email, usuario_criado.papel)
        finally:
            db.close()
        print(f"Usuário criado: {identificacao[0]} (papel={identificacao[1]})")
    elif args.comando == "gerar-chave-outbox":
        from app.cripto import gerar_chave

        print(gerar_chave())
        print("Guarde em ESTOQUE_OUTBOX_KEY (não versione).")
    elif args.comando == "configurar-webhook":
        db = SessionLocal()
        try:
            destino = servico.configurar_webhook_destino(
                db, args.slug, args.url, args.segredo
            )
            url_destino = destino.url
        finally:
            db.close()
        print(f"Webhook configurado para slug={args.slug} -> {url_destino}")
        print("Segredo guardado cifrado (Fernet).")


if __name__ == "__main__":
    main()
