"""Leitura crua da origem + conversão para o tipo declarado no Postgres.

A conversão é dirigida pelo **tipo de destino**, refletido do banco que o
alembic acabou de criar. Não há import de `app.models` em lugar nenhum desta
pasta: Portal e Control têm ambos um pacote chamado `app` e nenhum processo
pode importar os dois.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import types as sqltypes


def _quotar(identificador: str) -> str:
    """Aspas duplas em torno do identificador, com `"` embutido dobrado.

    Os nomes vêm do schema refletido, não de entrada de usuário — isso não é
    defesa contra injeção. É só para não gerar SQL inválido se algum dia um
    nome de tabela/coluna legítimo tiver `"` dentro.
    """
    return '"' + identificador.replace('"', '""') + '"'


def ler_cru(conn, tabela: str, colunas: list[str], schema: str | None = None):
    """Lê SEM passar pela camada tipada do SQLAlchemy.

    Existe porque o trabalho desta ferramenta é enxergar o que está **sujo** no
    arquivo, e o result-processor do tipo mente sobre isso. Medido no venv do
    Portal, com `10.00567` gravado numa coluna `NUMERIC(12,2)` e `2` numa
    coluna `Boolean` do SQLite::

        valor TIPADO      : 10.01      <- o que um select() devolve
        valor CRU (driver): 10.00567   <- o que está no arquivo
        SUM  TIPADO       : 10.01
        SUM  CRU (driver) : 10.00567
        booleano TIPADO   : True
        booleano CRU      : 2

    O `Numeric` do SQLite formata com `"%.{scale}f"` na leitura e o `Boolean`
    coage qualquer inteiro truthy. Com leitura tipada a cadeia inteira mente
    junto: `verificar` não vê as casas a mais, `copiar` grava arredondado e
    `validar` compara arredondado com arredondado — e imprime "Sem divergencia.
    Corte liberado." com centavos perdidos. Esse é o pior modo de falha do
    conjunto, e é ele que este helper fecha.

    **Não "simplifique" isto de volta para `select()` tipado.** Se alguém achar
    daqui a seis meses que dá na mesma, é porque o teste de guarda em
    `tests/test_tipos.py` está lá para provar que não dá.

    Os identificadores vêm do schema refletido (não de entrada de usuário), mas
    vão entre aspas duplas mesmo assim — nome de coluna como `order` ou `to`
    quebraria o SQL sem elas.
    """
    lista = ", ".join(_quotar(c) for c in colunas)
    alvo = (
        _quotar(tabela)
        if schema is None
        else f"{_quotar(schema)}.{_quotar(tabela)}"
    )
    return conn.exec_driver_sql(f"SELECT {lista} FROM {alvo}")


class ValorInconvertivel(Exception):
    """Valor que o Postgres não aceitaria e que não pode ser coagido em silêncio."""


def converter(valor, tipo):
    if valor is None:
        return None

    if isinstance(tipo, sqltypes.DateTime):
        if isinstance(valor, str):
            try:
                valor = datetime.fromisoformat(valor)
            except ValueError as exc:
                raise ValorInconvertivel(
                    f"datetime fora do formato ISO: {valor!r}"
                ) from exc
        if valor.tzinfo is None:
            # O SQLite guarda DateTime(timezone=True) sem offset e devolve
            # naive. Todo escritor do Portal e do Control usa
            # agora() = datetime.now(timezone.utc), então o que está guardado
            # É UTC: anexar tzinfo restaura a informação, não a inventa.
            valor = valor.replace(tzinfo=timezone.utc)
        return valor

    if isinstance(tipo, sqltypes.Date):
        # `Date` e `DateTime` são irmãos na hierarquia do SQLAlchemy — nenhum
        # é subclasse do outro (ambos herdam de `_RenderISO8601NoT`) — então
        # este ramo não pode capturar uma coluna DateTime por engano e a
        # posição dele aqui é só estética (perto do outro tipo temporal).
        if isinstance(valor, str):
            try:
                valor = date.fromisoformat(valor)
            except ValueError as exc:
                raise ValorInconvertivel(
                    f"data fora do formato ISO: {valor!r}"
                ) from exc
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
