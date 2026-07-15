"""Smoke LIVE do driver Fontecred: login -> simular -> parse, headed.

Roda o fluxo real do portal com a mesma stack anti-WAF do worker, para iterar
o driver ao vivo sem precisar do Portal/DB. Credenciais e dados de teste vêm de
variáveis de ambiente (a senha NUNCA vai no código nem em argumento).

Uso (PowerShell):
  cd motor-simulacao
  $env:MOTOR_FONTECRED_EMAIL   = "lojista@exemplo.com"
  $env:MOTOR_FONTECRED_SENHA   = "sua-senha"
  $env:FONTECRED_CPF           = "000.000.000-00"
  $env:FONTECRED_NASC          = "2002-12-13"      # ISO ou DD/MM/AAAA
  $env:FONTECRED_CELULAR       = "(51) 90000-0000"
  $env:FONTECRED_PLACA         = "ABC1D23"
  $env:FONTECRED_VALOR         = "21900"
  $env:FONTECRED_PRAZOS        = "24,36,48"          # opcional
  ./.venv/Scripts/python.exe scripts/probe_fontecred.py

Deixe o navegador abrir; se aparecer reCAPTCHA, resolva na janela.
"""
import os
import sys
from pathlib import Path

# Permite rodar direto (python scripts/probe_fontecred.py) achando o pacote app.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.drivers import (
    ErroTransitorio,
    IntervencaoNecessaria,
    RejeicaoNegocio,
)
from app.motor.fontecred import PROVEDOR, fabrica_fontecred


def _mask(s: str) -> str:
    s = s or ""
    return (s[:3] + "***") if s else "(vazio)"


def main() -> None:
    email = os.getenv("MOTOR_FONTECRED_EMAIL", "").strip()
    senha = os.getenv("MOTOR_FONTECRED_SENHA", "").strip()
    if not email or not senha:
        print("Defina MOTOR_FONTECRED_EMAIL e MOTOR_FONTECRED_SENHA.")
        return

    prazos = [
        int(x) for x in os.getenv("FONTECRED_PRAZOS", "24,36,48").split(",") if x.strip()
    ]
    sol = SolicitacaoSimulacao(
        pessoa=Pessoa(
            cpf=os.getenv("FONTECRED_CPF", ""),
            nascimento=os.getenv("FONTECRED_NASC", ""),
            celular=os.getenv("FONTECRED_CELULAR", ""),
        ),
        veiculo=Veiculo(
            placa=os.getenv("FONTECRED_PLACA", ""),
            valor=float(os.getenv("FONTECRED_VALOR", "0") or 0),
            categoria="moto",
        ),
        condicoes=Condicoes(entrada=0, prazos_meses=prazos),
        provedores=[PROVEDOR],
    )

    d = fabrica_fontecred()
    # Injeta credencial do env (sem DB); a senha não é logada.
    d._credencial = lambda ctx: (email, senha)  # type: ignore[assignment]
    print(f"login_url  {d.login_url}")
    print(f"headless   {d.headless}   email {_mask(email)}")
    print(f"placa {sol.veiculo.placa}  valor {sol.veiculo.valor}  prazos {prazos}")
    print("-" * 60)

    try:
        resultados = d.simular(sol)
    except (RejeicaoNegocio, IntervencaoNecessaria, ErroTransitorio) as exc:
        print(f"FALHA [{exc.codigo}] {exc}")
        print("RESULT FAIL (veja screenshot em", d.screenshot_dir, ")")
        return
    except Exception as exc:  # noqa: BLE001
        print(f"ERRO {type(exc).__name__}: {str(exc)[:240]}")
        print("RESULT FAIL")
        return

    entrada = next((r.entrada for r in resultados if r.entrada is not None), None)
    print(f"Entrada mínima: R$ {entrada}")
    print("Simulações:")
    for r in sorted(resultados, key=lambda x: x.prazo_meses or 0):
        print(
            f"  {r.prazo_meses:>3}x  parcela R$ {r.valor_parcela}"
            f"   financiado R$ {r.valor_financiado}"
        )
    print("RESULT OK")


if __name__ == "__main__":
    main()
