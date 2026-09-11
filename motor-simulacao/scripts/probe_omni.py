"""Smoke LIVE do driver Omni (Omni+ motocicletas), headed.

Abre o navegador visivel e roda o fluxo real do portal (login -> Nova Simulacao
-> CPF -> telefone -> placa -> valor -> ofertas), sem Portal/DB. A senha NUNCA
vai no codigo nem em argumento. Para no resultado: nao conclui a proposta.

Uso (a partir de motor-simulacao/, com .env.local preenchido):
  macOS:   .venv/bin/python scripts/probe_omni.py
  Windows: .\\.venv\\Scripts\\python.exe scripts/probe_omni.py

Env (.env.local, gitignored):
  MOTOR_OMNI_PORTAL_USUARIO / MOTOR_OMNI_PORTAL_SENHA (login do lojista)
  OMNI_CPF / OMNI_CELULAR / OMNI_PLACA / OMNI_VALOR / OMNI_UF / OMNI_ENTRADA
  OMNI_PRAZOS=12,18,24,36,48  MOTOR_OMNI_VENDEDOR=(parcial, opcional)

Screenshots de falha vao para data/screenshots. Usuario/senha/CPF nao impressos.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def carregar_env_local(caminho: Path) -> None:
    if not caminho.is_file():
        return
    for linha in caminho.read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        chave = chave.strip()
        valor = valor.strip().strip('"').strip("'")
        if chave and chave not in os.environ:
            os.environ[chave] = valor


carregar_env_local(Path(__file__).resolve().parent.parent / ".env.local")

from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.drivers import (
    ErroTransitorio,
    IntervencaoNecessaria,
    RejeicaoNegocio,
)
from app.motor.omni import PROVEDOR, fabrica_omni


def _mask(s: str) -> str:
    s = s or ""
    return (s[:3] + "***") if s else "(vazio)"


def main() -> None:
    usuario = os.getenv("MOTOR_OMNI_PORTAL_USUARIO", "").strip()
    senha = os.getenv("MOTOR_OMNI_PORTAL_SENHA", "").strip()
    if not usuario or not senha:
        print("Defina MOTOR_OMNI_PORTAL_USUARIO e MOTOR_OMNI_PORTAL_SENHA.")
        return

    prazos = [
        int(x)
        for x in os.getenv("OMNI_PRAZOS", "12,18,24,36,48").split(",")
        if x.strip()
    ]
    sol = SolicitacaoSimulacao(
        pessoa=Pessoa(
            cpf=os.getenv("OMNI_CPF", ""),
            nascimento=os.getenv("OMNI_NASC", ""),
            celular=os.getenv("OMNI_CELULAR", ""),
        ),
        veiculo=Veiculo(
            placa=os.getenv("OMNI_PLACA", ""),
            valor=float(os.getenv("OMNI_VALOR", "0") or 0),
            uf_licenciamento=os.getenv("OMNI_UF", "SP"),
            categoria="moto",
        ),
        condicoes=Condicoes(
            entrada=float(os.getenv("OMNI_ENTRADA", "0") or 0),
            prazos_meses=prazos,
        ),
        provedores=[PROVEDOR],
    )

    d = fabrica_omni(vendedor=os.getenv("MOTOR_OMNI_VENDEDOR", "").strip() or None)
    d.headless = False  # forca janela visivel para acompanhar
    d._credencial = lambda ctx: (usuario, senha)  # type: ignore[assignment]
    print(f"login_url  {d.login_url}")
    print(f"headless   {d.headless}   usuario {_mask(usuario)}")
    print(
        f"valor {sol.veiculo.valor}  entrada {sol.condicoes.entrada}  prazos {prazos}"
    )
    print("-" * 60)

    import time as _t

    def _log(etapa, mensagem, nivel="info", shot=None):
        print(f"  [{_t.strftime('%H:%M:%S')}] {etapa}: {mensagem}")

    from app.motor.drivers import DriverContext

    ctx = DriverContext(evento=_log)

    try:
        resultados = d.simular(sol, ctx)
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
