import httpx

from app.clients.meta_graph import ResolveResult, resolver_campanha_do_anuncio


def _transport(status, payload, headers=None):
    def handler(req):
        return httpx.Response(status, json=payload, headers=headers or {})

    return httpx.MockTransport(handler)


def test_resolve_ok():
    t = _transport(
        200,
        {"campaign": {"id": "120249613359800224", "name": "MT03 CAUA"}},
    )
    r = resolver_campanha_do_anuncio("120252470707220341", "TOKEN", transport=t)
    assert isinstance(r, ResolveResult)
    assert r.ok
    assert r.campaign_id == "120249613359800224"
    assert r.campaign_nome == "MT03 CAUA"


def test_resolve_erro_4xx_nao_lanca():
    t = _transport(400, {"error": {"message": "bad"}})
    r = resolver_campanha_do_anuncio("x", "TOKEN", transport=t)
    assert r.campaign_id is None
    assert r.erro == "http_4xx"
    assert r.retryable is False


def test_resolve_sem_token_ou_ad():
    assert resolver_campanha_do_anuncio("", "TOKEN").erro == "vazio"
    assert resolver_campanha_do_anuncio("123", "").erro == "vazio"


def test_resolve_429_backoff_e_sucesso():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                429, json={"error": {"message": "throttle"}}, headers={"Retry-After": "0"}
            )
        return httpx.Response(
            200, json={"campaign": {"id": "99", "name": "C"}}
        )

    sleeps: list[float] = []
    r = resolver_campanha_do_anuncio(
        "120",
        "TOKEN",
        transport=httpx.MockTransport(handler),
        max_retries=2,
        sleeper=sleeps.append,
    )
    assert r.ok
    assert r.campaign_id == "99"
    assert calls["n"] == 2
    assert sleeps  # houve backoff


def test_resolve_5xx_esgota_retries():
    def handler(req):
        return httpx.Response(503, json={"error": {"message": "down"}})

    sleeps: list[float] = []
    r = resolver_campanha_do_anuncio(
        "120",
        "TOKEN",
        transport=httpx.MockTransport(handler),
        max_retries=2,
        sleeper=sleeps.append,
    )
    assert not r.ok
    assert r.erro == "http_5xx"
    assert r.retryable is True
    assert len(sleeps) == 2  # 3 tentativas → 2 sleeps entre elas
