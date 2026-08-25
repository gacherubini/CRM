---
gatilho: escrever ou revisar script de operacao que aponta para uma loja por slug
produto: chatbot-api
custo: o passo de rollout para em "loja nao existe", e seguir sem ele estreia a loja com o prompt padrao
fonte: infra
verificado_em: 2026-08-25
---
# A loja do piloto se chama `moto-center` no banco e "vitor motos" no prompt

`scripts/semear_config_agente.py` existe para uma coisa só: pôr no ar, antes do
workflow, a config que reproduz o prompt que a loja do piloto já usa. Ele nasceu com
`CAMPOS_POR_SLUG = {"vitor-motos": ...}` — o nome que aparece no `systemMessage`, no
spec, nos READMEs e em todos os testes.

**Em produção não existe loja `vitor-motos`.** O Postgres do chatbot tem duas linhas:
`moto-center` (nome `Moto-Center`, instância `moto-center-48a9`, WhatsApp com DDD 19,
**1.235 conversas**) e `teste`. `moto-center` é slug de exemplo herdado do plano de
deploy de julho de 2026, e ficou. É para essa linha que o `CHATBOT_API_TOKEN` do
workflow do Modo 1 aponta — conferido resolvendo o hash do token contra
`credenciais_servico`.

O efeito: o passo 2 do rollout do agente por loja pararia com "loja não existe", e
quem seguisse para o passo 3 poria a loja de 1.235 conversas para se apresentar como
*"você atende os clientes da a loja"* — exatamente o teste de aceite que o script foi
escrito para proteger.

**A regra:** o nome que o produto usa para uma loja (prompt, spec, conversa com o
dono) e a chave que o banco usa não são a mesma coisa, e a distância entre os dois só
aparece consultando produção. Script de operação que grava por slug, cargo, e-mail ou
instância se confere **contra o banco**, não contra o texto que o descreve. A suíte
inteira ficou verde o tempo todo: nenhum teste podia saber quais lojas existem lá.

Hoje o script aceita os dois slugs, recusa banco SQLite quando só
`CHATBOT_DATABASE_URL` está definido (ver [[2026-08-23-alembic-mente-sem-database-url]])
e, quando não acha a loja, **lista as que existem** — para o operador não ficar preso
sem saber o que perguntar.

Ver [[2026-08-23-teste-verde-nao-prova-que-a-feature-existe]].
