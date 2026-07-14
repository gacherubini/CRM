"""Relatórios exportáveis (Plano #3B, Task 8): vendas, metas e funil em CSV.

Rotas isoladas neste router dedicado para não inchar app/main.py — o único
acoplamento com main.py é reaproveitar utilitários já existentes (templates,
contexto, autenticação, cliente do chatbot). A matemática financeira em si
vem de app.financeiro_calc, a MESMA usada por /app/financeiro, então os
totais exportados aqui reconciliam por construção com o painel.
"""
import csv
import io
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

router = APIRouter()

from app.auth import pode_ver_relatorios, usuario_atual  # noqa: E402
from app.clients.chatbot import ChatbotClient  # noqa: E402
from app.db import get_db  # noqa: E402
from app.financeiro_calc import (  # noqa: E402
    calcular_metricas_vendas,
    funil_periodo,
    metas_view_periodo,
    periodo_padrao,
)
from app.models import Usuario  # noqa: E402

# Importado de app.main (não o contrário): quando este módulo é carregado a
# partir do include_router no fim de app/main.py, todos estes nomes já
# existem no namespace de app.main.
from app.main import contexto, get_chatbot_client, redirecionar_login, templates  # noqa: E402


def _sem_permissao(usuario: Usuario | None) -> RedirectResponse | None:
    if not usuario:
        return redirecionar_login()
    if not pode_ver_relatorios(usuario):
        return RedirectResponse("/app", status_code=303)
    return None


def _num(valor) -> str:
    """Formata Decimal com 2 casas fixas, ponto decimal — CSV é separado por vírgula."""
    if valor is None:
        return ""
    return f"{Decimal(valor):.2f}"


def _csv_response(linhas: list[list], nome_arquivo: str) -> Response:
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=",", lineterminator="\r\n")
    for linha in linhas:
        escritor.writerow(linha)
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )


@router.get("/app/relatorios", response_class=HTMLResponse)
def relatorios_pagina(
    request: Request,
    inicio: str | None = None,
    fim: str | None = None,
    vendedor: str | None = None,
    origem: str | None = None,
    db: Session = Depends(get_db),
):
    usuario = usuario_atual(request, db)
    negado = _sem_permissao(usuario)
    if negado:
        return negado
    d_inicio, d_fim = periodo_padrao(inicio, fim)
    vendedores = (
        db.query(Usuario)
        .filter(
            Usuario.loja_slug == usuario.loja_slug,
            Usuario.ativo.is_(True),
            Usuario.papel.in_(["dono", "gerente", "vendedor"]),
        )
        .order_by(Usuario.nome)
        .all()
    )
    vendedores_por_email = {item.email: item for item in vendedores}
    vendedor_filtro = vendedor if vendedor in vendedores_por_email else None
    query = f"inicio={d_inicio.isoformat()}&fim={d_fim.isoformat()}"
    query_funil = query
    if vendedor_filtro:
        query_funil += f"&vendedor={vendedor_filtro}"
    if origem:
        query_funil += f"&origem={origem}"
    return templates.TemplateResponse(
        "relatorios/index.html",
        contexto(
            request,
            usuario,
            periodo={"inicio": d_inicio.isoformat(), "fim": d_fim.isoformat()},
            vendedores=vendedores,
            filtros={"vendedor": vendedor_filtro or "", "origem": origem or ""},
            query=query,
            query_funil=query_funil,
        ),
    )


@router.get("/app/relatorios/vendas.csv")
def relatorios_vendas_csv(
    request: Request,
    inicio: str | None = None,
    fim: str | None = None,
    db: Session = Depends(get_db),
):
    usuario = usuario_atual(request, db)
    negado = _sem_permissao(usuario)
    if negado:
        return negado
    d_inicio, d_fim = periodo_padrao(inicio, fim)
    resultado = calcular_metricas_vendas(db, usuario.loja_slug, d_inicio, d_fim)

    linhas: list[list] = [
        ["id", "data", "vendedor_email", "descricao", "veiculo_ref", "preco_venda", "custo_veiculo", "custos_diretos", "lucro_bruto"]
    ]
    for venda in sorted(resultado["confirmadas"], key=lambda v: v.criada_em):
        diretos = sum((c.valor for c in venda.custos_diretos), Decimal("0"))
        lucro = None
        if venda.custo_veiculo is not None:
            lucro = (venda.preco_venda - venda.custo_veiculo - diretos).quantize(Decimal("0.01"))
        linhas.append(
            [
                venda.id,
                venda.criada_em.date().isoformat(),
                venda.vendedor_email,
                venda.descricao,
                venda.veiculo_ref or "",
                _num(venda.preco_venda),
                _num(venda.custo_veiculo),
                _num(diretos),
                _num(lucro),
            ]
        )
    linhas.append([])
    linhas.append(["quantidade_vendas", resultado["quantidade"]])
    linhas.append(["faturamento_total", _num(resultado["faturamento"])])
    linhas.append(["lucro_bruto_total", _num(resultado["lucro_bruto"])])
    linhas.append(["lucro_completo", "sim" if resultado["lucro_completo"] else "nao"])

    nome = f"relatorio-vendas_{d_inicio.isoformat()}_{d_fim.isoformat()}.csv"
    return _csv_response(linhas, nome)


@router.get("/app/relatorios/metas.csv")
def relatorios_metas_csv(
    request: Request,
    inicio: str | None = None,
    fim: str | None = None,
    db: Session = Depends(get_db),
):
    usuario = usuario_atual(request, db)
    negado = _sem_permissao(usuario)
    if negado:
        return negado
    d_inicio, d_fim = periodo_padrao(inicio, fim)
    resultado = calcular_metricas_vendas(db, usuario.loja_slug, d_inicio, d_fim)
    realizado_por_tipo = {
        "quantidade": Decimal(resultado["quantidade"]),
        "faturamento": resultado["faturamento"],
        "lucro_bruto": resultado["lucro_bruto"],
    }
    metas = metas_view_periodo(
        db, usuario.loja_slug, d_inicio, d_fim, realizado_por_tipo, resultado["lucro_completo"]
    )

    linhas: list[list] = [["tipo", "alvo", "realizado", "percentual", "indisponivel"]]
    for meta in metas:
        linhas.append(
            [
                meta["tipo"],
                _num(meta["alvo"]),
                "" if meta["indisponivel"] else _num(meta["realizado"]),
                "" if meta["indisponivel"] else meta["pct"],
                "sim" if meta["indisponivel"] else "nao",
            ]
        )

    nome = f"relatorio-metas_{d_inicio.isoformat()}_{d_fim.isoformat()}.csv"
    return _csv_response(linhas, nome)


@router.get("/app/relatorios/funil.csv")
def relatorios_funil_csv(
    request: Request,
    inicio: str | None = None,
    fim: str | None = None,
    vendedor: str | None = None,
    origem: str | None = None,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    negado = _sem_permissao(usuario)
    if negado:
        return negado
    d_inicio, d_fim = periodo_padrao(inicio, fim)
    resultado = calcular_metricas_vendas(db, usuario.loja_slug, d_inicio, d_fim)

    vendedores_por_email = {
        item.email
        for item in db.query(Usuario).filter(
            Usuario.loja_slug == usuario.loja_slug,
            Usuario.ativo.is_(True),
            Usuario.papel.in_(["dono", "gerente", "vendedor"]),
        )
    }
    vendedor_filtro = vendedor if vendedor in vendedores_por_email else None
    funil, _origens = funil_periodo(
        chatbot, db, usuario.loja_slug, d_inicio, d_fim, vendedor_filtro, origem, resultado["confirmadas"]
    )

    linhas: list[list] = [
        [
            "periodo_inicio",
            "periodo_fim",
            "vendedor_filtro",
            "origem_filtro",
            "disponivel",
            "leads_elegiveis",
            "atendidos",
            "vendas_vinculadas",
            "erro",
        ],
        [
            d_inicio.isoformat(),
            d_fim.isoformat(),
            vendedor_filtro or "",
            origem or "",
            "sim" if funil["disponivel"] else "nao",
            funil["elegiveis"] if funil["elegiveis"] is not None else "",
            funil["atendidos"] if funil["atendidos"] is not None else "",
            funil["vendas_vinculadas"] if funil["vendas_vinculadas"] is not None else "",
            funil["erro"] or "",
        ],
    ]

    nome = f"relatorio-funil_{d_inicio.isoformat()}_{d_fim.isoformat()}.csv"
    return _csv_response(linhas, nome)
