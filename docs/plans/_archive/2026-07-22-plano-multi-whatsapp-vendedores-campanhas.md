# Plano: Multi-WhatsApp por vendedor e campanhas centralizadas no Revy

**Status:** SUPERSEDED / NÃO IMPLEMENTAR
**Data:** 2026-07-22  
**Escopo:** Chatbot API, Evolution API, n8n, Portal/CRM, campanhas, inbox e deploy Fly 3-VM  
**Fora do MVP:** mudar a versao da Evolution, compartilhar numero pessoal do vendedor e rotear o Catalogo por campanha

> Substituído pelo [design Revy Control](../superpowers/specs/2026-07-29-revy-control-design.md)
> e pela [Fase 5 do plano Revy Control](2026-07-29-plano-revy-control.md#fase-5--múltiplos-números-whatsapp-por-loja).
> A nova decisão usa vários números equivalentes por loja, sem vínculo fixo a vendedor,
> campanha ou finalidade. Este arquivo permanece apenas como diagnóstico técnico histórico.

## 1. Objetivo

Transformar o Revy no centro da operacao comercial, mantendo varios numeros de WhatsApp conectados ao mesmo ambiente:

- cada vendedor possui um canal/numero comercial conectado;
- uma campanha aponta para um vendedor e para o canal daquele vendedor;
- o lead entra pelo numero anunciado e aparece no Revy com campanha, vendedor e canal corretos;
- o vendedor pode continuar respondendo pelo proprio WhatsApp;
- gestores enxergam todos os leads e conversas; vendedores enxergam somente os seus;
- um mesmo cliente que escrever para dois vendedores gera duas conversas, mas continua sendo um unico lead da loja.

Fluxo desejado:

```text
Campanha -> vendedor -> canal WhatsApp -> mensagem recebida
                                      -> conversa no Revy
                                      -> lead central da loja
                                      -> venda/ROI da campanha
```

## 2. Diagnostico do estado atual

Hoje o sistema foi desenhado para **um WhatsApp por loja**, nao para um WhatsApp por vendedor:

- `chatbot-api/app/models_db.py`: `Loja` guarda um unico `evolution_instance` e um unico `whatsapp`;
- `Conversa` e localizada por `(loja_id, telefone)`, portanto nao distingue o numero que recebeu a mensagem;
- `Mensagem` elimina duplicidade por `(loja_id, provider_message_id)`, sem considerar o canal;
- `Lead` e centralizado por `(loja_id, telefone)`, o que e adequado e deve ser preservado;
- `portal-gestao/app/models.py`: campanha nao possui vendedor nem canal de destino;
- rotas de conversa usam telefone como identificador e ficam ambiguas quando o mesmo cliente fala com dois vendedores;
- o workflow `n8n/workflow-ai-nao-salvos.json` possui `__INSTANCE__` fixo em chamadas da Evolution;
- o dashboard do vendedor usa uma atribuicao local por telefone/e-mail, sem identidade de canal/conversa;
- o Catalogo possui apenas o WhatsApp geral da loja.

O webhook ja entrega `body.instance`, e a memoria do n8n ja inclui `instance:telefone`. Essa base pode ser reaproveitada. O registro de mensagens `fromMe` tambem ja permite detectar quando um vendedor respondeu e pausar a automacao, mas deve passar a atuar somente na conversa do canal correto.

## 3. Decisoes de arquitetura

### 3.1 Entidades e responsabilidades

```text
Loja 1 ---- N CanalWhatsApp 0..1 ---- 1 Vendedor (Usuario do Portal)
  |                  |
  |                  N
  |              Conversa N ---- 1 Lead
  |                  |
  |                  N
  |               Mensagem
  |
  N Campanha ---- 1 Vendedor + 1 CanalWhatsApp
        |
        N IdentificadorExternoDeAnuncio
```

- **Chatbot API** e dono de canais, conversas, mensagens e leads.
- **Portal** e dono de usuarios, campanhas, vendas, permissoes e ROI.
- A integracao continua somente por HTTP; nao criar foreign key entre bancos dos produtos.
- `vendedor_ref` no Chatbot guarda o `Usuario.id` estavel do Portal, nunca nome ou e-mail.
- No MVP, cada vendedor tem no maximo um canal comercial ativo por loja. O modelo permite ampliar depois.

### 3.2 Identidade do lead e da conversa

- **Lead:** unico por `(loja_id, telefone_cliente)`. Representa a pessoa centralizada no Revy.
- **Conversa:** unica por `(canal_id, telefone_cliente)`. Representa a relacao daquele cliente com aquele numero/vendedor.
- **Mensagem:** pertence a uma conversa e a um canal; deduplicacao por `(canal_id, provider_message_id)`.

Exemplo: o telefone do cliente escreve para Joao e depois para Maria. O Revy mostra **1 lead, 2 conversas e 2 responsaveis/contextos comerciais**.

### 3.3 Numeros permitidos

Usar numeros comerciais dedicados. Conectar o WhatsApp pessoal de um vendedor faria conversas particulares chegarem ao webhook e ao CRM. Antes do rollout, a loja deve confirmar por escrito que cada numero conectado e corporativo e que as conversas comerciais serao registradas.

No MVP:

- capturar conversas 1:1 dos canais comerciais, mesmo quando o contato ja estiver salvo;
- manter a resposta automatica da IA para contatos salvos **desligada por padrao**;
- ignorar grupos, status, reacoes sem mensagem util e numeros internos autorizados;
- desativar/desconectar um canal sem apagar o historico.

### 3.4 Atribuicao de campanha

A atribuicao deve usar a melhor evidencia disponivel, nesta ordem:

1. identificador de anuncio/referral recebido da Meta/Evolution;
2. codigo publico da campanha presente na mensagem pre-preenchida;
3. UTM do Catalogo/site;
4. campanha desconhecida, mantendo ao menos canal e vendedor conhecidos.

Nao assumir o formato exato do referral na Evolution v2.3.7. A Task 0 deve capturar um evento real de Click-to-WhatsApp, remover dados pessoais e transformar o resultado em fixture de teste. A Meta informa que mensagens vindas de anuncios podem incluir `referral`, mas o usuario pode remover esses dados antes do envio; por isso o codigo publico e um fallback necessario.

## 4. Modelo de dados proposto

### 4.1 Chatbot API

Nova tabela `whatsapp_canais`:

| Campo | Finalidade |
|---|---|
| `id`, `loja_id` | identidade e tenant |
| `vendedor_ref` | `Usuario.id` do Portal; nulo apenas para canal legado/geral |
| `nome`, `tipo` | rotulo e `legado` ou `vendedor` |
| `instance_name` | nome opaco e unico na Evolution; nao incluir telefone/nome pessoal |
| `numero_e164` | numero efetivamente conectado |
| `status` | `aguardando_qr`, `conectando`, `conectado`, `desconectado` ou `desativado` |
| `bot_habilitado` | permite automacao naquele canal |
| `ia_contatos_salvos` | `false` por padrao |
| `ativo` | bloqueio logico, sem exclusao de historico |
| `conectado_em`, `ultimo_evento_em` | saude e operacao |
| timestamps | auditoria basica |

Alteracoes relacionadas:

- `conversas`: adicionar `canal_id`, `lead_id`, `vendedor_ref_snapshot`, `meta_ad_id_origem` e `campanha_codigo_origem`; trocar unicidade para `(canal_id, telefone)`;
- `mensagens`: adicionar `canal_id`; trocar deduplicacao para `(canal_id, provider_message_id)`;
- `leads`: manter unicidade por loja/telefone e adicionar referencias de primeiro/ultimo canal, vendedor, anuncio e campanha;
- manter `Loja.evolution_instance` e `Loja.whatsapp` temporariamente como campos legados.

Migrations sugeridas:

- `0010_whatsapp_canais.py`: cria canais e converte o numero atual de cada loja em um canal `legado`;
- `0011_conversas_por_canal.py`: preenche `canal_id`, cria os novos indices/restricoes e torna a leitura channel-aware.

### 4.2 Portal

Migration sugerida `0009_multi_whatsapp_campanhas.py`:

- `campanhas.vendedor_id`;
- `campanhas.canal_ref`;
- `campanhas.tipo_destino` (`whatsapp_direto`, `catalogo` ou `site`);
- `campanhas.codigo_publico`, unico por loja e sem dado pessoal;
- nova tabela `campanha_anuncios` com campanha, plataforma, tipo do objeto e ID externo;
- unicidade do anuncio por `(loja, plataforma, tipo_objeto, id_externo)`;
- `vendas.conversa_ref` para congelar a origem correta da venda;
- `atendimento_atribuicoes.conversa_ref` e `canal_ref`.

O vinculo campanha -> vendedor -> canal precisa ser validado no Portal: os tres devem pertencer a mesma loja, o canal deve estar ativo e o vendedor nao pode estar desativado.

## 5. APIs e contratos

### 5.1 Gestao de canais no Chatbot

```text
GET    /v1/whatsapp/canais
POST   /v1/whatsapp/canais
GET    /v1/whatsapp/canais/{canal_id}
PATCH  /v1/whatsapp/canais/{canal_id}
POST   /v1/whatsapp/canais/{canal_id}/conectar
GET    /v1/whatsapp/canais/{canal_id}/estado
POST   /v1/whatsapp/canais/{canal_id}/desconectar
POST   /v1/whatsapp/canais/{canal_id}/desativar
```

Regras:

- criacao exige `Idempotency-Key`;
- QR code e resposta sensivel, com `Cache-Control: no-store` e sem log;
- nenhuma rota retorna API key/token da Evolution;
- `instance_name` e criado pelo backend;
- requisicoes e respostas sempre respeitam `loja_id` do usuario autenticado;
- desconectar/desativar preserva conversas e mensagens.

### 5.2 Conversas

```text
GET   /v1/conversas?vendedor_ref=&canal_id=
GET   /v1/conversas/{conversa_id}/mensagens
GET   /v1/conversas/{conversa_id}/estado
PATCH /v1/conversas/{conversa_id}/estado
```

As rotas antigas baseadas em `{telefone}` ficam por uma versao para compatibilidade. Se houver duas conversas para o mesmo telefone, devem responder `409 ambiguous_conversation`, nunca escolher uma silenciosamente.

### 5.3 Adaptador Evolution

Criar um unico `evolution_client.py` para encapsular:

- criar instancia;
- obter QR/conectar;
- listar e consultar estado;
- configurar webhook por instancia;
- enviar texto e midia usando a instancia da conversa;
- logout/desconexao.

Toda chamada deve ter timeout, tratamento de erro sem vazar segredo e logs com `canal_id`/`instance_name`. A versao de producao continua fixada em **v2.3.7** durante esta mudanca.

## 6. Workflow n8n

Manter **um workflow dinamico**, nao uma copia por vendedor.

Mudancas:

- extrair `body.instance` no inicio;
- consultar o Chatbot para resolver a instancia em `canal_id`, loja e vendedor;
- rejeitar instancia desconhecida;
- substituir todos os usos de `__INSTANCE__` pelo canal do evento ou da conversa;
- registrar toda mensagem comercial 1:1, inclusive de contato salvo;
- separar a decisao de persistir da decisao de responder com IA;
- ao enviar texto/foto, usar a instancia retornada pela conversa;
- em `fromMe`, registrar a mensagem e pausar somente aquela conversa;
- manter a chave de memoria com instancia + telefone;
- validar e testar os caminhos de cliente, vendedor autorizado, grupo/status e erro.

O `prepare-workflow.ps1` deixa de injetar uma instancia unica. Configuracoes globais continuam sendo injetadas sem gravar segredos no JSON versionado.

## 7. Experiencia no Portal

### 7.1 Equipe / WhatsApp

Na tela da equipe, incluir por vendedor:

- estado do canal;
- acao **Conectar WhatsApp**;
- QR temporario;
- numero confirmado depois da conexao;
- ultimo evento e alerta de desconexao;
- desconectar/desativar sem excluir historico.

O Portal atua como BFF: o navegador nao fala diretamente com a Evolution.

### 7.2 Campanhas

No cadastro/edicao:

- escolher vendedor responsavel;
- selecionar o canal conectado daquele vendedor;
- informar IDs externos de anuncio/ad set/campanha quando existirem;
- gerar codigo publico curto para a mensagem pre-preenchida;
- impedir ativacao se o canal estiver inativo/desconectado;
- exibir aviso e impedir novas campanhas quando o vendedor estiver sem canal.

### 7.3 Inbox central

- dono/gestor: todas as conversas da loja, com filtros por vendedor, canal e campanha;
- vendedor: apenas conversas cujo `vendedor_ref_snapshot`/canal lhe pertence;
- cada item mostra cliente, vendedor, canal, campanha, ultima mensagem, estado do bot e desconexao;
- a conversa e aberta por `conversa_id`, nao por telefone;
- realocacao futura deve gerar auditoria e nao reescrever a origem historica.

## 8. Ordem de implementacao

### Task 0 — prova de contrato e baseline

- registrar versao/configuracao da Evolution v2.3.7 e uso de memoria/CPU atual;
- listar instancias existentes sem expor tokens;
- testar create/connect/state/webhook em ambiente controlado;
- capturar fixture sanitizada de mensagem comum, `fromMe` e Click-to-WhatsApp;
- confirmar persistencia das sessoes apos restart;
- tirar snapshot/backup e criar feature flags com multi-canal desligado.

**Saida:** contrato real documentado e fixtures; nenhuma regra baseada em payload presumido.

### Task 1 — schema aditivo e canal legado

- criar as migrations do Chatbot;
- converter o numero atual em canal `legado` sem downtime;
- criar migration do Portal;
- manter leitura/escrita compativel com o modelo anterior.

**Saida:** producao continua funcionando exatamente com o numero atual.

### Task 2 — servico de canais / Evolution

- criar adaptador e endpoints;
- provisionar nome opaco, webhook e QR;
- sincronizar status real e detectar instancia desconhecida;
- implementar logout/desativacao preservando historico.

### Task 3 — conversa, mensagem e lead por canal

- resolver canal antes de processar evento;
- alterar lookup e deduplicacao;
- ligar conversa ao lead central;
- tornar envio de texto, audio e foto channel-aware;
- aplicar pausa do bot somente a conversa correspondente.

### Task 4 — n8n dinamico

- remover `__INSTANCE__` fixo;
- separar persistencia de resposta da IA;
- usar instancia do evento/conversa em todos os envios;
- atualizar validador, script de preparacao e fixture.

### Task 5 — Portal BFF e conexao por vendedor

- clientes HTTP para as APIs de canal;
- permissoes de dono/gestor;
- UI de estado/QR/conexao/desconexao;
- alertas de canal inativo.

### Task 6 — campanha vinculada

- campos de vendedor/canal/codigo e IDs externos;
- validacoes tenant-aware;
- mensagem/URL de anuncio gerada com fallback de codigo publico;
- snapshot da origem quando a conversa nasce.

### Task 7 — venda, atribuicao e ROI

- ligar venda a `conversa_ref` quando houver;
- resolver campanha por referral, codigo e UTM;
- preservar first/last touch existente;
- manter vendas manuais e origens desconhecidas funcionando.

### Task 8 — inbox e RBAC

- trocar telas para `conversa_id`;
- filtros de dono/gestor;
- isolamento estrito do vendedor;
- auditoria de alteracoes e acesso cross-tenant negado.

### Task 9 — piloto Fly

- conectar somente dois numeros comerciais de teste;
- validar os dois simultaneamente e reiniciar a Evolution;
- observar erros, filas, memoria e desconexoes por 48 horas;
- aumentar RAM da VM Evolution somente se a medicao mostrar necessidade;
- depois ampliar em lotes, com canal legado mantido.

### Task 10 — Catalogo por campanha (fase 2)

No MVP, campanhas Click-to-WhatsApp ja apontam diretamente para o numero do vendedor. Depois, permitir que o CTA do Catalogo resolva `campanha -> canal` sem substituir o WhatsApp geral da loja para visitantes sem campanha.

### Task 11 — fechamento operacional

- metricas por instancia/canal;
- alerta por inatividade/desconexao;
- runbook de reconexao e QR;
- politica de retencao e privacidade;
- documentacao de suporte e treinamento dos vendedores.

## 9. Arquivos esperados

### Chatbot API

- alterar `app/models_db.py`, `app/config.py`, `app/main.py`, `app/servico.py`;
- adaptar `app/audio.py`, `app/vehicle_photo.py`, `app/operacao.py` e `app/cli.py` para receber canal/instancia;
- criar `app/evolution_client.py` e `app/canais_whatsapp.py`;
- criar migrations `0010_whatsapp_canais.py` e `0011_conversas_por_canal.py`;
- criar testes `test_canais_whatsapp.py` e `test_multi_canal.py` e atualizar os atuais.

### Portal

- alterar `app/models.py`, `app/clients/chatbot.py`, `app/main.py`, `app/campanhas.py`, `app/roi_calc.py` e `app/financeiro_calc.py`;
- alterar templates de equipe, campanhas, conversas e dashboard do vendedor;
- criar migration `0009_multi_whatsapp_campanhas.py`;
- ampliar testes de campanha, ROI, RBAC e clientes HTTP.

### n8n e deploy

- alterar `n8n/workflow-ai-nao-salvos.json`, `n8n/validate_workflow.py`, `n8n/update_live_workflow.js` e `n8n/prepare-workflow.ps1`;
- adicionar fixtures sanitizadas de webhook;
- manter `deploy/fly/3vm/fly.canal.toml`, ajustando RAM somente com evidencia;
- fixar o compose standalone em Evolution v2.3.7, removendo uso de `latest`;
- atualizar runbooks sem versionar segredos ou workflow preparado.

### Catalogo (fase 2)

- adaptar o redirecionamento `wa.me`, eventos, contratos e testes para destino por campanha.

## 10. Testes de aceite obrigatorios

- canal legado continua recebendo e respondendo durante a migracao;
- dois vendedores da mesma loja mantem duas instancias conectadas simultaneamente;
- o mesmo cliente nos dois numeros gera 2 conversas e 1 lead;
- o mesmo `provider_message_id` em canais diferentes nao colide;
- anuncio/referral identifica campanha e vendedor corretos;
- sem referral, o codigo publico identifica a campanha;
- sem qualquer identificador, canal e vendedor continuam corretos e campanha fica desconhecida;
- resposta `fromMe` pausa apenas o bot daquela conversa;
- toda resposta automatica sai pela instancia que recebeu a conversa;
- vendedor nao lista nem abre conversa de outro vendedor; gestor lista todas;
- instancia desconhecida e rejeitada e gera metrica/alerta;
- grupo e status nao viram lead/conversa comercial;
- contato salvo e registrado, mas nao recebe IA automaticamente por padrao;
- desconexao preserva historico e bloqueia ativacao de nova campanha;
- restart da Evolution preserva sessoes ou produz alerta operacional claro;
- UTM, first/last touch e ROI ja existentes continuam funcionando.

## 11. Rollout e rollback

Usar migracao **expand/contract**:

1. schema aditivo e flags desligadas;
2. backfill do canal legado;
3. codigo e workflow dinamicos, ainda usando somente o legado;
4. dois canais piloto;
5. observacao de 48 horas;
6. liberacao gradual para vendedores;
7. remocao dos campos antigos apenas em uma entrega futura.

Flags sugeridas:

- `MULTI_WHATSAPP_ENABLED`;
- `WHATSAPP_CHANNEL_MANAGEMENT_ENABLED`;
- `CAMPAIGN_CHANNEL_BINDING_ENABLED`;
- `CENTRAL_INBOX_V2_ENABLED`.

Depois que existirem conversas reais em varios canais, nao executar downgrade que colapse `canal_id`. O rollback seguro e desligar as features novas e voltar para uma versao da aplicacao que ja conheca o schema aditivo. Restauracao de banco e somente para desastre.

## 12. Riscos e controles

| Risco | Controle |
|---|---|
| conversas pessoais no CRM | aceitar apenas numero corporativo dedicado e termo operacional |
| mensagem sair pelo vendedor errado | conversa possui `canal_id`; envio nunca recebe instancia arbitraria do frontend |
| perda de atribuicao CTWA | referral + codigo publico + UTM + origem desconhecida explicita |
| webhook de instancia desconhecida | negar processamento, registrar metrica e alertar |
| vendedor acessar carteira alheia | RBAC no backend e testes cross-tenant/cross-seller |
| QR/token em log/cache | BFF, `no-store`, mascaramento e nunca retornar segredo |
| sessao cair/restart | volume persistente, health check, alerta e runbook de reconexao |
| Evolution sem capacidade | piloto de duas instancias e dimensionamento por metrica |
| migration irreversivel | expand/contract, canal legado e sem `DROP` no mesmo rollout |

## 13. Definicao de pronto do MVP

O MVP esta pronto quando uma loja consegue conectar dois numeros comerciais, vincular cada um ao vendedor e a uma campanha, receber conversas simultaneas, visualizar tudo centralmente no Revy, manter o isolamento do vendedor, responder pelo numero correto e atribuir uma venda a campanha correta sem quebrar o WhatsApp legado.

O primeiro passo de implementacao e a **Task 0**, porque o formato real do webhook e o custo de varias sessoes precisam ser medidos antes de alterar banco, n8n ou telas.
