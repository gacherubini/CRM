# Copiloto — consulta ad-hoc ao banco do Portal (design)

Data: 2026-08-16 · Produto: **Revy Loja** (`portal-gestao`) · Estado: **desenhado, não implementado**

O Copiloto hoje só alcança dado por sete funções de recorte fixo. Este design dá a ele
uma oitava: escrever `SELECT` contra o banco do próprio Portal, com o esquema visível no
prompt, sem que uma consulta livre consiga enxergar linha de outra loja nem travar a Loja.

---

## 1. O que foi levantado antes de desenhar

Quatro achados do código e da infra que sustentam as decisões abaixo. Nenhum veio de plano
antigo — todos de leitura do repo e de `fly secrets list -a app2037` em 16/08.

**São cinco bancos, não um.** `suite-pg` é um servidor Postgres com **um banco por
serviço**: `CHATBOT_DATABASE_URL`, `ESTOQUE_DATABASE_URL` e `MOTOR_DATABASE_URL` existem
como secrets, com três digests diferentes entre si. `PORTAL_DATABASE_URL` **não existe**
nos 60 secrets do `app2037`, então vale o `[env]` do toml: o Portal roda **SQLite** em
`/data/portal/portal.db`. Revy Control idem, em arquivo próprio.

**E não é acidente de configuração, é estrutural.** Chatbot, Estoque e Portal cada um
define sua própria tabela `loja_operacional_projecao`, e os três carimbam a mesma
`alembic_version`. Apontar os três para o mesmo banco quebraria o `alembic upgrade head`
do `entrypoint-app.sh` na segunda migração. Só o Revy Control está preparado para
coabitar (usa `alembic_version_revy_trafego`) — e o `run-revy-trafego.sh` ainda assim diz:
*"Banco próprio: vendas chegam por projeção HTTP/outbox; nunca ler o schema do Portal."*

**Consequência direta:** a consulta ad-hoc alcança venda, meta, campanha e atendimento.
**Nunca veículo e nunca lead** — esses vivem em outro motor de banco, em outro processo, e
só chegam por HTTP. Quem quiser "quais Onix abaixo de 80 mil estão parados" precisa de
filtros ricos na ferramenta de Estoque, que é card separado (§9).

**Não existe `PRAGMA journal_mode=WAL` em lugar nenhum.** Com o journal padrão, leitor e
escritor se bloqueiam no mesmo arquivo. O processo do Portal já roda cinco threads de
fundo nesse arquivo (turnos com lote de 3, sinais, purge, retry do CAPI, sync de gasto).
Uma consulta ad-hoc pesada trava os cinco. **Este é o risco número um deste design, acima
do vazamento entre lojas** — e é o risco que o Office Timesheet não teve que enfrentar,
porque lá o ad-hoc roda em Postgres com role própria e `statement_timeout`.

**`psycopg` já está em `requirements.txt`.** O Portal é agnóstico de engine via SQLAlchemy;
só está em SQLite hoje. Nada neste design pode assumir dialeto fixo.

---

## 2. Decisões do dono (16/08) — não reabrir sem ele

| # | Decisão | Consequência |
|---|---|---|
| D1 | Ad-hoc **só no banco do Portal**; veículo e lead seguem por HTTP | respeita "cada produto tem banco próprio" (AGENTS.md §2) |
| D2 | **PII é visível** — telefone e e-mail entram no esquema e no resultado | reverte constraint anterior, ver §3 |
| D3 | **Todos que já entram no Copiloto** rodam ad-hoc (dono, gerente, `admin_plataforma`) | nenhuma distinção nova de papel; o gate segue na porta |
| D4 | **WAL na mesma leva**, com snapshot do volume antes | não vira card separado |
| D5 | **As 7 funções continuam**; ad-hoc é o que sobra quando nenhuma cobre | preserva cobertura e comparação de período |
| D6 | Resultado aparece como **tabela renderizada pelo servidor** + texto do modelo | linhas vêm do banco, não da prosa |
| D7 | Esquema **estático no bloco estável** do prompt, não tool sob demanda | ~1.500 tokens, descontados pelo cache de prefixo |

### Sobre D7, para quem for revisar o custo

11 tabelas, 123 colunas. Um esquema compacto é ~1.500 tokens. A `prompt.py` já monta o
system prompt com o bloco estável primeiro **exatamente** para o cache do provedor
descontar o prefixo repetido. A ~US$ 0,14/M de entrada, isso é US$ 0,0002 no primeiro
turno da conversa e um décimo disso nos seguintes. Uma tool `descrever_esquema` sob demanda
economizaria esses centavos e gastaria **uma iteração do turno** em quase toda pergunta
ad-hoc — moeda muito mais cara que o token.

---

## 3. A constraint de PII foi revertida — de propósito

A Fase 2 do Copiloto travou "Sem PII no prompt" como constraint global, e o card da Fase 6
usou exatamente essa constraint para tirar a simulação do escopo (CPF como parâmetro de
ferramenta entraria no contexto enviado ao provedor).

**D2 sobrepõe essa constraint para o ad-hoc.** O raciocínio do dono: o telefone do cliente
é dado da própria loja, que ele já alcança navegando o Atendimento.

Isto está escrito aqui para o próximo agente **não "corrigir" isso achando que é bug**. Duas
coisas que continuam valendo e não foram revertidas:

- A constraint segue de pé para **CPF e data de nascimento** — nada neste design abre
  simulação bancária, e `redefinicoes_senha` / `convites_acesso_loja` / hash de senha
  ficam fora da allowlist de tabela e de coluna.
- **O log não recebe PII** (§7). Ver o telefone na tela é decisão de produto; deixá-lo
  gravado em log estruturado é outro assunto, e esse não foi decidido.

---

## 4. Arquitetura

Quatro módulos novos em `app/loja/copiloto/`, mais uma tool no catálogo existente.

```
esquema.py    declara tabelas, colunas e COMO cada tabela se escopa por loja
              ├── esquema_para_prompt()      → texto no bloco estável do system prompt
              └── subconsulta_escopada(t, l)  → o SELECT que o reescritor injeta
sql_guard.py  parse → valida → REESCREVE a AST → envelopa com LIMIT
sql_exec.py   conexão read-only própria, authorizer, progress handler, cap de linhas
tools.py      (existente) ganha a ferramenta `consultar_dados`
```

A regra que sustenta o resto: **`esquema.py` é fonte única**. O texto que promete colunas
ao modelo e a subconsulta que recorta as linhas saem da mesma estrutura. Duas listas
mantidas em paralelo divergem — é o mesmo motivo pelo qual o `enum` de `propor_acao` é
derivado de `ACOES_PERMITIDAS` em vez de escrito à mão.

### 4.1 Como cada tabela se escopa

Nem toda tabela tem `loja_slug`. `venda_custos_diretos` não tem. Então cada entrada
declara o caminho explicitamente:

| Tabela | Escopo |
|---|---|
| `vendas`, `metas`, `atendimento_atribuicoes`, `funil_eventos`, `campanhas`, `campanha_gastos`, `usuarios`, `loja_operacao_auditoria`, `copiloto_acao`, `loja_operacional_projecao` | `direto("loja_slug")` |
| `venda_custos_diretos` | `via("venda_id", "vendas", "id")` |

Fora da allowlist, por serem credencial ou ruído de infraestrutura:
`redefinicoes_senha`, `convites_acesso_loja`, `meta_capi_outbox`, `revy_trafego_event_outbox`,
`pixel_capi_auditoria`, `copiloto_conversa`, `copiloto_turno`, `copiloto_sinal*`,
`pessoa_revy_projetada`, `vinculo_loja_pessoa`. Em `usuarios`, a coluna de hash de senha
fica fora da lista de colunas.

`copiloto_acao` entra e `copiloto_turno` não sai por capricho: a mesma linha que a política
de retenção já traça. Ação é registro de alteração comercial (quem mudou o preço de qual
veículo, de quanto para quanto) e por isso o purge não a apaga; turno é conteúdo de
conversa, apagado em 30 dias. O ad-hoc segue essa divisão — não é papel dele deixar o
modelo ler conversa antiga do próprio Copiloto.

> `metas` ganhou peso depois de `d604a4f`: a página Resultado perdeu o bloco
> Metas/Atingimento, então a consulta ad-hoc passa a ser o único caminho para perguntar
> sobre meta pelo produto.

---

## 5. O reescritor (`sql_guard.py`)

Dependência nova: **`sqlglot`** — dialeto lido de `settings.database_url`, nunca fixo, para
não quebrar no dia em que o Portal for para o `suite-pg`.

Fluxo, nesta ordem:

1. parse; exige **exatamente um** statement
2. exige `SELECT` na raiz — recusa DML, DDL, `PRAGMA`, `ATTACH`
3. toda referência de tabela que não seja CTE do próprio SELECT precisa estar na allowlist
4. **transform**: cada referência de tabela vira a subconsulta escopada
5. envelopa: `SELECT * FROM (<sql>) LIMIT n`

O passo 4 é a decisão central deste design. O modelo escreve `FROM vendas`; o guard entrega
ao banco:

```sql
FROM (SELECT id, preco_venda, vendedor_email, criado_em
        FROM vendas WHERE loja_slug = :loja) AS vendas
```

Depois disso **o que o modelo escreve no WHERE é irrelevante**. `WHERE 1=1 OR loja_slug =
'outra'` não devolve nada de outra loja, porque `vendas` já não é a tabela — é o recorte
dela. O mesmo mecanismo resolve coluna de graça: a subconsulta lista as colunas permitidas,
então `SELECT *` já vem recortado.

### Por que não a abordagem do Office Timesheet

Lá o `sqlGuard.js` valida e recusa: allowlist de tabela, `LIMIT` forçado, e a fronteira real
é a role `agent_readonly` do Postgres. **Validar não basta aqui**, por duas razões:

- Lá o banco é de um cliente só; não existe "linha de outra loja" para vazar. Aqui existe.
- Exigir `loja_slug = ?` no WHERE e conferir por inspeção de AST é allow/deny enganável —
  `OR 1=1`, `LEFT JOIN` com só uma ponta filtrada, subquery correlacionada, CTE. O próprio
  comentário do `sqlGuard.js` diz que allow/deny enganável é finding de segurança. Provar
  que um WHERE arbitrário *implica* isolamento não se faz com inspeção de árvore.

Reescrever remove a necessidade da prova.

---

## 6. As três camadas físicas (`sql_exec.py`)

O reescritor é lógica, e lógica tem bug. Abaixo dele, uma conexão que **não passa pelo
engine do app** (a sessão do app é read-write, de propósito):

1. **`sqlite3.connect("file:<path>?mode=ro", uri=True)`** — o driver recusa escrita. Não é
   o nosso código dizendo não; é o SQLite.
2. **`set_authorizer`** — nega toda operação que não seja leitura em tabela da allowlist, e
   nega `PRAGMA`/`ATTACH`. Roda dentro do SQLite, na compilação da query, então pega o que
   o parser deixar passar.
3. **`set_progress_handler`** abortando em ~1s. SQLite não tem `statement_timeout`, e sem
   isso a contenção do §1 vira incidente.

Mais o cap de linhas (200, como no Office Timesheet) e um cap de bytes do resultado, porque
200 linhas de `vendas` com 19 colunas estouram o teto de 20k tokens do turno sozinhas.

Se o Portal um dia for para o `suite-pg`, o equivalente é `SET TRANSACTION READ ONLY` +
`statement_timeout` + role própria — o módulo isola essa escolha atrás de uma função só.

---

## 7. Integração com o turno

A tool `consultar_dados` entra no catálogo com `esforco_sugerido="high"` (escrever SQL é a
tarefa mais difícil do catálogo) e descrição mandando usá-la **só quando nenhuma das sete
cobre a pergunta**.

Recusa do guard volta como mensagem `role=tool` com o motivo, e o modelo reescreve — mesmo
mecanismo do nudge de JSON quebrado que o runner já tem. O motivo é útil ao modelo ("tabela
`x` não está disponível; as que estão são…") e não precisa esconder mecanismo do usuário:
com D6 a tabela aparece na tela, então o dono já sabe que houve consulta.

**`max_iteracoes` sobe de 4 para 6, mas só quando a flag está ligada.** Errar SQL e corrigir
gasta duas voltas; com 4 o turno morre em `max_iteracoes` antes de responder. Amarrar o
teto à flag (e não subir global) mantém **zero mudança de comportamento** em qualquer turno
com a flag desligada. Deadline de 45s e teto de 20k tokens ficam iguais e seguram o pior
caso.

### Tela

O `Passo` do runner já carrega o campo `extra` — genérico de propósito, hoje usado pelo
cartão de ação. A tabela vai por ali: `{colunas, linhas, truncado}`. O JS ganha
`criarTabelaResultado` ao lado do `criarCartao` existente, com o mesmo
`createElement`/`textContent` e **nunca `innerHTML`**, reusando o CSS de tabela da leva de
markdown.

O ponto que importa: as linhas vêm do banco. O modelo comenta por cima; se ele resumir
errado, a tabela ao lado o desmente.

### Auditoria

Log estruturado com loja, usuário, tabelas tocadas, número de linhas e duração — **com o
SQL normalizado, literais trocados por `?`**. Se o modelo escrever `WHERE telefone =
'11...'`, esse número não entra no log (§3).

### Configuração

| Variável | Default | O que controla |
|---|---|---|
| `REVY_LOJA_COPILOTO_SQL_ENABLED` | `0` (off) | liga a tool e o bloco de esquema no prompt |
| `PORTAL_COPILOTO_SQL_MAX_LINHAS` | `200` | cap de linhas do resultado |
| `PORTAL_COPILOTO_SQL_TIMEOUT_MS` | `1000` | corte do progress handler |

Flag de rollout default OFF, conforme invariante do AGENTS.md §5.

---

## 8. WAL

`PRAGMA journal_mode=WAL` + `synchronous=NORMAL` no boot, por listener do SQLAlchemy, só
quando o dialeto é sqlite. Vale para o Portal inteiro, não só para o Copiloto: os cinco
workers de fundo param de disputar o arquivo.

Cria `-wal` e `-shm` no volume. **Snapshot do volume do `app2037` antes do deploy** — é
mudança de formato de journal num banco de produção, e o AGENTS.md já exige snapshot antes
de deploy que altera schema. É a primeira tarefa do plano, deployada e observada antes de a
flag do SQL ser ligada, mesmo estando na mesma leva.

---

## 9. Fora de escopo

Decidido em 16/08, cada um vira card curto na fila depois:

- **Filtros ricos na ferramenta de Estoque** (marca, faixa de preço, dias parado). É o que
  responde "quais Onix abaixo de 80 mil" — e é parâmetro de API do Estoque, não SQL.
- **Painel de custo do Copiloto.** `custo_estimado` já é gravado por turno; falta a tela.
- **Registrar pedido não atendido** (já está na fila como Fase 5).
- **Sugestões depois de cada resposta.**
- **Renomear e apagar conversa.**

Fora permanentemente: qualquer caminho que traga veículo ou lead para dentro do banco do
Portal. Isso duplicaria dado entre produtos e criaria um jeito novo de o Portal ficar
desatualizado em relação ao Estoque.

---

## 10. O que os testes têm que provar

O teste que carrega o peso é o de **isolamento**: semear duas lojas e provar que cada uma
destas devolve só a loja da sessão —

- `SELECT * FROM vendas` (sem WHERE nenhum)
- `SELECT * FROM vendas WHERE 1=1 OR loja_slug = 'outra'`
- `LEFT JOIN` em que só uma ponta filtra
- subquery correlacionada referenciando a tabela de fora
- CTE (`WITH x AS (SELECT …) SELECT * FROM x`)
- `venda_custos_diretos`, que se escopa por FK e não por coluna

Mais:

| Teste | Prova |
|---|---|
| drift esquema ↔ `models.py` | nenhuma coluna prometida ao modelo deixou de existir |
| authorizer com SQL injetado direto no executor | escrita é negada mesmo se o guard for contornado |
| progress handler | consulta longa aborta em vez de segurar o arquivo |
| guard recusa | multi-statement, DML, DDL, `PRAGMA`, `ATTACH`, tabela fora da allowlist |
| runner | recusa vira `role=tool` e o modelo tenta de novo dentro do teto |
| flag desligada | catálogo sem a tool, prompt sem o esquema, `max_iteracoes` de volta a 4 |
| tela | tabela renderizada sem `innerHTML` |

Testes rodam da pasta do produto: `cd portal-gestao && .venv/Scripts/python.exe -m pytest -q`.

---

## 11. Riscos abertos

- **WAL num volume Fly.** É bloco local, não NFS, então WAL é seguro. Mas é mudança de
  formato: o rollback é restaurar o snapshot, não desligar o PRAGMA.
- **`sqlglot` é dependência nova.** Sem ela, dá para fazer com parser à mão e eu não
  confiaria no resultado — a reescrita de AST é o coração do isolamento.
- **Custo por pergunta sobe.** SQL errado e corrigido gasta duas voltas ao provedor. O teto
  de 20k tokens segura o pior caso, mas a pergunta ad-hoc é a mais cara do produto.
- **O modelo pode escrever SQL válido e semanticamente errado** (join errado, período
  errado) e narrar o resultado com confiança. É exatamente por isso que D6 exige a tabela
  na tela: o dono confere as linhas, não a prosa.
