from datetime import datetime, timezone

from app.tokens import as_utc, token_hash


def test_token_hash_is_sha256_hex_and_stable():
    h = token_hash("abc")
    assert h == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert token_hash("abc") == h


def test_as_utc_assumes_utc_for_naive_and_converts_aware():
    naive = datetime(2026, 1, 1, 12, 0, 0)
    assert as_utc(naive).tzinfo == timezone.utc
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert as_utc(aware) == aware
