# Estoque API

**Fonte única de verdade dos veículos**: cadastro, custo, fotos, publicação, vitrine
pública e eventos. Alimenta Chatbot, Revy Loja e Catálogo Público. Banco e migrations
próprios.

## Armadilhas — leia antes de mexer

- **Nunca duplique veículo em outro produto.** Portal, Chatbot e Catálogo consomem daqui
  por HTTP; não criem tabela paralela de veículos.
- **Custo nunca sai na API pública.** `GET /public/v1/...` devolve só disponíveis +
  publicados, sem custo nem dado interno. Papel `operador` também não vê custo.
- **Mídia: o banco guarda só URL e metadados** — nunca base64 nem path local. URLs com
  base64, host privado, credenciais, fragmento ou query são recusadas.
- **A limpeza de órfãos falha fechado.** Sem `ESTOQUE_MEDIA_PUBLIC_BASE_URL` o worker não
  remove arquivo algum — é intencional; não "corrija" removendo o guard.
- **Idempotência é contrato.** Cadastro e upload com `Idempotency-Key` persistem só hashes
  e devolvem o mesmo veículo/foto quando chave+payload se repetem.
- **Outbox descarta após 5 tentativas.** O receptor precisa validar o HMAC e deduplicar por
  `X-Evento-Id`; entrega não é garantida para sempre.

## Onde editar

| Arquivo | Responsabilidade |
|---|---|
| `app/main.py` | API privada `/v1`, pública `/public/v1`, health |
| `app/servico.py` | Domínio de veículos, publicação, importação CSV |
| `app/media.py` | Upload, validação de assinatura, escrita atômica, limpeza de órfãos |
| `app/outbox.py` · `app/worker.py` | Eventos `vehicle.*` + entrega HMAC com backoff |
| `app/auth.py` · `app/cripto.py` | Credenciais por loja e papéis |
| `app/admin.py` · `app/admin_auth.py` | Admin HTMX |
| `app/provisioning.py` | Projeção vinda do Revy Control |
| `app/cli.py` | `criar-loja`, `criar-credencial`, `configurar-webhook`, `limpar-midias-orfas` |

## Papéis

| Papel | Pode |
|---|---|
| `dono`, `gerente` | Operação completa, custo, auditoria e eventos |
| `operador` | Gerencia veículos, **sem** custo |
| `leitor` | Somente consulta privada |

## Eventos (outbox → webhook)

Cada mutação gera `vehicle.created/updated/published/reserved/sold`. A entrega leva
assinatura **HMAC-SHA256** em `X-Assinatura` (`sha256=<hex>`), `X-Evento-Id`
(idempotência) e `X-Entrega-Id` (rastreio). Verificação no receptor:
`HMAC_SHA256(segredo, corpo_bruto)`.

API para dono/gerente: `PUT /v1/webhook`, `GET /v1/webhook` (nunca devolve o segredo),
`GET /v1/entregas`.

## Rodar e testar

```bash
cd estoque-api
python -m pytest -q
python -m alembic upgrade head      # head: confira com `alembic heads`
```

Stack isolada com Docker, onboarding, exemplos de curl, CSV e configuração de mídia:
[`../deploy/estoque-standalone/README.md`](../deploy/estoque-standalone/README.md).
