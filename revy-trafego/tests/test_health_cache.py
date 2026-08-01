from app.control.health_cache import TTLCache


def test_cache_hit_dentro_do_ttl_e_expira_depois():
    t = {"v": 1000.0}
    c = TTLCache(ttl_seg=600, clock=lambda: t["v"])
    c.set("k", "resultado")
    assert c.get("k") == "resultado"           # hit
    t["v"] = 1000.0 + 599
    assert c.get("k") == "resultado"           # ainda dentro do TTL
    t["v"] = 1000.0 + 601
    assert c.get("k") is None                    # expirou


def test_invalidate_e_clear():
    t = {"v": 0.0}
    c = TTLCache(ttl_seg=600, clock=lambda: t["v"])
    c.set("a", 1); c.set("b", 2)
    c.invalidate("a")
    assert c.get("a") is None and c.get("b") == 2
    c.clear()
    assert c.get("b") is None
