"""Task 4 do plano de status de integrações: agregador `health_da_loja`.

Combina `check_meta` + `check_google` num único dict JSON-serializável,
aplicando o `TTLCache` (Task 1) para evitar rechecagem a cada request.

Segue o mesmo padrão de `tests/test_integrations_health_meta.py` e
`tests/test_integrations_health_google.py`: não há fixtures pytest
`db`/`loja` neste repositório — Loja é criada via `SessionLocal()` direto.
`FakeGraphProbe`/`FakeExchanger` são redefinidos localmente (mesmo shape das
tasks anteriores) para não acoplar este teste aos módulos de teste vizinhos.
"""

from __future__ import annotations

from app.control.health_cache import TTLCache
from app.control.integrations import IntegrationsControl, UpsertPixel
from app.control.integrations_health import (
    HealthStatus,
    health_da_loja,
    invalidar,
)
from app.control.types import Actor, StoreRef
from app.db import SessionLocal
from app.models import GestorRevy, Loja
from tests.test_integrations_health_whatsapp import FakeWppPort


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(id=admin.id, email=admin.email, name=admin.nome, role=admin.papel)


def _com_pixel_configurado(store_id: str) -> None:
    """Garante que `check_meta` de fato chame o probe (senão fica MISSING sem
    chamar `validar_token` — ver `check_meta` em `integrations_health.py`)."""
    IntegrationsControl(SessionLocal).upsert_pixel(
        _admin_actor(),
        UpsertPixel(store=StoreRef(id=store_id), pixel_id="123456789012345", token="tok-agg"),
    )


class FakeGraphProbe:
    def __init__(self, ok: bool = True, motivo: str | None = None) -> None:
        self.ok = ok
        self.motivo = motivo
        self.chamadas = 0

    def validar_token(self, token: str, pixel_id: str) -> tuple[bool, str | None]:
        self.chamadas += 1
        return (self.ok, None if self.ok else (self.motivo or "token inválido"))


class FakeExchanger:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.chamadas = 0

    def obter_access_token(self, refresh_token: str) -> str:
        self.chamadas += 1
        if not self.ok:
            raise RuntimeError("invalid_grant")
        return "access-xyz"


def _create_store(slug: str) -> str:
    with SessionLocal() as db:
        store = Loja(nome="Loja Health Agg", slug=slug)
        db.add(store)
        db.commit()
        db.refresh(store)
        return store.id


def _load_store(store_id: str, db) -> Loja:
    return db.query(Loja).filter(Loja.id == store_id).one()


def test_agrega_meta_e_google():
    store_id = _create_store("loja-health-agg-shape")
    with SessionLocal() as db:
        out = health_da_loja(
            db,
            _load_store(store_id, db),
            probe=FakeGraphProbe(),
            exchanger=FakeExchanger(),
            whatsapp_port=FakeWppPort(indisponivel=True),
        )

    assert set(out.keys()) >= {"meta", "google", "whatsapp", "checked_at", "cache_ttl_seg"}
    assert out["meta"]["status"] in {s.value for s in HealthStatus}
    assert out["google"]["status"] in {s.value for s in HealthStatus}
    assert out["whatsapp"]["status"] in {s.value for s in HealthStatus}
    assert isinstance(out["meta"]["itens"], list)
    assert isinstance(out["google"]["itens"], list)
    assert isinstance(out["whatsapp"]["itens"], list)
    for item in out["meta"]["itens"] + out["google"]["itens"] + out["whatsapp"]["itens"]:
        assert set(item.keys()) == {"kind", "status", "message"}
        assert item["status"] in {s.value for s in HealthStatus}
    assert isinstance(out["checked_at"], str)
    assert isinstance(out["cache_ttl_seg"], int)


def test_agrega_whatsapp_conectado():
    store_id = _create_store("loja-health-agg-whatsapp-ok")
    canais = [{"e164_or_label": "a", "estado": "conectado", "ativo": True}]
    with SessionLocal() as db:
        out = health_da_loja(
            db,
            _load_store(store_id, db),
            probe=FakeGraphProbe(),
            exchanger=FakeExchanger(),
            whatsapp_port=FakeWppPort(canais),
        )

    assert out["whatsapp"]["status"] == HealthStatus.CONNECTED.value


def test_cache_evita_rechecagem_e_forcar_recheca():
    store_id = _create_store("loja-health-agg-cache")
    _com_pixel_configurado(store_id)
    t = {"v": 0.0}
    cache = TTLCache(ttl_seg=600, clock=lambda: t["v"])
    probe = FakeGraphProbe()
    wpp = FakeWppPort(indisponivel=True)

    with SessionLocal() as db:
        loja = _load_store(store_id, db)
        health_da_loja(
            db,
            loja,
            probe=probe,
            exchanger=FakeExchanger(),
            whatsapp_port=wpp,
            cache=cache,
            clock=lambda: t["v"],
        )
        n1 = probe.chamadas

        health_da_loja(
            db,
            loja,
            probe=probe,
            exchanger=FakeExchanger(),
            whatsapp_port=wpp,
            cache=cache,
            clock=lambda: t["v"],
        )
        assert probe.chamadas == n1  # 2ª veio do cache, não chamou o probe de novo

        health_da_loja(
            db,
            loja,
            probe=probe,
            exchanger=FakeExchanger(),
            whatsapp_port=wpp,
            cache=cache,
            clock=lambda: t["v"],
            forcar=True,
        )
        assert probe.chamadas > n1  # forçou recheck


def test_cache_hit_nao_chama_whatsapp_port():
    store_id = _create_store("loja-health-agg-cache-wpp")
    t = {"v": 0.0}
    cache = TTLCache(ttl_seg=600, clock=lambda: t["v"])

    class _CountingWppPort:
        def __init__(self) -> None:
            self.chamadas = 0

        def listar_canais(self, loja_slug: str):
            self.chamadas += 1
            return None

    wpp = _CountingWppPort()

    with SessionLocal() as db:
        loja = _load_store(store_id, db)
        health_da_loja(
            db,
            loja,
            probe=FakeGraphProbe(),
            exchanger=FakeExchanger(),
            whatsapp_port=wpp,
            cache=cache,
            clock=lambda: t["v"],
        )
        n1 = wpp.chamadas
        assert n1 > 0

        health_da_loja(
            db,
            loja,
            probe=FakeGraphProbe(),
            exchanger=FakeExchanger(),
            whatsapp_port=wpp,
            cache=cache,
            clock=lambda: t["v"],
        )
        assert wpp.chamadas == n1  # cache hit, não chamou o whatsapp_port de novo


def test_invalidar_forca_recheck_na_proxima_chamada():
    # Usa o cache default (module-level `_CACHE`), sem passar `cache=` explícito,
    # para exercitar `invalidar(store_id)` de fato.
    store_id = _create_store("loja-health-agg-invalidar")
    _com_pixel_configurado(store_id)
    probe = FakeGraphProbe()
    wpp = FakeWppPort(indisponivel=True)

    with SessionLocal() as db:
        loja = _load_store(store_id, db)
        health_da_loja(db, loja, probe=probe, exchanger=FakeExchanger(), whatsapp_port=wpp)
        n1 = probe.chamadas

        health_da_loja(db, loja, probe=probe, exchanger=FakeExchanger(), whatsapp_port=wpp)
        assert probe.chamadas == n1  # veio do cache default, não rechecou

        invalidar(store_id)

        health_da_loja(db, loja, probe=probe, exchanger=FakeExchanger(), whatsapp_port=wpp)
        assert probe.chamadas > n1  # invalidado, rechecou
