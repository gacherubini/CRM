# Plano #3A — Portal do Vendedor Independente

> **Primeira fatia válida do Portal de Gestão.** Não acessa o banco do Chatbot, Motor ou Estoque.
> O pacote comercial do Dashboard inclui a Estoque API e a administra exclusivamente por contrato.
>
> **Status 2026-07-21:** base + #3A.1 entregues; **RBAC sim. vendedor (Task 13) feito**;
> **Task 9A** UI `/app/financeiras` (BFF → Motor credenciais) **feita**; gestão de
> **Equipe feita** (criar/editar/senha/ativar/desativar com RBAC + tenancy).
> **Ajustes/configuração real feita** (`/app/configuracoes`, RBAC e status seguro das integrações).
> **Aberto:** Playwright E2E (#3A.1 Task 15).

**Goal:** Entregar um portal revendível em que a loja administra usuários e vendedores, organiza
leads, registra atividades e administra o estoque incluído; Chatbot e Motor são opcionais.

**Stack:** FastAPI, Jinja2/HTMX, PostgreSQL, SQLAlchemy/Alembic, sessão segura, pytest e Docker.

## Critérios de independência

1. Compose próprio com Portal, Estoque API e Postgres com dados/credenciais separados.
2. Primeiro acesso e operação não exigem os outros produtos.
3. Nenhuma query usa tabela/view externa.
4. Integrações possuem adapter, timeout, retry e estado desconectado legível.
5. Leads podem ser criados manualmente, importados por CSV ou recebidos por webhook/API.
6. Chatbot/Motor indisponíveis não quebram o Portal; Estoque API faz parte do pacote suportado.

## Papéis

- `admin_plataforma`: administra clientes/lojas da instalação.
- `dono`: acesso total à própria loja.
- `gerente`: equipe, leads e operação, sem segredos/faturamento da plataforma.
- `vendedor`: leads próprios/compartilhados conforme política da loja.

Toda autorização valida usuário, papel, `loja_id` e propriedade do recurso no backend.

## Dados do Portal

- `lojas`, `usuarios`, `vendedores`;
- `leads_comerciais`: cópia operacional própria, com `origem_externa` e `referencia_externa`;
- `lead_etapas`, `lead_historico`, `atividades`, `tarefas`;
- `integracoes`: tipo, URL, estado e referência ao segredo no cofre/env;
- `eventos_recebidos`: idempotência de webhooks/importações;
- `auditoria`.

CPF completo não é necessário para a gestão comum e não entra na projeção recebida do Chatbot.

## Integrações opcionais

- `ChatbotProvider`: importa leads, consulta conversa e solicita handoff.
- `SimulationProvider`: cria/consulta simulação manual.
- `InventoryProvider`: integração obrigatória do pacote com a Estoque API incluída.
- `NoChatbotProvider`/`NoSimulationProvider`: mantêm CRM e Estoque funcionais sem Bot/Motor.

## Tasks

### Task 1: Scaffold e compose standalone

Criar `portal-gestao/` e `deploy/portal-standalone/` com Portal, Estoque API, Postgres, migrations,
health e `.env.example`. Chatbot e Motor não aparecem como serviços obrigatórios.

**Aceite:** instalação limpa abre onboarding e cria a primeira loja/dono.

### Task 2: Autenticação e segurança web

Implementar senha forte com Argon2/bcrypt atualizado, sessão segura, logout, rate limit de login,
CSRF, cookies `HttpOnly/Secure/SameSite`, recuperação administrativa e auditoria.

**Aceite:** testes cobrem sessão inválida, CSRF e tentativa cruzada entre lojas.

### Task 3: RBAC e tenancy

Implementar matriz do Plano #0 no backend e helpers de query sempre escopados por loja. IDs do
formulário não determinam tenant.

**Aceite:** suíte negativa prova que loja A e vendedor A não acessam recursos proibidos.

### Task 4: CRM mínimo próprio

Criar lead manual, etapas configuráveis, atribuição a vendedor, notas, atividade, próxima tarefa e
histórico imutável de mudanças relevantes.

**Aceite:** vendedor trabalha um lead completo sem Chatbot/Motor; Estoque incluído continua operável.

### Task 5: Entrada por CSV, API e webhook

Implementar importação com prévia/validação, endpoint autenticado e webhook idempotente. Deduplicar
por `(loja, origem, referencia_externa)` e permitir regras configuráveis para telefone duplicado.

**Aceite:** reenviar evento/CSV não duplica o mesmo lead externo.

### Task 6: Visão do vendedor

Página inicial com:

- leads atribuídos e por etapa;
- tarefas vencidas/hoje;
- novos leads ainda sem primeiro contato;
- ações rápidas: contatar, mover etapa, agendar e registrar observação.

Não mostrar faturamento/lucro neste plano.

### Task 7: Integração opcional com Chatbot

Consumir API para vincular lead, mostrar conversa read-only e solicitar assumir/devolver ao bot.
Falha de integração mostra estado e mantém o CRM utilizável.

### Task 8: Gestão de estoque incluída e Motor opcional

Criar no Dashboard as telas completas de cadastro, edição, publicação, reserva e venda consumindo a
Estoque API. Permitir simulação por `SimulationProvider`; sem Motor, ocultar apenas essa ação.

### Task 9: Administração mínima

Dono/gerente cadastram vendedores, desativam usuários, configuram etapas, distribuição de leads,
horários e integrações. Segredos nunca voltam completos para a interface.

> **Status parcial 2026-07-21 — Equipe FEITA:** Portal `/app/equipe` permite ao dono/admin da
> plataforma listar somente a loja atual, criar gerente/vendedor, editar nome/papel, redefinir
> senha e ativar/desativar sem exclusão física. E-mail é imutável para preservar referências;
> contas `dono`/`admin_plataforma` são protegidas contra gestão por terceiros. CSRF e testes
> negativos de tenancy cobrem todas as mutações. Configuração de horários, distribuição e a tela
> `/app/configuracoes` continuam abertas.

### Task 9A: Acessos das financeiras (rotação de senha)

> **Status: FEITA (2026-07-13).** UI `/app/financeiras`, client Motor, testes `test_financeiras.py`.
> Vendedor 403; senha nunca reexibida; env `MOTOR_URL`/`MOTOR_TOKEN`.

As senhas dos portais lojistas mudam com frequência (ex. **a cada ~2 semanas**). O Dashboard
precisa permitir atualizar sem redeploy e sem abrir ticket técnico.

**Tela** (só `dono` / `gerente`; vendedor sem acesso):

- Lista de provedores do Motor: nome, modo (`api` / `playwright` / `mock` / `agregador`), se
  credencial está configurada, data da última atualização, último login ok/erro sanitizado.
- Ações: **definir/atualizar usuário e senha** (form POST → Portal BFF → Motor
  `PUT /v1/provedores/{nome}/credenciais`); opcional **testar acesso**.
- Após salvar: UI mostra apenas “configurado em …” / máscara — **nunca** a senha de volta.
- Aviso se senha antiga (&gt; N dias) ou falhas recentes de login no Motor.

Regras:

- Tokens do Motor e senhas de banco **só no servidor** (BFF); zero no browser em localStorage.
- Não logar body com senha; auditar quem alterou.
- Sem Motor configurado: tela explica que a integração está desligada (não inventa mock de senha).

Detalhe de storage cifrado e API: **Plano #1A** (Tasks 11–12, seção híbrido + credenciais).

**Aceite:** dono troca senha do Pan no Portal; job seguinte usa a nova credencial; vendedor 403;
GET da tela não contém a senha em HTML.

### Task 10: Operação e revenda

Documentar instalação, branding, backup/restore, upgrade, criação de usuário, importação e suporte.
Executar teste E2E standalone e outro com providers falsos.

## Fora de escopo

- Vendas, metas e lucro (Plano #3B).
- Implementação interna do Estoque (pertence ao Plano #4A); o Portal apenas fornece a interface completa.
- Implementação dos drivers Playwright/API (Plano #1A); o Portal só gerencia credenciais e simulação manual via HTTP.
- Acesso direto ao banco de outro produto.

## Resultado

Um CRM/Portal útil ao vendedor e vendável sozinho, preparado para enriquecer a experiência quando
outros produtos estiverem conectados.
