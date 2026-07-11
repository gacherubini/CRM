"""Validação e normalização de entrada (reaproveitado do Plano #1 legado).

Sem dependência de LLM, n8n ou banco (Plano #1A, critério da Task 2).
"""
import re
from datetime import date, datetime


def valida_cpf(cpf: str) -> bool:
    numeros = re.sub(r"\D", "", cpf or "")
    if len(numeros) != 11:
        return False
    if numeros == numeros[0] * 11:
        return False
    for i in range(9, 11):
        soma = sum(int(numeros[num]) * ((i + 1) - num) for num in range(i))
        digito = (soma * 10 % 11) % 10
        if digito != int(numeros[i]):
            return False
    return True


def parse_nascimento(texto: str):
    if not texto:
        return None
    texto = str(texto).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return None


def idade(nascimento: date, hoje: date = None) -> int:
    hoje = hoje or date.today()
    antes_do_aniversario = (hoje.month, hoje.day) < (nascimento.month, nascimento.day)
    return hoje.year - nascimento.year - (1 if antes_do_aniversario else 0)


def parse_valor(texto: str):
    if texto is None:
        return None
    s = str(texto).lower().strip().replace("r$", "").strip()
    multiplicador = 1000 if "mil" in s else 1
    s = s.replace("mil", "").strip()
    s = s.replace(".", "").replace(",", ".")
    s = re.sub(r"[^0-9.]", "", s)
    if s == "" or s == ".":
        return None
    try:
        return float(s) * multiplicador
    except ValueError:
        return None
