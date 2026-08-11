"""Janela do período e a janela anterior comparável.

O Portal só sabia calcular UMA janela (``financeiro_calc.periodo_padrao``).
Comparação com período anterior — "meu ticket esse mês vs. o passado" — não
existia em ``app/``; nasce aqui.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from app.financeiro_calc import periodo_padrao, ultimo_dia_mes

MESES_PT = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)


@dataclass(frozen=True)
class Janela:
    inicio: date
    fim: date

    @property
    def dias(self) -> int:
        """Dias inclusivos: 01 a 31 são 31, não 30."""
        return (self.fim - self.inicio).days + 1

    @property
    def mes_cheio(self) -> bool:
        return (
            self.inicio.day == 1
            and self.fim == ultimo_dia_mes(self.inicio)
            and self.inicio.month == self.fim.month
            and self.inicio.year == self.fim.year
        )

    @property
    def rotulo(self) -> str:
        if self.mes_cheio:
            return f"{MESES_PT[self.inicio.month - 1]}/{self.inicio.year}"
        return (
            f"{self.inicio.strftime('%d/%m/%Y')} a {self.fim.strftime('%d/%m/%Y')}"
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "inicio": self.inicio.isoformat(),
            "fim": self.fim.isoformat(),
            "rotulo": self.rotulo,
        }


def janela_do_periodo(
    inicio: str | date | None = None,
    fim: str | date | None = None,
) -> Janela:
    """Normaliza o período com a MESMA regra do painel (mês corrente default)."""
    ini_s = inicio.isoformat() if isinstance(inicio, date) else inicio
    fim_s = fim.isoformat() if isinstance(fim, date) else fim
    d_inicio, d_fim = periodo_padrao(ini_s, fim_s)
    return Janela(inicio=d_inicio, fim=d_fim)


def janela_anterior(janela: Janela) -> Janela:
    """Período comparável imediatamente anterior.

    Mês cheio → mês cheio anterior (fevereiro tem 28 dias e a comparação
    continua honesta). Janela parcial → mesmo número de dias, colado antes.
    """
    if janela.mes_cheio:
        ultimo_dia_anterior = janela.inicio - timedelta(days=1)
        primeiro = ultimo_dia_anterior.replace(day=1)
        ultimo = date(
            ultimo_dia_anterior.year,
            ultimo_dia_anterior.month,
            calendar.monthrange(ultimo_dia_anterior.year, ultimo_dia_anterior.month)[1],
        )
        return Janela(inicio=primeiro, fim=ultimo)

    fim_anterior = janela.inicio - timedelta(days=1)
    inicio_anterior = fim_anterior - timedelta(days=janela.dias - 1)
    return Janela(inicio=inicio_anterior, fim=fim_anterior)
