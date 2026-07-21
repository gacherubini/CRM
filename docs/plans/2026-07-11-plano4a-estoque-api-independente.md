# Plano #4A — Estoque API Independente

> Plano válido do Estoque. Legado em `_archive/`. Estoque não pertence ao Motor nem ao Portal.
>
> **Status 2026-07-13:** núcleo (CRUD, tenancy, público, outbox, admin parcial) **entregue**;
> **`placa` + `GET /v1/veiculos/por-placa` + filtro + CSV + unicidade** **entregues** (migration `0005`);
> **placa no admin HTMX** (form/painel) e no Portal form/lista **feitos**.
> **Hardening 2026-07-21:** cadastro idempotente persistente, upload em volume e limpeza
> administrativa/automática de mídias órfãs entregues. **Aberto:** E2E outbox/restore; admin 100% fechado.
> Seção “CRM WhatsApp privado” = decisão de produto para o pacote Chatbot+Estoque Lite.

**Goal:** Entregar um produto de estoque multi-loja, com API, administração mínima, importação e
publicação próprias, vendável sem Chatbot, Portal ou Catálogo.

**Stack:** FastAPI, Jinja2/HTMX para admin mínimo, PostgreSQL, SQLAlchemy/Alembic, pytest e Docker.

## Critérios de independência

1. Compose próprio com Estoque API/admin e Postgres.
2. Veículo pode ser cadastrado e publicado sem Portal.
3. API privada e API pública possuem credenciais/permissões separadas.
4. Nenhum endpoint aceita `loja_id` livre sem validar o contexto autenticado.
5. Chatbot, Portal e Catálogo são consumidores opcionais.
6. CSV permite entrada/saída sem integração.

## Modelo inicial

- `lojas`: tenant, nome, slug e contatos públicos.
- `usuarios_estoque`: dono/gerente/operador.
- `veiculos`: tipo, marca, modelo, versão, ano/modelo, cor, km, preço, custo restrito, status,
  publicação, **placa** (identificador comercial da unidade), código interno/chassi mascarado e
  timestamps.
- `veiculo_fotos`: preparado desde o início, mesmo que a primeira versão aceite URLs.
- `importacoes`: arquivo, linhas, erros e resultado.
- `eventos_saida`: outbox para alterações/publicação.
- `auditoria`.

**Placa (obrigatória no pacote CRM WhatsApp privado):**

- Campo `placa` normalizado (sem hífen/espaços; maiúsculas; aceitar Mercosul e formato antigo).
- Unicidade por loja: `(loja_id, placa)` quando placa preenchida.
- Busca privada por placa para o Chatbot/Portal resolvê-la em **um** veículo (marca, modelo, ano,
  preço, status) **sem** o bot inventar valor.
- API pública **não** precisa expor placa se a loja preferir só slug/id; a consulta por placa é
  privada (credencial de serviço do Chatbot / admin).

Status inicial: `disponivel`, `reservado`, `vendido`, `indisponivel`. Apenas `disponivel` e
`publicado=true` aparece na API pública.

## Contratos

### API privada `/v1`

- `POST /v1/veiculos`
- `GET /v1/veiculos` (filtros: tipo, status, publicado, busca, **placa**)
- `GET /v1/veiculos/{id}`
- `GET /v1/veiculos/por-placa/{placa}` — resolve unidade da loja autenticada (404 se inexistente)
- `PATCH /v1/veiculos/{id}`
- `POST /v1/veiculos/{id}/publicar`
- `POST /v1/veiculos/{id}/despublicar`
- `POST /v1/veiculos/{id}/reservar`
- `POST /v1/veiculos/{id}/vender`
- `POST /v1/importacoes`
- `GET /v1/exportacoes/veiculos.csv`

Mutação aceita `Idempotency-Key`. Remoção física não é a operação comum; mudança de status mantém
histórico e referências.

CSV de importação inclui coluna `placa` (recomendado no pacote com Chatbot).

### API pública `/public/v1`

- `GET /public/v1/lojas/{slug}`
- `GET /public/v1/lojas/{slug}/veiculos`
- `GET /public/v1/lojas/{slug}/veiculos/{id-ou-slug}`

Nunca expor custo, chassi, auditoria, usuário ou dado de fornecedor.

## Tasks

### Task 1: Scaffold, migrations e compose

Criar `estoque-api/` e `deploy/estoque-standalone/`, health/version, Alembic e configuração sem
dependências externas obrigatórias.

### Task 2: Autenticação, RBAC e tenancy

Papéis `dono`, `gerente`, `operador` e credenciais de serviço. Toda query privada é escopada pela
identidade; API pública resolve somente slug publicado.

**Aceite:** loja A não lê/altera/reserva veículo da loja B, inclusive por ID conhecido.

### Task 3: CRUD e transições de estado

Implementar validação de tipo, preço, km, ano, **placa**, publicação e transições. `vendido` não
volta para `disponivel` sem ação autorizada/auditada de estorno. Incluir `GET .../por-placa/{placa}`
e unicidade `(loja_id, placa)`.

### Task 4: Administração mínima própria

Tela responsiva para listar, buscar, cadastrar, editar, publicar, reservar e marcar vendido. Essa
tela é parte do produto Estoque e não depende do Portal de Gestão.

### Task 5: Fotos

Primeira entrega aceita URLs validadas e ordenação em `veiculo_fotos`. Definir interface de storage
para futura implementação S3/R2/MinIO sem alterar o contrato do veículo.

### Task 6: Importação e exportação CSV

Upload com prévia, mapeamento de colunas, validação por linha e relatório de erros. Importação é
idempotente por loja+código interno quando configurado.

### Task 7: API pública

Entregar somente campos autorizados, paginação, filtros por tipo/marca/faixa de preço e cache
condicional (`ETag`/`Last-Modified`). Aplicar rate limit apropriado.

### Task 8: Eventos e integrações

Emitir `vehicle.created`, `vehicle.updated`, `vehicle.published`, `vehicle.reserved` e
`vehicle.sold` por webhook assinado com outbox/retry. Consumidores não escrevem no banco.

### Task 9: Auditoria e consistência

Auditar preço, custo, status, publicação e autoria. Testar concorrência de reserva/venda para que
duas solicitações não confirmem o mesmo veículo.

### Task 10: Operação e teste de revenda

Documentar onboarding, branding mínimo, backup/restore, upgrade e rotação de credenciais. Em
ambiente limpo, cadastrar/importar, publicar, consultar pela API pública, reservar, vender e restaurar.

## Integrações opcionais

- Chatbot usa `HttpInventoryProvider` para busca/interesse **e** resolução por **placa**.
- Portal usa API privada com credencial própria e permissões limitadas.
- Catálogo Público usa somente `/public/v1`.

## Pacote “CRM estoque no WhatsApp privado” (Estoque Lite + Chatbot)

O Estoque **não** roda a simulação. Ele é a fonte da **moto específica**. O fluxo mínimo de
simulação no WhatsApp privado (Chatbot Financiamento) fica assim:

```text
Cliente no WhatsApp (telefone já conhecido pela Evolution)
        │
        ▼
Chatbot: pede placa + dados mínimos do cliente + entrada
        │
        ├── Estoque API (privada): GET por placa → valor, marca, modelo, ano, status
        │     (recusa se não existir / vendido / outra loja)
        │
        └── SimulationProvider (mock | http Motor)
              enfileira com telefone + placa + veículo resolvido + pessoa + entrada
              └── resultado financeiro fica no Motor/Portal; bot faz handoff
```

### O que o bot **não** pede mais (MVP WhatsApp)

| Campo antigo nos planos | Decisão MVP |
|---|---|
| `prazo_meses` (“prazo da moto” / prazo desejado) | **Remover da coleta.** Mock/Motor usam prazos padrão configuráveis (ex.: 12/24/36/48); as opções ficam disponíveis ao vendedor. Cliente não escolhe um prazo único antes de simular. |
| `renda` (renda mensal) | **Remover da coleta e do payload obrigatório.** Opcional só em drivers bancários reais futuros, se o banco exigir. |

### O que o bot **passa a** exigir / enviar

| Campo | Origem | Uso |
|---|---|---|
| `telefone` | WhatsApp (Evolution) — **obrigatório** | Lead, conversa, handoff, referência no CRM. Hoje falta no payload de simulação; deve ir em `referencia` / `lead` e no resumo persistido. |
| `placa` | Cliente digita / vendedor informa | Resolve o veículo no Estoque; simulação da **unidade** certa, não de um valor solto. |
| `entrada` | Cliente | Condição de financiamento. |
| `cpf` (+ `nascimento` se o mock/Motor ainda validar idade) | Cliente | Identidade da simulação; CPF mascarado em mensagens. |
| `veiculo.valor` / marca / modelo / ano | **Só do Estoque** após placa | Nunca inventar preço no LLM. |

### Payload alvo (Chatbot → SimulationProvider / Motor)

Estado **atual** (mock) ainda usa o contrato antigo com `prazo_meses` e `renda` (ver Plano #1A e
código `chatbot-api` / `motor-simulacao`). Contrato **alvo** do CRM WhatsApp privado:

```json
{
  "referencia_externa": "wa:5511999999999",
  "telefone": "5511999999999",
  "pessoa": {
    "cpf": "12345678909",
    "nascimento": "1990-05-20"
  },
  "veiculo": {
    "placa": "ABC1D23",
    "veiculo_id": "uuid-estoque",
    "categoria": "moto",
    "marca": "Honda",
    "modelo": "CG 160",
    "ano_modelo": 2023,
    "valor": 18500
  },
  "condicoes": {
    "entrada": 3000
  },
  "prazos_padrao": [12, 24, 36, 48]
}
```

- Sem `renda`.
- Sem `prazo_meses` único na entrada; o mock calcula **uma linha por prazo padrão** (ou o Motor
  devolve resultados multi-prazo).
- `telefone` e `placa` obrigatórios no fluxo WhatsApp; valor do veículo **só** após lookup Estoque.

### Como a simulação está escrita **hoje** (mock — não mudar o plano sem código)

1. **Plano #1A (Motor):** `POST /v1/simulacoes` com `pessoa.cpf/nascimento/renda`, `veiculo.valor`,
   `condicoes.entrada/prazo_meses`, `provedores: ["mock"]`. Job async; worker roda `MockDriver`
   (Price + taxas **fictícias**). Ver `motor-simulacao/app/motor/mock.py`.
2. **Chatbot:** `SimulationProvider` = `none` | `mock` | `http`.
   - `mock`: Price local em `chatbot-api/app/simulation.py` (BancosDemo, sem Motor).
   - `http`: repassa o payload ao Motor e faz polling.
3. **n8n/WhatsApp:** tool chama `POST /v1/simular` do Chatbot; o workflow **não** sabe se é mock.
4. **Portal:** formulário manual ainda manda cpf, valor, entrada, prazo, renda → mesmo endpoint.
5. **Importante:** nomes Pan/BV/Bradesco no WhatsApp = **sempre mock** até existir driver `real: true`.

A evolução “placa + telefone, sem prazo/renda na coleta” é **decisão de produto** deste pacote;
implementação toca Estoque (#4A placa), Chatbot (#2A tools/payload) e, se necessário, contrato do
Motor (#1A) para multi-prazo e campos opcionais.

## Fora de escopo do produto Estoque sozinho

- CRM, leads e conversas (ficam no Chatbot).
- Cálculo de parcela / integração bancária (ficam no Chatbot mock ou Motor).
- Dashboard de vendas/metas.
- Upload binário na primeira entrega, se URLs forem suficientes para o piloto.

## Resultado

Um produto de estoque operável e vendável sozinho, que também serve como fonte confiável para as
outras superfícies.
