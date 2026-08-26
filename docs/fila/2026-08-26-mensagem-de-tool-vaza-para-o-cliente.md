# A mensagem interna da tool vaza para o cliente

**Status:** diagnóstico + proposta. Nada foi editado. Nenhum workflow foi publicado.
**Produto:** n8n (`workflow-ai-nao-salvos.json`) + `chatbot-api` (`app/agente_prompt.py`).
**Data:** 26/08/2026.

## O sintoma

Produção, loja `moto-center`, 26/08 00:00:59 UTC. O bot mandou ao cliente:

> "a moto ainda não foi escolhida. volte ao catálogo e pergunte somente qual moto o
> cliente quer..."

Isso é instrução escrita **para o modelo**. O cliente leu o roteiro do bot.

A conversa: entrada por anúncio → "financiamento" → "quando fica por mês" → o bot pediu
cpf/nascimento/cnh → o cliente mandou os três (`*********88`, `16/02/2009`, `não tenho`)
→ veio a instrução crua.

**Não é regressão de hoje.** No banco de produção: 22 ocorrências de "ainda não foi
escolhida" desde 06/08 e 9 de "volte ao catálogo" desde 10/08. A frase entrou no
workflow em `78369de` (03/08, "promove jornada de catálogo ao workflow oficial"); o
primeiro vazamento é três dias depois. O defeito é anterior ao agente por loja e
**sobreviveu a ele** — porque o agente por loja repetiu a mesma instrução ambígua no
núcleo Revy (ver §1.3).

---

## 1. Mecanismo

### 1.1 Onde a frase nasce

`n8n/workflow-ai-nao-salvos.json:291` — `jsCode` do nó `simular1`, linhas 85–91 do
código:

```js
const temVeiculoInterno = Boolean(placa) || (temValorEstoque && categoriaValida);

if (!temVeiculoInterno) {
  return JSON.stringify({
    ok: false,
    precisa_escolher_moto: true,
    mensagem: 'a moto ainda não foi escolhida. volte ao catálogo e pergunte somente qual moto o cliente quer conhecer melhor. não fale em simulação e não peça cpf, nascimento, entrada ou placa agora. NÃO diga certinho nem que vai preparar simulação.',
  });
}
```

O ramo dispara quando a tool não conseguiu recuperar a moto por **nenhum** dos caminhos
de recuperação (linhas 41–79 do mesmo `jsCode`):

1. `$getWorkflowStaticData('global')['moto-escolhida:' + telefone]` — só existe se
   `consultar_estoque1` já rodou nessa conversa **e** a busca voltou exatamente 1 veículo
   (`n8n/workflow-ai-nao-salvos.json:280`, `veiculos.length === 1`);
2. `origem.motoEscolhida || origem.moto_escolhida` (linha 46) — **caminho morto**:
   `origem` é `$('Extrair1').first().json`, e o `return` do `Extrair1`
   (`n8n/workflow-ai-nao-salvos.json:31`, linhas 94–103) não emite nenhum desses campos.
   O mesmo vale para `origem.cpfCliente` na linha 17. São dois fallbacks que nunca
   executam;
3. reconsulta a `/v1/estoque/buscar` pelo `interesse` que o modelo passou — só salva se
   voltar exatamente 1 veículo.

Ou seja: **na prática existem dois caminhos, não três**, e ambos dependem de uma busca
de estoque com resultado único.

### 1.2 Qual instrução faz o agente repassar em vez de agir

O defeito não é a frase — é o **contrato do payload**. A tool usa a mesma chave
`mensagem` para duas coisas incompatíveis:

| Ramo do `simular1` (linha do `jsCode`) | O que `mensagem` é |
|---|---|
| 89 — `precisa_escolher_moto` | **instrução ao modelo** |
| 134/135 — `faltando` (cnh / outros) | **instrução ao modelo** |
| 146 — `menor_de_idade` | **texto do cliente**, literal por design |
| 166, 235, 240 — falha técnica | **instrução ao modelo** |
| 222 — sucesso | **texto do cliente**, literal por design |

Nada no JSON diz ao modelo qual é qual. E o `systemMessage`
(`n8n/workflow-ai-nao-salvos.json:218`) manda repassar, em quatro lugares:

- linha 62 — *"chame simular1 com tem_cnh e **responda somente a mensagem que a tool
  devolver** (confirmação de encaminhamento, pedido de dado faltante, ou bloqueio por
  menoridade)"* ← esta é a que casa com o trace de produção: o cliente acabou de mandar
  cpf + nascimento + cnh, o modelo está exatamente neste parágrafo;
- linha 91 (regra 3) — *"depois da tool simular, responda somente a confirmação curta que
  a tool devolver"*;
- linha 22 e 59 — *"envie exatamente a mensagem devolvida"* (menor de idade);
- linha 23 — *"quando a tool concluir, responda somente a confirmação devolvida"*.

Contra elas, **uma só** linha diz para agir em vez de repassar:

- linha 109 — *"se a tool retornar ok:false, precisa_escolher_moto, faltando, ou qualquer
  erro: NÃO confirme simulação; **siga a mensagem da tool** (peça dado/moto)"*.

"Siga" perde para "responda somente a mensagem que a tool devolver" por três razões: é
uma contra quatro, está 47 linhas depois da regra específica de financiamento, e é a
única que exige do modelo uma tradução (ler a instrução, executá-la, escrever outra
coisa) em vez de uma cópia.

### 1.3 O núcleo Revy repete a ambiguidade — e ele é o último bloco

Desde 25/08 o `systemMessage` termina no prompt da loja, que termina no núcleo Revy
(`chatbot-api/app/agente_prompt.py:29-56`). O núcleo prevalece sobre tudo. E ele diz:

- `:36-38` — *"depois da tool simular, responda somente a confirmação curta que ela
  devolver"*;
- `:45-46` — *"se a tool devolver motivo_bloqueio=menor_de_idade, **envie exatamente a
  mensagem da tool**"*;
- `:47-49` — *"em erro, ok:false ou faltando, siga a mensagem da tool"*.

Mesma proporção, mesma ambiguidade, e agora no bloco que vence os outros. **Consequência
para qualquer conserto:** mexer só no template do n8n não fecha o buraco — o texto que
prevalece está no `chatbot-api`. Isso muda o preço de todas as saídas abaixo (§3).

### 1.4 O que o cliente vê, e o que o banco registra, não são a mesma coisa

`Responder WhatsApp1` (`n8n/workflow-ai-nao-salvos.json:337`) é o gargalo único de saída
para cliente e já higieniza o texto por loja (minúsculas, emoji, bordão "me conta") —
por isso a frase chegou minúscula ao cliente.

Mas `Registrar saida do bot1` (`n8n/workflow-ai-nao-salvos.json:366`) grava
`$('AI Agent1').item.json.output` — o **output cru**, antes da higienização. As 22
ocorrências do banco medem o que o modelo *produziu*, não o que o cliente *leu*. Quem for
medir o conserto precisa saber disso: um bloqueio feito no `Responder WhatsApp1` conserta
o cliente e **não muda a contagem no banco**; um conserto feito no prompt ou no payload
muda as duas.

---

## 2. Por que só às vezes — 22 em 20 dias, não sempre

Duas condições independentes têm de coincidir. Nenhuma das duas é rara, mas as duas
juntas são minoria.

### 2.1 A condição de disparo: o modelo pediu CPF de uma moto que nunca foi resolvida

O caminho de anúncio é o que produz isso, e produz por instrução própria:

- `systemMessage:49` — na abertura de anúncio o bot pergunta *"à vista ou financiamento?"*
  e **não** consulta o estoque;
- `systemMessage:51` — *"na abertura de anúncio, não mande foto automaticamente"* — ou
  seja, `enviar_foto_veiculo` também não roda, e ele é o outro consumidor da moto única;
- `systemMessage:82` — *"quando houver uma moto específica clara (busca única, cliente já
  escolheu **ou moto do anúncio**)"* — o `titulo_anuncio` conta como moto clara **para o
  modelo**;
- `systemMessage:84` — com moto clara e pedido de simular, *"NÃO exija foto antes: peça
  cpf, data de nascimento e se tem cnh"*.

Resultado: o modelo trata a moto do anúncio como escolhida e pede os dados, mas
`consultar_estoque1` nunca rodou, então `moto-escolhida:<telefone>` nunca foi escrito.
Quando `simular1` é chamado, os dois caminhos vivos de recuperação (§1.1) falham, e o
ramo dispara. É exatamente o trace de 26/08: anúncio → financiamento → cpf/nascimento/cnh
→ vazamento, sem nenhuma consulta de estoque no meio.

Reforço do mesmo efeito: `systemMessage:18` manda chamar `TEMP continuar sem estoque1`
quando o estoque volta zero. Se a busca **volta zero e o cliente já mandou os dados**, o
modelo tem duas tools plausíveis e escolher a errada (`simular1`) cai no mesmo ramo.

Fatores que somam: `moto-escolhida:` mora no **static data do workflow**, que não é
memória de conversa — reimport/update do workflow no n8n (a sequência de
`2026-08-23-import-do-n8n-desativa-o-workflow.md`) reseta essa chave. Conversa que
atravessa uma publicação perde a moto e cai no ramo mesmo tendo consultado o estoque
antes.

### 2.2 A condição de vazamento: copiar é mais barato que traduzir

Disparar o ramo não basta — em muitas execuções o modelo faz a coisa certa (volta a
perguntar qual moto). O que empurra para a cópia:

- a `mensagem` do ramo 89 é a **mais longa e mais completa** de todas as internas: três
  frases, já em minúsculas, já no tom do bot, sem citar nenhum campo do payload. Lida como
  resposta pronta. Compare com a do ramo 135 — *"peça somente os campos listados em
  faltando"* — que cita um campo e por isso se denuncia como instrução;
- o modelo acabou de ler `systemMessage:62` (§1.2), a instrução mais específica e mais
  próxima do momento;
- não há sinal estrutural nenhum no JSON separando os dois usos de `mensagem`.

**A prova de que é cópia parcial, não cópia inteira:** as duas frases estão na *mesma*
string desde 03/08, mas o banco tem 22 hits da primeira e 9 da segunda. Se toda ocorrência
fosse cópia literal do payload inteiro, os dois números seriam iguais. A diferença de 13 é
o modelo reproduzindo a primeira frase e reescrevendo (ou cortando) o resto — o que
explica também por que "volte ao catálogo" só aparece a partir de 10/08: não é uma mudança
de código, é a cauda de um comportamento probabilístico.

**Corolário que fecha uma armadilha de conserto:** qualquer solução baseada em procurar a
string exata na saída (blocklist, `includes()` do texto completo) já erra 13 dos 22 casos
conhecidos. O conserto tem que ser de contrato, não de string.

---

## 3. Saídas

### A — separar o payload em "campo que o agente lê" e "texto que o cliente pode ouvir" *(recomendada)*

Trocar a chave única `mensagem` por duas, em todas as tools:

- `mensagem_ao_cliente` — só nos ramos que hoje já são texto de cliente: `simular1:146`
  (menor de idade) e `simular1:222` (sucesso). São **dois** ramos, de treze;
- `instrucao_agente` — todo o resto. E uma frase no prompt: *"`instrucao_agente` é para
  você, nunca para o cliente; nunca a repita, nem em parte, nem reescrita. só
  `mensagem_ao_cliente` pode ser enviado."*

Isso conserta pela estrutura, não pela persuasão: o modelo passa a ter um sinal para
distinguir, que é exatamente o que falta hoje.

**O contrato tem de ser um só.** Se `simular1` separar e as outras não, a ambiguidade
volta pela porta do lado. O mesmo defeito está em:

| Tool | Linhas do `jsCode` com instrução vestida de `mensagem` |
|---|---|
| `TEMP continuar sem estoque1` | 25, 98, 122, 193, 200 |
| `enviar_foto_veiculo1` | 15, 21, 34, 60, 68 |
| `solicitar_handoff1` | 6, 7, 19 |
| `enviar_link_catalogo1` | 27 |

(`enviar_link_catalogo1:20`, `solicitar_handoff1:67` e `TEMP…:37` e `:112` são texto de
cliente legítimo.)

**Cuidado com o repasse do backend.** `simular1:214/222/230` devolve `resp.mensagem` de
`POST /v1/operacao/solicitacoes-simulacao-humana`. A do ramo 222 é texto de cliente; a do
ramo 230 (*"peça somente os campos listados em faltando"*) é instrução. Não é preciso
mudar o contrato HTTP: a tool sabe em que ramo está e classifica ali. Mas fica registrado
que o `chatbot-api` escreve `mensagem` em registro imperativo, e quem um dia rotear esse
campo direto ao cliente reabre este bug.

**Custo:** edição no `simular1` + 4 tools do `workflow-ai-nao-salvos.json`; ~6 linhas no
`systemMessage` (22, 23, 59, 62, 91, 109) e nas `description` das tools; **e o núcleo
Revy** (`chatbot-api/app/agente_prompt.py:36-38, 45-46, 47-49`), porque é ele que
prevalece (§1.3).

**O que exige dos três derivados:** regerar os três e revalidar os quatro —

```powershell
node   n8n\build_test_workflow.js      ; python n8n\validate_test_workflow.py
python n8n\fork_cloud_workflow.py      ; python n8n\validate_workflow_cloud.py
python n8n\build_preview_workflow.py   ; python n8n\validate_preview_workflow.py
python n8n\validate_workflow.py
node n8n\test_modo_seco.js
node n8n\test_higienizacao_saida.js
npm install --no-save @n8n/tournament ; node n8n\test_expressoes.js
```

`fork_cloud_workflow.py` **para** se a forma de uma chamada mudar (`INJECOES_INSTANCE`), e
`build_preview_workflow.py` **para** se a forma do freio de modo seco mudar. Mexer nos
`return` das tools é exatamente onde os dois geradores olham — contar com uma rodada de
ajuste nos geradores, não só nos JSON.

Mexer no núcleo tem um passo a mais, que é fácil esquecer: o núcleo vive **duas vezes**
(gerador do chatbot + constante JS de fallback no `Gate config do agente1`). Depois de
editar `agente_prompt.py`:

```powershell
cd chatbot-api ; .\.venv\Scripts\python.exe -m scripts.sincronizar_fallback_n8n
.\.venv\Scripts\python.exe -m tests.test_agente_prompt_snapshot   # regrava o golden
```

— e esse script **reescreve o JSON do n8n**, então os três derivados são regerados
*depois* dele, não antes.

**Deploy:** dois alvos. `n8n2037` (workflow) **e** `app2037` (núcleo). Um sem o outro
deixa metade do conserto no chão.

### B — só desambiguar o texto *(mais barata, incompleta)*

Não tocar no payload; reescrever as seis linhas do `systemMessage` e as três do núcleo
para "só envie ao cliente o texto que a tool marcar como do cliente; o resto é para você".

**Custo:** menor em edição, **idêntico em publicação** — continua sendo os dois deploys, o
snapshot, o `sincronizar_fallback_n8n` e os três derivados, porque o núcleo mora nos dois
lugares. Ou seja: economiza a parte barata e paga a parte cara inteira.

**Por que não recomendo:** sem um campo que separe, "o texto que a tool marcar" não existe
— o modelo continua tendo uma chave só e treze significados. Fica probabilístico, e §2.2
mostra que a falha já é probabilística hoje.

### C — rede de segurança na saída *(complemento, não substituto)*

`Responder WhatsApp1` (`:337`) é o gargalo único: toda resposta a cliente passa por ele e
já é reescrita ali. Dá para barrar o vazamento de forma determinística **se** a saída A
existir: pôr um sentinela no início de todo `instrucao_agente` e, no `Responder`, recusar
a mensagem que o contenha (e responder um fallback seguro, tipo "qual moto você quer
conhecer melhor?").

**Limite honesto:** o sentinela só pega a cópia literal. §2.2 mostra que 13 dos 22 casos
foram cópia parcial — e uma cópia parcial que corte o sentinela passa. Vale como cinto de
segurança e como sonda (loga quando dispara), não como conserto.

**Não fazer sozinha.** Sem A, C vira caça a strings, e além de errar os 13 casos parciais,
ela mente na medição: como `Registrar saida do bot1` grava o output cru (§1.4), a contagem
no banco continuaria subindo com o cliente já protegido.

**O que exige dos derivados:** a mesma lista da saída A. Atenção extra ao Modo 2 — o
`Responder WhatsApp1` do fork manda `{ telefone, texto }` e já perdeu uma vez o que o Modo
1 calculava nesse nó (o `__delayAntiBan`, learning `2026-08-23-workflow-cloud-e-gerado`).
Se a checagem for escrita no `jsonBody` do Modo 1, conferir que o fork **consome** o
resultado, não só que o nó existe.

### Recomendação

**A + C, nessa ordem, no mesmo card de implementação.** A conserta o mecanismo; C dá o
piso determinístico e a sonda para saber se voltou. B está contida em A (A obriga a
reescrever o mesmo texto), então não é uma terceira opção — é a metade de A que não
resolve nada sozinha.

Ordem de execução sugerida, porque a ordem importa:
1. `agente_prompt.py` (núcleo) → `sincronizar_fallback_n8n` → snapshot;
2. `workflow-ai-nao-salvos.json` (tools + `systemMessage` + `Responder WhatsApp1`);
3. os três geradores + os quatro validadores + os testes de execução;
4. deploy `app2037` **e** `n8n2037`.

---

## 4. O que muda em `validate_workflow.py`

Nenhuma assertiva se apaga. Duas mudam de forma, e uma nasce.

| Linha | Assertiva | O que acontece |
|---|---|---|
| `:358` | `"precisa_escolher_moto: true" in simulation_code` | **não muda** — a flag continua |
| `:361` | `"a moto ainda não foi escolhida" in simulation_code` — *"fallback da tool não pede escolha de moto no catálogo"* | **muda**. A frase pode continuar existindo (o texto segue certo como instrução), mas a garantia que interessa passou a ser outra: que ela sai em `instrucao_agente` e que esse ramo **não** devolve `mensagem_ao_cliente`. Trocar a afirmação de *"a frase existe"* para *"a frase existe **e** está no campo interno"* |
| `:364` | `"conhecer melhor" or "não repita dados"` | mesmo caso de `:361` |
| `:379` | `"não peça cpf, nascimento, entrada ou placa agora"` | mesmo caso de `:361` |
| `:384` | `"certo, já tenho seus dados. vou encaminhar pro setor de simulação"` | **sobrevive** — vira `mensagem_ao_cliente`, e vale endurecer para exigir que esteja nesse campo |
| `:390` | `menor_de_idade` + `"menores de 18 anos"` | idem `:384` |
| — | **nova** | o `systemMessage` contém a frase que separa os dois campos. É o padrão da casa: o validador prende o prompt por frase literal (`:120` em diante), e foi isso que já pegou regressão de prompt |

**Por quê, e não "porque o texto mudou":** a assertiva de `:361` foi escrita para impedir
que alguém tirasse o freio que manda voltar ao catálogo. Esse freio continua existindo —
só muda de canal. A regra do learning
`2026-08-23-o-prompt-do-bot-mora-no-n8n` vale aqui: **nunca apagar assertiva para o
validador passar**; mover a garantia para onde o texto foi morar. Aqui ele não sai do
arquivo, só sai da chave — então a assertiva fica no mesmo lugar, apertada.

Fora do n8n, se o núcleo mudar: `chatbot-api/tests/test_agente_prompt_snapshot.py` (golden
`tests/snapshots/agente_prompt.txt`, regravar com o próprio módulo),
`test_agente_prompt_fallback_do_n8n.py` (compara a constante JS com o gerador) e
`test_agente_prompt_migrado_do_n8n.py`.

---

## 5. O que este card não faz

- Não edita nenhum dos quatro JSON, não roda `prepare-workflow.ps1` nem
  `upload-and-import-workflow.ps1`, não deploya. Produção segue no ar.
- Não mexe no caminho de anúncio (§2.1). O `systemMessage:82` tratar "moto do anúncio"
  como moto clara é **decisão de produto**, não bug — mudar isso muda o atendimento de
  anúncio inteiro. Se o dono quiser fechar a condição de disparo também, isso é card
  próprio: hoje o modelo pede CPF de uma moto que o backend não resolveu, e o único aviso
  disso chega tarde demais, dentro da tool.
- Não corrige os dois fallbacks mortos do `simular1` (`origem.motoEscolhida` na linha 46 e
  `origem.cpfCliente` na 17, ambos ausentes do `Extrair1`). São inofensivos hoje — só
  fazem o código parecer ter três redes quando tem duas. Anotado, não consertado.

## Verificação

`python n8n/validate_workflow.py` → **exit 0**, verde:
*"workflow n8n válido: 34 nós, replay >5min bloqueado, debounce pela última entrada,
fallback temporário sem fotos, multi-WA instance dinâmica, áudio ignorado, webhook seguro
e resultado privado"*.

---

## 6. Prioridade — medido, não estimado (25/08, contra o Postgres de produção)

| Medida | Valor |
|---|---|
| Ocorrências de "ainda não foi escolhida" | 22, desde 06/08 |
| Conversas distintas afetadas | 22 (nunca duas na mesma) |
| **Cliente respondeu depois mesmo assim** | **19** |
| Cliente sumiu depois | 3 |
| Volume do bot no mesmo período | ~900 mensagens/dia |

**Não é urgente, e a razão está na terceira linha.** O cliente releva: em 19 dos 22 casos
ele continuou a conversa como se nada tivesse acontecido. O prejuízo defensável são as 3
conversas que pararam ali — em 20 dias.

O que mantém isto no topo da fila mesmo assim é **onde** cai: logo depois de o cliente
entregar CPF e data de nascimento, que é o momento de maior intenção da jornada inteira.

Não justifica hotfix, janela noturna nem rollback. Justifica ser o próximo card pego.

## 7. Execução — tasks para agente

Um filho por task, na ordem. O pai cola **só a task da vez + as constraints globais**;
não cola o card inteiro nem manda "leia o AGENTS.md primeiro".

### Constraints globais (vão em todo brief)

- **Produto:** `chatbot-api` e `n8n`. Nenhum outro.
- Testes: `chatbot-api` → `.\.venv\Scripts\python.exe -m pytest -q` (Windows) /
  `.venv/bin/python -m pytest -q` (macOS), a partir de `chatbot-api/`.
  `n8n` → `python n8n/validate_workflow.py` e os `node n8n/test_*.js` do
  `n8n/GUIA-WORKFLOW.md`, a partir da raiz.
- **Nada pode ser colado depois do slot** `{{ $('Gate config do agente1').first().json.promptAgente }}`
  no `systemMessage`. O núcleo Revy só prevalece por ser o último bloco.
- `workflow-cloud.json`, `workflow-preview.json` e `workflow-teste-numero-autorizado.json`
  são **gerados**. Editar à mão é regressão silenciosa.
- Mexeu no gerador do prompt? `python -m scripts.sincronizar_fallback_n8n` no `chatbot-api`,
  senão `test_agente_prompt_fallback_do_n8n.py` reprova.
- **Não deploya, não roda `prepare-workflow.ps1`, `upload-and-import-workflow.ps1` nem
  `fly`.** Tudo isto está no ar desde 25/08 e o deploy é do dono.
- Não abrir `docs/nao-plano/`. Docs permitidos: este card, `n8n/GUIA-WORKFLOW.md`,
  `chatbot-api/README.md` (seção do agente por loja).

### Task 1 — o núcleo Revy para de mandar copiar

`chatbot-api/app/agente_prompt.py:36-49`. Desambiguar as três regras que hoje mandam
"siga/responda a mensagem da tool" sem dizer **qual campo** é falável. É a primeira porque
o núcleo é o bloco que vence, e porque ele reescreve o fallback JS do n8n — fazer depois
obrigaria a mexer no JSON duas vezes.

Pronto quando: `pytest -q` verde no `chatbot-api` com
`tests/snapshots/agente_prompt.txt` regravado de propósito
(`python -m tests.test_agente_prompt_snapshot`, com o diff conferido à mão),
`python -m scripts.sincronizar_fallback_n8n` rodado, e `python n8n/validate_workflow.py`
ainda exit 0.

### Task 2 — `simular1` separa os dois campos

`n8n/workflow-ai-nao-salvos.json:291`, jsCode. Os treze ramos passam a devolver
`mensagem_ao_cliente` (só os dois de §1.1 que já são texto de cliente) ou
`instrucao_agente` (os outros onze). O `systemMessage:218` linha 62 deixa de dizer
"responda somente a mensagem que a tool devolver" e passa a nomear o campo.

Pronto quando: as assertivas `validate_workflow.py:361`, `:364` e `:379` exigirem a frase
**no campo interno** (§4), `python n8n/validate_workflow.py` exit 0, e
`node n8n/test_expressoes.js` verde.

### Task 3 — as outras quatro tools, mesmo padrão

`TEMP continuar sem estoque1`, `enviar_foto_veiculo1`, `solicitar_handoff1`,
`enviar_link_catalogo1` — o mapa linha a linha está em §3-A. Sem inventar padrão novo:
o de Task 2, repetido.

Pronto quando: `python n8n/validate_workflow.py`, `python n8n/validate_workflow_cloud.py`,
`python n8n/validate_preview_workflow.py` e a bateria `node n8n/test_*.js` verdes.

### Task 4 — sentinela na saída (piso, não substituto)

Saída C, §3. `Responder WhatsApp1` (`:337`) é o gargalo único de saída: barrar ali a frase
sentinela. **Só cobre cópia literal** — §2.2 mostra que 13 dos 22 casos são cópia parcial,
então isto é rede, não conserto.

Pronto quando: `node n8n/test_higienizacao_saida.js` verde e com caso novo provando o
barramento nos três modos.

### Task 5 — regerar os derivados e fechar

`python n8n/fork_cloud_workflow.py`, `python n8n/build_preview_workflow.py`,
`node n8n/build_test_workflow.js`, depois a bateria inteira do `n8n/GUIA-WORKFLOW.md` mais
`pytest -q` no `chatbot-api`.

Pronto quando: tudo verde, `git diff --check` limpo, e o card atualizado com o que mudou
durante a execução.

### Não é task: fechar a condição de disparo

§2.1 e §5. Mexer no tratamento de anúncio é decisão de produto do dono, e muda o
atendimento de anúncio inteiro. Card próprio, se ele quiser.

### Depois das tasks (é do dono, não do agente)

Dois deploys: `app2037` (núcleo) e `n8n2037` (workflow, com restart e a janela de 404).
Sequência na skill `revy-deploy`. **A métrica engana:** `Registrar saida do bot1` (`:366`)
grava o output cru do modelo, não o texto higienizado — medir o conserto por
`select ... texto like '%ainda não foi escolhida%'` vai dizer que não funcionou mesmo
quando funcionou (§1.4).
