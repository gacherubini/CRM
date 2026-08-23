# Skill `revy-research` — mapa, learnings e decisões do monorepo

Data: 2026-08-23 · Status: desenhado, não implementado

## O problema

O repo tem **694 arquivos `.py` nos seis produtos** — 724 contando todo o
projeto — dentro de uma árvore de **10.288**. Os cinco `.venv` respondem por
**9.564 deles, 93%**: é essa a fração que uma busca ingênua devolve como
código-fonte do FastAPI, e aconteceu duas vezes durante o levantamento desta
spec. (Medido em 23/08 pela varredura da Task 2.)

Os arquivos de entrada são grandes demais para leitura integral:

| Arquivo | Linhas |
|---|---|
| `portal-gestao/app/main.py` | 2.609 |
| `chatbot-api/app/servico.py` | 2.285 |
| `revy-trafego/app/web/control_ui.py` | 2.184 |
| `chatbot-api/app/main.py` | 2.038 (57 rotas) |

O `AGENTS.md` já diz "não abra `app/main.py` inteiro", e está certo. Mas ele
não diz **onde a coisa está**, e sobra `rg` às cegas dentro de 10 mil arquivos.

Em paralelo, o conhecimento operacional do projeto vive em ~35 memórias
pessoais de sessão do agente: fora do git, invisíveis no Mac do dono, invisíveis
para subagentes, perdidas em qualquer troca de máquina.

## O que se constrói

Uma skill de projeto em `.claude/skills/revy-research/`, auto-contida e
versionada, com três dados e um gerador. O gerador nasceu como um arquivo só e
virou quatro no plano de implementação: cada um é testável isolado, e só
`extratores.py` precisa entender `ast`.

Versionar é **requisito**, não conveniência: o dono trabalha em Mac e Windows, e
o que não está no git não existe na outra máquina. É daí que vem a mudança no
`.gitignore` logo abaixo.

```
.claude/skills/revy-research/
  SKILL.md            protocolo (67 linhas) — única coisa sempre carregada
  varredura.py        acha os 694 dos produtos e ignora os 9.564 dos .venv
  extratores.py       AST estático, os 7 extratores; funções puras texto → Entrada
  gerar_mapa.py       CLI, render do markdown, selo de frescor, modo --verificar
  cruzamentos.py      clientes HTTP × rotas declaradas; funções sem chamador
  test_gerar_mapa.py  unittest da stdlib, roda sem .venv
  mapa/
    _frescor.json     SHA da geração + o inventário que o --verificar reabre
    _cruzamentos.md   quem chama quem + suspeitas de órfão
    chatbot-api.md  portal-gestao.md  motor-simulacao.md
    estoque-api.md  revy-trafego.md   catalogo-publico.md
  learnings/  INDEX.md + um arquivo por armadilha
  decisoes/   INDEX.md + um arquivo por escolha do dono
  propostas.md  o que o agente mudaria no protocolo; o dono aprova
```

### Pré-requisito: versionar `.claude/skills/`

`.gitignore:46` ignora `.claude/` inteiro. Sem correção, a skill morre na
máquina onde foi criada. Troca-se a exclusão de pasta por exclusão de conteúdo
com uma exceção:

```gitignore
.claude/*
!.claude/skills/
```

`settings.local.json` e `worktrees/` continuam ignorados como hoje.

### Divisão de donos

Nenhuma linha do mapa é opinião. Onde há julgamento, o dono continua sendo o
`README.md` do produto, que já existe — a skill aponta, não copia.

| Dado | Dono | Envelhece |
|---|---|---|
| `mapa/` | o script, sempre | não; o selo de frescor denuncia |
| `learnings/` | o agente, ao se surpreender | não |
| `decisoes/` | o dono, ao decidir | não |
| `propostas.md` | o agente propõe, o dono decide | esvazia quando aplicada |
| `SKILL.md` | humano, raramente | é protocolo, não conteúdo |

## O gerador

**Decisão de fundo: AST estático da stdlib, nunca importar o app.** Respeita o
invariante "sem import `app` entre produtos", dispensa `.venv`, roda igual no
Mac e no Windows, não pode quebrar nada. ~694 arquivos em 2–4 segundos.

Verificado no levantamento: `APIRouter()` e `include_router()` são chamados sem
`prefix=` em todo o repo, então **o path do decorator é o path real**. Se um
`prefix=` aparecer no futuro, o gerador compõe quando conseguir resolver
estaticamente e marca `?` quando não conseguir — nunca inventa. É o único
ponto por onde o mapa consegue mentir com o `--verificar` verde (o decorator
continua com o path nu), então a regra virou código e um teste-armadilha que
fica vermelho no dia em que o primeiro `prefix=` aparecer.

Extratores, por produto:

| Seção | Fonte |
|---|---|
| Rotas | `@app.<verbo>` / `@router.<verbo>` → método, path, função, `arquivo:linha` |
| Modelos | classe com `__tablename__` → tabela, classe, `arquivo:linha` |
| Migrations | `alembic/versions/*.py`; calcula o head por `down_revision` |
| Workers | `*_job.py`, `*_workers.py`, classes `*Worker` |
| Flags | `REVY_*` / `MULTI_*` em `os.getenv` + default no código (74 hoje) |
| Templates | `.html` + a rota que faz `TemplateResponse` |
| Testes | tabela fixa no gerador, macOS **e** Windows |

"Testes" é a única seção escrita à mão, porque não é inferível — e é onde mora a
exceção que sempre morde (`revy-trafego` não tem `.venv`; usa o do
`portal-gestao`).

**O mapa é gerado e commitado.** Sem isso ele não existe para quem clona, para o
outro sistema operacional nem para subagente em worktree. O gerador roda sob
demanda em dois casos: o agente oferece quando o selo de frescor acusa atraso, e
o dono pede quando quiser. Não roda sozinho em hook nem em commit.

Contagens atuais para conferência: chatbot 25 migrations, portal 26,
control 20, estoque 10, motor 14. Templates: portal 61, control 20,
catálogo 4, estoque 3, chatbot 0.

### `_cruzamentos.md`

Quatro checagens, todas rotuladas **suspeitas, não erros**:

1. **Rota órfã de servidor** — um cliente HTTP chama um path que nenhum produto
   declara. É o bug documentado do Modo 2 ("o `chatbot-api` não expõe rota de
   oferta"), cujo efeito prático é *lead que ninguém pega some*.
2. **Função pública sem chamador** — `def` sem underscore, zero referências nos
   694 arquivos dos produtos. É o caso `criar_sinal_direcionado`.
3. **n8n × chatbot** — os `n8n/workflow-*.json` declaram webhook e chamam rotas
   do chatbot. Cruzar as duas listas. É a junta de severidade máxima do repo:
   quando ela abre, o bot fica mudo e o produto para. JSON é `json.loads`; a
   rota já está no mapa. Custo baixo, severidade máxima.

   **Só 2 dos 3 arquivos estão publicados** (painel do n8n, 23/08):
   `workflow-ai-nao-salvos.json` ("WhatsApp IA - Somente Nao Salvos", canônico)
   e `workflow-cloud.json` ("whatsapp-cloud"). `workflow-teste-numero-autorizado.json`
   existe no repo e não está no ar. A checagem de rota sem servidor roda **só nos
   publicados** — workflow morto chamando rota removida não é incidente, e alarme
   falso mata a seção. (`workflow-echo.json` era o quarto e foi apagado em 23/08:
   3 nós, nunca publicado, sem referência em código ou validador.)

   O `nome` do workflow é derivável (está dentro do JSON); **estar publicado não
   é**, e vira a tabela `PUBLICADOS` escrita à mão, no mesmo padrão de `TESTES` e
   `ALVO_POR_CLIENTE`. Para não envelhecer em silêncio, o render denuncia
   qualquer `workflow-*.json` não classificado: publicar um terceiro faz aparecer
   a linha pedindo para acrescentá-lo.
4. **`fly.toml` → app declarado** — os 7 do repo, numa tabela. O `AGENTS.md`
   avisa que os da pasta de cada produto apontam para apps **destruídos**;
   listá-los torna a armadilha visível em vez de decorada. **Quais** estão
   mortos não entra: isso é conhecimento humano, muda com o tempo, e nenhum
   script verifica — vai para o README do deploy ou para um learning.

Todas geram falso positivo (dispatch dinâmico, path montado por string, função
só consumida por teste). Cada linha sai com o motivo, e o `SKILL.md` fixa a
regra: **suspeita não vira commit; vira pergunta.** Seção que grita lobo é
seção que ninguém lê.

Evidência disso, colhida em 23/08 ao desenhar a checagem 3: uma primeira versão
crua acusou `/pode-responder` como rota faltando. Era falso positivo — casou um
prefixo (`/v1/conversas/`) contra a rota errada; a rota existe em
`chatbot-api/app/main.py:921`. **O casamento tem que ser de path inteiro
normalizado, nunca de substring.**

### A fronteira do mapa é a verificabilidade, não a importância

O `--verificar` reabre cada `arquivo:linha` e prova o símbolo. Um fato que não
pode ser provado assim não entra no mapa, porque fato não-verificável dentro de
arquivo gerado **eventualmente mente** — a doença que esta skill existe para
curar. É esse critério, e não relevância, que decide o que o mapa cobre.

Por isso ficam **de fora**: `docs/` (já roteado pelo `AGENTS.md` §3 e pelo
`docs/README.md`, e sem símbolo para ancorar), `shared/` e `site/` (CSS e HTML
estático — pertencem a uma futura skill de UI e à do site).

### Frescor por produto

`_frescor.json` guarda o SHA da geração. Ao disparar, a skill roda
`git diff --name-only <sha>..HEAD -- <produto>/`. Vazio → silêncio. Não vazio →
aviso nomeando os arquivos e oferecendo regerar.

A granularidade é por produto de propósito: mexer no `site/` não pode disparar
aviso sobre o mapa do motor. Aviso que dispara à toa é aviso que se aprende a
ignorar.

## Learnings e decisões

**Learning** = armadilha técnica reproduzível. O campo `gatilho` é o que o torna
achável; `INDEX.md` é uma linha por learning, e só os 1–2 que batem são abertos.

```markdown
---
gatilho: rodar alembic ou conferir migration em produção
produto: chatbot-api
custo: 1h30
---
# O chatbot responde SQLite e mente
`alembic current` sem `CHATBOT_DATABASE_URL` responde do SQLite local, com
cara de sucesso. Sempre: `CHATBOT_DATABASE_URL=<pg> .venv/bin/alembic current`
```

**Decisão** = escolha do dono a não re-propor. Categoria separada porque o
desperdício que ela evita é outro: repropor o que já foi recusado. O repo já
precisou de um invariante inteiro no `AGENTS.md` para isso ("13 itens recusados
não voltam como proposta"), e seis memórias são deste tipo. O `SKILL.md` manda
ler o índice de decisões **antes de propor**, não antes de codar.

```markdown
---
decidido: 2026-08-16
nao_reproponha: rateio de despesa fixa no lucro por moto
---
Despesa fixa não entra no lucro de cada moto; o lugar disso é o ponto de
equilíbrio. Não é falta de implementação — foi escolha.
```

## Disparo

Uma skill dispara por julgamento do agente lendo o `description`. Isso é bom,
não é garantido. Duas camadas:

1. `description` nomeando os verbos reais: codar, corrigir, implementar, mexer
   em qualquer produto do monorepo.
2. Passo 0 no `AGENTS.md` §1 ("Antes de qualquer ferramenta"): **invoque
   `revy-research` antes de procurar código.** Como o `AGENTS.md` já é lido e
   obedecido em todo boot, isso torna o disparo determinístico sem hook. O §6
   ganha o fechamento (ver "Onde o loop fecha").

Terceira camada disponível e **não adotada**: hook `UserPromptSubmit` injetando
a instrução em todo turno. Custa tokens em toda mensagem; só se as duas
primeiras falharem na prática.

## Protocolo do `SKILL.md` — um gatilho, uma porta

**Uma skill só, não quatro.** Skill dispara por competição de `description`;
quatro skills cujas descrições dizem quase a mesma coisa ("use ao mexer em
código do Revy") competem pelo mesmo gatilho, e o modo de falha dominante passa
a ser **nenhuma disparar**. Além disso `implementar`, `feature` e `debug`
compartilham o mesmo primeiro passo — achar o código — e separá-las exigiria ou
duplicar o protocolo do mapa, ou criar uma quinta skill "núcleo" que é a skill
única com indireção na frente. O `AGENTS.md` já legisla contra o espalhamento
("não espalhe um eixo em vários filhos").

**E a skill não inventa protocolo que já existe.** ORIENTAR e PROPOR foram
desenhados do zero num primeiro rascunho e recusados em 23/08: `brainstorming`,
`systematic-debugging` e `test-driven-development` já fazem essas três coisas, e
melhor. A skill é **porta, não caminho** — mesmo princípio que o design já
aplicava ao julgamento ("o mapa aponta, não copia"), agora aplicado ao processo.

```
revy-research = TRONCO (contexto) → BRIEFING (empacota) → ROTEAMENTO (entrega)
```

### Tronco — o que só ela sabe fazer, porque só ela conhece o repo

```
1. Identifique o produto (1 dos 6). Tarefa que cruza dois: PARE e diga.
2. Cheque o frescor do mapa daquele produto.
3. Abra mapa/<produto>.md  →  arquivo:linha.
4. Leia learnings/INDEX.md e decisoes/INDEX.md; abra só os que batem.
```

`decisoes/` é lido **no tronco**, não num modo. Se a leitura ficasse para depois
do roteamento, a skill destino começaria cega e re-proporia o que o dono já
recusou — que é exatamente o desperdício que a pasta existe para evitar.

### Briefing — o que atravessa o roteamento

Roteamento sem contexto é só um "vá para lá". O que a skill entrega é um pacote,
no formato do
[`task-brief.md`](../agents/task-brief.md) que o `AGENTS.md` §4 já exige para
subagente: produto, arquivos com linha, invariantes da tarefa, learnings que
batem, decisões que restringem, comando de teste nos dois SOs.

### Roteamento — para skills que já existem

| Intenção | Destino |
|---|---|
| construir algo novo, desenhar, decidir rumo | `superpowers:brainstorming` |
| bug, teste vermelho, comportamento estranho | `superpowers:systematic-debugging` |
| implementar feature ou correção | `superpowers:test-driven-development` |
| já tem spec, quer plano | `superpowers:writing-plans` |
| já tem plano, quer executar | `superpowers:subagent-driven-development` |
| mudar UI da Loja/Control | `frontend-design` + as 13 recusas em `decisoes/` |
| achar que acabou | `superpowers:verification-before-completion` |

Se a skill destino não estiver instalada na máquina, a regra é seguir o tronco e
avisar — nunca improvisar o protocolo que faltou.

Custo por disparo: `SKILL.md` (~55) + `mapa/<produto>.md` (~150) + os dois
`INDEX.md` (~55) ≈ **260 linhas** para saber onde tudo está e para onde ir,
contra 2.609 de um `main.py` que ainda não responde a pergunta.

## O loop de auto-melhoria

A skill se atualiza sozinha, mas **cada camada tem permissão diferente**. Loop
uniforme é como o conhecimento apodrece.

| Camada | Quem escreve | Loop | Por quê essa permissão |
|---|---|---|---|
| Mapa | o script | **automático**, no mesmo commit do código | a fonte é o código; `--verificar` prova |
| Learnings / decisões | o agente, só append | **automático, com filtro e poda** | append-only é reversível e revisável em PR |
| Protocolo (`SKILL.md`) | humano aprova | **proposta, nunca auto-edição** | é o que carrega sempre; deriva sai cara |

**A forma mais forte do loop é mecânica e sai de graça:** se a tarefa mexeu em
rota, modelo, worker, migration ou flag, o gerador roda e o mapa entra no mesmo
commit. O mapa não fica velho porque envelhecer virou impossível — a mudança e o
registro da mudança viajam juntos.

### Onde o loop fecha, já que a skill saiu de cena

Como a skill só faz o primeiro passo, **ela não está mais no comando quando a
tarefa acaba** — o controle passou para `test-driven-development` ou
`systematic-debugging`. Instrução de fechamento embutida no briefing seria
frágil: depende de alguém lembrar dez passos depois.

O fechamento entra no **`AGENTS.md` §6 "Antes de dizer que acabou"**, checklist
que é lida em todo boot e já exige testes do produto, `alembic upgrade head`,
`validate_workflow.py` e `git diff --check`. Duas linhas a mais:

```markdown
Mexeu em rota, modelo, worker, migration ou flag? Regere o mapa e commite junto
com o código: `cd .claude/skills/revy-research && python gerar_mapa.py` (Windows)
ou `python3 gerar_mapa.py` (macOS).
Algo te surpreendeu? Escreva um learning — procurando duplicata pelo gatilho antes.
```

Assim o loop fecha independente de qual skill esteja no comando. O `AGENTS.md`
ganha **duas** edições no total: o passo 0 no §1 (abre) e estas duas linhas no
§6 (fecha).

**O `SKILL.md` não se auto-edita.** Um protocolo que se reescreve a cada tarefa
deriva: em trinta tarefas vira 400 linhas que ninguém escreveu nem revisou, com
regras contraditórias, encarecendo todo disparo. É a doença que o `AGENTS.md` de
99 linhas foi escrito para curar. A válvula é `propostas.md`: quando o agente
percebe que o *protocolo* falhou — não o código, o protocolo — escreve uma linha
lá dizendo o que falhou e o que mudaria. O dono lê quando quiser.

### Poda — a força contrária

Base de conhecimento que só cresce é base que ninguém lê. Se o
`learnings/INDEX.md` chegar a 200 linhas, o passo "leia o índice, é barato"
morreu, e com ele a skill. Três regras, dentro do protocolo de escrita:

1. **Antes de criar learning, procurar duplicata pelo gatilho.** Já existe um do
   mesmo gatilho? **Edita** o existente; não cria o 201º.
2. **Learning que se provou falso morre.** Abriu o learning, seguiu a instrução e
   ela não é mais verdade porque a armadilha foi corrigida no código? **Apaga o
   arquivo** no mesmo commit. Learning não expira por data — expira por
   evidência.
3. **Teto de revisão declarado no índice:** passou de ~40 learnings, é sinal de
   que falta poda. Gatilho de revisão, não regra rígida.

## Verificação

`gerar_mapa.py --verificar` **reabre cada `arquivo:linha` do mapa e confere que
a linha contém o símbolo prometido.** Uma entrada fora do lugar → exit 1. Isso
transforma "o mapa está desatualizado?" de opinião em teste, e torna auditável a
promessa de que o mapa não mente. Cabe no `AGENTS.md` §6.

`test_gerar_mapa.py` — três testes são o **piso** obrigatório (o plano de
implementação chegou a 42, um por comportamento):

1. os 6 produtos aparecem no mapa;
2. fatos conhecidos existem (`POST /webhook/cloud` no chatbot; `fila_vendedor`
   em `models_db.py`) — **sem fixar número de linha**, senão o teste quebra a
   cada edição e se aprende a ignorá-lo;
3. `--verificar` sai 0 em um mapa recém-gerado.

Rodam com `python` puro (stdlib), sem `.venv`.

## Migração das memórias

As ~35 memórias em `~/.claude/.../memory/` se separam em três:

| Tipo | ~Qtd | Destino |
|---|---|---|
| Learning técnico reproduzível | 20 | `learnings/` |
| Decisão do dono | 6 | `decisoes/` |
| Estado da semana ("v114 LIVE", "próximo foco") | 9 | fica na memória pessoal; é efêmero e o lugar é esse |

Exceção: *"revy-trafego não tem `.venv`, use o do portal-gestao"* não é learning
— é **linha de mapa**, e vai para a seção Testes, onde é lida sempre.

Depois da migração a memória pessoal guarda preferências do dono e estado de
conversa; o conhecimento técnico passa a existir no Mac, no Windows e para
subagentes.

## Fora de escopo

- **Diário de trabalho.** Estava no desenho e foi cortado pelo dono em 23/08: o
  `git log` já registra o que foi feito, e o delta que sobrava (caminho
  abandonado, pergunta em aberto) não paga o custo de um registro por tarefa.
  Não re-propor.
- **Quatro skills separadas** (`implementar` / `feature` / `debug` / `research`).
  Avaliado e recusado em 23/08: descrições concorrentes pelo mesmo gatilho, e as
  três primeiras compartilham o mesmo protocolo. Viraram um tronco único que
  roteia — ver "um gatilho, uma porta". Não re-propor.
- **Auto-edição do `SKILL.md`.** O protocolo não se reescreve sozinho; a válvula
  é `propostas.md`. Ver "O loop de auto-melhoria".
- **Protocolo próprio de implementar, propor ou depurar.** Um primeiro rascunho
  desenhou modos ORIENTAR e PROPOR do zero; recusado em 23/08. `brainstorming`,
  `test-driven-development` e `systematic-debugging` já fazem isso e evoluem
  sozinhos — cópia local só envelheceria. A skill roteia. Não re-propor.
- Hook de `UserPromptSubmit` (ver Disparo).
- Reaproveitar `graphify-out/graph.json`: snapshots de 30/07 e 03/08,
  três semanas atrás, com o Modo 2 inteiro construído no meio. Grafo responde
  "como isto se relaciona"; não responde `arquivo:linha`. Segue como
  ferramenta separada de exploração.
- CI rodando `--verificar`. Possível depois; não agora.
- **Mapear `docs/`.** Avaliado e recusado em 23/08: já é roteado pelo `AGENTS.md`
  §3 e pelo `docs/README.md`, não tem símbolo para o `--verificar` ancorar, e é a
  maior pasta de churn do repo (247 toques em 150 commits). Um índice gerado dela
  seria o quarto lugar dizendo onde as coisas estão. Não re-propor.
- **Mapear `shared/` e `site/`.** CSS e HTML estático; pertencem a uma futura
  skill de UI e à do site, não a este mapa.
- **Julgar qual `fly.toml` aponta para app morto.** A tabela lista os 7; dizer
  quais estão destruídos é conhecimento humano e muda com o tempo — vai para o
  README do deploy ou para um learning.
- Qualquer mudança no contrato de `docs/` (segue com três pastas).
- Mapear JS/HTML além da listagem de templates.

## Entregáveis

| Peça | Tamanho |
|---|---|
| `.gitignore` | 3 linhas |
| `AGENTS.md` | 2 edições, 6 linhas: passo 0 no §1 (abre), 4 no §6 (fecha) |
| `SKILL.md` | 67 linhas — tronco, briefing, roteamento, regras e poda |
| `propostas.md` | começa com só o cabeçalho |
| `varredura.py` + `extratores.py` + `gerar_mapa.py` + `cruzamentos.py` | ~600 linhas somadas |
| `test_gerar_mapa.py` | 42 testes, `unittest` da stdlib |
| `mapa/` | gerado, 8 arquivos |
| `learnings/` + `decisoes/` | ~32 arquivos: 20 learnings, 10 decisões, 2 índices |

O `SKILL.md` foi estimado em ~55 linhas contando tronco + briefing + roteamento.
Poda e Regras, que este mesmo spec manda estarem lá, não cabiam nessa conta — o
teto real é ~70.
