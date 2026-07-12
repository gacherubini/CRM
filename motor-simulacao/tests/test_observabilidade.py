"""Task 9: métricas operacionais agregadas e sem dados pessoais."""
from datetime import datetime, timezone

from app.motor.drivers import ErroTransitorio, ResultadoDriver
from app.processamento import drenar_fila


def _payload():
    return {
        "referencia_externa": "cliente-confidencial-42",
        "pessoa": {"cpf": "529.982.247-25", "nascimento": "1990-05-20", "renda": 3000},
        "veiculo": {"categoria": "moto", "valor": 20000},
        "condicoes": {"entrada": 5000, "prazo_meses": 48},
        "provedores": ["banco_teste"],
    }


def test_metricas_mostram_fila_sem_dados_pessoais(client):
    criada = client.post("/v1/simulacoes", json=_payload()).json()
    resposta = client.get("/metrics")

    assert resposta.status_code == 200
    texto = resposta.text
    assert 'motor_queue_jobs{status="recebida"} 1' in texto
    assert "motor_queue_oldest_age_seconds" in texto
    assert "529.982.247-25" not in texto
    assert "cliente-confidencial-42" not in texto
    assert criada["id"] not in texto


def test_metricas_mostram_resultado_latencia_e_retry(client, db):
    chamadas = 0

    def driver(_sol):
        nonlocal chamadas
        chamadas += 1
        if chamadas == 1:
            raise ErroTransitorio("temporario")
        return ResultadoDriver("banco_teste", "concluida", prazo_meses=48)

    client.post("/v1/simulacoes", json=_payload())
    drenar_fila(db, drivers=[("banco_teste", driver)])

    texto = client.get("/metrics").text
    assert 'motor_provider_results{provider="banco_teste",status="concluida"} 1' in texto
    assert 'motor_provider_attempts{provider="banco_teste",status="erro_transitorio"} 1' in texto
    assert 'motor_provider_retries{provider="banco_teste"} 1' in texto
    assert "motor_provider_attempt_duration_seconds_count" in texto
    assert "motor_provider_attempt_duration_seconds_sum" in texto


def test_idade_da_fila_aceita_datetime_com_timezone(client, db):
    from app.observabilidade import gerar_metricas

    client.post("/v1/simulacoes", json=_payload())
    texto = gerar_metricas(db, agora=datetime.now(timezone.utc))
    assert "motor_queue_oldest_age_seconds" in texto


def test_metricas_exigem_token_quando_configurado(client, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "METRICS_TOKEN", "segredo-metricas")
    assert client.get("/metrics").status_code == 401
    resposta = client.get(
        "/metrics", headers={"Authorization": "Bearer segredo-metricas"}
    )
    assert resposta.status_code == 200
