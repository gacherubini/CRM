# Embedded Signup + Tech Provider — design (2026-08-29)

Fase 2 do §11 do [`2026-08-12-whatsapp-dois-modos-design.md`](2026-08-12-whatsapp-dois-modos-design.md).
Este spec detalha os §16.5 e §16.6 daquele documento e **substitui** o onboarding
assistido descrito lá.

## 1. Problema

O §16.6 põe a WABA no CNPJ da loja e chama o onboarding de "assistido, manual nos
passos 5-8". **Isso não roda.** Para um token da Revy tocar numa WABA que não pertence
ao negócio dono do app, o app precisa de **Advanced Access** em
`whatsapp_business_management`; sem ele a chamada volta o **erro de código 200** da Graph
(permissão, não o status HTTP 200 — confusão fácil e cara). Advanced Access só sai
por **App Review**, e o App Review pede vídeo do fluxo funcionando.

Ou seja: o passo 4 do §16.5 depende do passo 6. Não há caminho manual que contorne —
o manual é o que está bloqueado.

O que roda hoje é pendurar o número da loja na WABA da Revy (é o que o piloto de 23-24/08
provou). O dono **recusou** esse caminho em 29/08: não faz sentido pôr o WhatsApp do
cliente na Revy agora.

**Resultado desejado:** o lojista conecta o WhatsApp dele ao Modo 2 sozinho, por um botão
na Revy Loja, e a Revy tem Advanced Access aprovado para operar a WABA dele.

## 2. Decisões tomadas com o dono (2026-08-29)

| # | Decisão | Descartado |
|---|---|---|
| 1 | A loja do cliente **espera**. Constrói-se contra business de teste, alvo é o App Review submetido | pôr o número do cliente na WABA da Revy agora |
| 2 | O botão mora na **Revy Loja**; o Control ganha só a visão | botão no Control (o §11 dizia Control) |
| 3 | Cadeia pós-popup **toda automática**, canal nasce `pendente`, portão de liberação no Control | tudo automático sem freio; automático só até o canal |
| 4 | O **Control continua dono do modo**. Conectar propõe; liberar decide | conectar ligar `whatsapp_modo=2` sozinho; derivar o modo do canal |
| 5 | O fluxo aceita **número novo e número existente**, com a decisão do §16.4 numa tela antes do popup | só número novo na v1 |

Herdadas e **não re-propostas**: billing (cada loja põe o cartão dela na WABA dela e paga a
Meta direto; a Revy fatura só o software — Tech Provider não tem linha de crédito) e
**Embedded Signup v4** (o v2 morre em 15/10/2026).

## 3. O que já está pronto e não se refaz

- Verificação de negócio da Revy: **Verificada em 24/08**. É o degrau 2 do §16.5.
- Ficha do app: ícone, política de privacidade, categoria, URLs legais — 16/08.
- App Ao Vivo, vinculado ao portfólio `4040462592922875`.
- Corpo do template `chama_vendedor` fixado pelo §16.2.
- Webhook da Meta → n8n → chatbot, com assinatura conferida.

## 4. Arquitetura — fronteira entre produtos

O `portal-gestao` serve a página e o SDK. O navegador recebe `code`, `waba_id`,
`phone_number_id` e `business_id`.

**Quem troca o `code` por token é o `chatbot-api`**, porque a troca exige o App Secret, que
já mora lá (`CHATBOT_META_APP_SECRET`) e não ganha segunda cópia. O portal repassa e nunca
vê segredo da Meta. Mantém o invariante: canais são do Chatbot, integração é HTTP versionado.

Rota nova: `POST /v1/whatsapp/canais/cloud/onboarding`, com os quatro campos no corpo. A
loja sai da credencial, nunca do corpo.

**Síncrona de ponta a ponta no primeiro elo.** O `code` tem TTL de **30 segundos** — não
sobrevive a fila, backoff ou máquina fria.

## 5. Dados

`WhatsAppCanal` já tem `waba_id` e `template_oferta` sem caminho de escrita
(`models_db.py:75-79`). Este projeto é esse caminho. Somam-se:

- `estado`: `pendente` | `ativo` | `falhou`
- `business_id` do cliente
- `elo_concluido`: até onde a cadeia chegou (para retomada)
- token da loja e PIN de duas etapas, **cifrados em repouso**

`evolution_instance` continua guardando o `phone_number_id`, como o §16.3 manda.
**Não renomear** — é a chave de roteamento do inbound nos dois modos e é `UNIQUE`, que é
a garantia de um número por loja.

## 6. Fluxo do lojista

```
sem_canal -> decidindo -> autorizando -> conectando -> pendente -> ativo
                                              |
                                              v
                                           falhou
```

**`decidindo`** é a tela do §16.4 e é a mais importante do projeto: é o único momento em
que o lojista toma decisão irreversível. Número novo, ou o que ele já anuncia — perdendo o
histórico do celular e virando bot-only para sempre. As três linhas do trade-off (histórico,
reconhecimento, CTWA) ficam na tela e o botão só acende depois da escolha. A escolha **é** o
aceite; não há "li e concordo".

Junto, a lista do que ele precisa ter em mãos: ser admin do portfólio empresarial, cartão
para a WABA, e o chip. Descobrir que não é admin dentro do popup é o pior lugar possível.

**`autorizando`** é o popup, com o `config_id` da configuração v4 do Facebook Login for
Business. Quem conduz a escolha do número, o SMS e a migração é a Meta.

**`conectando`** roda os elos e mostra progresso por elo, não spinner.

**`pendente`** mostra o que falta e de quem é: template em análise (Meta), meio de pagamento
(lojista), fila de vendedores (lojista, autoatendida) — e empurra para a fila, a única
acionável na hora. Diz que a liberação é da Revy, sem fingir que ele está no ar.

**`falhou`** nomeia o elo e o dono. O caso mais comum — número ainda ativo no aplicativo —
falha **dentro** do popup e pode não gerar evento nenhum; por isso `autorizando` precisa de
saída explícita de "não deu certo", nunca espera infinita.

## 7. A cadeia no servidor

| # | Elo | Retentável | Estado da informação |
|---|---|---|---|
| 1 | `code` -> token de negócio | **não** (TTL 30 s) | endpoint a confirmar |
| 2 | inscrever o app na WABA (`POST /{waba_id}/subscribed_apps`) | sim, idempotente | **verificado em produção 23/08** |
| 3 | registrar o número com PIN | sim | endpoint a confirmar |
| 4 | criar e submeter o template na WABA do cliente | sim | corpo fixado pelo §16.2 |
| 5 | gravar o canal `pendente` | sim | rota nova |

**Depois do elo 1 o popup nunca mais é necessário** — o token já está guardado. Falha do
elo 2 em diante retoma no servidor a partir de `elo_concluido`. Só o elo 1 devolve o
lojista ao popup.

**Os elos 2-4 são idempotentes de propósito.** `subscribed_apps` repetido não dói; número
já registrado e template já existente são **sucesso**, não erro. Tratá-los como falha
transforma retry inofensivo em laço.

**O elo 2 é o que precisa de teste dedicado.** É o que falhou calado na WABA da Revy em
23/08: sem ele, o teste do painel funciona e mensagem real nunca chega. Num fluxo
automático ele é invisível até um cliente sumir.

**Template.** `chama_vendedor`, `pt_BR`, `UTILITY`, uma variável, botão `[Peguei]`
(`QUICK_REPLY`). Tem de casar exatamente com `oferta_envio.py:74`, senão o envio falha.
Ficar em `UTILITY` é o que segura o custo: como `MARKETING` cada oferta custa ~10x.

**Aprovação do template chega por webhook**, assinando o campo
`message_template_status_update` — mesmo caminho que já existe, sem rota nova. É o que faz
o portão do Control mostrar status de verdade em vez de mandar olhar o painel.

## 8. Segredos

Token da loja e PIN cifrados em repouso, chave em secret nova. **Nunca** em rota de leitura
nem em log — a tela de números lista canais. O PIN é gerado por nós e guardado: o lojista
não tem uso para ele, e PIN perdido trava o re-registro do número.

**Efeito colateral bom:** hoje um token de System User da Revy alcança todas as lojas e, se
cair, derruba todas juntas (dívida do §16.7). Com token por loja, o raio da falha vira uma
loja. O §16.7 encolhe sozinho.

## 9. O portão do Control

Nenhum caminho de escrita novo. O Control já projeta `whatsapp_modo` para o chatbot, com
versionamento. "Liberar a loja" continua sendo só isso, e o chatbot ativa o canal `pendente`
quando a projeção chega dizendo `2`. Um lever, uma fonte.

O Control ganha **visão**: estado do canal, elo que falhou, status do template.

## 10. A metade que não é código

**Tech Provider:** aceite de termos, sem taxa. O degrau que costuma travar — verificação de
negócio da Revy — já está feito.

**App Review** de `whatsapp_business_messaging` e `whatsapp_business_management`, ambos em
Advanced. É documental e "screencast-driven". Pede **três** demonstrações, não uma:

1. o fluxo de signup,
2. **envio de mensagem**,
3. **criação de template**.

Turnaround médio ~24 h depois de submetido. O custo é montar a submissão, não esperar.

**A ordem é contra-intuitiva:** constrói-se contra um business de teste, grava, e só então
submete. Usuários de teste precisam de papel dev ou admin no app.

## 11. Testes

Suíte do `chatbot-api`: cada elo idempotente, retomada a partir de `elo_concluido`, e canal
saindo de `pendente` só pela projeção do Control.

Duas armadilhas já registradas se aplicam inteiras:

- **teste verde não prova que a feature existe** — foi assim que o Modo 2 foi entregue sem bot;
- **JS só se verifica no navegador** — o popup é JS; checagem no navegador com portal local,
  não só pytest.

Comandos, a partir da pasta do produto:
`.venv/bin/python -m pytest -q` (macOS) e `.\.venv\Scripts\python.exe -m pytest -q` (Windows).

**Ganho de brinde:** conectar **duas** lojas pelo fluxo é a primeira prova real do multi-loja,
consertado em 24/08 e nunca exercitado com mais de uma loja.

## 12. Riscos

| Risco | Mitigação |
|---|---|
| **Advanced Access negado** — mata o projeto inteiro; sem ele a WABA do cliente é intocável | Não há como reduzir antes de submeter, e não há como submeter antes de construir. Seguir a submissão-modelo da Meta ao pé da letra e contar com uma rodada de ida e volta |
| Sequência exata de chamadas dos elos 1 e 3 não confirmada | Spike contra o business de teste **antes** de virar task |
| Elo 2 falha calado | Teste dedicado; é o defeito que esta base já cometeu uma vez |
| Lojista perde o histórico sem ter entendido | A tela `decidindo` é requisito, não enfeite |

## 13. Fora de escopo / não re-propor

- Pôr número de cliente na WABA da Revy (recusado em 29/08).
- Solution Partner / faturar a mensagem junto da mensalidade (exige linha de crédito).
- Derivar `whatsapp_modo` do canal (decisão 4).
- Renomear `evolution_instance`.
- Embedded Signup v2.

## 14. Ordem de execução

Um eixo por vez, na ordem:

1. **Spike** da sequência exata de chamadas contra o business de teste (elos 1 e 3).
2. Cadeia no `chatbot-api` (rota, elos, dados, segredos).
3. Tela na Revy Loja (`decidindo` → popup → `conectando` → `pendente`).
4. Visão e portão no Revy Control.
5. Gravar as três demonstrações e submeter o App Review.

O spike vem primeiro porque o §16.5 marcou confiança "média" na sequência do passo 6, e a
conferência de 29/08 confirmou a forma, não todos os endpoints.
