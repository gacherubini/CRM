"""Campanhas, ROI, Pixel/CAPI, Ads e jobs internos de trafego."""

from __future__ import annotations

from fastapi import APIRouter

from app import main as main_module
from app.main import (  # import tardio; main registra este router no fim
    CANAIS_ROTULO,
    Campanha,
    CampanhaGasto,
    ChatbotClient,
    ChatbotIndisponivel,
    Decimal,
    Depends,
    HTMLResponse,
    Header,
    JSONResponse,
    MetaAdsConfig,
    MetaCapiOutbox,
    MetaPixelConfig,
    RedirectResponse,
    Request,
    Response,
    STATUS_ROTULO,
    Session,
    SessionLocal,
    agora,
    calcular_metricas_vendas,
    calcular_roi_loja,
    campanha_payload_form,
    campanha_por_utm,
    cifrar,
    contexto,
    csrf_valido,
    date,
    gerar_insights_roi,
    get_chatbot_client,
    get_db,
    meta_ads_spend_job,
    normalizar_ad_account_id,
    normalizar_pixel_id,
    normalizar_utm,
    novo_id,
    os,
    parse_brl_valor,
    parse_gastos_csv,
    periodo_padrao,
    pode_gerir_trafego,
    preencher_campanha,
    processar_outbox_pendentes,
    provisioning,
    redirecionar_login,
    salvar_gasto_manual,
    secrets,
    templates,
    totais_roi,
    usuario_atual,
    validar_campanha_payload,
    venda_casa_campanha,
)

router = APIRouter()


def _trafego_contexto(
    request: Request,
    usuario,
    config: MetaPixelConfig | None,
    *,
    ads_config: MetaAdsConfig | None = None,
    ultimo_outbox: MetaCapiOutbox | None = None,
    pendentes: int = 0,
    ok=None,
    erro=None,
    sync_resumo=None,
):
    token_configurado = bool(config and config.token_ciphertext)
    ads_token_configurado = bool(ads_config and ads_config.token_ciphertext)
    ultimo_erro_exibicao = None
    if ultimo_outbox is not None and ultimo_outbox.status == "failed":
        ultimo_erro_exibicao = (
            f"Meta respondeu HTTP {ultimo_outbox.last_http_status}."
            if ultimo_outbox.last_http_status
            else "O último envio falhou. Retente para processar novamente."
        )
    return contexto(
        request,
        usuario,
        config=config,
        ads_config=ads_config,
        token_configurado=token_configurado,
        ads_token_configurado=ads_token_configurado,
        pixel_id=normalizar_pixel_id(config.pixel_id if config else None),
        test_event_code=(config.test_event_code if config else "") or "",
        enviar_page_view=bool(config.enviar_page_view) if config else True,
        enviar_lead=bool(config.enviar_lead) if config else True,
        enviar_purchase=bool(config.enviar_purchase) if config else True,
        atualizada_em=config.atualizada_em if config else None,
        ad_account_id=(ads_config.ad_account_id if ads_config else "") or "",
        ads_sync_enabled=bool(ads_config.sync_enabled) if ads_config else True,
        ads_ultima_sync_em=ads_config.ultima_sync_em if ads_config else None,
        ads_ultima_sync_status=(ads_config.ultima_sync_status if ads_config else None),
        ads_ultima_sync_erro=(ads_config.ultima_sync_erro if ads_config else None),
        ads_ultima_sync_resumo=(ads_config.ultima_sync_resumo if ads_config else None),
        ultimo_outbox=ultimo_outbox,
        ultimo_erro_exibicao=ultimo_erro_exibicao,
        outbox_pendentes=pendentes,
        ok=ok,
        erro=erro,
        sync_resumo=sync_resumo,
    )


@router.get("/app/campanhas", response_class=HTMLResponse)
def campanhas_lista(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_trafego(usuario):
        return RedirectResponse("/app", status_code=303)
    campanhas = (
        db.query(Campanha)
        .filter(Campanha.loja_slug == usuario.loja_slug)
        .order_by(Campanha.criada_em.desc())
        .all()
    )
    gastos_totais: dict[str, Decimal] = {}
    for g in db.query(CampanhaGasto).filter(CampanhaGasto.loja_slug == usuario.loja_slug).all():
        gastos_totais[g.campanha_id] = gastos_totais.get(g.campanha_id, Decimal("0")) + g.valor
    return templates.TemplateResponse(
        "campanhas/lista.html",
        contexto(
            request,
            usuario,
            campanhas=campanhas,
            gastos_totais=gastos_totais,
            canais=CANAIS_ROTULO,
            status_rotulo=STATUS_ROTULO,
        ),
    )


def _campanha_form_ctx(request, usuario, *, titulo, valores, erro=None):
    return contexto(
        request,
        usuario,
        titulo=titulo,
        valores=valores,
        erro=erro,
        canais=CANAIS_ROTULO,
        status_rotulo=STATUS_ROTULO,
    )


@router.get("/app/campanhas/nova", response_class=HTMLResponse)
def campanhas_nova_get(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_trafego(usuario):
        return RedirectResponse("/app", status_code=303)
    return templates.TemplateResponse(
        "campanhas/form.html",
        _campanha_form_ctx(
            request,
            usuario,
            titulo="Nova campanha",
            valores={"canal": "meta", "status": "ativa"},
        ),
    )


@router.post("/app/campanhas/nova")
async def campanhas_nova_post(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)
    dados = campanha_payload_form(form)
    erros = validar_campanha_payload(dados)
    if erros:
        return templates.TemplateResponse(
            "campanhas/form.html",
            _campanha_form_ctx(
                request, usuario, titulo="Nova campanha", valores=dados, erro="; ".join(erros)
            ),
            status_code=422,
        )
    norm = normalizar_utm(dados["utm_campaign"])
    if campanha_por_utm(db, usuario.loja_slug, norm):
        return templates.TemplateResponse(
            "campanhas/form.html",
            _campanha_form_ctx(
                request,
                usuario,
                titulo="Nova campanha",
                valores=dados,
                erro="Já existe uma campanha com este utm_campaign nesta loja.",
            ),
            status_code=422,
        )
    c = Campanha(
        id=novo_id(),
        loja_slug=usuario.loja_slug,
        utm_campaign=dados["utm_campaign"].strip(),
        utm_campaign_norm=norm or "",
        criada_por_email=usuario.email,
    )
    preencher_campanha(c, dados, email=usuario.email)
    db.add(c)
    db.commit()
    return RedirectResponse("/app/campanhas?ok=criada", status_code=303)


def _gastos_lote_contexto(
    request: Request,
    usuario,
    db: Session,
    *,
    erro: str | None = None,
    relatorio: dict | None = None,
):
    from app.financeiro_calc import hoje_portal

    campanhas = (
        db.query(Campanha)
        .filter(Campanha.loja_slug == usuario.loja_slug, Campanha.status == "ativa")
        .order_by(Campanha.nome)
        .all()
    )
    return contexto(
        request,
        usuario,
        campanhas=campanhas,
        hoje=hoje_portal().isoformat(),
        canais=CANAIS_ROTULO,
        erro=erro,
        relatorio=relatorio,
    )


@router.get("/app/campanhas/gastos/lote", response_class=HTMLResponse)
def campanhas_gastos_lote_get(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_trafego(usuario):
        return RedirectResponse("/app", status_code=303)
    return templates.TemplateResponse(
        "campanhas/gastos_lote.html",
        _gastos_lote_contexto(request, usuario, db),
    )


@router.post("/app/campanhas/gastos/lote")
async def campanhas_gastos_lote_post(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)
    try:
        referencia = date.fromisoformat((form.get("referencia") or "").strip())
    except ValueError:
        referencia = None
    if referencia is None:
        return templates.TemplateResponse(
            "campanhas/gastos_lote.html",
            _gastos_lote_contexto(request, usuario, db, erro="Informe uma data de referência válida."),
            status_code=422,
        )
    campanhas = db.query(Campanha).filter(
        Campanha.loja_slug == usuario.loja_slug,
        Campanha.status == "ativa",
    ).all()
    nota_global = (form.get("nota_global") or "").strip()[:240] or None
    novos: list[tuple[Campanha, Decimal, str | None]] = []
    for campanha in campanhas:
        texto_valor = (form.get(f"valor_{campanha.id}") or "").strip()
        if not texto_valor:
            continue
        valor = parse_brl_valor(texto_valor)
        if valor is None or valor <= 0:
            return templates.TemplateResponse(
                "campanhas/gastos_lote.html",
                _gastos_lote_contexto(
                    request,
                    usuario,
                    db,
                    erro=f"Informe um valor maior que zero para {campanha.nome}.",
                ),
                status_code=422,
            )
        nota = (form.get(f"nota_{campanha.id}") or "").strip()[:240] or nota_global
        novos.append((campanha, valor, nota))
    for campanha, valor, nota in novos:
        salvar_gasto_manual(
            db,
            campanha=campanha,
            loja_slug=usuario.loja_slug,
            valor=valor,
            referencia=referencia,
            nota=nota,
            criada_por=usuario.email,
        )
    db.commit()
    return RedirectResponse(f"/app/campanhas/gastos/lote?ok={len(novos)}", status_code=303)


@router.get("/app/campanhas/gastos/csv/modelo")
def campanhas_gastos_csv_modelo(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_trafego(usuario):
        return RedirectResponse("/app", status_code=303)
    conteudo = "\ufeffutm_campaign;valor;referencia;nota\n"
    return Response(
        content=conteudo,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="modelo-gastos-revy.csv"'},
    )


@router.post("/app/campanhas/gastos/csv", response_class=HTMLResponse)
async def campanhas_gastos_csv_post(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)
    arquivo = form.get("arquivo")
    if arquivo is None or not hasattr(arquivo, "read"):
        return templates.TemplateResponse(
            "campanhas/gastos_lote.html",
            _gastos_lote_contexto(request, usuario, db, erro="Selecione um arquivo CSV."),
            status_code=422,
        )
    conteudo = await arquivo.read()
    if len(conteudo) > 1024 * 1024:
        return templates.TemplateResponse(
            "campanhas/gastos_lote.html",
            _gastos_lote_contexto(request, usuario, db, erro="O CSV deve ter no máximo 1 MB."),
            status_code=413,
        )
    campanhas = db.query(Campanha).filter(Campanha.loja_slug == usuario.loja_slug).all()
    linhas, erros = parse_gastos_csv(conteudo, campanhas)
    for linha in linhas:
        salvar_gasto_manual(
            db,
            campanha=linha.campanha,
            loja_slug=usuario.loja_slug,
            valor=linha.valor,
            referencia=linha.referencia,
            nota=linha.nota,
            criada_por=usuario.email,
        )
    db.commit()
    return templates.TemplateResponse(
        "campanhas/gastos_lote.html",
        _gastos_lote_contexto(
            request,
            usuario,
            db,
            relatorio={"importados": len(linhas), "erros": erros},
        ),
    )


@router.get("/app/campanhas/{campanha_id}", response_class=HTMLResponse)
def campanhas_detalhe(
    request: Request,
    campanha_id: str,
    inicio: str | None = None,
    fim: str | None = None,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_trafego(usuario):
        return RedirectResponse("/app", status_code=303)
    campanha = (
        db.query(Campanha)
        .filter(Campanha.id == campanha_id, Campanha.loja_slug == usuario.loja_slug)
        .first()
    )
    if not campanha:
        return RedirectResponse("/app/campanhas?erro=1", status_code=303)
    gastos = (
        db.query(CampanhaGasto)
        .filter(
            CampanhaGasto.campanha_id == campanha.id,
            CampanhaGasto.loja_slug == usuario.loja_slug,
        )
        .order_by(CampanhaGasto.referencia.desc(), CampanhaGasto.criada_em.desc())
        .all()
    )
    gasto_total = sum((g.valor for g in gastos), Decimal("0"))
    d_inicio, d_fim = periodo_padrao(inicio, fim)
    metricas_vendas = calcular_metricas_vendas(db, usuario.loja_slug, d_inicio, d_fim)
    leads: list[dict] = []
    chatbot_erro = False
    try:
        leads = chatbot.listar_leads()
    except ChatbotIndisponivel:
        chatbot_erro = True
    linha_roi = next(
        linha
        for linha in calcular_roi_loja(
            campanhas=[campanha],
            gastos=gastos,
            leads=leads,
            vendas_confirmadas=metricas_vendas["confirmadas"],
            d_inicio=d_inicio,
            d_fim=d_fim,
            modo_atribuicao="last",
        )
        if linha.campanha_id == campanha.id
    )
    vendas_atribuidas = [
        venda
        for venda in metricas_vendas["confirmadas"]
        if venda_casa_campanha(venda, campanha, modo="last")
    ]
    from app.financeiro_calc import hoje_portal

    return templates.TemplateResponse(
        "campanhas/detalhe.html",
        contexto(
            request,
            usuario,
            campanha=campanha,
            gastos=gastos,
            gasto_total=gasto_total,
            canais=CANAIS_ROTULO,
            status_rotulo=STATUS_ROTULO,
            periodo={"inicio": d_inicio.isoformat(), "fim": d_fim.isoformat()},
            linha_roi=linha_roi,
            vendas_atribuidas=sorted(
                vendas_atribuidas,
                key=lambda venda: venda.confirmada_em or venda.criada_em,
                reverse=True,
            )[:10],
            chatbot_erro=chatbot_erro,
            hoje=hoje_portal().isoformat(),
            erro=request.query_params.get("erro"),
        ),
    )


@router.get("/app/campanhas/{campanha_id}/editar", response_class=HTMLResponse)
def campanhas_editar_get(request: Request, campanha_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_trafego(usuario):
        return RedirectResponse("/app", status_code=303)
    campanha = (
        db.query(Campanha)
        .filter(Campanha.id == campanha_id, Campanha.loja_slug == usuario.loja_slug)
        .first()
    )
    if not campanha:
        return RedirectResponse("/app/campanhas?erro=1", status_code=303)
    valores = {
        "nome": campanha.nome,
        "canal": campanha.canal,
        "status": campanha.status,
        "utm_source": campanha.utm_source or "",
        "utm_medium": campanha.utm_medium or "",
        "utm_campaign": campanha.utm_campaign,
        "utm_content": campanha.utm_content or "",
        "utm_term": campanha.utm_term or "",
        "meta_campaign_id": campanha.meta_campaign_id or "",
        "codigo_ctwa": campanha.codigo_ctwa or "",
        "periodo_inicio": campanha.periodo_inicio.isoformat() if campanha.periodo_inicio else "",
        "periodo_fim": campanha.periodo_fim.isoformat() if campanha.periodo_fim else "",
        "notas": campanha.notas or "",
    }
    return templates.TemplateResponse(
        "campanhas/form.html",
        _campanha_form_ctx(request, usuario, titulo="Editar campanha", valores=valores),
    )


@router.post("/app/campanhas/{campanha_id}/editar")
async def campanhas_editar_post(request: Request, campanha_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)
    campanha = (
        db.query(Campanha)
        .filter(Campanha.id == campanha_id, Campanha.loja_slug == usuario.loja_slug)
        .first()
    )
    if not campanha:
        return RedirectResponse("/app/campanhas?erro=1", status_code=303)
    dados = campanha_payload_form(form)
    erros = validar_campanha_payload(dados)
    if erros:
        return templates.TemplateResponse(
            "campanhas/form.html",
            _campanha_form_ctx(
                request, usuario, titulo="Editar campanha", valores=dados, erro="; ".join(erros)
            ),
            status_code=422,
        )
    norm = normalizar_utm(dados["utm_campaign"])
    outra = campanha_por_utm(db, usuario.loja_slug, norm)
    if outra and outra.id != campanha.id:
        return templates.TemplateResponse(
            "campanhas/form.html",
            _campanha_form_ctx(
                request,
                usuario,
                titulo="Editar campanha",
                valores=dados,
                erro="Já existe uma campanha com este utm_campaign nesta loja.",
            ),
            status_code=422,
        )
    preencher_campanha(campanha, dados)
    db.commit()
    return RedirectResponse(f"/app/campanhas/{campanha.id}?ok=salvo", status_code=303)


@router.post("/app/campanhas/{campanha_id}/apagar")
async def campanhas_apagar_post(request: Request, campanha_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)
    campanha = (
        db.query(Campanha)
        .filter(Campanha.id == campanha_id, Campanha.loja_slug == usuario.loja_slug)
        .first()
    )
    if not campanha:
        return RedirectResponse("/app/campanhas?erro=1", status_code=303)
    db.delete(campanha)
    db.commit()
    return RedirectResponse("/app/campanhas?ok=apagada", status_code=303)


@router.post("/app/campanhas/{campanha_id}/gastos")
async def campanhas_gasto_post(request: Request, campanha_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)
    campanha = (
        db.query(Campanha)
        .filter(Campanha.id == campanha_id, Campanha.loja_slug == usuario.loja_slug)
        .first()
    )
    if not campanha:
        return RedirectResponse("/app/campanhas?erro=1", status_code=303)
    valor = parse_brl_valor(form.get("valor"))
    try:
        referencia = date.fromisoformat((form.get("referencia") or "").strip())
    except ValueError:
        referencia = None
    if valor is None or referencia is None:
        return RedirectResponse(
            f"/app/campanhas/{campanha.id}?erro=Informe+valor+e+data+válidos",
            status_code=303,
        )
    salvar_gasto_manual(
        db,
        campanha=campanha,
        loja_slug=usuario.loja_slug,
        valor=valor,
        referencia=referencia,
        nota=(form.get("nota") or "").strip() or None,
        criada_por=usuario.email,
    )
    db.commit()
    return RedirectResponse(f"/app/campanhas/{campanha.id}?ok=gasto", status_code=303)


@router.get("/app/trafego/roi", response_class=HTMLResponse)
def trafego_roi(
    request: Request,
    inicio: str | None = None,
    fim: str | None = None,
    touch: str | None = None,
    db: Session = Depends(get_db),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_trafego(usuario):
        return RedirectResponse("/app", status_code=303)
    d_inicio, d_fim = periodo_padrao(inicio, fim)
    modo = touch if touch in ("first", "last") else "last"
    campanhas = (
        db.query(Campanha).filter(Campanha.loja_slug == usuario.loja_slug).all()
    )
    gastos = (
        db.query(CampanhaGasto).filter(CampanhaGasto.loja_slug == usuario.loja_slug).all()
    )
    metricas = calcular_metricas_vendas(db, usuario.loja_slug, d_inicio, d_fim)
    chatbot_erro = None
    leads: list[dict] = []
    try:
        leads = get_chatbot_client().listar_leads()
    except ChatbotIndisponivel:
        chatbot_erro = "indisponivel"
    linhas = calcular_roi_loja(
        campanhas=campanhas,
        gastos=gastos,
        leads=leads,
        vendas_confirmadas=metricas["confirmadas"],
        d_inicio=d_inicio,
        d_fim=d_fim,
        modo_atribuicao=modo,
    )
    totais = totais_roi(linhas)
    return templates.TemplateResponse(
        "trafego/roi.html",
        contexto(
            request,
            usuario,
            periodo={"inicio": d_inicio.isoformat(), "fim": d_fim.isoformat()},
            touch=modo,
            linhas=linhas,
            totais=totais,
            insights=gerar_insights_roi(linhas, totais),
            canais=CANAIS_ROTULO,
            chatbot_erro=chatbot_erro,
            totais_roas_barra=(
                min(100.0, float(totais["roas"]) / 5.0 * 100.0) if totais.get("roas") else 0.0
            ),
        ),
    )


@router.get("/app/trafego/pixel-auditoria", response_class=HTMLResponse)
def trafego_pixel_auditoria(
    request: Request,
    db: Session = Depends(get_db),
    origem: str | None = None,
):
    """Auditoria de chaves Pixel/CAPI (Event Match Quality flags)."""
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_trafego(usuario):
        return RedirectResponse("/app", status_code=303)
    from app.pixel_capi_auditoria import listar_auditoria_pixel

    origem_filtro = (origem or "").strip() or None
    itens = listar_auditoria_pixel(
        db, usuario.loja_slug, limit=100, origem=origem_filtro
    )
    return templates.TemplateResponse(
        "trafego/pixel_auditoria.html",
        contexto(
            request,
            usuario,
            itens=itens,
            origem_filtro=origem_filtro or "",
        ),
    )


@router.get("/app/trafego/ctwa-auditoria", response_class=HTMLResponse)
def trafego_ctwa_auditoria(
    request: Request,
    db: Session = Depends(get_db),
    so_com_clid: str | None = None,
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    """Auditoria de sinais CTWA recebidos no webhook (via Chatbot API)."""
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_trafego(usuario):
        return RedirectResponse("/app", status_code=303)
    filtro_clid = (so_com_clid or "").strip() in {"1", "true", "on", "sim"}
    itens: list = []
    erro_chatbot = None
    try:
        dados = chatbot.listar_auditoria_ctwa(limit=80, so_com_clid=filtro_clid)
        itens = dados.get("itens") or []
    except ChatbotIndisponivel:
        erro_chatbot = "Chatbot indisponível — não foi possível carregar a auditoria CTWA."
    return templates.TemplateResponse(
        "trafego/ctwa_auditoria.html",
        contexto(
            request,
            usuario,
            itens=itens,
            so_com_clid=filtro_clid,
            erro_chatbot=erro_chatbot,
        ),
    )


@router.get("/app/trafego", response_class=HTMLResponse)
def trafego_pagina(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_trafego(usuario):
        return RedirectResponse("/app", status_code=303)
    config = (
        db.query(MetaPixelConfig)
        .filter(MetaPixelConfig.loja_slug == usuario.loja_slug)
        .first()
    )
    ads_config = (
        db.query(MetaAdsConfig)
        .filter(MetaAdsConfig.loja_slug == usuario.loja_slug)
        .first()
    )
    ok = request.query_params.get("ok")
    outboxes = (
        db.query(MetaCapiOutbox)
        .filter(MetaCapiOutbox.loja_slug == usuario.loja_slug)
        .order_by(MetaCapiOutbox.criada_em.desc())
        .all()
    )
    return templates.TemplateResponse(
        "trafego/form.html",
        _trafego_contexto(
            request,
            usuario,
            config,
            ads_config=ads_config,
            ultimo_outbox=outboxes[0] if outboxes else None,
            pendentes=sum(o.status in {"pending", "failed"} for o in outboxes),
            ok=ok,
            sync_resumo=request.query_params.get("sync"),
        ),
    )


@router.post("/app/trafego/capi/retentar")
async def trafego_capi_retentar(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)
    resultado = processar_outbox_pendentes(db, usuario.loja_slug)
    return RedirectResponse(
        f"/app/trafego?ok=retry-{resultado['entregues']}-{resultado['falharam']}",
        status_code=303,
    )


@router.post("/app/trafego/onboarding/dispensar")
async def trafego_onboarding_dispensar(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)
    config = db.query(MetaPixelConfig).filter(
        MetaPixelConfig.loja_slug == usuario.loja_slug
    ).first()
    if config is None:
        config = MetaPixelConfig(loja_slug=usuario.loja_slug, pixel_id="")
        db.add(config)
    config.medicao_onboarding_dismiss_em = agora()
    db.commit()
    return RedirectResponse("/app?ok=onboarding-dispensado", status_code=303)


@router.post("/app/trafego/ads/salvar")
async def trafego_ads_salvar(request: Request, db: Session = Depends(get_db)):
    """Salva conta de anúncios Meta (Marketing API / spend) — separado do CAPI."""
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)

    ads_config = (
        db.query(MetaAdsConfig)
        .filter(MetaAdsConfig.loja_slug == usuario.loja_slug)
        .first()
    )
    config = (
        db.query(MetaPixelConfig)
        .filter(MetaPixelConfig.loja_slug == usuario.loja_slug)
        .first()
    )
    account = normalizar_ad_account_id(form.get("ad_account_id"))
    token_novo = (form.get("ads_token") or "").strip()
    sync_enabled = form.get("ads_sync_enabled") == "on"

    if not account:
        return templates.TemplateResponse(
            "trafego/form.html",
            _trafego_contexto(
                request,
                usuario,
                config,
                ads_config=ads_config,
                erro="Informe o ID da conta de anúncios Meta (act_… ou só números).",
            ),
            status_code=422,
        )
    if not token_novo and not (ads_config and ads_config.token_ciphertext):
        return templates.TemplateResponse(
            "trafego/form.html",
            _trafego_contexto(
                request,
                usuario,
                config,
                ads_config=ads_config,
                erro="Informe o token com permissão ads_read (Marketing API).",
            ),
            status_code=422,
        )

    if ads_config is None:
        ads_config = MetaAdsConfig(loja_slug=usuario.loja_slug, ad_account_id=account)
        db.add(ads_config)
    ads_config.ad_account_id = account
    ads_config.sync_enabled = sync_enabled
    if token_novo:
        ads_config.token_ciphertext = cifrar(token_novo)
    ads_config.atualizada_em = agora()
    db.commit()
    return RedirectResponse("/app/trafego?ok=ads-salvo", status_code=303)


@router.post("/app/trafego/ads/sincronizar")
async def trafego_ads_sincronizar(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)
    result = main_module.sincronizar_gastos_meta(db, usuario.loja_slug, janela_dias=7)
    if result.status == "erro":
        return RedirectResponse("/app/trafego?ok=sync-erro", status_code=303)
    return RedirectResponse("/app/trafego?ok=sync-ok", status_code=303)


@router.post("/internal/v1/provisioning/state")
def receber_estado_provisionamento(
    payload: dict,
    db: Session = Depends(get_db),
    x_service_token: str = Header(default="", alias="X-Service-Token"),
):
    """Recebe snapshot operacional do Control e aplica projeção monotônica local.

    Autentica com ``X-Service-Token`` vs ``PORTAL_SERVICE_TOKEN`` (ou
    ``PORTAL_PROVISIONING_TOKEN``). Token vazio → 503; incorreto → 401.
    Multi-tenant por ``loja_slug`` no body (sem sessão de usuário).
    """
    esperado = (
        os.getenv("PORTAL_SERVICE_TOKEN")
        or os.getenv("PORTAL_PROVISIONING_TOKEN")
        or ""
    ).strip()
    if not esperado:
        return JSONResponse(
            {
                "detail": (
                    "provisioning desabilitado "
                    "(PORTAL_SERVICE_TOKEN / PORTAL_PROVISIONING_TOKEN vazio)"
                )
            },
            status_code=503,
        )
    if not secrets.compare_digest(x_service_token or "", esperado):
        return JSONResponse({"detail": "não autorizado"}, status_code=401)

    loja_slug = str(payload.get("loja_slug") or "").strip()
    if not loja_slug:
        return JSONResponse({"detail": "loja_slug obrigatório"}, status_code=422)

    reasons = provisioning.apply_payload(db, loja_slug, payload)
    db.commit()
    return {
        "ok": True,
        "reasons": reasons,
        "allows_processing": provisioning.allows_processing(db, loja_slug),
    }


@router.post("/internal/jobs/meta-spend-sync")
def job_meta_spend_sync(
    x_job_token: str = Header(default="", alias="X-Job-Token"),
):
    """Dispara sync de todas as lojas (cron externo ou health-ops).

    Autentica com ``PORTAL_META_SPEND_JOB_SECRET``. Se o segredo estiver vazio,
    o endpoint responde 503 (desligado de propósito).
    """
    esperado = (os.getenv("PORTAL_META_SPEND_JOB_SECRET") or "").strip()
    if not esperado:
        return JSONResponse(
            {"detail": "job desabilitado (PORTAL_META_SPEND_JOB_SECRET vazio)"},
            status_code=503,
        )
    if not secrets.compare_digest(x_job_token or "", esperado):
        return JSONResponse({"detail": "não autorizado"}, status_code=401)

    worker = meta_ads_spend_job.get_worker()
    if worker is None:
        # Processo sem lifespan worker (ex.: testes) — executa uma vez direto.
        janela = int(os.getenv("PORTAL_META_SPEND_SYNC_JANELA_DIAS", "3") or "3")
        runner = meta_ads_spend_job.MetaSpendSyncWorker(
            db_factory=SessionLocal,
            enabled=True,
            interval_seconds=86400,
            initial_delay_seconds=0,
            janela_dias=janela,
        )
        payload = runner.run_once()
    else:
        payload = worker.run_once()
    return JSONResponse(payload)


@router.post("/app/trafego")
async def trafego_salvar(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)

    pixel_id_informado = (form.get("pixel_id") or "").strip()
    pixel_id = normalizar_pixel_id(pixel_id_informado)
    token_novo = (form.get("capi_token") or "").strip()
    test_event_code = (form.get("test_event_code") or "").strip() or None
    enviar_page_view = form.get("enviar_page_view") == "on"
    enviar_lead = form.get("enviar_lead") == "on"
    enviar_purchase = form.get("enviar_purchase") == "on"

    config = (
        db.query(MetaPixelConfig)
        .filter(MetaPixelConfig.loja_slug == usuario.loja_slug)
        .first()
    )
    ads_config = (
        db.query(MetaAdsConfig)
        .filter(MetaAdsConfig.loja_slug == usuario.loja_slug)
        .first()
    )
    if not pixel_id:
        return templates.TemplateResponse(
            "trafego/form.html",
            _trafego_contexto(
                request,
                usuario,
                config,
                ads_config=ads_config,
                erro="Informe um Pixel ID válido, contendo somente números.",
            ),
            status_code=422,
        )
    if not token_novo and not (config and config.token_ciphertext):
        return templates.TemplateResponse(
            "trafego/form.html",
            _trafego_contexto(
                request,
                usuario,
                config,
                ads_config=ads_config,
                erro="Informe o token de acesso da Conversions API (CAPI).",
            ),
            status_code=422,
        )

    if config is None:
        config = MetaPixelConfig(loja_slug=usuario.loja_slug, pixel_id=pixel_id)
        db.add(config)

    config.pixel_id = pixel_id
    config.test_event_code = test_event_code
    config.enviar_page_view = enviar_page_view
    config.enviar_lead = enviar_lead
    config.enviar_purchase = enviar_purchase
    config.atualizada_em = agora()
    if token_novo:
        config.token_ciphertext = cifrar(token_novo)
    try:
        from app.pixel_capi_auditoria import registrar_auditoria_pixel

        registrar_auditoria_pixel(
            db,
            loja_slug=usuario.loja_slug,
            origem="config_salva",
            pixel_id=pixel_id,
            modo="config",
            tem_test_event_code=bool(test_event_code),
            enviar_page_view=enviar_page_view,
            enviar_lead=enviar_lead,
            enviar_purchase=enviar_purchase,
            status="ok",
            detalhe="token_atualizado" if token_novo else "token_mantido",
        )
    except Exception:
        pass
    db.commit()
    return RedirectResponse("/app/trafego?ok=salvo", status_code=303)
