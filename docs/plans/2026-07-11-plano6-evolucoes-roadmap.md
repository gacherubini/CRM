# Plano #6 — Evoluções (roadmap)

> **Regra de produto:** toda evolução declara em qual produto vive e integra os demais somente por
> contrato. Nenhum item futuro pode transformar Portal, Catálogo ou Motor em dependência obrigatória
> do Chatbot Standalone.

> **Natureza deste documento:** diferente dos Planos #1–#5, este é um **roadmap** de evoluções
> futuras — cada item é um esboço de abordagem, não uma sequência de tarefas TDD. Quando um item
> for priorizado, ele vira um plano completo próprio (via a skill de escrita de planos).
>
> **Status 2026-07-14 (limpeza + confirmação dono):** **E3**, **E5**, **E10** entregues.
> Ativos: **E1**, **E6**, **E8**, **E11–E12**, **E13–E18** (aprovados na rodada de alta aderência).
> **Fora do core:** **E9** redes. **Adiados:** **E2**, **E4**, **E7**.
> Backlog C1–C12: confirmação **encerrada** (aprovados→E13–E18; rejeitados registrados no fim).

**Origem:** revenda de veículos (moto) — WhatsApp, simulação, estoque, vitrine e gestão da loja.
Não é suite genérica de marketing/redes.

**Princípio:** todos encaixam sem quebrar os contratos versionados de cada produto
(`/v1/simulacoes`, Chatbot API, Estoque API pública/privada e Portal). São extensões por adapter ou
evento, não acesso direto a bancos de dados vizinhos.

| Evolução | Status no roadmap | Produto proprietário |
|---|---|---|
| **E1** Áudio/multimodal | Ativo | Chatbot |
| **E2** Score de crédito | **Adiado** (bureau + LGPD) | Motor (+ Portal UI) |
| **E3** Auto-pausa atendente | **Feito** | Chatbot |
| **E4** Multi-agente | **Adiado** (só com ≥3 fluxos) | Chatbot / n8n |
| **E5** Cadastro veículo WA | **Feito** (fase 1 texto) | Chatbot → Estoque |
| **E6** Fotos / galeria | Ativo | Estoque + Catálogo |
| **E7** Analytics avançado | **Adiado** (precisa volume) | Portal |
| **E8** Atribuição / ROI campanhas | Ativo (após Task 5) | Portal |
| **E9** Redes sociais | **Fora do core** (não planejar) | — |
| **E10** Pixel Meta | **Feito** (MVP) | Portal + Catálogo |
| **E11** WhatsApp em massa | Ativo (após go-live WA) | Chatbot + Portal UI |
| **E12** Campanhas e-mail | Ativo (suíte Portal) | Portal |
| **E13** Notificação interna de lead | Ativo (esboço 2026-07-14) | Portal (config) + Chatbot (evento/envio WA) |
| **E14** Reserva / status de veículo | Ativo (esboço 2026-07-14) | Estoque (+ Catálogo; Portal BFF) |
| **E15** Proposta / PDF da simulação | Ativo (esboço 2026-07-14) | Portal/Chatbot (formato) + Motor (dados) |
| **E16** Avaliação de troco | Ativo (esboço 2026-07-14) | Portal (+ opcional Chatbot) |
| **E17** Onboarding multi-loja / revenda | Ativo (esboço 2026-07-14) | Todos (ops + Task 10 Motor) |
| **E18** Domínio próprio no catálogo | Ativo (esboço 2026-07-14) | Catálogo + deploy |

---

## E1 — Áudio / multimodal (transcrição)

**O que é:** cliente manda **áudio** (ou imagem) no WhatsApp e o bot entende.

**Por quê:** grande parte dos clientes de loja manda áudio; hoje o bot só lê texto.

**Abordagem:**
- No workflow `Bot`, após o Webhook, classificar o tipo da mensagem (`conversation` vs `audioMessage`).
- Se áudio: baixar o arquivo (a Evolution entrega base64/URL), enviar para uma API de transcrição
  (OpenAI Whisper ou equivalente) e usar o texto transcrito como `texto` no fluxo normal.
- Imagem/documento: enviar para um modelo multimodal (Claude com visão) e extrair o conteúdo.

**Onde pluga:** somente no Chatbot (Plano #2A), antes do gate de handoff.

**Esforço/risco:** médio. Custo por transcrição; latência maior.

**Gatilho:** quando clientes reais começarem a mandar áudio com frequência.

---

## E2 — Busca de score de crédito (enriquecimento)

> **Status no roadmap: ADIADO.** Condizente com financiamento, mas **bloqueado por contrato de
> bureau + custo por consulta + LGPD reforçada**. Não priorizar até a loja (ou o produto revendido)
> ter base legal e fornecedor. Manter o esboço para não perder a ideia.

**O que é:** antes de simular de verdade, consultar um **score/bureau** (ex.: DirectD, Serasa,
Boa Vista) a partir do CPF, como a plataforma de referência faz ("busca score" via `api v3.directd`).

**Por quê:** confirma na prática o que já sabíamos — **CPF + nascimento não bastam**. O score
define elegibilidade e afina a simulação real. É o passo que falta entre coletar dados e ter uma
oferta de banco confiável.

**Abordagem:**
- Novo endpoint no serviço: `POST /score` `{cpf}` → `{score, faixa, ...}`, chamando o provedor
  contratado. Mockável primeiro (igual ao motor).
- O motor real (híbrido API + Playwright + agregador opcional — ver Plano #1A) pode usar o score
  como entrada do driver.

**Onde pluga:** Motor + opcionalmente Chatbot. O contrato de simulação pode ganhar `score`
opcional sem quebrar quem não usa. Credenciais de portal: UI no Portal (#3A Task 9A).

**Esforço/risco:** médio-alto. Exige **contrato com o bureau** (custo por consulta, LGPD reforçada).

**Gatilho:** depois do Plano #1A, junto do primeiro driver real e somente com contrato/base legal.

---

## E3 — Auto-pausa ao detectar o atendente

> **Status: FEITA (2026-07-13) — MVP.** `from_me`+`origem_bot`, ignore ack/status, n8n Extrair/Gate,
> testes handoff. Fase 2 opcional (reativar após X h silêncio) **não** feita.

**O que é:** completar o handoff (Plano #2A Task 7) para **pausar sozinho** quando o atendente
responde manualmente pelo WhatsApp — sem precisar clicar no portal. Deve funcionar inclusive no
**Chatbot Standalone** (sem Portal); o Portal continua podendo assumir/devolver manualmente.

**Por quê:** é o "Parar Resposta Agent" da referência; mais natural que o botão.

**Abordagem:**
- Detectar mensagens `fromMe = true` no payload da Evolution (a instância precisa **emitir** eventos
  `fromMe`; hoje o webhook trata inbound → habilitar/encaminhar `fromMe`).
- Deduplicar bot × humano: **registrar todo envio do bot** guardando o `provider_message_id` que a
  Evolution devolve ao enviar (reusando o mecanismo de dedupe de `provider_message_id` que o Chatbot
  já tem no webhook). Ao chegar um `fromMe`: se **casar** com um envio do bot → é eco do próprio bot
  (ignora); se **não** casar → é o atendente digitando no app → `bot_ativo=false` naquela conversa.
- Idempotência: **não** alternar o bot a cada eco/ack/status de entrega; ignorar reações/recibos. Só
  `fromMe` de conteúdo que não seja envio conhecido do bot dispara a pausa.
- Fase 2 (opcional, documentada): reativar o bot após X horas de silêncio do atendente.

**O que muda onde (explícito):**
- **Chatbot API (#2A) — é aqui que mora a lógica:** (a) ao **enviar** mensagem, persistir o
  `provider_message_id` do envio; (b) ramo `fromMe` no handler do webhook que consulta esse registro e
  aplica `bot_ativo=false` pelo mesmo caminho do handoff manual; (c) idempotência de ack/status.
- **n8n/Evolution:** garantir que a instância **entrega eventos `fromMe`** ao webhook (config Evolution
  + o nó de webhook não descartar `fromMe`). **Sem regra de negócio no n8n** — só encaminhar.

**Aceite:**
- Atendente manda 1 msg pelo celular → o bot para naquela conversa.
- Msg enviada pelo **próprio bot** (via API) **não** pausa (dedupe por `provider_message_id`).
- Ack/recibo/status/reação **não** alteram `bot_ativo`.
- Reativação manual pelo Portal continua funcionando; funciona no Chatbot Standalone (sem Portal).

**Esforço/risco:** médio. A deduplicação `fromMe` é a parte chata (rastrear os envios do bot com
confiabilidade do `provider_message_id` da Evolution).

**Gatilho:** quando o handoff manual do portal já estiver em uso e incomodar clicar.

---

## E4 — Roteador de intenção / multi-agente

> **Status no roadmap: ADIADO.** Com um fluxo dominante (financiamento + estoque), multi-agente
> só aumenta manutenção de n8n. **Gatilho real:** ≥3 jornadas distintas e estáveis em produção.
> Até lá, um agente + tools basta.

**O que é:** um "Direcionamento" (como na referência) que classifica a intenção e manda para
agentes especializados: `financiamento`, `vendas`, `test_drive`, `grupos`, etc.

**Por quê:** conforme o bot cresce, um único prompt fica sobrecarregado; separar melhora qualidade.

**Abordagem:**
- Nó de classificação (LLM) logo após o buffer → `Switch` por intenção → sub-workflows por agente
  (n8n "Execute Workflow").
- Cada agente é um workflow com seu próprio prompt e ferramentas.

**Onde pluga:** Chatbot (Plano #2A) vira um roteador + N sub-workflows. Outros produtos intactos.

**Esforço/risco:** médio-alto (mais workflows para manter).

**Gatilho:** quando houver ≥3 fluxos distintos bem definidos (hoje o financiamento sozinho justifica 1 agente).

---

## E5 — Cadastro de veículo via WhatsApp

> **Status: FEITA (2026-07-13) — fase 1 texto.** `POST /v1/operacao/veiculos`, números autorizados,
> CLI, tool n8n `cadastrar_veiculo1`. Foto real WhatsApp = **E6** (só `foto_url` opcional agora).

**O que é:** o dono/vendedor **adiciona um veículo ao estoque mandando mensagem** para o bot (texto e,
se possível, foto) — equivalente ao "Adiciona Veículo BD - Whatsapp" da referência.

**Por quê:** cadastrar estoque sem abrir o portal, direto do celular na loja. Disponível para **todos**
os clientes da suíte.

**Escopo comercial (importante):**
- **Suíte completa (com Portal):** WhatsApp **e** Portal são caminhos de cadastro; WhatsApp é conveniência.
- **Chatbot Standalone (sem Portal):** o WhatsApp é o **caminho canônico** de cadastro de estoque — não
  pode depender do HTML do portal. É o requisito mais forte desta feature.

**Abordagem:**
- **Números autorizados por loja** (dono/vendedor); número de cliente comum **não** cadastra (recusa).
  Lista/flag mantida no Chatbot, escopada por loja.
- `loja_id` do remetente vem da **instância Evolution** (cada loja = instância). Nunca cadastrar em loja
  errada (tenancy).
- Intenção clara/comando (ex.: "CG 160 2023 16000 placa ABC1D23") → extração dos campos por LLM
  (marca/modelo/ano/valor/km/**placa**) → chama **Estoque API `POST /v1/veiculos`** (privada) com a
  **credencial de serviço de escrita** da loja. Só HTTP; o Chatbot **não** grava veículo no próprio
  banco como fonte de verdade.
- **Placa** no desenho desde já (Estoque normaliza e tem `por-placa`); `Idempotency-Key` p/ não duplicar
  em reenvio.
- **Foto:** Fase 1 texto (+URL se houver); Fase 2 foto real via WhatsApp → upload/storage (depende de
  **E6**) → `foto_url`.
- Resposta no WhatsApp: **resumo do veículo criado/atualizado** ou **erro legível** ("faltou o valor",
  "placa inválida", "número não autorizado").

**O que muda onde:**
- **Chatbot (#2A):** ferramenta/agente `adicionar_veiculo` restrita por número; parsing; cliente HTTP de
  **escrita** no Estoque (hoje o `HttpInventoryProvider` é de leitura → precisa de credencial/escopo de escrita).
- **Estoque (#4A):** `POST /v1/veiculos` já existe; garantir escopo de credencial de serviço p/ o Chatbot
  escrever. Auditoria mínima (quem/quando) já é padrão do Estoque.

**Aceite:**
- Número autorizado + dados válidos → veículo criado no Estoque na loja certa; bot confirma o resumo.
- Número **não** autorizado → recusa, nada criado.
- Dados incompletos/ambíguos → erro legível pedindo o que falta; nada criado.
- Reenvio idêntico não duplica (idempotência). Funciona no Chatbot Standalone (sem Portal).

**Riscos:** parsing ambíguo (mitigar pedindo **confirmação antes de gravar**); número não autorizado
(negar cedo); foto grande/formato (limitar tamanho; Fase 2).

**Esforço/risco:** médio (parsing + autorização + credencial de escrita no Estoque).

**Gatilho:** para Chatbot-only é caminho de **dia 1**; para a suíte, quando o cadastro pelo portal for gargalo.

---

## E6 — Upload real de fotos + página de detalhe do veículo

**O que é:** hoje `foto_url` é um link manual. Evoluir para **upload** de fotos (portal e/ou
WhatsApp) e uma página de detalhe na vitrine (`/l/{loja_id}/v/{id}`) com galeria.

**Abordagem:**
- Armazenamento de objetos (S3/MinIO/Cloudflare R2) ou volume; guardar a URL em `foto_url`
  (ou uma tabela `veiculo_fotos` para múltiplas).
- Página de detalhe no catálogo público (Plano #5A).

**Onde pluga:** Estoque API é dona de `veiculo_fotos`; Catálogo apenas consome URLs/metadados;
Portal pode oferecer uma interface cliente da API.

**Esforço/risco:** médio.

**Gatilho:** quando a vitrine (Produto C) for pra produção de verdade.

---

## E7 — Analytics avançado e projeção de simulações

> **Status no roadmap: ADIADO.** Relatórios do #3B (vendas, metas, funil, CSV) cobrem o dia a dia.
> Coorte/projeção só vale com **volume real** de sims e vendas. Não competir com Task 4/5 nem E8.

**O que é:** após os Planos #3A/#3B, projetar no Portal o estado resumido das simulações e criar
análises avançadas de coorte, tempo por etapa e reconciliação. O Motor continua dono da simulação;
o Portal guarda referência/projeção, não copia payload pessoal bancário.

**Onde pluga:** eventos/API do Motor → projeção idempotente do Portal.

**Esforço/risco:** baixo-médio.

**Gatilho:** quando o volume tornar relatórios operacionais dos Planos #3A/#3B insuficientes.

---

## E8 — Atribuição e retorno de campanhas

**O que é:** evoluir campanhas do Plano #3B para importar custos e comparar origem, lead, venda e
lucro bruto por canal, mantendo `first_touch` e `last_touch` explícitos.

**Onde pluga:** Portal. Catálogo e Chatbot apenas emitem UTMs/eventos padronizados.

**Gatilho:** quando houver campanhas reais com custos e volume suficiente para decisão.

---

## E9 — Gestão de redes sociais e tráfego — FORA DO CORE

> **Status: REMOVIDO DO ROADMAP ATIVO (2026-07-14).**  
> Agendar posts / gerir Instagram-Facebook como produto **não é o CRM da revenda** (simulação +
> estoque + WhatsApp + vendas). Meta Business, Buffer e similares já cobrem isso.  
> **Não implementar** salvo pedido explícito do dono com escopo comercial novo (outro produto).  
> Tráfego pago **mensurável** continua via **E10** (Pixel/CAPI) + **E8** (ROI), sem virar social suite.

~~Conectores de publicação, alertas e automação de anúncio.~~

---

## E10 — Pixel Meta / aba Tráfego (eventos de conversão)

> **Status: FEITA (2026-07-13) — MVP.** Portal `/app/trafego` + CAPI Purchase no confirm venda +
> catálogo PageView/Lead. Residual: retry worker outbox, sync Pixel ID, phone hash, toggles no catálogo.

**O que é:** dono/gerente configura no **Portal** uma aba **Tráfego** para o **Pixel da Meta**
(Facebook/Instagram Ads) e dispara eventos de conversão — sobretudo **venda** — para medir e otimizar
anúncios. **MVP: só Meta.**

**Por quê:** hoje a loja roda anúncio sem devolver conversão à Meta; sem `Purchase`/`Lead` o algoritmo
do Ads não otimiza. É o building block concreto que alimenta a atribuição do **E8**.

**Decisões de produto:**
- Aba **Tráfego** no Portal — papéis **dono/gerente**; **vendedor não** vê tokens.
- Config por loja: **Pixel ID** + **token CAPI** (Conversions API), **Test Event Code** opcional, e
  liga/desliga por evento.
- **Site (Catálogo público):** **Pixel browser** — `PageView` no load e, no **CTA WhatsApp**, evento
  **Lead** (preservar UTM/`CAT-*` já existentes).
- **Venda:** ao **confirmar venda no Portal (#3B)** → **Purchase via CAPI (servidor)** com valor/moeda
  quando houver. **Não** tratar clique no WhatsApp como Purchase. Ideal: Lead no clique + Purchase na venda.
- **Segredos:** token CAPI cifrado no servidor; **nunca** no front do catálogo nem no git. O **Pixel ID**
  é público (vai no browser); o token CAPI é server-only.
- **Dedupe de evento:** o mesmo evento pode sair pelo Pixel (browser) e pela CAPI (servidor) → enviar
  **`event_id` compartilhado** para a Meta deduplicar (obrigatório; senão conta em dobro).
- **Resiliência:** falha na CAPI **não** pode quebrar o fluxo de venda — envio assíncrono best-effort com
  retry (padrão outbox, como o do Catálogo), fora do caminho crítico da confirmação.

**Escopo comercial (Chatbot-only vs suíte):**
- **Suíte (Portal + Catálogo):** feature completa — config, PageView/Lead no site, Purchase na venda.
- **Chatbot Standalone (sem Portal/Catálogo):** pixel de **site** e **Purchase na venda** ficam
  **limitados/indisponíveis** (não há vitrine nem confirmação de venda no Portal). Opcional documentado:
  emitir `Lead` via CAPI quando um lead é criado no Chatbot. Deixar explícito o que **exige Catálogo+Portal**.

**Onde pluga:**
- **Portal (#3B):** aba Tráfego (config cifrada por loja) + gancho no "confirmar venda" → CAPI `Purchase`.
- **Catálogo (#5A):** injeta o Pixel (browser) — `PageView` + `Lead` no CTA, com `event_id` e UTM/`CAT-*`.
- **Meta CAPI:** integração HTTP server-side (Graph API `/events`).

**Tasks (esboço):**
1. Portal: modelo de config Meta por loja (Pixel ID, token CAPI cifrado, test code, toggles) + aba
   Tráfego (RBAC dono/gerente; token mascarado na leitura).
2. Portal: mecanismo de **segredo em repouso** (cifra do token CAPI — o Portal ainda não tem; definir).
3. Catálogo: injeção do Pixel + `PageView` + `Lead` no CTA com `event_id`/UTM (Pixel ID via config pública da loja).
4. Portal: no "confirmar venda", enfileirar `Purchase` (valor/moeda, `event_id`, identificadores
   disponíveis) → worker/outbox CAPI com retry.
5. Testes: config salva/mascarada; Lead no CTA; Purchase na confirmação; **falha CAPI não quebra a
   venda**; dedupe por `event_id`.

**Aceite:**
- Config salva por loja (token **mascarado** na leitura; vendedor sem acesso).
- Catálogo dispara `PageView` no load e `Lead` no CTA WhatsApp (com UTM/`CAT-*`).
- Confirmar venda no Portal dispara `Purchase` via CAPI com valor/moeda quando houver.
- Pixel + CAPI do mesmo evento não contam em dobro (dedupe por `event_id`).
- Erro/timeout da CAPI **não** impede registrar a venda (vai pra retry).

**Fora (evolução, não MVP):** Google/TikTok; criar campanha no Ads Manager; ROI completo com custo
importado (→ **E8**).

**Esforço/risco:** médio. Risco de dado (token) e de contagem dupla (mitigados por cifra + `event_id`).

**Gatilho:** quando a loja rodar tráfego pago de verdade e precisar otimizar por conversão.

---

## E11 — WhatsApp em massa (broadcast / disparo)

> **Status: NÃO INICIADO (esboço 2026-07-14).** Depende de go-live estável do bot (Evolution → n8n
> → Chatbot) e de regras claras de opt-out. Complementa **#3B Task 5** (campanha como entidade de
> marketing) e alimenta **E8** (atribuição). **Não** substitui o fluxo 1:1 do agente IA.

**O que é:** o dono/gerente monta uma **mensagem em massa** (lista de leads ou segmento) e dispara
pelo **mesmo número WhatsApp da loja**, com fila, limite de ritmo e relatório de entrega — sem
copiar/colar no celular.

**Por quê:** revenda usa WhatsApp como canal principal (promoção de estoque, “chegou CG 160”,
reengajar leads frios). Hoje só existe conversa reativa (webhook) e tools do agente; não há outbound
controlado pela loja.

### Princípios (alinhados à suíte)

1. **Chatbot é dono do canal WhatsApp** — só ele fala com a Evolution (como no inbound). O Portal
   **nunca** grava token Evolution nem manda mensagem direto.
2. **Portal é a UI de campanha** (suíte completa): dono/gerente cria rascunho, escolhe público,
   agenda, aprova e acompanha status. Vendedor **não** dispara massa (RBAC).
3. **Integração só HTTP:** Portal → `POST /v1/campanhas/whatsapp` (Chatbot) com escopo de loja +
   token de serviço. Chatbot **não** lê o Postgres do Portal.
4. **Chatbot Standalone (sem Portal):** CLI + endpoints mínimos no Chatbot
   (`criar-campanha` / `disparar` / `status`) — mesmo contrato; a UI rica é opcional.
5. **Não usar n8n como motor de fila em massa.** n8n orquestra o bot 1:1; broadcast usa
   **outbox/worker no Chatbot** (mesmo padrão de resiliência do outbox do Estoque/CAPI): retry,
   idempotência, ritmo.
6. **Campanha = entidade de marketing** compartilhada conceitualmente com #3B Task 5 / E8:
   `canal=whatsapp`, UTM/`CAMP-*` no texto ou deep-link do catálogo, para fechar atribuição depois.
   Cadastro “só métrica” (Task 5) pode existir antes do envio real (E11).

### Público (audiência)

Fontes **no Chatbot** (dono dos telefones/leads/conversas):

| Segmento (MVP) | Regra |
|---|---|
| Lista explícita | telefones colados / CSV (normalizados E.164) |
| Leads da loja | filtro: etapa, data de criação, tags, “sem venda” |
| Conversas | `bot_ativo` / última msg há N dias (reativação) |
| Opt-out | **excluir** quem pediu para sair (ver abaixo) |

Portal **não** espelha a lista de telefones no próprio banco como fonte de verdade: envia filtros
ou IDs de lead conhecidos via API; o Chatbot resolve e materializa a fila.

### Conteúdo e templates

- MVP: texto simples + variáveis (`{{nome}}`, `{{modelo}}`, link `/l/{loja}` do Catálogo).
- Fase 2: mídia (imagem do veículo) — depende de **E6** se a foto for do estoque.
- Rodapé obrigatório de marketing: instrução de opt-out (ex.: “responda SAIR para não receber”).
- **Risco de ban (Evolution / WhatsApp não-oficial):** disparo agressivo queima o número.
  Documentar limites conservadores (ex.: N msgs/min, janela comercial, aquecimento) e preferir
  listas **opt-in** (clientes que já falaram com a loja). Se no futuro migrar para **WhatsApp Cloud
  API** com templates HSM, o mesmo contrato de campanha permanece; só o adapter de envio muda.

### Opt-out e LGPD

- Tabela no Chatbot: `preferencias_contato(loja_id, telefone, whatsapp_marketing=bool, …)`.
- Inbound com palavra-chave (`SAIR`, `PARAR`, `STOP`) → `whatsapp_marketing=false` **antes** de
  qualquer lógica de agente (gate no webhook, fail-closed no próximo disparo).
- Consentimento de marketing **separado** do consentimento opcional de simulação já existente:
  não reutilizar o flag genérico sem finalidade explícita.
- Auditoria: quem criou a campanha, texto versionado, horário, contagens (enviado/falha/opt-out).

### Interação com E3 (auto-pausa) e o bot 1:1

- Toda msg de campanha grava `origem_campanha=true` (ou `origem=broadcast`) +
  `provider_message_id` no mesmo dedupe de envio do bot.
- Eco `fromMe` da Evolution **não** deve pausar o bot se casar com envio de campanha (mesmo
  mecanismo de E3 para `origem_bot`).
- Se o cliente **responder** a uma campanha: conversa normal; se o bot estiver ativo, o agente
  atende; se o atendente assumiu, handoff permanece. Opcional: tag `origem_campanha_id` no lead
  para #3B/E8.

### Contrato esboço (Chatbot)

```
POST /v1/campanhas/whatsapp
  { nome, texto_template, segmento|telefones[], agendar_em?, ritmo_por_minuto?, utm? }
  → { campanha_id, status: rascunho|agendada|em_fila|concluida|cancelada, total_destinatarios }

POST /v1/campanhas/whatsapp/{id}/disparar   # confirmação explícita (não dispara no create)
GET  /v1/campanhas/whatsapp/{id}           # contadores: enfileirados, enviados, falhas, opt_outs
POST /v1/campanhas/whatsapp/{id}/cancelar  # para a fila; não “desenvia” o já entregue
```

Worker: processa outbox `envio_whatsapp` com lease, rate-limit por loja/instância Evolution,
backoff em 429/erro de sessão.

### UI (Portal)

- Aba **Campanhas** (ou subaba de Marketing): canal WhatsApp | E-mail (E12).
- Papéis: **dono/gerente** criam e disparam; vendedor no máximo vê contadores da loja (decisão
  de produto na implementação).
- Preview do texto, estimativa de destinatários, confirmação “enviar para N contatos”.
- Link opcional para veículo do Estoque (HTTP) → URL do Catálogo com UTM.

### Aceite

- Disparo para N telefones elegíveis com ritmo configurável; opt-out nunca recebe.
- Cancelamento para a fila restante.
- Eco de campanha não altera `bot_ativo` indevidamente (E3 intacto).
- Portal sem Evolution: se Chatbot offline, campanha fica em erro legível; **não** há fallback
  gravando WA em outro produto.
- Chatbot Standalone: mesmo fluxo via API/CLI sem Portal.

### Fora de escopo (E11)

- Disparo multi-instância / multi-número com balanceamento.
- Templates HSM oficiais da Meta (futuro adapter).
- Sequências de nurturing multi-dia (pode reusar campanha + agendamento depois).
- SMS.

**Esforço/risco:** médio-alto (fila, ToS/ban, opt-out, RBAC).  
**Gatilho:** depois do go-live WhatsApp estável e de a loja ter base de leads real para reengajar.

---

## E12 — Campanhas por e-mail

> **Status: NÃO INICIADO (esboço 2026-07-14).** Irmão do **E11** no mesmo módulo de **Campanhas**
> do Portal. Envio **não** passa pelo Chatbot (canal diferente); audiência de leads pode vir do
> Chatbot via HTTP. Atribuição fecha com **#3B Task 5** + **E8**.

**O que é:** montar e-mail de marketing/transacional leve (oferta de estoque, “sua simulação”,
newsletter da loja), enviar por provedor SMTP/API, e medir abertura/clique o suficiente para
ligar a campanha ao funil — sem virar Mailchimp completo no dia 1.

**Por quê:** nem todo lead responde no WhatsApp; e-mail cobre follow-up formal, segundo contato e
clientes que preferem não receber blast no celular. Complementa o WA sem misturar canais no mesmo
adapter.

### Princípios (alinhados à suíte)

1. **Portal é dono da campanha de e-mail e do envio** (config do provedor por loja, fila/outbox no
   Portal ou worker dedicado do Portal). Chatbot **não** vira ESP (e-mail service provider).
2. **Audiência:** preferir leads com e-mail. Hoje o modelo de lead é forte em **telefone**; E12
   exige **e-mail opcional no lead** (Chatbot) e/ou contatos importados no Portal com finalidade
   marketing. Leitura de leads: Portal → `GET /v1/leads?…` (já existe o espírito BFF); **sem**
   SQL cruzado.
3. **Mesma aba Campanhas** do E11: um cadastro de campanha com `canal ∈ {whatsapp, email, ads…}`.
   Task 5 (#3B) cobre metadados (nome, UTM, custo, período); E11/E12 cobrem **execução**.
4. **Chatbot Standalone:** e-mail em massa **não é obrigatório** no pacote “só bot”. Se a loja
   quiser e-mail sem Portal, fica como add-on futuro (CLI no Portal mínimo ou provedor externo).
   Documentar: **E12 assume suíte com Portal** no MVP.
5. **Segredos:** API key SMTP/Resend/SendGrid cifrada no Portal (mesmo padrão da Task 9A / token
   CAPI) — nunca no front nem no Catálogo.
6. **Catálogo:** links no corpo do e-mail apontam para `/l/{loja}` com UTM; Pixel (E10) continua no
   site. E-mail não injeta Pixel no cliente de e-mail de forma invasiva no MVP (só link + UTM).

### Provedor e entrega

- Adapter `EmailProvider` (interface): `enviar(para, assunto, html|texto, tags_campanha)`.
- MVP: um provedor (ex. Resend ou SMTP genérico); mock nos testes.
- Outbox no Portal: `status=pendente|enviado|falha`, retry, **não** bloquear a UI no submit.
- Rate limit e bounce básico (marcar e-mail inválido para não reenviar).

### Opt-in / opt-out e LGPD

- Finalidade `email_marketing` separada; não enviar para quem não tem e-mail ou opt-out.
- Link de descadastro no rodapé (token assinado → endpoint público do Portal
  `POST /public/email/descadastrar` ou página simples) → grava preferência **por loja**.
- Se o e-mail veio do lead no Chatbot, o Portal propaga opt-out via HTTP
  (`PATCH` preferência) **ou** mantém preferência local de e-mail no Portal e o Chatbot só
  abastece contatos — decidir na implementação, mas **uma** fonte canônica por canal:
  - WhatsApp marketing → Chatbot (E11)
  - E-mail marketing → Portal (E12), com espelho opcional no lead

### Conteúdo (MVP)

- Assunto + corpo HTML simples (template da loja: logo/nome).
- Variáveis: nome, link catálogo, 1–3 veículos em destaque (dados via Estoque HTTP no momento do
  preview/envio, não snapshot eterno de preço sem atualizar).
- Preview e envio de teste para o e-mail do dono antes do disparo.

### Contrato esboço (Portal interno + APIs)

```
# Config (dono/gerente)
PUT  /app/campanhas/email/config     # provedor, from_name, from_email (token cifrado)
GET  /app/campanhas/email/config     # token mascarado

# Campanha (HTML do Portal; APIs JSON se útil para testes)
POST /app/campanhas                  # canal=email, assunto, corpo, segmento|lista
POST /app/campanhas/{id}/disparar
GET  /app/campanhas/{id}             # enviados / falhas / descadastros
```

Eventos mínimos para E8 depois: `email_enviado`, `email_falhou`, `email_descadastro`;
abertura/clique (fase 2, pixel 1×1 ou redirect de link) **opcional** no MVP.

### Aceite

- Config de provedor salva cifrada; vendedor não vê segredo.
- Disparo só para destinatários com e-mail e sem opt-out; contadores reconciliam com o outbox.
- Link de descadastro funciona sem login e impede reenvio.
- Campanha com `canal=email` aparece no mesmo lugar conceitual que WhatsApp (E11) e alimenta
  o cadastro de campanhas do #3B (nome, UTM, custo manual se houver).
- Falha do provedor **não** corrompe venda/lead; fica no outbox com erro legível.

### Fora de escopo (E12)

- Builder drag-and-drop de e-mail.
- Automação complexa (jornada por score/etapa) — reusa campanha + regras depois.
- SMTP “da própria caixa Gmail do vendedor” como solução suportada (frágil; só se adapter
  explícito de risco).
- WhatsApp misturado no mesmo job de e-mail (canais separados; campanha “multi-canal” = 2 jobs).

**Esforço/risco:** médio (provedor + LGPD + modelo de e-mail no lead).  
**Gatilho:** quando a loja tiver e-mails de clientes e quiser follow-up além do WhatsApp; ideal
depois ou em paralelo ao cadastro de campanhas (#3B Task 5).

---

## E11 + E12 — visão conjunta (Campanhas outbound)

| | **E11 WhatsApp** | **E12 E-mail** |
|---|---|---|
| Dono do envio | Chatbot → Evolution | Portal → provedor e-mail |
| UI principal | Portal (suíte) / API+CLI (standalone) | Portal (MVP suíte) |
| Público | telefones / leads Chatbot | e-mails (lead + lista) |
| Opt-out canônico | Chatbot (`SAIR` no WA) | Portal (link descadastro) |
| Fila | outbox Chatbot | outbox Portal |
| Atribuição | `campanha_id` + UTM → #3B / E8 | idem |
| Risco principal | ban do número WA | bounce / spam / LGPD e-mail |

**Ordem interna sugerida:** (1) modelo de campanha no Portal (#3B Task 5, metadados) →
(2) **E11** se WhatsApp já é o canal da loja → (3) **E12** quando houver e-mails e provedor.
Os dois compartilham tela e `campanha_id`; não compartilham adapter de envio.

---

## E13 — Notificação interna de lead / handoff

> **Status: APROVADO pelo dono 2026-07-14 (era C1).** Esboço — vira plano de implementação quando
> priorizado. Depende de go-live WA razoável se o canal de aviso for WhatsApp.

**O que é:** quando nasce um **lead novo** ou o bot faz **handoff** (cliente pediu humano /
`bot_ativo=false`), o sistema **avisa a equipe** (dono/gerente/vendedor responsável) por
**WhatsApp e/ou e-mail**, configurável por loja — sem depender de ficar com o Portal aberto.

**Por quê:** o funil morre se o lead chega e ninguém vê. A loja vive no celular; notificação
interna fecha o ciclo Chatbot → humano.

### Princípios

1. **Chatbot emite o evento** (dono de lead/conversa/handoff): `lead_criado`, `handoff_solicitado`,
   opcional `primeira_mensagem` se ainda não houver lead.
2. **Portal guarda preferências da loja** (suíte): quem recebe, canal (WA / e-mail / ambos),
   horário silencioso opcional. Vendedor só recebe o que for da sua responsabilidade quando houver
   atribuição; senão dono/gerente.
3. **Envio WhatsApp interno:** Chatbot → Evolution (mesmo adapter de envio; **não** é campanha E11).
   Números de equipe ≠ clientes; lista separada (`destinatarios_internos` por loja).
4. **Envio e-mail:** Portal (ou Chatbot se standalone sem Portal) via provedor simples — pode reusar
   adapter de **E12** quando existir; MVP pode ser só WA.
5. **Chatbot Standalone:** CLI/env com telefones internos + toggle; sem UI rica do Portal.
6. **Idempotência:** um handoff não dispara 10 avisos (dedupe por `conversa_id` + tipo + janela).
7. **Não** pausar o bot por eco dessas msgs se forem `origem_sistema`/`origem_notificacao` (mesmo
   espírito do E3).

### Conteúdo mínimo do aviso

- Tipo: lead novo / handoff  
- Telefone do cliente (e nome se houver)  
- Resumo curto (última mensagem ou interesse)  
- Link opcional para o Portal (`/app/conversas/...` ou `/app/leads/...`) quando suíte  

### Aceite

- Handoff → destinatário configurado recebe 1 aviso; reenvio/eco não multiplica.
- Lead criado via tool/API → aviso se toggle ligado.
- Preferências por loja; vendedor sem config de tokens Evolution.
- Falha de envio não quebra o webhook do cliente (best-effort + log).

**Esforço/risco:** baixo-médio.  
**Gatilho:** assim que o bot estiver respondendo de verdade e a loja reclamar que “não vi o lead”.

---

## E14 — Reserva / status de veículo

> **Status: APROVADO pelo dono 2026-07-14 (era C3).** Esboço — implementação no Estoque (fonte de
> verdade); Catálogo e Portal só consomem.

**O que é:** ciclo de vida explícito do veículo no estoque além de “disponível/indisponível”:
**disponível → reservado → vendido** (e cancelamento de reserva). Reserva tem **prazo**, **quem
reservou** (vendedor/loja) e opcionalmente lead/cliente vinculado.

**Por quê:** na revenda, dois vendedores não podem “vender” a mesma unidade; o catálogo não deve
continuar empurrando CTA de moto já comprometida.

### Princípios

1. **Estoque API é dona do status** (`status` ou máquina de estados). Portal só chama HTTP.
2. **Catálogo** lista por padrão só `disponível` + `publicado`; `reservado` some **ou** exibe
   selo “Reservado” sem CTA WhatsApp (decisão na implementação; default sugerido: **ocultar**).
3. **Reserva expira:** job/cron leve no Estoque devolve para `disponível` se `reservado_ate` passou
   sem venda/confirmacão.
4. **Venda no Portal (#3B):** confirmar venda → Estoque `vendido` (HTTP); cancelar venda pode
   reabrir conforme política.
5. **Chatbot/consulta estoque:** `buscar` / `por-placa` não oferecem unidade `reservada`/`vendida`
   como disponível (mesmo contrato Lite).
6. Auditoria: quem reservou/liberou, quando.

### Aceite

- Reservar unidade remove (ou bloqueia CTA) no catálogo público após sync/outbox.
- Dois POSTs de reserva concorrentes: só um ganha (condicional no status).
- Expiração devolve a `disponível` sem intervenção manual.
- Standalone Estoque funciona sem Portal (CLI/API); Portal é UI conveniente.

**Esforço/risco:** médio (estados + race + catálogo).  
**Gatilho:** quando houver mais de um vendedor ou estoque com giro real.

---

## E15 — Proposta / PDF (ou link) da simulação

> **Status: APROVADO pelo dono 2026-07-14 (era C4).** Esboço.

**O que é:** após uma simulação concluída (Portal ou bot), gerar um **resumo apresentável** —
PDF e/ou **link público temporário** — com opções por banco (parcela, prazo, entrada quando
houver), dados do veículo e identificação da loja, para o vendedor **mandar ao cliente no
WhatsApp**.

**Por quê:** JSON/tela do Portal não é o que o cliente leva para casa; a loja precisa de algo
compartilhável e legível.

### Princípios

1. **Motor continua dono** do resultado bruto; **não** grava PDF no Motor se puder evitar.
2. **Portal (suíte)** gera o artefato a partir de `GET` simulação (token servidor) — HTML→PDF ou
   página assinada `/p/{token}` com TTL.
3. **Chatbot/bot:** tool ou formatação texto rica no WA no MVP; PDF/link na fase 2 se o Portal
   expuser URL ou o Chatbot gerar HTML simples sem PII extra em log.
4. **PII:** CPF mascarado na proposta ao cliente; não expor payload cifrado cru.
5. **Marca da loja:** nome/logo opcional (config Portal); sem white-label multi-tenant complexo no MVP.
6. Link público: token opaco, expira, só leitura, escopo loja.

### Aceite

- A partir de simulação `concluida`, vendedor obtém PDF ou link com multi-prazo/bancos ok.
- CPF não aparece completo no artefato.
- Link expirado retorna 404/410.
- Falha de geração não apaga a simulação no Motor.

**Esforço/risco:** médio (PDF/link + PII + TTL).  
**Gatilho:** quando simulação real (Santander) estiver em uso diário com cliente.

---

## E16 — Avaliação de troco (veículo do cliente)

> **Status: APROVADO pelo dono 2026-07-14 (era C6).** Esboço.

**O que é:** registrar o veículo que o cliente **quer dar na troca** (marca, modelo, ano, km,
estado, valor estimado de avaliação e/ou valor pretendido pelo cliente), ligado a **lead** e/ou
**venda**. Fase 2 opcional: bot coleta esses campos no WhatsApp.

**Por quê:** na seminova, a negociação quase sempre tem troco; hoje isso fica em mensagem solta
e some do CRM.

### Princípios

1. **Portal é dono do registro de avaliação** na suíte (dado comercial da loja), não o Estoque
   (Estoque = unidades **à venda** da loja).
2. Campos mínimos: identificação do bem, km, ano, `valor_avaliado`, `valor_oferecido_cliente`,
   status (`rascunho|avaliado|aceito_na_venda|recusado`), notas.
3. Na **venda (#3B)**: opcional vincular avaliação → compõe negociação (não precisa entrar no
   lucro bruto automaticamente no MVP; pode ser só referência + custo/ajuste manual).
4. **Chatbot (fase 2):** tool `registrar_troco` → HTTP no Portal **ou** campos no lead do Chatbot
   exportáveis; preferir não duplicar fonte de verdade. Se standalone sem Portal: campos no lead.
5. **Não** é FIPE automática no MVP (pode ser evolução com provider depois).

### Aceite

- Criar/editar avaliação ligada a lead; listar no detalhe do lead.
- Venda pode referenciar uma avaliação.
- Sem FIPE obrigatória; valor é humano.
- Fase 1 só Portal já fecha o aceite.

**Esforço/risco:** baixo-médio.  
**Gatilho:** quando vendas reais com troco começarem a ser registradas no Portal.

---

## E17 — Onboarding multi-loja / revenda (produto instalável)

> **Status: APROVADO pelo dono 2026-07-14 (era C9).** Esboço. Une e estende a **Task 10 do Motor**
> e equivalentes de Chatbot/Estoque/Portal — “revendível de verdade”, não só lab de uma loja.

**O que é:** checklist e ferramentas para **subir uma loja cliente nova**: tenant/`loja_id`,
usuário dono, tokens de serviço, credenciais Motor, instância Evolution, webhooks n8n, health
por produto e smoke mínimo (login Portal, estoque vazio, bot eco).

**Por quê:** sem isso a suíte é “funciona na Moto Center”; não é produto que você entrega a
outra revenda em horas.

### Princípios

1. **Cada produto** já tem tenancy; E17 é o **roteiro + automação** (CLI/scripts/docs), não um
   monólito central.
2. Motor **Task 10** (clientes API, isolamento) é fatia obrigatória; Portal: criar loja+dono;
   Chatbot: loja+token+webhook; Estoque: loja+credencial escrita.
3. **Segredos** gerados e entregues fora do git (mesmo espírito do Fly `.env.production.local`).
4. **Pacotes comerciais** do índice (#2A atendimento vs financiamento, etc.) viram **perfis de
   install** (quais containers sobem).
5. Lab Fly de uma org pode continuar single-Postgres; **doc de revenda** recomenda Postgres
   (ou schema/DB) por cliente quando for SaaS real.

### Aceite

- Runbook “loja nova do zero” executável em ambiente limpo.
- Smoke: health de todos os produtos do pacote escolhido + 1 login dono.
- Segunda loja no mesmo deploy **não** vê dados da primeira (teste de tenancy).
- Task 10 Motor fechada ou explicitamente coberta pelo runbook.

**Esforço/risco:** alto (ops + todos os produtos).  
**Gatilho:** quando for vender para a **segunda** loja ou embalar SaaS.

---

## E18 — Domínio próprio no catálogo

> **Status: APROVADO pelo dono 2026-07-14 (era C11).** Esboço / ops.

**O que é:** a vitrine pública da loja responde em **domínio próprio** (ex.: `motos.lojadfulano.com.br`
ou `catalogo.lojadfulano.com.br`), com TLS, não só `*.fly.dev`. Path `/l/{loja}` (ou host→loja)
continua resolvendo o catálogo correto.

**Por quê:** link no Instagram/anúncio com domínio da loja passa confiança; `fly.dev` parece lab.

### Princípios

1. **Catálogo** é o app público; DNS/TLS no provedor (Fly certificates, Cloudflare, etc.).
2. **Multi-loja:** (a) um host por loja com `loja_id` fixo na config, ou (b) host genérico + path
   `/l/{slug}` — documentar os dois; MVP de uma loja = host único + redirect raiz.
3. Links de CTA WhatsApp, Pixel (E10) e UTM continuam válidos no domínio custom.
4. Portal/Motor **não** precisam de domínio custom no MVP desta feature.
5. Segredos/certificados fora do git; runbook em `deploy/`.

### Aceite

- HTTPS no domínio da loja serve a vitrine com veículos publicados.
- CTA WhatsApp e Pixel funcionam no domínio custom.
- Documentado no deploy (passos DNS + `fly certs` ou equivalente).

**Esforço/risco:** baixo-médio (quase só ops).  
**Gatilho:** quando a loja for usar o catálogo em anúncio/rede de verdade.

---

## Ordem sugerida de ataque (depois do MVP)

### Roadmap ativo (foco da suíte)

| # | Item | Status 2026-07-14 |
|---:|---|---|
| — | **E3** auto-pausa | **Feito** |
| — | **E5** cadastro WhatsApp fase 1 | **Feito** (foto = E6) |
| — | **E10** Pixel Meta MVP | **Feito** |
| 1 | Go-live WhatsApp E2E | Ops (`docs/go-live-chatbot.md`) — base para E11 |
| 2 | #3B Task 4–5 (funil + campanhas metadados) | Portal — base para E8/E11/E12 |
| 3 | **E1** áudio | Aberto (uso diário do bot) |
| 4 | **E6** upload fotos | Aberto (vitrine + E5 foto) |
| 5 | **E8** atribuição / ROI | Aberto (após Task 5 + volume) |
| 6 | **E13** notificação interna lead/handoff | **Aprovado** (esboço); priorizar cedo pós go-live |
| 7 | **E14** reserva / status veículo | **Aprovado** (esboço); Estoque + Catálogo |
| 8 | **E15** proposta / PDF simulação | **Aprovado** (esboço) |
| 9 | **E16** avaliação de troco | **Aprovado** (esboço); Portal |
| 10 | **E17** onboarding multi-loja / revenda | **Aprovado** (esboço); Task 10+ |
| 11 | **E18** domínio próprio catálogo | **Aprovado** (esboço); ops |
| 12 | **E11** WhatsApp em massa | Aberto (após go-live WA estável) |
| 13 | **E12** campanhas e-mail | Aberto (suíte Portal) |

### Adiado (não puxar sprint)

| Item | Motivo |
|---|---|
| **E2** score | Contrato bureau + LGPD + custo |
| **E4** multi-agente | Prematuro com 1 fluxo dominante |
| **E7** analytics avançado | #3B basico basta até ter volume |

### Fora do core

| Item | Motivo |
|---|---|
| **E9** redes sociais | Outro produto; usar Meta Business etc. |

**Evoluções E10 residual:** worker retry outbox CAPI; hash telefone no Purchase; sync Pixel ID
Portal↔Catálogo; toggles PageView/Lead lidos pelo catálogo.

> **Chatbot-only:** E5 é caminho canônico de cadastro (sem Portal) — **já disponível** via API/tool.
> **E11** também faz sentido no standalone (API/CLI). **E12** no MVP é feature de **suíte (Portal)**.

---

## Backlog candidato — alta aderência (só após confirmação do dono)

Itens que **encaixam** na suíte (revenda + WA + estoque + simulação + gestão), mas **ainda não**
estão no roadmap numerado. Regra: o dono confirma **um a um**; só os aprovados viram **E13+**
(ou task em plano de produto) com esboço completo.

| ID temp | Ideia | Produto(s) | Notas |
|---|---|---|---|
| ~~C1~~ | ~~Notificação interna de lead~~ | — | **→ E13 aprovado** |
| ~~C2~~ | ~~Tarefas / follow-up do vendedor~~ | — | **Rejeitado pelo dono 2026-07-14** |
| ~~C3~~ | ~~Reserva / status de veículo~~ | — | **→ E14 aprovado** |
| ~~C4~~ | ~~Proposta / PDF da simulação~~ | — | **→ E15 aprovado** |
| ~~C5~~ | ~~Agenda de test-drive / visita~~ | — | **Rejeitado pelo dono 2026-07-14** |
| ~~C6~~ | ~~Avaliação de troco~~ | — | **→ E16 aprovado** |
| ~~C7~~ | ~~Respostas rápidas no Portal~~ | — | **Rejeitado pelo dono 2026-07-14** |
| ~~C8~~ | ~~WhatsApp Cloud API oficial~~ | — | **Rejeitado pelo dono 2026-07-14** |
| ~~C9~~ | ~~Onboarding multi-loja / revenda~~ | — | **→ E17 aprovado** |
| ~~C10~~ | ~~Backup/restore + runbook~~ | — | **Rejeitado pelo dono 2026-07-14** |
| ~~C11~~ | ~~Domínio próprio no catálogo~~ | — | **→ E18 aprovado** |
| ~~C12~~ | ~~Kanban de atendimento~~ | — | **Rejeitado pelo dono 2026-07-14** |

**Aprovados:** **E13**–**E18** (notif, reserva, PDF, troco, onboarding, domínio catálogo).  
**Rejeitados:** **C2** tarefas; **C5** agenda; **C7** respostas rápidas; **C8** Cloud API;
**C10** backup/runbook; **C12** kanban.

> Confirmação do backlog C1–C12 **encerrada** em 2026-07-14. Novas ideias = nova rodada com o dono.
