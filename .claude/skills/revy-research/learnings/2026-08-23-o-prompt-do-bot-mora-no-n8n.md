---
gatilho: mudar o prompt do bot, o tom da IA ou o que ela pode responder
produto: n8n
custo: um deploy do bundle inteiro sem efeito nenhum
fonte: repo
verificado_em: 2026-08-25
---
# Metade do prompt do bot nao esta no chatbot-api

**Atualizado em 25/08:** desde o agente por loja o prompt tem duas metades. A
**operacao do atendimento** (jornada, tools, anti-alucinacao) continua literal em
`n8n/workflow-ai-nao-salvos.json`; a **identidade, o tom e as regras da loja**, mais o
nucleo Revy, sao gerados em `chatbot-api/app/agente_prompt.py` e entram por um slot no
fim do `systemMessage`. Qual metade voce quer mudar decide onde mexer — e a ordem
entre elas e o mecanismo de seguranca: ver
[[2026-08-25-o-prompt-e-metade-template-metade-dado]].

O que continua valendo: nao existe **IA** dentro do `chatbot-api` (sem gemini/openai/
langchain). O agente roda no n8n nos dois modos; o produto gera texto e expoe as tools.

Consequencia no deploy, e ela tambem virou dupla: mexer na **operacao** e deployar o
`app2037` nao muda nada — o alvo e o **n8n2037**, com a sequencia de
`2026-08-23-import-do-n8n-desativa-o-workflow.md`. Mexer no **gerador de texto da
loja** e o contrario: e deploy do `app2037`, e o bot muda na proxima mensagem, sem
tocar no n8n.

O canonico e gerado: nao editar o `*.ready.json`, e no Modo 2 nao editar o
`workflow-cloud.json` a mao (ver `2026-08-23-workflow-cloud-e-gerado.md`).

## O `validate_workflow.py` prende o prompt por frase literal

Mexer no `systemMessage` não é só editar JSON: `n8n/validate_workflow.py:121` em diante
afirma **frases literais** do texto — "privacidade do resultado", "nunca crie lead
por cumprimento", "mande as fotos do catálogo ou prefere", "não exija foto antes",
"recusa e não insistir", "nunca peça placa ao cliente". Reescrever uma delas deixa o
validador vermelho, e ele é gate do `AGENTS.md` §6.

Isso é proteção, não estorvo: foi o que já pegou regressão de prompt. **Nunca apague uma
assertiva para o validador passar** — mova a garantia para onde o texto foi morar (teste
de snapshot, se o texto virou dado) e deixe registrado o destino.

## As tools do agente dependem do nó `Extrair1`

Elas não são nós HTTP: são `toolCode` (JS) que chamam `http://chatbot-api:8000/...` com
`Bearer __CHATBOT_TOKEN__`, e **todas** leem `$('Extrair1').first().json` para achar
`instance` e `telefone`. Qualquer workflow novo que reaproveite as tools precisa de um nó
com esse nome exato — foi assim que o fork do Modo 2 se consertou, com nó-ponte.

E `consultar_estoque1` **não é só leitura**: com resultado único ela grava a moto
escolhida no CRM (`POST /v1/operacao/moto-escolhida`), chaveada por telefone. Workflow de
laboratório que use telefone real corrompe conversa real.
