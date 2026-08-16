"""Conversão de valor lido do SQLite para o tipo declarado no Postgres.

A conversão é dirigida pelo **tipo de destino**, refletido do banco que o
alembic acabou de criar. Não há import de `app.models` em lugar nenhum desta
pasta: Portal e Control têm ambos um pacote chamado `app` e nenhum processo
pode importar os dois.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import types as sqltypes


class ValorInconvertivel(Exception):
    """Valor que o Postgres não aceitaria e que não pode ser coagido em silêncio."""


def converter(valor, tipo):
    if valor is None:
        return None

    if isinstance(tipo, sqltypes.DateTime):
        if isinstance(valor, str):
            valor = datetime.fromisoformat(valor)
        if valor.tzinfo is None:
            # O SQLite guarda DateTime(timezone=True) sem offset e devolve
            # naive. Todo escritor do Portal e do Control usa
            # agora() = datetime.now(timezone.utc), então o que está guardado
            # É UTC: anexar tzinfo restaura a informação, não a inventa.
            valor = valor.replace(tzinfo=timezone.utc)
        return valor

    if isinstance(tipo, sqltypes.Boolean):
        if valor in (0, 1, False, True):
            return bool(valor)
        raise ValorInconvertivel(f"booleano fora de 0/1: {valor!r}")

    if isinstance(tipo, sqltypes.Numeric) and not isinstance(tipo, sqltypes.Float):
        if isinstance(valor, Decimal):
            return valor
        # str() e nunca float(): Decimal(0.1) é
        # 0.1000000000000000055511151231257827…, Decimal(str(0.1)) é 0.1.
        return Decimal(str(valor))

    return valor
