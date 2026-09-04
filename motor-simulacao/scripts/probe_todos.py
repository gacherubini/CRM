r"""Roda os quatro drivers Playwright ao vivo, um de cada vez, e diz quais falham.

Um lugar so para responder "quais bancos estao funcionando hoje". Cada banco roda
headed (janela visivel), com log de etapa ao vivo, screenshot na falha e um
relatorio final em tabela. Nao precisa de Portal, DB nem Fly: a credencial vem do
`.env.local` e e injetada direto no driver.

Uso (PowerShell, a partir de motor-simulacao/):

    copy .env.local.exemplo .env.local     # preencha uma vez, fica fora do git
    .\.venv\Scripts\python.exe scripts\probe_todos.py

Rodar so alguns:

    .\.venv\Scripts\python.exe scripts\probe_todos.py --bancos bradesco,pan

macOS:

    .venv/bin/python scripts/probe_todos.py

Senha, CPF e usuario nunca sao impressos nem gravados no relatorio.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


# --------------------------------------------------------------------------
# .env.local — carregado antes de importar app.config (config le env no import)
# --------------------------------------------------------------------------
def carregar_env_local(caminho: Path) -> int:
    """Le KEY=VALUE simples. Nao sobrescreve variavel ja setada no shell."""
    if not caminho.is_file():
        return 0
    carregadas = 0
    for linha in caminho.read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        chave = chave.strip()
        valor = valor.strip().strip('"').strip("'")
        if chave and chave not in os.environ:
            os.environ[chave] = valor
            carregadas += 1
    return carregadas


_ENV_LOCAL = RAIZ / ".env.local"
_N_ENV = carregar_env_local(_ENV_LOCAL)


def _template_preenchido() -> bool:
    """Erro facil de cometer: preencher o .exemplo e nao o .env.local."""
    exemplo = RAIZ / ".env.local.exemplo"
    if not exemplo.is_file():
        return False
    for linha in exemplo.read_text(encoding="utf-8-sig").splitlines():
        chave, _, valor = linha.strip().partition("=")
        if chave.startswith("MOTOR_") and chave.endswith("_SENHA") and valor.strip():
            return True
    return False

from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo  # noqa: E402
from app.motor.drivers import (  # noqa: E402
    DriverContext,
    ErroTransitorio,
    IntervencaoNecessaria,
    RejeicaoNegocio,
)


# --------------------------------------------------------------------------
# Catalogo: nome -> fabrica + par de env vars da credencial
# --------------------------------------------------------------------------
BANCOS: dict[str, dict[str, object]] = {
    "santander": {
        "rotulo": "Santander",
        "modulo": "app.motor.santander",
        "fabrica": "fabrica_santander",
        "env_usuario": "MOTOR_SANTANDER_USUARIO",
        "env_senha": "MOTOR_SANTANDER_SENHA",
        "rotulo_usuario": "CPF do lojista",
    },
    "fontecred": {
        "rotulo": "Fontecred",
        "modulo": "app.motor.fontecred",
        "fabrica": "fabrica_fontecred",
        "env_usuario": "MOTOR_FONTECRED_EMAIL",
        "env_senha": "MOTOR_FONTECRED_SENHA",
        "rotulo_usuario": "e-mail do portal",
    },
    "bradesco": {
        "rotulo": "Bradesco",
        "modulo": "app.motor.bradesco",
        "fabrica": "fabrica_bradesco",
        "env_usuario": "MOTOR_BRADESCO_CPF_LOJISTA",
        "env_senha": "MOTOR_BRADESCO_SENHA",
        "rotulo_usuario": "CPF do lojista",
    },
    "pan": {
        "rotulo": "Banco PAN (portal)",
        "modulo": "app.motor.pan_portal",
        "fabrica": "fabrica_pan_portal",
        "env_usuario": "MOTOR_PAN_PORTAL_USUARIO",
        "env_senha": "MOTOR_PAN_PORTAL_SENHA",
        "rotulo_usuario": "usuario do go!PAN",
    },
    "motrix": {
        "rotulo": "Motrix (joinbank)",
        "modulo": "app.motor.motrix",
        "fabrica": "fabrica_motrix",
        "env_usuario": "MOTOR_MOTRIX_PORTAL_USUARIO",
        "env_senha": "MOTOR_MOTRIX_PORTAL_SENHA",
        "rotulo_usuario": "usuario do portal Motrix",
    },
}

ORDEM_PADRAO = ["fontecred", "pan", "bradesco", "santander", "motrix"]

# Fixtures desviam o driver do portal real e devolveriam um OK falso.
ENVS_FIXTURE = [
    "MOTOR_SANTANDER_FIXTURE_HTML",
    "MOTOR_FONTECRED_FIXTURE_HTML",
    "MOTOR_BRADESCO_FIXTURE_HTML",
    "MOTOR_PAN_PORTAL_FIXTURE_HTML",
    "MOTOR_MOTRIX_FIXTURE_HTML",
]


def _env(nome: str, default: str = "") -> str:
    return (os.getenv(nome) or default).strip()


def _mascara(valor: str) -> str:
    if not valor:
        return "(vazio)"
    return valor[:3] + "*" * max(0, len(valor) - 3)


def montar_solicitacao(banco: str) -> SolicitacaoSimulacao:
    """Dados do cliente/veiculo: PROBE_* comum, com override por banco."""
    pref = banco.upper()

    def dado(sufixo: str, default: str = "") -> str:
        return _env(f"{pref}_{sufixo}") or _env(f"PROBE_{sufixo}", default)

    prazos = [int(x) for x in dado("PRAZOS", "24,36,48").split(",") if x.strip()]
    return SolicitacaoSimulacao(
        pessoa=Pessoa(
            cpf=dado("CPF"),
            nascimento=dado("NASC"),
            celular=dado("CELULAR"),
        ),
        veiculo=Veiculo(
            placa=dado("PLACA"),
            valor=float(dado("VALOR", "0") or 0),
            uf_licenciamento=dado("UF", "SP"),
            categoria=dado("CATEGORIA", "moto"),
        ),
        condicoes=Condicoes(
            entrada=float(dado("ENTRADA", "0") or 0),
            prazos_meses=prazos,
        ),
        provedores=[banco],
    )


class Relato:
    """Uma linha do relatorio final."""

    def __init__(self, banco: str, rotulo: str):
        self.banco = banco
        self.rotulo = rotulo
        self.status = "nao rodou"
        self.codigo = ""
        self.detalhe = ""
        self.ultima_etapa = "-"
        self.segundos = 0.0
        self.ofertas = 0
        self.shots: list[str] = []


def rodar_banco(banco: str, saida_dir: Path, headless: bool) -> Relato:
    meta = BANCOS[banco]
    rel = Relato(banco, str(meta["rotulo"]))

    usuario = _env(str(meta["env_usuario"]))
    senha = _env(str(meta["env_senha"]))
    if not usuario or not senha:
        rel.status = "SEM CREDENCIAL"
        rel.detalhe = f"defina {meta['env_usuario']} e {meta['env_senha']}"
        return rel

    sol = montar_solicitacao(banco)
    faltando = [
        nome
        for nome, valor in (
            ("cpf", sol.pessoa.cpf),
            ("nascimento", sol.pessoa.nascimento),
            ("celular", sol.pessoa.celular),
            ("placa", sol.veiculo.placa),
        )
        if not valor
    ]
    if faltando or not sol.veiculo.valor:
        if not sol.veiculo.valor:
            faltando.append("valor")
        rel.status = "SEM DADOS"
        rel.detalhe = "faltam PROBE_" + ", PROBE_".join(f.upper() for f in faltando)
        return rel

    modulo = __import__(str(meta["modulo"]), fromlist=[str(meta["fabrica"])])
    driver = getattr(modulo, str(meta["fabrica"]))()
    driver.headless = headless
    driver.screenshot_dir = saida_dir / banco
    driver.screenshot_dir.mkdir(parents=True, exist_ok=True)
    # Credencial do env, sem DB. A senha nao e logada.
    driver._credencial = lambda ctx: (usuario, senha)  # type: ignore[assignment]

    log_path = saida_dir / f"{banco}.log"
    log = log_path.open("w", encoding="utf-8")

    def evento(etapa, mensagem, nivel="info", shot=None, **_kw):
        rel.ultima_etapa = str(etapa)
        linha = f"[{time.strftime('%H:%M:%S')}] {nivel:>5} {etapa}: {mensagem}"
        print("    " + linha)
        log.write(linha + "\n")
        log.flush()
        if shot:
            rel.shots.append(str(shot))

    print(f"\n{'=' * 70}")
    print(f"  {rel.rotulo}  ({banco})")
    print(f"{'=' * 70}")
    print(f"  login    {getattr(driver, 'login_url', '?')}")
    print(f"  headless {driver.headless}   {meta['rotulo_usuario']} {_mascara(usuario)}")
    print(
        f"  cliente  cpf {_mascara(sol.pessoa.cpf)}  celular {_mascara(sol.pessoa.celular)}"
    )
    print(
        f"  veiculo  placa {sol.veiculo.placa}  valor {sol.veiculo.valor}  "
        f"uf {sol.veiculo.uf_licenciamento}  entrada {sol.condicoes.entrada}  "
        f"prazos {sol.condicoes.prazos_meses}"
    )
    print("  " + "-" * 66)

    ctx = DriverContext(evento=evento, screenshot_dir=str(driver.screenshot_dir))
    inicio = time.monotonic()
    try:
        resultados = driver.simular(sol, ctx)
        rel.segundos = time.monotonic() - inicio
        if not resultados:
            rel.status = "VAZIO"
            rel.detalhe = "driver terminou sem levantar erro e sem oferta"
        else:
            rel.status = "OK"
            rel.ofertas = len(resultados)
            print("  Ofertas:")
            for r in sorted(resultados, key=lambda x: x.prazo_meses or 0):
                linha = (
                    f"    {r.prazo_meses:>3}x  parcela R$ {r.valor_parcela}"
                    f"   financiado R$ {r.valor_financiado}   entrada R$ {r.entrada}"
                )
                print(linha)
                log.write(linha + "\n")
    except RejeicaoNegocio as exc:
        # O banco respondeu "nao" — driver funcionou. Misturar isso com FALHA faz
        # ler como quebra o que e resposta de negocio (Motrix, 04/09).
        rel.segundos = time.monotonic() - inicio
        rel.status = "RECUSA"
        rel.codigo = exc.codigo
        rel.detalhe = str(exc)[:200]
    except (IntervencaoNecessaria, ErroTransitorio) as exc:
        rel.segundos = time.monotonic() - inicio
        rel.status = "FALHA"
        rel.codigo = exc.codigo
        rel.detalhe = str(exc)[:200]
    except KeyboardInterrupt:
        rel.segundos = time.monotonic() - inicio
        rel.status = "INTERROMPIDO"
        rel.detalhe = "Ctrl+C"
    except Exception as exc:  # noqa: BLE001
        rel.segundos = time.monotonic() - inicio
        rel.status = "ERRO"
        rel.codigo = type(exc).__name__
        rel.detalhe = str(exc).replace("\n", " ")[:200]
        log.write("\n" + traceback.format_exc())
    finally:
        log.write(f"\nstatus={rel.status} codigo={rel.codigo} {rel.segundos:.0f}s\n")
        log.close()

    # Screenshots que o driver gravou sozinho tambem contam.
    for png in sorted(driver.screenshot_dir.glob("*.png")):
        if str(png) not in rel.shots:
            rel.shots.append(str(png))

    print(f"  -> {rel.status} {rel.codigo} em {rel.segundos:.0f}s")
    if rel.detalhe:
        print(f"     {rel.detalhe}")
    return rel


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--bancos",
        default=",".join(ORDEM_PADRAO),
        help="lista separada por virgula (padrao: todos)",
    )
    ap.add_argument(
        "--headless",
        action="store_true",
        help="sem janela (mais bloqueado pelo WAF; use so para CI)",
    )
    args = ap.parse_args()

    pedidos = [b.strip().lower() for b in args.bancos.split(",") if b.strip()]
    desconhecidos = [b for b in pedidos if b not in BANCOS]
    if desconhecidos:
        print(f"Banco desconhecido: {', '.join(desconhecidos)}")
        print(f"Validos: {', '.join(BANCOS)}")
        return 2

    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    saida_dir = RAIZ / "data" / "probes" / carimbo
    saida_dir.mkdir(parents=True, exist_ok=True)

    print(f"env.local   {_ENV_LOCAL}  ({_N_ENV} variaveis)")
    sem_senha = not any(
        _env(str(m["env_senha"])) for m in BANCOS.values()
    )
    if sem_senha and _template_preenchido():
        print(
            "\nERRO: as senhas estao no .env.local.exemplo, que e so o modelo.\n"
            "  Renomeie:  move /y .env.local.exemplo .env.local     (Windows)\n"
            "             mv -f .env.local.exemplo .env.local       (macOS)\n"
        )
        return 2
    print(f"saida       {saida_dir}")
    fixtures = [e for e in ENVS_FIXTURE if _env(e)]
    if fixtures:
        print(f"AVISO: fixture ligada ({', '.join(fixtures)}) — o driver NAO abre o portal.")

    relatos = [rodar_banco(b, saida_dir, args.headless) for b in pedidos]

    print(f"\n{'=' * 78}")
    print("  RESUMO")
    print(f"{'=' * 78}")
    print(f"  {'banco':<12} {'status':<15} {'codigo':<26} {'tempo':>7}  etapa")
    for r in relatos:
        print(
            f"  {r.banco:<12} {r.status:<15} {r.codigo[:26]:<26} "
            f"{r.segundos:>6.0f}s  {r.ultima_etapa}"
        )
    for r in relatos:
        if r.detalhe:
            print(f"\n  {r.banco}: {r.detalhe}")
        if r.shots:
            print(f"    screenshots: {len(r.shots)} em {saida_dir / r.banco}")
    print(f"\n  logs e screenshots: {saida_dir}")

    # RECUSA nao entra no codigo de saida: o driver fez o trabalho, o banco e que
    # nao ofertou. So quebra de verdade (FALHA/ERRO/VAZIO) reprova a rodada.
    quebrados = [r for r in relatos if r.status not in ("OK", "RECUSA")]
    if quebrados:
        return 1
    recusados = [r.banco for r in relatos if r.status == "RECUSA"]
    if recusados:
        print(f"\n  recusa de negocio (nao e quebra): {', '.join(recusados)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
