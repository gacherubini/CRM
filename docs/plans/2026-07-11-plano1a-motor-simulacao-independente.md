# Plano #1A — Motor de Simulação Independente

> Plano válido do Motor. O #1 monolítico está em `docs/plans/_archive/` (não executar).
>
> **Status 2026-07-14:** mock async, auth/tenancy, worker/lease, cifra, **Task 11** e **Task 12 piloto
> Santander LIVE** (Playwright headed+Xvfb, multi-prazo real no Portal, **entrada retornada pelo banco**
> via `parse_entrada`, **fix skeleton** dos cards). Histórico por usuário, **Registros/prints ao vivo**,
> timeout duro de 240 s e base API do PAN entregues; migrations head **0011**. Suíte de testes
> **123 verde**. Lições:
> `2026-07-13-playwright-licoes-santander.md`.
> **Aberto:** Task 10 (revenda multi-tenant); credenciais/contrato PAN; demais bancos reais
> (API-first); fan-out multi-banco e workers sob demanda conforme
> `2026-07-14-plano1a-workers-playwright-sob-demanda.md`; `testar-login` real. Contrato multi-prazo
> no Motor **já existe**.

**Goal:** Entregar uma API de simulação instalável e vendável separadamente, capaz de operar com
mock agora e drivers bancários depois, sem depender de WhatsApp, n8n, Portal, Estoque ou Chatbot.

**Stack:** Python 3.12+, FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL, worker Python,
Playwright nos drivers reais, pytest e Docker Compose.

## Critérios de independência

1. `deploy/motor-standalone/docker-compose.yml` sobe apenas API, worker e Postgres.
2. A API não conhece lead, conversa, veículo de estoque, vendedor ou campanha.
3. Todo consumidor usa `/v1/simulacoes`; não há import de código de outro produto.
4. O mock funciona sem credenciais bancárias.
5. Cada driver bancário é um adapter e pode ser ativado/desativado por configuração.
6. Falha de um banco não elimina resultados válidos dos demais.
7. O pacote possui healthcheck, migrations, backup/restore e versão.

## Contrato público

### Criar simulação

```http
POST /v1/simulacoes
Authorization: Bearer <token>
Idempotency-Key: <uuid>
```

```json
{
  "referencia_externa": "lead-ou-pedido-opcional",
  "pessoa": {
    "cpf": "12345678909",
    "nascimento": "1990-05-20",
    "renda": 3000
  },
  "veiculo": {
    "categoria": "moto",
    "valor": 20000
  },
  "condicoes": {
    "entrada": 5000,
    "prazo_meses": 48
  },
  "provedores": ["mock"]
}
```

> **Estado atual do código (mock):** o contrato acima ainda é o implementado. Taxas fictícias;
> não é cotação bancária.

### Evolução — CRM WhatsApp privado (Estoque + Chatbot; ver Plano #4A)

Decisão de produto para o pacote básico no WhatsApp:

| Campo | Hoje (mock) | Alvo WhatsApp CRM |
|---|---|---|
| `pessoa.renda` | opcional no JSON, ainda aceito | **não coletar / não obrigar** |
| `condicoes.prazo_meses` | **obrigatório** (um prazo) | **não coletar**; usar `prazos_padrao` multi-opção |
| `telefone` | **ausente** no Motor | **obrigatório** no Chatbot; no Motor via `referencia_externa` ou campo dedicado |
| `veiculo.placa` / `veiculo_id` | **ausente** | **obrigatório** no fluxo WhatsApp; valor vem do Estoque |
| `veiculo.valor` | digitado/livre | **só** após lookup por placa no Estoque |

Mock continua calculando Price; só muda o que o cliente digita e de onde vem o valor do veículo.
Drivers reais (futuro) podem voltar a exigir renda/prazo se o banco pedir.

Resposta `202`:

```json
{
  "id": "uuid",
  "status": "recebida",
  "criada_em": "2026-07-11T12:00:00Z"
}
```

### Consultar

```http
GET /v1/simulacoes/{id}
```

Estados gerais: `recebida`, `processando`, `parcial`, `concluida`, `falhou`,
`aguardando_intervencao`, `cancelada`.

Cada resultado contém `provedor`, `status`, parcela, taxa, prazo, valor financiado, **`entrada`
(necessária, devolvida pelo banco — Santander)**, timestamps e `codigo_erro` estável. Mensagens
técnicas e páginas bancárias nunca são devolvidas ao consumidor.

### Listar (histórico / ao vivo) — **FEITO (Task 16, 2026-07-13)**

```http
GET /v1/simulacoes?status=&solicitado_por=&desde=&ate=&limite=&offset=
```

- Tenancy: só jobs do `cliente_id` do token.
- Serve o **histórico de simulações do usuário** no Portal (#3A.1 Task 16): o Portal envia o e-mail do
  ator no create via header **`X-Ator`** → gravado em `simulacoes.solicitado_por` (migration 0009) e a
  lista filtra por esse campo.
- Resposta `{itens, total, limite, offset, resumo}`; `simulacao_resumo` **não decifra** payload pessoal
  (CPF omitido — índice cego não é reversível).
- Inclui estados finais (`concluida`/`parcial`/`falhou`/`aguardando_intervencao`) e em andamento.

### Outros endpoints

- `POST /v1/simulacoes/{id}/cancelar`
- `GET /v1/provedores`
- `GET /health/live`
- `GET /health/ready`
- `GET /version`

## Dados pertencentes ao Motor

- `clientes_api`: consumidor, credencial e limites.
- `simulacoes`: estado do job, referência externa, **`solicitado_por`** (ator do Portal) e retenção.
- `simulacao_resultados`: um registro por provedor/banco (parcela, taxa, prazo, financiado, **`entrada`**).
- `simulacao_tentativas`: tentativas, duração e erro sanitizado.
- `idempotencia`: chave por cliente e hash da requisição.
- `auditoria`: ações administrativas sem payload pessoal em claro.

Payload pessoal necessário ao job é cifrado em aplicação. Logs, métricas e traces usam somente IDs.

## Interface de driver

```python
class DriverSimulacao(Protocol):
    nome: str

    async def simular(self, solicitacao: SolicitacaoNormalizada) -> ResultadoDriver: ...
```

O worker escolhe drivers habilitados, executa com timeout individual e persiste cada resultado.
Captcha/2FA produz `aguardando_intervencao`; indisponibilidade produz erro transitório com retry
limitado; rejeição de negócio não sofre retry.

## Estratégia real: híbrido API + Playwright (+ mock)

Decisão de produto (2026-07-12): **não** apostar só em RPA nem só em agregador no dia 1.

```text
Job de simulação (paralelo, limite de browsers)
  ├── Driver API      → bancos/parceiros com contrato (ex. BV Open, Pan quando houver)
  ├── Driver Playwright → portais do lojista sem API (Santander, Bradesco, Fontcred, …)
  ├── Driver Agregador  → opcional depois (1 HTTP → N bancos da rede deles)
  └── Driver Mock       → demo / sem credencial / CI
```

Regras:

1. Cada banco = **um adapter** com a mesma saída (`provedor`, parcela, taxa, prazo, status, `real`).
2. Preferir **API** quando existir e a loja tiver contrato; Playwright no resto.
3. Rollout **um banco por vez** (piloto), não os 5 de uma vez.
4. Credenciais de portal **nunca** no chat com IA, nunca no git, nunca em log; só cofre/DB cifrado
   + UI do Portal (ver abaixo e Plano #3A).
5. Playwright roda **só no worker** do Motor (imagem/profile com browser), nunca no n8n.
6. WhatsApp: ack imediato; resultados **parciais** conforme drivers terminam; timeout comercial
   ~90–120 s no canal (o que não veio → falhou/timeout, sem silêncio).

### Latência esperada (ordem de grandeza)

| Modo | 1ª oferta útil | Fechamento típico (até 5) |
|---|---|---|
| Só mock | &lt; 1–3 s | &lt; 3 s |
| Só API (2 bancos) | 2–8 s | 5–15 s |
| Híbrido 2 API + 3 Playwright (sessão quente) | 5–15 s | 45–120 s |
| 5× Playwright paralelo (sessão quente) | 20–40 s | 60–180 s |
| Login frio / 2FA / captcha | pode travar | minutos ou `aguardando_intervencao` |
| **Agregador** (HTTP único) | ver nota abaixo | ver nota abaixo |

**Agregador — tempo:** não há SLA público estável “por simulação”. Na prática:

- **Só grade de simulação** (API do parceiro, sem ficha completa): costuma ficar na casa de
  **poucos segundos a ~30–60 s** para devolver várias financeiras — melhor que 5 Playwrights.
- **Marketing de F&I** (ex. “aprova em até 3–6 min”) fala de **processo de ficha/aprovação**,
  não só do cálculo de parcela. Não use isso como meta do bot de WhatsApp.
- Trate agregador como **1 driver** com timeout próprio (ex. 45–90 s); se cair, demais drivers
  (API/Playwright) ainda podem completar em `parcial`.

Medir latência real por `provedor` nas métricas do Motor (sem PII) e ajustar timeouts.

### Credenciais de portal (rotação ~a cada 2 semanas)

As senhas dos portais lojistas **mudam com frequência** (ex. a cada 2 semanas). Por isso:

- **Não** fixar senha só em `.env` de deploy eterno: o dono/gerente precisa **atualizar pelo
  Dashboard** sem redeploy e sem chamar suporte.
- Fonte da verdade operacional: Motor guarda por **tenant/cliente da API** + `provedor`:
  usuário, segredo cifrado, `atualizado_em`, `ultimo_sucesso_em`, `ultimo_erro_sanitizado`,
  `habilitado`.
- API administrativa do Motor (Bearer da loja/serviço, nunca browser direto com senha do banco):
  - `GET /v1/provedores` — lista, `real`, se tem credencial, saúde (sem devolver senha).
  - `PUT /v1/provedores/{nome}/credenciais` — body `{usuario, senha}` → cifra e grava; senha
    **nunca** retorna em GET (só máscara `****` / “configurado em …”).
  - `POST /v1/provedores/{nome}/testar-login` — opcional: valida sessão (Playwright/API) e
    atualiza `ultimo_sucesso_em` ou erro sanitizado.
- UI: **Portal** (Plano #3A) — tela “Acessos das financeiras” para dono/gerente; Portal só
  repassa ao Motor com token de serviço. Vendedor **não** vê nem edita.
- Auditoria: quem alterou credencial e quando; sem logar a senha nova/antiga.
- Alerta operacional: se `atualizado_em` &gt; N dias ou N falhas de login → status degradado no
  ready/dashboard (“atualize a senha do Pan”).

Implementação de drivers Playwright: desenvolvimento com credenciais **só no ambiente local da
loja** (env ou UI); agentes de IA **não** recebem login/senha no chat.

## Tasks

### Task 1: Scaffold e qualidade

Criar `motor-simulacao/` com FastAPI, configuração tipada, pytest, lint, API `/health` e `/version`.
Fixar dependências e impedir inicialização com segredos default em produção.

**Aceite:** testes rodam localmente e na imagem; API informa commit/versão sem expor segredos.

### Task 2: Validadores e normalização

Validadores e normalização (já no código; referência histórica em `_archive/` se preciso):

- CPF com dígitos verificadores;
- nascimento válido e idade mínima configurável;
- valores monetários normalizados;
- entrada entre zero e valor do veículo;
- prazo dentro dos limites configurados;
- categorias versionadas (`moto`, `leve`, etc.).

**Aceite:** nenhuma regra depende de LLM ou n8n.

### Task 3: Amortização e driver mock

Implementar fórmula Price em `Decimal`, arredondamento explícito e `MockDriver` determinístico.
Taxas mock são claramente marcadas como fictícias e nunca habilitadas como oferta real.

**Aceite:** testes cobrem taxa zero, entradas limite, prazos e resultados reprodutíveis.

### Task 4: Schema e migrations

Criar modelos canônicos com Alembic, `TIMESTAMPTZ`, UUIDs externos, índices por cliente/status/data,
restrições de estado e retenção. Proibir `create_all` em produção.

**Aceite:** banco vazio sobe até a versão atual e downgrade da última migration é testado.

### Task 5: API assíncrona e idempotência

Implementar criação, consulta e cancelamento. A mesma `Idempotency-Key` com o mesmo payload retorna
o mesmo recurso; com payload diferente retorna conflito. A API autentica e restringe por cliente.

**Aceite:** cliente A não consulta/cancela job do cliente B; reenvio não duplica execução.

### Task 6: Worker e resultados parciais

Worker reserva jobs no Postgres sem execução dupla, controla timeout/retry e atualiza o estado geral.
O mock pode concluir rapidamente, mas percorre o mesmo pipeline dos drivers reais.

**Aceite:** matar o worker durante um job não perde nem executa indefinidamente a solicitação.

### Task 7: Proteção de dados

Implementar cifra de payload, rotação de chave documentada, sanitização de exceções e expurgo.
Definir retenção separada para payload pessoal, resultado e auditoria.

**Aceite:** busca por CPF nos logs e banco em claro não encontra o valor usado no teste E2E.

### Task 8: Compose standalone

Criar:

- `deploy/motor-standalone/docker-compose.yml`
- `deploy/motor-standalone/.env.example`
- `deploy/motor-standalone/README.md`

Serviços: `motor-api`, `motor-worker`, `postgres`. Playwright entra somente na imagem/profile dos
drivers reais.

**Aceite:** instalação limpa cria credencial de cliente, executa mock e sobrevive a reinício.

### Task 9: Observabilidade e operação

Métricas: quantidade, latência, resultado por provedor, retry e fila — sem CPF. Documentar backup,
restore, upgrade, rotação de credenciais e diagnóstico.

### Task 10: Teste final de revenda

Em ambiente vazio, subir somente o pacote Motor, criar dois clientes, executar jobs idempotentes,
validar isolamento, simular falha parcial, reiniciar worker e restaurar backup.

### Task 11: Credenciais de provedor e rotação

Schema cifrado para credenciais por cliente+provedor; endpoints admin de listar/atualizar/testar
login; métricas de falha de auth; nunca retornar senha em claro. Documentar rotação a cada ~2
semanas e fluxo via Portal.

**Aceite:** PUT de credencial + simulação Playwright/API usa o valor novo sem restart do compose;
GET não vaza senha; auditoria registra o ator.

### Task 12: Drivers reais (híbrido) — piloto

> **Detalhado em** `2026-07-13-plano1a-task12-santander-design.md` (design) + `...-santander-implementacao.md`
> (plano Fase 1, 11 tasks TDD) + `...-bancos-reconhecimento.md` (mapa por banco). Piloto: Santander via
> Playwright; princípio **API-first** (Pan/BV/Bradesco provavelmente têm API → `ApiBankDriver`).

Implementar o **primeiro** driver real (API se houver contrato, senão Playwright) com
`real: true`, timeout, resultado parcial e falha sanitizada. Demais bancos em incrementos
separados. Agregador fica como adapter opcional quando houver contrato comercial.

**Aceite:** job com mock + 1 real em paralelo; parcial visível; WhatsApp/Chatbot só consomem o
contrato HTTP existente.

**Concorrência multi-banco (design aprovado 2026-07-14):** o job cria uma tarefa por banco;
workers Playwright pré-criados ficam parados, são acordados em paralelo e desligam após esvaziar a
fila. API drivers não usam browser. Rollout e rollback estão detalhados em
`2026-07-14-plano1a-workers-playwright-sob-demanda.md`. **Histórico de simulações do usuário: FEITO**
(#3A.1 Task 16 — listagem `GET /v1/simulacoes` + `solicitado_por`). Fan-out ainda não implementado.

## Integrações opcionais

- Chatbot Financiamento usa `HttpSimulationProvider`.
- Portal usa o mesmo contrato para simulação manual **e** tela de credenciais de financeiras.
- Outros sistemas podem consumir a API sem instalar qualquer produto da suíte.

## Fora de escopo

- Conversa, consentimento comercial e leads.
- Estoque/catálogo.
- Vendas, metas e dashboard.
- Score de crédito, até existir contrato e base legal próprios.
- Drivers bancários reais no primeiro incremento; cada banco terá plano específico.

## Resultado

Um Motor de Simulação com contrato estável, execução resiliente e pacote comercial autônomo.
