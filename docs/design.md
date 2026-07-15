# Design — Bot de WhatsApp para Simulação de Financiamento de Motos

**Data:** 2026-07-11
**Status:** Pesquisa/histórico (**SUPERSEDED** para implementação).

> Agentes: **não implemente a partir deste arquivo.**  
> Canônico: `docs/contexto-compacto.md` → `docs/plans/README.md` → planos `*A`/`*B`.  
> Este texto ainda cita Claude, consentimento obrigatório e mock-only — **tudo superado**.

---

## 1. Objetivo

Bot de WhatsApp para uma revenda de motos que:

1. Recebe a mensagem de um cliente interessado em comprar/financiar uma moto.
2. Conversa com ele (via LLM), coleta os dados necessários.
3. Dispara a **simulação de financiamento** (mock agora; RPA nos portais dos bancos depois).
4. Devolve as opções de cada banco (parcela, taxa, nº de parcelas) organizadas no WhatsApp.

**Princípio central de design:** o mecanismo de acesso aos bancos é **desacoplado** do resto.
O bot inteiro é construído e validado com um "motor de simulação" mockado; o motor real
é plugado depois sem alterar o fluxo do WhatsApp, a conversa ou o banco de dados.

---

## 2. Contexto de negócio (o que já existe)

- A loja **já possui acesso ao portal do lojista dos 5 bancos** (Santander, Bradesco,
  Fontcred, Banco Pan, Banco BV). Hoje as simulações são feitas manualmente nesses
  portais (abrir portal → digitar dados do cliente → ler a parcela).
- Consequência: **não é necessário** contratar agregador pago nem fechar contrato de API
  com os bancos para começar. O caminho natural do motor real é **RPA** (automatizar os
  portais que a loja já usa).
- O usuário tem background em programação Python (favorece Playwright para o RPA).
- O usuário nunca usou n8n.

### Decisão de integração bancária: EM HOLD

A escolha final do mecanismo de simulação real (RPA vs API vs agregador) está
**intencionalmente adiada**. O design garante que essa decisão não bloqueia nenhuma das
fases iniciais. Ver Seção 9 (pesquisa por banco) e Seção 7 (motor plugável).

---

## 3. Arquitetura geral

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
│  3. Chama o LLM (Claude) → entende + extrai    │
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

**Stack final:** produtos independentes que podem compartilhar um servidor sem compartilhar
contratos de banco: Chatbot Standalone (Evolution + n8n + Chatbot API + Estoque Lite), Motor de
Simulação, Portal de Gestão com Estoque API, Catálogo Público opcional e Postgres com
dados/credenciais isolados por componente.

---

## 4. Componentes (responsabilidade única)

| Componente | Responsabilidade | Não faz |
|---|---|---|
| **Canal WhatsApp** (Evolution API) | Transporta mensagens (recebe/envia) | Não interpreta conteúdo |
| **n8n** (orquestrador) | Roteia eventos, chama LLM e a Chatbot API, formata resposta | Não é fonte de verdade; não autoriza tenancy; não roda Playwright |
| **LLM** (Claude) | Entende o cliente, extrai dados, conduz a coleta | Não inventa simulação |
| **Chatbot API** | Consentimentos, leads, mensagens, conversas, handoff e integrações plugáveis | Não depende de portal ou catálogo |
| **Motor de Simulação** | Executa jobs por banco e devolve resultados parciais/finais | Produto/API independente; mock na Fase 1 |
| **Postgres** | Persiste lead, consentimento LGPD, simulações | — |

**Contrato funcional inicial entre o Chatbot e o Motor de Simulação:**

> O payload abaixo continua válido como entrada de negócio, mas o recurso será versionado e
> assíncrono (`POST /v1/simulacoes` + consulta de status), conforme o Plano #0. Não tratar o
> endpoint síncrono do mock como contrato definitivo do RPA.

- **Entrada** (`POST /simular`):
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
- **Saída:**
  ```json
  {
    "resultados": [
      {"banco": "BV", "valor_parcela": 512.30, "taxa_am": 1.79, "n_parcelas": 48, "valor_financiado": 15000, "status": "ok"},
      {"banco": "Pan", "valor_parcela": 498.10, "taxa_am": 1.72, "n_parcelas": 48, "valor_financiado": 15000, "status": "ok"}
    ]
  }
  ```
- O n8n nunca sabe se por trás é mock ou Playwright. Trocar o motor não afeta o n8n.

---

## 5. Fluxo conversacional

1. **Saudação + consentimento LGPD** (antes de qualquer dado pessoal):
   > "Oi! Posso te ajudar a simular o financiamento da tua moto. Vou precisar de alguns
   > dados (nome, CPF, data de nascimento), usados **só** para essa simulação e contato
   > da loja. Posso seguir?"
   → registra o "sim" com data/hora + versão do texto.
2. **Qual moto** → modelo, ano, valor aproximado.
3. **Condições** → valor de entrada, prazo desejado (meses).
4. **Dados pessoais** → nome completo, CPF, data de nascimento. *(Renda: opcional — melhora a simulação.)*
5. **Validação** → CPF (algoritmo do dígito verificador), data real, idade ≥ 18.
6. **Confirmação** → o bot resume tudo e pede "confirma?".
7. **Dispara o motor** → `POST /simular` (mock na Fase 1).
8. **Resposta formatada** → opções por banco (parcela, taxa, nº de parcelas), organizadas e legíveis.
9. **Fechamento** → salva o lead e oferece falar com um vendedor humano.

### Regras de validação

- **CPF:** 11 dígitos + cálculo dos 2 dígitos verificadores; rejeita sequências
  inválidas (`00000000000`, `11111111111`, etc.).
- **Data de nascimento:** data existente e válida; idade mínima 18 anos.
- **Valores monetários:** interpretar "20 mil", "R$ 20.000", "20000" como 20000.
- **Robustez conversacional:** o LLM deve lidar com o cliente que manda vários dados de
  uma vez, na ordem errada, ou pergunta algo no meio — extraindo o que der e pedindo só o
  que falta.

---

## 6. LGPD (tratamento de CPF + data de nascimento)

- **Consentimento:** mensagem explícita **antes** de coletar dado pessoal; armazenar
  texto da versão do consentimento + timestamp + telefone.
- **Minimização:** coletar apenas o necessário para a simulação.
- **Segurança:** CPF armazenado com criptografia (ou coluna protegida); acesso restrito;
  segredos (chaves, logins de portal) fora do código, em variáveis de ambiente/cofre.
- **Retenção:** lead não convertido é apagado em **6 meses** (rotina de expurgo);
  cliente pode solicitar exclusão a qualquer momento (comando "sair" / "apagar meus dados").
- **Finalidade declarada:** simulação de financiamento e contato comercial da loja.

---

## 7. Motor de Simulação (peça plugável)

Micro-serviço **Python (FastAPI)**, separado do n8n, exposto via HTTP.

- **Fase 1 (mock):** internamente calcula a parcela com a fórmula real de amortização
  (Price) a partir de uma taxa fictícia por banco. O resultado "parece real" e valida
  toda a experiência ponta a ponta.
- **Fase 3+ (real):** cada banco vira um **driver Playwright** independente
  (`santander.py`, `bradesco.py`, `pan.py`, `bv.py`, `fontcred.py`) que:
  1. loga no portal do lojista (credenciais em variável de ambiente/cofre),
  2. preenche o formulário de simulação,
  3. lê a parcela/taxa/prazo,
  4. normaliza para o formato de saída padrão.

**Vantagens do desenho:**

- A parte de RPA fica 100% em Python (forte do usuário); o n8n só orquestra.
- Cada driver é isolado e testável sozinho (roda no PC, sem WhatsApp/n8n no meio).
- Um banco de cada vez; se um portal mudar, conserta-se só aquele arquivo.

**Riscos conhecidos do RPA (Fase 3, não bloqueiam Fases 0–2):**

- **Captcha / 2FA por SMS** em alguns portais pode travar automação. Estratégia:
  começar pelos portais sem captcha; nos que tiverem, tratar caso a caso (ex.: manter
  sessão logada, intervenção humana pontual).
- Portais mudam de layout → drivers quebram → manutenção contínua. Por isso o motor é
  modular por banco.

---

## 8. Modelo de dados (Postgres)

```
leads
  id                  (PK)
  telefone            (text)
  nome                (text)
  cpf                 (text, criptografado)
  nascimento          (date)
  moto_modelo         (text)
  ano                 (int)
  valor_moto          (numeric)
  entrada             (numeric)
  prazo_meses         (int)
  renda               (numeric, nullable)
  status              (text: novo | simulado | contatado | descartado)
  consentimento_em    (timestamptz)
  consentimento_texto (text)
  criado_em           (timestamptz)

simulacoes
  id                (PK)
  lead_id           (FK -> leads.id)
  banco             (text)
  valor_parcela     (numeric)
  taxa_am           (numeric)
  n_parcelas        (int)
  valor_financiado  (numeric)
  resposta_bruta    (jsonb)     -- payload cru do portal/mock, para auditoria
  criado_em         (timestamptz)

conversa_estado (para manter o contexto entre mensagens)
  telefone          (PK)
  etapa             (text)      -- em que ponto do fluxo o cliente está
  dados_parciais    (jsonb)     -- o que já foi coletado
  atualizado_em     (timestamptz)
```

---

## 9. Pesquisa por banco (referência)

Levantamento de como cada banco disponibiliza simulação de financiamento de veículo ao lojista:

| Banco | Tem API de parceiro? | Como acessa de verdade | Estratégia recomendada |
|---|---|---|---|
| **Banco BV** (ex-Votorantim) | ✅ **Sim (a mais aberta)** — BV Open (Apigee), sandbox público; endpoint "Iniciar Simulação Financiamento Veículo" aceita CPF + categoria (moto/leve/pesado). Produção exige contrato de parceiro. | Plataforma "Parceiro BV" + API | RPA agora (portal já disponível); **API é upgrade futuro** — melhor candidato técnico por ter sandbox |
| **Banco Pan** | ✅ **Sim** — Portal do Desenvolvedor com doc de financiamento de veículos (`developers.bancopan.com.br`). Exige contrato. | Portal `go!PAN Veículos` + API | RPA agora; API como upgrade |
| **Santander** (Aymoré) | ❌ Não (pública) | App/portal "Financiamento Lojista" + simulador Autoline; integradores homologados (ex.: Cockpit) | **RPA no portal** |
| **Bradesco** (Bradesco Financiamentos) | ❌ Não (para simulação de veículo) | Portal do lojista (`bfportalcli`, `finilojmobile`) + simulador Autoline. O "Bradesco Developers" é para cobrança/cash, não veículo. | **RPA no portal** |
| **Fontcred** | ❌ Não aparente | Modelo de parceiro/correspondente; foco em moto | **RPA no portal** ou proposta manual |

**Agregadores multibanco (alternativa não escolhida, documentada para referência):**

- **FANDI** — líder de F&I (~80% do mercado, 3.000+ lojas); integra Itaú, Bradesco,
  Santander, Safra, Porto, bancos digitais/montadora; tem API para clientes. Preço não
  público ("fale com o comercial"). Provável identidade do "F1" citado inicialmente.
- **Autoconf** — sistema para revenda com simulador multibanco nativo; sem exclusividade
  com banco; API para integrar no site/sistema. Planos ~R$199 (Basic) a ~R$899/mês
  (valores de busca, confirmar no comercial).
- **Creditas** — correspondente de Santander, Itaú, Porto Bank, Bradesco; modelo por
  comissão (loja não paga mensalidade, mas cede parte da originação).

**Por que agregador foi descartado por ora:** a loja já tem acesso direto aos portais,
então RPA elimina o custo do agregador. Fica registrado como plano B caso o RPA se mostre
inviável em vários bancos.

---

## 10. MVP em fases

| Fase | Entrega | Valida |
|---|---|---|
| **Fundação** | Plano #0: domínio, contratos, tenancy, papéis, idempotência e LGPD | Base não exige retrabalho para portal do dono/vendedor |
| **0** | WhatsApp ↔ n8n com eco idempotente | Canal e confiabilidade básica funcionam |
| **1** ⭐ | Conversa + consentimento + lead + simulação mock | Jornada completa sem banco real |
| **2** | Estoque, catálogo e portal mínimo do vendedor | Operação comercial básica |
| **3** | Vendas, metas e dashboard do dono | Gestão por dados reais, inclusive lucro bruto |
| **4** | Primeiro driver bancário assíncrono | Primeira simulação real e resiliente |
| **5** | Campanhas, atribuição e marketing | Origem → lead → venda mensurável |

A **Fase 1 é o coração** e pode ser 100% construída/testada agora, com a decisão de banco em hold.

---

## 11. Contas / credenciais a providenciar

**Para o MVP (Fases 0–2):**

1. **Servidor** — Fly.io **ou** VPS (ex.: Hetzner ~€4/mês) para rodar Evolution + n8n +
   Serviço Python + Postgres. Nota: n8n e Evolution precisam ficar **sempre ligados**
   (não podem "dormir", senão perdem a sessão do WhatsApp).
2. **Número de WhatsApp dedicado** (um chip só para o bot).
3. **Chave de API do Claude (Anthropic)** para a parte conversacional.
4. **Postgres** — container no mesmo servidor (custo ~zero). Alternativa de conveniência:
   Supabase free (troca não afeta o design).

**Para a Fase 3+ (quando sair do hold):**

5. **Logins dos portais do lojista** (a loja já possui) — armazenados com segurança
   (variáveis de ambiente/cofre) para os drivers Playwright.
6. (Opcional/futuro) Contrato de API com **BV Open** ou **Pan** se decidir migrar de RPA
   para API.

---

## 12. Decisões travadas

- **Canal WhatsApp:** Evolution API (self-host, gratuito). Pode migrar para WhatsApp
  Cloud API (oficial) no futuro sem mudar o núcleo.
- **Orquestrador:** n8n.
- **LLM:** Claude (Anthropic API).
- **Produtos:** Chatbot, Motor, Portal e Estoque/Catálogo possuem deploy próprio e integram-se por API/eventos.
- **Banco de dados:** Postgres (container no mesmo servidor).
- **Hospedagem / ambientes:**
  - **Desenvolvimento:** stack local via `docker-compose` (n8n + Evolution + Postgres +
    serviço Python). Iteração rápida e gratuita; workflows do n8n exportados como JSON.
  - **Produção:** self-host no **Fly.io** (n8n com volume persistente e
    `min_machines_running = 1`, Evolution sempre-on, Postgres, serviço Python).
  - Migração dev→prod não altera o código; só o alvo de deploy.
  - Ferramentas já instaladas na máquina do dev: Docker 29, Docker Compose v5, Node v24,
    Python 3.14 — nada adicional a baixar para começar.

## 13. Em aberto

- Escolha final RPA vs API vs agregador por banco (hold).
- Qual portal atacar primeiro no RPA (sugestão: o mais simples / sem captcha).
- Estratégia de captcha/2FA por banco.
- Fornecedor/cofre da chave de cifra do CPF (a estratégia e o ciclo de dados são bloqueadores do Plano #2A).
- Regras finais de cálculo de custo direto e lucro bruto por venda.
