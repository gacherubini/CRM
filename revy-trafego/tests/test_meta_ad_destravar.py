"""Ad travado no teto de tentativas volta a ser tentado quando a config muda.

`_deve_pular` descarta qualquer linha com `tentativas >= max_tentativas`, sem
prazo e sem caminho de reset. Em producao 10 ads pararam nesse estado no mesmo
lote (07/08). Quando a configuracao da Meta e corrigida, eles continuam mortos
— e nada na tela mostra "N anuncios sem campanha".

Cuidado com a chave: `invalidar` usa `store.id`, mas `MetaAdCampanha` e indexada
por `loja_slug`. Reusar o id no WHERE nao zera nada e o teste passa se olhar so
"nao quebrou" — por isso aqui se conta linha com `tentativas` zerado.
"""
from datetime import datetime, timezone

import pytest
from conftest import csrf_da_resposta

from app.db import Base, SessionLocal, engine
from app.meta_ad_resolver_job import (
    contar_ads_nao_resolvidos,
    destravar_ads_nao_resolvidos,
    resolver_ads_pendentes,
)
from app.models import MetaAdCampanha, novo_id


def _db():
    Base.metadata.create_all(bind=engine)
    return SessionLocal()


def _ad(db, *, loja_slug, ad_id, tentativas=0, erro=None, campanha=None):
    row = MetaAdCampanha(
        id=novo_id(),
        loja_slug=loja_slug,
        ad_id=ad_id,
        meta_campaign_id=campanha,
        tentativas=tentativas,
        erro=erro,
        ultima_tentativa_em=datetime(2026, 8, 7, 2, 20, tzinfo=timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


def test_destravar_zera_tentativas_dos_nao_resolvidos_da_loja():
    db = _db()
    try:
        travado = _ad(db, loja_slug="moto-center", ad_id="111", tentativas=5, erro="sem_acesso")
        resolvido = _ad(
            db,
            loja_slug="moto-center",
            ad_id="222",
            tentativas=3,
            campanha="120249613359800224",
        )
        alheio = _ad(db, loja_slug="outra-loja", ad_id="333", tentativas=5, erro="sem_acesso")

        assert destravar_ads_nao_resolvidos(db, "moto-center") == 1
        db.commit()

        assert travado.tentativas == 0
        assert travado.erro is None
        # Resolvido nao e mexido: nao ha o que retentar.
        assert resolvido.tentativas == 3
        # Outra loja nao e tocada.
        assert alheio.tentativas == 5
        assert alheio.erro == "sem_acesso"
    finally:
        db.close()


def test_destravado_volta_a_ser_chamado_pelo_resolver():
    """A prova de que o reset serve para alguma coisa: o job chama de novo."""
    db = _db()
    try:
        _ad(db, loja_slug="moto-center", ad_id="111", tentativas=5, erro="sem_acesso")
        db.commit()

        chamadas: list[str] = []

        def resolver(ad_id, token, **kw):
            chamadas.append(ad_id)
            return ("120249613359800224", "MT03 CAUA")

        antes = resolver_ads_pendentes(
            db, "moto-center", ["111"], resolver=resolver, token="T",
            sleep_entre_calls=0, cooldown_seconds=0, max_tentativas=5,
        )
        assert antes.skipped_max_tentativas == 1
        assert chamadas == []

        destravar_ads_nao_resolvidos(db, "moto-center")
        db.commit()

        depois = resolver_ads_pendentes(
            db, "moto-center", ["111"], resolver=resolver, token="T",
            sleep_entre_calls=0, cooldown_seconds=0, max_tentativas=5,
        )
        db.commit()
        assert chamadas == ["111"]
        assert depois.resolvidos == 1
    finally:
        db.close()


def test_destravar_sem_nada_para_fazer_e_no_op():
    db = _db()
    try:
        _ad(db, loja_slug="moto-center", ad_id="222", campanha="120249613359800224")
        db.commit()
        assert destravar_ads_nao_resolvidos(db, "moto-center") == 0
        assert destravar_ads_nao_resolvidos(db, "loja-que-nao-existe") == 0
    finally:
        db.close()


def test_contador_de_ads_nao_resolvidos():
    """Sem esse numero na tela, a falha fica invisivel — foi o que aconteceu."""
    db = _db()
    try:
        _ad(db, loja_slug="moto-center", ad_id="111", tentativas=5, erro="sem_acesso")
        _ad(db, loja_slug="moto-center", ad_id="112", tentativas=1, erro="timeout")
        _ad(db, loja_slug="moto-center", ad_id="222", campanha="120249613359800224")
        _ad(db, loja_slug="outra-loja", ad_id="333", tentativas=5, erro="sem_acesso")
        db.commit()

        assert contar_ads_nao_resolvidos(db, "moto-center") == 2
        assert contar_ads_nao_resolvidos(db, "outra-loja") == 1
        assert contar_ads_nao_resolvidos(db, "sem-nada") == 0
    finally:
        db.close()


def test_mudar_config_de_ads_destrava_os_ads_da_loja():
    """O enganche real: corrigir a config da Meta tem que ressuscitar os ads.

    `invalidar` ao lado usa `store.id`; aqui a chave e `loja_slug`. Por isso o
    teste conta linha com `tentativas` zerado, e nao so ausencia de excecao.
    """
    from app.control.integrations import IntegrationsControl, UpsertMetaAds
    from app.control.types import Actor, StoreRef
    from app.models import Loja

    db = _db()
    try:
        loja = Loja(nome="Moto Center", slug="moto-center", status="ativa")
        outra = Loja(nome="Outra", slug="outra-loja", status="ativa")
        db.add_all([loja, outra])
        db.flush()
        _ad(db, loja_slug="moto-center", ad_id="111", tentativas=5, erro="sem_acesso")
        _ad(db, loja_slug="outra-loja", ad_id="333", tentativas=5, erro="sem_acesso")
        db.commit()
    finally:
        db.close()

    IntegrationsControl(SessionLocal).upsert_meta_ads(
        Actor(id="gestor-1", email="trafego@revy.local", name="Equipe", role="admin"),
        UpsertMetaAds(
            store=StoreRef(slug="moto-center"),
            ad_account_id="act_123456",
            token="EAAtoken-de-teste",
            sync_enabled=True,
        ),
    )

    db = SessionLocal()
    try:
        destravado = db.query(MetaAdCampanha).filter_by(ad_id="111").one()
        alheio = db.query(MetaAdCampanha).filter_by(ad_id="333").one()
        assert destravado.tentativas == 0
        assert destravado.erro is None
        assert alheio.tentativas == 5, "loja diferente nao pode ser tocada"
    finally:
        db.close()


@pytest.fixture
def client_loja(client_logado):
    """Gestor logado com a loja `loja-teste` selecionada na sessão."""
    home = client_logado.get("/app")
    resposta = client_logado.post(
        "/app/loja",
        data={"loja_slug": "loja-teste", "csrf": csrf_da_resposta(home)},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    return client_logado


def test_tela_de_auditoria_mostra_o_contador(client_loja):
    """Sem numero na tela, "10 ads travados" fica invisivel — foi o que aconteceu."""
    db = SessionLocal()
    try:
        _ad(db, loja_slug="loja-teste", ad_id="111", tentativas=5, erro="sem_acesso")
        _ad(db, loja_slug="loja-teste", ad_id="112", tentativas=2, erro="timeout")
        db.commit()
    finally:
        db.close()

    pagina = client_loja.get("/app/trafego/ctwa-auditoria")
    assert pagina.status_code == 200
    assert "2 anúncios sem campanha" in pagina.text


def test_tela_de_auditoria_sem_ads_travados_nao_mostra_alarme(client_loja):
    pagina = client_loja.get("/app/trafego/ctwa-auditoria")
    assert pagina.status_code == 200
    assert "sem campanha resolvida" not in pagina.text
