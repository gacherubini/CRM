"""Dispatcher da outbox: entrega, assinatura HMAC, retry com backoff e descarte."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import text

from app import servico
from app.models_db import EntregaEvento, EventoSaida
from app.outbox import assinar, assinatura_valida, poster_httpx, processar_pendentes

SEGREDO = "segredo-super-secreto-1234"
URL = "https://exemplo.test/hook"


@pytest.fixture(autouse=True)
def _limpar_outbox(db):
    # O banco de teste é compartilhado; a outbox é global (processa todas as lojas).
    # Começa cada teste sem eventos/entregas pendentes de outros testes.
    for tabela in ("entregas_evento", "eventos_saida", "webhook_destinos"):
        db.execute(text(f"DELETE FROM {tabela}"))
    db.commit()
    yield


class FakePoster:
    """Transporte falso: registra chamadas e devolve um resultado fixo (ou levanta)."""

    def __init__(self, resultado=(200, None), excecao=None):
        self.chamadas: list[dict] = []
        self.resultado = resultado
        self.excecao = excecao

    def __call__(self, url, corpo, headers):
        self.chamadas.append({"url": url, "corpo": corpo, "headers": dict(headers)})
        if self.excecao is not None:
            raise self.excecao
        return self.resultado


def _preparar_evento(db, loja, com_destino=True, url=URL):
    servico.criar_veiculo(
        db, loja["loja_id"],
        {"tipo": "moto", "marca": "Honda", "modelo": "CG 160", "ano_modelo": 2022, "preco": 15000},
        "dono",
    )
    if com_destino:
        servico.configurar_webhook_destino(db, loja["slug"], url, SEGREDO)
    return db.query(EventoSaida).filter_by(loja_id=loja["loja_id"], tipo="vehicle.created").one()


def test_assinatura_hmac_valida():
    corpo = b'{"a":1}'
    assinatura = assinar(SEGREDO, corpo)
    assert assinatura.startswith("sha256=")
    assert assinatura_valida(SEGREDO, corpo, assinatura)
    assert not assinatura_valida("outro-segredo", corpo, assinatura)


def test_entrega_sucesso_marca_entregue_e_assina(db, loja_a):
    evento = _preparar_evento(db, loja_a)
    poster = FakePoster((200, None))

    resumo = processar_pendentes(db, poster)

    assert resumo["entregues"] == 1
    db.refresh(evento)
    assert evento.status == "entregue"
    assert evento.processada_em is not None
    assert evento.proxima_tentativa_em is None

    assert len(poster.chamadas) == 1
    chamada = poster.chamadas[0]
    assert chamada["url"] == URL
    # A assinatura confere com o corpo realmente enviado.
    assert assinatura_valida(SEGREDO, chamada["corpo"], chamada["headers"]["X-Assinatura"])

    entrega = db.query(EntregaEvento).filter_by(evento_id=evento.id).one()
    assert entrega.sucesso is True
    assert entrega.status_http == 200
    # X-Evento-Id é a chave de idempotência estável; X-Entrega-Id identifica a tentativa.
    assert chamada["headers"]["X-Evento-Id"] == evento.id
    assert chamada["headers"]["X-Entrega-Id"] == entrega.id


def test_transporte_http_real_entrega_corpo_assinado(db, loja_a):
    recebida = {}

    def receptor(request: httpx.Request) -> httpx.Response:
        recebida["corpo"] = request.content
        recebida["headers"] = request.headers
        return httpx.Response(204)

    evento = _preparar_evento(
        db,
        loja_a,
        url="https://receptor.test/eventos",
    )
    transporte = httpx.MockTransport(receptor)
    resumo = processar_pendentes(
        db,
        poster_httpx(timeout=2, transport=transporte),
    )

    assert resumo["entregues"] == 1
    db.refresh(evento)
    assert evento.status == "entregue"
    assert json.loads(recebida["corpo"]) == evento.payload
    assert recebida["headers"]["X-Evento-Id"] == evento.id
    assert assinatura_valida(
        SEGREDO,
        recebida["corpo"],
        recebida["headers"]["X-Assinatura"],
    )


def test_falha_500_reagenda_com_backoff(db, loja_a):
    evento = _preparar_evento(db, loja_a)
    agora = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)

    resumo = processar_pendentes(db, FakePoster((500, None)), agora=agora)

    assert resumo["reagendados"] == 1
    assert resumo["entregues"] == 0
    db.refresh(evento)
    assert evento.status == "pendente"
    assert evento.tentativas == 1
    assert evento.proxima_tentativa_em is not None
    prox = evento.proxima_tentativa_em
    if prox.tzinfo is None:
        prox = prox.replace(tzinfo=timezone.utc)
    assert prox > agora

    entrega = db.query(EntregaEvento).filter_by(evento_id=evento.id).one()
    assert entrega.sucesso is False
    assert entrega.status_http == 500


def test_timeout_conta_como_falha(db, loja_a):
    evento = _preparar_evento(db, loja_a)

    resumo = processar_pendentes(db, FakePoster(excecao=TimeoutError("estourou")))

    assert resumo["reagendados"] == 1
    db.refresh(evento)
    assert evento.tentativas == 1
    assert evento.status == "pendente"
    entrega = db.query(EntregaEvento).filter_by(evento_id=evento.id).one()
    assert entrega.sucesso is False
    assert entrega.status_http is None
    assert "TimeoutError" in (entrega.erro or "")


def test_descarta_apos_max_tentativas(db, loja_a):
    evento = _preparar_evento(db, loja_a)
    poster = FakePoster((503, None))
    base = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)

    for k in range(1, 6):
        # avança bem além do backoff para o evento ficar pronto a cada rodada
        processar_pendentes(db, poster, agora=base + timedelta(hours=2 * k))

    db.refresh(evento)
    assert evento.status == "descartado"
    assert evento.tentativas == 5
    assert evento.proxima_tentativa_em is None
    assert len(poster.chamadas) == 5
    assert db.query(EntregaEvento).filter_by(evento_id=evento.id).count() == 5

    # Uma rodada extra não toca mais no evento descartado.
    resumo = processar_pendentes(db, poster, agora=base + timedelta(days=1))
    assert resumo == {"entregues": 0, "reagendados": 0, "descartados": 0, "sem_destino": 0}


def test_sem_destino_nao_falha_evento(db, loja_a):
    evento = _preparar_evento(db, loja_a, com_destino=False)

    resumo = processar_pendentes(db, FakePoster((200, None)))

    # Loja sem destino não entra no lote (ver o teste do giro em falso logo
    # abaixo): o que este teste guarda é que o evento sobrevive intacto.
    assert resumo["sem_destino"] == 0
    db.refresh(evento)
    assert evento.status == "pendente"
    assert evento.tentativas == 0
    assert db.query(EntregaEvento).filter_by(evento_id=evento.id).count() == 0


def test_loja_sem_destino_nao_gira_em_falso(db, loja_a):
    """Sem destino configurado, o lote sai vazio — não 100 eventos pulados.

    Em produção isto girou de 14/07 a 25/08: 1.429 eventos da mesma loja, nenhum
    `webhook_destinos`, e o worker relendo os mesmos 100 a cada 5s. O `continue`
    do `sem_destino` não mexia em `proxima_tentativa_em`, então o mesmo lote
    voltava para sempre — e como o resumo era "truthy", o worker logava a cada
    tick e afogava o log do app inteiro.
    """
    _preparar_evento(db, loja_a, com_destino=False)
    poster = FakePoster((200, None))

    resumo = processar_pendentes(db, poster)

    assert resumo == {"entregues": 0, "reagendados": 0, "descartados": 0, "sem_destino": 0}
    # É o resumo todo-zero que faz o worker calar (`if any(resumo.values())`).
    assert not any(resumo.values())
    assert not poster.chamadas


def test_destino_configurado_depois_entrega_sem_esperar(db, loja_a):
    """Ignorar o evento não pode virar atraso quando o destino enfim aparece.

    A alternativa (empurrar `proxima_tentativa_em` para o futuro) também mataria
    o giro, mas deixaria o primeiro lote preso pelo backoff depois da
    configuração. Por isso o filtro é na consulta, e o evento fica pronto.
    """
    evento = _preparar_evento(db, loja_a, com_destino=False)
    assert processar_pendentes(db, FakePoster((200, None)))["entregues"] == 0
    db.refresh(evento)
    assert evento.proxima_tentativa_em is None

    servico.configurar_webhook_destino(db, loja_a["slug"], URL, SEGREDO)
    poster = FakePoster((200, None))

    resumo = processar_pendentes(db, poster)

    assert resumo["entregues"] == 1
    assert len(poster.chamadas) == 1
    db.refresh(evento)
    assert evento.status == "entregue"


def test_backoff_cresce_entre_tentativas(db, loja_a):
    evento = _preparar_evento(db, loja_a)
    poster = FakePoster((500, None))
    base = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)

    def _prox_em_segundos(agora):
        processar_pendentes(db, poster, agora=agora)
        db.refresh(evento)
        prox = evento.proxima_tentativa_em
        if prox.tzinfo is None:
            prox = prox.replace(tzinfo=timezone.utc)
        return (prox - agora).total_seconds()

    d1 = _prox_em_segundos(base)
    d2 = _prox_em_segundos(base + timedelta(hours=2))
    assert d2 > d1


def test_destino_url_invalida_rejeitada(db, loja_a):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        servico.configurar_webhook_destino(db, loja_a["slug"], "ftp://x", SEGREDO)
    assert exc.value.status_code == 422


def test_segredo_curto_rejeitado(db, loja_a):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        servico.configurar_webhook_destino(db, loja_a["slug"], URL, "curto")
    assert exc.value.status_code == 422


def test_segredo_guardado_cifrado(db, loja_a):
    from app.models_db import WebhookDestino

    servico.configurar_webhook_destino(db, loja_a["slug"], URL, SEGREDO)
    destino = db.get(WebhookDestino, loja_a["loja_id"])
    assert destino.segredo_cifrado != SEGREDO
    assert SEGREDO not in destino.segredo_cifrado


def test_api_configura_e_le_webhook_sem_vazar_segredo(client, loja_a):
    r = client.put(
        "/v1/webhook",
        headers=loja_a["headers"],
        json={"url": URL, "segredo": SEGREDO},
    )
    assert r.status_code == 200

    r = client.get("/v1/webhook", headers=loja_a["headers"])
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["configurado"] is True
    assert corpo["url"] == URL
    assert SEGREDO not in r.text


def test_api_webhook_exige_gestao(client, operador_loja_a):
    r = client.put(
        "/v1/webhook",
        headers=operador_loja_a["headers"],
        json={"url": URL, "segredo": SEGREDO},
    )
    assert r.status_code == 403
    assert client.get("/v1/webhook", headers=operador_loja_a["headers"]).status_code == 403


def test_api_lista_entregas(client, db, loja_a):
    _preparar_evento(db, loja_a)
    processar_pendentes(db, FakePoster((200, None)))

    r = client.get("/v1/entregas", headers=loja_a["headers"])
    assert r.status_code == 200
    entregas = r.json()["entregas"]
    assert len(entregas) == 1
    assert entregas[0]["sucesso"] is True
    assert entregas[0]["status_http"] == 200
