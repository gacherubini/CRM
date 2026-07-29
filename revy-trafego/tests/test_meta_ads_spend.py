"""Cobertura do spend Meta Ads no revy-trafego.

Portado de ``portal-gestao/tests/test_meta_ads_spend.py`` e adaptado ao
idioma do revy-trafego (auth por ``GestorRevy`` + seleção de loja via
``POST /app/loja``).

Nunca faz rede: todo ``fetch`` é fake e ``fetch_campaign_insights`` roda
sobre ``httpx.MockTransport``. O worker de background fica desligado
(``REVY_TRAFEGO_SKIP_INIT=1`` + ``REVY_TRAFEGO_META_SPEND_SYNC_ENABLED=0``
no conftest), então nenhum teste aqui pode iniciar thread.
"""
from datetime import date
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.exc import IntegrityError

from app.cripto import cifrar
from app.db import SessionLocal
from app.meta_ads_spend import (
    SyncAllResult,
    SyncResult,
    external_key_meta,
    fetch_campaign_insights,
    listar_lojas_para_sync,
    normalizar_ad_account_id,
    normalizar_meta_campaign_id,
    parse_spend,
    sincronizar_gastos_meta,
    sincronizar_todas_lojas,
)
from app.models import Campanha, CampanhaGasto, MetaAdsConfig, agora, novo_id
from tests.conftest import csrf_da_resposta

LOJA = "loja-teste"


# ---------- helpers locais (nada é adicionado ao conftest compartilhado) ----------


def _selecionar_loja(client, slug: str = LOJA):
    """revy-trafego exige loja na sessão (``exigir_loja``) antes de /app/trafego."""
    home = client.get("/app")
    assert home.status_code == 200
    r = client.post(
        "/app/loja",
        data={"loja_slug": slug, "csrf": csrf_da_resposta(home)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    return client


def _campanha(loja_slug: str = LOJA, **kwargs) -> Campanha:
    base = dict(
        id=novo_id(),
        loja_slug=loja_slug,
        nome="Meta Sync",
        canal="meta",
        status="ativa",
        utm_campaign="sync-test",
        utm_campaign_norm="sync-test",
        meta_campaign_id="111",
        criada_por_email="gestor@revy.local",
    )
    base.update(kwargs)
    return Campanha(**base)


def _ads_config(loja_slug: str = LOJA, **kwargs) -> MetaAdsConfig:
    base = dict(
        loja_slug=loja_slug,
        ad_account_id="act_1",
        token_ciphertext=cifrar("token-ads"),
        sync_enabled=True,
        atualizada_em=agora(),
    )
    base.update(kwargs)
    return MetaAdsConfig(**base)


# ---------- puros ----------


def test_normalizar_ad_account_e_spend():
    assert normalizar_ad_account_id("123456") == "act_123456"
    assert normalizar_ad_account_id("act_99") == "act_99"
    assert normalizar_ad_account_id("  act_12-34  ") == "act_1234"
    assert normalizar_ad_account_id("") == ""
    assert normalizar_ad_account_id(None) == ""
    assert normalizar_ad_account_id("act_") == ""
    assert parse_spend("12.50") == Decimal("12.50")
    assert parse_spend("12.345") == Decimal("12.35")  # ROUND_HALF_UP
    assert parse_spend("-1") is None
    assert parse_spend(None) is None
    assert parse_spend("abc") is None


def test_normalizar_meta_campaign_id_e_external_key():
    assert normalizar_meta_campaign_id("120339") == "120339"
    assert normalizar_meta_campaign_id(" 12-03 ") == "1203"
    assert normalizar_meta_campaign_id("") is None
    assert normalizar_meta_campaign_id(None) is None
    assert normalizar_meta_campaign_id("abc") is None
    assert external_key_meta(LOJA, "111", date(2026, 7, 20)) == (
        "meta:loja-teste:111:2026-07-20"
    )


# ---------- fetch (sem rede real) ----------


def test_fetch_campaign_insights_pagina_e_agrega():
    paginas = {
        "/v21.0/act_1234/insights": {
            "data": [{"campaign_id": "1", "spend": "10.00", "date_start": "2026-07-20"}],
            "paging": {"next": "https://graph.facebook.com/v21.0/next-page?after=abc"},
        },
        "/v21.0/next-page": {
            "data": [{"campaign_id": "2", "spend": "20.00", "date_start": "2026-07-20"}],
            "paging": {},
        },
    }
    vistos = []

    def handler(request: httpx.Request) -> httpx.Response:
        vistos.append(request.url)
        return httpx.Response(200, json=paginas[request.url.path])

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        rows = fetch_campaign_insights(
            ad_account_id="1234",
            access_token="tok-secreto",
            since=date(2026, 7, 20),
            until=date(2026, 7, 20),
            client=http,
        )

    assert [r["campaign_id"] for r in rows] == ["1", "2"]
    assert len(vistos) == 2
    # token vai só na 1ª chamada; o "next" já carrega a query string da Meta
    assert "access_token=tok-secreto" in str(vistos[0])
    assert "access_token" not in str(vistos[1])


def test_fetch_campaign_insights_valida_argumentos():
    with pytest.raises(ValueError):
        fetch_campaign_insights(
            ad_account_id="",
            access_token="t",
            since=date(2026, 7, 1),
            until=date(2026, 7, 2),
        )
    with pytest.raises(ValueError):
        fetch_campaign_insights(
            ad_account_id="123",
            access_token="t",
            since=date(2026, 7, 5),
            until=date(2026, 7, 1),
        )


# ---------- sincronização por loja ----------


def test_sincronizar_importa_atualiza_e_orfa():
    db = SessionLocal()
    campanha = _campanha()
    db.add(campanha)
    db.add(_ads_config())
    db.commit()
    campanha_id = campanha.id
    db.close()

    rows = [
        {
            "campaign_id": "111",
            "spend": "100.00",
            "date_start": "2026-07-20",
            "date_stop": "2026-07-20",
        },
        {
            "campaign_id": "999",
            "spend": "50.00",
            "date_start": "2026-07-20",
            "date_stop": "2026-07-20",
        },
    ]

    def fake_fetch(**kwargs):
        return rows

    db = SessionLocal()
    r1 = sincronizar_gastos_meta(
        db,
        LOJA,
        since=date(2026, 7, 20),
        until=date(2026, 7, 20),
        fetch=fake_fetch,
    )
    assert r1.imported == 1
    assert r1.orphans == 1
    assert r1.orphan_ids == ["999"]
    assert r1.status in {"ok", "partial"}
    gastos = db.query(CampanhaGasto).filter(CampanhaGasto.campanha_id == campanha_id).all()
    assert len(gastos) == 1
    assert gastos[0].origem == "meta_api"
    assert gastos[0].valor == Decimal("100.00")
    assert gastos[0].external_key == external_key_meta(LOJA, "111", date(2026, 7, 20))
    assert gastos[0].criada_por == "meta_api"
    db.close()

    rows[0]["spend"] = "120.50"
    db = SessionLocal()
    r2 = sincronizar_gastos_meta(
        db,
        LOJA,
        since=date(2026, 7, 20),
        until=date(2026, 7, 20),
        fetch=fake_fetch,
    )
    assert r2.imported == 0
    assert r2.updated == 1
    g = db.query(CampanhaGasto).filter(CampanhaGasto.campanha_id == campanha_id).one()
    assert g.valor == Decimal("120.50")
    db.close()

    # 3ª rodada com o mesmo valor: no-op silencioso (idempotente)
    db = SessionLocal()
    r3 = sincronizar_gastos_meta(
        db,
        LOJA,
        since=date(2026, 7, 20),
        until=date(2026, 7, 20),
        fetch=fake_fetch,
    )
    assert (r3.imported, r3.updated) == (0, 0)
    assert db.query(CampanhaGasto).filter(CampanhaGasto.campanha_id == campanha_id).count() == 1
    db.close()


def test_sincronizar_ignora_linhas_invalidas():
    db = SessionLocal()
    campanha = _campanha()
    db.add(campanha)
    db.add(_ads_config())
    db.commit()
    campanha_id = campanha.id
    db.close()

    def fake_fetch(**kwargs):
        return [
            {"campaign_id": "", "spend": "10.00", "date_start": "2026-07-20"},
            {"campaign_id": "111", "spend": None, "date_start": "2026-07-20"},
            {"campaign_id": "111", "spend": "-5.00", "date_start": "2026-07-20"},
            {"campaign_id": "111", "spend": "0", "date_start": "2026-07-20"},
            {"campaign_id": "111", "spend": "10.00", "date_start": "nao-e-data"},
        ]

    db = SessionLocal()
    r = sincronizar_gastos_meta(db, LOJA, fetch=fake_fetch)
    assert r.imported == 0
    assert r.orphans == 0
    assert r.errors == []
    assert db.query(CampanhaGasto).filter(CampanhaGasto.campanha_id == campanha_id).count() == 0
    db.close()


def test_linhas_duplicadas_no_mesmo_batch_consolidam_ultima_linha():
    """Mesma campanha+dia repetida no batch vira UMA linha, com o último valor.

    A dedupe contra o banco não bastava: ``SessionLocal`` usa ``autoflush=False``
    (``app/db.py:14``), então o ``db.add()`` da linha anterior seguia pendente e
    o commit estourava ``UNIQUE(external_key)`` (``app/models.py:206``).
    A consolidação é por substituição (última prevalece), nunca soma — a Meta
    já manda o total do dia, somar inflaria o gasto e distorceria o ROI.
    """
    db = SessionLocal()
    db.add(_campanha())
    db.add(_ads_config())
    db.commit()
    db.close()

    def linha(spend: str) -> dict:
        return {
            "campaign_id": "111",
            "spend": spend,
            "date_start": "2026-07-20",
            "date_stop": "2026-07-20",
        }

    def fake_fetch(**kwargs):
        # paginação da Graph API pode repetir a mesma campanha+dia entre páginas,
        # às vezes com o valor já corrigido na 2ª ocorrência
        return [linha("10.00"), linha("12.50")]

    db = SessionLocal()
    try:
        r = sincronizar_gastos_meta(
            db,
            LOJA,
            since=date(2026, 7, 20),
            until=date(2026, 7, 20),
            fetch=fake_fetch,
        )
        assert r.imported == 1
        assert r.updated == 0
        assert r.errors == []
        assert r.status == "ok"
    finally:
        db.close()

    key = external_key_meta(LOJA, "111", date(2026, 7, 20))
    db = SessionLocal()
    try:
        gastos = db.query(CampanhaGasto).filter(CampanhaGasto.external_key == key).all()
        assert len(gastos) == 1
        # última linha prevalece; jamais 22.50 (soma) nem 10.00 (primeira)
        assert gastos[0].valor == Decimal("12.50")
    finally:
        db.close()


def test_duplicata_no_batch_sobre_gasto_ja_existente_conta_um_update():
    """Duplicata sobre linha já persistida: 1 update, valor da última linha."""
    db = SessionLocal()
    db.add(_campanha())
    db.add(_ads_config())
    db.commit()
    db.close()

    valores = ["10.00"]

    def fake_fetch(**kwargs):
        return [
            {
                "campaign_id": "111",
                "spend": v,
                "date_start": "2026-07-20",
                "date_stop": "2026-07-20",
            }
            for v in valores
        ]

    db = SessionLocal()
    try:
        primeira = sincronizar_gastos_meta(
            db, LOJA, since=date(2026, 7, 20), until=date(2026, 7, 20), fetch=fake_fetch
        )
        assert primeira.imported == 1
    finally:
        db.close()

    valores = ["10.00", "33.00", "40.00"]
    db = SessionLocal()
    try:
        segunda = sincronizar_gastos_meta(
            db, LOJA, since=date(2026, 7, 20), until=date(2026, 7, 20), fetch=fake_fetch
        )
        assert segunda.imported == 0
        assert segunda.updated == 1  # uma linha física atualizada, não três
        assert segunda.status == "ok"
    finally:
        db.close()

    key = external_key_meta(LOJA, "111", date(2026, 7, 20))
    db = SessionLocal()
    try:
        g = db.query(CampanhaGasto).filter(CampanhaGasto.external_key == key).one()
        assert g.valor == Decimal("40.00")
    finally:
        db.close()


def test_duplicata_no_batch_com_gasto_manual_preserva_manual_uma_vez():
    db = SessionLocal()
    campanha = _campanha(meta_campaign_id="444", utm_campaign_norm="dup-manual")
    db.add(campanha)
    db.add(
        CampanhaGasto(
            id=novo_id(),
            campanha_id=campanha.id,
            loja_slug=LOJA,
            valor=Decimal("7.00"),
            referencia=date(2026, 7, 22),
            origem="manual",
            criada_por="gestor@revy.local",
        )
    )
    db.add(_ads_config())
    db.commit()
    cid = campanha.id
    db.close()

    def fake_fetch(**kwargs):
        return [
            {
                "campaign_id": "444",
                "spend": s,
                "date_start": "2026-07-22",
                "date_stop": "2026-07-22",
            }
            for s in ("50.00", "60.00")
        ]

    db = SessionLocal()
    try:
        r = sincronizar_gastos_meta(
            db, LOJA, since=date(2026, 7, 22), until=date(2026, 7, 22), fetch=fake_fetch
        )
        assert r.imported == 0
        assert r.skipped_manual == 1  # contabiliza a linha protegida uma única vez
    finally:
        db.close()

    db = SessionLocal()
    try:
        g = db.query(CampanhaGasto).filter(CampanhaGasto.campanha_id == cid).one()
        assert g.valor == Decimal("7.00")
        assert g.origem == "manual"
    finally:
        db.close()


def test_falha_ao_gravar_nao_escapa_para_o_chamador(monkeypatch):
    """Contrato do módulo: erro de persistência vira status ``erro``, não exceção."""
    db = SessionLocal()
    db.add(_campanha())
    db.add(_ads_config())
    db.commit()
    db.close()

    def fake_fetch(**kwargs):
        return [
            {
                "campaign_id": "111",
                "spend": "10.00",
                "date_start": "2026-07-20",
                "date_stop": "2026-07-20",
            }
        ]

    db = SessionLocal()
    try:
        def commit_explode():
            raise IntegrityError("INSERT INTO campanha_gastos", {}, Exception("uq"))

        monkeypatch.setattr(db, "commit", commit_explode)
        r = sincronizar_gastos_meta(
            db, LOJA, since=date(2026, 7, 20), until=date(2026, 7, 20), fetch=fake_fetch
        )
        assert r.status == "erro"
        assert r.imported == 0
        assert r.errors  # mensagem amigável, sem stacktrace
    finally:
        monkeypatch.undo()
        db.close()

    db = SessionLocal()
    try:
        assert db.query(CampanhaGasto).count() == 0
    finally:
        db.close()


def test_nao_sobrescreve_gasto_manual_mesmo_dia():
    db = SessionLocal()
    campanha = _campanha(
        nome="Manual Protect",
        utm_campaign="manual-protect",
        utm_campaign_norm="manual-protect",
        meta_campaign_id="222",
    )
    db.add(campanha)
    db.add(
        CampanhaGasto(
            id=novo_id(),
            campanha_id=campanha.id,
            loja_slug=LOJA,
            valor=Decimal("10.00"),
            referencia=date(2026, 7, 21),
            origem="manual",
            criada_por="gestor@revy.local",
        )
    )
    db.add(_ads_config())
    db.commit()
    cid = campanha.id
    db.close()

    def fake_fetch(**kwargs):
        return [
            {
                "campaign_id": "222",
                "spend": "99.00",
                "date_start": "2026-07-21",
                "date_stop": "2026-07-21",
            }
        ]

    db = SessionLocal()
    r = sincronizar_gastos_meta(
        db,
        LOJA,
        since=date(2026, 7, 21),
        until=date(2026, 7, 21),
        fetch=fake_fetch,
    )
    assert r.skipped_manual == 1
    assert r.imported == 0
    g = db.query(CampanhaGasto).filter(CampanhaGasto.campanha_id == cid).one()
    assert g.valor == Decimal("10.00")
    assert g.origem == "manual"
    db.close()


def test_sincronizar_sem_config_ou_desligada():
    db = SessionLocal()
    r_sem = sincronizar_gastos_meta(db, "loja-sem-config", fetch=lambda **k: [])
    assert r_sem.status == "erro"
    assert "Configure a conta de anúncios Meta" in r_sem.errors[0]
    db.close()

    db = SessionLocal()
    db.add(_ads_config(loja_slug="loja-off", sync_enabled=False))
    db.commit()
    db.close()

    db = SessionLocal()
    r_off = sincronizar_gastos_meta(db, "loja-off", fetch=lambda **k: [])
    assert r_off.status == "erro"
    assert "desligada" in r_off.errors[0]
    db.close()


def test_falha_da_api_e_sanitizada_e_persistida():
    db = SessionLocal()
    db.add(_campanha())
    db.add(_ads_config())
    db.commit()
    db.close()

    def fetch_explode(**kwargs):
        request = httpx.Request("GET", "https://graph.facebook.com/v21.0/act_1/insights")
        raise httpx.HTTPStatusError(
            "boom",
            request=request,
            response=httpx.Response(400, request=request),
        )

    db = SessionLocal()
    r = sincronizar_gastos_meta(db, LOJA, fetch=fetch_explode)
    assert r.status == "erro"
    assert r.errors == ["Meta Insights respondeu HTTP 400."]
    db.close()

    db = SessionLocal()
    cfg = db.query(MetaAdsConfig).filter(MetaAdsConfig.loja_slug == LOJA).one()
    assert cfg.ultima_sync_status == "erro"
    assert cfg.ultima_sync_erro == "Meta Insights respondeu HTTP 400."
    assert cfg.ultima_sync_em is not None
    db.close()


def test_falha_de_rede_nao_vaza_url_nem_token():
    db = SessionLocal()
    db.add(_ads_config())
    db.commit()
    db.close()

    def fetch_rede(**kwargs):
        raise httpx.ConnectError("dns falhou em graph.facebook.com?access_token=SEGREDO")

    db = SessionLocal()
    r = sincronizar_gastos_meta(db, LOJA, fetch=fetch_rede)
    db.close()
    assert r.status == "erro"
    assert r.errors == ["Falha de rede ao contatar a Meta Insights."]
    assert "SEGREDO" not in r.errors[0]


def test_token_ilegivel_vira_erro_amigavel():
    db = SessionLocal()
    db.add(_ads_config(token_ciphertext="nao-e-fernet"))
    db.commit()
    db.close()

    chamou = {"fetch": False}

    def fetch_nao_deve_rodar(**kwargs):
        chamou["fetch"] = True
        return []

    db = SessionLocal()
    r = sincronizar_gastos_meta(db, LOJA, fetch=fetch_nao_deve_rodar)
    db.close()
    assert r.status == "erro"
    assert "token" in r.errors[0].lower()
    assert chamou["fetch"] is False


def test_resumo_do_sync_result():
    r = SyncResult(imported=2, updated=1, orphans=3, skipped_manual=1, errors=["x"])
    texto = r.resumo()
    assert "2 novo(s)" in texto
    assert "1 atualizado(s)" in texto
    assert "3 sem campanha no Revy" in texto
    assert "1 manual preservado(s)" in texto
    assert "1 erro(s)" in texto
    assert len(texto) <= 240


# ---------- multi-loja (revy-trafego é multi-tenant) ----------


def test_listar_lojas_para_sync_filtra_desabilitadas():
    db = SessionLocal()
    db.add(_ads_config(loja_slug="loja-on"))
    db.add(_ads_config(loja_slug="loja-off", sync_enabled=False))
    db.add(_ads_config(loja_slug="loja-sem-token", token_ciphertext=None))
    db.add(_ads_config(loja_slug="loja-sem-conta", ad_account_id=""))
    db.commit()
    db.close()

    db = SessionLocal()
    try:
        assert listar_lojas_para_sync(db) == ["loja-on"]
    finally:
        db.close()


def test_sincronizar_todas_lojas_isola_falha_por_loja():
    db = SessionLocal()
    db.add(_ads_config(loja_slug="loja-a"))
    db.add(_ads_config(loja_slug="loja-b"))
    db.add(
        _campanha(
            loja_slug="loja-a",
            nome="Camp A",
            utm_campaign="camp-a",
            utm_campaign_norm="camp-a",
            meta_campaign_id="333",
        )
    )
    db.commit()
    db.close()

    def fake_fetch(*, ad_account_id, access_token, since, until):
        # a loja-b não tem campanha mapeada -> órfã; nenhuma explode a outra
        return [
            {
                "campaign_id": "333",
                "spend": "15.00",
                "date_start": since.isoformat(),
                "date_stop": until.isoformat(),
            }
        ]

    agg = sincronizar_todas_lojas(SessionLocal, janela_dias=1, fetch=fake_fetch)
    assert agg.lojas == 2
    assert agg.imported == 1
    assert agg.ok == 1
    assert agg.partial == 1
    assert {d["loja_slug"] for d in agg.details} == {"loja-a", "loja-b"}
    assert "2 loja(s)" in agg.resumo()

    db = SessionLocal()
    try:
        assert db.query(CampanhaGasto).filter(CampanhaGasto.loja_slug == "loja-a").count() == 1
        assert db.query(CampanhaGasto).filter(CampanhaGasto.loja_slug == "loja-b").count() == 0
    finally:
        db.close()


def test_sincronizar_todas_lojas_sem_lojas_habilitadas():
    agg = sincronizar_todas_lojas(SessionLocal, janela_dias=1, fetch=lambda **k: [])
    assert agg.lojas == 0
    assert agg.imported == 0
    assert isinstance(agg, SyncAllResult)


# ---------- UI /app/trafego ----------


def test_ui_salva_ads_e_sincroniza(client_logado, monkeypatch):
    client = _selecionar_loja(client_logado)
    pagina = client.get("/app/trafego")
    assert pagina.status_code == 200
    assert "Gasto automático" in pagina.text
    csrf = csrf_da_resposta(pagina)
    r = client.post(
        "/app/trafego/ads/salvar",
        data={
            "csrf": csrf,
            "ad_account_id": "act_555",
            "ads_token": "tok-xyz",
            "ads_sync_enabled": "on",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "ads-salvo" in r.headers["location"]

    db = SessionLocal()
    cfg = db.query(MetaAdsConfig).filter(MetaAdsConfig.loja_slug == LOJA).one()
    assert cfg.ad_account_id == "act_555"
    assert cfg.token_ciphertext
    assert cfg.token_ciphertext != "tok-xyz"  # cifrado em repouso
    assert cfg.sync_enabled is True
    db.close()

    called = {}

    def fake_sync(db, loja_slug, **kwargs):
        called["loja"] = loja_slug
        called["kwargs"] = kwargs
        return SyncResult(imported=2, status="ok")

    monkeypatch.setattr("app.main.sincronizar_gastos_meta", fake_sync)
    pagina2 = client.get("/app/trafego")
    r2 = client.post(
        "/app/trafego/ads/sincronizar",
        data={"csrf": csrf_da_resposta(pagina2)},
        follow_redirects=False,
    )
    assert r2.status_code == 303
    assert "sync-ok" in r2.headers["location"]
    assert called["loja"] == LOJA
    assert called["kwargs"]["janela_dias"] == 7


def test_ui_sincronizar_reporta_erro(client_logado, monkeypatch):
    client = _selecionar_loja(client_logado)
    monkeypatch.setattr(
        "app.main.sincronizar_gastos_meta",
        lambda db, loja_slug, **kw: SyncResult(status="erro", errors=["falhou"]),
    )
    pagina = client.get("/app/trafego")
    r = client.post(
        "/app/trafego/ads/sincronizar",
        data={"csrf": csrf_da_resposta(pagina)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "sync-erro" in r.headers["location"]


def test_ui_ads_salvar_exige_conta_e_token(client_logado):
    client = _selecionar_loja(client_logado)
    pagina = client.get("/app/trafego")
    csrf = csrf_da_resposta(pagina)

    sem_conta = client.post(
        "/app/trafego/ads/salvar",
        data={"csrf": csrf, "ad_account_id": "", "ads_token": "tok"},
        follow_redirects=False,
    )
    assert sem_conta.status_code == 422

    sem_token = client.post(
        "/app/trafego/ads/salvar",
        data={"csrf": csrf, "ad_account_id": "act_9", "ads_token": ""},
        follow_redirects=False,
    )
    assert sem_token.status_code == 422

    db = SessionLocal()
    try:
        assert db.query(MetaAdsConfig).filter(MetaAdsConfig.loja_slug == LOJA).first() is None
    finally:
        db.close()


def test_ui_ads_salvar_sem_loja_redireciona(client_logado):
    r = client_logado.post(
        "/app/trafego/ads/salvar",
        data={"csrf": "x", "ad_account_id": "act_9", "ads_token": "tok"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "erro=loja" in r.headers["location"]


def test_campanha_form_aceita_meta_campaign_id(client_logado):
    client = _selecionar_loja(client_logado)
    p = client.get("/app/campanhas/nova")
    assert p.status_code == 200
    r = client.post(
        "/app/campanhas/nova",
        data={
            "csrf": csrf_da_resposta(p),
            "nome": "Com Meta ID",
            "canal": "meta",
            "utm_campaign": "com-meta-id",
            "meta_campaign_id": "12033999888777",
            "status": "ativa",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    db = SessionLocal()
    try:
        c = db.query(Campanha).filter(Campanha.utm_campaign_norm == "com-meta-id").one()
        assert c.meta_campaign_id == "12033999888777"
        assert c.loja_slug == LOJA
    finally:
        db.close()


# ---------- worker / endpoint interno ----------


def test_worker_respeita_enabled_false():
    from app.meta_ads_spend_job import MetaSpendSyncWorker

    w = MetaSpendSyncWorker(
        db_factory=SessionLocal,
        enabled=False,
        interval_seconds=1,
        initial_delay_seconds=0,
    )
    w.start()
    assert w._thread is None
    w.stop()


def test_worker_nao_inicia_com_intervalo_invalido():
    from app.meta_ads_spend_job import MetaSpendSyncWorker

    w = MetaSpendSyncWorker(
        db_factory=SessionLocal,
        enabled=True,
        interval_seconds=0,
        initial_delay_seconds=0,
    )
    w.start()
    assert w._thread is None
    w.stop()


def test_worker_run_once_sucesso_e_falha(monkeypatch):
    from app import meta_ads_spend_job

    w = meta_ads_spend_job.MetaSpendSyncWorker(
        db_factory=SessionLocal,
        enabled=False,
        interval_seconds=1,
        initial_delay_seconds=0,
        janela_dias=5,
    )
    assert w.janela_dias == 5

    visto = {}

    def fake_todas(db_factory, *, janela_dias):
        visto["janela"] = janela_dias
        return SyncAllResult(lojas=2, ok=1, partial=1, imported=3, updated=1)

    monkeypatch.setattr(meta_ads_spend_job, "sincronizar_todas_lojas", fake_todas)
    payload = w.run_once()
    assert visto["janela"] == 5
    assert payload["ok"] is True
    assert payload["lojas"] == 2
    assert payload["imported"] == 3
    assert w.last_result == payload

    def explode(db_factory, *, janela_dias):
        raise RuntimeError("boom")

    monkeypatch.setattr(meta_ads_spend_job, "sincronizar_todas_lojas", explode)
    falha = w.run_once()
    assert falha == {"ok": False, "erro": "RuntimeError"}
    # nunca deixa a exceção escapar para o loop da thread
    assert w._thread is None


def test_worker_default_le_env_do_processo(monkeypatch):
    """No revy-trafego o worker lê os nomes ``PORTAL_*`` de propósito.

    ``app/main.py:83`` força ``PORTAL_META_SPEND_SYNC_ENABLED=1`` no processo
    quando ``REVY_TRAFEGO_META_SPEND_SYNC_ENABLED`` está ligado — o job em si
    nunca olha o prefixo ``REVY_TRAFEGO_*``. Este teste trava esse contrato
    para que uma renomeação de env não passe silenciosa.
    """
    from app.meta_ads_spend_job import MetaSpendSyncWorker

    monkeypatch.setenv("PORTAL_META_SPEND_SYNC_ENABLED", "0")
    monkeypatch.setenv("REVY_TRAFEGO_META_SPEND_SYNC_ENABLED", "1")
    monkeypatch.setenv("PORTAL_META_SPEND_SYNC_JANELA_DIAS", "9")
    monkeypatch.setenv("PORTAL_META_SPEND_SYNC_INTERVAL_SECONDS", "60")
    w = MetaSpendSyncWorker(db_factory=SessionLocal)
    assert w.enabled is False
    assert w.janela_dias == 9
    assert w.interval == 60.0
    w.start()
    assert w._thread is None
    w.stop()


def test_worker_nao_esta_ligado_durante_os_testes():
    """Guarda-corpo: nenhum job de spend pode estar rodando na suíte."""
    from app import meta_ads_spend_job

    assert meta_ads_spend_job.get_worker() is None


def test_job_endpoint_exige_secret_e_token(client, monkeypatch):
    from app import meta_ads_spend_job

    monkeypatch.delenv("PORTAL_META_SPEND_JOB_SECRET", raising=False)
    r = client.post("/internal/jobs/meta-spend-sync")
    assert r.status_code == 503

    monkeypatch.setenv("PORTAL_META_SPEND_JOB_SECRET", "segredo-job")
    r401 = client.post(
        "/internal/jobs/meta-spend-sync",
        headers={"X-Job-Token": "errado"},
    )
    assert r401.status_code == 401

    r_sem_header = client.post("/internal/jobs/meta-spend-sync")
    assert r_sem_header.status_code == 401

    class FakeWorker:
        def __init__(self):
            self.chamadas = 0

        def run_once(self):
            self.chamadas += 1
            return {"ok": True, "lojas": 1, "resumo": "ok"}

    fake = FakeWorker()
    monkeypatch.setattr(meta_ads_spend_job, "get_worker", lambda: fake)
    r_ok = client.post(
        "/internal/jobs/meta-spend-sync",
        headers={"X-Job-Token": "segredo-job"},
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["ok"] is True
    assert fake.chamadas == 1
