# Plano #0 — Fundação da Plataforma (produtos, domínio e segurança)

> **Fundação canônica** (produtos, tenancy, HTTP-only, segurança). Não reexecutar tasks de
> “criar docs” se já existirem — use como referência de limites.
>
> **Override de produto (2026-07):** o Chatbot **não** exige mais trava de consentimento antes de
> salvar nome/lead (decisão do dono). LGPD continua valendo (minimização, máscara de CPF em
> mensagens, sem logar PII). Seção de consentimento abaixo = capacidade opcional / histórico,
> não gate obrigatório do fluxo WhatsApp.

**Goal:** Fixar os limites do sistema, o domínio mínimo, os contratos e as regras de segurança
que permitem construir bot, portal, estoque e catálogo sem retrabalho estrutural quando entrarem
dashboard do dono, dashboard do vendedor, vendas, metas, lucro e integrações de tráfego.

**Architecture:** A solução é formada por **produtos modulares empacotáveis**, cada um com API,
migrações, dados e deploy próprios. O Chatbot Standalone inclui tudo de que precisa para conversar,
persistir consentimento/leads, consultar o Estoque Lite incluído e integrar uma simulação, sem
depender de Portal, Catálogo Público ou gestão completa.
Quando a suíte completa é instalada, os produtos se conectam por contratos HTTP/eventos — nunca por
imports de código da aplicação vizinha ou acesso direto ao banco dela.

**Tech Stack:** FastAPI, PostgreSQL, SQLAlchemy/Alembic, Redis, n8n, Evolution API, pytest.

## Decisões obrigatórias

1. Não existe uma Core API central obrigatória para todos os produtos. Cada produto possui seu
   backend mínimo; código técnico reutilizável pode existir como biblioteca, sem criar dependência
   de runtime entre produtos.
2. Todo dado operacional pertence a uma loja. `loja_id` é obrigatório, tem chave estrangeira e é
   derivado da identidade autenticada ou da instância Evolution — nunca confiado a partir do body.
3. Papéis iniciais: `admin_plataforma`, `dono`, `gerente`, `vendedor`. Autenticação não substitui
   autorização; cada operação valida papel, loja e, quando aplicável, vendedor responsável.
4. Cada produto escreve somente em seus próprios dados. Dashboard, bot e catálogo integram-se por
   APIs/eventos versionados; nenhum produto consulta diretamente tabelas ou views de outro.
5. Eventos do WhatsApp e comandos mutáveis são idempotentes.
6. CPF e data de nascimento nunca aparecem em logs comuns. CPF persistido é cifrado e possui,
   somente se necessário, índice cego separado para igualdade/deduplicação.
7. O mock não define o contrato operacional do RPA. A simulação real admite processamento,
   resultado parcial, timeout, 2FA e falha por banco.

## Produtos e propriedade dos dados

### Produto A — Chatbot Standalone

Pacote revendível que sobe sozinho com:

- Evolution API, n8n, Redis, Postgres e `chatbot-api`;
- configuração de uma ou mais lojas/instâncias;
- Estoque Lite incluído no pacote, usando a mesma Estoque API do Plano #4A;
- consentimentos, leads, mensagens, conversas, handoff e auditoria do bot;
- adaptador `SimulationProvider` configurável;
- simulador mock/demonstração incluído e conexão opcional com o Motor de Simulação real;
- webhooks de saída e exportação CSV/API para o cliente usar sem comprar o portal.

O chatbot consulta por padrão o Estoque Lite e responde somente com veículos realmente disponíveis.
Se o estoque estiver vazio/indisponível, aceita o interesse em texto livre e oferece confirmação
humana; nunca inventa veículo, preço ou disponibilidade. Catálogo Público continua opcional.

Há duas edições comerciais sobre o mesmo pacote:

- **Chatbot Atendimento:** conversa, Estoque Lite, qualificação, lead, handoff e exportação; sem Motor obrigatório.
- **Chatbot Financiamento:** inclui ou aponta para o Motor de Simulação como add-on do próprio pacote.

Para o comprador, ambas são uma instalação autônoma; “add-on” descreve composição comercial e não
uma dependência do Portal ou Catálogo Público. A Estoque API é um componente incluído no pacote.

### Produto B — Motor de Simulação

API revendível separadamente, dona de `simulacoes`, resultados e drivers bancários. Não depende de
n8n, WhatsApp, portal ou estoque. Recebe dados normalizados e executa jobs assíncronos.

### Produto C — Portal de Gestão

Dono de usuários, vendedores, vendas, metas e campanhas. Pode operar manualmente sem chatbot.
Quando integrado, consome leads/conversas pela API do Chatbot e simulações pela API do Motor.

### Produto D — Estoque API

Dono de veículos e publicação. Pode ser vendido sozinho e também é incluído em modo Lite no pacote
do Chatbot e com interface completa no Dashboard.

### Produto E — Catálogo Público

Vitrine read-only, opcional, alimentada exclusivamente pela API pública do Estoque. Não cadastra
veículos e não é necessária para Chatbot ou Dashboard.

### Suíte completa

Um `docker-compose` combinado instala os cinco componentes e configura URLs/credenciais entre eles.
Isso é conveniência de implantação, não acoplamento: remover Portal ou Catálogo não derruba o Bot.

## Escopo do domínio

### Dados do Chatbot Standalone

- `lojas`: tenant e configurações da operação.
- `usuarios`: identidade, papel, loja e estado ativo/inativo.
- `leads`: cliente potencial, responsável, etapa, origem e consentimento.
- `mensagens`: histórico idempotente de entrada/saída.
- `conversas`: estado, responsável e controle de handoff.
- `auditoria`: alterações sensíveis e ações administrativas.

### Dados dos produtos opcionais

- Motor: `simulacoes` e `simulacao_resultados`.
- Estoque/Catálogo: `veiculos`, `veiculo_fotos` futuramente.
- Portal: `vendas`, `metas`, `lead_eventos` materializados/importados e `campanhas`.

### Domínio comercial preparado, mas implementado na fatia do portal

- `vendas`: veículo, lead, vendedor, preço, custo, lucro bruto e data.
- `metas`: vendedor/loja, período, tipo e valor-alvo.
- `lead_eventos`: mudanças de etapa e atribuição para calcular funil e tempo de resposta.
- `campanhas`: origem, canal, UTM e custo opcional.

Não criar ainda automação de postagens, gestão de redes sociais ou otimização de anúncios. Esses
módulos entram depois que `campanhas` e `lead_eventos` conseguirem medir origem → lead → venda.

## Contratos-base

### Contexto autenticado

Toda chamada interna que acessa dados multi-loja resolve um contexto equivalente a:

```json
{
  "actor_id": 42,
  "actor_type": "usuario|n8n|catalogo",
  "loja_id": 7,
  "papel": "dono|gerente|vendedor|servico",
  "request_id": "uuid"
}
```

O cliente não escolhe `loja_id` livremente. Para mensagens, a Chatbot API resolve a loja por
`evolution_instance`; para usuários, pela sessão/token; para catálogo público, pelo slug da loja.

### Contratos plugáveis do Chatbot

```python
class SimulationProvider(Protocol):
    async def criar(self, solicitacao: dict, idempotency_key: str) -> dict: ...
    async def consultar(self, simulacao_id: str) -> dict: ...


class InventoryProvider(Protocol):
    async def buscar(self, termo: str, loja_ref: str) -> list[dict]: ...
```

Implementações mínimas: `MockSimulationProvider`, `HttpSimulationProvider`,
`HttpInventoryProvider` apontando ao Estoque Lite e fallback seguro quando ele estiver indisponível.

### Simulação assíncrona

```http
POST /v1/simulacoes
Idempotency-Key: <uuid>

202 Accepted
{"id":"uuid","status":"processando"}
```

```http
GET /v1/simulacoes/{id}
```

Estados: `recebida`, `processando`, `parcial`, `concluida`, `falhou`, `aguardando_intervencao`.
Cada banco possui seu próprio `status`, `codigo_erro`, tentativas e timestamps. No mock, o `POST`
pode devolver `201` com `concluida`, mantendo o mesmo recurso e formato.

### Eventos do WhatsApp

- `provider_message_id` tem restrição `UNIQUE` por instância.
- Webhook autenticado e persistido antes do processamento.
- Reentrega do mesmo evento devolve sucesso sem gerar nova resposta.
- Saída do bot registra o ID retornado pela Evolution para diferenciar bot de atendente.
- Falhas transitórias têm retry limitado; falhas finais ficam consultáveis.

## Tasks

### Task 1: Registrar as decisões arquiteturais

**Files:**
- Create: `docs/architecture/0001-core-api-monolito-modular.md`
- Create: `docs/architecture/0002-multitenancy-autorizacao.md`
- Create: `docs/architecture/0003-simulacao-assincrona.md`
- Create: `docs/architecture/0004-dados-pessoais-lgpd.md`

**Critério de aceite:** cada decisão documenta contexto, decisão, consequências e alternativas
rejeitadas. Os planos seguintes referenciam essas decisões em vez de contradizê-las.

### Task 2: Definir o modelo relacional canônico

**Files:**
- Create: `docs/modelo-dados.md`
- Create: `docs/diagramas/modelo-dominio.mmd`

Requisitos:

- IDs estáveis (UUID para recursos expostos; inteiro interno é aceitável onde não vaza).
- `loja_id NOT NULL REFERENCES lojas(id)` em toda tabela de tenant.
- `veiculos.loja_id`, `leads.loja_id`, `mensagens.loja_id` e `conversas.loja_id` obrigatórios.
- `usuarios.papel` com enum/check dos quatro papéis.
- `leads.vendedor_id` opcional e pertencente à mesma loja.
- estados definidos com `CHECK`/enum, não strings livres.
- timestamps com timezone (`TIMESTAMPTZ`) e estratégia de soft delete quando houver auditoria.
- índices por `(loja_id, criado_em)`, responsáveis e IDs externos idempotentes.

**Critério de aceite:** o modelo consegue responder, sem inferência ambígua: leads por vendedor,
tempo de primeira resposta, conversão, veículos vendidos, faturamento, lucro bruto e origem da venda.

### Task 3: Versionar os contratos HTTP e de produto

**Files:**
- Create: `docs/contracts/chatbot-api-v1.yaml`
- Create: `docs/contracts/motor-simulacao-v1.yaml`
- Create: `docs/contracts/estoque-api-v1.yaml`
- Create: `docs/contracts/eventos-whatsapp.md`
- Create: `docs/contracts/integracao-produtos.md`

Incluir, no mínimo:

- `/v1/leads`, `/v1/conversas`, `/v1/mensagens`;
- `/v1/veiculos` e `/v1/public/lojas/{slug}/veiculos`;
- `/v1/simulacoes` e `/v1/simulacoes/{id}`;
- erros padronizados com `code`, `message`, `request_id`;
- paginação, filtros e regras de idempotência;
- campos de contexto que nunca podem ser fornecidos livremente pelo cliente.

**Critério de aceite:** cada produto pode ser instalado e testado sem os demais. Na suíte, eles se
integram usando somente contratos documentados, sem conhecer tabelas internas.

### Task 3A: Definir empacotamento do Chatbot Standalone

**Files:**
- Create: `deploy/chatbot-standalone/docker-compose.yml`
- Create: `deploy/chatbot-standalone/.env.example`
- Create: `docs/produtos/chatbot-standalone.md`

O pacote deve declarar healthchecks, volumes, backup, criação da primeira loja, conexão do número,
credenciais e opções de provider. Inclui `estoque-api` em modo Lite, mas não pode referenciar
containers de Portal ou Catálogo Público.

**Teste de independência:** em ambiente vazio, somente o compose standalone deve permitir conectar
um WhatsApp, cadastrar veículos, responder quais estão disponíveis, conversar, consentir, gerar
lead, executar a simulação configurada e exportar o lead.

### Task 4: Criar a matriz de autorização e testes de ameaça

**Files:**
- Create: `docs/security/matriz-autorizacao.md`
- Create: `docs/security/threat-model.md`

Cobrir:

- ações por `admin_plataforma`, `dono`, `gerente` e `vendedor`;
- isolamento entre lojas;
- vendedor vendo apenas leads próprios quando configurado;
- webhook falso, replay, IDOR, CSRF, brute force e vazamento em logs;
- credenciais n8n/Evolution/bancos, rotação e acesso mínimo;
- trilha de auditoria para handoff, exclusão, venda e alteração de papel.

**Critério de aceite:** existe um caso de teste negativo para cada fronteira relevante, especialmente
“usuário da loja A não lê/altera/remove recurso da loja B”.

### Task 5: Definir o ciclo LGPD ponta a ponta

**Files:**
- Create: `docs/security/lgpd-ciclo-dados.md`

Documentar coleta, finalidade, consentimento versionado, armazenamento cifrado, acesso, logs,
backup, retenção, anonimização/exclusão e propagação da exclusão para:

- leads, mensagens e memória do n8n;
- simulações e resultados bancários;
- auditoria com dados minimizados;
- backups e exportações.

**Critério de aceite:** o comando de exclusão produz um relatório interno do que foi excluído,
anonimizado ou retido por obrigação, sem registrar CPF em texto claro.

### Task 6: Gate de prontidão para iniciar os Planos #1A e #2A

- [ ] Vocabulário e limites do domínio aprovados.
- [ ] Modelo multi-loja sem `loja_id` opcional em dados operacionais.
- [ ] Papéis e matriz de autorização aprovados.
- [ ] Contratos v1 e estados da simulação aprovados.
- [ ] Estratégia de idempotência de mensagens aprovada.
- [ ] Estratégia de cifra, chaves e logs aprovada.
- [ ] Métricas do dono e vendedor possuem fonte de dados definida.

## Nova ordem de entrega

1. **Plano #0:** contratos, limites de produto e segurança.
2. **Plano #1A:** Motor de Simulação independente com mock.
3. **Plano #4A:** Estoque API e modo Lite reutilizável nos pacotes.
4. **Plano #2A:** Chatbot Standalone + Estoque Lite; Motor é provider opcional.
5. **Plano #5A:** Catálogo público conectado ou empacotado com Estoque.
6. **Plano #3A:** Portal do vendedor, consumindo APIs opcionais do Bot/Motor/Estoque.
7. **Plano #3B:** vendas, metas e dashboard do dono.
8. Primeiro driver bancário real.
9. Evoluções priorizadas do Plano #6.

## Fora de escopo deste plano

- Implementar postagem ou compra de mídia.
- Escolher fornecedor de tráfego/redes sociais.
- Calcular lucro líquido contábil; o primeiro dashboard usa **lucro bruto da venda**
  (`preco_venda - custo_veiculo - custos_diretos`), claramente rotulado.
- Criar microserviços separados antes de existir necessidade operacional.

## Resultado

Ao concluir o Plano #0, os planos existentes deixam de construir apenas um bot e passam a entregar
produtos independentes que também compõem a mesma plataforma. O Chatbot Standalone é instalável,
operável e revendível sem Portal, Catálogo Público ou módulos de marketing.
