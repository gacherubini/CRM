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

A API sobe em `http://localhost:8000`. O schema é migrado pelo Alembic no boot.

## Testar

```bash
curl -s http://localhost:8000/health/ready

curl -s -X POST http://localhost:8000/v1/simulacoes \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"pessoa":{"cpf":"529.982.247-25","nascimento":"1990-05-20"},
       "veiculo":{"categoria":"moto","valor":20000},
       "condicoes":{"entrada":5000,"prazo_meses":48}}'
# -> {"id":"...","status":"concluida","criada_em":"..."}

curl -s http://localhost:8000/v1/simulacoes/<id>   # traz os 5 provedores
```

## Operação

- **Backup:** `docker compose exec postgres pg_dump -U motor motor > backup.sql`
- **Logs:** `docker compose logs -f motor-api`
- **Parar:** `docker compose down` (dados ficam no volume `motor_pg`)

> As taxas são **fictícias** (driver mock). Drivers bancários reais entram em planos próprios.
