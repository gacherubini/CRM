# Arquitetura viva — mapa navegável por zoom contínuo

**Status:** **implementado e em uso** (`.claude/skills/revy-research/arquitetura.html`,
gerado por `gerar_arquitetura.py`). O desenho abaixo é o de 30/08; o que mudou depois
de abrir a página no navegador está na [§14](#14-revisão-de-3108--o-que-o-navegador-mudou),
que **vence este documento** onde os dois divergirem.
**Produto:** ferramenta interna (`.claude/skills/revy-research/`), não é produto do cliente.
**Decisão em uma frase:** a arquitetura deixa de ser um diagrama que alguém redesenha e
vira um artefato gerado, do mesmo jeito que `mapa/*.md` já é.

---

## 1. O problema

Hoje a arquitetura da Revy existe em quatro lugares e em nenhum ao mesmo tempo:

| Onde | O que sabe | O que não sabe |
|---|---|---|
| `AGENTS.md` §2 | os 8 produtos e de quem é cada domínio | nada do interior |
| `mapa/*.md` | 714 entradas com `arquivo:linha` | que o Chatbot chama o Motor |
| `mapa/_cruzamentos.md` | as costuras entre produtos | onde elas rodam |
| `deploy/fly/3vm/` | onde cada coisa roda | o que ela faz |

Ninguém vê os quatro juntos, e um diagrama desenhado à mão mente no dia seguinte
sem avisar.

## 2. A forma da solução

Quatro camadas. **Três já existem.**

```
CONTEXT.md         ── Language: termos do domínio          JÁ EXISTE
decisoes/*.md      ── 13 ADRs                              JÁ EXISTE
mapa/_frescor.json ── 714 entradas, arquivo:linha          JÁ EXISTE (gerado)
arquitetura.py     ── caixas, setas, VMs, fluxos, SPOF     NOVO, à mão, ~150 linhas
        │
        ▼
gerar_arquitetura.py  ── layout determinístico + SVG + JSON embutido   NOVO
        ▼
arquitetura.html      ── arquivo único, auto-contido, commitado        NOVO
```

O `_frescor.json` sabe que `FollowupWorker` mora em `chatbot-api/app/followup_job.py:64`.
Ele **não** sabe que o Chatbot fala com o Motor por HTTP, que o Playwright do Motor é
single-flight, nem que "venda → outbox → Control" é um caminho com nome. Isso é o
`arquitetura.py`: a única parte escrita à mão, e a única que não muda quando você
acrescenta uma rota.

### Por que uma camada à mão e não inferência total

Inferir tudo do código produz um grafo de 700 nós sem hierarquia e sem semântica —
não dá pra saber qual seta é crítica. As ~150 linhas à mão são o que transforma
um grafo em um mapa. E elas mudam com a topologia (raro), não com o código (toda hora).

## 3. Reuso — o que NÃO reescrever

`cruzamentos.py` já expõe funções tipadas que derivam setas do código:

- `paths_chamados(texto) -> set[str]` — cliente HTTP → rota de outro produto
- `paths_do_workflow(caminho) -> set[str]` — n8n → rota do Chatbot
- `sem_chamador(raiz, produto, usados)` — função pública órfã

`gerar_arquitetura.py` **importa** essas funções. Não duplica extração.

Igual ao `gerar_mapa.py`, ele **não importa `app` de produto nenhum** (invariante
do AGENTS.md §5): tudo é lido como texto e parseado com `ast`.

Infra também é derivável, não inventada:

- `deploy/fly/3vm/supervisord.conf` → quais programas rodam na `app2037`
  (nginx, healthz, chatbot, estoque, portal, revy-trafego, catalogo, motor)
- `deploy/fly/3vm/nginx-edge.conf` → o roteamento de porta real
  (`:8080` → chatbot `:8001`, estoque `:8002`, catálogo `:8003`,
  portal `:9000`, tráfego `:9010`, motor `:8004`, healthz `:8099`)
- `deploy/fly/3vm/fly.*.toml` → `app2037`, `motor2037`, `n8n2037`, `evolution2037`

Isso torna visível o fato mais importante da infra e que hoje não está desenhado
em lugar nenhum: **a `app2037` carrega cinco produtos e a API do Motor.** Uma caixa
que cai leva seis coisas junto.

## 4. `arquitetura.py` — schema

### Por que não é YAML

O Mac do dono roda **Python 3.9.6**, sem `pyyaml` instalado, e `tomllib` só existe
no 3.11+. A pasta é **stdlib apenas** por invariante (`gerar_mapa.py:1`). Sobram
JSON — que não aceita comentário, justamente onde o valor está na prosa — ou um
módulo Python de dados.

Módulo Python, então. E não é invenção: `gerar_mapa.py:39` já tem exatamente isso —
`TESTES`, um dict literal comentado, descrito no próprio arquivo como "a ÚNICA parte
escrita a mão do mapa". `arquitetura.py` é o mesmo padrão, um nível acima.

Ganha comentário livre, vírgula final, tipo declarado, e zero parser para manter.
É código executável como config, o que seria risco se viesse de fora — vem do repo.

### O schema

Um arquivo, quatro dicts. Mora em `.claude/skills/revy-research/arquitetura.py`.

```python
"""Intencao da arquitetura: o que o codigo nao diz de si mesmo.

Escrito a mao. Muda quando a TOPOLOGIA muda, nao quando nasce uma rota.
Mesmo padrao do TESTES em gerar_mapa.py:39.
"""

# 1. NOS — nome, papel, e onde ancorar prosa que ja existe no repo.
NOS: dict[str, dict] = {
    "motor-simulacao": {
        "titulo": "Motor de Simulação",
        "papel": "banco",
        "vm": "app2037",        # a API; o worker vive na motor2037
        "termo": None,          # entrada do ## Language do CONTEXT.md, se houver
        "decisoes": [],         # arquivos de decisoes/ ancorados nesta caixa
        "spof": True,
        # Sem retry entre a falha do driver e o chamador.
        "spof_porque": (
            "Playwright single-flight — ver learnings/"
            "2026-08-23-driver-playwright-engole-o-clique-que-falha.md"
        ),
    },
}

# 2. ARESTAS — so as que cruzamentos.py nao infere, ou que precisam de semantica.
#    protocolo: http | outbox | evento | webhook | tcp
ARESTAS: list[dict] = [
    {"de": "portal-gestao", "para": "revy-trafego",
     "protocolo": "outbox", "sincrono": False, "retry": True},
]

# 3. VMs — agrupamento e blast radius.
VMS: dict[str, dict] = {
    "app2037": {
        "tipo": "fly-machine",
        "contem": ["chatbot-api", "estoque-api", "portal-gestao",
                   "revy-trafego", "catalogo-publico", "motor-simulacao"],
        "nota": "nginx-edge:8080 na frente, supervisord por tras",
    },
}

# 4. FLUXOS — o caminho com nome, em passos.
FLUXOS: dict[str, dict] = {
    "whatsapp-simulacao": {
        "titulo": "WhatsApp → simulação",
        "passos": [
            {"no": "evolution2037", "faz": "recebe a mensagem"},
            {"no": "n8n2037", "faz": "roteia", "protocolo": "webhook"},
            {"no": "chatbot-api", "faz": "interpreta e decide"},
            {"no": "motor-simulacao", "faz": "simula no banco", "sincrono": False},
        ],
        "invariante": "a parcela nao volta ao cliente pelo bot",
    },
}
```

**Campos obrigatórios:** `titulo` e `papel` em cada nó. Todo o resto é opcional e o
gerador degrada sem quebrar — um `arquitetura.py` com 3 nós e nada mais já produz página.

**Validação:** o gerador falha alto se o arquivo citar um produto que não existe no
`_frescor.json`, ou um arquivo de `decisoes/` que não existe. Referência morta é erro,
não aviso — é exatamente o modo como este arquivo apodreceria em silêncio. `saude.py`
já faz essa checagem para learnings e decisões (`citacoes_mortas`); o mesmo espírito.

## 5. Duas vistas, níveis recursivos

**Revisado duas vezes em 30/08, as duas depois de abrir a página no navegador.**

A primeira versão tinha dois níveis fixos: produto, e dentro dele uma lista de rotas.
Errado — entrar num nó tem que **trocar o que está na tela** pela estrutura interna
dele. Então `NOS` é recursivo: todo nó pode ter `dentro`, um dicionário de sub-nós com
a mesma forma, e a profundidade é decidida pelo `arquitetura.py`, não pelo gerador.

A segunda correção veio de olhar o resultado: uma vista só, com tudo junto, é densa
demais para ser lida.

### As duas vistas

| Vista | Seções do `_frescor.json` | Arestas | Fluxos |
|---|---|---|---|
| **Arquitetura** | `worker`, `flag` | sim (chamada/outbox/timer/http) | sim |
| **Schema** | `modelo`, `migration` | sim (chave estrangeira) | não |
| *dispensadas* | `rota`, `template` | — | — |

> Atualizado em 31/08 — ver §14. `rota` e `template` saíram das duas vistas por
> decisão do dono; a Schema **ganhou** arestas próprias (as FK). A tabela original
> desta seção listava `rota`/`template` na Arquitetura e dizia que a Schema não tinha
> aresta nenhuma.

Schema é **vista separada, não caixa dentro da arquitetura**. Fluxo é caminho de
execução; relação de dado é outra coisa, e misturar as duas foi o que deixou a
página ilegível. Um alternador no topo troca entre elas. A metade da regra que
continua de pé: a Schema não tem **fluxo** — não se pergunta caminho de execução a
um schema.

Um nó que fica sem item numa vista — e sem filho que tenha — é podado daquela cena.
Sem a poda, a vista Schema fica cheia de moldura vazia.

**Seção nova avisa.** Se o `_frescor.json` passar a trazer uma seção que não está em
`SECOES_ARQUITETURA` nem em `SECOES_SCHEMA`, o gerador imprime um aviso e segue. Dado
que some calado é como este arquivo apodreceria.

### Os níveis, dentro de cada vista

| Camada | O que se vê | De onde vem |
|---|---|---|
| **Raiz** | VMs como molduras, produtos como caixas com uma **face** (título + resumo). **Nenhum interior aberto** — é o escopo inteiro e mais nada | `arquitetura.py` |
| **Dentro de um nó** | o diagrama interno daquele nó; a face do pai some | `arquitetura.py` → `dentro` |
| **Automáticos** | o que sobra vira árvore derivada do caminho do arquivo: diretório → arquivo | `_frescor.json` |
| **Folha** | as entradas daquele arquivo, com `arquivo:linha` | `_frescor.json` |

Decisões e termos do `CONTEXT.md` ancoram em qualquer nível.

## 6. O zoom — mecânica

**Um `<svg>` só, tudo dentro dele desde o load.** O interior de cada nó é desenhado
*dentro* da caixa dele, em escala minúscula. Clicar não troca de tela: anima o `viewBox`
até aquela caixa preencher a viewport. É a diferença entre cair dentro e trocar de slide.

**As duas rampas.** É o que faz o efeito, e o protótipo provou que uma só não basta:

- `data-k-min` — o **interior entra**: fica opaco conforme você se aproxima.
- `data-face-ate` — a **face sai**: o título grande e o resumo do nó desaparecem no
  mesmo intervalo. Sem esta segunda rampa, entrar numa caixa só aumenta a fonte.

**E uma trava de ancestralidade.** Escala sozinha não basta: caixas irmãs de tamanho
parecido abriam juntas, e entrar no Chatbot mostrava o interior do Portal ao lado. O
interior de um nó só acende se aquele nó for o foco atual ou um ancestral dele. Como os
`id` são caminhos pontuados (`app2037.chatbot-api.app.main.py`), o teste é de prefixo:
`atual === id || atual.indexOf(id + ".") === 0` — com o ponto, senão `chatbot-api`
casaria com `chatbot-apix`. Cada grupo de interior declara `data-dono`.

Quatro coisas decidem se fica bom:

1. **LOD por escala, por grupo.** Nunca por elemento: escrever opacidade em 714 nós a
   cada quadro trava; ~10 grupos não.
2. **Os limiares saem do layout, nunca de constante.** O protótipo mostrou o erro:
   `K_MIN` fixo em 3 com uma caixa que só chega a `k=2.27` ao ser clicada deixa o
   interior invisível para sempre — você entra e não vê nada. O limiar de um filho é
   derivado da largura do pai: `k_min = 0.6 * (largura_da_cena / largura_do_pai)`.
3. **Layout determinístico.** Posições calculadas no Python por empacotamento em grade
   aninhada, ordenado por chave. **Nunca force-directed:** posição diferente a cada run
   faz o diff do arquivo commitado virar ruído puro.
4. **Caminho de volta.** Breadcrumb clicável, `Esc` sobe um nível, wheel dá zoom livre,
   arrastar dá pan. Sem isso o usuário se perde no nível 3.

**Armadilha achada no navegador:** não use `setPointerCapture` no `<svg>` para o pan.
Capturar o ponteiro faz o `click` seguinte ter o próprio svg como alvo, e o
`closest("[data-navegavel]")` devolve `null` — o clique nunca navega, e nada no console
avisa. Use um limiar de 3px para separar arrasto de clique.

Animação: `requestAnimationFrame` interpolando o `viewBox`, `cubic-bezier(.4,0,.2,1)`,
~450 ms. `prefers-reduced-motion` corta pra 0 ms (salta em vez de voar).

**Sem biblioteca.** `d3-zoom` resolve pan/zoom genérico, não "voar até esta caixa e
revelar o interior" — isso se escreve de qualquer jeito. São ~80 linhas de JS.

### A restrição que decide tudo

`file://` bloqueia `fetch()`. O JSON tem que estar **embutido** no HTML, o que força
arquivo único auto-contido — que por acaso é exatamente o que o zoom contínuo precisa.
Fontes e CSS também inline: a página tem que abrir sem internet.

## 7. Aparência

Tokens de `shared/brand/revy-tokens.css`, como `como-funciona.html` já faz. Nada de
paleta inventada — o learning `2026-08-23-tokens-de-marca-tem-fonte-unica.md` existe
por um motivo.

Convenções do desenho, todas com legenda na própria página:

- traço **cheio** = síncrono; **tracejado** = assíncrono/fila
- borda **grossa vermelha** = SPOF (hoje só o Motor)
- moldura pontilhada = VM
- **forma técnica** (31/08): fila, worker, cache, browser — ver §14

Duas regras que valem para tudo, e que já foram quebradas uma vez cada:

- **cor é só o SPOF.** Nada de "vermelho porque é importante", nada de verde para
  decorar — o verde da marca aparece só na moldura da VM e no alternador ativo.
  Quem quiser destacar uma caixa muda a **forma**, não a tinta.
- **rótulo de aresta é só o protocolo**, e `chamada` não leva rótulo nenhum.

## 8. O que NÃO faz

- Não mostra dado de runtime. Isso é o painel Axiom, projeto separado.
- Não roda em CI e não bloqueia commit.
- Não edita o `arquitetura.py` sozinho — o gerador só lê.
- Não vira rota do Control. É ferramenta de dev, não superfície de cliente.
- Não desenha a arquitetura-alvo ao lado da atual. Depois, se doer.

## 9. Interface do módulo

`gerar_arquitetura.py` expõe uma função:

```python
def gerar(raiz: Path, destino: Path) -> None
```

Tudo o mais é privado. Internamente, três estágios com fronteira testável:

1. `carregar(raiz) -> Modelo` — funde `arquitetura.py` + frescor + cruzamentos + decisões.
   Falha alto em referência morta.
2. `dispor(modelo) -> Cena` — layout determinístico; puro, sem I/O.
3. `render(cena) -> str` — SVG + JS + CSS numa string.

O estágio 2 é puro e determinístico, então o teste é: rodar duas vezes dá byte a byte
o mesmo resultado.

## 10. Como saber que acabou

`test_gerar_arquitetura.py`, ao lado do `test_gerar_mapa.py` que já existe.
**`unittest` da stdlib, não pytest** — não há pytest neste Python, e o teste vizinho
usa `unittest.TestCase`:

- `NOS` mínimo (3 nós, sem aresta) produz HTML válido
- nó citando produto inexistente **falha** com mensagem nomeando o produto
- nó citando `decisoes/` inexistente **falha** nomeando o arquivo
- `dispor()` é determinístico: duas chamadas, saída idêntica
- toda entrada do `_frescor.json` aparece no HTML (nada some no caminho)
- o HTML não contém `http://` nem `https://` fora de comentário (auto-contido)

Além dos testes, `--verificar` — o mesmo idioma que `gerar_mapa.py` já usa
(`SKILL.md:69`): regera em memória, compara com o `arquitetura.html` commitado e
sai 1 se o arquivo no git estiver mentindo.

Comandos (o dono usa Mac e Windows; esta pasta é stdlib, não tem `.venv`):

```
# macOS
cd .claude/skills/revy-research && python3 gerar_arquitetura.py --verificar
cd .claude/skills/revy-research && python3 -m unittest test_gerar_arquitetura -v

# Windows
cd .claude\skills\revy-research && python gerar_arquitetura.py --verificar
cd .claude\skills\revy-research && python -m unittest test_gerar_arquitetura -v
```

Prova final que teste não dá: abrir `arquitetura.html` no navegador, cair dentro do
Chatbot, chegar num `arquivo:linha`, voltar com `Esc`. O learning
`2026-08-23-copiloto-so-se-verifica-no-navegador.md` vale aqui igual.

## 11. Custo depois de pronto

`gerar_arquitetura.py` entra na mesma linha do `gerar_mapa.py` no AGENTS.md §6.
Atualizar a arquitetura passa a custar zero token: um comando que você já é obrigado
a rodar. Prompt só quando a **topologia** muda — e aí é diff no `arquitetura.py`, não redesenho.

## 12. Riscos

| Risco | Mitigação |
|---|---|
| `arquitetura.py` apodrece em silêncio | referência morta é erro de build, não aviso |
| HTML de ~250 KB churnando no git | `_frescor.json` (145 KB) já churna; layout determinístico mantém o diff proporcional à mudança real |
| zoom bonito e inútil | o nível 3 tem que chegar em `arquivo:linha` — se não chegar, é enfeite |
| escopo virar "e também runtime" | §8 |

## 13. Fora de escopo (projeto irmão)

Painel de usuários reais sobre Axiom. Decidido em conversa, não especificado aqui:
**não leva machine própria** — vira rota no Revy Control com um endpoint proxy
(o token do Axiom fica no servidor; no browser seria secret vazado, AGENTS.md §5),
cache de 20–30 s contra o polling, e o dashboard nativo do Axiom como *break-glass*
quando a `app2037` cair. Hoje não há **nenhuma** instrumentação Axiom no repo, então
o primeiro passo daquele projeto é schema de evento e instrumentação, não tela.

---

## 14. Revisão de 31/08 — o que o navegador mudou

Tudo nesta seção saiu de **abrir a página e olhar**, não de raciocínio sobre o
código. Onde ela discorda das seções acima, ela vence.

### 14.1 A camada de componente, nos seis produtos

Cada produto deixou de ser uma caixa com árvore de arquivo dentro e passou a ter
**unidades de responsabilidade** com `arquivo:linha` provando que existem.

| Produto | Componentes | Arestas internas |
|---|---|---|
| Chatbot API | 16 folhas em 4 gavetas | 20 |
| Estoque API | 9, sem gaveta | 11 |
| Catálogo Público | 7, sem gaveta | 8 |
| Motor de Simulação | 10 (8 soltas + gaveta `rpa`) | 17 |
| Revy Control | 10, sem gaveta | 16 |
| Revy Loja | 10, sem gaveta | 15 |

Teto de **seis a dez folhas** por produto: abaixo de seis não conta a história,
acima de dez volta a ser a lista de arquivos com outro nome. O que ficou de fora
por causa do teto está escrito em comentário, na caixa que o absorveu.

**Gaveta só onde ela diz algo que a caixa sozinha não diz.** Sobraram cinco:
`canais`, `config`, `integracoes` e `workers` no Chatbot, e `rpa` no Motor (fato de
deploy — ali dentro sobe Chromium num slot da `motor2037`). Recusadas: "Anúncios"
(nomeia plataforma), "Workers" no Control (cada worker é o relógio de uma regra que
já mora no domínio) e agrupar por camada (`web`, `clients`, `jobs`) — que é a árvore
de pastas com outro nome.

**O `modulo` aponta o arquivo que TEM entrada de inventário**, que quase sempre é o
de rota, não o de domínio. Isso saiu do navegador: com o prefixo no domínio, as dez
caixas da Loja saíam vazias e as fichas caíam numa caixa automática chamada `web` —
a árvore de pastas voltando pela porta dos fundos.
Learning: `learnings/2026-08-30-modulo-no-dominio-devolve-a-arvore-de-pastas.md`.

### 14.2 Parede de ficha não é desenho

Três seções do inventário viravam colunas de fichas que respondiam *quais arquivos
existem* — pergunta que esta página não faz. O `mapa/<produto>.md` continua listando
todas, com `arquivo:linha`.

| Seção | Quantas | O que virou |
|---|---|---|
| `rota` | 407 | dispensada (30/08) |
| `template` | 90 | dispensada (31/08) |
| `flag` | 102 | **contagem**, acima de 4 por caixa |

O rótulo da contagem diz **duas** contas — `59 env · 19 rollout OFF` — porque o
extrator emite toda variável de ambiente sob o nome `flag`, e `REVY_TRAFEGO_TIMEZONE`
está no meio. "Todas default OFF" seria uma mentira que o desenho afirma sozinho.
Abaixo de quatro a lista fica: ler as duas flags do Motor vale mais que contar até dois.

**Print de tela renderizada foi cogitado e recusado** como substituto das fichas de
`template`: renderizar Jinja exige subir os quatro produtos com banco e sessão, a
skill é stdlib puro e não pode importar `app` (AGENTS.md §5), e o `arquitetura.html` é
commitado com `--verificar` byte a byte — 90 imagens viram binário que apodrece calado
a cada mudança de CSS. Seria uma parede mais bonita, e ainda parede.

### 14.3 A face só apaga quando há o que pôr no lugar dela

O zoom **troca** conteúdo: o título e a linha de prova saem, o interior entra. A troca
só se paga quando o que entra vale mais que o que sai. Clicar no `Outbox (vehicle.*)`
do Estoque deixava uma **tela branca** — você tinha `HMAC, backoff, desiste em 5
(outbox.py:19,27,83)` e passava a não ter nada.

A regra final conta filho que é **caixa**, não filho qualquer: ficha não substitui
título, ela **acompanha**. Com a contagem crua, `Copiloto de Vendas` perdia o título
para mostrar seis pílulas de env.

Hoje apagam a face **11 caixas** — os 6 produtos e as 5 gavetas —, e **70 das 81**
caixas de nó ficam com o título preto fixo em qualquer zoom.
Guardado por `test_a_face_so_apaga_quando_ha_o_que_por_no_lugar`.

### 14.4 Vocabulário técnico de forma

O dono lê o desenho pela forma antes de ler o texto; caixa toda igual obriga a ler
cada legenda, e aí o diagrama vira lista. A forma diz o que a caixa **é
tecnicamente**; o `papel` continua dizendo de que **domínio** ela é.

| Forma | Marca | Onde |
|---|---|---|
| `fila` | três divisórias na base | toda outbox do monorepo + fan-out do Motor (5) |
| `worker` | duas barras verticais (processo predefinido) | roda sozinho, em laço próprio (4) |
| `cache` | boca de cilindro tracejada | TTL do Pixel, `storage_state` do Playwright (2) |
| `browser` | barra de janela | o RPA, onde sobe Chromium (1) |

Sai do **dado** (`forma:` escrito à mão), nunca de importância, e **não troca a cor**.
Desenhada *sobre* o retângulo, não trocando a silhueta: o layout já calculou tamanho
contando com retângulo, e mudar a silhueta moveria o texto e as pontas de aresta.
As quatro estão na legenda, com teste ligando as duas pontas.

### 14.5 A Schema virou mapa conceitual de banco

Era a árvore de arquivo outra vez, e pior que a da Arquitetura: o Chatbot abria com
**28 caixas de migration de uma ficha cada** e as 19 tabelas espremidas como pílulas
dentro de `models_db.py`.

Agora cada **tabela é uma caixa**, com os **atributos** dentro, e cada **FK é uma seta
rotulada** com a cardinalidade — que não é chutada, já estava escrita no SQLAlchemy:

| No modelo | Cardinalidade |
|---|---|
| `ForeignKey` em coluna comum | `n:1` |
| a mesma FK com `primary_key` ou `unique` | `1:1` |
| `nullable=True` (ou `Mapped[T \| None]`) | `:0..1` |

No Chatbot isso revelou **4 tabelas que são extensão 1:1 de `lojas`**
(`agente_config`, `rodizio_ponteiro`, `grupos_estoque`,
`loja_operacional_projecao`), que o desenho antigo mostrava iguaizinhas a uma tabela
de muitos.

A coluna traz tipo, chave e nulidade (`canal_id · str · FK whatsapp_canais · nulo`).
O tipo sai da **anotação** (`Mapped[str | None]`), não do argumento do
`mapped_column`: é ela que o autor escreveu pensando no domínio, e é ela que o mypy
cobra. A ordem é a do **arquivo**, nunca alfabética — quem escreveu pôs a PK primeiro
e os carimbos de tempo no fim, e isso é informação.

As 28 migrations viram **uma** caixa com contagem e head: são a história de como o
schema chegou aqui, não a forma dele.

Duas regras se inverteram de propósito:

- aresta interna nasce **apagada** na Arquitetura (são 99 marcadores, ninguém pergunta
  pelas 20 do Chatbot ao mesmo tempo) e nasce **acesa** na Schema — ali a seta *é* o
  conteúdo, e um mapa de relações escondidas é uma lista de tabelas;
- `dispor` ganhou `folga` e a Schema usa o **triplo** da Arquitetura. A `MARGEM` não
  mudou: ela é também o padding *dentro* da caixa, e mexer nas duas juntas incha o
  desenho sem separar nada.

`relacoes` e `colunas` entram no `_frescor.json` com **chave própria**, não como seção
do inventário: `Entrada` descreve *um* lugar no código, e uma relação liga *dois*;
uma coluna não é um lugar que alguém procura, é o *conteúdo* de uma tabela.

### 14.6 O vocabulário de protocolo interno tem quatro palavras

`chamada` (mesmo processo), `outbox` (uma grava, a outra consome), `timer` (thread
periódica) e `http`. A quarta entrou com o Motor, único produto cujo **interior**
atravessa VM: o wake do orquestrador é uma chamada à Machines API do Fly
(`app2037` → `motor2037`). Não é `chamada`, que quer dizer mesmo processo, nem
`outbox`, que quer dizer que alguém grava e outro consome depois.

Antes de propor uma quinta, o teste é: ela diz algo que estas quatro não dizem, ou é
sinônimo de uma delas?

### 14.7 O que ficou aberto

1. **O hub `loja_id` na Schema.** 17 das 26 relações do Chatbot apontam para `lojas`
   — isso é *multi-tenancy*, não modelagem, e afoga as 9 que descrevem o domínio.
   Nenhum arranjo resolve: `lojas` tem 17 vizinhos, o cruzamento é geométrico.
   Ou se tiram essas setas do desenho (marcando as tabelas como "por loja") ou se
   aceita o emaranhado. **Esconde dado, então é decisão do dono.** Recomendação:
   tirar.
2. **Só o Chatbot foi conferido na Schema.** Os outros cinco já ganharam a mesma
   mecânica automaticamente (Loja tem 266 colunas, Control 300), mas ninguém abriu
   nenhum deles no navegador.
3. **`TestArestasInternasLegiveis` continua olhando só o Chatbot.** Ela não reprovou
   com os cinco produtos novos porque não os enxerga. Antes de estender, **confira o
   sinal dela** — na fase dos estágios ela premiava o desenho ilegível, e subir o teto
   até passar não é teste, é enfeite. A história está na docstring da classe.

### 14.8 Como conferir no navegador

Obrigatório, e não opcional: **sete defeitos desta página só apareceram abrindo ela**,
e dois não deixavam rastro no console.

```bash
cd .claude/skills/revy-research
python3 -m http.server 8899          # a extensão de navegador bloqueia file://
python3 recorte_produto.py chatbot-api           # o interior de um produto
python3 recorte_produto.py chatbot-api schema    # a mesma coisa na Schema
```

O `recorte_produto.py` existe porque a automação de navegador vê a aba em **segundo
plano**: `document.hidden` é `true`, o `requestAnimationFrame` não roda, e mexer no
`viewBox` pelo DOM muda o atributo mas o screenshot volta do quadro antigo. **Só
navegação repinta.** A docstring dele tem o resto, inclusive que a sobreposição
face × interior **no recorte** não é defeito da página.

Armadilhas que custaram caro, todas com learning em
`.claude/skills/revy-research/learnings/`:

- termo comprido **apaga a própria prova em silêncio** (~59 caracteres na caixa de um
  componente); `TestProvaCabeNaCaixa` pega — desde que o produto esteja na lista
  `com_componente` dele;
- `getComputedStyle(el).opacity` devolve o **meio** da transição — leia o atributo
  `style` inline;
- `hidden` não esconde um `<svg>`, por dois motivos independentes;
- `setPointerCapture` no `<svg>` engole todo clique, sem rastro no console.
