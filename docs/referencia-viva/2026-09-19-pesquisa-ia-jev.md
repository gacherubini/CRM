# Pesquisa: IA "jev" — existe? dá pra plugar o Motor?

Pesquisa feita em 2026-09-19. Só fontes primárias (typesafe.ai e docs.typesafe.ai);
onde uso terceiro, está marcado como terceiro.

## Veredito

Existe: **Jev**, da TypeSafe AI, lançado em 15/09/2026, em early access ([blog oficial](https://typesafe.ai/blog/introducing-system-one-models-and-jev)).
Não dá pra plugar o Motor nele: Jev não é agente, não chama URL nenhuma e não tem tool use no sentido de invocar a sua API — ele só devolve decisão tipada, e quem executa é o seu código ([docs](https://docs.typesafe.ai/concepts/how-to-build-with-system-one.md)).
O único encaixe real seria o inverso do que foi perguntado: usar o Jev como classificador barato dentro do fluxo que *você* orquestra, com o `POST /v1/simulacoes` chamado pelo seu código como já é hoje.

## O que é

| Item | Valor | Fonte |
|---|---|---|
| Quem faz | TypeSafe AI, fundada por Diogo Almeida (ex-OpenAI) | [blog oficial](https://typesafe.ai/blog/introducing-system-one-models-and-jev) |
| O que é | Modelo transformer de uma nova categoria que eles chamam "System One". Não é LLM: não gera texto | [blog oficial](https://typesafe.ai/blog/introducing-system-one-models-and-jev) |
| Entrada / saída | "unstructured state in, typed probabilistic decisions out" — você define as saídas possíveis de antemão | [blog oficial](https://typesafe.ai/blog/introducing-system-one-models-and-jev) |
| Tipos de pergunta | `noul` (probabilidade 0–1), `choice` (uma opção de um conjunto fechado), `score` (nível numa régua ordenada) | [API reference](https://docs.typesafe.ai/api.md) |
| Lançamento | 15/09/2026 | [blog oficial](https://typesafe.ai/blog/introducing-system-one-models-and-jev) |
| Estado | Early access, com fila de espera | [blog oficial](https://typesafe.ai/blog/introducing-system-one-models-and-jev) |
| Modelo atual | `jev-1.13.0`, alias `jev-latest` | [models](https://docs.typesafe.ai/models.md) |
| API pública | `POST https://api.typesafe.ai/v1/systemone`, header `Authorization: Bearer <API_KEY>` | [API reference](https://docs.typesafe.ai/api.md) |
| Preço | US$ 0,042 por milhão de tokens de entrada; saída grátis | [blog oficial](https://typesafe.ai/blog/introducing-system-one-models-and-jev) |
| Limites | 64k tokens por request (32k para o `state` + a pergunta mais longa); 250 mil tokens/s e 1.200 req/min; só texto — sem imagem, áudio ou vídeo | [models](https://docs.typesafe.ai/models.md) |
| Latência | "Most queries complete in about 100 ms" | [how to build](https://docs.typesafe.ai/concepts/how-to-build-with-system-one.md) |

A frase que decide a pergunta do dono, da doc oficial:

> "System One is TypeSafe's model for building AI-powered software, not agents.
> It does not generate code or choose its own next action."
> — [how-to-build-with-system-one](https://docs.typesafe.ai/concepts/how-to-build-with-system-one.md)

E, no mesmo lugar: "Code handles deterministic work and owns the control flow."
O controle é do seu código, não do modelo.

## Como se integra com ferramenta externa

| Mecanismo | Existe? | Fonte |
|---|---|---|
| Tool use / o modelo chama uma URL HTTP sua | **Não.** A doc de "Function calling" é o modelo escolher *nome de função + argumentos de um conjunto fechado*; a execução é do seu código (`CALLS[command].run()` no exemplo). Nada de HTTP saindo do lado deles | [cookbook function calling](https://docs.typesafe.ai/cookbooks/function_calling.md) |
| Ferramenta definida pelo usuário no request da API | **Não documentado.** O request tem `state`, `model` e um mapa de `questions`. Não há campo de tools | [API reference](https://docs.typesafe.ai/api.md) |
| MCP oficial (remoto ou local) | **Não existe, nas duas formas.** O índice completo da doc (`llms.txt`) não tem página de MCP, e a org no GitHub tem 10 repos públicos — SDK Python, SDK JS, `skills`, infra — e nenhum servidor MCP | [llms.txt](https://docs.typesafe.ai/llms.txt), [github.com/typesafe-ai](https://github.com/orgs/typesafe-ai/repositories) |
| MCP de terceiro | Existe, e é **local (stdio, via `npx`)**, não remoto. E vai na direção **oposta**: expõe o Jev *como ferramenta para o seu agente*. As ferramentas que ele publica (`jev_verify`, `jev_classify`, `jev_decide`…) chamam só a API da TypeSafe sobre dados que o chamador já passou — não chamam URL arbitrária. Repo de comunidade, MIT, sem vínculo com a TypeSafe | terceiro — [github.com/jkudish/jev-mcp](https://github.com/jkudish/jev-mcp) |
| Webhook | **Não documentado.** Nenhuma página no índice | [llms.txt](https://docs.typesafe.ai/llms.txt) |
| Plugin / actions / custom connector | **Não documentado** | [llms.txt](https://docs.typesafe.ai/llms.txt) |
| "Agent skill" oficial | Existe, mas é outra coisa: uma skill para Claude Code/Codex que ensina o *seu agente de código* a usar a API da TypeSafe. Não é conector de runtime nem MCP | [agent skill](https://docs.typesafe.ai/agent-skill.md) |
| Streaming / async / polling / batch | **Não documentado** na API reference | [API reference](https://docs.typesafe.ai/api.md) |

Resumo do mecanismo: o Jev responde perguntas sobre um estado que **você já montou** e
devolve valores tipados com confiança. Ele nunca sai para buscar nada. Então a pergunta
"dá pra usar o Motor através do Jev" não tem onde se apoiar — não existe o passo em que
o Jev faz uma chamada de saída.

## Bloqueios para o caso do Motor

**Tarefa longa — o bloqueio decisivo.** Antes de tudo: o Jev não chama o Motor, então não
existe o passo em que ele esperaria. Mas mesmo se existisse, a escala está errada por
duas ordens de grandeza, e isso tem número oficial:

| | Valor | Fonte |
|---|---|---|
| Timeout padrão por operação HTTP do SDK | `DEFAULT_TIMEOUT = 10.0` segundos | [constants](https://docs.typesafe.ai/sdk/python/api/constants.md) |
| Orçamento padrão por chamada (tentativa inicial + retries + esperas) | 30,0 segundos | [retries](https://docs.typesafe.ai/sdk/python/api/retries.md) |
| Latência típica do Jev | "Most queries complete in about 100 ms" | [how to build](https://docs.typesafe.ai/concepts/how-to-build-with-system-one.md) |
| Async / polling / streaming / batch | **não documentado** | [API reference](https://docs.typesafe.ai/api.md) |

O Motor responde 202 e o resultado sai em 35 s a 136 s por banco, teto de 420 s, com
polling. Isso é 4x a 14x o orçamento inteiro de uma chamada do SDK, e 42x o teto contra o
timeout de 10 s por operação. O padrão do SDK é ajustável (`timeout=None` desativa o
limite), mas ajustar não resolve nada aqui: o modelo é de um passo, síncrono, sem primitivo
de tarefa longa nem de callback. Não há onde encaixar 202 + polling.

**Credencial bancária.** Como o Jev não chama o Motor, a credencial não chega perto dele —
esse risco some junto com a integração. O que sobraria, se um dia você mandasse `state`
para lá, é o de sempre com SaaS de terceiro: a doc legal diz que não treinam em dado de
usuário e que **zero data retention é só para cliente enterprise**, por contato com
`privacy@typesafe.ai` ([legal](https://docs.typesafe.ai/legal.md)). Onde o serviço roda,
self-host e VPC: **não documentado**.

**Exposição pública.** Não se aplica, e é o único ponto onde a notícia é boa: como não há
chamada de saída do lado deles, você não precisaria expor o `POST /v1/simulacoes` na
internet. O tráfego é sempre seu código → `api.typesafe.ai`. Se o Jev tivesse tool use, aí
sim a pergunta de host privado apareceria — e ela **não está documentada**, porque o
mecanismo não existe.

**Tamanho de entrada.** Se algum dia for usar o Jev para classificar resultado de
simulação, o teto é 64k tokens por request, 32k para o `state`, e só texto
([models](https://docs.typesafe.ai/models.md)).

## Fontes

Todas acessadas em 2026-09-19.

Primárias:

- <https://typesafe.ai/blog/introducing-system-one-models-and-jev> — anúncio oficial: quem faz, data (15/09/2026), early access, preço, "unstructured state in, typed probabilistic decisions out".
- <https://docs.typesafe.ai/llms.txt> — índice completo da documentação. Sustenta as ausências: sem MCP, sem webhook, sem batch, sem self-host, sem VPC.
- <https://docs.typesafe.ai/api.md> — endpoint `POST /v1/systemone`, auth Bearer, formato de request/response, códigos de erro, ausência de tools/streaming/async.
- <https://docs.typesafe.ai/concepts/how-to-build-with-system-one.md> — "not agents… does not choose its own next action", controle de fluxo no código, ~100 ms por query.
- <https://docs.typesafe.ai/cookbooks/function_calling.md> — o que a TypeSafe chama de function calling: escolher nome de função e argumentos de conjunto fechado, com a execução no código do desenvolvedor.
- <https://docs.typesafe.ai/agent-skill.md> — a skill oficial é para agente de código, com `claude plugin install typesafe@typesafe-ai`; não é MCP.
- <https://docs.typesafe.ai/models.md> — `jev-1.13.0`, 64k/32k tokens, só texto, rate limits, preço por Btok.
- <https://docs.typesafe.ai/sdk/python/api/constants.md> — `DEFAULT_TIMEOUT = 10.0` segundos por operação HTTP, `DEFAULT_BASE_URL = 'https://api.typesafe.ai'`, `DEFAULT_MODEL = 'jev-latest'`.
- <https://docs.typesafe.ai/sdk/python/api/retries.md> — orçamento padrão de 30,0 s por chamada cobrindo tentativa inicial mais retries; 2 retries; backoff exponencial 0,5 s → 5,0 s; `timeout=None` desativa o limite.
- <https://github.com/orgs/typesafe-ai/repositories> — os 10 repos públicos oficiais: SDK Python, SDK JS, `skills`, infra. Nenhum servidor MCP, o que sustenta "não há MCP oficial, nem remoto nem local".
- <https://docs.typesafe.ai/legal.md> — não treinam em dado de usuário; ZDR só enterprise via `privacy@typesafe.ai`.

Terceiro (citado só para mostrar que o MCP existente vai na direção oposta, e que é da comunidade):

- <https://github.com/jkudish/jev-mcp> — "Proof of concept MCP for Typesafe's new Jev AI model": stdio local via `npx`, dez ferramentas de julgamento que chamam só a API da TypeSafe. Expõe o Jev como ferramenta para o agente, não o contrário.
