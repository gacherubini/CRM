"""Smoke LIVE do driver Pan **portal** (veiculos.bancopan.com.br), headed.

Abre o navegador visivel e roda o fluxo do portal do lojista (usuario/senha),
para voce ver como esta o Pan e iterar o driver ao vivo, sem Portal/DB. A senha
NUNCA vai no codigo nem em argumento.

Uso (PowerShell):
  cd motor-simulacao
  $env:MOTOR_PAN_PORTAL_USUARIO = "seu-usuario-ou-cpf"
  $env:MOTOR_PAN_PORTAL_SENHA   = "sua-senha"
  $env:PAN_CPF                  = "000.000.000-00"
  $env:PAN_CELULAR              = "(51) 90000-0000"
  $env:PAN_PLACA                = "ABC1D23"
  $env:PAN_VALOR                = "21900"
  $env:PAN_ENTRADA              = "0"                # opcional (Pan nao exige)
  $env:PAN_PRAZOS               = "24,36,48"          # opcional
  ./.venv/Scripts/python.exe scripts/probe_pan_portal.py

Deixe o navegador abrir; observe cada etapa. Screenshots de falha vao para
data/screenshots. Usuario/senha/CPF nao sao impressos.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.drivers import (
    ErroTransitorio,
    IntervencaoNecessaria,
    RejeicaoNegocio,
)
from app.motor.pan_portal import PROVEDOR, fabrica_pan_portal


def _mask(s: str) -> str:
    s = s or ""
    return (s[:3] + "***") if s else "(vazio)"


def main() -> None:
    usuario = os.getenv("MOTOR_PAN_PORTAL_USUARIO", "").strip()
    senha = os.getenv("MOTOR_PAN_PORTAL_SENHA", "").strip()
    if not usuario or not senha:
        print("Defina MOTOR_PAN_PORTAL_USUARIO e MOTOR_PAN_PORTAL_SENHA.")
        return

    prazos = [
        int(x) for x in os.getenv("PAN_PRAZOS", "24,36,48").split(",") if x.strip()
    ]
    sol = SolicitacaoSimulacao(
        pessoa=Pessoa(
            cpf=os.getenv("PAN_CPF", ""),
            nascimento=os.getenv("PAN_NASC", ""),
            celular=os.getenv("PAN_CELULAR", ""),
        ),
        veiculo=Veiculo(
            placa=os.getenv("PAN_PLACA", ""),
            valor=float(os.getenv("PAN_VALOR", "0") or 0),
            categoria="moto",
        ),
        condicoes=Condicoes(
            entrada=float(os.getenv("PAN_ENTRADA", "0") or 0),
            prazos_meses=prazos,
        ),
        provedores=[PROVEDOR],
    )

    d = fabrica_pan_portal()
    d.headless = False  # forca janela visivel
    d._credencial = lambda ctx: (usuario, senha)  # type: ignore[assignment]
    print(f"login_url  {d.login_url}")
    print(f"headless   {d.headless}   usuario {_mask(usuario)}")
    print(
        f"placa {sol.veiculo.placa or '(sem placa)'}  valor {sol.veiculo.valor}  "
        f"entrada {sol.condicoes.entrada}  prazos {prazos}"
    )
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

    print("Simulacoes:")
    for r in sorted(resultados, key=lambda x: x.prazo_meses or 0):
        print(
            f"  {r.prazo_meses:>3}x  parcela R$ {r.valor_parcela}"
            f"   financiado R$ {r.valor_financiado}   entrada R$ {r.entrada}"
        )
    print("RESULT OK")


if __name__ == "__main__":
    main()
