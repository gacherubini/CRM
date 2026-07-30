# Plano — Evolução do Revy Tráfego para Revy Control

**Status:** ATIVO / CÓDIGO F0–6 + residual F3/F4-HTTP/F5-n8n/F6/F7-UI COMPLETE (Meta, readiness, Google ports+HTTP adapters, multi-WA n8n instance dinâmica, jobs com gate de suspensão, dashboard rico, RBAC sem slug; residual = GCP/token humano, E2E lab, flags F7, worker outbox Google)
**Data:** 2026-07-29
**Spec:** [`docs/superpowers/specs/2026-07-29-revy-control-design.md`](../superpowers/specs/2026-07-29-revy-control-design.md)
**Vocabulário:** [`CONTEXT.md`](../../CONTEXT.md)
**Pesquisa Google:** [`docs/research/2026-07-29-google-ads-revy-control.md`](../research/2026-07-29-google-ads-revy-control.md)

## Objetivo

Transformar o app existente `revy-trafego` no **Revy Control**, preservando Tráfego,
ROI, CAPI, Portal e Catálogo enquanto são adicionados:

- cadastro real e ciclo de vida de lojas;
- Admin Revy global e gestores escopados por loja;
- pessoas, cargos, módulos, contrato e cobrança administrativa;
- prontidão, saúde de integrações e auditoria completa;
- Google Ads com OAuth, métricas, atribuição e devolução de conversões;
- múltiplos números WhatsApp equivalentes por loja;
- arquitetura preparada para Evolution e WhatsApp Cloud API.

Este plano não implementa as funcionalidades internas dos módulos Vendas e Estoque
nem Chatbot, Seller AI e Simulação Multibanco embutidos em Vendas.

## Arquitetura

- O diretório e o processo continuam chamados `revy-trafego` durante a migração.
- A UI passa a usar a marca **Revy Control**; Tráfego vira um módulo interno.
- Novas regras ficam em módulos profundos; rotas HTML/JSON são chamadores finos.
- `app/main.py` fica apenas com montagem, middleware, lifespan e routers.
- Revy Control é fonte de verdade de loja, vínculo, módulo, contrato e auditoria.
- Revy Control é a superfície administrativa e a fonte de política das integrações
  técnicas Meta, Google e WhatsApp.
- Chatbot continua fonte operacional e persistente dos canais WhatsApp, conversas,
  mensagens e leads. O Control administra canais por contrato HTTP e mantém somente
  projeção de estado, saúde e prontidão.
- Revy Loja continua fonte de vendas e operação; credenciais bancárias permanecem no
  domínio Vendas/Motor e não são projetadas ao Control.
- Bancos não compartilham foreign keys; integração entre processos é HTTP/evento.
- Migrações seguem expand/contract; campos e contratos atuais permanecem durante o cutover.

## Restrições globais

- Não criar entidade Organização, Rede ou Agência.
- Não permitir loja manual por slug como forma de autorização.
- Toda consulta ou escrita de gestor deve validar vínculo ativo no backend.
- Admin Revy tem acesso total permanente e auditado.
- Uma loja tem no máximo um Gestor Responsável ativo e vários colaboradores.
- Colaborador não desconecta integrações nem números WhatsApp.
- Não apagar lojas, canais, contratos, módulos contratados ou histórico.
- Um número WhatsApp nunca muda de loja.
- Números não têm finalidade nem vendedor fixo neste plano.
- Não operar anúncios Meta/Google dentro da Revy.
- Tratar campanha exibida na Revy como Registro de Campanha para atribuição e medição,
  nunca como o anúncio externo em si.
- Não implementar serviços de criação, alteração ou pausa de campanha Google.
- Não administrar acessos bancários ou receber seus segredos no Control.
- Não processar pagamentos neste plano.
- Não implementar Cloud API agora; somente preservar o seam para o adapter futuro.
- TDD por interface: teste falha, implementação mínima, teste passa.

## Fases e gates

| Fase | Entrega | Gate para avançar |
|---:|---|---|
| 0 | Baseline e inventário | dados e rollback conhecidos |
| 1 | Loja de primeira classe + RBAC | nenhum acesso cruzado entre gestores |
| 2 | Pessoas, cargos, módulos e contrato | loja configurável sem editar banco/env |
| 3 | Integrações, prontidão e auditoria | ativação bloqueada por requisito inválido |
| 4 | Google Ads | leitura e conversões sem mutação de campanhas |
| 5 | Multi-WhatsApp | dois números na mesma loja sem mistura |
| 6 | Dashboards e rebrand | Admin e gestor veem painéis corretos |
| 7 | Rollout e limpeza | lab estável e fallbacks legados removíveis |

---

## Fase 0 — Baseline, contratos e segurança de migração

### Objetivo

Conhecer o estado real antes de criar tabelas ou alterar autorização.

**Evidência canônica:** [`2026-07-29-revy-control-fase0-baseline-inventario.md`](../research/2026-07-29-revy-control-fase0-baseline-inventario.md).

### Tarefas

- [x] Registrar baseline das suítes Revy Tráfego, Portal, Chatbot, Estoque e Catálogo
      (682 testes no commit auditado; comandos e resultados na evidência canônica).
- [x] Inventariar no código todos os `loja_slug`/`loja_id`, shims e nomes de env
      presentes em mídia, vendas, Portal, Chatbot, Motor, Estoque e Catálogo.
- [ ] Reconciliar os valores reais do lab em um mapa
      `origem → slug bruto → slug normalizado → loja_id`.
- [ ] Detectar colisões de slug, e-mail e telefone antes do backfill.
- [x] Inventariar schemas, nomes de env e pontos de envio direto da Evolution sem
      expor tokens.
- [ ] Confirmar no lab as instâncias Evolution e números atuais mascarados.
- [ ] Capturar fixtures sanitizadas de webhook inbound, `fromMe`, mídia e CTWA.
- [ ] Confirmar backup/snapshot e ensaio de restauração dos bancos afetados.
- [x] Definir matriz de suspensão por serviço e módulo: leitura histórica, novas escritas,
      webhooks inbound, automações, jobs e visibilidade do Catálogo Público
      ([ADR 0001](../adr/0001-suspensao-distribuida.md)).
- [x] Criar flag default off `REVY_CONTROL_ENABLED` para proteger as superfícies
      administrativas do Control.
- [x] Criar flag default off `REVY_CONTROL_RBAC_ENABLED` para o cutover do escopo por
      vínculo após o gate de isolamento da Fase 1.
- [x] Criar flag default off `GOOGLE_ADS_SYNC_ENABLED`.
- [x] Criar flag default off `GOOGLE_CONVERSIONS_ENABLED`.
- [x] Criar flag default off `MULTI_WHATSAPP_ENABLED`.
- [x] Criar flag default off `REVY_CONTROL_DASHBOARD_ENABLED`.
- [x] Documentar contratos HTTP/evento atuais que não podem quebrar.

### Saída

- Relatório de inventário e mapeamento de IDs/slugs.
- Fixtures e baseline de testes.
- Rollback conhecido antes da primeira migration.

---

## Fase 1 — Cadastro de Lojas e Controle de Acesso

### Módulos

Criar em `revy-trafego/app/control/`:

- `stores.py`: cadastro, consulta e transição de estado;
- `access.py`: autorização, vínculos e escopo visível;
- `audit.py`: trilha administrativa genérica;
- `types.py`: comandos/resultados estáveis das interfaces.

Criar routers finos em `revy-trafego/app/web/` e reduzir gradualmente `app/main.py`.

### Dados

Migration aditiva após o head atual:

- `lojas`;
- `vinculos_trafego`;
- `auditoria_eventos`;
- referência opcional `loja_id` nas tabelas de mídia existentes.

Backfill:

1. criar uma Loja para cada slug confirmado no inventário;
2. preservar o slug como identificador público/compatível;
3. mapear configs, campanhas e vendas projetadas para `loja_id`;
4. importar seeds de env como `rascunho`, nunca como loja ativa automaticamente.

### Regras

- Admin lista e opera todas as lojas.
- Gestor lista somente lojas com vínculo ativo.
- Responsável único por loja; colaboradores ilimitados.
- Troca de responsável preserva configuração e histórico.
- Sessão pode selecionar somente loja retornada por `AccessControl`.
- Campo manual de slug deixa de existir na UI.

> **Evidência local:** implementação protegida por `REVY_CONTROL_ENABLED=0` e
> `REVY_CONTROL_RBAC_ENABLED=0` nos commits `377e2f1`, `c10a637`, `f603a69`,
> `13d7400`, `93ffd16`, `0fc9850`, `335aa8c`, `4c72e22`; suíte Revy com **125 testes
> passando**. Não houve migration nem rollout no lab. O inventário e o restore
> drill pendentes da Fase 0 bloqueiam a ativação remota.

### Testes obrigatórios

- [x] Gestor A não lista, abre nem altera Loja B.
- [x] Digitar URL/slug de Loja B retorna 403/404 seguro.
- [x] Admin acessa qualquer loja e suas ações são auditadas.
- [x] Segunda atribuição de responsável ativo falha de forma explícita.
- [x] Remover vínculo encerra acesso na próxima requisição.
- [x] Backfill é idempotente.
- [x] Rotas e APIs atuais de ROI/CAPI continuam passando.

### Critério de pronto

Não existe mais autorização baseada apenas em conhecer ou digitar `loja_slug`.

**Estado:** cobertura local concluída; Fase 1 ainda não está pronta em produção.
O critério acima precisa ser validado no lab depois dos gates pendentes da Fase 0,
da migration/backfill e da ativação controlada das flags.

---

## Fase 2 — Pessoas, cargos, módulos, contrato e cobrança

### Dados

Adicionar:

- `pessoas`: identidade canônica por e-mail normalizado;
- `acessos_control`: autenticação de Admin e gestor;
- `cargos_loja`: dono, gerente e vendedor, permitindo múltiplos cargos;
- `modulos_revy`;
- `loja_modulos`;
- `contratos_loja`.

### Migração de identidade

- [x] Backfill de `GestorRevy` para `pessoas` + `acessos_control` sem invalidar sessões.
- [x] Importar usuários atuais do Portal como pessoas/cargos, registrando conflitos
      (`POST /control/v1/imports/portal-usuarios`, push-style, origem=portal).
- [x] Manter `portal-gestao.usuarios` como projeção/legado até o plano do Revy Loja
      (import não corta auth nem apaga usuários do Portal).
- [ ] Definir contrato versionado de provisionamento de pessoa, cargo e entitlement.
- [x] Definir ciclo de acesso: convite de uso único com expiração, criação da própria
      senha, recuperação, desativação e revogação de sessões. Admin nunca lê senha.
- [ ] Projetar estado da Loja e dos Módulos Contratados para Revy Loja, Chatbot, Motor,
      Estoque e Catálogo por entrega idempotente; nenhum serviço confia só no menu.
      **Local:** enqueue para chatbot/estoque/portal/motor/catalogo + retry failed +
      worker opt-in; todos os destinos consomem projeção; falta rollout lab.
- [ ] Não cortar autenticação do Portal neste plano.

### Interface administrativa

- [x] Admin cria/edita loja em estado Rascunho pela API.
- [x] Admin cadastra pessoa uma vez e atribui vários cargos/lojas.
- [ ] Permitir que a mesma pessoa tenha acesso ao Control e cargo na Loja sem herdar
      permissões de uma superfície na outra.
- [x] Admin escolhe Vendas, Estoque ou ambos para a loja pela API e UI.
- [x] Admin registra valor, vigência, vencimento e situação da cobrança pela API e UI.
- [x] Exigir pelo menos um Dono da Loja com acesso ativável antes de marcar a loja pronta.
- [x] Suspender/reativar módulo preserva estado, versão, histórico e auditoria locais.
- [ ] Aplicar o bloqueio de novos processamentos nos serviços de destino.
- [x] Cobrança atrasada gera alerta, mas não suspende automaticamente.

### Testes obrigatórios

- [x] Convite expirado/usado, reset e usuário desativado falham de forma segura.
- [x] Admin atribui cargos sem criar, conhecer ou reapresentar a senha da pessoa.
- [x] Múltiplos cargos ativos somam permissões somente dentro da loja selecionada;
      nenhum cargo ou acesso ao Control vaza para outra loja/superfície
      (`control/permissions.py` + testes de isolamento).
- [x] Projeção repetida ou fora de ordem não reativa loja/módulo suspenso
      (apply monotônico no Control + Chatbot).
- [ ] Loja/Módulo suspenso bloqueia novo processamento nos serviços de destino e mantém
      leitura do histórico conforme o cargo autorizado.
      **Local:** Chatbot, Estoque, Portal, Motor (nova simulação) e Catálogo (vitrine
      404/HIDE, fail-open sem projeção) aplicam gates; `despublicar` Estoque e cancel
      Motor permanecem abertos (ações redutoras).

> **Evidência local — Fase 2 parcial (pós-configuração comercial):** Pessoas/Cargos,
> convite/ativação, recuperação, lifecycle e versão de sessão (`fda42fb` a `17a0963`),
> portfólio/contrato/UI (`08fd64e` a `fa83257`) e versão/reativação da Loja
> (`d218da3`, `f55677a`) permanecem. O corte seguinte fecha identidade canônica e
> prontidão:
>
> - login e `Actor` via `AcessoControl` sem exigir `GestorRevy` (convite deixa de
>   dual-escrever gestor legado; recuperação/reativação só sincronizam o legado se
>   existir);
> - snapshot de provisionamento versionado com loja/módulos **e** pessoas/cargos ativos;
> - transição a `pronta` exige Dono ativo **com** `AcessoControl` em `pendente` ou
>   `ativo` (`activatable_owner`); o último Dono ativo continua protegido em estados
>   operacionais.
>
> O Alembic head local do Control é `0009_revy_control_provisioning_outbox`; o
> Chatbot tem `0014_loja_operacional_projecao`. Flags de delivery e Control seguem
> default off; sem migration/rollout no lab.
>
> Entrega local da projeção operacional está fechada no código: fan-out completo,
> import Portal, isolamento Control×Loja e gates nos cinco destinos. Residual de
> Fase 2 = rollout lab e gates finos (WA, confirmar venda).

Pendências para concluir a Fase 2:

- ~~expandir gates finos (WA / confirmar venda)~~ **feito no código**
  (`feat(chatbot): captura passiva…`, `feat(portal): bloqueia confirmar venda…`);
- rollout lab residual: recriar Evolution/n8n se precisar de WA E2E; smoke reativar loja;
  ver [runbook](2026-07-29-runbook-rollout-lab-provisionamento.md).

### Critério de pronto

Admin configura a estrutura comercial da loja pelo Revy Control sem editar env ou DB.
A aplicação efetiva desses cargos dentro de Vendas e Estoque está detalhada no
[plano do Revy Loja](2026-07-29-plano-revy-loja.md).

---

## Fase 3 — Central de Integrações, prontidão e auditoria

### Módulos

- `integrations.py`: catálogo, conexão, desconexão, saúde e requisitos;
- `readiness.py`: calcula por que a loja está ou não pronta;
- adapters para Meta/Google e ports para sistemas Revy remotos.

As configurações atuais de Pixel, CAPI e Meta Ads não são reescritas. Elas passam a
ser chamadas pela interface da Central de Integrações.

### Regras

- Gestor Responsável e Admin conectam/desconectam integrações.
- Colaborador acompanha tráfego, métricas e alertas, mas não desconecta integrações.
- Revy não cria conta Meta/Google nem administra login, 2FA ou concessão de acesso.
- Token é cifrado e nunca reapresentado ao navegador.
- Cada Módulo Contratado declara requisitos obrigatórios e alertas.
- Loja vira `pronta` somente quando todos os requisitos obrigatórios passam.
- Admin ativa loja pronta; aceite de alerta não crítico exige motivo auditado.
- Credencial bancária não é requisito de prontidão do Control. A disponibilidade da
  Simulação Multibanco é mostrada e resolvida dentro de Vendas no Revy Loja.

### Testes obrigatórios

- [x] Colaborador recebe 403 ao desconectar integração
      (`test_control_integrations.py::test_colaborador_nao_pode_desconectar_pixel`).
- [x] Erro obrigatório impede estado Pronta e Ativa
      (`StoreReadinessBlocked` em `CONFIGURING→READY` e `*→ACTIVE`;
      `test_control_readiness.py`).
- [x] Alerta aceito não bloqueia e gera auditoria
      (`readiness_alert_acceptances` + `readiness.alert.accepted`;
      aceite não inventa `ready=True` se required falhar).
- [x] Suspensão interrompe jobs da loja sem apagar filas/histórico
      (Meta spend skip + CAPI park pending + Google conversion outbox skip;
      `store_blocks_traffic_jobs` em `stores.py`).
- [x] Falha externa é sanitizada e não vaza segredo
      (token nunca no JSON de integrações; auditoria sem ciphertext cru).
- [x] Readiness é determinístico e testado pela interface
      (`StoreReadiness` + `GET /control/v1/lojas/{id}/prontidao` +
      `POST .../prontidao/alertas/{code}/aceitar`; Central Meta lean).

### Critério de pronto

O dashboard consegue explicar exatamente por que cada loja está configurando, pronta,
ativa ou com erro.

**Estado código (lean):** Meta Pixel/CAPI/Ads na Central; readiness determinístico;
aceite de alerta durable + auditado; ativação bloqueada sem required. Residual lab =
flags + smoke; jobs de suspensão finos ainda abertos.

---

## Fase 4 — Google Ads: conexão, leitura e conversões

Esta fase substitui a Fase G residual do plano de conversões de 2026-07-21. A nova
integração pertence ao Control e segue a arquitetura oficial vigente em 2026:

- **Google Ads API:** OAuth, contas, hierarquia, ações, campanhas e métricas;
- **Data Manager API:** conversões offline e enhanced conversions for leads.

Não usar `ConversionUploadService.UploadClickConversions` como base de uma integração
nova e não implementar nenhum método de mutação de campanhas.

### Fase 4A — Fundação e conexão

- [ ] Criar projeto Google Cloud de teste e produção, consent screen, domínios,
      política, termos e redirect URIs HTTPS. (**humano / GCP**)
- [ ] Solicitar developer token da Google Ads API pelo manager account da Revy.
      (**humano**)
- [ ] Habilitar Google Ads API e Data Manager API. (**humano / GCP**)
- [x] Criar `GoogleAdsReadPort`, `GoogleDataManagerPort` e adapters falsos para testes
      + HTTP reais em `google_ads_http.py` (`build_google_ads_ports`).
- [x] Implementar OAuth multiusuário no backend com `state`, acesso offline e escopos
      `adwords` e `datamanager`.
- [x] Cifrar refresh token; client secret e developer token via env/secret manager.
- [x] Descobrir contas diretas e hierarquia, distinguindo `customer_id` de
      `login_customer_id`; impedir seleção de manager como conta anunciante.
- [x] Tratar conexão como `conectado`, `atenção`, `expirado`, `revogado` ou `erro`.

Dados:

- `google_ads_connections`;
- `google_ads_accounts`;
- auditoria de conexão, troca, reconexão e revogação.

### Fase 4B — Métricas e dashboard de aquisição

- [ ] Sincronizar com GAQL conta, moeda, fuso, auto-tagging, ações e métricas diárias.
- [ ] Persistir `google_ads_campaign_daily` por conta/campanha/data.
- [ ] Fazer carga inicial, incremental e reprocessamento de janela recente.
- [ ] Derivar CTR, CPC, CPL, custo por venda e ROAS com money/`cost_micros` corretos.
- [ ] Separar no dashboard métricas Google de eventos Revy e suas datas diferentes.
- [ ] Aplicar throttling, backoff e seleção mínima de campos.
- [ ] Expor à Revy Loja somente o resumo comercial read-only.

### Fase 4C — Captura e contrato comercial

- [ ] Preservar `gclid`, `gbraid` e `wbraid` como valores opacos no Catálogo,
      landing pages, redirects, sessão, Chatbot e lead.
- [ ] Manter UTMs, URL de entrada e referrer para explicação interna.
- [ ] Estender `PurchaseConversion`, `revy_trafego_outbox.py` e
      `VendaConfirmadaBody`: o `gclid` já existe no evento interno, mas hoje não
      atravessa Portal → Control; adicionar também `gbraid` e `wbraid`.
- [ ] Versionar o contrato com consentimento, fonte, timestamp, valor/moeda e
      identificadores first-party permitidos.
- [ ] Testar Catálogo/landing → WhatsApp/formulário → lead → venda → Control.

### Fase 4D — Ações e devolução de conversões

- [ ] Listar ações existentes e permitir mapear evento Revy → ação; a Revy não cria
      nem define ação primária/secundária.
- [ ] Validar a conta proprietária da ação, termos de dados e enhanced conversions.
- [ ] Criar `google_ads_conversion_bindings`, `google_ads_conversion_outbox` e
      `google_ads_upload_attempts`.
- [ ] Gerar `transaction_id` determinístico:
      `revy:{loja_id}:{tipo_evento}:{id_evento_de_dominio}`.
- [ ] Normalizar e hashear email/telefone somente quando consentimento/base aplicável
      permitir; segredos bancários nunca entram no payload.
- [ ] Enviar lotes por loja/ação/janela com `IngestEvents`.
- [ ] Guardar `request_id` e consultar `RetrieveRequestStatus` até `SUCCESS`,
      `PARTIAL_SUCCESS` ou `FAILURE`, com backoff, reconciliação e dead-letter.
- [ ] Falha Google nunca reverte confirmação de venda nem bloqueia o Revy Loja.

### Saúde e testes obrigatórios

- [ ] OAuth `state` inválido é rejeitado; token nunca volta ao browser/log.
- [ ] Gestor não acessa conta Google de loja sem vínculo.
- [ ] Nenhum módulo Google oferece ou chama método `Mutate`.
- [ ] `customer_id`/`login_customer_id` e conta proprietária da ação são validados.
- [ ] Upsert diário é idempotente e respeita moeda/fuso.
- [ ] Redirects preservam os três click IDs exatamente.
- [ ] Retry reutiliza o mesmo `transaction_id` e não duplica conversão.
- [ ] Evento sem consentimento não envia user data enhanced.
- [ ] Fast-fail, diagnóstico assíncrono e sucesso parcial ficam rastreáveis.
- [ ] Revogação OAuth gera alerta e não afeta Meta, Portal ou venda.

### Critério de pronto

Uma loja conecta a conta permitida, o Control sincroniza investimento e métricas,
recebe a jornada comercial e devolve conversões idempotentes com diagnóstico. Nenhum
caminho cria, edita, pausa ou otimiza campanha.

---

## Fase 5 — Múltiplos números WhatsApp por loja

Esta fase substitui o plano de 2026-07-22 que vinculava canais a vendedor/campanha.
A configuração aparece no Revy Control, mas o Chatbot permanece dono dos registros e
da operação dos canais; o Control chama sua interface e projeta saúde/prontidão.

### Chatbot API — dados

Adicionar por expand/contract:

- `whatsapp_canais`: identidade do número e vínculo imutável à loja;
- `whatsapp_conexoes`: provedor, referência externa, estado e histórico;
- `canal_id` em conversas e mensagens;
- índices/uniques por canal.

Backfill do `Loja.evolution_instance` + `Loja.whatsapp` como um canal legado da mesma
loja. Não migrar `NumeroAutorizado`: ele representa pessoa autorizada a operar estoque,
não um canal de atendimento da loja.

### Interface de canais

No Chatbot, criar port `WhatsAppProvider` e módulo de canais com interface:

- cadastrar número;
- conectar/reconectar;
- consultar estado;
- desconectar;
- inativar.

Adapters:

- `EvolutionAdapter` em produção;
- adapter em memória nos testes;
- `CloudApiAdapter` apenas em trabalho futuro.

No Revy Control, criar port `WhatsAppChannelsPort`, adapter HTTP para o Chatbot e
adapter em memória para testes. O navegador nunca chama Evolution diretamente.

### Regras

- Vários números equivalentes por loja, sem finalidade fixa.
- Número globalmente único e nunca transferível.
- Estados: pendente, conectado, desconectado e inativo.
- Apenas uma conexão/provedor ativo por número.
- Desconectar permite reconectar na mesma loja; inativar preserva histórico.
- Admin e Gestor Responsável alteram; colaborador apenas consulta.
- QR e credenciais usam `Cache-Control: no-store` e não entram em logs.

### Conversas, mensagens e leads

- Conversa única por `(canal_id, telefone_cliente)`.
- Mensagem deduplicada por `(canal_id, provider_message_id)`.
- Lead continua único por `(loja_id, telefone_cliente)`.
- Evento inbound resolve a loja pela instância/canal conhecido; instância desconhecida
  é rejeitada e gera alerta.
- Resposta sempre usa o canal da conversa.

### n8n

- [x] Remover dependência de `__INSTANCE__` fixa no workflow de produção
      (`n8n/workflow-ai-nao-salvos.json` + `validate_workflow.py`;
      `prepare-workflow.ps1` não grava instance).
- [x] Resolver dinamicamente `body.instance` no Chatbot
      (`resolver_loja_e_canal_por_instancia` / `resolve_canal_for_instance`;
      PATCH `/estado` aceita `instance` para handoff por canal).
- [x] Manter um workflow, não uma cópia por número (doc em
      `deploy/fly/3vm/README.md` + `n8n/GUIA-WORKFLOW.md`).
- [x] Registrar `fromMe` e pausar apenas a conversa correspondente
      (testes multi-WA: fromMe + PATCH estado com instance).
- [ ] Testar texto, áudio, foto, CTWA, contato salvo, grupo e instância desconhecida
      no lab (código/unitário coberto; E2E Evolution pendente).

### Critério de pronto

Uma loja opera dois números simultaneamente; mensagens, dedupe e respostas usam o canal
correto; o mesmo cliente pode ter duas conversas e um único lead da loja.

---

## Fase 6 — Dashboards e marca Revy Control

### Admin

- [x] Cards: lojas ativas, configurando, suspensas e com erro
      (`DashboardControl.overview` + `GET /control/v1/dashboard` + UI
      `/app/control/dashboard`).
- [x] Onboardings e requisitos pendentes (`pending_readiness` com failing codes).
- [x] Saúde de integrações por loja (pixel/meta_ads/google_status/whatsapp stub).
- [x] Módulos contratados e falhas de integração (detalhe rico além do stub).
- [x] Gestor Responsável por loja no card do dashboard.
- [x] Alterações recentes (trilha de auditoria no painel).

Usuários e números ficam no detalhe da loja, não como cards do dashboard.

**Estado código (lean):** overview com contagens + lista de pendências + health stubs;
isolamento gestor coberto por testes. Residual visual = detalhe acionável completo e
métricas Meta/Google de aquisição (dependem F4B).

### Linguagem visual

- Grid responsivo, hierarquia clara, contraste acessível e estados carregando, vazio,
  parcial, atualizado e erro.
- Cards abrem o detalhe acionável da loja/integração; o painel não exibe apenas números.
- Componentes visuais podem ser compartilhados com Revy Loja, mas métricas, permissões
  e read models permanecem separados.
- Seguir o brand kit e evitar visual decorativo genérico de “IA”.

### Gestor

- Somente lojas atribuídas.
- Investimento Meta/Google, leads, CPL, contato, agendamento, venda e ROAS.
- Origem/campanha, funil, alertas e saúde das integrações.
- Sem acesso às conversas operacionais dos vendedores, salvo diagnóstico já autorizado.

### Navegação

- Rebrand visual para Revy Control.
- Áreas: Visão geral, Lojas, Módulos, Tráfego, Integrações e Auditoria.
- URLs antigas de Tráfego preservadas ou redirecionadas durante o cutover.

### Critério de pronto

Admin acompanha saúde do ecossistema; gestor acompanha aquisição e resultado apenas de
suas lojas; dono, gerente e vendedor continuam fora do Control.

---

## Fase 7 — Rollout, observabilidade e limpeza

- [ ] Rodar todas as suítes antes e depois de cada migration.
- [ ] Smoke no lab: login, RBAC, loja, onboarding, Meta, Google, ROI, CAPI, Portal e Catálogo.
- [ ] Piloto com uma loja e um número legado; depois dois números na mesma loja.
- [ ] Observar filas, erros, duplicidade, uso de memória e estabilidade Evolution.
- [ ] Validar suspensão/reativação e reconexão de número.
- [ ] Validar restauração de backup com tabelas novas.
- [ ] Ativar flags gradualmente e manter rollback somente por flag/código compatível.
- [x] Remover seletor manual na UI/API quando `REVY_CONTROL_RBAC_ENABLED=1`
      (`home.html` sem `loja_slug_manual`; POST só `loja_id` + `select_store`;
      legado por slug permanece com flag off). Residual lab: ativar flag após backfill.
- [ ] Remover campos legados de uma instância por loja apenas em release posterior.
- [x] Atualizar README operacional e runbooks de deploy
      (checklist de flags/smoke Control no
      [runbook de provisionamento](2026-07-29-runbook-rollout-lab-provisionamento.md);
      **sem deploy lab neste corte**).

**Estado:** docs/checklist de flags e smoke endpoints do Control atualizados no
código; execução no lab permanece pendente (F7 operacional).

## Matriz mínima de testes

| Área | Casos obrigatórios |
|---|---|
| Isolamento | gestor cruzando loja, slug manual, URL direta, API interna |
| Cargos | múltiplos cargos, responsável único, colaborador sem desconexão |
| Loja | transições válidas/inválidas, suspensão e preservação histórica |
| Módulos | entitlement, suspensão individual e requisitos |
| Integrações | segredo, timeout, erro externo, prontidão e auditoria |
| Google | OAuth, hierarquia, GAQL, click IDs, consentimento, outbox e diagnóstico |
| WhatsApp | dois canais, dedupe por canal, resposta pelo canal correto, inativação |
| Compatibilidade | ROI, Pixel, CAPI, venda projetada, Portal e Catálogo |
| Migração | backfill idempotente, rollback por flag, restore |

## Ordem de implementação recomendada

1. Fase 0 inteira.
2. Fase 1 inteira antes de qualquer dashboard novo.
3. Fases 2 e 3.
4. Fases 4 e 5 após RBAC, lojas e Central de Integrações estarem estáveis. Elas são
   independentes entre si e podem ser priorizadas em qualquer ordem ou em paralelo.
5. Fase 6 sobre dados reais das fases anteriores.
6. Fase 7 em cada corte e no encerramento.

Não começar pelo frontend bonito: o dashboard depende de Loja, vínculo, módulos,
integrações e saúde confiáveis.

## Definição de pronto

- Admin cria, configura, ativa, suspende e encerra lojas pelo painel.
- Gestor acessa somente lojas atribuídas; Admin acessa todas.
- Pessoas acumulam cargos e lojas sem existir Organização.
- Módulos, contrato e cobrança são independentes por loja.
- Readiness explica bloqueios e impede ativação inválida.
- Google Ads sincroniza métricas e recebe conversões pela Data Manager API sem
  mutação de campanha.
- Loja opera múltiplos números equivalentes sem transferência nem perda de histórico.
- Evolution fica atrás de interface substituível e Cloud API pode ser adicionada depois.
- Dashboards refletem saúde operacional e resultado comercial.
- Acessos bancários continuam exclusivos do Revy Loja e nunca entram no Control.
- A operação existente de tráfego, Portal, Catálogo, ROI e CAPI permanece funcional.
