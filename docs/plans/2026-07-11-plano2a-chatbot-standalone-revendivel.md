# Plano #2A — Chatbot Standalone Revendível

> Plano válido do Chatbot. Detalhes históricos n8n/Evolution do #2 monolítico: `docs/plans/_archive/`
> (não executar; mistura Chatbot com Motor).
>
> **Status 2026-07-12:** API + providers + funil catálogo em grande parte **entregues**; bot **off**
> de propósito. **Decisão de produto:** sem trava de consentimento no fluxo (dono); CPF mascarado.
> Tabelas/endpoints de consentimento podem existir, mas **não** reativar gate 409 de nome sem pedido.
> **Aberto:** go-live, prompt n8n, simulação por **placa**+telefone (ver #4A), LGPD exclusão.

**Goal:** Entregar um pacote instalável e revendível que conecta um WhatsApp, conversa com clientes,
qualifica e exporta leads, consulta o Estoque Lite, executa handoff humano e, na edição
Financiamento, consulta um Motor plugável — sem Portal ou Catálogo Público.

**Produto:**

- **Chatbot Atendimento:** conversa, Estoque Lite, qualificação, lead, handoff, webhook e CSV.
- **Chatbot Financiamento:** todos os itens acima + `SimulationProvider` mock ou HTTP.

**Stack:** Evolution API, n8n, Redis, `chatbot-api` FastAPI, PostgreSQL e Docker Compose.

## Critérios comerciais de independência

O produto só é considerado revendível quando:

1. sobe com um único comando a partir de `deploy/chatbot-standalone/`;
2. não contém dependência de Portal ou Catálogo Público; a Estoque API vem configurada no pacote;
3. funciona sem Motor na edição Atendimento;
4. inclui mock demonstrável e aceita Motor HTTP na edição Financiamento;
5. possui onboarding de loja/número sem editar código;
6. exporta os leads por CSV e webhook/API;
7. possui backup, restore e migração de versão documentados;
8. aceita identidade visual, textos, horário e regras por configuração;
9. expõe health/status suficiente para suporte remoto;
10. passa o teste E2E em ambiente vazio com apenas o compose standalone.

## Arquitetura do pacote

```text
Cliente WhatsApp
      │
Evolution API
      │ webhook autenticado
      ▼
chatbot-api ── Postgres (dados do produto)
      │  └──── Redis (buffer/idempotência curta)
      │
      ├── n8n (orquestração e LLM)
      ├── SimulationProvider (none | mock | http)
      ├── InventoryProvider ── Estoque API Lite ── dados de veículos
      └── Saídas (CSV | webhook | API)
```

n8n não escreve diretamente no banco e não decide autorização/tenancy. Toda mudança passa pela
Chatbot API. O workflow pode ser trocado sem migrar os dados do produto.

## Dados pertencentes ao Chatbot

- `lojas`: configuração mínima do tenant e instância Evolution.
- `bot_configuracoes`: prompt/textos, horário, providers e identidade.
- `leads`: qualificação, etapa, responsável externo opcional e consentimento.
- `consentimentos`: versão do texto, finalidade, timestamp e evidência.
- `mensagens`: evento de entrada/saída com ID externo idempotente.
- `conversas`: estado, bot ativo, handoff e timestamps.
- `webhook_entregas`: outbox, tentativas e resultado da exportação.
- `auditoria`: alterações administrativas e exclusões.

Simulações completas pertencem ao Motor. O Chatbot guarda apenas referência, status resumido e os
resultados necessários para apresentar ao cliente, respeitando retenção configurada.

## Contratos internos

### Providers

```python
class SimulationProvider(Protocol):
    async def criar(self, payload: dict, idempotency_key: str) -> dict: ...
    async def consultar(self, simulacao_id: str) -> dict: ...


class InventoryProvider(Protocol):
    async def buscar(self, termo: str) -> list[dict]: ...
```

Implementações obrigatórias:

- `NoSimulationProvider` para Chatbot Atendimento;
- `MockSimulationProvider` para demo/teste;
- `HttpSimulationProvider` para Motor vendido junto ou externo;
- `HttpInventoryProvider` apontando por padrão ao Estoque Lite incluído;
- fallback controlado para registrar interesse em texto livre quando o estoque estiver indisponível.

### Simulação no WhatsApp privado (CRM estoque — alinhar ao Plano #4A)

**Como está hoje (mock):** tool/n8n ou `POST /v1/simular` recebe em geral valor + entrada +
`prazo_meses` (+ cpf/nascimento/renda no Portal). `MockSimulationProvider` aplica Price com taxas
demo; `http` repassa ao Motor. **Não** resolve veículo por placa; **não** exige telefone no payload
de simulação (o telefone existe na conversa Evolution, mas não amarra o job de simulação).

**Alvo do pacote básico (Estoque Lite + Chatbot Financiamento):**

1. Telefone = identidade WhatsApp (sempre presente no lead/conversa).
2. Cliente informa **placa** → Chatbot consulta Estoque (`por-placa`) → preço/modelo reais.
3. Coleta: CPF (+ nascimento se necessário), **entrada**. **Sem** prazo desejado e **sem** renda.
4. Simulação devolve opções em prazos padrão (ex. 12/24/36/48) sobre o valor daquela placa.
5. Troca mock → Motor HTTP sem o n8n saber a diferença.

Detalhe do payload e tabela de campos: seção *Pacote CRM estoque no WhatsApp privado* no Plano #4A.

### Saída de lead

- `GET /v1/leads.csv` autenticado e filtrado pela loja.
- `GET /v1/leads` paginado.
- webhook configurável `lead.created`, `lead.updated`, `handoff.requested`.
- assinatura HMAC, retry com backoff e histórico de entregas.

## Tasks

### Task 1: Scaffold isolado da Chatbot API

**Create:**

- `chatbot-api/app/main.py`
- `chatbot-api/app/config.py`
- `chatbot-api/app/db.py`
- `chatbot-api/requirements.txt`
- `chatbot-api/Dockerfile`
- `chatbot-api/tests/test_health.py`

**Produces:**

- `GET /health/live` sem dependências;
- `GET /health/ready` verifica Postgres e Redis;
- `GET /version` informa versão do pacote e schema.

**Aceite:** testes passam e a imagem não importa código de outros produtos.

### Task 2: Compose comercial standalone

**Create:**

- `deploy/chatbot-standalone/docker-compose.yml`
- `deploy/chatbot-standalone/.env.example`
- `deploy/chatbot-standalone/README.md`
- `deploy/chatbot-standalone/scripts/healthcheck.ps1`

Serviços permitidos: `chatbot-api`, `estoque-api` em modo Lite, `n8n`, `evolution`, `redis` e
Postgres com propriedade lógica/credenciais separadas por serviço. O Motor pode aparecer somente
em profile opcional; Portal e Catálogo Público são proibidos neste compose.

**Aceite:** `docker compose config` funciona apenas com o `.env.example` copiado e nenhum nome de
host externo de produto é obrigatório.

### Task 2A: Estoque Lite incluído

Reutilizar a Estoque API do Plano #4A com uma administração reduzida para cadastrar, editar,
disponibilizar/vender veículos, preço, foto e importação CSV. O Chatbot consulta somente veículos
`disponivel` e responde filtros como tipo, marca, modelo e faixa de preço.

**Aceite:** após cadastrar três veículos, perguntas como “quais carros tem?”, “tem Onix?” e
“o que tem até R$ 50 mil?” retornam apenas dados reais; estoque indisponível gera fallback/handoff,
nunca resposta inventada.

### Task 3: Migrações e isolamento por loja

**Create:** modelos/migrações das tabelas do Chatbot e testes de tenancy.

Regras:

- `loja_id NOT NULL` em todo dado operacional;
- loja resolvida pela instância Evolution ou identidade autenticada;
- IDs externos de mensagem únicos por instância;
- estados e direções com enum/check;
- `TIMESTAMPTZ`;
- nenhuma coluna CPF em texto claro;
- Alembic para upgrade, sem `create_all` em produção.

**Aceite:** usuário/serviço da loja A não lê, altera nem remove recurso da loja B, mesmo fornecendo
IDs válidos dela.

### Task 4: Webhook confiável da Evolution

Implementar:

- autenticação do webhook;
- persistência idempotente antes de enfileirar;
- resposta rápida ao provedor;
- buffer de rajadas no Redis;
- deduplicação de entrada e saída;
- correlação `request_id`, `provider_message_id` e conversa;
- retry limitado e consulta de falhas.

**Aceite:** reenviar o mesmo payload três vezes cria uma mensagem e no máximo uma resposta.

### Task 5: Conversa e consentimento (opcional / legado de gate)

> **Override:** não bloquear lead/nome por falta de consentimento. Manter capacidade de registrar
> evidência se o dono quiser; o fluxo WhatsApp atual opera **sem** trava.

O n8n recebe contexto mínimo da Chatbot API e pede ao LLM saída estruturada. A API valida e aplica
as transições; o LLM nunca grava dados nem chama banco diretamente.

Fluxo mínimo:

1. saudação e explicação;
2. consentimento versionado antes de dados pessoais;
3. interesse/veículo em texto livre ou catálogo opcional;
4. qualificação configurável;
5. confirmação;
6. registro/atualização de lead;
7. simulação apenas quando o provider estiver ativo;
8. handoff ou encerramento.

**Aceite:** pergunta fora de ordem, correção de dado e rajada de mensagens não duplicam lead nem
pulam o consentimento.

### Task 6: Simulação plugável

Implementar os providers `none`, `mock` e `http`. O workflow chama somente a fachada da Chatbot API;
trocar provider é configuração, não edição no n8n.

Regras:

- tratar processamento assíncrono e resultado parcial;
- timeout e indisponibilidade geram mensagem segura e handoff opcional;
- nenhuma taxa/parcela é inventada pelo LLM;
- CPF e nascimento não entram em logs;
- idempotency key por tentativa confirmada do cliente.

**Aceite:** a mesma suíte E2E roda com `mock`; com `none`, o bot qualifica e encaminha sem quebrar.

### Task 7: Handoff vendável

Implementar:

- pausar/devolver bot por endpoint autenticado;
- pausar automaticamente quando mensagem manual for detectada e não for saída conhecida do bot;
- janela configurável de reativação;
- evento `handoff.requested` para CRM/cliente externo;
- auditoria de quem alterou o estado.

O produto não depende do Portal para handoff: deve existir endpoint e uma tela administrativa mínima
ou comando seguro suficiente para operar o recurso standalone.

### Task 8: Exportação e integrações genéricas

Implementar API paginada, CSV e webhooks HMAC. Não criar integração específica com o Portal neste
plano; o Portal é apenas mais um consumidor dos mesmos contratos.

**Aceite:** um sistema fictício recebe `lead.created`, confirma a assinatura e uma falha temporária
é reenviada sem duplicar o evento lógico.

### Task 9: Configuração por cliente

Configurações sem editar código/workflow:

- nome, logo/identidade textual e tom;
- número/instância Evolution;
- campos de qualificação obrigatórios;
- texto e versão do consentimento;
- horário e mensagem fora de expediente;
- destino de handoff;
- providers e URLs opcionais;
- retenção e exportações.

Segredos ficam em env/cofre; configurações operacionais ficam no banco com auditoria.

### Task 10: Operação e atualização

Documentar e testar:

- primeira instalação;
- criação da loja e usuário administrativo;
- conexão/recuperação do WhatsApp;
- backup e restore;
- upgrade com migrations e rollback da aplicação;
- rotação de chaves;
- coleta de diagnóstico sem dados pessoais;
- limites e custos de LLM.

### Task 11: Teste final de revenda

Em máquina/ambiente limpo:

1. copiar somente `deploy/chatbot-standalone` e artefatos/imagens publicados;
2. configurar `.env` sem Portal/Catálogo Público;
3. subir a edição Atendimento;
4. cadastrar veículos no Estoque Lite e confirmar consultas pelo WhatsApp;
5. consentir, qualificar, criar e exportar lead;
6. testar handoff e exclusão de dados;
7. ativar mock e repetir como edição Financiamento;
8. reiniciar containers e confirmar persistência;
9. executar backup, apagar ambiente de teste e restaurar;
10. comprovar que nenhum request tentou acessar Portal/Catálogo Público.

**Critério de conclusão:** todos os passos possuem evidência e checklist assinado. Só então o pacote
pode ser chamado de Chatbot Standalone revendível.

## Integração opcional com a suíte

- Portal recebe eventos/consulta leads pela API do Chatbot.
- O pacote já inclui Estoque Lite; pode trocar a URL para uma Estoque API externa compatível.
- Chatbot consulta Motor via `HttpSimulationProvider`.
- Um compose combinado apenas preenche URLs e credenciais entre produtos.

Portal, Catálogo Público e Motor não são necessários para a edição Atendimento.

## Fora de escopo

- Dashboard completo do dono/vendedor.
- Catálogo/vitrine pública e gestão avançada de estoque.
- Vendas, metas, lucro e campanhas.
- Drivers bancários — pertencem ao Motor.
- Integração específica com CRM de terceiros; usar webhook/API genéricos primeiro.

## Resultado

Um produto de chatbot que pode ser demonstrado, instalado, operado, atualizado e vendido sozinho.
A suíte completa agrega capacidades por contrato, sem transformar os outros produtos em requisitos.
