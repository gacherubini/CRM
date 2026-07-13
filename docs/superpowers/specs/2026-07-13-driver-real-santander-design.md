# Design — 1º driver real de simulação: Santander (Playwright)

> Spec de brainstorming. Alimenta o plano de implementação (Motor Task 12 do #1A).
> Data: 2026-07-13. Decisões de produto do dono nesta sessão.

## Objetivo

Substituir a taxa **fictícia** (mock) por **cotação real** do Santander Financiamentos (Aymoré),
automatizando o portal `https://financiamentos.santander.com.br/originacao-auto/login` com Playwright,
usando a credencial da própria loja. É o 1º driver `real: true` — os demais bancos virão em incrementos
separados. Não reintroduzir mock como "banco real".

## Decisões fixas (desta sessão)

- **Banco piloto:** Santander (portal auto/originação).
- **Acesso:** Playwright no portal web (não há API). Login **só usuário+senha**, sem 2FA → automação
  unattended é viável.
- **Saída:** **multi-prazo** — devolve a parcela de todos os prazos padrão (ex.: 24/36/48/60x) num
  pedido, não um prazo por vez.
- **Valor do veículo:** vem do **próprio portal** (ele resolve o veículo pela placa/FIPE). Não depende
  do Estoque para a cotação.

## Escopo

**Dentro (Fase 1 — Motor):**
- Driver `santander` (Playwright sync) plugado no motor de drivers existente, marcado `real: true`.
- Extensão do contrato de simulação com os campos que o portal exige.
- Sessão autenticada reaproveitada (login 1x, reuso, re-login ao expirar).
- Mapeamento de desfechos para as exceções que o worker já trata.
- Testes por fixtures + smoke live atrás de flag.
- Imagem Docker do Motor com Playwright + Chromium.

**Dentro (Fase 2 — coleta):**
- Portal (form do vendedor) e Chatbot (fluxo WhatsApp) coletam os campos novos e os repassam ao Motor.

**Fora:**
- Outros bancos (cada um é um incremento próprio).
- Agregador.
- API oficial (não existe para este portal).

## Fluxo do robô (5 passos do wizard)

1. Motor recebe a solicitação e carrega a credencial cifrada da loja (Task 11, `credenciais.py`).
2. Abre navegador headless, loga em `/originacao-auto/login` (usuário+senha).
3. **Passo 1 — Cliente/Veículo:** CPF/CNPJ, data de nascimento, "possui CNH?" (sim/não), busca por
   **placa** + UF de licenciamento, **finalidade** (Comum/PCD), aceite dos Termos → Concordar e Continuar.
4. **Passos 2–5:** entrada, seleção de prazo(s) e plano → oferta. *(Campos exatos a mapear via codegen
   na implementação.)*
5. Lê a **parcela de cada prazo padrão** e devolve a lista ao Motor.

## Arquitetura

### Peças

- **`SantanderDriver`** (novo, em `app/motor/`): implementa a interface `Driver`, usa
  `playwright.sync_api` (encaixa no worker síncrono atual, sem refactor async). Isola todo o
  conhecimento do portal (URLs, âncoras, passos).
- **Sessão persistente:** guarda o `storage_state` autenticado (num caminho por cliente, fora do git),
  reusa entre jobs e re-loga quando expira. Reduz logins e footprint de automação.
- **Credenciais:** lidas via `credenciais.py` (`obter_segredo_para_uso`), decifradas **só em memória**
  durante a sessão. Nunca logadas.
- **Contrato:** campos novos abaixo.

### Mudança no contrato (Motor `app/motor/base.py`)

- `Pessoa`: adicionar `cnh: Optional[bool]`. `cpf` e `nascimento` já existem. **`renda` deixa de ser
  necessária** para o Santander (mantida opcional p/ compat).
- `Veiculo`: adicionar `placa: Optional[str]`, `uf_licenciamento: Optional[str]`,
  `finalidade: Optional[Literal["comum","pcd"]]`. `valor` vira opcional (o portal resolve pela placa).
- `Condicoes`: `prazo_meses` único vira **lista de prazos** (`prazos_meses: list[int]`), com um default
  padrão. Mock e contrato antigo continuam aceitos (compat retroativa).
- **Driver retorna lista:** hoje cada driver devolve **um** `ResultadoDriver`; passa a poder devolver
  `list[ResultadoDriver]` (um por prazo). `processamento.py` achata a lista em `ResultadoProvedor[]`.
  A resposta pública (`Simulacao.resultados`) já é uma lista — nada muda para quem consome.

### `real: true` e colisão de nomes

- O driver real só é resolvido para um `cliente+provedor` **quando há credencial configurada** (Task 11);
  sem credencial, não aparece (não cai em mock silencioso).
- **Conflito atual:** o mock do Motor usa nomes de bancos **reais** ("Santander", "Bradesco"…). Para o
  real Santander não ser confundido com o mock, quando o driver real está ativo ele **substitui** o
  mock "Santander" para aquele cliente. Recomendado (fora do caminho crítico): renomear os provedores
  mock para rótulos claramente fictícios (`BancoDemo …`), como o Chatbot já faz.

## Como o robô localiza os campos (confiabilidade)

1. **Descobrir gravando:** `playwright codegen` no portal real → captura o fluxo verdadeiro (sem chutar).
2. **Ancorar no texto visível**, não em `div`/classe volátil: rótulo/placeholder que o humano vê
   ("CPF ou CNPJ do cliente", "Data de nascimento", "Placa (obrigatório)", "Finalidade",
   "Concordar e Continuar"). Usar `get_by_label` / `get_by_role` / `get_by_placeholder`.
3. **Falhar em voz alta:** se uma âncora sumir (site mudou), o robô **não chuta** outro campo — para,
   tira **screenshot** e devolve `IntervencaoNecessaria` ("campo X não encontrado"). O print acelera o
   re-mapeamento.

## Mapeamento de desfechos

| Situação no portal | Exceção | Efeito no worker |
|---|---|---|
| Sucesso | — (`ResultadoDriver[]`) | `concluida` / `parcial` |
| Portal fora, timeout, queda de rede | `ErroTransitorio` | retry limitado com backoff |
| CPF/negócio recusado | `RejeicaoNegocio` | `rejeitada`, sem retry |
| Captcha/2FA/bloqueio/campo sumiu | `IntervencaoNecessaria` | `aguardando_intervencao` + screenshot |

## Estratégia de testes

- **Não** bater no Santander real em CI (risco de bloqueio). Testes automáticos rodam contra **cópias
  gravadas** das telas do portal (HTML/fixtures servidos localmente): validam preenchimento correto e
  parsing da parcela de forma determinística.
- **Smoke live:** um teste real contra o portal, com credencial da loja, **gated** por env
  (`MOTOR_SANTANDER_LIVE=1`) + rodado **manualmente**. Nunca em CI.
- Cobrir os 4 desfechos da tabela acima com fixtures.

## Infra

- Imagem Docker do Motor ganha Playwright + Chromium (imagem maior). Worker roda o browser.
- `storage_state` por cliente em volume fora do git; tratado como segredo.
- Concorrência: sessão de browser é pesada; respeitar o modelo worker/lease atual (um job por vez por
  worker) e um rate-limit para não martelar o portal.

## Segurança e privacidade

- Credencial da loja e `storage_state`: **nunca** no git, nunca em log, decifradas só em memória.
- Dado pessoal do cliente (CPF/nascimento) já trafega cifrado no payload do job (cifra existente).
- Screenshots de falha podem conter dado pessoal → guardar em local restrito, com retenção curta, e
  mascarar CPF quando possível.

## Riscos (assumidos pelo dono)

1. **ToS:** os Termos do Santander proíbem raspagem/automação para fins comerciais sem consentimento.
   Uso é da credencial da própria loja, B2B legítimo, mas há risco de **bloqueio da conta**. Mitigações:
   sessão reaproveitada, ritmo humano, rate-limit, degradar gracioso — não eliminam o risco.
2. **Fragilidade:** mudança de layout do portal quebra o robô → **manutenção recorrente**. Mitigado por
   âncoras estáveis + falha explícita com screenshot.
3. **Detecção de automação:** portais bancários podem detectar headless. Mitigação: contexto persistente,
   pacing, sem paralelismo agressivo.

## Impacto nos outros produtos (Fase 2)

- **Chatbot (#2A):** o fluxo WhatsApp coleta CNH, UF e finalidade (placa já é a chave), sem renda; monta
  o payload novo.
- **Portal (#3A):** form de simulação do vendedor ganha os campos novos.
- Onde a parcela aparece hoje **não muda** — só passa a ser real.

## Fases de entrega

1. **Motor:** contrato estendido + `SantanderDriver` (multi-prazo) + fixtures + smoke live + imagem
   Docker. (Driver validado gravando o fluxo real com codegen.)
2. **Coleta:** Portal e Chatbot coletam/repassam os campos novos.
3. **Hardening:** métricas de sucesso/falha por banco (já há base na Task 11), retenção de screenshots,
   rename do mock para rótulos fictícios.

## Questões em aberto (resolver na implementação)

- Mapa exato dos passos 2–5 (onde entram entrada/prazo e onde a parcela aparece) — via codegen.
- O portal mostra todos os prazos numa tela só ou um por vez? Define se é 1 run ou N runs por simulação.
- Formato do prazo padrão (quais prazos oferecer por default).
