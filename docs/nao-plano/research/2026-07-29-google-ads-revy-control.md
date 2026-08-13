# Google Ads no Revy Control

Data da pesquisa: 29 de julho de 2026

Escopo: conexão, leitura, mensuração, atribuição, dashboards, saúde, auditoria e devolução de conversões.
Fora do escopo: criar, editar, ativar, pausar ou otimizar campanhas.

## Conclusão executiva

A implementação correta usa duas APIs, com responsabilidades diferentes:

1. **Google Ads API** para OAuth, descoberta das contas acessíveis, leitura de
   campanhas, métricas, ações de conversão e configurações de mensuração.
2. **Data Manager API** para enviar conversões offline e enhanced conversions for
   leads.

O `ConversionUploadService.UploadClickConversions` da Google Ads API não deve ser a
base de uma integração nova. Desde 15 de junho de 2026, tokens sem uso anterior
desse fluxo ficam bloqueados e o próprio Google orienta novas integrações a usar a
Data Manager API. A Data Manager API também não requer developer token; o token
continua necessário para as leituras feitas na Google Ads API
([mudança oficial](https://developers.google.com/google-ads/api/docs/deprecations),
[comparação e migração](https://developers.google.com/data-manager/api/devguides/events/google-ads/offline/upgrade)).

```text
Google Ads
    │
    ├── Google Ads API ──► contas, campanhas e métricas ──► Revy Control
    │
    └◄─ Data Manager API ◄── conversões da Revy Loja
                                  │
                   lead → simulação → proposta → venda
```

Essa fronteira mantém a Revy como infraestrutura de inteligência comercial: ela
mede aquisição e devolve resultados comerciais ao Google, sem assumir a operação
de tráfego ou alterar campanhas.

## 1. Conta técnica e aprovação do Google

### Developer token

A Revy precisa de um **Google Ads manager account** para solicitar seu developer
token no API Center. Em geral, uma empresa usa um único token. O token identifica
a aplicação e deve ser enviado em todas as chamadas à Google Ads API
([documentação do developer token](https://developers.google.com/google-ads/api/docs/api-policy/developer-token)).

Os níveis atuais têm impactos diferentes:

- Test Account: somente contas de teste.
- Explorer: produção com limite reduzido; é suficiente para começar a integração
  de leitura.
- Basic: produção com limite maior.
- Standard: produção sem limite diário de operações, ainda sujeito aos demais
  limites da API.

Os valores de cota e o processo de aprovação podem mudar e devem ser conferidos
antes do lançamento
([níveis e usos permitidos](https://developers.google.com/google-ads/api/docs/api-policy/access-levels)).
O pedido deve descrever com precisão que a Revy faz reporting, mensuração e
devolução de conversões, mas não gerencia campanhas.

### Projeto Google Cloud

Usar um projeto Google Cloud de produção, separado do projeto de testes, contendo:

- OAuth consent screen e identidade pública da Revy;
- cliente OAuth do tipo Web Application;
- Google Ads API habilitada;
- Data Manager API habilitada;
- redirect URIs HTTPS do backend da Revy;
- página inicial, política de privacidade e termos em domínio verificado.

Apps de produção que usam escopos sensíveis precisam passar pela verificação OAuth.
O Google também exige domínios próprios/verificados e redirect URIs seguros
([preparação e conformidade OAuth](https://developers.google.com/identity/protocols/oauth2/production-readiness/policy-compliance)).

## 2. OAuth e conexão de cada loja

### Fluxo recomendado

O Revy Control é uma aplicação multiusuário. Portanto, deve usar o fluxo OAuth de
**multi-user authentication** no backend:

1. gestor autorizado da loja clica em “Conectar Google Ads”;
2. a Revy gera um `state` único e não previsível;
3. o navegador é redirecionado à tela oficial do Google;
4. o callback valida o `state` e troca o authorization code por tokens;
5. a Revy solicita acesso offline e guarda o refresh token criptografado;
6. a Revy lista as contas que aquele usuário pode acessar;
7. o gestor escolhe qual conta cliente pertence à loja;
8. a Revy valida a conta e inicia a primeira sincronização.

O escopo da Google Ads API é:

```text
https://www.googleapis.com/auth/adwords
```

Para a Data Manager API:

```text
https://www.googleapis.com/auth/datamanager
```

As mesmas credenciais podem receber os dois escopos. O acesso offline é necessário
para sincronizações e uploads sem o usuário presente
([OAuth multiusuário da Google Ads API](https://developers.google.com/google-ads/api/docs/oauth/multi-user-authentication),
[acesso à Data Manager API](https://developers.google.com/data-manager/api/devguides/quickstart/set-up-access),
[OAuth para aplicações web](https://developers.google.com/identity/protocols/oauth2/web-server)).

Não existe um escopo somente leitura mais estreito documentado para a Google Ads
API. Por isso, a Revy deve impor sua fronteira de leitura no próprio produto:

- não implementar nem expor serviços `Mutate`;
- credencial técnica acessível somente ao backend;
- autorização interna proibindo qualquer comando de campanha;
- testes que rejeitem operações de criação, edição e pausa;
- auditoria de todos os serviços e métodos Google chamados.

### Segurança dos tokens

Client secret, developer token e refresh tokens devem ficar em secret manager ou
equivalente, nunca no repositório. Tokens de usuário não devem trafegar em texto
plano e precisam ser criptografados em repouso. A desconexão deve revogar o acesso
quando possível e apagar definitivamente os tokens armazenados. Refresh tokens
podem ser revogados ou expirar a qualquer momento
([gestão oficial de credenciais](https://developers.google.com/google-ads/api/docs/oauth/credential-management)).

O callback OAuth deve validar `state` contra CSRF, e a Revy deve tratar revogação e
expiração como estados normais da conexão
([boas práticas OAuth](https://developers.google.com/identity/protocols/oauth2/resources/best-practices)).
Usuários do fluxo OAuth da Google Ads API precisam de verificação em duas etapas
para gerar novos refresh tokens
([requisito de segurança](https://developers.google.com/google-ads/api/docs/oauth/security-requirements)).

## 3. Customer ID, manager account e descoberta de contas

Há três identificadores que não podem ser confundidos:

- **developer token account:** manager account da Revy onde o token foi obtido;
- **login customer ID:** conta manager pela qual o usuário autenticado acessa a
  hierarquia, quando houver;
- **client customer ID:** conta anunciante cujas campanhas e métricas serão lidas.

O customer ID tem dez dígitos e deve ser enviado sem hífens
([conceitos iniciais](https://developers.google.com/google-ads/api/docs/get-started/make-first-call)).
Quando a autorização passa por uma conta manager, a Google Ads API exige o header
`login-customer-id`. Quando o usuário tem acesso direto à conta anunciante, esse
header não é necessário
([headers de autorização](https://developers.google.com/google-ads/api/rest/auth)).

Descoberta:

1. chamar `CustomerService.ListAccessibleCustomers`;
2. essa chamada retorna somente contas às quais o usuário OAuth tem acesso direto;
3. para cada manager account, consultar `customer_client` via GAQL e percorrer a
   hierarquia;
4. exibir contas anunciantes selecionáveis e impedir a escolha acidental de uma
   manager account como conta de campanhas.

O comportamento de `ListAccessibleCustomers` e a consulta recursiva da hierarquia
estão documentados em
[listar contas acessíveis](https://developers.google.com/google-ads/api/docs/account-management/listing-accounts)
e
[obter hierarquia](https://developers.google.com/google-ads/api/docs/account-management/get-account-hierarchy).

Uma loja pode selecionar mais de uma conta Google Ads se isso existir no negócio,
mas cada vínculo precisa registrar explicitamente:

- `customer_id`;
- `login_customer_id`, quando aplicável;
- nome, moeda, fuso e indicador de manager account;
- usuário/conexão OAuth que concedeu acesso;
- data da última validação e da última sincronização;
- estado: conectado, atenção, expirado, revogado ou erro.

## 4. Sincronização somente leitura

### Serviços e recursos

Usar:

- `CustomerService.ListAccessibleCustomers` para a entrada;
- `GoogleAdsService.Search` ou `SearchStream` para GAQL;
- `customer_client` para hierarquia;
- `customer` para moeda, fuso, auto-tagging e configuração de conversões;
- `campaign` para campanhas e métricas;
- `conversion_action` para descobrir as ações já criadas pelo cliente;
- opcionalmente `click_view` para enriquecer GCLIDs recentes.

GAQL consulta recursos, segmentos e métricas pelo mesmo serviço
([visão geral do GAQL](https://developers.google.com/google-ads/api/docs/query/overview)).
`Search` pagina em blocos fixos; `SearchStream` é mais eficiente para volumes
maiores
([Search e SearchStream](https://developers.google.com/google-ads/api/rest/common/search)).

Consulta-base de campanhas, a ser validada com o Query Builder da versão vigente:

```sql
SELECT
  segments.date,
  campaign.id,
  campaign.name,
  campaign.status,
  campaign.advertising_channel_type,
  metrics.impressions,
  metrics.clicks,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversions_value
FROM campaign
WHERE segments.date BETWEEN 'YYYY-MM-DD' AND 'YYYY-MM-DD'
  AND campaign.status != 'REMOVED'
```

Para o dashboard, a Revy pode derivar CTR, CPC, custo por lead, custo por venda e
ROAS combinando métricas Google com eventos próprios. `cost_micros` precisa ser
dividido por 1.000.000 para virar valor monetário
([referência de métricas](https://developers.google.com/google-ads/api/fields/latest/metrics)).

### Estratégia de sincronização recomendada

Esta é uma recomendação de arquitetura da Revy, não uma exigência da API:

- carga inicial diária por conta e campanha;
- sincronização incremental periódica;
- reprocessamento de uma janela recente para absorver atrasos de atribuição;
- upsert pela chave `(customer_id, campaign_id, segments.date)`;
- sincronização noturna de metadados e status;
- job de reconciliação quando a conta volta após falha de OAuth;
- horário exibido no fuso da conta Google Ads e moeda preservada por conta.

O Google recomenda sincronização periódica porque alterações feitas diretamente
na interface podem deixar o banco local desatualizado
([boas práticas da API](https://developers.google.com/google-ads/api/docs/best-practices/overview)).

## 5. Captura de GCLID, GBRAID e WBRAID

### Na entrada do lead

Auto-tagging precisa estar habilitado na conta. Ele adiciona o `gclid` à URL e é
necessário para conversões offline. Redirects devem preservar os parâmetros até a
landing page final
([auto-tagging](https://support.google.com/google-ads/answer/3095550)).

Todas as páginas de entrada da Revy — catálogo, landing page e formulários —
devem:

1. ler `gclid`, `gbraid` e `wbraid` da query string;
2. guardar os valores exatamente como chegaram, tratando-os como opacos;
3. preservar os parâmetros em redirects internos;
4. associá-los a um identificador first-party de sessão;
5. anexá-los ao lead quando ele informar telefone ou iniciar o atendimento;
6. manter também URL de entrada, referrer e UTMs para explicação interna.

O GCLID é case-sensitive, deve ser armazenado sem transformação e ligado ao
prospect no sistema de leads
([configuração oficial com GCLID](https://support.google.com/google-ads/answer/7012522)).
GBRAID e WBRAID também devem ser preservados como valores opacos. Ao devolver a
conversão, o mapeamento atual da Data Manager API é:

| Captura Revy | Data Manager API |
|---|---|
| `gclid` | `event.ad_identifiers.gclid` |
| `gbraid` | `event.ad_identifiers.gbraid` |
| `wbraid` | `event.ad_identifiers.wbraid` |
| identificador único | `event.transaction_id` |

O mapeamento é oficial
([field mappings](https://developers.google.com/data-manager/api/devguides/events/google-ads/offline/upgrade/field-mappings)).

Se nenhum click ID estiver disponível, a Data Manager API recomenda capturar
`session_attributes`; eles também podem ser enviados junto com outros
identificadores
([envio de eventos e session attributes](https://developers.google.com/data-manager/api/devguides/events/send-events)).

### Atribuição dentro da Revy

GCLID/GBRAID/WBRAID servem para o Google fazer o match. Eles não devem ser
“decodificados” pela Revy. Para explicar a origem ao empreendedor, a Revy deve
guardar também UTMs e URL de entrada.

Opcionalmente, `click_view` permite consultar GCLID com campanha para cliques
recentes. Essas queries devem cobrir um único dia e só alcançam os 90 dias
anteriores, portanto não substituem a captura first-party no momento da entrada
([limitação do ClickView](https://developers.google.com/google-ads/api/fields/latest/overview)).

## 6. Devolução de conversões

### Ações de conversão

A Revy não deve criar ações de conversão silenciosamente. O cliente ou gestor cria
as ações no Google Ads e a Revy permite selecionar as correspondências, por
exemplo:

- Lead qualificado;
- Simulação multibanco concluída;
- Proposta enviada;
- Venda confirmada.

O cliente decide no Google Ads quais ações são primárias ou secundárias. No Revy
Control, cada tipo de evento interno fica vinculado ao ID de uma ação existente.

Para conversões offline e enhanced conversions for leads, o destino precisa:

- apontar `operatingAccount` para a conta que **possui** a ação de conversão;
- usar em `productDestinationId` uma ação com tipo `UPLOAD_CLICKS`;
- informar `loginAccount` quando o usuário entra por uma manager account.

Essas regras são diferentes de simplesmente enviar para qualquer conta pai/filha
e estão descritas em
[destinos de eventos](https://developers.google.com/data-manager/api/devguides/events/send-events)
e
[diferenças na migração](https://developers.google.com/data-manager/api/devguides/events/google-ads/offline/upgrade).

### Evento a enviar

Um `Event` deve conter, conforme o caso:

- timestamp da conversão em RFC 3339;
- `transaction_id` único e estável;
- `event_source`, como `WEB`, `PHONE`, `IN_STORE` ou `OTHER`;
- `gclid`, `gbraid` e/ou `wbraid`, quando disponíveis;
- email e telefone normalizados e hasheados, quando houver consentimento;
- valor e moeda para eventos com valor econômico;
- consentimento;
- destino da ação de conversão.

O Google recomenda enviar GCLID e dados fornecidos pelo usuário juntos quando
ambos estiverem disponíveis
([guia de upgrade das importações](https://support.google.com/google-ads/answer/15479791)).

Para enhanced conversions for leads, o cliente precisa aceitar os termos de dados
do cliente e habilitar enhanced conversions. O estado pode ser verificado pela
Google Ads API usando:

```sql
SELECT
  customer.id,
  customer.conversion_tracking_setting.accepted_customer_data_terms,
  customer.conversion_tracking_setting.enhanced_conversions_for_leads_enabled
FROM customer
```

Esses pré-requisitos são documentados pelo Google
([enhanced conversions for leads](https://developers.google.com/google-ads/api/docs/conversions/upload-offline)).

### Normalização e hash

Antes do envio:

- email: normalizar conforme as regras do domínio e aplicar SHA-256;
- telefone: normalizar em E.164 e aplicar SHA-256;
- nome/sobrenome, quando usados: normalizar e aplicar SHA-256;
- país e CEP não são hasheados;
- informar se a codificação final é HEX ou Base64.

As regras detalhadas, inclusive o tratamento especial de endereços Gmail, estão em
[formatação de dados](https://developers.google.com/data-manager/api/devguides/concepts/formatting).
Criptografia adicional dos valores já hasheados é suportada com DEK e KMS e pode
ser adotada como defesa em profundidade
([criptografia da Data Manager API](https://developers.google.com/data-manager/api/devguides/concepts/encryption)).

## 7. Idempotência, falhas e auditoria de uploads

### Idempotência

Dentro da mesma ação de conversão, o Google usa `transactionId` para
deduplicar eventos enviados de fontes diferentes
([deduplicação](https://developers.google.com/data-manager/api/devguides/events/send-events)).

A Revy deve gerar um identificador determinístico, por exemplo:

```text
revy:{loja_id}:{tipo_evento}:{id_evento_de_dominio}
```

Recomendações:

- restrição única local por loja, tipo de evento e evento de domínio;
- outbox transacional criada junto com a mudança comercial;
- todo retry reutiliza o mesmo `transaction_id`;
- nunca gerar um novo ID apenas porque houve timeout;
- guardar payload canônico, destino, tentativa, request ID e resultado;
- impedir que “venda confirmada” seja enviada duas vezes por caminhos diferentes.

### O modelo de falha atual

A Data Manager API **não usa** o `partial_failure=true` da antiga Google Ads API.
Ela usa:

1. **fast-fail síncrono:** se qualquer registro falhar na validação básica, a
   requisição inteira falha e nenhum registro é processado;
2. **processamento assíncrono:** uma requisição aceita retorna `request_id`;
3. **diagnóstico posterior:** `RetrieveRequestStatus` pode terminar em `SUCCESS`,
   `PARTIAL_SUCCESS` ou `FAILURE`, com contagens de avisos e erros.

Essa distinção está documentada em
[modelo de erros](https://developers.google.com/data-manager/api/devguides/concepts/understand-errors)
e
[diagnósticos](https://developers.google.com/data-manager/api/devguides/diagnostics).

Fluxo da Revy:

```text
PENDING
  → VALIDATING (validateOnly)
  → SUBMITTED (request_id)
  → PROCESSING
  → SUCCESS | PARTIAL_SUCCESS | FAILURE
  → RETRYABLE | DEAD_LETTER, quando necessário
```

Usar `validateOnly=true` na homologação e nas primeiras remessas de cada
configuração. Em produção, armazenar cada `request_id` e consultar o diagnóstico
com backoff exponencial e jitter. O Google recomenda esperar inicialmente 30
minutos; o processamento pode levar até 24 horas.

Como os diagnósticos assíncronos são agregados por motivo, os lotes devem ser
separados por loja, ação e janela de tempo. Isso limita o impacto e facilita
reconciliação sem misturar clientes.

## 8. Consentimento, privacidade e segurança

Enhanced conversions só pode usar dados first-party recebidos diretamente do
cliente. A loja precisa:

- informar que compartilha dados com terceiros para mensuração publicitária;
- obter consentimento quando exigido;
- cumprir as leis de privacidade e as políticas do Google;
- não enviar dados de menores de 13 anos;
- não enviar conversões relacionadas a categorias sensíveis proibidas.

A Revy, como third-party uploader autorizado, também precisa de termos contratuais
adequados com as lojas
([política de dados do cliente](https://support.google.com/google-ads/answer/7475709)).

O modelo de consentimento da Data Manager API contém:

- `adUserData`: consentimento para dados de usuário de publicidade;
- `adPersonalization`: consentimento para personalização de anúncios;
- valores granted, denied ou unspecified.

([objeto Consent](https://developers.google.com/data-manager/api/reference/rest/v1/Consent))

Requisitos internos recomendados:

- registrar versão, origem e timestamp do consentimento;
- não enviar `userData` quando a base legal/consentimento aplicável não permitir;
- minimizar a retenção de PII e click IDs;
- separar dados e chaves por loja;
- criptografar banco, backups e tokens;
- mascarar email, telefone, click IDs e tokens em logs;
- manter trilha de quem conectou, trocou conta, mapeou ação e reprocessou evento;
- permitir desconexão e exclusão conforme a política de retenção da Revy.

## 9. Dashboard, saúde e auditoria

### Dashboard de aquisição

Por loja e período:

- investimento;
- impressões;
- cliques;
- CTR;
- CPC;
- leads Revy atribuídos;
- simulações;
- propostas;
- vendas;
- custo por lead;
- custo por venda;
- receita e/ou margem atribuída;
- ROAS;
- comparação por campanha.

É importante separar visualmente:

- **métricas Google**, atribuídas pelo modelo e pela data do clique/impressão;
- **eventos Revy**, organizados pela data em que lead, simulação ou venda ocorreu.

Conversões importadas aparecem nos relatórios do Google pela data do clique ou da
impressão, não pela data do upload. O processamento costuma ser mais rápido, mas
pode levar até 72 horas para eventos com GBRAID/WBRAID
([discrepâncias em conversões offline](https://support.google.com/google-ads/answer/13321563)).

### Saúde por conexão

Mostrar:

- OAuth válido ou revogado;
- conta cliente ainda acessível;
- `login_customer_id` válido;
- auto-tagging habilitado;
- última sincronização e atraso;
- ações de conversão mapeadas e ativas;
- termos de dados aceitos;
- enhanced conversions habilitado;
- último upload e último sucesso;
- eventos pendentes, com erro e em dead-letter;
- taxa de sucesso/erro por ação;
- avisos e erros dos diagnósticos;
- uso de quota e throttling;
- request IDs para suporte.

### Auditoria

Registrar sem PII:

- loja, conexão e customer ID;
- ator que conectou/desconectou;
- troca de conta ou ação de conversão;
- método/serviço Google utilizado;
- início/fim e quantidade de linhas da sincronização;
- request ID retornado pelo Google;
- contagens de eventos enviados, aceitos, rejeitados e avisos;
- código do erro e número de retries;
- versão da integração.

## 10. Limites e riscos

### Google Ads API

- Cada `Search` ou `SearchStream` conta como uma operação, independentemente do
  número de lotes retornados pelo stream.
- A cota diária depende do nível do developer token.
- Respostas gRPC têm limite de tamanho; consultas devem selecionar somente os
  campos necessários.
- Limites de QPS são aplicados por customer ID e developer token e podem variar
  com a carga; usar throttling e retries com backoff.

([cotas da Google Ads API](https://developers.google.com/google-ads/api/docs/best-practices/quotas),
[rate limits](https://developers.google.com/google-ads/api/docs/productionize/rate-limits))

### Data Manager API

Na documentação atual:

- `IngestionService`: 100.000 requisições/dia por projeto;
- 300 requisições/minuto;
- até 2.000 eventos por `IngestEventsRequest`;
- até 10 identificadores de usuário por evento;
- até 10 destinos por requisição.

Esses números devem ser lidos da documentação no momento da implementação
([limites da Data Manager API](https://developers.google.com/data-manager/api/devguides/limits)).

### Janelas e atrasos

- GCLID é mantido por 90 dias.
- Enhanced conversions for leads têm janela de até 63 dias após o clique.
- Uma conversão não pode ocorrer antes do clique.
- Cliques muito recentes podem exigir nova tentativa após pelo menos seis horas.

([FAQ de conversões offline](https://support.google.com/google-ads/answer/10029210),
[erros de importação](https://support.google.com/google-ads/answer/13321563))

### Riscos principais

| Risco | Mitigação |
|---|---|
| Usuário conecta a manager account errada | descoberta hierárquica, seleção explícita e validação |
| Ação de conversão pertence a outra conta | validar o conversion customer antes de habilitar uploads |
| OAuth revogado | health check, reconexão guiada e alerta |
| Duplicidade de venda | `transaction_id` determinístico e restrição única local |
| Perda de GCLID em redirect | teste ponta a ponta de parâmetros e persistência first-party |
| Lead sem click ID | user data consentido e session attributes |
| Painel diverge do Google | explicar data de atribuição e reprocessar janela recente |
| Lote parcialmente processado | guardar `request_id`, consultar diagnóstico e reconciliar |
| PII exposta em logs | hash, criptografia, mascaramento e allowlist de campos |
| Revy alterar campanha por engano | nenhum endpoint `Mutate`, autorização e testes de contrato |
| Versão da API expirar | acompanhar release notes, sunset e atualizar cliente regularmente |

## 11. Modelo técnico mínimo sugerido

```text
google_ads_connections
  id, loja_id, oauth_secret_ref, scopes, status,
  connected_by, connected_at, expires_or_revoked_at

google_ads_accounts
  id, connection_id, customer_id, login_customer_id,
  name, currency_code, time_zone, is_manager, selected, sync_status

google_ads_campaign_daily
  account_id, campaign_id, date, name, status, channel,
  impressions, clicks, cost_micros, conversions, conversion_value

lead_attribution
  lead_id, landing_url, referrer,
  gclid, gbraid, wbraid,
  utm_source, utm_medium, utm_campaign, captured_at

google_ads_conversion_bindings
  loja_id, revy_event_type, account_id,
  conversion_action_id, conversion_action_name, enabled

google_ads_conversion_outbox
  id, loja_id, domain_event_id, event_type,
  transaction_id, payload_encrypted, status, next_attempt_at

google_ads_upload_attempts
  outbox_or_batch_id, request_id, attempt,
  status, error_code, warning_counts, error_counts, created_at
```

PII e click IDs não devem aparecer em telas técnicas nem logs. No banco, devem
seguir criptografia e retenção compatíveis com o risco e a política de privacidade.

## 12. Sequência de implementação recomendada

### Fase 0 — aprovação e fundação

- criar projeto Google Cloud de produção e teste;
- configurar consent screen, políticas e domínios;
- solicitar developer token;
- habilitar Google Ads API e Data Manager API;
- configurar secrets e criptografia;
- definir eventos comerciais que poderão virar conversão.

### Fase 1 — conexão e leitura

- OAuth multiusuário;
- descoberta de contas e hierarquia;
- seleção da conta por loja;
- GAQL de cliente, campanhas, métricas e ações de conversão;
- sincronização incremental;
- dashboard de aquisição;
- saúde e auditoria.

### Fase 2 — captura e atribuição

- capturar GCLID, GBRAID, WBRAID, UTMs e landing metadata;
- preservar parâmetros em redirects;
- associar sessão ao lead e à conversa;
- testar catálogo → WhatsApp/formulário → lead;
- exibir origem explicável no Revy Loja e métricas no Revy Control.

### Fase 3 — devolução de conversões

- mapear eventos Revy para ações existentes;
- verificar termos e enhanced conversions;
- normalizar/hash de user data;
- outbox idempotente;
- `IngestEvents` pela Data Manager API;
- validação, retries e diagnósticos;
- tela de reconciliação e dead-letter.

### Fase 4 — inteligência comercial

- cruzar custo Google com lead, simulação, proposta, venda, receita e margem;
- alertas de queda de conversão ou conexão;
- comparação por campanha sem alterar a campanha;
- recomendações para o gestor e para o empreendedor.

## 13. Critérios de aceite

- uma loja conecta sua própria conta sem compartilhar senha com a Revy;
- a Revy lista somente contas permitidas pelo OAuth;
- campanhas e métricas sincronizam sem usar nenhum método `Mutate`;
- redirects preservam os identificadores Google;
- cada lead mantém atribuição first-party;
- eventos são enviados à conta que possui a ação de conversão;
- retries não duplicam conversões;
- cada upload possui request ID e diagnóstico rastreável;
- dados sem consentimento não são usados em enhanced conversions;
- dono/gerente veem resultado comercial; gestor vê aquisição e mensuração;
- nenhuma tela permite criar, editar ou pausar campanha.

## Decisão recomendada

Implementar a integração Google Ads dentro do **Revy Control**, não como agência de
tráfego:

- o gestor conecta a conta e continua operando campanhas diretamente no Google;
- a Revy lê resultados, mede a jornada dentro do Revy Loja e devolve conversões;
- o Revy Control mostra onde o tráfego gera leads, simulações, vendas e margem;
- a Revy não recebe responsabilidade de criação ou otimização operacional das
  campanhas.

Usar a versão vigente da Google Ads API suportada pela biblioteca oficial escolhida,
sem fixar o plano a uma versão histórica. O Google recomenda atualizar para a
versão mais recente e publica versões novas com frequência
([versionamento e sunset](https://developers.google.com/google-ads/api/docs/sunset-dates),
[guia de upgrade](https://developers.google.com/google-ads/api/docs/upgrade)).
