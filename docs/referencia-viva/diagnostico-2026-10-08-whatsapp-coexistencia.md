# WhatsApp oficial e sincronização com o aplicativo: diagnóstico

Data da consulta: 08/10/2026 (America/Sao_Paulo).
Produto responsável: Chatbot API. Este documento não implementa a correção,
não altera permissões Meta e não comprova o estado do código em produção.

## Problema e objetivo

A loja precisa manter o mesmo número no aplicativo WhatsApp Business do celular
e continuar usando atendimento e automações da Revy, sem depender da conclusão
imediata da verificação empresarial Meta.

A prioridade é diagnosticar e aproveitar a conexão oficial existente. Contratar
outro provedor ou recadastrar o telefone não deve ser o primeiro passo.

## Evidências observadas e limites da conclusão

Consulta autenticada ao Meta Business Manager, autorizada pelo responsável:

| Evidência | Situação em 08/10/2026 |
| --- | --- |
| Portfólio empresarial | Não verificado; solicitação com envio pendente |
| Conta WhatsApp do número terminado em 1046 | Aprovada |
| Número confirmado pelo responsável | Conectado; qualidade alta |
| Parceiro na conta WhatsApp | Revy, com controle total |
| Limite exibido | 250 contatos iniciados pela empresa em 24 horas |
| Pagamento da conta | Forma de pagamento cadastrada |
| Insights de 10/09 a 07/10/2026 | 118 mensagens enviadas e entregues; 114 recebidas |

Não publicar telefone completo, documentos, dados de pagamento, tokens, cookies
ou capturas da conta neste diagnóstico ou nos logs da futura correção.

Os insights comprovam operação oficial no período consultado sem a verificação
empresarial concluída. Não identificam qual aplicação enviou cada mensagem e não
comprovam a entrega atual pela Revy, o modo de onboarding nem a coexistência.
O responsável confirmou que o mesmo número é usado no aplicativo do celular.
Isso deve ser conciliado com o cadastro técnico, sem presumir que o fluxo de
coexistência já foi concluído.

## O que a verificação empresarial limita

A documentação Meta descreve o nível inicial de 250 destinatários únicos fora
da janela de atendimento por período contínuo de 24 horas, compartilhado pelo
portfólio. Não é um teto de 250 mensagens recebidas ou de 250 respostas.
Receber uma mensagem do cliente abre a janela de atendimento de 24 horas;
fora dela, o envio pela API normalmente exige um modelo aprovado.

Separar verificação empresarial, verificação do telefone, permissões/App Review
da aplicação e elegibilidade para coexistência. Uma pendência empresarial não
prova que o webhook, o token ou o número estejam bloqueados.

Há divergência nos critérios de aumento de limite: o painel consultado oferece
1.000 clientes únicos em sete dias, enquanto a documentação geral descreve
2.000 mensagens qualificadas em 30 dias. Não prometer aumento automático;
consultar os critérios e o limite efetivos da conta antes do rollout.

Desde 01/10/2026, a documentação de preços informa uma franquia mensal de
1.000 mensagens de serviço entregues por número e cobrança após a franquia.
Sem pagamento disponível, essas mensagens deixam de ser entregues após o
consumo da franquia. Esse limite financeiro é independente da cota diária.

## Lacunas encontradas no código

Referência da inspeção: commit `aa627be3f7e52bc5678e84b5e30d6c8283c16fe2`.

| Local | Comportamento encontrado | Implicação |
| --- | --- | --- |
| `chatbot-api/app/meta_webhook.py`, `parse_inbound` | Interpreta `messages` e `statuses`; não trata `message_echoes`, `history` ou `smb_app_state_sync` | Respostas do aplicativo podem não ser registradas na Revy |
| `chatbot-api/app/meta_webhook.py`, `assinatura_valida` | HMAC SHA-256 sobre corpo cru | Preservar a validação de origem; não desligar para acomodar um BSP |
| `chatbot-api/app/main.py`, `/webhook/cloud` | Entrada Cloud e contrato normalizado `mensagens[]` | Preservar os consumidores existentes, inclusive n8n |
| `chatbot-api/app/onboarding_cloud.py` | Inscreve app e executa `registrar_numero` | Separar o fluxo comum da coexistência, que orienta pular `/register` |
| `chatbot-api/app/whatsapp_outbound.py`, `CloudWhatsAppOutbound` | Graph API com Bearer e caminho por `phone_number_id` | Não aceita uma chave 360dialog por simples substituição de token |
| `portal-gestao/app/templates/loja/whatsapp_decidir.html` | Usa `sessionInfoVersion: "3"` e `featureType` vazio | Revisar configuração do fluxo e contrato do SDK, sem assumir suporte à coexistência |

O evento oficial de resposta do aplicativo tem `changes[].field` igual a
`smb_message_echoes` e o conteúdo em `changes[].value.message_echoes[]`.
Ele representa saída da empresa; não deve virar uma nova mensagem do cliente
nem disparar o agente como se fosse inbound.

A documentação consultada anuncia a descontinuação das versões 2 e 3 do
Embedded Signup em 15/10/2026. **`sessionInfoVersion` é um parâmetro de eventos
de sessão e, sozinho, não comprova a versão geral do Embedded Signup.** Validar
a integração e os parâmetros exigidos pela versão 4 na documentação atual;
não trocar esse valor mecanicamente nem afirmar que a tela já foi migrada.

## Diagnóstico antes de qualquer alteração externa

1. Confirmar a modalidade do canal existente: Cloud API, aplicação responsável
   e cadastro oficial de coexistência, se houver. Manter o número e a conta.
2. Conferir `phone_number_id`, associação canal/loja, permissões da credencial,
   inscrição da aplicação em `subscribed_apps` e assinatura do campo de echoes.
3. Com um contato autorizado, enviar uma mensagem ao número e acompanhar
   entrada, persistência, encaminhamento normalizado e resposta pela API.
4. Responder pelo celular e verificar, com metadados mínimos, se o evento de
   echo chega ao servidor. Não registrar corpo de conversa ou segredos.
5. Se o echo não chega, investigar assinatura e configuração Meta. Se chega e
   é descartado, corrigir parser e persistência. Se é persistido mas não aparece
   no CRM, seguir o contrato HTTP existente até o consumidor responsável.

Não atribuir toda falha à verificação empresarial ou à ausência do parser:
token, inscrição da aplicação, roteamento, consumidor e rollout também precisam
ser validados. Não foram executados envios reais nem testes em produção nesta
pesquisa.

## Escopo proposto para a futura correção

- Interpretar echoes como mensagens enviadas pela equipe no canal correto,
  resolvendo cliente por destinatário e preservando identidade da loja.
- Persistir o identificador Meta (`wamid`) com idempotência. Tratar reentregas,
  concorrência e correlação com saídas da API sem duplicar mensagens.
- Integrar a resposta do celular às regras existentes de atendimento humano;
  impedir resposta automática concorrente e permitir retomada explícita.
  Não atribuir uma resposta a um vendedor específico sem identidade comprovada.
- Manter assinatura, limites de payload e isolamento entre lojas. Eventos
  desconhecidos não podem gerar respostas ou efeitos de negócio indevidos.
- Preservar `mensagens[]` e os contratos HTTP existentes. Não importar módulos
  `app` entre produtos. Alterações em consumidores são trabalhos separados.
- Tratar texto, áudio e imagem conforme o contrato de mídia existente, incluindo
  falhas de recuperação. Definir como representar tipos ainda não suportados.
- Separar sincronização contínua de importação de histórico. A importação exige
  consentimento e sincronização dentro da janela definida no onboarding; não
  tentar reexecutá-la em uma conta existente sem confirmar o procedimento.
- Se necessário, separar o onboarding de coexistência do fluxo comum para não
  chamar `/register` nesse caminho. Validar versão/configuração do Signup.
- Qualquer flag nova deve iniciar OFF. Ativar somente após testes e piloto
  acompanhado; não migrar ou desregistrar o telefone como parte da correção.

Critérios de aceite: mensagem do cliente chega uma vez; resposta da API é
entregue; resposta do celular aparece uma vez como saída humana; bot respeita
handoff; reentrega e eventos fora de ordem não duplicam conversa/mensagem;
nenhum evento acessa outra loja; áudio/imagem e status seguem o contrato.

Testes da futura implementação, a partir de `chatbot-api/`:

- macOS: `.venv/bin/python -m pytest -q`.
- Windows: `.\.venv\Scripts\python.exe -m pytest -q`.
- Cobrir assinatura inválida, echo válido, deduplicação, isolamento de loja,
  handoff e regressão do inbound Cloud. Testes não substituem o piloto Meta.
- Regenerar o mapa se forem alteradas rotas, modelos, workers, migrations ou
  flags; validar consumidores se o contrato HTTP mudar.

## Alternativas oficiais e decisão para esta loja

| Opção | Verificação imediata e celular | Custo e compatibilidade |
| --- | --- | --- |
| Conexão Meta/Revy existente | Há evidência de operação sem verificação concluída; confirmar coexistência | Primeira opção. Sem mensalidade BSP; tarifas Meta e infraestrutura |
| 360dialog | Verificação não obrigatória para todas as empresas; coexistência sujeita à elegibilidade | €49 ou US$59 por canal/mês, mais Meta. Exige adaptador próprio |
| Infobip | Documenta início após registro e conexão do app; verificação para recursos ampliados | Cotação. Exige integração de API/webhooks |
| Gupshup | Coexistência documentada; política de produção sem verificação não confirmada de forma consistente | Self-service anuncia ausência de assinatura; uso a confirmar |
| Twilio | Self Sign-up exige verificação antes de produção; fluxo padrão exige número livre | US$0,005 por envio/recebimento, mais Meta. Não atende ao requisito atual |
| Zenvia | Página oficial lista conta empresarial Meta verificada como requisito | API sob cotação. Não comprovada como saída sem verificação |

Não contratar um BSP antes de determinar a modalidade atual do número. Contas
de coexistência possuem restrições de migração entre WABAs; não aplicar uma
migração tradicional ao número já conectado. O programa de verificação conduzida
pelo parceiro (PLBV) da 360dialog informa pausa desde 01/09/2026.

Se um BSP for necessário, implementar saída e entrada autenticada próprias:
360dialog usa `POST https://waba-v2.360dialog.io/messages` com `D360-API-KEY` e
permite headers na configuração do webhook. n8n pode orquestrar o fluxo após
normalização, mas não substitui persistência, idempotência ou autenticação.
Não encaminhar payload reserializado para o webhook Meta esperando que a
assinatura do corpo original continue válida.

Coexistência mantém app e API no mesmo número, mas não sincroniza grupos e
altera recursos como listas de transmissão. Não prometer paridade total ou
risco zero. Se a Meta não considerar o número elegível, o provisório oficial é
manter o aplicativo e o CRM com atendimento manual; não há workaround oficial
confirmado que force elegibilidade.

## Fontes primárias consultadas

- [Meta: limites](https://developers.facebook.com/documentation/business-messaging/whatsapp/messaging-limits).
- [Meta: preços](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing).
- [Meta: coexistência, eventos e onboarding](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users/).
- [Meta: Embedded Signup versão 4](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/version-4).
- [360dialog: verificação](https://docs.360dialog.com/docs/resources/meta-business-verification), [preços](https://docs.360dialog.com/docs/get-started/pricing), [coexistência](https://docs.360dialog.com/docs/resources/phone-numbers/coexistence), [onboarding](https://docs.360dialog.com/docs/hub/embedded-signup/coexistence-onboarding) e [pausa PLBV](https://docs.360dialog.com/docs/resources/meta-business-verification/plbv).
- [360dialog: mensagens](https://docs.360dialog.com/docs/messaging-api/api-reference/messages) e [webhook](https://docs.360dialog.com/docs/messaging/webhook).
- [Infobip: verificação](https://www.infobip.com/docs/whatsapp/get-started/business-verification) e [registro](https://www.infobip.com/docs/whatsapp/get-started/embedded-signup).
- [Gupshup: coexistência](https://partner-docs.gupshup.io/docs/co-existence-closed-beta-phase), [self-service](https://docs.gupshup.io/docs/overview) e [orientação antiga de Go-Live](https://support.gupshup.io/hc/en-us/articles/360012075939-What-is-required-to-Go-Live-with-my-app) (2024; não assumir regra atual).
- [Twilio: Self Sign-up](https://www.twilio.com/docs/whatsapp/self-sign-up) e [preços](https://www.twilio.com/en-us/whatsapp/pricing).
- [Zenvia: requisitos](https://zenvia.com/whatsapp/).

Dados da conta foram observados no navegador; regras dos fornecedores são
temporais e precisam de reconferência antes de implementação ou contratação.
