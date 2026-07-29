from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa


_EMAIL_VALIDO = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_PAPEIS_CONTROL = frozenset({"admin", "gestor"})


def validar_colisoes_email_gestores_revy(connection: sa.Connection) -> None:
    """Falha antes do DDL se duas identidades legadas convergem no mesmo e-mail."""

    gestores = connection.execute(
        sa.text("SELECT id, email FROM gestores_revy ORDER BY id")
    ).mappings()
    gestores_por_email: dict[str, str] = {}
    for gestor in gestores:
        email = _normalizar_email(gestor["email"], gestor["id"])
        gestor_anterior = gestores_por_email.get(email)
        if gestor_anterior is not None and gestor_anterior != gestor["id"]:
            raise RuntimeError(
                "GestoresRevy legados possuem o mesmo e-mail normalizado: "
                f"{gestor_anterior} e {gestor['id']}"
            )
        gestores_por_email[email] = gestor["id"]


def backfill_acessos_control(connection: sa.Connection) -> None:
    """Reconcilia Gestores Revy legados com Pessoas e Acessos Control."""

    gestores = connection.execute(
        sa.text(
            """
            SELECT id, email, nome, senha_hash, papel, ativo
            FROM gestores_revy
            ORDER BY id
            """
        )
    ).mappings()
    for gestor in gestores:
        email = _normalizar_email(gestor["email"], gestor["id"])
        papel = gestor["papel"]
        if papel not in _PAPEIS_CONTROL:
            raise RuntimeError(
                f"GestorRevy {gestor['id']} possui papel global inválido"
            )
        pessoa = _uma_linha_ou_nenhuma(
            connection.execute(
                sa.text(
                    """
                    SELECT id, email, nome
                    FROM pessoas
                    WHERE email = :email
                    """
                ),
                {"email": email},
            ).mappings().all(),
            f"mais de uma Pessoa Revy encontrada para GestorRevy {gestor['id']}",
        )
        if pessoa is None:
            pessoa_id = str(uuid.uuid4())
            nome = _normalizar_nome(gestor["nome"], gestor["id"])
            agora = datetime.now(timezone.utc)
            connection.execute(
                sa.text(
                    """
                    INSERT INTO pessoas (
                        id, email, nome, criada_em, atualizada_em
                    ) VALUES (
                        :id, :email, :nome, :agora, :agora
                    )
                    """
                ),
                {
                    "id": pessoa_id,
                    "email": email,
                    "nome": nome,
                    "agora": agora,
                },
            )
        else:
            pessoa_id = pessoa["id"]

        acesso_por_legado = _buscar_acesso(
            connection,
            "gestor_legado_id",
            gestor["id"],
        )
        acesso_por_pessoa = _buscar_acesso(
            connection,
            "pessoa_id",
            pessoa_id,
        )
        if (
            acesso_por_legado is not None
            and acesso_por_pessoa is not None
            and acesso_por_legado["id"] != acesso_por_pessoa["id"]
        ):
            raise RuntimeError(
                f"GestorRevy {gestor['id']} conflita com outro AcessoControl"
            )
        acesso = acesso_por_legado or acesso_por_pessoa
        if acesso is not None:
            _validar_reconciliacao(
                acesso,
                pessoa_id=pessoa_id,
                gestor_legado_id=gestor["id"],
            )

        estado = "ativo" if bool(gestor["ativo"]) else "desativado"
        desejado = {
            "pessoa_id": pessoa_id,
            "papel": papel,
            "estado": estado,
            "senha_hash": gestor["senha_hash"],
            "gestor_legado_id": gestor["id"],
        }
        if acesso is None:
            agora = datetime.now(timezone.utc)
            connection.execute(
                sa.text(
                    """
                    INSERT INTO acessos_control (
                        id, pessoa_id, papel, estado, senha_hash,
                        sessao_versao, gestor_legado_id, criada_em,
                        atualizada_em
                    ) VALUES (
                        :id, :pessoa_id, :papel, :estado, :senha_hash,
                        1, :gestor_legado_id, :agora, :agora
                    )
                    """
                ),
                {
                    "id": gestor["id"],
                    **desejado,
                    "agora": agora,
                },
            )
        elif any(acesso[campo] != valor for campo, valor in desejado.items()):
            connection.execute(
                sa.text(
                    """
                    UPDATE acessos_control
                    SET
                        pessoa_id = :pessoa_id,
                        papel = :papel,
                        estado = :estado,
                        senha_hash = :senha_hash,
                        gestor_legado_id = :gestor_legado_id,
                        atualizada_em = :agora
                    WHERE id = :id
                    """
                ),
                {
                    "id": acesso["id"],
                    **desejado,
                    "agora": datetime.now(timezone.utc),
                },
            )


def _normalizar_email(email_bruto: Any, gestor_id: str) -> str:
    email = str(email_bruto or "").strip().lower()
    if len(email) > 320 or not _EMAIL_VALIDO.fullmatch(email):
        raise RuntimeError(f"GestorRevy {gestor_id} possui e-mail inválido")
    return email


def _normalizar_nome(nome_bruto: Any, gestor_id: str) -> str:
    nome = str(nome_bruto or "").strip()
    if not nome or len(nome) > 160:
        raise RuntimeError(f"GestorRevy {gestor_id} possui nome inválido")
    return nome


def _uma_linha_ou_nenhuma(
    linhas: list[sa.RowMapping],
    mensagem_conflito: str,
) -> sa.RowMapping | None:
    if len(linhas) > 1:
        raise RuntimeError(mensagem_conflito)
    return linhas[0] if linhas else None


def _buscar_acesso(
    connection: sa.Connection,
    campo: str,
    valor: str,
) -> sa.RowMapping | None:
    if campo not in {"pessoa_id", "gestor_legado_id"}:
        raise ValueError("campo de reconciliação inválido")
    return _uma_linha_ou_nenhuma(
        connection.execute(
            sa.text(
                f"""
                SELECT
                    id, pessoa_id, papel, estado, senha_hash,
                    gestor_legado_id
                FROM acessos_control
                WHERE {campo} = :valor
                """
            ),
            {"valor": valor},
        ).mappings().all(),
        f"mais de um AcessoControl encontrado por {campo}",
    )


def _validar_reconciliacao(
    acesso: sa.RowMapping,
    *,
    pessoa_id: str,
    gestor_legado_id: str,
) -> None:
    if acesso["pessoa_id"] != pessoa_id:
        raise RuntimeError(
            f"GestorRevy {gestor_legado_id} aponta para outra Pessoa Revy"
        )
    legado_atual = acesso["gestor_legado_id"]
    if legado_atual not in {None, gestor_legado_id}:
        raise RuntimeError(
            f"Pessoa Revy {pessoa_id} já possui outro GestorRevy legado"
        )
