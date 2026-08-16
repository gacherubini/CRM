# Portal e Control para Postgres — banco `revy` com schema por produto (design)

Data: 2026-08-16 · Produtos: **Revy Loja** (`portal-gestao`) e **Revy Control** (`revy-trafego`)
Estado: **desenhado, não implementado**
Calibrado contra o main em **`fd56092`** — já inclui a leva do Financeiro (`despesas_fixas_loja`,
`0024_venda_excluida`, `0025`, `0019_financeiro_modulo`). Migration nova nos produtos depois
disso obriga a reconferir as contagens de §1 e §4.4.

Tira os dois últimos produtos do SQLite e os coloca num banco Postgres novo dentro do
`suite-pg`, cada um no seu schema. Não é faxina: é o que desbloqueia RLS, simplifica a
consulta ad-hoc, e abre o caminho para acabar com a duplicação de schema entre produtos.

---

## 1. O estado de hoje, medido

Levantado em 16/08 do código e da infra real (`fly status`, `fly pg db list`,
`fly volumes snapshots list`), não de plano antigo.

### Os cinco bancos

| Produto | Tabelas | Migrations | Onde | Engine |
|---|---|---|---|---|
| Revy Control | 31 | 19 | `/data/revy-trafego/revy_trafego.db` | SQLite |
| Revy Loja | 26 | 25 | `/data/portal/portal.db` | SQLite |
| Chatbot | 13 | 19 | `suite-pg`, banco `chatbot` | Postgres |
| Estoque | 12 | 10 | `suite-pg`, banco `estoque` | Postgres |
| Motor | 12 | 14 | `suite-pg`, banco `motor` | Postgres |

`fly pg db list -a suite-pg` mostra ainda um banco **`evolution`** — o WhatsApp também
mora lá. São **quatro** consumidores do `suite-pg` hoje, não três.

### A infra

- `suite-pg`: `postgres-flex 18.1`, **shared-1x, 512 MB**, volume de **1 GB**, primary
  única em `iad`. Esta máquina **já teve OOM** em 20/07 quando estava em 256 MB e derrubou
  o lab inteiro — foi por isso que subiu para 512.
- Tamanho do dado a migrar: `portal.db` **564 KB**, `revy_trafego.db` **872 KB**.
  1,4 MB somados, num volume de 1 GB. Volume de dado é irrelevante aqui.
- **Snapshots**: os dois volumes (`suite-pg` e `app2037`) têm snapshot diário automático
  com retenção de 5 dias. A proteção **não piora** com a mudança — é o mesmo mecanismo.

### O código é portável

- **Zero SQL específico de engine.** Todos os `strftime` do Portal são do Python
  formatando texto para exibição, nenhum é função SQL.
- **Um único `text()` cru** no Portal inteiro: `SELECT 1 FROM revy_trafego_event_outbox
  LIMIT 1`. Portável.
- **53 colunas `DateTime(timezone=True)`** — declaração correta, vira `TIMESTAMPTZ`, e o
  código já grava com `datetime.now(timezone.utc)`. É o caso bem-comportado.
- **12 `batch_alter_table`** nas migrations do Portal. É a gambiarra do Alembic para o
  `ALTER TABLE` limitado do SQLite, mas em Postgres o Alembic detecta o dialeto e emite
  `ALTER TABLE` direto. **Não é bloqueador.**
- **11 colunas `Numeric`** (8 no Portal, 3 no Control) — ver §3.3, é o único ponto que
  exige conferência de valor.

### O custo

Nenhuma linha nova na fatura: o `suite-pg` já existe, é always-on, e vai receber 1,4 MB num
volume de 1 GB já provisionado. O volume do `app2037` continua existindo do mesmo jeito
(guarda mídia do Estoque, screenshots do Motor, `catalogo.db`), então também não há
economia — é neutro.

O único custo plausível é **RAM**: se 512 MB não aguentar o pool de conexões de mais dois
serviços, subir para 1 GB custa poucos dólares por mês. Ver §3.5.

---

## 2. Decisões do dono (16/08)

| # | Decisão |
|---|---|
| D1 | Banco **`revy`** novo no `suite-pg`, com **schema por produto** (`portal`, `control`) — não um 5º banco |
| D2 | Janela de corte de **30–60 min**, avisada. Sem dual-write, sem zero-downtime |
| D3 | **Portal e Control migram juntos**, num corte só |
| D4 | Backup: não estava confirmado; **verificado neste design** (§1) e reforçado com `pg_dump` explícito |

### Por que schema e não banco (D1)

Porque **Postgres não faz join entre bancos diferentes**. Colocar o Portal como quinto banco
repetiria exatamente o desenho que motivou esta conversa: o cadastro de loja em cinco
lugares e 10 nomes de tabela duplicados entre produtos continuariam impossíveis de
reconciliar sem outra migração depois.

Schema separado dá a mesma fronteira, e uma **mais forte** do que a de hoje: hoje a
separação entre produtos é um comentário no `AGENTS.md` dizendo "não faça import entre
produtos" — sistema de honra, sem mecanismo. Uma role do Postgres com `USAGE` só no próprio
schema é o banco recusando.

E preserva a opção de separar depois: um schema sai para banco próprio com um `pg_dump -n`
no dia em que um produto precisar escalar sozinho.

### Por que os dois juntos (D3)

Com D1, migrar junto fica mais coerente do que separado: os dois acabam no mesmo banco, o
fork de 6 tabelas entre Portal e Control passa a ser visível lado a lado (`portal.campanhas`
e `control.campanhas` coexistem sem colidir, cada uma no seu schema), e é **uma** janela de
corte em vez de duas.

O custo aceito: o Control traz 31 tabelas e 19 migrations próprias para validar no mesmo
corte.

---

## 3. Os perigos

Esta seção é o coração do documento. Migrar 1,4 MB é fácil; o que segue não é.

### 3.1 A semântica de concorrência muda — o perigo nº 1

**SQLite serializa escrita. Postgres não.** Hoje o banco do Portal só admite um escritor por
vez, e isso vem escondendo corridas entre os cinco workers de fundo que rodam no mesmo
processo. No Postgres eles passam a escrever **de verdade ao mesmo tempo**.

Pontos a auditar antes do corte, porque nenhum deles usa `SELECT ... FOR UPDATE` nem
constraint de unicidade que os proteja:

| Ponto | Risco concreto |
|---|---|
| `_checar_rate_limit` (`copiloto/acoes.py`) | conta ações da última hora e decide; dois cliques simultâneos passam ambos |
| `copiloto_turnos_job.run_once` | pega lote de `pendente` e processa; duas instâncias pegariam o mesmo turno |
| `expirar_orfaos` | varre `executando` e falha; corre com o worker que está escrevendo o resultado |
| `meta_capi_outbox` / `revy_trafego_event_outbox` | entrega de evento sem lock vira entrega dupla |
| `copiloto_purge_job` | apaga por idade enquanto outro escreve |

Isto **não é regressão da migração** — é bug latente que o SQLite vinha mascarando. Mas ele
aparece no dia do corte, e quem não souber disso vai culpar o Postgres.

**Mitigação:** auditar os cinco pontos e acrescentar `SELECT FOR UPDATE SKIP LOCKED` (ou
constraint de unicidade) onde a corrida for real, **antes** do corte. Isso é parte do
escopo, não item futuro.

### 3.2 Postgres é estrito onde o SQLite é frouxo

O SQLite aceita string numa coluna inteira, número em coluna de texto, e data em formato
livre. O Postgres recusa. Dado torto que está no arquivo há semanas **só aparece na hora da
carga** — e a carga é dentro da janela de corte.

**Mitigação:** o ensaio (§4.1) roda a carga inteira contra uma cópia, dias antes. Qualquer
linha que o Postgres recusar aparece ali, com tempo de consertar.

### 3.3 Dinheiro: `Numeric` sobre SQLite é float

São **11 colunas `Numeric`** entre os dois produtos — 8 no Portal (`preco_venda`,
`custo_veiculo`, `valor_alvo`, `valor_novo`, `valor_mensal` e três `valor`) e 3 no Control.
O SQLite **não tem tipo numérico exato**: o SQLAlchemy guarda como float e reconverte para
`Decimal` na leitura. Isso significa que **pode já existir arredondamento** no arquivo atual.

`valor_mensal` (despesa fixa) entrou com a leva do Financeiro em `fd56092` — a DRE depende
dela, então é a coluna cuja divergência apareceria mais rápido para o dono.

A migração carrega fielmente o que está lá — não corrompe, mas também **não conserta**.

**Mitigação:** a validação do corte compara, além da contagem de linhas por tabela, a **soma
de cada coluna de dinheiro antes e depois, exigindo igualdade ao centavo**. Se não bater, o
corte não é liberado. E fica registrado que, a partir do Postgres, dinheiro passa a ser
guardado com tipo exato de verdade — melhoria por si só.

### 3.4 O domínio de falha passa a ser compartilhado

Hoje, se o `suite-pg` cai, o Chatbot, o Estoque, o Motor e a Evolution caem, mas a Revy Loja
em SQLite ainda serve alguma coisa. Depois da migração, `suite-pg` fora = **tudo** fora.

Isso é uma perda real e não tem mitigação barata — o `suite-pg` é primary única, sem
réplica. Aceito conscientemente porque os seis serviços já sobem, caem e são implantados
juntos no `app2037`: o domínio de falha já é quase todo compartilhado, e esta mudança fecha
a última fresta.

Registrado aqui para não ser descoberto num incidente.

### 3.5 RAM e conexões numa máquina de 512 MB

Cada conexão do Postgres custa RAM. O pool padrão do SQLAlchemy é 5 + 10 de overflow **por
engine** — até 15 conexões por serviço. Dois serviços novos podem somar 30 conexões numa
máquina que já serve quatro bancos e que **já teve OOM**.

**Mitigação:** `pool_size` e `max_overflow` explícitos e pequenos para os dois serviços, em
vez do default. Medir `pg_stat_activity` depois do corte. Subir para 1 GB se precisar — são
poucos dólares e é reversível.

### 3.6 `alembic_version` colide se ninguém cuidar

O Portal usa a tabela padrão `alembic_version`. O Control já usa
`alembic_version_revy_trafego` — foi preparado para coabitar. No mesmo **banco**, se as duas
caírem no schema `public`, os dois produtos brigam.

**Mitigação:** `version_table_schema` no `env.py` de cada produto, apontando para o próprio
schema. A tabela de versão do Portal vive em `portal.alembic_version`; a do Control, em
`control.alembic_version_revy_trafego`.

### 3.7 `search_path` errado é o bug mais silencioso possível

Se a conexão não apontar para o schema certo, o SQLAlchemy cria/lê tabela no `public` e tudo
parece funcionar — até alguém notar que há duas cópias.

**Mitigação:** `search_path` fixado na conexão de cada serviço (via `options` na URL ou
`connect_args`), e um teste de boot que falha se o schema efetivo não for o esperado.

### 3.8 O ponto de não-retorno

Depois do corte, escrita feita no Postgres **se perde** se houver rollback para o SQLite.
Com janela de 30–60 min isso é aceitável, mas exige uma regra explícita:

- Os arquivos `.db` **não são apagados** no corte. Ficam no volume, intocados, por pelo
  menos 30 dias.
- O rollback é remover o secret `PORTAL_DATABASE_URL` / `REVY_TRAFEGO_DATABASE_URL` e
  redeployar — o `[env]` do toml volta a valer e o arquivo antigo reassume.
- A partir do momento em que a primeira venda for confirmada no Postgres, rollback deixa de
  ser gratuito. Esse instante precisa ser anunciado.

### 3.9 A cadeia de migrations tem que estar estável e publicada

**Resolvido em 16/08:** a leva do Financeiro, que estava com 26 arquivos abertos durante o
desenho deste spec, foi commitada em `fd56092` e a árvore ficou limpa. Este spec já está
calibrado contra ela.

O que continua valendo como pré-requisito: **o corte só acontece sobre um main publicado**.
Migrar com migration que existe só na árvore local faz o banco novo nascer com um schema
que não está no git — e o `fly deploy` usa a árvore local, não o commit, então prod e repo
divergiriam com o banco novo no meio. Antes do corte: `git push`, e conferir que
`origin/main` bate com o `HEAD` local.

Migration nova em qualquer um dos dois produtos depois de `fd56092` obriga a reconferir as
contagens de §1 e a lista de validação de §4.4.

### 3.10 O isolamento por role hoje pode ser só convenção

`fly pg db list -a suite-pg` lista **todas as roles em todos os bancos**. Isso pode ser
apenas o formato de saída do comando, ou pode significar que a role `chatbot` alcança o
banco `motor` — onde estão as credenciais bancárias.

**Verificar antes**, com `\du` e `\l` no cluster. Se o isolamento atual for só convenção, o
desenho de roles deste spec (§4.2) conserta isso de passagem para os dois produtos novos, e
o restante vira card próprio.

---

## 4. O plano

### 4.1 Ensaio, dias antes

Contra uma **cópia** dos dois `.db`, num banco descartável:

1. criar banco e schemas
2. rodar `alembic upgrade head` dos dois produtos, do zero
3. carregar as linhas
4. rodar a validação (§4.4)
5. **cronometrar**

O ensaio é o que transforma "30–60 min" de estimativa em número. E é onde §3.2 aparece com
tempo de conserto.

### 4.2 Banco, schemas e roles

```
banco  revy
├── schema portal    role portal_app    USAGE + CRUD só em portal
└── schema control   role control_app   USAGE + CRUD só em control
```

Nenhuma das duas roles enxerga o schema da outra. `public` fica vazio, e nenhuma das duas
tem permissão de criar nele — assim um `search_path` errado (§3.7) falha alto em vez de
criar tabela fantasma.

### 4.3 O corte

1. anunciar a janela
2. `pg_dump` do `suite-pg` inteiro (backup lógico, além do snapshot de volume)
3. parar o `app2037`
4. copiar os dois `.db` do volume para fora, como cópia extra
5. `alembic upgrade head` dos dois produtos contra `revy`
6. carregar as linhas
7. **validar (§4.4)** — se falhar, aborta aqui e nada mudou
8. setar os secrets `PORTAL_DATABASE_URL` e `REVY_TRAFEGO_DATABASE_URL`
9. subir, conferir `/healthz` e o `/trafego/health/ready`
10. liberar o acesso

Os passos 1–7 acontecem **sem nada mudar em produção**. O ponto de virada é o 8.

### 4.4 A validação que libera o corte

| Conferência | Critério |
|---|---|
| contagem de linhas, tabela a tabela | igual nos dois lados, 57 tabelas |
| soma de cada coluna `Numeric` | igual **ao centavo** |
| `MAX(criado_em)` das tabelas de evento | igual |
| `alembic current` dos dois produtos | head esperado, no schema certo |
| schema efetivo da conexão | `portal` e `control`, nunca `public` |

Qualquer divergência aborta o corte. O `app2037` volta a subir apontando para os `.db`,
que não foram tocados.

### 4.5 Depois do corte

- medir `pg_stat_activity` e a RAM do `suite-pg` por alguns dias (§3.5)
- `pg_dump` do banco `revy` entrando na rotina, porque snapshot de volume é
  crash-consistent do cluster inteiro, não backup lógico por banco
- os `.db` ficam no volume por 30 dias (§3.8)

---

## 5. Capacidade e multi-loja — o que esta migração NÃO resolve

Levantado em 16/08 a pedido do dono, que perguntou se a arquitetura aguenta muitas lojas ao
mesmo tempo. **A resposta curta é que o desenho de banco não é o gargalo.** Uma linha por
loja discriminada por `loja_slug`, com schema compartilhado, é o padrão normal de SaaS e
aguenta centenas de lojas. O que quebra primeiro é outra coisa — e a maior parte disso
**continua quebrada depois desta migração**.

Esta seção existe para que a migração não passe a falsa sensação de que multi-loja está
resolvido.

### 5.1 Os muros, em ordem de quem chega primeiro

| # | Muro | Medido ou estimado | Esta migração resolve? |
|---|---|---|---|
| 1 | **SQLite admite um escritor por vez** no arquivo inteiro — não por tabela, não por loja | fato do engine | **Sim, direto** |
| 2 | **Worker de sinais é sequencial**: `for loja_slug in lojas_ativas(db)`, thread única, ciclo de 30 min | medido no código | Não — é código |
| 3 | **Teto da FIPE é POR LOJA** (10/ciclo), contra API comunitária sem SLA | medido no código | Não |
| 4 | **Fan-out de 3–4 idas HTTP por página**, com `listar_leads()` chamado três vezes sem memoização | medido no código | Não — só sumiria se os schemas fossem unificados |
| 5 | **Cadastro de loja em 6 tabelas de 5 produtos** — cada loja nova é uma chance de provisionamento parcial | medido | Não, mas fica **possível** de resolver |
| 6 | **Isolamento depende de 28 `WHERE loja_slug`** estarem corretos | levantado na Fase 5 | Não, mas **habilita** o RLS que resolve |

### 5.2 Por que o muro nº 1 muda a urgência desta leva

Com 3 lojas ninguém percebe a serialização do SQLite. Com 30 lojas vendendo, lançando
despesa e recebendo lead ao mesmo tempo, **toda escrita do Portal entra numa fila única** —
e não há ajuste de código que resolva, porque é o engine.

Isso reclassifica esta migração: ela não é "melhoria que desbloqueia RLS e conserta o tipo
do dinheiro". Ela é **pré-requisito de multi-loja**. Antes de vender a segunda dúzia de
lojas, isto precisa estar feito.

### 5.3 O número que falta medir

O muro nº 2 tem um teto que depende de um número que ninguém mediu: **quanto tempo
`avaliar_loja` leva com uma loja real**.

A conta é direta. O ciclo é sequencial num intervalo de 1800s:

- a 15s por loja → o ciclo comporta ~120 lojas
- a 60s por loja (FIPE lenta: são até 10 chamadas com timeout de 8s cada) → ~30 lojas
- acima disso, um ciclo não termina antes de o próximo começar, e os sinais atrasam sem
  ninguém notar

**Medir isso é uma linha de log e vale mais que qualquer estimativa desta seção.** Enquanto
não for medido, não se sabe se o worker aguenta 20 ou 120 lojas — uma diferença de seis
vezes na hora de decidir se ele precisa ser paralelizado.

### 5.4 Fairness, não só capacidade

O worker de turnos pega os pendentes em **FIFO global** (`limit(lote)`, padrão 3, a cada
segundo). A capacidade é folgada, mas a fila é única para todas as lojas: uma loja
disparando muitas perguntas atrasa as outras. Com poucas lojas é irrelevante; com muitas,
vira "o Copiloto da minha loja está lento por culpa de outro cliente".

Não é problema desta leva, mas é o tipo de coisa que só aparece com escala e que ninguém
lembra de ter desenhado.

### 5.5 O limite que nenhum código resolve

`suite-pg` é **uma máquina shared-1x de 512 MB, primary única, sem réplica**, e já teve OOM
uma vez (§1). Muitas lojas em produção pedem mais RAM e, mais cedo ou mais tarde, uma
réplica de leitura. Isso é dinheiro e configuração, não arquitetura — mas depois desta
migração **todo o produto** passa a depender dessa máquina (§3.4), então o custo de ela cair
sobe junto com o número de lojas.

---

## 6. O que este spec deliberadamente não faz

- **Não consolida as tabelas duplicadas.** `portal.campanhas` e `control.campanhas`
  continuam sendo duas tabelas com as mesmas 20 colunas. Ficam no mesmo banco, visíveis lado
  a lado, prontas para a leva seguinte — que é onde essa dívida se paga.
- **Não unifica o cadastro de loja**, hoje em 6 tabelas espalhadas por 5 produtos.
- **Não liga RLS.** Este spec só torna o RLS possível; a Parte B da Fase 5 passa a ser
  implementável e vira leva própria.
- **Não mexe no Chatbot, Estoque, Motor nem Evolution.** Eles seguem em bancos próprios.
- **Não implementa a consulta ad-hoc**, adiada por decisão do dono em 16/08. O spec dela
  (`2026-08-16-copiloto-consulta-adhoc-design.md`) **encolhe** depois desta migração:
  conexão `mode=ro`, authorizer do SQLite, progress handler e o PRAGMA de WAL saem todos de
  cena, substituídos por role read-only + `statement_timeout`.

---

## 7. Sequência e pendências

Decidido em 16/08:

1. **Card próprio de concorrência** (§3.1), antes do corte. São correções válidas por si
   só — melhoram o código mesmo se a migração nunca acontecer — e podem ser testadas e
   deployadas ainda no SQLite, sem janela. Chegar no dia do corte com isso fechado remove a
   maior fonte de surpresa.
2. **Publicar o main** (§3.9) e conferir `origin/main == HEAD`.
3. **Ensaio** contra cópia (§4.1), que transforma "30–60 min" em número medido.
4. **Corte** (§4.3).

Fora da leva, mas barato e informativo — pode ser feito a qualquer momento, inclusive antes:

- **Medir `avaliar_loja` com uma loja real** (§5.3). É uma linha de log, e ela decide se o
  worker de sinais aguenta 20 ou 120 lojas. Nenhuma outra estimativa deste spec vale tanto.

Depois do corte, os muros 2 a 6 de §5.1 continuam de pé e viram fila própria. A migração é
pré-requisito de multi-loja, **não** a solução dele.

Pendências que ainda precisam do dono:

- **Nomes**: `revy` / `portal` / `control` — confirmar antes de existirem no banco.
  Renomear schema depois é migração nova.
- **Verificar o isolamento de roles atual** (§3.10) com `\du` e `\l`. Se a role do Chatbot
  alcança o banco do Motor hoje, isso vira card próprio e sobe de prioridade.
