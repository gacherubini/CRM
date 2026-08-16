"""Venda excluída no Portal precisa sair da projeção do Control.

Leva de 2026-08-16: o dono passou a poder apagar uma venda registrada por
engano. "Excluída" é diferente de "cancelada" (negócio desfeito) — mas do
ponto de vista do Control as duas têm o mesmo efeito: a venda sai do ROI e
qualquer evento CAPI ainda não enviado é cancelado.

O endpoint recusava com 400 qualquer status fora de confirmada/cancelada, o
que faria o outbox do Portal reentregar para sempre sem nunca convergir.
"""
from dataclasses import replace
from datetime import datetime, timezone

from app import config as config_mod
from app.db import SessionLocal
from app.models import MetaCapiOutbox, VendaProjetada, novo_id


def _token(monkeypatch, valor: str = "tok-teste-svc"):
    config_mod.settings = replace(config_mod.settings, service_token=valor)
    return {"X-Service-Token": valor}


def _snapshot(venda_id: str, status: str, *, valor: str = "50000.00") -> dict:
    return {
        "venda_id": venda_id,
        "valor": valor,
        "moeda": "BRL",
        "status": status,
        "criada_em": datetime.now(timezone.utc).isoformat(),
        "atualizada_em": datetime.now(timezone.utc).isoformat(),
    }


def _projetada(venda_id: str) -> VendaProjetada | None:
    db = SessionLocal()
    try:
        return db.get(VendaProjetada, (venda_id, "loja-demo"))
    finally:
        db.close()


def test_venda_excluida_e_aceita_e_projetada(client, monkeypatch):
    headers = _token(monkeypatch)
    venda_id = f"venda-excluir-{novo_id()[:8]}"

    r = client.post(
        "/v1/lojas/loja-demo/eventos/venda-atualizada",
        json=_snapshot(venda_id, "confirmada"),
        headers=headers,
    )
    assert r.status_code == 200, r.text

    r = client.post(
        "/v1/lojas/loja-demo/eventos/venda-atualizada",
        json=_snapshot(venda_id, "excluida"),
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert _projetada(venda_id).status == "excluida"


def test_venda_excluida_cancela_capi_pendente(client, monkeypatch):
    """Se o Purchase ainda não saiu, apagar a venda impede o disparo."""
    headers = _token(monkeypatch)
    venda_id = f"venda-capi-{novo_id()[:8]}"
    db = SessionLocal()
    try:
        db.add(
            MetaCapiOutbox(
                id=novo_id(),
                loja_slug="loja-demo",
                venda_id=venda_id,
                event_id=f"purchase-{venda_id}",
                status="pending",
                payload_json="{}",
                attempts=0,
                criada_em=datetime.now(timezone.utc),
                atualizada_em=datetime.now(timezone.utc),
            )
        )
        db.commit()
    finally:
        db.close()

    r = client.post(
        "/v1/lojas/loja-demo/eventos/venda-atualizada",
        json=_snapshot(venda_id, "excluida"),
        headers=headers,
    )
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        item = (
            db.query(MetaCapiOutbox)
            .filter(MetaCapiOutbox.venda_id == venda_id)
            .one()
        )
        assert item.status == "cancelled"
    finally:
        db.close()


def test_status_desconhecido_continua_recusado(client, monkeypatch):
    """Aceitar 'excluida' não pode abrir a porta para qualquer string."""
    headers = _token(monkeypatch)
    r = client.post(
        "/v1/lojas/loja-demo/eventos/venda-atualizada",
        json=_snapshot("venda-status-invalido", "arquivada"),
        headers=headers,
    )
    assert r.status_code == 400
