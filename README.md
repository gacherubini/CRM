# 🏍️ Bot de WhatsApp — Simulação de Financiamento de Motos

Bot de WhatsApp para revenda de motos que conversa com o cliente, coleta os dados
necessários, solicita a simulação internamente e transfere o atendimento para um vendedor.
Parcelas, taxas e bancos não são enviados automaticamente ao cliente.

> **Status:** 🟢 MVP demonstrável; lab Fly **3-VM no ar** (`app2037` + `evolution2037` + `suite-pg`; workers Playwright on-demand).  
> **Ambiente:** local (dev) **ou** Fly consolidado — ver [`deploy/fly/3vm/README.md`](deploy/fly/3vm/README.md).  
> **Estado canônico:** [`docs/contexto-compacto.md`](docs/contexto-compacto.md) · planos
> [`docs/plans/README.md`](docs/plans/README.md) · go-live WA [`docs/go-live-chatbot.md`](docs/go-live-chatbot.md).  
> **As-built Control/Loja:** [`docs/design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md`](docs/design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md).

### Estado atual do Revy Control

> **Agentes e manutencao:** comece por [`CLAUDE.md`](CLAUDE.md) para o mapa dos sete produtos,
> acoplamentos HTTP, arquivos certos e comandos de teste/deploy com baixo uso de contexto.

O corte lean está implementado no código: **Control F0–F6** e **Loja F0–F6 + F8**,
com shells, RBAC, projeções, Vendas/Estoque, Atendimento, Multibanco e contratos.
As flags continuam desligadas por padrão para permitir cutover gradual. Restam tarefas
operacionais de lab — rollout, credenciais Google, E2E Evolution/multi-WhatsApp e
smokes bancários. Seller AI (F7) segue explicitamente adiado. Consulte o
[as-built atual](docs/design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md)
antes de reabrir trabalho já entregue.

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
 Revy Loja (`portal-gestao`) ←→ Estoque API → Catálogo
 (CRM, vendas, metas; resultados de mídia)
      │ outbox transacional de vendas (HTTP)
      ▼
 Revy Control `/trafego` (banco próprio; Pixel, CAPI, Ads, ROI, canais, leads)
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
| CRM / vitrine | **Revy Loja** + **Revy Control** + Catálogo + Estoque | Loja: CRM/resultados · Control: Pixel/CAPI/Ads e operação multi-loja |
| Banco de dados | **PostgreSQL** (container / lab) | Por produto (tenancy) |
| Hospedagem | **Local (dev)** · **Fly.io 3-VM** (lab ativo) | Always-on: Postgres + Evolution + app bundle; Playwright on-demand |

---

## 🧭 Quem o bot atende (roteamento)

A decisão fica no Chatbot (`POST /v1/operacao/roteamento`), não só no n8n.
Sinal de “contato novo” = `isSaved === false` na Evolution (agenda do WhatsApp).

| Caso | Quem | Ação |
|---|---|---|
| **1** Contato que já fala | Salvo na agenda (`isSaved=true`), **não** é equipe | **Ignora** — sem bot de vendas |
| **2** Contato **novo** | Não salvo (`isSaved=false`), **não** é equipe | **IA** (único caso de bot de vendas) |
| **3** Grupo do estoque | Mensagem no único grupo escolhido no Portal | **Menu e estoque**: cadastrar, consultar, editar e enviar fotos |
| **4** Privado ou outro grupo | Imagem fora do grupo escolhido | **Ignora silenciosamente**; não baixa nem cadastra a foto |

Qualquer participante do grupo escolhido pode operar o estoque. A lista de números da equipe é
apenas compatibilidade/identificação e não abre o menu no privado quando existe um grupo configurado.
Sem sinal claro de contato novo → fail-closed (**ignora**).

---

## 💬 Fluxo conversacional (contato novo)

1. **Saudação + identificação do interesse**; consentimento explícito pode ser registrado quando informado, sem bloquear o atendimento.
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

- **Consentimento:** registro disponível, sem criar uma barreira artificial antes de lead/simulação.
- **Minimização:** coleta só o necessário para simular.
- **Segurança:** CPF criptografado; segredos/logins de portal fora do código (env/cofre).
- **Retenção/exclusão:** somente por processo administrativo autorizado; o cliente não recebe
  controle de autosserviço para apagar dados.

---

## 🚀 Roadmap (MVP em fases)

- [x] **Fundação** — domínio, contratos v1, multi-loja, papéis e segurança (Plano #0).
- [x] **Chatbot + n8n** — API, handoff, E3/E5, tools, sim mock e real.
- [x] **Estoque + Catálogo + Portal** — CRUD, vitrine, CRM vendedor, 9A financeiras.
- [x] **Vendas / metas / CSV / E10 Pixel** — + **campanhas + ROI (E8)** DONE 2026-07-20.
- [x] **Motor multi-banco** — Santander, Fontecred, Bradesco, Pan portal LIVE; fan-out; warm session teto 2.
- [x] **Deploy Fly 3-VM** — `suite-pg` + `evolution2037` + `app2037` (n8n/chatbot/estoque/portal/catálogo/site/motor-api); `motor2037` Playwright on-demand.
- [x] **Roteamento WA 3 casos** — só contato novo recebe IA; equipe em modo cadastro; match de telefone com variantes.
- [ ] **Go-live WhatsApp E2E estável** — Gemini no n8n + primeira conversa real monitorada (eixo A).
- [x] **#3B Task 4 + event bus** — eventos/tempos, UI do funil e adapter Meta concluídos.
- [x] **Revy Tráfego Fase 3** — banco/Alembic próprios, projeção de vendas e outbox
  criptografado Portal → Revy; CAPI assíncrona e isolada por loja.
- [x] **Revy Control/Loja lean** — shells, RBAC, prontidão, operação Google Ads e
  números multi-WhatsApp com QR efêmero.
- [x] **Mídia WhatsApp backend** — áudio efêmero; foto automática WhatsApp → Estoque → Catálogo; lote por sessão; envio da capa ao cliente.
- [ ] **Residual CRM/ops** — rollout/secrets/E2E Google e multi-WhatsApp; outbound
  E11/E12; transcritor real; polish revenda.

Estado canônico: [`docs/contexto-compacto.md`](docs/contexto-compacto.md) · planos: [`docs/plans/README.md`](docs/plans/README.md) · handoff: [`docs/handoff-contexto.md`](docs/handoff-contexto.md).

---

## 📁 Estrutura do monorepo

```
bot-whatsapp-financiamento/
├── README.md
├── docs/                      # contexto, planos, brand, guias, manuais
├── n8n/                       # workflows exportados (placeholders de token)
├── chatbot-api/               # Chatbot Standalone (FastAPI)
├── motor-simulacao/           # Motor mock + Playwright
├── estoque-api/               # Estoque + admin HTMX
├── portal-gestao/             # CRM, vendas, metas, campanhas/ROI
├── revy-trafego/              # operação de mídia, CAPI e ROI em banco próprio
├── catalogo-publico/          # vitrine + Pixel
├── site/                      # landing marketing
└── deploy/
    ├── chatbot-standalone/    # docker-compose local
    ├── motor-standalone/
    ├── estoque-standalone/
    ├── catalogo-conectado/
    └── fly/
        ├── up-all.sh / down-all.sh   # lab: use --3vm
        └── 3vm/                      # stack Fly consolidada (canônica)
```

---

## 🔑 O que precisa para rodar

**Local:**
1. Docker (Postgres / n8n / Evolution conforme o compose do pacote).
2. Python 3.12+ por produto (`requirements.txt` + venv).
3. Chave Gemini no n8n (se testar conversa IA).
4. Credenciais de portal lojista no Motor (cifradas; via Portal 9A ou env de dev).

**Lab Fly (3-VM — path atual):**
5. `flyctl` + org com apps `suite-pg`, `evolution2037`, `app2037` (+ `motor2037` on-demand).
6. Subir: `bash deploy/fly/up-all.sh --3vm` · desligar: `bash deploy/fly/down-all.sh --3vm --yes`.
7. Detalhes, secrets e deploy: [`deploy/fly/3vm/README.md`](deploy/fly/3vm/README.md).
8. Workflow n8n: prepare a partir de `n8n/workflow-ai-nao-salvos.json` + `.secrets.local`
   (`prepare-workflow.ps1`) — **não** versionar `workflow-fly.ready.json` (tokens reais).

---

## 🧩 Superfícies vendáveis separadamente

O sistema possui produtos com deploy e dados próprios, ligados por contratos HTTP/eventos
versionados. Cada produto funciona sem os demais:

| Produto | O que é | Contrato |
|---|---|---|
| **Chatbot Standalone** | Evolution + n8n + Chatbot API + Estoque Lite; responde veículos disponíveis | funciona sem Portal/Catálogo Público |
| **Motor de Simulação** | Jobs mock ou bancários; pode ser acoplado ao chatbot ou vendido sozinho | `/v1/simulacoes` |
| **Revy Loja** (`portal-gestao`) | Dono, gerente, vendedor, estoque incluído, vendas e metas | Estoque API incluída; Bot/Motor opcionais |
| **Revy Control** (`revy-trafego`) | Operação multi-loja de Pixel, CAPI, Google Ads, campanhas, ROI e prontidão | recebe projeções de venda da Loja por HTTP/outbox |
| **Estoque API** | Fonte oficial dos veículos; incluída em modo Lite no Chatbot e completa no Dashboard | API privada e pública |
| **Catálogo Público** | Vitrine opcional, alimentada somente pelos veículos publicados no Estoque | API pública read-only |

O Estoque API é a fonte única de veículos; bot, portal e vitrine integram-se somente por contratos HTTP/eventos.

### Acesso no Portal por papel

- **Dono/gerente:** estoque completo, vendas, custos, lucro, metas, funil, resultados de mídia
  e simulações. Configuração técnica de Pixel/CAPI/campanhas fica no Revy Control.
- **Vendedor:** painel e vendas próprios, leads/conversas autorizados, estoque sem custos e
  **simulação manual**. Nunca expõe custo do veículo, lucro, tokens ou credenciais do Motor.

A liberação da simulação para vendedor é uma decisão de produto registrada no Plano #3A.1 e deve
ser aplicada por RBAC no backend, não apenas ocultando ou exibindo itens de menu.

## 📄 Documentação

- **[docs/contexto-compacto.md](docs/contexto-compacto.md)** — ponto de entrada para agentes (estado + regras).
- **[docs/handoff-contexto.md](docs/handoff-contexto.md)** — checkpoint operacional.
- **[deploy/fly/3vm/README.md](deploy/fly/3vm/README.md)** — inventário Fly, deploy, secrets, up/down.
- **[docs/tutorial-dono.md](docs/tutorial-dono.md)** / **[docs/tutorial-vendedor.md](docs/tutorial-vendedor.md)** — manuais de operação.
- **[Índice dos planos válidos](docs/plans/README.md)** — ordem, status e pacotes comerciais.
- **Planos de implementação** (`docs/plans/` — só `*A`/`*B` e #0/#6; legados em `_archive/`):
  - [Plano #0 — Fundação](docs/plans/2026-07-11-plano0-fundacao-core-dominio-seguranca.md)
  - [Plano #1A — Motor](docs/plans/2026-07-11-plano1a-motor-simulacao-independente.md)
  - [Plano #2A — Chatbot](docs/plans/2026-07-11-plano2a-chatbot-standalone-revendivel.md)
  - [Plano #3A / #3A.1 / #3B — Portal](docs/plans/2026-07-11-plano3a-portal-vendedor-independente.md)
  - [Plano #4A — Estoque](docs/plans/2026-07-11-plano4a-estoque-api-independente.md)
  - [Plano #5A — Catálogo](docs/plans/2026-07-11-plano5a-catalogo-publico-independente.md)
  - [Plano #6 — Roadmap](docs/plans/2026-07-11-plano6-evolucoes-roadmap.md)
- **[As-built Control/Loja](docs/design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md)** — estado real, gaps e próximos incrementos.
