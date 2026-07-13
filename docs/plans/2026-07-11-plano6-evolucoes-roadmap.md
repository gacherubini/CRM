# Plano #6 — Evoluções (roadmap)

> **Regra de produto:** toda evolução declara em qual produto vive e integra os demais somente por
> contrato. Nenhum item futuro pode transformar Portal, Catálogo ou Motor em dependência obrigatória
> do Chatbot Standalone.

> **Natureza deste documento:** diferente dos Planos #1–#5, este é um **roadmap** de evoluções
> futuras — cada item é um esboço de abordagem, não uma sequência de tarefas TDD. Quando um item
> for priorizado, ele vira um plano completo próprio (via a skill de escrita de planos).
>
> **Status 2026-07-13:** **E3** (auto-pausa), **E5** (cadastro WA, fase 1 texto) e **E10** (Pixel Meta
> MVP: aba Tráfego + CAPI Purchase + pixel catálogo) — **entregues em código**. Restante do roadmap
> **não iniciado** (E1 áudio, E2 score, E4 multi-agente, E6 fotos, E7–E9).

**Origem:** recursos observados em uma plataforma de referência madura (prints do usuário) que
fazem sentido depois dos produtos-base relevantes estarem de pé.

**Princípio:** todos encaixam sem quebrar os contratos versionados de cada produto
(`/v1/simulacoes`, Chatbot API, Estoque API pública/privada e Portal). São extensões por adapter ou
evento, não acesso direto a bancos de dados vizinhos.

| Evolução | Produto proprietário | Integração opcional |
|---|---|---|
| Áudio/multimodal, auto-pausa, multi-agente | Chatbot | provedor de IA/transcrição |
| Score; drivers API/Playwright/agregador (híbrido) | Motor + UI credenciais no Portal | banco/parceiro/agregador |
| Cadastro de veículo por WhatsApp | Chatbot | Estoque API |
| Fotos e galeria | Estoque + Catálogo | storage de objetos |
| Funil, vendas, metas, campanhas | Portal | eventos do Chatbot/Estoque/Motor |
| Pixel Meta / conversões (aba Tráfego) | Portal + Catálogo | Meta Conversions API (CAPI) |

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

## E9 — Gestão de redes sociais e tráfego

**O que é:** conectores para cadastro/agendamento de publicações e plataformas de anúncio, além de
alertas e recomendações. São módulos/add-ons separados, não parte obrigatória do Dashboard.

**Pré-requisito:** E8 funcionando; sem atribuição confiável, automação de tráfego gera atividade sem
provar impacto em venda.

**Onde pluga:** produto/add-on de Marketing → API de campanhas do Portal.

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

## Ordem sugerida de ataque (depois do MVP)

| # | Item | Status 2026-07-13 |
|---:|---|---|
| — | **E3** auto-pausa | **Feito** (API + n8n Extrair/Gate + docs go-live) |
| — | **E5** cadastro WhatsApp fase 1 | **Feito** (API/CLI + tool n8n; foto = E6) |
| — | **E10** Pixel Meta MVP | **Feito** (Portal Tráfego + CAPI + catálogo browser) |
| 1 | **E1** áudio | Aberto |
| 2 | **E6** upload fotos | Aberto (desbloqueia foto no E5) |
| 3 | **E8** atribuição campanhas / ROI | Aberto (E10 é pré-requisito de conversão) |
| 4 | **E2** score | Aberto (com driver real + contrato bureau) |
| 5 | **E7** analytics avançado | Aberto |
| 6 | **E4** multi-agente | Aberto |
| 7 | **E9** redes sociais | Aberto (depois de medir origem→venda) |

**Evoluções E10 residual:** worker retry outbox CAPI; hash telefone no Purchase; sync Pixel ID
Portal↔Catálogo; toggles PageView/Lead lidos pelo catálogo.

> **Chatbot-only:** E5 é caminho canônico de cadastro (sem Portal) — **já disponível** via API/tool.
