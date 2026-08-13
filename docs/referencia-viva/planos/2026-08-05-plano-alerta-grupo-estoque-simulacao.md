# Plano — alerta confiável de simulação no grupo do estoque

**Status 2026-08-13:** F0–F3 no código (`notificacoes_operacionais`,
`notificacoes_outbox_job` no lifespan, dead-letter após `CHATBOT_NOTIF_MAX_ATTEMPTS`).
Residual é **ops**: smoke e Active ON do workflow. Não é mais card de código.

**Objetivo:** toda solicitação de simulação aceita pelo bot deve ser persistida, pausar o bot e
gerar exatamente um aviso no grupo de estoque configurado para a loja. O cliente só recebe a
confirmação depois que a solicitação durável foi aceita pelo backend.

**Escopo:** Chatbot API, workflow n8n oficial e Evolution. O Motor/RPA continua independente:
uma falha bancária não pode apagar o pedido humano nem o alerta operacional.

## Veredito do incidente `***9225`

O grupo não deixou de apitar por falta de configuração e o Estoque API não caiu. O caminho
temporário nem chegou a executar seu JavaScript.

Na noite de 2026-08-04, horário de Brasília, o n8n chamou a tool
`TEMP continuar sem estoque1` três vezes para esse contato:

| Execução | Início UTC | Etapa observada | Resultado da tool |
|---:|---|---|---|
| `12407` | `02:35:55` | anúncio sem veículo no estoque digital | erro de schema |
| `12412` | `02:38:34` | cliente aceitou simular | erro de schema |
| `12413` | `02:41:57` | cliente enviou os dados | erro de schema |

Erro reproduzido nas três:

```text
Received tool input did not match expected schema
Unrecognized key(s): instance, remoteJid, telefone, providerMessageId, ...
```

O n8n anexou ao argumento da tool os campos de contexto vindos do webhook. O schema do nó
temporário declara `additionalProperties: false`, então a validação rejeitou a chamada antes da
primeira linha do `jsCode`. Consequências no caso:

- não criou/qualificou o lead pelo caminho temporário;
- não consultou destinos;
- não enviou aviso;
- não pausou o bot;
- ainda assim o Agent produziu “certinho. vou preparar a simulação pra você”.

A execução externa foi gravada como `success` porque o erro da tool foi entregue ao Agent, que
continuou e gerou texto. Por isso olhar apenas o status geral da execução mascara o defeito.

Na janela auditada desde `2026-08-05 00:00:00 UTC` havia cinco chamadas do fallback temporário:
**0 sucessos e 5 erros de schema**. No mesmo período houve uma chamada de `simular1` normal com
status de tool `success`.

## O que não causou este incidente

- **Grupo ausente:** falso. A loja tinha o grupo `estoque revy` configurado, além de um vendedor
  ativo e um dono ativo.
- **Reinício do n8n:** houve reinício às `02:51 UTC`, cerca de nove minutos depois da terceira
  falha. Não foi a causa deste caso.
- **Crash do Estoque API:** o primeiro atendimento recebeu normalmente a resposta de estoque
  vazio. A falha ocorreu na validação de entrada da tool seguinte.

O estado temporário usa `$getWorkflowStaticData('global')`. Isso continua sendo uma fragilidade
para reinício, concorrência e escala horizontal, mas não foi o gatilho do caso `***9225`: a tool
falhou antes de ler ou gravar esse estado.

## Segunda causa: o código atual não envia ao grupo

Mesmo quando as tools executam, `simular1` e `TEMP continuar sem estoque1` fazem isto:

```text
GET /v1/operacao/numeros-autorizados
  → escolhe vendedores; se vazio, donos
  → POST Evolution sendText para cada telefone individual
```

Nenhuma delas chama `/v1/operacao/grupo-estoque`. Portanto, hoje o grupo cadastrado é usado para
operações do estoque, mas não como destino do alerta de simulação.

Há ainda perda silenciosa:

- `simular1` contém sete blocos `catch (_)`, inclusive no envio;
- o fallback temporário contém cinco;
- lista vazia, número inválido, timeout ou HTTP 4xx/5xx da Evolution não mudam a resposta ao
  cliente e não geram uma pendência durável;
- a deduplicação usa memória estática do workflow, não uma chave persistida no banco.

Isso explica a aparência de intermitência:

1. no caminho temporário, a tool atualmente falha sempre que recebe o contexto adicional;
2. no caminho normal, a tool pode concluir, mas envia no privado e absorve qualquer erro;
3. em ambos, o Agent pode falar como se tudo tivesse funcionado.

## Lacuna dos testes atuais

`node n8n/test_fallback_estoque_temporario.js` executa diretamente apenas o conteúdo de
`jsCode`, passando um objeto limpo. Ele não passa pela validação de schema do Tool Code do n8n e,
por isso, fica verde mesmo quando a execução real é rejeitada antes do JavaScript.

`python n8n/validate_workflow.py` valida presença, conexões e trechos de código, mas não verifica
a compatibilidade entre o schema e os campos que o n8n acrescenta ao argumento da tool.

## Arquitetura proposta

```text
n8n identifica intenção + dados mínimos
  → POST Chatbot /v1/operacao/solicitacoes-simulacao-humana
       Idempotency-Key = providerMessageId
       transação: qualifica lead + pausa conversa + cria notificação pending
  → worker/outbox do Chatbot resolve grupo + canal
  → Evolution sendText(instance, grupo_jid)
  → notificação sent ou failed com tentativa/erro sanitizado
  → n8n confirma ao cliente somente após HTTP 202 idempotente
```

O Chatbot deve ser dono desse efeito porque já possui, por loja:

- conversa, lead e canal/instância;
- grupo selecionado em `grupos_estoque`;
- adapter `WhatsAppOutboundPort` com Fake para testes;
- autenticação que deriva `loja_id` do token.

O n8n fica responsável pela conversa e pela extração, não por montar uma sequência de efeitos
HTTP independentes e sem transação.

## Plano de implementação

### Fase 0 — correção imediata e teste de regressão

- [ ] Alterar o schema do nó `TEMP continuar sem estoque1` para tolerar os campos de contexto
  (`additionalProperties: true`) ou isolar explicitamente apenas os argumentos do modelo antes da
  validação. Aplicar no workflow canônico e no workflow de teste gerado.
- [ ] Adicionar teste que valide a tool com o mesmo objeto enriquecido observado na execução
  `12413`, mas com valores sintéticos e sem PII.
- [ ] Fazer o teste falhar com `additionalProperties: false` e passar após a correção.
- [ ] No prompt, proibir a frase de confirmação quando a tool retornar erro ou não retornar
  `ok: true`/`simulacao_humana_solicitada: true`.
- [ ] Não publicar o workflow antes dos testes locais e do smoke controlado.

Aceite: o fallback executa o JavaScript com contexto adicional e uma falha da tool nunca vira
“vou preparar a simulação”.

### Fase 1 — endpoint único e persistência

- [ ] Criar `POST /v1/operacao/solicitacoes-simulacao-humana` no Chatbot.
- [ ] Payload mínimo: `telefone`, `interesse`, `tem_cnh`, `instance` opcional. CPF e nascimento
  não entram no texto do grupo; o endpoint pode receber apenas flags `cpf_recebido` e
  `nascimento_recebido` quando o objetivo for o alerta humano.
- [ ] Exigir `Idempotency-Key` baseada no `providerMessageId` e validá-la como já é feito em outros
  contratos do Chatbot.
- [ ] Em uma transação: criar/atualizar lead qualificado, pausar a conversa e inserir a
  notificação operacional.
- [ ] Nova tabela `notificacoes_operacionais`: `id`, `loja_id`, `canal_id`, `tipo`,
  `idempotency_key` unique por loja, `destino_jid`, `status`, `attempts`, `next_attempt_at`,
  `provider_message_id`, `last_error_code`, `created_at`, `sent_at`.
- [ ] Nunca persistir CPF, nascimento, token ou texto bruto do cliente nessa tabela.

Aceite: duas chamadas com a mesma chave criam um único lead/alerta; reinício entre aceite e envio
não perde a notificação.

### Fase 2 — envio para o grupo selecionado

- [ ] Resolver `GrupoEstoque` pela loja autenticada e usar `grupo_jid` como `number` no adapter
  Evolution existente.
- [ ] Resolver a instância pelo canal da conversa; usar o campo recebido do n8n apenas como
  compatibilidade validada contra uma instância pertencente à mesma loja.
- [ ] Se não houver grupo, retornar/persistir `grupo_estoque_nao_configurado`; não fingir envio.
- [ ] Enviar exatamente uma mensagem, sem CPF/nascimento completos, com final mascarado do
  telefone, interesse, CNH, link do atendimento e instrução para simular.
- [ ] Definir política explícita para fallback privado. Recomendação inicial: **não duplicar**;
  grupo é o destino canônico, e falha aparece no Portal/observabilidade.

Aceite: o Fake recebe uma chamada cujo destino termina em `@g.us`; nenhum telefone individual é
chamado no caminho nominal.

### Fase 3 — outbox, retry e observabilidade

- [ ] Worker com claim atômico, backoff e teto de tentativas; `sent` só após resposta 2xx da
  Evolution.
- [ ] Erros estruturados: `grupo_estoque_nao_configurado`, `canal_desconectado`,
  `evolution_unreachable`, `evolution_send_failed`, sem resposta/payload sensível.
- [ ] Logar `notification_id`, sufixo da loja, tipo, tentativa e status; nunca API key ou PII.
- [ ] Métricas: pedidos aceitos, alertas enviados, falhas, idade da pendência e duplicatas
  evitadas.
- [ ] Expor no Atendimento uma indicação “alerta do grupo pendente/falhou”, com ação de reenvio
  que gere nova tentativa sem duplicar a solicitação.

Aceite: desligar a Evolution, criar o pedido, religá-la e observar a mesma linha `pending` virar
`sent` uma única vez.

### Fase 4 — remover estado crítico do n8n

- [ ] Persistir a moto/interesse escolhido e o estágio do fallback na conversa/sessão do Chatbot.
- [ ] Substituir `$getWorkflowStaticData('global')` para `moto-escolhida:*`,
  `TEMP-estoque-incompleto:*` e dedupe de notificação por consultas ao backend.
- [ ] Manter o static data apenas como cache não autoritativo, se ainda trouxer benefício.
- [ ] Testar reinício do n8n entre: oferta → aceite → dados completos.

Aceite: após reiniciar o n8n, o cliente continua do ponto certo e o alerta não some nem duplica.

### Fase 5 — smoke e rollout

- [ ] Testar caminho com veículo real (`simular1`).
- [ ] Testar anúncio com estoque vazio (fallback temporário).
- [ ] Testar grupo ausente, canal desconectado, Evolution 500/timeout e replay do mesmo webhook.
- [ ] Confirmar no grupo pelo ID retornado pela Evolution, no Portal e na tabela de outbox.
- [ ] Publicar primeiro no workflow de teste; depois promover teste → oficial e manter backup.

## Comandos para reproduzir o diagnóstico

### 1. Estado dos serviços e logs do horário

```powershell
fly status -a n8n2037
fly status -a app2037
fly status -a evolution2037
fly logs -a n8n2037 --no-tail |
  Select-String -Pattern 'DynamicStructuredTool|Received tool input|02:36|02:39|02:42'
```

Os timestamps da Fly/n8n estão em UTC. Para este incidente, subtrair três horas para Brasília.

### 2. Auditar execuções sem parar o n8n

Não usar `n8n list:workflow` no volume em produção. O script abaixo abre o SQLite como
`OPEN_READONLY` e só imprime IDs, horários, status e códigos sanitizados:

```powershell
fly ssh sftp put n8n\diagnose_simulation_executions.js `
  /tmp/diagnose_simulation_executions.js -a n8n2037

fly ssh console -a n8n2037 -C `
  "node /tmp/diagnose_simulation_executions.js --since=2026-08-05T00:00:00.000Z"
```

Resultado observado nesta investigação:

```json
{"summary":{"temp_success":0,"temp_error":5,"normal_success":1,"normal_error":0}}
```

### 3. Conferir destino configurado, sem mostrar telefones ou JID completo

```powershell
fly ssh sftp put chatbot-api\scripts\diagnose_notification_config.py `
  /tmp/diagnose_notification_config.py -a app2037

fly ssh console -a app2037 -C "python /tmp/diagnose_notification_config.py"
```

Resultado observado: grupo configurado, um vendedor ativo e um dono ativo.

### 4. Provar no Git que as tools ignoram o grupo

```powershell
$wf = Get-Content n8n\workflow-ai-nao-salvos.json -Raw | ConvertFrom-Json
$wf.nodes |
  Where-Object name -in @('simular1', 'TEMP continuar sem estoque1') |
  ForEach-Object {
    [pscustomobject]@{
      nome = $_.name
      schema = $_.parameters.inputSchema
      usa_grupo = $_.parameters.jsCode -match '/v1/operacao/grupo-estoque'
      usa_numeros = $_.parameters.jsCode -match '/v1/operacao/numeros-autorizados'
    }
  }
```

Esperado no código atual: `usa_grupo=False` e `usa_numeros=True` para os dois nós.

### 5. Testes atuais e novos gates

```powershell
node n8n/test_fallback_estoque_temporario.js
python n8n/validate_workflow.py

cd chatbot-api
.\.venv\Scripts\python.exe -m pytest `
  tests/test_grupo_estoque.py `
  tests/test_whatsapp_provider_evolution.py `
  tests/test_simulation.py -q
```

Adicionar ao gate um teste de schema real/enriquecido; os dois primeiros comandos sozinhos não
reproduzem a validação que falhou em produção.

## Definição de pronto

- os dois caminhos de simulação usam o mesmo endpoint idempotente;
- o grupo configurado recebe exatamente um alerta;
- nenhum dado sensível vai ao grupo ou aos logs;
- nenhuma exceção de envio é engolida sem estado persistido;
- a confirmação ao cliente depende de aceite durável;
- reinício do n8n/Evolution não perde nem duplica o alerta;
- testes cobrem schema enriquecido, grupo, retries, idempotência e falsa confirmação.
