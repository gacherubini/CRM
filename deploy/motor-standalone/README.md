# Motor de Simulação — pacote standalone

Sobe **apenas** o Motor de Simulação (API + Postgres). Não depende de WhatsApp, n8n,
Portal, Estoque ou Chatbot (Plano #1A).

## Subir

```bash
cd deploy/motor-standalone
cp .env.example .env
# gere e cole a chave de cifra:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# edite .env com essa chave

docker compose up -d --build
```

A API sobe em `http://localhost:8000` e o worker (`motor-worker`) processa a fila. O schema é
migrado pelo Alembic no boot.

## Fluxo assíncrono

A criação **enfileira** o job e responde `202` com `status: recebida`. O **worker** executa os
provedores (com retry para erros transitórios e resultados parciais) e atualiza o estado geral:
`recebida → processando → concluida | parcial | falhou | aguardando_intervencao`.

```bash
curl -s http://localhost:8000/health/ready

# 1) enfileirar -> 202 {"id":"...","status":"recebida",...}
curl -s -X POST http://localhost:8000/v1/simulacoes \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"pessoa":{"cpf":"529.982.247-25","nascimento":"1990-05-20"},
       "veiculo":{"categoria":"moto","valor":20000},
       "condicoes":{"entrada":5000,"prazo_meses":48}}'

# 2) consultar (o worker conclui em segundos) -> status + 5 provedores
curl -s http://localhost:8000/v1/simulacoes/<id>

# cancelar um job ainda não concluído
curl -s -X POST http://localhost:8000/v1/simulacoes/<id>/cancelar
```

Reenvio com a mesma `Idempotency-Key` e mesmo payload devolve `200` com o mesmo `id`; payload
diferente devolve `409`. Um cliente nunca vê mensagens técnicas nem páginas bancárias — só
`codigo_erro` estável por provedor.

## Operação

- **Logs:** `docker compose logs -f motor-api` · `docker compose logs -f motor-worker`
- **Métricas:** `curl -H "Authorization: Bearer $MOTOR_METRICS_TOKEN" http://localhost:8000/metrics`
- **Ritmo do worker:** `MOTOR_WORKER_INTERVALO` (segundos, padrão 2).
- **Parar:** `docker compose down` (dados ficam no volume `motor_pg`)

Backup/restore, upgrade, rotação de segredos e diagnóstico estão detalhados no
[`RUNBOOK.md`](RUNBOOK.md). Não use `docker compose down -v` em operação: `-v` remove os dados.

> As taxas são **fictícias** (driver mock). Drivers bancários reais entram em planos próprios.
