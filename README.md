# 🏍️ Bot de WhatsApp — Simulação de Financiamento de Motos

Bot de WhatsApp para revenda de motos que conversa com o cliente, coleta os dados
necessários e devolve simulações de financiamento de vários bancos (parcela, taxa,
nº de parcelas) de forma organizada.

> **Status:** 🟢 MVP em grande parte **implementado** (~90% demo). Estado canônico:
> [`docs/contexto-compacto.md`](docs/contexto-compacto.md) · planos em [`docs/plans/README.md`](docs/plans/README.md).
> Design histórico: [`docs/design.md`](docs/design.md) (pode divergir — prevalece contexto + planos `*A`).

---

## ✨ Visão geral

```
Cliente (WhatsApp)
      │
      ▼
┌─────────────────┐
│  Evolution API  │  ← canal WhatsApp (self-host, gratuito)
└─────────────────┘
      │ webhook
      ▼
┌──────────────────────────────────────────────┐
│                    n8n                        │  ← orquestrador
│  1. Recebe mensagem                           │
│  2. Carrega estado da conversa (Postgres)     │
│  3. Chama o LLM (Gemini) → entende + extrai    │
│  4. Valida dados (CPF, data, valores)         │
│  5. Quando completo → chama o MOTOR (HTTP)     │
│  6. Formata resposta → devolve no WhatsApp    │
└──────────────────────────────────────────────┘
      │  (SQL)                    │  (HTTP POST /simular)
      ▼                          ▼
┌───────────────┐      ┌──────────────────────────────┐
│  Postgres     │      │  Serviço de Simulação (Python)│
│  leads +      │      │  FastAPI                       │
│  simulações + │      │   hoje  → MOCK                 │
│  consentim.   │      │   depois→ drivers Playwright   │
└───────────────┘      │   (santander.py, pan.py, ...)  │
                       └──────────────────────────────┘
                                     │
                                     ▼
                       Portais dos bancos (Fase 3+)
```

**Princípio central:** o mecanismo de acesso aos bancos é **desacoplado** do resto.
O bot é construído e validado com um "motor de simulação" mockado; o motor real é
plugado depois **sem alterar** o fluxo do WhatsApp, a conversa ou o banco de dados.

---

## 🧱 Stack

| Camada | Tecnologia | Papel |
|---|---|---|
| Canal WhatsApp | **Evolution API** (self-host) | Recebe/envia mensagens |
| Orquestração | **n8n** | Roteia, mantém estado, chama LLM e motor |
| Conversa (NLU) | **Google Gemini** (API, via n8n) | Entende o cliente, extrai e valida dados |
| Motor de simulação | **Python + FastAPI** (mock → Playwright) | Devolve opções por banco |
| Banco de dados | **PostgreSQL** (container) | Leads, consentimento LGPD, simulações |
| Hospedagem | **Fly.io** ou **VPS** (ex.: Hetzner) | Tudo num servidor sempre ligado |

---

## 💬 Fluxo conversacional

1. **Saudação + consentimento LGPD** (antes de qualquer dado pessoal).
2. **Qual moto** → modelo, ano, valor aproximado.
3. **Condições** → valor de entrada, prazo desejado (meses).
4. **Dados pessoais** → nome completo, CPF, data de nascimento *(renda opcional)*.
5. **Validação** → CPF (dígito verificador), data real, idade ≥ 18.
6. **Confirmação** → resume tudo e pede "confirma?".
7. **Dispara o motor** → `POST /simular`.
8. **Resposta formatada** → opções por banco.
9. **Fechamento** → salva lead + oferece falar com vendedor humano.

**Validações:** CPF com cálculo de dígito verificador (rejeita sequências inválidas);
data existente com idade mínima 18; valores como "20 mil"/"R$ 20.000"/"20000" → 20000.

---

## 🔌 Contrato do Motor de Simulação (fixo)

O n8n nunca sabe se por trás é mock ou Playwright — o contrato é sempre o mesmo:

**Entrada — `POST /simular`:**
```json
{
  "cpf": "12345678909",
  "nascimento": "1990-05-20",
  "valor_moto": 20000,
  "entrada": 5000,
  "prazo_meses": 48,
  "renda": 3000,
  "categoria": "moto"
}
```

**Saída:**
```json
{
  "resultados": [
    {"banco": "BV",  "valor_parcela": 512.30, "taxa_am": 1.79, "n_parcelas": 48, "valor_financiado": 15000, "status": "ok"},
    {"banco": "Pan", "valor_parcela": 498.10, "taxa_am": 1.72, "n_parcelas": 48, "valor_financiado": 15000, "status": "ok"}
  ]
}
```

---

## 🏦 Estratégia por banco

A loja **já tem acesso ao portal do lojista dos 5 bancos**, então o caminho do motor
real é **RPA** (automatizar os portais com Playwright). Agregador pago fica como plano B.

| Banco | API de parceiro? | Acesso real | Estratégia |
|---|---|---|---|
| **Banco BV** | ✅ Sim (BV Open, sandbox público; aceita CPF + categoria moto) | Parceiro BV + API | RPA agora; **API é upgrade** (melhor candidato técnico) |
| **Banco Pan** | ✅ Sim (`developers.bancopan.com.br`, exige contrato) | go!PAN Veículos + API | RPA agora; API como upgrade |
| **Santander** (Aymoré) | ❌ Não | Portal "Financiamento Lojista" + Autoline | **RPA no portal** |
| **Bradesco** | ❌ Não (para veículo) | Portal do lojista + Autoline | **RPA no portal** |
| **Fontcred** | ❌ Não | Parceiro/correspondente (foco moto) | **RPA no portal** / manual |

> **Decisão de integração bancária: EM HOLD.** A escolha final (RPA vs API vs agregador)
> está adiada de propósito e **não bloqueia** as fases iniciais. Detalhes e comparativo de
> agregadores (FANDI, Autoconf, Creditas) em [`docs/design.md`](docs/design.md).

---

## 🔒 LGPD

- **Consentimento** explícito antes de coletar dado pessoal (guarda texto + timestamp).
- **Minimização:** coleta só o necessário para simular.
- **Segurança:** CPF criptografado; segredos/logins de portal fora do código (env/cofre).
- **Retenção:** lead não convertido expira em **6 meses**; cliente pode pedir exclusão
  a qualquer momento ("apagar meus dados").

---

## 🚀 Roadmap (MVP em fases)

- [x] **Fundação** — domínio, contratos v1, multi-loja, papéis e segurança (Plano #0).
- [x] **Fase 0/1** — Chatbot API + n8n tools + simulação **MOCK** + lead/handoff (bot off até go-live).
- [x] **Fase 2** — Estoque, catálogo público, portal vendedor, placa CRM, E3/E5.
- [x] **Fase 3 (parcial)** — Vendas, metas loja, funil, Task 9A financeiras, E10 Pixel Meta.
- [ ] **Fase 4** — Plugar **1 driver bancário real** (Task 12 — design pronto, código não).
- [ ] **Fase 5** — Campanhas/ROI (E8), go-live WhatsApp em produção, polish revenda.

Estado detalhado: `docs/handoff-contexto.md`.

---

## 📁 Estrutura planejada

```
bot-whatsapp-financiamento/
├── README.md
├── docs/
│   └── design.md              # documento de design completo
├── n8n/                       # workflows exportados do n8n (JSON)
├── chatbot-api/               # dados e regras do Chatbot Standalone
├── servico-simulacao/         # Motor de Simulação independente
│   ├── app/
│   │   └── motor/
│   │       ├── mock.py        # simulação mockada (fórmula Price)
│   │       └── drivers/       # um conector por banco
│   └── requirements.txt
├── estoque-api/               # estoque e publicação, produto independente
├── portal-dashboards/         # gestão, vendas e metas
├── catalogo-publico/          # vitrine independente
└── deploy/
    ├── chatbot-standalone/    # pacote revendível sem portal/catálogo
    └── suite-completa/        # composição opcional dos produtos
```

---

## 🔑 O que providenciar antes de codar

**MVP (Fases 0–2):**
1. Servidor (Fly.io ou VPS) — n8n e Evolution precisam ficar **sempre ligados**.
2. Número de WhatsApp dedicado (um chip só para o bot).
3. Chave de API do Google Gemini (Google AI Studio) — configurada como credencial no n8n.
4. Postgres (container no mesmo servidor).

**Fase 3+ (quando sair do hold):**
5. Logins dos portais do lojista (a loja já tem) — guardados com segurança.
6. (Opcional) Contrato de API com BV Open / Pan, se migrar de RPA para API.

---

## 🧩 Superfícies vendáveis separadamente

O sistema possui produtos com deploy e dados próprios, ligados por contratos HTTP/eventos
versionados. Cada produto funciona sem os demais:

| Produto | O que é | Contrato |
|---|---|---|
| **Chatbot Standalone** | Evolution + n8n + Chatbot API + Estoque Lite; responde veículos disponíveis | funciona sem Portal/Catálogo Público |
| **Motor de Simulação** | Jobs mock ou bancários; pode ser acoplado ao chatbot ou vendido sozinho | `/v1/simulacoes` |
| **Portal de Gestão** | Dono, gerente, vendedor, estoque incluído, vendas e metas | Estoque API incluída; Bot/Motor opcionais |
| **Estoque API** | Fonte oficial dos veículos; incluída em modo Lite no Chatbot e completa no Dashboard | API privada e pública |
| **Catálogo Público** | Vitrine opcional, alimentada somente pelos veículos publicados no Estoque | API pública read-only |

O Estoque API é a fonte única de veículos; bot, portal e vitrine integram-se somente por contratos HTTP/eventos.

### Acesso no Portal por papel

- **Dono/gerente:** estoque completo, vendas, custos, lucro, metas, funil financeiro e simulações.
- **Vendedor:** painel e vendas próprios, leads/conversas autorizados, estoque sem custos e
  **simulação manual**. A simulação do vendedor nunca expõe custo do veículo, lucro, métricas
  financeiras, tokens ou credenciais do Motor.

A liberação da simulação para vendedor é uma decisão de produto registrada no Plano #3A.1 e deve
ser aplicada por RBAC no backend, não apenas ocultando ou exibindo itens de menu.

## 📄 Documentação

- **[docs/contexto-compacto.md](docs/contexto-compacto.md)** — ponto de entrada para agentes (estado + regras).
- **[docs/handoff-contexto.md](docs/handoff-contexto.md)** — checkpoint operacional.
- **[Índice dos planos válidos](docs/plans/README.md)** — ordem, status e pacotes comerciais.
- **Planos de implementação** (`docs/plans/` — só `*A`/`*B` e #0/#6; legados em `_archive/`):
  - [Plano #0 — Fundação](docs/plans/2026-07-11-plano0-fundacao-core-dominio-seguranca.md)
  - [Plano #1A — Motor](docs/plans/2026-07-11-plano1a-motor-simulacao-independente.md)
  - [Plano #2A — Chatbot](docs/plans/2026-07-11-plano2a-chatbot-standalone-revendivel.md)
  - [Plano #3A / #3A.1 / #3B — Portal](docs/plans/2026-07-11-plano3a-portal-vendedor-independente.md)
  - [Plano #4A — Estoque](docs/plans/2026-07-11-plano4a-estoque-api-independente.md)
  - [Plano #5A — Catálogo](docs/plans/2026-07-11-plano5a-catalogo-publico-independente.md)
  - [Plano #6 — Roadmap](docs/plans/2026-07-11-plano6-evolucoes-roadmap.md)
- **[docs/design.md](docs/design.md)** — pesquisa e decisões longas (não é ordem de implementação).
