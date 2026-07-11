# Plano #4A — Estoque API Independente

> **Substitui o Plano #4 legado.** Estoque não pertence ao Motor nem ao Portal.

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
  publicação, código interno/chassi mascarado e timestamps.
- `veiculo_fotos`: preparado desde o início, mesmo que a primeira versão aceite URLs.
- `importacoes`: arquivo, linhas, erros e resultado.
- `eventos_saida`: outbox para alterações/publicação.
- `auditoria`.

Status inicial: `disponivel`, `reservado`, `vendido`, `indisponivel`. Apenas `disponivel` e
`publicado=true` aparece na API pública.

## Contratos

### API privada `/v1`

- `POST /v1/veiculos`
- `GET /v1/veiculos`
- `GET /v1/veiculos/{id}`
- `PATCH /v1/veiculos/{id}`
- `POST /v1/veiculos/{id}/publicar`
- `POST /v1/veiculos/{id}/despublicar`
- `POST /v1/veiculos/{id}/reservar`
- `POST /v1/veiculos/{id}/vender`
- `POST /v1/importacoes`
- `GET /v1/exportacoes/veiculos.csv`

Mutação aceita `Idempotency-Key`. Remoção física não é a operação comum; mudança de status mantém
histórico e referências.

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

Implementar validação de tipo, preço, km, ano, publicação e transições. `vendido` não volta para
`disponivel` sem ação autorizada/auditada de estorno.

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

- Chatbot usa `HttpInventoryProvider` somente para busca/interesse.
- Portal usa API privada com credencial própria e permissões limitadas.
- Catálogo Público usa somente `/public/v1`.

## Fora de escopo

- CRM, leads e conversas.
- Simulação financeira.
- Dashboard de vendas/metas.
- Upload binário na primeira entrega, se URLs forem suficientes para o piloto.

## Resultado

Um produto de estoque operável e vendável sozinho, que também serve como fonte confiável para as
outras superfícies.
