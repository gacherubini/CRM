"""Simulacao manual, progresso, historico e registros para impressao."""

from __future__ import annotations

from fastapi import APIRouter

from app.main import (  # import tardio; main registra este router no fim
    Depends,
    HTMLResponse,
    MotorClient,
    MotorIndisponivel,
    RedirectResponse,
    Request,
    Response,
    Session,
    contexto,
    csrf_valido,
    enriquecer_credenciais,
    get_db,
    get_motor_client,
    mascarar_cpf,
    pode_gerir_financeiras,
    pode_ver_custo,
    pode_ver_financeiro,
    redirecionar_login,
    templates,
    usuario_atual,
    uuid,
)

router = APIRouter()


def pode_simular(usuario) -> bool:
    return usuario.papel in {"dono", "gerente", "vendedor", "admin_plataforma"}


# Campos que o vendedor pode ver na simulação. Whitelist é o padrão seguro:
# qualquer campo novo que um driver real devolva (custo, lucro, margem,
# spread, comissão, tokens do Motor, métricas financeiras) fica de fora por
# omissão, sem depender de manter uma lista de campos proibidos atualizada.
_SIMULACAO_CAMPOS_PUBLICOS = {
    "id",
    "status",
    "criada_em",
    "resultados",
    "mensagem",
    "provedores",
    "tarefas",
    "placa",
    "prazos_meses",
}
_SIMULACAO_RESULTADO_CAMPOS_PUBLICOS = {
    "provedor",
    "status",
    "valor_parcela",
    "taxa_am",
    "prazo_meses",
    "valor_financiado",
    "entrada",
    "codigo_erro",
}


def simulacao_sem_dados_sensiveis(resultado: dict) -> dict:
    """Remove dados sensíveis da simulação para papéis sem acesso financeiro.

    Devolve uma cópia contendo apenas os campos públicos (parcelas, taxa,
    prazo, valor financiado). Não muta o dicionário original — dono/gerente
    continuam recebendo a resposta completa.
    """
    if not isinstance(resultado, dict):
        return resultado
    limpo = {k: v for k, v in resultado.items() if k in _SIMULACAO_CAMPOS_PUBLICOS}
    resultados = limpo.get("resultados")
    if isinstance(resultados, list):
        limpo["resultados"] = [
            {k: v for k, v in item.items() if k in _SIMULACAO_RESULTADO_CAMPOS_PUBLICOS}
            if isinstance(item, dict)
            else item
            for item in resultados
        ]
    return limpo


UFS_BR = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
]


# Bancos reais do Motor; "todos" consulta os que tiverem credencial.
_PROVEDORES_REAIS = frozenset({"santander", "pan", "fontecred", "bradesco"})
_ROTULOS_BANCO = {
    "santander": "Santander",
    "pan": "Banco PAN",
    "fontecred": "Fontecred",
    "bradesco": "Bradesco",
}


def _parse_celular_form(raw: str | None) -> tuple[str | None, str | None]:
    """Extrai (ddd, celular) de um campo livre com DDD.

    Aceita 10/11 dígitos (com DDD) ou 12/13 com prefixo 55.
    Devolve celular sem DDD (8–9 dígitos) e ddd com 2 dígitos.
    """
    digitos = "".join(c for c in (raw or "") if c.isdigit())
    if digitos.startswith("55") and len(digitos) >= 12:
        digitos = digitos[2:]
    if len(digitos) in (10, 11):
        return digitos[:2], digitos[2:]
    return None, None


def _lista_form(form, nome: str) -> list[str]:
    """Lê campo multi-valor do form (checkboxes) de forma compatível com testes."""
    if hasattr(form, "getlist"):
        vals = form.getlist(nome)
    else:
        vals = form.get(nome)
    if vals is None:
        return []
    if isinstance(vals, (str, bytes)):
        return [str(vals)]
    return [str(v) for v in vals if v is not None and str(v).strip()]


def _valores_form_simulacao(form) -> dict:
    provedores = [
        p.strip().lower()
        for p in _lista_form(form, "provedores")
        if p and str(p).strip()
    ]
    return {
        "modo": "selecionados" if provedores else "todos",
        "provedores": provedores,
        "cpf": form.get("cpf") or "",
        "nascimento": form.get("nascimento", ""),
        "celular": form.get("celular") or "",
        "cnh": form.get("cnh") or "sim",
        "valor": form.get("valor", ""),
        "prazos_meses": form.get("prazos_meses", ""),
        "entrada": form.get("entrada", ""),
        "categoria": form.get("categoria", "moto"),
        "placa": (form.get("placa") or "").strip().upper(),
        "uf_licenciamento": form.get("uf_licenciamento") or "SP",
        "finalidade": form.get("finalidade") or "comum",
        "zero_km": form.get("zero_km") or "nao",
    }


def _credenciais_prontas_motor(motor: "MotorClient", ator: str | None) -> list[dict]:
    """Bancos com login configurado e habilitado (máscara do Motor)."""
    try:
        raw = motor.listar_credenciais(ator=ator)
        provedores = motor.listar_provedores(ator=ator)
    except MotorIndisponivel:
        return []
    itens = enriquecer_credenciais(raw, provedores)
    return [
        c
        for c in itens
        if c.get("senha_configurada") and c.get("habilitado")
    ]


def _provedores_da_simulacao(
    form, credenciais_prontas: list[dict]
) -> list[str]:
    """Bancos escolhidos no form ∩ credencial pronta.

    Se o form não mandar ``provedores``, mantém o comportamento antigo
    (todos os prontos) para compatibilidade com clientes/testes legados.
    """
    prontos: list[str] = []
    vistos: set[str] = set()
    for c in credenciais_prontas:
        nome = (c.get("provedor") or "").strip().lower()
        if nome and nome not in vistos:
            vistos.add(nome)
            prontos.append(nome)

    escolhidos = {
        p.strip().lower()
        for p in _lista_form(form, "provedores")
        if p and str(p).strip()
    }
    if not escolhidos:
        return prontos
    return [p for p in prontos if p in escolhidos]


def dados_simulacao_motor(
    form, provedores: list[str] | str | None = None
) -> dict:
    """Payload SolicitacaoSimulacao para um ou mais provedores reais do Motor."""
    if isinstance(provedores, str):
        lista = [provedores]
    elif provedores:
        lista = list(provedores)
    else:
        lista = ["santander"]
    lista = [p.strip().lower() for p in lista if p and str(p).strip()]
    if not lista:
        raise ValueError("informe ao menos um provedor")
    cpf = "".join(c for c in (form.get("cpf") or "") if c.isdigit())
    nascimento = form.get("nascimento", "").strip()
    ddd, celular = _parse_celular_form(form.get("celular"))
    if not ddd or not celular:
        raise ValueError("informe celular com DDD (10 ou 11 dígitos)")
    entrada = float(str(form.get("entrada") or 0).replace(",", "."))
    placa = (form.get("placa") or "").replace("-", "").strip().upper() or None
    valor_raw = (form.get("valor") or "").strip()
    valor = float(valor_raw.replace(",", ".")) if valor_raw else None
    if valor is None and not placa:
        raise ValueError("informe placa ou valor")
    prazos_txt = (form.get("prazos_meses") or "").strip()
    if prazos_txt:
        prazos = [int(p.strip()) for p in prazos_txt.split(",") if p.strip()]
    else:
        prazos = [24, 36, 48]
    cnh = (form.get("cnh") or "sim").lower() != "nao"
    # Portais (Fontecred/Bradesco/PAN) costumam mascarar DDD+número no mesmo campo.
    # APIs (PAN) usam ddd e celular separados — enviamos os dois formatos úteis.
    celular_completo = f"{ddd}{celular}"
    return {
        "pessoa": {
            "cpf": cpf,
            "nascimento": nascimento,
            "cnh": cnh,
            "ddd": ddd,
            "celular": celular_completo,
        },
        "veiculo": {
            "categoria": form.get("categoria") or "moto",
            "valor": valor,
            "placa": placa,
            "uf_licenciamento": form.get("uf_licenciamento") or "SP",
            "finalidade": form.get("finalidade") or "comum",
            "zero_km": (form.get("zero_km") or "nao").lower() == "sim",
        },
        "condicoes": {"entrada": entrada, "prazos_meses": prazos},
        "provedores": lista,
    }


@router.get("/app/simulacoes", response_class=HTMLResponse)
def simulacoes_pagina(
    request: Request,
    celular: str | None = None,
    db: Session = Depends(get_db),
    motor: MotorClient = Depends(get_motor_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_simular(usuario):
        return RedirectResponse("/app", status_code=303)
    bancos_prontos = _credenciais_prontas_motor(motor, usuario.email)
    # Prefill opcional a partir do workspace de Atendimento (?celular=).
    celular_limpo = "".join(c for c in (celular or "") if c.isdigit())
    valores: dict = {"modo": "todos"}
    if celular_limpo:
        valores["celular"] = celular_limpo
    return templates.TemplateResponse(
        "simulacoes/form.html",
        contexto(
            request,
            usuario,
            valores=valores,
            ufs=UFS_BR,
            bancos_prontos=bancos_prontos,
        ),
    )


@router.post("/app/simulacoes", response_class=HTMLResponse)
async def simulacoes_simular(
    request: Request,
    db: Session = Depends(get_db),
    motor: MotorClient = Depends(get_motor_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_simular(usuario):
        return RedirectResponse("/app", status_code=303)
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/simulacoes", status_code=303)
    valores = _valores_form_simulacao(form)
    bancos_prontos = _credenciais_prontas_motor(motor, usuario.email)

    def _rerender(erro: str, status: int = 422):
        return templates.TemplateResponse(
            "simulacoes/form.html",
            contexto(
                request,
                usuario,
                valores=valores,
                ufs=UFS_BR,
                bancos_prontos=bancos_prontos,
                erro=erro,
            ),
            status_code=status,
        )

    provedores = _provedores_da_simulacao(form, bancos_prontos)
    if not bancos_prontos:
        return _rerender(
            "Nenhum banco com acesso configurado. Cadastre login em "
            "Acessos dos bancos e tente de novo."
        )
    if not provedores:
        return _rerender(
            "Selecione ao menos um banco com acesso configurado para simular."
        )
    try:
        payload_motor = dados_simulacao_motor(form, provedores)
    except (TypeError, ValueError):
        return _rerender(
            "Confira CPF, nascimento, celular (DDD+número), placa/valor, entrada e prazos."
        )
    try:
        criada = motor.criar_simulacao(
            payload_motor, ator=usuario.email, idempotency_key=str(uuid.uuid4())
        )
    except MotorIndisponivel as exc:
        return _rerender(str(exc), status=503)
    sim_id = criada.get("id")
    if not sim_id:
        return _rerender("Motor não devolveu id da simulação.", status=503)
    valores_job = dict(valores)
    valores_job["modo"] = "selecionados" if len(provedores) == 1 else "multi"
    valores_job["provedores"] = list(provedores)
    jobs = request.session.get("sim_jobs") or {}
    jobs[sim_id] = {
        "valores": valores_job,
        "cpf": payload_motor["pessoa"]["cpf"],
        "criada_em": criada.get("criada_em") or "",
        "provedores": list(provedores),
    }
    request.session["sim_jobs"] = jobs
    return RedirectResponse(f"/app/simulacoes/job/{sim_id}", status_code=303)


# Estados do job no Motor (worker Playwright).
_SIM_STATUS_TERMINAIS = frozenset(
    {"concluida", "parcial", "falhou", "aguardando_intervencao", "cancelada"}
)

_SIM_STATUS_LABELS = {
    "recebida": "Na fila",
    "processando": "Processando no banco",
    "concluida": "Concluída",
    "parcial": "Parcial (alguns prazos)",
    "falhou": "Falhou",
    "aguardando_intervencao": "Aguardando intervenção",
    "cancelada": "Cancelada",
}


def _cards_bancos_progresso(
    provedores: list[str],
    resultados: list[dict] | None,
    tarefas: list[dict] | None,
    status_job: str,
) -> list[dict]:
    """Um card por banco com estado derivado de tarefas e resultados parciais."""
    resultados = resultados or []
    tarefas = tarefas or []
    por_tarefa = {
        (t.get("provedor") or "").lower(): t for t in tarefas if t.get("provedor")
    }
    por_resultado: dict[str, list[dict]] = {}
    for r in resultados:
        chave = (r.get("provedor") or "").lower()
        por_resultado.setdefault(chave, []).append(r)

    cards = []
    for nome in provedores:
        chave = (nome or "").lower()
        rotulo = _ROTULOS_BANCO.get(chave, nome or "Banco")
        tarefa = por_tarefa.get(chave)
        linhas = por_resultado.get(chave) or []
        # Resultados de mock usam nomes capitalizados; se só há um provedor na lista, usa todos.
        if not linhas and len(provedores) == 1:
            linhas = list(resultados)

        if tarefa and tarefa.get("status"):
            st = (tarefa.get("status") or "").lower()
        elif linhas:
            if any(r.get("status") == "concluida" for r in linhas):
                st = "concluida"
            elif any(r.get("codigo_erro") for r in linhas):
                st = "falhou"
            else:
                st = (linhas[0].get("status") or "processando").lower()
        elif status_job in _SIM_STATUS_TERMINAIS:
            st = "falhou"
        elif status_job == "processando":
            st = "processando"
        else:
            st = "recebida"

        ofertas_ok = sum(1 for r in linhas if r.get("status") == "concluida")
        parcela_exemplo = next(
            (
                r.get("valor_parcela")
                for r in linhas
                if r.get("status") == "concluida" and r.get("valor_parcela") is not None
            ),
            None,
        )
        label_status = {
            "recebida": "Na fila",
            "acordando_worker": "Acordando worker",
            "reservada": "Reservada",
            "processando": "Consultando",
            "concluida": "Com oferta" if ofertas_ok else "Concluída",
            "parcial": "Parcial",
            "falhou": "Falhou",
            "rejeitada": "Rejeitada",
            "cancelada": "Cancelada",
        }.get(st, st.replace("_", " "))
        cards.append(
            {
                "provedor": chave,
                "rotulo": rotulo,
                "status": st,
                "status_label": label_status,
                "ofertas": ofertas_ok,
                "parcela_exemplo": parcela_exemplo,
                "codigo_erro": (tarefa or {}).get("codigo_erro")
                or next((r.get("codigo_erro") for r in linhas if r.get("codigo_erro")), None),
            }
        )
    return cards


def _passos_progresso_simulacao(
    status: str, provedor: str = "santander"
) -> list[dict]:
    """Etapas visíveis na tela de progresso de um provedor real."""
    rotulo = _ROTULOS_BANCO.get(provedor, provedor.title() if provedor else "Banco")
    if provedor == "todos":
        rotulo = "bancos configurados"
    modo = "portal lojista"
    ordem = ["recebida", "processando", "terminal"]
    terminal_ok = status in ("concluida", "parcial")
    terminal_fail = status in ("falhou", "cancelada", "aguardando_intervencao")
    idx = {
        "recebida": 0,
        "processando": 1,
    }.get(status, 2 if status in _SIM_STATUS_TERMINAIS else 0)

    def estado(passo_i: int) -> str:
        if passo_i < idx:
            return "done"
        if passo_i == idx:
            if passo_i == 2 and terminal_fail:
                return "fail"
            if passo_i == 2 and terminal_ok:
                return "done"
            return "active"
        return "pending"

    titulo_final = _SIM_STATUS_LABELS.get(status, "Finalizando")
    if status not in _SIM_STATUS_TERMINAIS:
        titulo_final = "Aguardando resultado"
    detalhe_final = {
        "concluida": f"Parcelas recebidas com sucesso do {rotulo}.",
        "parcial": "Parte dos prazos retornou; confira a tabela.",
        "falhou": "O Motor não conseguiu concluir. Veja o código de erro abaixo ou em Acessos bancos.",
        "aguardando_intervencao": "O portal pediu ação manual (captcha, 2FA, senha).",
        "cancelada": "Job cancelado.",
    }.get(status, "Quando o worker terminar, as parcelas aparecem automaticamente.")

    return [
        {
            "num": "01",
            "titulo": "Simulação enfileirada",
            "detalhe": "Pedido aceito pelo Motor e colocado na fila do worker.",
            "estado": estado(0),
        },
        {
            "num": "02",
            "titulo": f"Consultando {rotulo}",
            "detalhe": f"Conectando pela {modo} e aguardando as condições de financiamento.",
            "estado": estado(1),
        },
        {
            "num": "03",
            "titulo": titulo_final,
            "detalhe": detalhe_final,
            "estado": estado(2),
        },
    ]


@router.get("/app/simulacoes/job/{sim_id}", response_class=HTMLResponse)
def simulacoes_job(
    sim_id: str,
    request: Request,
    db: Session = Depends(get_db),
    motor: MotorClient = Depends(get_motor_client),
):
    """Tela de progresso: mostra o status do job no Motor e atualiza sozinha."""
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_simular(usuario):
        return RedirectResponse("/app", status_code=303)

    jobs = request.session.get("sim_jobs") or {}
    meta = jobs.get(sim_id) or {}
    valores = meta.get("valores") or {"modo": "todos"}
    provedores = list(
        meta.get("provedores")
        or valores.get("provedores")
        or (
            [valores["modo"]]
            if valores.get("modo") in _PROVEDORES_REAIS
            else []
        )
    )
    provedor_passo = (
        "todos"
        if len(provedores) != 1
        else (provedores[0] if provedores else "santander")
    )
    cpf = meta.get("cpf") or ""

    try:
        resultado = motor.obter_simulacao(sim_id, ator=usuario.email)
    except MotorIndisponivel as exc:
        return templates.TemplateResponse(
            "simulacoes/progresso.html",
            contexto(
                request,
                usuario,
                sim_id=sim_id,
                status="erro_motor",
                status_label="Motor indisponível",
                passos=_passos_progresso_simulacao("recebida", provedor_passo),
                valores=valores,
                cpf_mascarado=mascarar_cpf(cpf),
                auto_refresh=True,
                refresh_segundos=5,
                erro=str(exc),
                resultados_parciais=[],
                cards_bancos=_cards_bancos_progresso(
                    provedores, [], [], "erro_motor"
                ),
            ),
            status_code=503,
        )

    status = (resultado.get("status") or "recebida").lower()
    status_label = _SIM_STATUS_LABELS.get(status, status.replace("_", " "))
    if not provedores:
        provedores = list(resultado.get("provedores") or [])

    if status in _SIM_STATUS_TERMINAIS:
        if not pode_ver_custo(usuario):
            resultado = simulacao_sem_dados_sensiveis(resultado)
        # Histórico sem sessão: completa parâmetros a partir do job no Motor.
        if not valores.get("placa") and resultado.get("placa"):
            valores = {**valores, "placa": resultado.get("placa")}
        if not valores.get("prazos_meses") and resultado.get("prazos_meses"):
            valores = {**valores, "prazos_meses": resultado.get("prazos_meses")}
        if not valores.get("provedores") and resultado.get("provedores"):
            valores = {**valores, "provedores": resultado.get("provedores")}
        resultados_lista = resultado.get("resultados") or []
        return templates.TemplateResponse(
            "simulacoes/resultado.html",
            contexto(
                request,
                usuario,
                valores=valores,
                resultado=resultado,
                grupos_resultados=_grupos_resultados_por_banco(resultados_lista),
                cpf_mascarado=mascarar_cpf(cpf),
            ),
        )

    resultados = resultado.get("resultados") or []
    tarefas = resultado.get("tarefas") or []
    return templates.TemplateResponse(
        "simulacoes/progresso.html",
        contexto(
            request,
            usuario,
            sim_id=sim_id,
            status=status,
            status_label=status_label,
            passos=_passos_progresso_simulacao(status, provedor_passo),
            valores=valores,
            cpf_mascarado=mascarar_cpf(cpf),
            auto_refresh=True,
            refresh_segundos=3,
            erro=None,
            resultados_parciais=resultados,
            cards_bancos=_cards_bancos_progresso(
                provedores, resultados, tarefas, status
            ),
        ),
    )


@router.get("/app/simulacoes/historico", response_class=HTMLResponse)
def simulacoes_historico(
    request: Request,
    status: str | None = None,
    escopo: str | None = None,
    limite: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    motor: MotorClient = Depends(get_motor_client),
):
    """Histórico das simulações do usuário logado (ator/email).

    Escopo padrão = "minhas" (filtra por solicitado_por = email do usuário).
    Dono/gerente podem alternar para "toda a loja" (mesmo cliente Motor/tenant).
    A listagem não traz valores financeiros (o Motor projeta só campos não
    sensíveis), então não há o que esconder do vendedor aqui.
    """
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_simular(usuario):
        return RedirectResponse("/app", status_code=303)

    pode_ver_loja = pode_ver_financeiro(usuario)
    ver_loja = escopo == "loja" and pode_ver_loja
    solicitado_por = None if ver_loja else usuario.email

    limite = max(1, min(int(limite or 20), 100))
    offset = max(0, int(offset or 0))
    status_filtro = status if status in _SIM_STATUS_LABELS else None

    itens, total, erro = [], 0, None
    try:
        dados = motor.listar_simulacoes(
            ator=usuario.email,
            status=status_filtro,
            solicitado_por=solicitado_por,
            limite=limite,
            offset=offset,
        )
        itens = dados.get("itens") or []
        total = dados.get("total") or 0
    except MotorIndisponivel as exc:
        erro = str(exc)

    return templates.TemplateResponse(
        "simulacoes/historico.html",
        contexto(
            request,
            usuario,
            itens=itens,
            total=total,
            limite=limite,
            offset=offset,
            escopo="loja" if ver_loja else "minhas",
            pode_ver_loja=pode_ver_loja,
            status_filtro=status_filtro or "",
            status_labels=_SIM_STATUS_LABELS,
            integracao_erro=erro,
        ),
    )


def _grupos_eventos_por_banco(eventos: list[dict]) -> list[dict]:
    """Agrupa timeline por provedor (fan-out multi-banco). Ordem = primeira aparição."""
    ordem: list[str] = []
    buckets: dict[str, list[dict]] = {}
    for ev in eventos or []:
        chave = (ev.get("provedor") or "").strip().lower() or "geral"
        if chave not in buckets:
            ordem.append(chave)
            buckets[chave] = []
        buckets[chave].append(ev)
    grupos = []
    for chave in ordem:
        rotulo = (
            "Geral"
            if chave == "geral"
            else _ROTULOS_BANCO.get(chave, chave.replace("_", " ").title())
        )
        grupos.append({"provedor": chave, "rotulo": rotulo, "eventos": buckets[chave]})
    return grupos


def _grupos_resultados_por_banco(resultados: list[dict] | None) -> list[dict]:
    """Agrupa ofertas por provedor para a tela de resultado multi-banco."""
    ordem: list[str] = []
    buckets: dict[str, list[dict]] = {}
    for r in resultados or []:
        if not isinstance(r, dict):
            continue
        chave = (r.get("provedor") or "banco").strip().lower() or "banco"
        if chave not in buckets:
            ordem.append(chave)
            buckets[chave] = []
        buckets[chave].append(r)
    grupos = []
    for chave in ordem:
        linhas = buckets[chave]
        ofertas_ok = sum(
            1
            for r in linhas
            if (r.get("status") or "").lower() == "concluida"
            and r.get("valor_parcela") is not None
        )
        codigo_erro = next(
            (r.get("codigo_erro") for r in linhas if r.get("codigo_erro")),
            None,
        )
        grupos.append(
            {
                "provedor": chave,
                "rotulo": _ROTULOS_BANCO.get(chave, chave.replace("_", " ").title()),
                "linhas": linhas,
                "ofertas_ok": ofertas_ok,
                "codigo_erro": codigo_erro,
            }
        )
    return grupos


@router.get("/app/simulacoes/{sim_id}/registros", response_class=HTMLResponse)
def simulacoes_registros(
    sim_id: str,
    request: Request,
    db: Session = Depends(get_db),
    motor: MotorClient = Depends(get_motor_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_simular(usuario):
        return RedirectResponse("/app", status_code=303)
    erro = None
    dados = {"status": "desconhecido", "eventos": []}
    try:
        dados = motor.listar_eventos(sim_id, ator=usuario.email)
    except MotorIndisponivel as exc:
        erro = str(exc)
    status = str(dados.get("status") or "desconhecido").lower()
    eventos = dados.get("eventos") or []
    return templates.TemplateResponse(
        "simulacoes/registros.html",
        contexto(
            request,
            usuario,
            sim_id=sim_id,
            status=status,
            status_label=_SIM_STATUS_LABELS.get(status, status.replace("_", " ")),
            eventos=eventos,
            grupos_eventos=_grupos_eventos_por_banco(eventos),
            pode_ver_print=pode_gerir_financeiras(usuario),
            auto_refresh=status not in _SIM_STATUS_TERMINAIS,
            erro=erro,
        ),
    )


@router.get("/app/simulacoes/{sim_id}/registros/{evento_id}/print")
def simulacoes_registro_print(
    sim_id: str,
    evento_id: int,
    request: Request,
    db: Session = Depends(get_db),
    motor: MotorClient = Depends(get_motor_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    # Prints podem conter CPF/placa: vendedor vê a timeline, mas não a imagem.
    if not pode_gerir_financeiras(usuario):
        return Response(status_code=403)
    try:
        conteudo, tipo = motor.obter_print_evento(sim_id, evento_id, ator=usuario.email)
    except MotorIndisponivel:
        return Response(status_code=404)
    return Response(
        content=conteudo,
        media_type=tipo,
        headers={"Cache-Control": "private, no-store, max-age=0"},
    )
