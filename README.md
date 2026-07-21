# 🏍️ Bot de WhatsApp — Simulação de Financiamento de Motos

Bot de WhatsApp para revenda de motos que conversa com o cliente, coleta os dados
necessários, solicita a simulação internamente e transfere o atendimento para um vendedor.
Parcelas, taxas e bancos não são enviados automaticamente ao cliente.

> **Status:** 🟢 MVP demonstrável (~**97%** demo / multi-banco + CRM campanhas/ROI).  
> **Ambiente:** preferência **local** (Fly lab **parado** desde 2026-07-20).  
> **Estado canônico:** [`docs/contexto-compacto.md`](docs/contexto-compacto.md) · planos
> [`docs/plans/README.md`](docs/plans/README.md) · go-live WA [`docs/go-live-chatbot.md`](docs/go-live-chatbot.md).  
> `docs/design.md` = pesquisa **histórica** — **não** implementar a partir dele.

---

## ✨ Visão geral

```
Cliente (WhatsApp)          Catálogo público (UTM/Pixel)
      │                              │
      ▼                              ▼
┌─────────────────┐          Chatbot API (leads, first/last)
│  Evolution API  │
└─────────────────┘
      │ webhook
      ▼
┌──────────────────────────────────────────────┐
│                    n8n                        │  ← orquestra + LLM (Gemini)
│  tools HTTP → Chatbot / Motor / Estoque       │
└──────────────────────────────────────────────┘
      │                         │
      ▼                         ▼
 Chatbot API              Motor de Simulação (FastAPI)
 (leads, handoff)         mock + Playwright LIVE
      │                   (Santander, Fontecred, Bradesco, Pan portal)
      ▼
 Portal de Gestão  ←→  Estoque API  →  Catálogo
 (CRM, vendas, metas, campanhas/ROI, CAPI)
```

**Princípio central:** produtos **independentes** ligados só por HTTP. Motor mock ou real
não muda o contrato `/v1/simulacoes`. Estoque é a fonte de verdade de veículos.

---

## 🧱 Stack

| Camada | Tecnologia | Papel |
|---|---|---|
| Canal WhatsApp | **Evolution API** (self-host) | Recebe/envia mensagens |
| Orquestração | **n8n** | Roteia, mantém estado, chama LLM e motor |
| Conversa (NLU) | **Google Gemini** (API, via n8n) | Entende o cliente, extrai e valida dados |
| Motor de simulação | **Python + FastAPI** + Playwright | Mock + drivers reais (4 bancos LIVE) |
| CRM / vitrine | Portal FastAPI + Catálogo + Estoque API | Vendas, metas, campanhas/ROI, Pixel |
| Banco de dados | **PostgreSQL** (container / lab) | Por produto (tenancy) |
| Hospedagem | **Local (dev)** · Fly.io lab opcional (OFF) | Sempre ligado só o que for demo |

---

## 💬 Fluxo conversacional

1. **Saudação + consentimento LGPD** (antes de qualquer dado pessoal).
2. **Qual moto** → modelo, ano, valor aproximado.
3. **Condições** → valor de entrada, prazo desejado (meses).
4. **Dados pessoais** → nome completo, CPF, data de nascimento *(renda opcional)*.
5. **Validação** → CPF (dígito verificador), data real, idade ≥ 18.
6. **Confirmação** → resume tudo e pede "confirma?".
7. **Dispara o motor internamente** → a resposta financeira não volta ao cliente pelo bot.
8. **Handoff automático** → pausa o bot e chama um vendedor.
9. **Fechamento** → o bot avisa que o vendedor trará o resultado; parcelas/taxas ficam no Portal.

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

| Banco | Estado no Motor | Estratégia atual |
|---|---|---|
| **Santander** (Aymoré) | **LIVE** Playwright | Portal lojista |
| **Fontecred** | **LIVE** Playwright | Portal + warm session |
| **Bradesco** (Turbo) | **LIVE** Playwright | Portal lojista |
| **Pan** | **LIVE** dual-path | Portal go!PAN (default) + API se config completa |
| **BV** | backlog | API parceiro como upgrade futuro |

Mapa de campos e decisões: [`docs/plans/2026-07-13-plano1a-task12-bancos-reconhecimento.md`](docs/plans/2026-07-13-plano1a-task12-bancos-reconhecimento.md).

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
- [x] **Chatbot + n8n** — API, handoff, E3/E5, tools, sim mock e real.
- [x] **Estoque + Catálogo + Portal** — CRUD, vitrine, CRM vendedor, 9A financeiras.
- [x] **Vendas / metas / CSV / E10 Pixel** — + **campanhas + ROI (E8)** DONE 2026-07-20.
- [x] **Motor multi-banco** — Santander, Fontecred, Bradesco, Pan portal LIVE; fan-out; warm session teto 2.
- [ ] **Go-live WhatsApp E2E** — Gemini + Evolution + n8n em ambiente estável (eixo A).
- [x] **Backend #3B Task 4 + event bus** — eventos/tempos e adapter Meta concluídos.
- [ ] **Residual CRM** — UI do funil; Google; outbound E11/E12; polish revenda.

Estado canônico: [`docs/contexto-compacto.md`](docs/contexto-compacto.md) · planos: [`docs/plans/README.md`](docs/plans/README.md) · handoff: [`docs/handoff-contexto.md`](docs/handoff-contexto.md).

---

## 📁 Estrutura do monorepo

```
bot-whatsapp-financiamento/
├── README.md
├── docs/                      # contexto, planos, brand, guias
├── n8n/                       # workflows exportados
├── chatbot-api/               # Chatbot Standalone (FastAPI)
├── motor-simulacao/           # Motor mock + Playwright
├── estoque-api/               # Estoque + admin HTMX
├── portal-gestao/             # CRM, vendas, metas, campanhas/ROI
├── catalogo-publico/          # vitrine + Pixel
├── site/                      # landing marketing
└── deploy/
    ├── chatbot-standalone/    # docker-compose local
    ├── motor-standalone/
    ├── estoque-standalone/
    ├── catalogo-conectado/
    └── fly/                   # scripts lab Fly (OFF por padrão)
```

---

## 🔑 O que precisa para rodar

**Local (preferido):**
1. Docker (Postgres / n8n / Evolution conforme o compose do pacote).
2. Python 3.12+ por produto (`requirements.txt` + venv).
3. Chave Gemini no n8n (se testar conversa IA).
4. Credenciais de portal lojista no Motor (cifradas; via Portal 9A ou env de dev).

**Lab Fly (opcional, hoje parado):**
5. `flyctl` + `deploy/fly/up-all.sh` — só com pedido explícito (custo).

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

- **Dono/gerente:** estoque completo, vendas, custos, lucro, metas, funil, **campanhas/ROI**,
  tráfego (Pixel/CAPI) e simulações.
- **Vendedor:** painel e vendas próprios, leads/conversas autorizados, estoque sem custos e
  **simulação manual**. Nunca expõe custo do veículo, lucro, tokens ou credenciais do Motor.

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
