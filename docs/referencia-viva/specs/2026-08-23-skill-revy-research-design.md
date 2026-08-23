# Skill `revy-research` — mapa, learnings e diário do monorepo

Data: 2026-08-23 · Status: desenhado, não implementado

## O problema

O repo tem **722 arquivos `.py` de projeto** convivendo com **10.286 quando se
conta os cinco `.venv`**. Uma busca ingênua devolve o código-fonte do FastAPI
em 93% dos casos — aconteceu duas vezes durante o levantamento desta spec.

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
versionada, com quatro dados e um gerador.

```
.claude/skills/revy-research/
  SKILL.md            protocolo (~70 linhas) — única coisa sempre carregada
  gerar_mapa.py       AST estático, 7 extratores, modo --verificar
  test_gerar_mapa.py
  mapa/
    _frescor.json     SHA da geração
    _cruzamentos.md   quem chama quem + suspeitas de órfão
    chatbot-api.md  portal-gestao.md  motor-simulacao.md
    estoque-api.md  revy-trafego.md   catalogo-publico.md
  learnings/  INDEX.md + um arquivo por armadilha
  decisoes/   INDEX.md + um arquivo por escolha do dono
  diario/     2026-08.md, append por tarefa
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
| `diario/` | o agente, ao fechar tarefa | sim, e tudo bem |
| `SKILL.md` | humano, raramente | é protocolo, não conteúdo |

## O gerador

**Decisão de fundo: AST estático da stdlib, nunca importar o app.** Respeita o
invariante "sem import `app` entre produtos", dispensa `.venv`, roda igual no
Mac e no Windows, não pode quebrar nada. ~722 arquivos em 2–4 segundos.

Verificado no levantamento: `APIRouter()` e `include_router()` são chamados sem
`prefix=` em todo o repo, então **o path do decorator é o path real**. Se um
`prefix=` aparecer no futuro, o gerador compõe quando conseguir resolver
estaticamente e marca `?` quando não conseguir — nunca inventa.

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

Duas checagens, ambas rotuladas **suspeitas, não erros**:

1. **Rota órfã de servidor** — um cliente HTTP chama um path que nenhum produto
   declara. É o bug documentado do Modo 2 ("o `chatbot-api` não expõe rota de
   oferta"), cujo efeito prático é *lead que ninguém pega some*.
2. **Função pública sem chamador** — `def` sem underscore, zero referências nos
   722 arquivos. É o caso `criar_sinal_direcionado`.

Ambas geram falso positivo (dispatch dinâmico, path montado por string, função
só consumida por teste). Cada linha sai com o motivo, e o `SKILL.md` fixa a
regra: **suspeita não vira commit; vira pergunta.** Seção que grita lobo é
seção que ninguém lê.

### Frescor por produto

`_frescor.json` guarda o SHA da geração. Ao disparar, a skill roda
`git diff --name-only <sha>..HEAD -- <produto>/`. Vazio → silêncio. Não vazio →
aviso nomeando os arquivos e oferecendo regerar.

A granularidade é por produto de propósito: mexer no `site/` não pode disparar
aviso sobre o mapa do motor. Aviso que dispara à toa é aviso que se aprende a
ignorar.

## Learnings, decisões, diário

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

**Diário** = só o que o `git log` não registra: caminho tentado e abandonado,
comando de teste que realmente rodou com o resultado, pergunta em aberto. Sem
nenhum dos três, o registro é uma linha. Regra explícita no `SKILL.md`:
*diário não repete o `git log`.*

## Disparo

Uma skill dispara por julgamento do agente lendo o `description`. Isso é bom,
não é garantido. Duas camadas:

1. `description` nomeando os verbos reais: codar, corrigir, implementar, mexer
   em qualquer produto do monorepo.
2. Passo 0 no `AGENTS.md` §1 ("Antes de qualquer ferramenta"): **invoque
   `revy-research` antes de procurar código.** Como o `AGENTS.md` já é lido e
   obedecido em todo boot, isso torna o disparo determinístico sem hook.

Terceira camada disponível e **não adotada**: hook `UserPromptSubmit` injetando
a instrução em todo turno. Custa tokens em toda mensagem; só se as duas
primeiras falharem na prática.

## Protocolo do `SKILL.md`

```
1. Identifique o produto (1 dos 6). Tarefa que cruza dois: PARE e diga.
2. Cheque o frescor do mapa daquele produto.
3. Abra mapa/<produto>.md.
4. Leia learnings/INDEX.md; abra só os de gatilho compatível (0, 1 ou 2).
5. Vai PROPOR algo? Leia decisoes/INDEX.md antes.
6. Só agora abra código.
7. Ao fechar: teste do produto, uma entrada no diário, e um learning
   SE algo surpreendeu.
```

Custo por disparo: `SKILL.md` (~70) + `mapa/<produto>.md` (~150) + `INDEX.md`
(~40) ≈ **260 linhas** para saber onde tudo está, contra 2.609 de um `main.py`
que ainda não responde a pergunta.

## Verificação

`gerar_mapa.py --verificar` **reabre cada `arquivo:linha` do mapa e confere que
a linha contém o símbolo prometido.** Uma entrada fora do lugar → exit 1. Isso
transforma "o mapa está desatualizado?" de opinião em teste, e torna auditável a
promessa de que o mapa não mente. Cabe no `AGENTS.md` §6.

`test_gerar_mapa.py`, três testes:

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

- Hook de `UserPromptSubmit` (ver Disparo).
- Reaproveitar `graphify-out/graph.json`: snapshots de 30/07 e 03/08,
  três semanas atrás, com o Modo 2 inteiro construído no meio. Grafo responde
  "como isto se relaciona"; não responde `arquivo:linha`. Segue como
  ferramenta separada de exploração.
- CI rodando `--verificar`. Possível depois; não agora.
- Qualquer mudança no contrato de `docs/` (segue com três pastas).
- Mapear JS/HTML além da listagem de templates.

## Entregáveis

| Peça | Tamanho |
|---|---|
| `.gitignore` | 3 linhas |
| `AGENTS.md` §1 | 1 linha |
| `SKILL.md` | ~70 linhas |
| `gerar_mapa.py` | ~350 linhas |
| `test_gerar_mapa.py` | ~60 linhas |
| `mapa/` | gerado, 8 arquivos |
| `learnings/` + `decisoes/` | ~26 arquivos migrados |
| `diario/2026-08.md` | começa vazio |
