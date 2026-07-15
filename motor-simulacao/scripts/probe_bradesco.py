"""Smoke LIVE do driver Bradesco (Turbo Lojista): login -> simular -> parse, headed.

Abre o navegador de verdade (janela visivel) e roda o fluxo real do portal para
voce ver como esta o Bradesco e iterar o driver ao vivo, sem precisar do Portal/DB.
Credenciais e dados de teste vem de variaveis de ambiente (a senha NUNCA vai no
codigo nem em argumento).

Uso (PowerShell):
  cd motor-simulacao
  $env:MOTOR_BRADESCO_CPF_LOJISTA = "000.000.000-00"   # CPF do LOJISTA (login)
  $env:MOTOR_BRADESCO_SENHA       = "sua-senha"
  $env:BRADESCO_CPF               = "000.000.000-00"   # CPF do CLIENTE
  $env:BRADESCO_CELULAR           = "(51) 90000-0000"
  $env:BRADESCO_PLACA             = "ABC1D23"          # opcional no portal
  $env:BRADESCO_VALOR             = "21900"
  $env:BRADESCO_UF                = "SP"                # opcional (default SP)
  $env:BRADESCO_ENTRADA           = "0"                # opcional (Bradesco nao exige)
  $env:BRADESCO_PRAZOS            = "18,24,36,48"       # opcional
  ./.venv/Scripts/python.exe scripts/probe_bradesco.py

Deixe o navegador abrir; observe cada etapa. Screenshots de falha vao para
data/screenshots. A senha e o CPF nao sao impressos.
"""
import os
import sys
from pathlib import Path

# Permite rodar direto (python scripts/probe_bradesco.py) achando o pacote app.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.drivers import (
    ErroTransitorio,
    IntervencaoNecessaria,
    RejeicaoNegocio,
)
from app.motor.bradesco import PROVEDOR, fabrica_bradesco


def _mask(s: str) -> str:
    s = s or ""
    return (s[:3] + "***") if s else "(vazio)"


def main() -> None:
    cpf_lojista = os.getenv("MOTOR_BRADESCO_CPF_LOJISTA", "").strip()
    senha = os.getenv("MOTOR_BRADESCO_SENHA", "").strip()
    if not cpf_lojista or not senha:
        print("Defina MOTOR_BRADESCO_CPF_LOJISTA e MOTOR_BRADESCO_SENHA.")
        return

    prazos = [
        int(x)
        for x in os.getenv("BRADESCO_PRAZOS", "18,24,36,48").split(",")
        if x.strip()
    ]
    sol = SolicitacaoSimulacao(
        pessoa=Pessoa(
            cpf=os.getenv("BRADESCO_CPF", ""),
            nascimento=os.getenv("BRADESCO_NASC", ""),
            celular=os.getenv("BRADESCO_CELULAR", ""),
        ),
        veiculo=Veiculo(
            placa=os.getenv("BRADESCO_PLACA", ""),
            valor=float(os.getenv("BRADESCO_VALOR", "0") or 0),
            uf_licenciamento=os.getenv("BRADESCO_UF", "SP"),
            categoria="moto",
        ),
        condicoes=Condicoes(
            entrada=float(os.getenv("BRADESCO_ENTRADA", "0") or 0),
            prazos_meses=prazos,
        ),
        provedores=[PROVEDOR],
    )

    d = fabrica_bradesco()
    d.headless = False  # forca janela visivel para voce acompanhar
    # Injeta credencial do env (sem DB); a senha nao e logada.
    d._credencial = lambda ctx: (cpf_lojista, senha)  # type: ignore[assignment]
    print(f"login_url  {d.login_url}")
    print(f"headless   {d.headless}   lojista {_mask(cpf_lojista)}")
    print(
        f"placa {sol.veiculo.placa or '(sem placa)'}  valor {sol.veiculo.valor}  "
        f"uf {sol.veiculo.uf_licenciamento}  entrada {sol.condicoes.entrada}  "
        f"prazos {prazos}"
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
