# Plano — Evolução do Portal para Revy Loja

**Status:** ATIVO / F0–F1 em código (flags default OFF)
**Data:** 2026-07-29
**Spec:** [`docs/superpowers/specs/2026-07-29-revy-loja-design.md`](../superpowers/specs/2026-07-29-revy-loja-design.md)
**Depende por gates de:** [`Plano Revy Control`](2026-07-29-plano-revy-control.md) —
o desenvolvimento não espera o Control inteiro terminar.
**Vocabulário:** [`CONTEXT.md`](../../CONTEXT.md)
**Mapa de rotas F0:** [`portal-gestao/docs/revy-loja-route-map.md`](../../portal-gestao/docs/revy-loja-route-map.md)

## Objetivo

Transformar `portal-gestao` no **Revy Loja** sem reescrever os serviços que já
funcionam. O resultado terá somente:

- Vendas → Visão geral e Atendimento;
- Estoque → Visão geral e Veículos.

Chatbot, Seller AI e Simulação Multibanco ficam embutidos em Vendas. Catálogo fica
ligado aos veículos. Estoque não recebe IA.

## Situação inicial

Baseline verificado:

| Serviço | Testes passando |
|---|---:|
| Chatbot API | 170 |
| Portal | 293 |
| Estoque API | 87 |
| Catálogo Público | 37 |
| Motor de Simulação | 222 |
| **Total** | **809** |

Os workflows canônico e de teste do n8n também estavam válidos. Esse baseline é o
gate de regressão; cada fase adiciona testes sem reduzir essa cobertura.

## Restrições globais

- Evoluir `portal-gestao`; não criar uma aplicação Revy Loja paralela.
- Preservar contratos HTTP atuais e bancos separados.
- Não mover dados entre serviços somente para facilitar tela.
- Não remover rota ou menu antes de existir destino equivalente e redirect.
- Estrutura de pessoas/cargos e integrações técnicas pertencem ao Revy Control.
- Operação da equipe, negociação e venda pertencem ao Revy Loja.
- Acessos bancários permanecem na Loja e só podem ser geridos por dono/gerente.
- Meta, Google, tokens, webhooks e conexão WhatsApp não aparecem na Loja.
- Seller AI sugere; serviços determinísticos autorizam e executam.
- Estoque não usa IA.
- Mudanças entram por flags e migrations expand/contract.

## Dependências do Revy Control

| Necessidade do Revy Loja | Gate no Control |
|---|---|
| pessoa com várias lojas/cargos | Fase 2 — identidade e cargos |
| Vendas/Estoque contratados | Fase 2 — entitlements |
| resumo de aquisição Meta | Fase 3 — Central de Integrações sobre os dados atuais |
| resumo e conversões Google | Fase 4 — Google Ads |
| múltiplos números por loja | Fase 5 — Multi-WhatsApp |
| remoção definitiva de telas técnicas | Fases 3–4 — equivalentes no Control prontos |

O desenvolvimento visual pode começar com adapters em memória, mas o corte de
produção respeita esses gates.

### Cortes de produto entre os dois planos

- **MVP comercial base:** Control 0–3 + Loja 0–5. Entrega a Loja reorganizada, RBAC,
  dashboard comercial, Atendimento, Estoque e Simulação Multibanco usando a medição
  Meta já existente. Google não aparece como zero: fica indisponível até Control 4.
- **Google Ads:** Control 4; não bloqueia o MVP base se não fizer parte do escopo piloto.
- **Multi-WhatsApp:** Control 5 + Loja 6.
- **Seller AI e negociação ampliada:** Loja 7, depois do Atendimento estável.

## Fases e gates

| Fase | Entrega | Gate para avançar |
|---:|---|---|
| 0 | Baseline, contratos e flags | rollback e mapa de rotas conhecidos |
| 1 | Shell, identidade e dois módulos | menus e autorização por entitlement |
| 2 | Estoque consolidado | visão e veículos sem regressão |
| 3 | Visão geral de Vendas | KPIs confiáveis e sem configuração técnica |
| 4 | Atendimento unificado | negociação completa em um workspace |
| 5 | Equipe operacional e acessos bancários | limite Control/Loja aplicado |
| 6 | Múltiplos canais | conversa responde pelo canal correto |
| 7 | Seller AI, follow-ups e propostas | sugestões seguras e auditáveis |
| 8 | Rollout e limpeza | piloto estável e rotas antigas redirecionadas |

---

## Fase 0 — Baseline e segurança de migração

- [x] Registrar os 809 testes e comandos exatos por serviço.
      (comandos no mapa de rotas; contagens de referência do plano — reexecução integral opcional)
- [ ] Versionar fixtures sanitizadas dos contratos Portal → Chatbot, Motor, Estoque
      e Revy Control.
- [x] Mapear todas as rotas, templates e itens de navegação atuais para um destino.
      → `portal-gestao/docs/revy-loja-route-map.md`
- [x] Classificar cada configuração como estrutural, técnica, operacional ou financeira.
- [x] Criar flags default off:
      `REVY_LOJA_SHELL_ENABLED`, `REVY_LOJA_ENTITLEMENTS_ENABLED`,
      `REVY_LOJA_ATENDIMENTO_ENABLED` e `SELLER_AI_ENABLED`.
- [ ] Confirmar backup e restauração do banco do Portal.
- [x] Definir redirects e rollback antes da primeira remoção visual.

**Critério de pronto:** nenhuma função atual fica sem destino, e o shell antigo pode
ser restaurado apenas desligando flags.

---

## Fase 1 — Shell, identidade e entitlements

### Módulos

Criar interfaces em `portal-gestao/app/loja/`:

- `identity.py`: resolve pessoa, loja e cargos;
- `entitlements.py`: resolve Vendas/Estoque habilitados;
- `navigation.py`: produz navegação permitida;
- `types.py`: contratos independentes de FastAPI/SQLAlchemy.
- `control_projection.py`, `permissions.py` (+ wiring `app/web/loja_shell.py`).

### Tarefas

- [x] Criar port `ControlProjectionPort` com adapter HTTP e adapter em memória.
- [x] Aceitar contrato versionado e idempotente de pessoa, cargo, estado da loja e entitlement.
- [x] Manter `Usuario` atual como projeção compatível durante o cutover.
- [x] Permitir que uma pessoa escolha entre lojas autorizadas.
- [x] Permitir múltiplos cargos na mesma loja sem papel global implícito.
- [x] Calcular permissões pela união dos cargos ativos da loja selecionada; acesso da
      mesma pessoa ao Revy Control não concede nenhuma permissão operacional extra.
- [x] Renderizar somente Vendas e/ou Estoque conforme contrato.
- [x] Manter autorização no backend; menu oculto não é controle de acesso.
- [~] Definir degradação segura quando o Control estiver indisponível: sessão e
      entitlement previamente válidos podem usar cache curto; mudança estrutural não.
      (fail-open por flag + projeção local; cache curto de sessão fica para F1+/Control HTTP)

### Testes

- [x] Pessoa alterna entre duas lojas sem misturar sessão ou dados.
- [x] Cargo de uma loja não concede acesso em outra.
- [x] Pessoa que também é gestora no Control continua limitada aos cargos da Loja ao
      entrar no Revy Loja.
- [x] Loja sem Estoque recebe 403 nas rotas de Estoque.
- [x] Entitlement suspenso bloqueia novo processamento e preserva histórico.
- [~] Loja suspensa não inicia atendimento, simulação, venda ou alteração de estoque,
      mesmo por URL/API direta; histórico autorizado continua legível.
      (gate estoque+vendas write com flag; cobertura total de simulação/atendimento F2–F4)
- [x] Convite ainda não ativado e acesso revogado não criam sessão na Loja.
- [x] Payload repetido do Control é idempotente.

**Critério de pronto:** a navegação possui somente dois módulos e nenhuma autorização
depende apenas de `loja_slug` ou do papel legado.

---

## Fase 2 — Consolidar Estoque

### Visão geral

Criar um read model determinístico com:

- total disponível, reservado e vendido;
- idade do estoque em faixas;
- veículos sem preço, foto ou campo obrigatório;
- procura por modelo com base em interesses registrados;
- reservas e vendas recentes.

### Veículos

- [ ] Reaproveitar CRUD, fotos, preço, custo, disponibilidade, reserva e venda.
- [ ] Manter Estoque API como fonte de verdade.
- [ ] Integrar publicação no Catálogo como ação/estado do veículo.
- [ ] Abrir interessados no Atendimento, sem criar CRM dentro do Estoque.
- [ ] Aplicar campos sensíveis por cargo; vendedor não recebe custo/margem se essa for
      a política aprovada.
- [ ] Redirecionar rotas antigas somente após equivalência funcional.

### Testes

- [ ] Indicadores têm fixtures e fórmulas explícitas.
- [ ] Sem dados retorna estado vazio, não métricas inventadas.
- [ ] Publicar/despublicar preserva integração atual do Catálogo.
- [ ] Falha de Catálogo não corrompe o veículo.
- [ ] Nenhum caminho chama provedor de IA.

**Critério de pronto:** toda operação atual de estoque e catálogo cabe em Visão geral
ou Veículos, sem IA e sem perda funcional.

---

## Fase 3 — Consolidar Visão geral de Vendas

Criar `SalesOverview` como interface única de leitura, compondo:

- receita, margem, vendas e metas;
- leads e SLA de primeira resposta;
- funil e conversão;
- produtividade;
- pendências acionáveis derivadas dos dados atuais; as Próximas Ações persistentes entram
  somente na Fase 7;
- resumo de investimento, CAC e ROAS recebido do Control;
- alertas de medição em linguagem comercial.

### Tarefas

- [ ] Reaproveitar cálculos existentes de dashboard, financeiro, funil, relatórios,
      metas e painel do vendedor.
- [ ] Separar consulta/agregação de template e rota.
- [ ] Normalizar período, timezone e semântica dos KPIs.
- [ ] Criar cards com estados carregando, vazio, parcial, atualizado e erro.
- [ ] Aplicar a linguagem visual do brand kit em um grid responsivo, com hierarquia clara,
      gráficos acessíveis e destaque para ações — sem tema decorativo genérico de “IA”.
- [ ] Manter componentes visuais reutilizáveis entre Vendas e Estoque sem misturar as
      fórmulas ou os read models de cada módulo.
- [ ] Mostrar origem e resultado; não mostrar OAuth, tokens, Pixel, webhook ou
      diagnóstico técnico.
- [ ] Omitir ou marcar Google como indisponível enquanto o gate Control 4 não estiver
      pronto; nunca renderizar ausência de integração como gasto zero.
- [ ] Manter detalhe de mídia no Control e contrato read-only para a Loja.

### Testes

- [ ] KPIs batem com vendas e funil existentes no mesmo período.
- [ ] ROAS sem investimento aparece como indisponível, nunca infinito.
- [ ] Falha do Control deixa aquisição como parcial sem derrubar Vendas.
- [ ] Dono/gerente e vendedor recebem apenas métricas autorizadas.

**Critério de pronto:** dono entende operação e resultado até venda em uma tela, sem
entrar no painel técnico.

---

## Fase 4 — Atendimento unificado

### Domínio

Criar um `AttendanceWorkspace` que compõe, sem duplicar propriedade:

- lead e conversa do Chatbot;
- atribuição operacional do Portal;
- veículo de interesse do Estoque;
- solicitações e retornos do Motor;
- venda do Portal.

### Tarefas

- [ ] Unificar listas atuais de Leads e Conversas.
- [ ] Criar visão de cliente/negociação com histórico e responsável.
- [ ] Exibir o canal de origem e preservar o canal da conversa.
- [ ] Incorporar handoff, etapa, Simulação Multibanco e confirmação de venda.
- [ ] Manter o Chatbot capaz de solicitar simulação.
- [ ] Definir estados de atendimento e transições explícitas.
- [ ] Decidir e testar política de visibilidade do vendedor antes do cutover.
- [ ] Implementar composer humano de texto por `HumanMessagingPort`, com adapter HTTP
      do Chatbot e adapter em memória nos testes. O Chatbot continua dono da mensagem.
- [ ] Antes de habilitar o composer, fechar permissão, canal da conversa, idempotência,
      dedupe, auditoria, limites e pausa/handoff do bot. Mídia fica fora do primeiro corte.

### Testes

- [ ] Mesmo telefone em lojas diferentes nunca cruza dados.
- [ ] Vendedor fora do escopo recebe 403/404 seguro.
- [ ] Handoff repetido é idempotente.
- [ ] Vendedor autorizado envia texto uma vez pela conversa correta; retry não duplica,
      a mensagem aparece no histórico e o bot permanece pausado conforme a regra.
- [ ] Vendedor sem escopo não envia e não consegue escolher outro canal/loja no payload.
- [ ] Confirmação de venda continua acionando a projeção ao Control.
- [ ] Falha de Chatbot/Motor/Estoque degrada somente o bloco correspondente.

**Critério de pronto:** o vendedor conduz a negociação sem alternar entre páginas
separadas de lead, conversa, simulação e venda.

---

## Fase 5 — Equipe operacional e configurações financeiras

### Equipe

- [ ] Remover da Loja criação de conta, senha estrutural e troca de cargo.
- [ ] Exibir equipe provisionada pelo Control somente onde a operação exige.
- [ ] Manter distribuição, reatribuição, fila e produtividade no Revy Loja.
- [ ] Auditar mudança de responsável por atendimento.
- [ ] Não mostrar números WhatsApp, tokens ou integrações como cadastro de equipe.

### Acessos bancários

- [ ] Manter credenciais de portais bancários no domínio atual do
      Portal/Motor.
- [ ] Colocar a entrada em ação contextual “Configurações financeiras” dentro de
      Vendas, não no menu principal.
- [ ] Autorizar somente dono e gerente.
- [ ] Nunca reapresentar segredo em claro; permitir substituir e testar.
- [ ] Auditar criação, troca, teste e revogação sem registrar o segredo.
- [ ] Confirmar que Admin Revy e gestor de tráfego não recebem esse payload pelo Control.
- [ ] Tratar banco ainda não configurado como pendência operacional de Vendas, sem
      impedir que o Control ative a Loja ou que as demais funções de Vendas operem.

**Critério de pronto:** Control define quem compõe a loja; Loja distribui o trabalho;
somente dono/gerente administram acesso aos bancos.

Esse é o corte mínimo recomendado para o primeiro MVP comercial do Revy Loja.

---

## Fase 6 — Múltiplos canais WhatsApp

**Dependência:** Fase 5 do plano Revy Control concluída.
O Control configura os números, o Chatbot continua dono dos canais e o Revy Loja apenas
opera as conversas autorizadas.

- [ ] Receber `canal_id`, número mascarado e estado nos contratos do Chatbot.
- [ ] Listar e filtrar conversas por canal sem transformar canal em finalidade fixa.
- [ ] Preservar conversa por `(canal_id, telefone)` e lead por `(loja, telefone)`.
- [ ] Responder sempre pelo canal original da conversa.
- [ ] Exibir canal inativo no histórico e bloquear novo envio por ele.
- [ ] Não permitir conectar, transferir ou inativar número pela Loja.
- [ ] Testar dois números, mesmo cliente, duas conversas e um lead.

**Critério de pronto:** usuários operam conversas de vários números sem misturar
mensagens; toda configuração dos números permanece no Control.

---

## Fase 7 — Follow-ups, propostas e Seller AI

### Dados

Adicionar por migration:

- `proximas_acoes`;
- `followups`;
- `propostas`;
- `seller_ai_execucoes`.

### Seller AI

Criar `SellerCopilot` com interface:

- resumir negociação;
- sugerir resposta;
- sugerir próxima ação e prazo;
- listar dados faltantes;
- preparar rascunho de follow-up/proposta.

### Guardrails

- [ ] Contexto sempre limitado à loja e ao atendimento autorizado.
- [ ] Estoque, preço e simulação vêm de ports determinísticos.
- [ ] Sugestão inclui referências internas usadas e avisos de dado ausente.
- [ ] Nenhuma sugestão envia mensagem ou altera negócio automaticamente.
- [ ] Prompt/modelo, latência, custo, ator e aceite/rejeição são auditáveis.
- [ ] PII é minimizada; segredos bancários nunca entram no prompt.
- [ ] Timeout ou falha retorna UI convencional sem bloquear a operação.
- [ ] Testes de prompt não substituem testes determinísticos de autorização.

**Critério de pronto:** Seller AI economiza tempo do vendedor, mas todo efeito
comercial continua explícito, autorizado e auditável.

---

## Fase 8 — Rollout, observabilidade e limpeza

- [ ] Pilotar com uma loja e medir tempo de resposta, uso, conversão e erros.
- [ ] Rodar as suítes dos cinco serviços a cada corte.
- [ ] Validar permissões de dono, gerente e vendedor por rota e API.
- [ ] Validar indisponibilidade isolada de Control, Chatbot, Motor, Estoque e IA.
- [ ] Observar filas/outboxes, dedupe e atraso das projeções.
- [ ] Ativar redirects de rotas antigas gradualmente.
- [ ] Remover menus antigos depois de telemetria provar ausência de uso necessário.
- [ ] Remover escrita estrutural de `Usuario` somente após projeção do Control estável.
- [ ] Atualizar runbooks, ajuda e onboarding da loja.

## Matriz mínima de testes

| Área | Casos obrigatórios |
|---|---|
| Isolamento | loja, pessoa, atendimento, venda e estoque cruzados |
| Cargos | múltiplos cargos, escopo do vendedor e ação dono/gerente |
| Entitlements | Vendas, Estoque, ambos, suspensão e cache |
| Atendimento | atribuição, handoff, canal, simulação e confirmação |
| Financeiro | segredo cifrado, mascaramento, RBAC e auditoria |
| Estoque | fórmulas, CRUD, mídia, estado e catálogo |
| Control | projeção idempotente, indisponibilidade e resultados read-only |
| IA | contexto escopado, grounding, falha segura e nenhuma execução implícita |
| Compatibilidade | 809 testes existentes + contratos n8n |

## Ordem recomendada

1. Fases 0 e 1.
2. Fase 2 em paralelo ao fechamento dos read models da Fase 3.
3. Fase 4 depois de identidade e autorização estáveis.
4. Fase 5 antes de remover Equipe e Financeiras antigas.
5. Fase 6 somente após Multi-WhatsApp no Control/Chatbot.
6. Fase 7 depois que Atendimento tiver dados e ações confiáveis.
7. Fase 8 acompanha todos os cortes e encerra o rollout.

## Definição de pronto

- O Portal passa a se apresentar como Revy Loja.
- Só existem Vendas e Estoque como módulos principais.
- As quatro áreas cobrem as funções atuais sem regressão.
- Estrutura da equipe e integrações técnicas são administradas no Control.
- Operação comercial e acessos bancários continuam na Loja com RBAC correto.
- Chatbot e Simulação Multibanco aparecem dentro do Atendimento.
- Seller AI é opcional, assistivo, auditável e nunca bloqueia a venda.
- Estoque continua determinístico e alimenta o Catálogo.
- Multi-loja, multi-cargo e multi-número respeitam isolamento.
- O baseline de 809 testes permanece verde.
