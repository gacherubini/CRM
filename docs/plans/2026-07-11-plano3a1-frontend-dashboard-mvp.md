# Plano #3A.1 — Frontend do Dashboard MVP

> **Workstream executável do Plano #3A.** Pode começar agora em paralelo à evolução do Chatbot.
> O primeiro MVP conecta Estoque e Leads reais; vendas, metas e lucro entram somente no Plano #3B.

**Goal:** Entregar o primeiro Dashboard web utilizável por dono, gerente e vendedor, com login,
navegação responsiva, gestão completa do estoque, visualização de leads e controle de handoff — sem
expor tokens internos ao navegador e sem depender diretamente dos bancos dos outros produtos.

**Stack escolhida:** FastAPI, Jinja2, HTMX, Tailwind CSS compilado, SQLAlchemy/Alembic, PostgreSQL,
httpx, sessão segura, pytest e Playwright para os fluxos críticos.

## 1. Decisões de arquitetura

### Backend for Frontend (BFF)

O navegador conversa somente com o Portal:

```text
Browser
   ↓ sessão/cookie
Portal FastAPI (BFF)
   ├── Estoque API (token de serviço)
   ├── Chatbot API (token de serviço)
   └── Motor (opcional, depois)
```

Tokens de Estoque, Chatbot e Motor ficam no servidor/cofre. Nunca aparecem em HTML, JavaScript,
localStorage, cookies legíveis ou respostas do browser.

### Fonte de verdade

- Veículos: Estoque API.
- Leads, estado do bot e conversas de WhatsApp: Chatbot API.
- Usuários, papéis, sessões, tarefas e preferências: banco próprio do Portal.
- Vendas, metas e campanhas: banco do Portal, mas somente no Plano #3B.

### Sem métricas fictícias

O Dashboard inicial mostra apenas métricas calculáveis com os contratos existentes. Cards de
faturamento, lucro e meta não recebem números mock em produção; ficam ausentes ou marcados como
“módulo ainda não habilitado”. Fixtures são permitidas somente em testes e story/demo local.

## 2. Contratos disponíveis hoje

### Estoque API — pronto para integração

- `GET /v1/veiculos?tipo=&status=&publicado=&busca=`
- `POST /v1/veiculos`
- `GET /v1/veiculos/{id}`
- `PATCH /v1/veiculos/{id}`
- `POST /v1/veiculos/{id}/publicar`
- `POST /v1/veiculos/{id}/despublicar`
- `POST /v1/veiculos/{id}/reservar`
- `POST /v1/veiculos/{id}/vender`

### Chatbot API — pronto para integração

- `GET /v1/leads?etapa=`
- `GET /v1/leads/{id}`
- `GET /v1/leads.csv`
- `GET /v1/conversas/{telefone}/estado`
- `PATCH /v1/conversas/{telefone}/estado`
- `POST /v1/simular` (somente quando habilitado)

### Lacunas que bloqueiam telas completas

Antes de mostrar threads reais, a Chatbot API precisa produzir:

- `GET /v1/conversas` — lista paginada, última mensagem e estado;
- `GET /v1/conversas/{telefone}/mensagens` — histórico paginado;
- filtros por período, estado e busca;
- saída sem CPF ou outros dados desnecessários.

Antes do Dashboard financeiro, o Portal precisa implementar o domínio do Plano #3B.

## 3. Rotas do Portal

```text
/login
/logout

/app                         visão geral operacional
/app/leads
/app/leads/{id}
/app/conversas
/app/conversas/{telefone}
/app/estoque
/app/estoque/novo
/app/estoque/{id}
/app/simulacoes
/app/equipe
/app/configuracoes

# Entram no Plano #3B
/app/vendas
/app/metas
/app/campanhas
```

## 4. Navegação por papel

### Dono

Visão geral, Leads, Conversas, Estoque, Simulações, Equipe e Configurações. Pode ver custo do
veículo, publicar, vender e administrar usuários.

### Gerente

Leads, Conversas, Estoque e Simulações. Pode cadastrar, editar, publicar, reservar e vender,
conforme política da loja. Não administra a plataforma.

### Vendedor

Leads atribuídos, Conversas autorizadas e Estoque. Não vê custo do veículo nem credenciais; ações
de publicação/venda dependem de permissão explícita.

Autorização é aplicada no backend das rotas. Ocultar botão não é controle de acesso suficiente.

## 5. Estrutura planejada

```text
portal-gestao/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── auth.py
│   ├── tenancy.py
│   ├── csrf.py
│   ├── models.py
│   ├── routes/
│   │   ├── auth.py
│   │   ├── dashboard.py
│   │   ├── estoque.py
│   │   ├── leads.py
│   │   ├── conversas.py
│   │   └── configuracoes.py
│   ├── clients/
│   │   ├── estoque.py
│   │   ├── chatbot.py
│   │   └── motor.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── components/
│   │   ├── dashboard/
│   │   ├── estoque/
│   │   ├── leads/
│   │   └── conversas/
│   └── static/
│       ├── src/app.css
│       └── dist/app.css
├── alembic/
├── tests/
├── Dockerfile
├── requirements.txt
└── package.json

deploy/portal-standalone/
├── docker-compose.yml
├── .env.example
└── README.md
```

## 6. Componentes visuais mínimos

- `AppShell`: menu lateral desktop + drawer mobile.
- `PageHeader`: título, descrição e ações.
- `MetricCard`: somente para métrica real e definida.
- `DataTable`: cabeçalho, paginação, vazio, erro e carregamento.
- `StatusBadge`: disponível, reservado, vendido, publicado, novo, handoff.
- `FilterBar`: busca e filtros persistidos na URL.
- `ConfirmDialog`: ações destrutivas/irreversíveis.
- `FlashMessage`: sucesso, aviso e erro.
- `FormField`: label, ajuda e erro acessível.
- `EmptyState` e `IntegrationUnavailable`.

Toda tela precisa funcionar em 320 px, por teclado e com contraste adequado.

## 7. Tasks

### Task 1: Scaffold e health

**Create:**

- `portal-gestao/app/main.py`
- `portal-gestao/app/config.py`
- `portal-gestao/app/db.py`
- `portal-gestao/requirements.txt`
- `portal-gestao/pytest.ini`
- `portal-gestao/tests/test_health.py`

**Produces:**

- `GET /health/live`
- `GET /health/ready` verificando banco e configuração mínima.

**Aceite:** suíte inicia sem Chatbot/Motor; falha de configuração da Estoque API aparece no ready.

### Task 2: Banco próprio, migrations e usuário inicial

Criar com Alembic:

- `lojas_portal` com referência externa/slug da loja;
- `usuarios` com email, senha hash, papel, loja e ativo;
- `sessoes` ou sessão assinada com estratégia de revogação;
- `integracoes` com URLs e referência segura aos tokens;
- `auditoria` para login e ações administrativas.

Criar CLI `criar-dono` para onboarding, sem usuário/senha default em produção.

### Task 3: Autenticação, sessão, CSRF e RBAC

Implementar login/logout, hash Argon2 ou bcrypt atualizado, cookies `HttpOnly`, `SameSite=Lax`,
`Secure` em produção, expiração, rate limit e CSRF em toda mutação HTML/HTMX.

**Testes:** senha inválida, sessão expirada, CSRF ausente e usuário de outra loja.

### Task 4: Clientes HTTP server-side

Implementar `EstoqueClient`, `ChatbotClient` e interface `MotorClient` com:

- `httpx.Client`/`AsyncClient`;
- timeout curto e explícito;
- autenticação no servidor;
- erro de domínio amigável;
- `request_id` e logs sem tokens;
- testes usando `httpx.MockTransport`.

O frontend nunca monta `Authorization: Bearer` no browser.

### Task 5: Design system e AppShell

Compilar Tailwind localmente. Criar layout, menu por papel, breadcrumbs, estados e componentes
listados na seção 6. Não usar CDN obrigatória em produção.

**Aceite visual:** desktop 1366 px e mobile 390 px sem overflow, controles cortados ou texto
ilegível. Navegação completa por teclado.

### Task 6: Visão geral operacional

Primeira versão calcula, pelas APIs atuais:

- total de veículos disponíveis, reservados e publicados;
- total de leads e leads novos;
- aviso de integração Chatbot/Motor;
- atalhos para cadastrar veículo, abrir leads e conversas.

Não mostrar faturamento/lucro/meta até o Plano #3B.

### Task 7: Estoque — lista e filtros

Conectar `GET /v1/veiculos`. Entregar busca, filtros por tipo/status/publicado, formatação BRL/km,
foto/fallback, paginação visual e ações autorizadas.

Estados obrigatórios: carregando, vazio, sem resultado, API indisponível e erro de autenticação.

### Task 8: Estoque — cadastro e edição

Formulário para tipo, marca, modelo, versão, ano, cor, km, preço, custo, código interno e foto URL.
Validação ocorre no Portal para UX e novamente na Estoque API.

**Permissão:** custo só é enviado/exibido para dono/gerente autorizado.

### Task 9: Estoque — publicação e transições

Integrar publicar, despublicar, reservar e vender. Usar confirmação com descrição da consequência:

- publicar: aparece no Catálogo Público;
- reservar: deixa de estar livre para outra reserva;
- vender: despublica automaticamente e não volta sem fluxo auditado futuro.

Após ação HTMX, atualizar linha/cards sem recarregar a aplicação inteira.

### Task 10: Leads — lista e detalhe

Conectar endpoints atuais da Chatbot API. Mostrar telefone mascarável, nome quando consentido,
interesse, etapa, consentimento e criação. Filtros por etapa e busca local inicial.

O detalhe não exibe CPF/nascimento nem inventa responsável, origem ou histórico inexistentes.

### Task 11: Fechar lacuna de conversas na Chatbot API

Antes da UI de thread, implementar e testar na Chatbot API:

- `GET /v1/conversas`;
- `GET /v1/conversas/{telefone}/mensagens`;
- paginação e ordenação;
- tenancy;
- conteúdo mínimo de mensagem, direção e timestamp.

**Aceite de segurança:** loja A não consulta thread da loja B; respostas não contêm token, CPF ou
payload bruto da Evolution.

### Task 12: Conversas e handoff

Criar lista de conversas, thread visual e estado do bot. Ações:

- “Assumir atendimento” → `bot_ativo=false`;
- “Devolver ao bot” → `bot_ativo=true`;
- destaque claro de handoff;
- envio manual de mensagem fica fora desta primeira fatia, salvo contrato específico.

O auto-handoff já implementado na Chatbot API continua funcionando quando o atendente responde pelo
WhatsApp; o Portal apenas reflete/controla o estado.

### Task 13: Simulação manual opcional

Mostrar a rota somente quando `SimulationProvider` estiver disponível. Formulário server-side,
consentimento operacional explícito e resposta real da API. Nunca calcular/inventar parcela no
frontend.

### Task 14: Docker e composição

Criar `portal-gestao/Dockerfile` e `deploy/portal-standalone/docker-compose.yml`. No pacote Dashboard,
a Estoque API é incluída. Chatbot e Motor são URLs opcionais.

Porta sugerida do Portal: `9000`.

### Task 15: Teste E2E do MVP

Com Playwright:

1. dono faz login;
2. cadastra veículo;
3. publica e confirma na API pública do Estoque;
4. filtra e edita veículo;
5. abre lista/detalhe de lead;
6. abre conversa e assume/devolve ao bot;
7. vendedor não vê custo/configuração;
8. indisponibilidade de Chatbot não derruba Estoque;
9. nenhum token aparece em HTML, storage ou requests do browser.

## 8. Sequência de entrega

### Incremento A — Fundação visual

Tasks 1–5. Resultado: login, layout responsivo, RBAC e clientes HTTP testados.

### Incremento B — Estoque em produção

Tasks 6–9. Resultado: dono/gerente administra veículos pelo Dashboard e publicação alimenta a API
pública usada pelo Catálogo.

### Incremento C — Leads e handoff

Tasks 10–12. Resultado: operação do Chatbot visível/controlável pelo Portal.

### Incremento D — Simulação e empacotamento

Tasks 13–15. Resultado: Dashboard MVP instalável e testado ponta a ponta.

## 9. O que fica para o Plano #3B

- registro e confirmação de venda comercial;
- custos diretos e lucro bruto;
- metas por loja/vendedor;
- funil histórico e tempo de resposta;
- campanhas e atribuição;
- dashboard financeiro e gráficos reconciliados;
- exportações de vendas/metas.

## 10. Definition of Done

- [ ] Login, sessão, CSRF, RBAC e tenancy testados.
- [ ] Estoque completo operado pelo Dashboard usando API, sem acesso direto ao banco.
- [ ] Publicação reflete na API pública/ futuro Catálogo.
- [ ] Leads reais listados sem dados pessoais desnecessários.
- [ ] Conversas e handoff funcionam após os novos endpoints.
- [ ] Tokens não chegam ao navegador.
- [ ] Mobile, teclado, vazio, erro e loading verificados.
- [ ] Testes unitários, integração e E2E passando.
- [ ] Compose e onboarding documentados.

## Resultado

Um Dashboard MVP que já resolve operação diária de estoque, leads e handoff, com uma fundação visual
reutilizável para vendas, metas e métricas do dono no Plano #3B.
