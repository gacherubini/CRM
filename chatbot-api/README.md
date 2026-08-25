# Chatbot API

Leads, conversas, handoff, roteamento WhatsApp e as tools que o n8n chama. Fonte única de
verdade de conversas e mensagens. Chama Motor e Estoque por HTTP. Banco e migrations
próprios.

Domínio em `app/servico.py`; bootstrap e rotas em `app/main.py`.

## Armadilhas — leia antes de mexer

- **Nunca casar lead ↔ `ctwa_auditoria` por telefone mascarado.** São `***` + 4 dígitos.
  Testada contra o dado real em 08/08, a heurística casou o lead de uma venda com o anúncio
  de **outro cliente** (DDI/DDD e 6 últimos dígitos diferentes). O aviso está repetido em
  `scripts/diagnose_ctwa_sinais.py`.
- **Comparação de `ctwa_source_type` exige `casefold`.** O valor real em produção é
  `FB_Ads`, com maiúsculas; comparar sensível a caixa classifica 205 leads errado.
- **`origem = meta_ctwa` só para quem veio de anúncio** — identificador de anúncio ou
  `ctwa_source_type` em `FAMILIA_ANUNCIO`. O sinal cru (`ctwa_clid`, `meta_ad_id`,
  `ctwa_source_type`) é gravado **sempre**, sem guard. O guard decide se escreve, nunca
  apaga.
- **`FAMILIA_ANUNCIO` é duplicação consciente** com `portal-gestao/app/loja/sales_overview.py`
  — produtos diferentes, sem import entre eles. Mudou aqui, muda lá.
- **`Conversa` é única por `(canal_id, telefone)`**, com `canal_id` nullable: o mesmo
  cliente tem uma linha **por canal**. Qualquer busca por telefone tem de varrer todas e
  ordenar `criada_em ASC` — `aplicar_touch_ctwa` só grava os campos `_first` enquanto
  estão nulos, então o toque mais antigo precisa chegar primeiro.
- **O bot só responde pela instância por onde a conversa entrou.** Canal
  `desconectado`/`inativo` deixa a conversa órfã; **nenhum PATCH de estado resolve** — é
  preciso reconectar o canal por QR (Ajustes na Revy Loja) ou migrar a conversa.
- **Bot mudo em produção mas o chatbot e `/healthz` de pé? A causa costuma estar no n8n, não
  aqui.** Volume do `n8n2037` cheio → o webhook responde **500** (Evolution entra em backoff);
  ou n8n reiniciado há < ~6 min → webhook **404** (Evolution **cancela** o retry no 404).
  Diagnóstico e correção na seção `n8n2037` de `deploy/fly/3vm/README.md`.
- **Nunca ecoar payload inválido nem desligar o rate limit do webhook** em produção
  (`CHATBOT_WEBHOOK_MAX_*`, `CHATBOT_WEBHOOK_RATE_LIMIT_*`; corpo limitado a 32 KiB).
- **O LLM não escolhe identidade autorizada.** `telefone_solicitante` e `Idempotency-Key`
  vêm do webhook real, não do modelo.
- **A loja de um pedido do bot vem da `instance`, não do token.** O `n8n-cloud` é **um**
  workflow para N lojas (spec §6.2), então as rotas do bot chamam
  `auth.resolver_loja_id(db, ctx, instance)` em vez de ler `ctx.loja_id`. Três armadilhas
  ao migrar mais uma rota: **(a)** resolva **antes** de `_exigir_loja_operacional`, senão o
  gate responde `423` e engole o `400` que diz o erro de verdade; **(b)** rota que usa o
  `loja_id` para buscar um objeto estoura `AttributeError` (500) em vez de recusar; **(c)**
  se a rota não lê `ctx.loja_id`, `instance` ali é teatro — foi o caso de
  `GET /v1/config/catalogo-bot`, cega para loja pelo **contrato com o Estoque**.
- **`alembic upgrade head` não roda neste produto fora do Postgres.** A cadeia para na
  `0017` (`add_column` NOT NULL) com `NotImplementedError` do SQLite, **do zero** — não é o
  seu banco de dev fora de sincronia. Para conferir uma migration nova sem conectar em
  lugar nenhum, gere o SQL do dialeto de produção:
  `DATABASE_URL="postgresql+psycopg://u:p@localhost/x" .venv/bin/python -m alembic upgrade <anterior>:<nova> --sql`.
  Corolário: `batch_alter_table` aqui só serviria ao SQLite que a cadeia já não atende.
- **Não existe IA aqui dentro.** Nem Gemini, nem OpenAI, nem LangChain: o agente vive nos
  workflows do n8n, nos **dois** modos. Este produto expõe as ferramentas que ele chama.
  Foi confundir isso que deixou o Modo 2 sem bot por dois dias — havia rodízio, oferta e
  handoff, e ninguém respondendo o cliente.
- **Modo 2: `/webhook/cloud` devolve `mensagens[]`, e o n8n depende disso.** A assinatura da
  Meta só fecha sobre o **corpo cru**, então validar, deduplicar por `wamid` e persistir
  acontece aqui; o n8n recebe o evento já normalizado e segue no agente. Mudou o formato
  desse retorno? O bot do Modo 2 para. Ver
  [`docs/referencia-viva/design/2026-08-16-whatsapp-modo2-asbuilt.md`](../docs/referencia-viva/design/2026-08-16-whatsapp-modo2-asbuilt.md).
- **Modo 2 mudo com tudo "configurado"? Confira `subscribed_apps` da WABA.** Webhook
  verificado, campo `messages` assinado, token válido e **nenhuma mensagem chegando** é o
  sintoma de app não inscrito na WABA. Em 23/08 o único inscrito era o
  `WA DevX Webhook Events 1P App` — o app interno que o botão *Teste* do painel usa, e por
  isso o teste chegava e uma mensagem real não chegaria, sem erro em lugar nenhum.
  Diagnóstico e correção:

  ```bash
  curl -s "https://graph.facebook.com/v21.0/<WABA_ID>/subscribed_apps?access_token=$T"
  curl -s -X POST "https://graph.facebook.com/v21.0/<WABA_ID>/subscribed_apps" -d "access_token=$T"
  ```

  Vale para **toda WABA nova**, inclusive a de cada loja quando o §16.6 entrar. O app
  também precisa estar **Ao Vivo**: em Desenvolvimento a Meta só entrega webhook de teste.
- **Falha no inbound Cloud não pode virar só log.** Já respondemos `200` à Meta (§6.1), então
  ela **não reentrega**: engolir a exceção perde o lead calado. O corpo cru vai para
  `cloud_evento_falho` e o worker `cloud_retry` reprocessa (teto de 5 tentativas).
- **Áudio do Modo 2 passa por um gate de confiança pós-transcrição** (`app/audio.py`). O
  Whisper alucina frase plausível em trecho mudo ou com ruído, e o bot agiria em cima. O
  provider pede `response_format=verbose_json` e a transcrição é reprovada por
  `no_speech_prob > 0.6`, `avg_logprob < -1.0`, `compression_ratio > 2.4` (loop), frase da
  lista de legenda ("Legendas pela comunidade Amara.org") ou duração acima do teto — esta
  **depois** da transcrição, porque a Meta não manda duração no inbound. Reprovou, cai no
  fallback "manda por texto" de sempre. **Falha-abre de propósito:** provider que não devolve
  os sinais volta a ter o texto aprovado — bot surdo em silêncio numa troca de fornecedor
  seria pior. Não há VAD sobre o sinal, e não se adiciona dependência de áudio para isso.
  No log vai só o motivo (`transcrição reprovada motivo=...`), **nunca** o texto do cliente.
- **Ligar a transcrição são dois secrets, e o `model` não é um deles.** O Modo 2 transcreve
  assim que `CHATBOT_AUDIO_TRANSCRIPTION_URL` existir — `processador_de_audio` (`app/audio.py`)
  olha só a URL, não o `..._PROVIDER`, que é do Modo 1. Para o Groq:
  `CHATBOT_AUDIO_TRANSCRIPTION_URL=https://api.groq.com/openai/v1/audio/transcriptions` e
  `CHATBOT_AUDIO_TRANSCRIPTION_TOKEN=<chave>`. O `model` é **obrigatório** no Groq, e por isso
  tem default no código (`whisper-large-v3`) em vez de vazio: esquecê-lo daria 400 em todo
  áudio e um bot que parece apenas não ouvir. Trocar para `whisper-large-v3-turbo` é só
  `CHATBOT_AUDIO_TRANSCRIPTION_MODEL`. O Groq cobra **no mínimo 10 s** por chamada, então um
  "oi" de 2 s custa como 10 s — irrelevante no volume do piloto, não em campanha.
- **Portfólio verificado desde 24/08 — e isso não destrava nada aqui.** A verificação da
  empresa (CNPJ) saiu `Verificada` em 24/08/2026, um dia depois de submetida. Ela **não**
  muda limite: o teto de 250 clientes únicos/24h da conta não verificada já contava **só
  conversa iniciada pela empresa**, e o funil é CTWA (inbound), que roda inteiro dentro da
  janela do cliente. O que ela compra é **nome de exibição**, **mais de 2 números** (a
  terceira loja) e disparo para a base — os três inúteis enquanto o número for o de teste
  da Meta. Não planeje nenhum passo do Modo 2 como "agora que estamos verificados".

## Configuração do agente por loja

Desde 25/08 o `chatbot-api` guarda, versiona e serve **o prompt do agente de cada loja**.
Antes disso existia um agente só, com `vitor motos` escrito à mão dentro do
`n8n/workflow-ai-nao-salvos.json` — a segunda loja se apresentaria como a primeira.

**Os quatro cards estão no código. O cliente não sente nenhum deles ainda.**

| Card | O que é | Onde | Em produção? |
|---|---|---|---|
| 1 · dado e texto | gerador, núcleo, tabelas, migration `0027`, rotas | `chatbot-api` | **sim** (25/08) — as rotas existem e ninguém as chama |
| 2 · n8n | slot no `systemMessage`, nó de config, fallback, assertivas migradas | `n8n` | não |
| 3 · tela | formulário, rascunho, publicar, histórico | `portal-gestao` | não |
| 4 · preview | workflow gerado, modo seco, telefone sintético | `n8n` + `chatbot-api` | não |

O `app2037` de hoje já tem a migration `0027` e as cinco rotas do card 1; o que falta
deployar dele são os **ajustes** que os cards 2–4 trouxeram (o campo `saida` e o `modo`
nas rotas, a rota de preview, e as correções do gerador). O `n8n2037` ainda roda o
workflow anterior, com `vitor motos` escrito à mão. Ver "O que foi feito" e "O que
falta", no fim desta seção.

Spec: [`../docs/referencia-viva/specs/2026-08-24-agente-por-loja-design.md`](../docs/referencia-viva/specs/2026-08-24-agente-por-loja-design.md).

### Onde mora o quê

| Coisa | Onde |
|---|---|
| Campos do formulário | `agente_config_versao.campos` (JSON) |
| Texto final do prompt, congelado | `agente_config_versao.prompt_gerado` |
| Qual versão está no ar | `agente_config.versao_publicada_id` |
| Núcleo Revy (regras que o lojista não edita) | `app/agente_prompt.py`, em **código**, não em dado |
| Geradores de texto por campo | `app/agente_prompt.py` |
| Rascunho, publicar, restaurar, histórico | `app/agente_config.py` |
| Rotas | `app/main.py`, prefixo `/v1/agente` |

O prompt é **montado uma vez, no `salvar_rascunho`**, e congelado em `prompt_gerado`.
`GET /v1/agente/config` faz um `SELECT`, não remonta. Isso é o que permite auditar o texto
que o bot recebeu naquela versão — melhorar o gerador amanhã não reescreve o histórico.

### Rotas

| Rota | Papel |
|---|---|
| `GET /v1/agente/config` | o que o n8n consome: prompt + `max_output_tokens` + `agente_ativo` + `saida` |
| `GET` / `PUT /v1/agente/rascunho` | a tela edita aqui; devolve `campos`, `prompt`, `conflitos` e `modo` |
| `POST /v1/agente/publicar` | leva o rascunho ao ar |
| `GET /v1/agente/versoes` | histórico |
| `POST /v1/agente/versoes/{id}/restaurar` | traz uma versão antiga **para dentro do rascunho** |
| `POST /v1/agente/preview` | um turno de conversa com o agente do **rascunho**, sem WhatsApp |

### Armadilhas desta feature

- **O núcleo Revy é o último bloco do prompt, sempre.** É o mecanismo de segurança
  inteiro: o lojista escreve os cinco blocos de cima, e o núcleo vem depois dizendo que
  nada acima pode contradizê-lo. Não é confiança no lojista, é ordem de leitura. Se
  alguém acrescentar qualquer coisa depois dele — rodapé, marca d'água, debug — a
  proteção acabou. Há teste no nível do serviço **e** no nível HTTP guardando isso.
- **`restaurar` sobrescreve o rascunho em andamento.** Ele não cria versão nova: carrega
  os campos da versão antiga para dentro da linha de rascunho que já existe. Nenhuma
  versão publicada ou arquivada é alterada. A tela precisa avisar antes.
- **`GET /v1/agente/rascunho` escreve.** Para loja sem rascunho, `obter_rascunho` cria a
  linha e commita. Um GET não idempotente — de propósito, mas surpreende.
- **Só existe um rascunho por loja, e há índice único parcial garantindo isso**
  (`uq_agente_config_versao_rascunho_por_loja`, restrito a `estado = 'rascunho'`). Ele é
  **parcial** porque um `UniqueConstraint(loja_id, estado)` simples proibiria duas versões
  `arquivada` da mesma loja — ou seja, mataria o histórico. Sem esse índice, duas linhas de
  rascunho fazem o `PUT` escrever numa e devolver outra, e o `publicar` seguinte põe no ar
  um texto que o lojista não escreveu.
- **Os campos de escolha são `Literal`, não `str`.** Já foram `str`, e um espaço a mais
  vindo do formulário (`"so_quando_pedir "`) caía no `else` e **invertia o comportamento**
  em silêncio — o bot passava a mandar foto na abertura. Hoje isso é 422. Ao acrescentar
  opção nova, mude o `Literal` **e** o dicionário gerador juntos.
- **`horario` é validado na forma: `HH:MM` com zero à esquerda, sempre 2 valores.**
  `esta_em_horario` compara string, então `"8:00" <= "14:00"` é `False` — sem a validação,
  uma grade sem zero à esquerda deixa o bot mudo o dia inteiro, sem log e sem erro.
- **Fuso fixo `America/Sao_Paulo`.** A tabela `lojas` não tem coluna de timezone. Vira
  coluna quando existir loja fora do fuso de Brasília, não antes.
- **O modelo de LLM e o teto de tokens são globais**, não por loja (decisões do dono,
  25/08). Não existe coluna `modelo`, nem rota para trocá-lo, e `maxOutputTokens` fica em
  250 para todas as lojas. O campo "tamanho da resposta" é por loja, mas age pelo **texto
  do prompt**, não por parâmetro do n8n — 250 tokens são ~175 palavras, que já é bem mais
  do que qualquer resposta de WhatsApp deste bot. O teto fixo é a rede que impede resposta
  descontrolada; o sinal de que ele não bastou seria **resposta cortada no meio da frase**
  em produção. A rota `GET /v1/agente/config` **continua devolvendo** `max_output_tokens`, e
  ele varia mesmo (250/400/700) — o que não varia é o que o n8n aplica, que segue sendo o
  250 fixo do nó. O valor fica ali informativo, pronto para o dia em que o teto por loja
  se justificar.
- **A trava contra endereço inventado só sai quando existe endereço.** `endereco_completo`
  sozinho não desliga nada: sem `endereco` preenchido o gerador mantém "não informe rua,
  número, bairro nem ponto de referência". Marcar a opção e deixar o campo vazio deixava o
  agente sem endereço **e** sem a trava — livre para inventar rua e número.
- **`oferece` não pode ser lista vazia (422).** O gerador diz ao cliente o que a loja
  **não** faz; com zero marcado ele passava a afirmar que a loja não faz financiamento,
  nem à vista, nem troca, nem consignação. Ninguém notaria até um cliente reclamar.
- **O prompt padrão existe em dois lugares.** Aqui, em `montar_prompt(CAMPOS_PADRAO_REVY)`,
  e como constante JS dentro do nó `Gate config do agente1` (o fallback do n8n). Mudou o
  gerador? `python -m scripts.sincronizar_fallback_n8n`, e regere os três workflows
  derivados. `tests/test_agente_prompt_fallback_do_n8n.py` reprova a divergência.
- **`tests/snapshots/agente_prompt.txt` guarda o texto inteiro** em sete combinações,
  incluindo as feias. Mudou de propósito? confira o diff e regenere com
  `python -m tests.test_agente_prompt_snapshot`. Foi ele que achou os dois campos
  perigosos acima — assertiva por frase não pegaria nenhum dos dois.
- **`pode_responder` passou a consultar `agente_config`.** É o caminho quente: toda
  mensagem de cliente passa por lá. Loja que nunca configurou nada cai no padrão Revy com
  `agente_ativo=True` e continua respondendo — há teste explícito para isso, porque
  quebrar essa invariante deixa o bot mudo em produção, em silêncio.

### Como o n8n consome (card 2)

O `systemMessage` do `AI Agent1` virou **expressão**: a operação do atendimento (jornada,
ferramentas, anti-alucinação) continua literal no JSON, e a última coisa da mensagem é o
prompt desta loja — que termina no núcleo Revy. **A ordem é o mecanismo de segurança
inteiro**: `validate_workflow.py` reprova qualquer coisa colada depois do slot.

Dois nós novos, entre o debounce e o agente:

| Nó | Papel |
|---|---|
| `Buscar config do agente1` | `GET /v1/agente/config?instance=…`, com `fullResponse` + `neverError` |
| `Gate config do agente1` | 200 → prompt da loja · **423 → para o fluxo** · resto → padrão Revy |

- **423 não cai no fallback.** Loja suspensa responde 423, e tratar isso como "falhou, usa
  o padrão" deixaria a loja suspensa sendo atendida pelo bot — contra o gate de backend do
  `AGENTS.md` §5. Só falha técnica (timeout, 5xx, rede) cai no padrão.
- **O fallback é uma cópia** de `montar_prompt(CAMPOS_PADRAO_REVY)` dentro do `jsCode`.
  `tests/test_agente_prompt_fallback_do_n8n.py` compara os dois e reprova a divergência;
  a correção é `python -m scripts.sincronizar_fallback_n8n`, nunca editar o nó à mão.
- **A higienização da saída passou a obedecer a loja.** O `Responder WhatsApp1` forçava
  minúsculas e removia emoji de toda resposta de cliente. Se continuasse incondicional,
  `escrita` e `emoji` seriam campos decorativos — por isso a rota devolve `saida`.
- **Os dois nós estão em `HERDADOS`** no `fork_cloud_workflow.py`. O gerador reclama de nó
  que sumiu do Modo 1, nunca de nó que ele deixou de copiar.
- **Loja que já atendia precisa de config antes do deploy do workflow**, senão estreia com
  o padrão Revy: `python -m scripts.semear_config_agente moto-center` (spec §11).
  **O slug é `moto-center`**: é assim que a loja do piloto está gravada, embora o nome
  que o cliente ouve seja "vitor motos". Conferido no Postgres de produção em 25/08.

O `modo` do rascunho existe porque o formulário esconde o que não existe do lado dele
(spec §4.4.1): não há tool de foto no Modo 2, nem worker de follow-up no Modo 1. Quem sabe
o modo é este produto — a Loja reimplementar o gate seria divergir dele na primeira
mudança.

### O preview (card 4)

`POST /v1/agente/preview` monta o pedido e chama o webhook `whatsapp-ai-preview` do
n8n (`CHATBOT_AGENTE_PREVIEW_URL`). Quem roda o agente é o n8n — **não existe IA neste
produto**; o papel daqui é de porteiro.

- **O telefone é sintético e nasce aqui** (`agente_preview.telefone_sintetico`), nunca
  vem da tela. Começa em `0`, então não é MSISDN nenhum. `consultar_estoque` guarda a
  moto escolhida chaveada por telefone: o lojista testando com o próprio número
  sobrescreveria uma conversa real. A rota **recusa** `telefone` no corpo (422).
- **O prompt é o do rascunho**, não o publicado. Testar o publicado não serviria para
  nada: o lojista está justamente decidindo se publica.
- **`AGENTE_PREVIEW_URL` vazio responde 503** e o rascunho devolve
  `preview_disponivel: false`, para a tela esconder o botão em vez de oferecer um teste
  que sempre falha.
- **Timeout de 45 s**, generoso de propósito: o agente encadeia consulta ao estoque e
  ainda pensa. Curto demais mostra "o preview não respondeu" para um agente que
  respondeu — e o lojista conclui que a configuração dele está errada.
- **O modo seco das ferramentas é guardado por dois testes, e são dois de propósito.**
  `n8n/validate_preview_workflow.py` confere a ordem no texto; `n8n/test_modo_seco.js`
  **executa** cada ferramenta no caminho feliz e afirma que nenhuma chamada que age
  acontece. Ordem não é execução: um `return` dentro de um `if` passa no primeiro e
  reprova no segundo — conferido por mutação.

### O que foi feito

Neste produto: o gerador de prompt e o núcleo (`app/agente_prompt.py`), as versões
(`app/agente_config.py`), as seis rotas `/v1/agente`, o porteiro do preview
(`app/agente_preview.py`), o gate por loja dentro do `pode_responder`, e dois scripts —
`semear_config_agente` (a config que reproduz o prompt de hoje) e
`sincronizar_fallback_n8n`.

Nos outros: o slot e os dois nós no n8n, o workflow de preview gerado, e a tela em
`/app/loja/agente/configuracao`. Os READMEs de `portal-gestao/` e `n8n/GUIA-WORKFLOW.md`
contam o lado deles.

### O que falta

**Só operação — nenhuma linha de código.** Os cards 2–4 não foram deployados, por
decisão do dono (25/08): ele quer acompanhar o passo que muda o que o cliente ouve.

| # | Passo | Muda o que o cliente ouve? |
|---|---|---|
| 1 | `fly deploy` do `app2037` | **não** — sobe os ajustes dos cards 2–4 nas rotas, e ninguém as chama. Sem migration nova: a `0027` já está aplicada |
| 2 | `DATABASE_URL=$CHATBOT_DATABASE_URL python -m scripts.semear_config_agente moto-center`, por `fly ssh console -a app2037` em `/srv/chatbot` (a variável é `DATABASE_URL`: é ela que o `app/db.py` lê, e num shell avulso o entrypoint não traduziu) | **não** — só o `pode_responder` lê `agente_config` hoje, e a config semeada é equivalente ao estado atual (`agente_ativo` ligado, sem janela de horário) |
| 3 | `prepare-workflow.ps1 -Mode production` + `upload-and-import` + restart | **sim** — é aqui que o bot passa a montar o prompt a partir da config |
| 4 | secret `REVY_LOJA_AGENTE_CONFIG_ENABLED=1` | libera a tela para o lojista |
| 5 | `-Mode preview` + secret `CHATBOT_AGENTE_PREVIEW_URL` | libera o botão Testar |

**A ordem 1 → 2 → 3 não é preferência.** Workflow subindo antes da rota busca o que não
existe (por isso o fallback), e antes da semente a vitor motos estreia se apresentando
como "loja". Sequência completa na skill `revy-deploy`.

**Teste de aceite do passo 3:** a vitor motos **não muda de jeito de falar**. Se mudar, é
bug — reverte republicando o workflow anterior.

Fora da v1, com motivo registrado no spec e na
`decisoes/2026-08-25-agente-por-loja-o-que-ficou-de-fora.md`: cadência de follow-up por
loja (§4.4.2), `só lead de anúncio` (§4.6, depende de atribuição CTWA confiável), e tela
no Control para trocar modelo (§7, o modelo é global).

A dívida herdada que encostava nesta feature — `GET /v1/config/catalogo-bot` cega para
loja — **foi resolvida em 25/08**, com o dono escolhendo expor `catalogo_url` na rota
pública por slug do Estoque. Ver §8 do spec e
[`../docs/referencia-viva/planos/2026-08-25-catalogo-por-loja.md`](../docs/referencia-viva/planos/2026-08-25-catalogo-por-loja.md).

## Rodar e testar

```bash
cd chatbot-api
.venv/bin/python -m pytest tests -q         # `pytest -q` da raiz não coleta: ver abaixo
```

`pytest -q` sem o `tests` estoura `PermissionError` no scandir por causa de dois
diretórios órfãos (`test-tmp-run4/`, `test-tmp-run5/`). No Windows:
`.\.venv\Scripts\python.exe -m pytest tests -q`.

`alembic upgrade head` **não roda aqui sem Postgres** (armadilha acima). Confira uma
migration nova pelo SQL offline, e `alembic heads` para achar a head.

Testes que cobrem os pontos sensíveis:

- `tests/test_whatsapp_outbound.py` — `send_text`: sucesso, classificação dos codes e
  **sanitização do log** (CPF/nascimento redigidos, apikey nunca vaza).
- `tests/test_solicitacoes_simulacao.py` — pedido de simulação humana: maioridade,
  CNH objetiva (sim/não), dedupe por telefone/CPF, qualifica lead, pausa bot,
  enfileira/reenvia alerta, reprocessa dead-letters.
- `tests/test_whatsapp_provider_evolution.py` — provisionamento/estado das instâncias
  (connect/QR, status, logout) sem vazar URL/apikey.
- `tests/test_fluxo_modo2_ponta_a_ponta.py` — atravessa webhook → gatilho → oferta → clique
  → trava. Existe porque os testes unitários passavam com o produto morto: cada função tinha
  teste chamando ela direto e ninguém percorria "chega mensagem → o rodízio começa".
- `tests/test_cloud_retry.py` — o "processar depois" da §6.1, incluindo o teto de tentativas.

## Rotas do Modo 2 que o `n8n-cloud` chama

O agente do Modo 2 vive no `n8n/workflow-cloud.json` (gerado — ver
`n8n/fork_cloud_workflow.py`). Estas são as portas que ele usa aqui:

| Rota | Papel |
|---|---|
| `POST /webhook/cloud` | inbound da Meta; confere assinatura no corpo cru, deduplica por `wamid`, persiste e **devolve `mensagens[]`** para o agente seguir |
| `GET /webhook/cloud` | verificação do webhook da Meta (`hub.challenge`) |
| `POST /v1/operacao/responder` | saída do bot. Existe porque o token do Graph **não pode entrar no workflow** (spec §6.2) |
| `POST /v1/operacao/handoff-humano` | 3º gatilho da §5.2. Sem CPF/nascimento de propósito — "pediu humano" pode vir antes da simulação |

**Toda chamada do bot carrega `instance`** (o `phone_number_id`, que o nó `Extrair1` do
workflow publica). Credencial de **loja** segue mandando o corpo de hoje, sem o campo;
credencial de **integração** (`papel="integracao"`, criada por
`python -m app.cli criar-credencial-integracao`) não tem loja e é **`400` sem `instance`** —
fail-closed de propósito, porque cair em "alguma" loja mandaria a mensagem de uma pela
outra. Quem exige o campo do lado do n8n é `validate_workflow_cloud.py`.

| Rota | Onde vai o `instance` |
|---|---|
| `POST /v1/conversas/{tel}/pode-responder` | corpo, **obrigatório** desde sempre |
| `POST /v1/operacao/responder` | corpo |
| `POST /v1/operacao/handoff-humano` | corpo |
| `POST /v1/operacao/moto-escolhida` | corpo |
| `POST /v1/operacao/solicitacoes-simulacao-humana` | corpo |
| `POST /v1/simulacoes/solicitar` | corpo |
| `GET /v1/estoque/buscar` | query |
| `GET /v1/config/catalogo-bot` | **não recebe** — é cega para loja por outro motivo |

Workers do Modo 2 (`app/modo2_workers.py`, todos atrás de `MODO2_ENABLED`): `rodizio`
(expira oferta), `followup` (30 min + 1 h) e `cloud_retry` (reprocessa inbound que falhou).

## Gates antes do alerta de simulação

`POST /v1/operacao/solicitacoes-simulacao-humana` só envia ao grupo depois de, nesta ordem:

1. **Nascimento válido + maioridade** (`>= 18` em `America/Sao_Paulo`). Menor retorna
   HTTP 200 com `bloqueado=true`, `motivo_bloqueio=menor_de_idade` e a mensagem fixa ao
   cliente — sem lead/pausa/alerta.
2. **CNH objetiva** (`sim` ou `não`). Resposta vaga → `motivo_bloqueio=cnh_nao_confirmada`
   e `faltando: ["cnh"]` (sem envio). **Não ter CNH não bloqueia**: `não`/`não tenho`
   é confirmação válida e a solicitação segue para o grupo com `CNH: NÃO`.
3. **Dedupe**: mesma `Idempotency-Key`, ou solicitação recente do mesmo telefone/CPF
   (janela `CHATBOT_SIMULACAO_DEDUPE_HORAS`, default 48h) → reutiliza o atendimento e
   **não** reenvia o alerta.

Todo bloqueio grava `motivo_bloqueio` no log (`simulação bloqueada motivo=...`) e no body.

## Alerta de simulação ao grupo de estoque

Código F0–F3 pronto (2026-08-13): tabela `notificacoes_operacionais`, worker
`notificacoes_outbox_job` no lifespan, dead-letter após `CHATBOT_NOTIF_MAX_ATTEMPTS`.
Residual é smoke do workflow, não implementação.

Quando um cliente pede financiamento (após os gates), o bot pausa a conversa e envia
**"🚨 precisa de simulação humana"** ao grupo de estoque (`solicitacoes_simulacao.py`). Se
esse envio falha, o cliente fica preso em `handoff` **e ninguém fica sabendo** — o sintoma
é "o bot parou de responder" para aquele cliente.

O envio grava em `notificacoes_operacionais` (outbox): `status`, `attempts`,
`last_error_code`, `next_attempt_at`. O drenador (`processar_pendentes`) reprocessa
`pending`/`failed` com `attempts < MAX_TENTATIVAS_ALERTA`; ao esgotar vira **dead-letter**
(`next_attempt_at = NULL`) e **não reprocessa mais**.

| `last_error_code` | Significa | Ação |
|---|---|---|
| `evolution_group_forbidden` | instância **não é participante** do grupo | readicionar o número ativo ao grupo |
| `evolution_target_not_found` | grupo/JID não existe para essa instância | corrigir o `destino_jid`/grupo da loja |
| `evolution_send_failed` (HTTP 5xx) | erro transitório do Evolution | normalmente resolve no retry |
| `evolution_unreachable` | não conectou no Evolution | rede/URL do Evolution |
| `grupo_estoque_nao_configurado` | loja sem grupo configurado | configurar o grupo de estoque |

Diagnóstico:

```bash
fly logs -a app2037 | rg "sendText falhou|alerta simulação"    # corpo já sanitizado
```

```sql
SELECT loja_id, status, attempts, last_error_code, next_attempt_at, created_at
FROM notificacoes_operacionais
WHERE tipo = 'simulacao_humana' AND status <> 'sent'
ORDER BY created_at DESC;
```

Para reprocessar **um** dead-letter, zere `attempts`, ponha `next_attempt_at = NULL` e
`status = 'pending'` no id escolhido; o worker (`notificacoes_outbox_job`, ligado no
lifespan) reenvia no ciclo seguinte. ⚠️ Isso **reenvia o alerta real ao grupo**, com a PII
daquele cliente — prefira o registro mais recente.

---

Histórico (origem CTWA honesta, tracking pendente multi-canal, desmascaramento do erro do
Evolution): [`../docs/nao-plano/historico/chatbot.md`](../docs/nao-plano/historico/chatbot.md).
