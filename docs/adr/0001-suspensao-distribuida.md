---
status: accepted
---

# Suspensão distribuída preserva histórico e captura ingressos sem processá-los

O Revy Control projeta o estado da Loja e dos módulos Vendas e Estoque para cada
serviço operacional. O estado mais restritivo prevalece: suspensão interrompe novos
efeitos, mas não apaga histórico, não desliga autenticação e não usa a situação da
cobrança como autorização. Webhooks externos continuam sendo autenticados,
deduplicados e registrados de forma passiva para evitar perda e tempestades de retry,
sem atendimento, automação ou saída.

## Invariantes

- Um efeito operacional só é permitido quando a Loja está `ativa` e o módulo exigido
  está contratado e `ativo`.
- `encerrada` é terminal. `suspensa` pode voltar a `ativa` somente por transição
  explícita e versionada do Control.
- Reativar a Loja não reativa um módulo suspenso. Reativar um módulo não supera uma
  Loja não ativa.
- Cobrança `atrasada` é alerta administrativo e nunca muda o estado operacional.
- Histórico privado continua legível apenas para identidade, Loja e cargo autorizados.
- Ações redutoras de risco — cancelar trabalho pendente, desconectar credencial,
  despublicar e revogar — podem continuar, com auditoria.
- O gate existe no serviço que produz o efeito. Esconder menu, bloquear apenas o
  proxy ou parar um worker global não constitui suspensão.
- Todo envio WhatsApp deve passar pelo port de provedor do Chatbot. Enquanto o n8n
  legado chamar a Evolution diretamente, ele precisa revalidar o estado imediatamente
  antes da chamada externa; validar apenas no início do workflow não fecha a corrida.

## Precedência

| Estado projetado | Efeito |
|---|---|
| Loja `encerrada` | somente histórico, auditoria e captura terminal de ingressos |
| Loja `suspensa` | todos os módulos bloqueados, ainda que estejam ativos |
| Loja `rascunho`, `em_configuracao` ou `pronta` | onboarding no Control permitido; produção bloqueada |
| Loja `ativa` + módulo ausente | módulo não contratado; efeito bloqueado |
| Loja `ativa` + módulo `suspenso` | somente esse módulo bloqueado |
| Loja `ativa` + módulo `ativo` | efeito permitido, sujeito a cargo, flag e saúde local |

Uma integração, credencial ou flag local pode restringir uma capacidade, mas nunca
elevar a permissão recebida do Control.

## Matriz normativa

`ALLOW` significa permitir sob a autorização já existente. `CAPTURE` significa
persistir envelope/fato e dedupe, sem avançar o domínio. `BLOCK` significa não criar
novo efeito. `TERMINATE` encerra trabalho pendente sem retomada. `PARK` preserva uma
entrega idempotente para revalidação posterior. Loja suspensa sempre substitui as
colunas de módulo.

| Superfície | Loja suspensa | Vendas suspenso | Estoque suspenso |
|---|---|---|---|
| Histórico privado de vendas, conversas, simulações, estoque e auditoria | ALLOW | ALLOW | ALLOW |
| Configuração estrutural e reparo de integração no Control | ALLOW | ALLOW | ALLOW |
| Novo lead, etapa, handoff, mensagem, proposta, meta ou venda | BLOCK | BLOCK | ALLOW se não tocar Estoque |
| Criar, editar, importar, fotografar, publicar, reservar ou vender veículo | BLOCK | ALLOW se Loja e Estoque ativos; `vender` só atualiza inventário | BLOCK |
| WhatsApp inbound de cliente | CAPTURE, sem atendimento | CAPTURE, sem atendimento | ALLOW por Vendas |
| WhatsApp inbound de grupo de estoque | CAPTURE, sem comando | ALLOW se Estoque ativo | CAPTURE, sem comando |
| Mensagem humana ou do bot para cliente | BLOCK | BLOCK | ALLOW por Vendas |
| Nova simulação por dados informados | BLOCK | BLOCK | ALLOW |
| Simulação que consulta veículo/placa | BLOCK | BLOCK | BLOCK |
| Leitura de resultado de simulação | ALLOW | ALLOW | ALLOW |
| Cancelamento de job ainda pendente | ALLOW | ALLOW | ALLOW |
| Projeção autenticada de venda/cancelamento | criação/confirmação anterior ao corte reconcilia histórico; posterior é CAPTURE; cancelamento ALLOW | criação/confirmação anterior ao corte reconcilia histórico; posterior é CAPTURE; cancelamento ALLOW | reconciliar Vendas; bloquear a baixa de Estoque; cancelamento ALLOW |
| Meta/Google: leitura de métricas já persistidas localmente | ALLOW | ALLOW | ALLOW |
| Meta/Google: sincronização de campanhas e gasto | BLOCK | ALLOW; Tráfego não é entitlement de Vendas | ALLOW; Tráfego não é entitlement de Estoque |
| Outbox de mensuração CAPI/Google criado antes do corte | PARK | PARK | ALLOW por Vendas |
| Mensagem, simulação ou automação de Vendas pendente | TERMINATE | TERMINATE | ALLOW |
| Entrega webhook/outbox de Estoque já confirmada | PARK e revalidar recurso/versão | ALLOW | PARK e revalidar recurso/versão |
| Catálogo público e mídia pública | 404/HIDE | ALLOW read-only se Estoque ativo | 404/HIDE |
| CTA, interesse e evento de conversão do Catálogo | BLOCK | BLOCK | BLOCK porque a vitrine está oculta |
| Despublicar, revogar, desconectar e auditar | ALLOW | ALLOW | ALLOW |

O Catálogo não altera em massa o campo `publicado` durante suspensão. A visibilidade
é calculada pelo estado operacional, permitindo reativação sem reescrever veículos.
Caches públicos precisam de purge ou chave versionada; o origin sozinho não revoga
uma resposta já armazenada.

## Ingressos, filas e trabalho em voo

- Webhooks WhatsApp e eventos autenticados recebem sucesso após captura durável.
  O registro usa disposição `received_suspended` ou `received_closed` e nunca sofre
  replay automático ao reativar.
- Um evento de criação, avanço ou confirmação de venda ocorrido antes do
  `effective_at` da transição suspensiva correspondente pode reconciliar projeções
  internas depois da suspensão, mas não dispara mensagem, simulação, CAPI ou outra
  saída externa enquanto o gate estiver fechado. Evento posterior ao corte é apenas
  capturado; cancelamento e revogação continuam por reduzirem risco.
- Simulações e mensagens pendentes são canceladas/terminalizadas com motivo de
  entitlement; não retomam como trabalho antigo.
- Somente outboxes de mensuração já existentes no corte, ou derivados de fato anterior
  ao corte, podem ficar estacionados com a mesma chave idempotente. Após reativação
  explícita, só retomam se ainda estiverem dentro da janela de retenção/consentimento;
  caso contrário terminam como expirados. Ingresso ocorrido durante suspensão nunca
  cria entrega futura automática.
- Entrega de Estoque estacionada só retoma após revalidar que a versão do recurso
  ainda é a mesma e que o efeito continua válido.
- Uma chamada externa já iniciada quando a suspensão chega pode concluir e ter seu
  resultado registrado. Nenhum próximo provedor, retry ou etapa é iniciado.
- Limpeza técnica, expiração e compactação podem continuar quando não produzem efeito
  comercial nem apagam histórico obrigatório.

## Contrato da projeção

Cada destino mantém uma projeção local por Loja com:

- `schema_version`;
- `event_id`;
- `loja_id`;
- `aggregate`: `loja`, `vendas` ou `estoque`;
- `version` monotônica e independente por agregado;
- `state`;
- `effective_at`, `occurred_at` e `reason`;
- data de aplicação local.

O Control precisa introduzir uma versão monotônica para Loja; `LojaModulo.versao`
já cumpre esse papel para cada módulo. O consumidor aplica estas regras:

1. se a Loja local já está `encerrada`, qualquer estado posterior diferente de
   `encerrada` vai para quarentena, mesmo com versão maior;
2. versão menor que a atual: ignora como atrasada e registra diagnóstico;
3. mesma versão e mesmo payload: no-op;
4. mesma versão e payload diferente: conflito em quarentena;
5. versão maior: aplica atomicamente;
6. ausência de projeção ou cache vencido: histórico permitido, novo efeito falha
   fechado;
7. cobrança, retry, health check ou ausência de evento nunca reativam estado.

No Motor, o cliente autenticado precisa estar vinculado autoritativamente a uma Loja.
Cada simulação e tarefa persiste esse `loja_id` imutável; o caller nunca escolhe nem
substitui o identificador livremente.

O gate é revalidado na entrada da mutação, ao reservar uma fila e imediatamente antes
do side effect externo. Workers filtram por Loja; nunca se pausa um processo inteiro
multi-loja.

## Respostas estáveis

- rota privada sem módulo contratado: `403 module_not_entitled`;
- rota privada com Loja não operacional: `423 store_not_operational`;
- rota privada com módulo suspenso: `423 module_suspended`;
- recurso de outra Loja: `404`, sem revelar existência;
- Catálogo/ mídia públicos não operacionais: `404`;
- webhook capturado passivamente: `2xx`, com disposição interna auditável.

## Pontos de enforcement auditados

| Serviço | Pontos principais atuais |
|---|---|
| Portal/Revy Loja | `portal-gestao/app/main.py`: Estoque 595–868; Leads/Conversas 883–1120; Simulações 1337–1854; Vendas 1941–2215 |
| Chatbot | `chatbot-api/app/main.py`: webhooks 326–420, conversas/leads 423–638, simulações 719–841; `app/servico.py`: mensagem 546–724 |
| n8n/Evolution | workflows de envio direto precisam migrar para o Chatbot ou revalidar entitlement imediatamente antes de chamar a Evolution |
| Motor | `motor-simulacao/app/servico.py`: criação 91–162; `app/processamento.py`: reserva/execução 614–1007 |
| Estoque | `estoque-api/app/main.py`: mutações 158–346, webhook/importação 401–521, público 527–595; `app/outbox.py`: entregas 55–140; `app/worker.py`: fila 21–81 |
| Catálogo | `catalogo-publico/app/main.py`: vitrine 231–357 e interesse 360–443; `app/events.py`: outbox 112–210 |
| Control/Tráfego | `revy-trafego/app/meta_ads_spend.py`, `app/meta_capi.py`, `app/vendas_projection.py` e workers correspondentes |

O estado atual ainda não implementa esses gates nos destinos. Esta decisão fecha a
semântica necessária para criar as projeções e seus testes sem comportamentos
divergentes entre serviços.
