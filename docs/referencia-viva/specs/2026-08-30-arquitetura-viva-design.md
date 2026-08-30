# Arquitetura viva — mapa navegável por zoom contínuo

**Status:** design aprovado, não implementado.
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

## 5. Os três níveis

| Nível | O que se vê | De onde vem |
|---|---|---|
| **1 — Contexto** | VMs como molduras, produtos como caixas dentro delas, setas com protocolo, SPOF marcado | `arquitetura.py` |
| **2 — Interior** | rotas, workers, flags, migrations do produto, agrupados por seção; decisões e termo ancorados na moldura | `_frescor.json` + `CONTEXT.md` + `decisoes/` |
| **3 — Item** | `arquivo:linha`, símbolo, e o texto da decisão que o governa | `_frescor.json` |

Fluxos são uma camada por cima: escolher um fluxo acende o caminho e apaga o resto.
Não é um quarto nível.

## 6. O zoom — mecânica

**Um `<svg>` só, tudo dentro dele desde o load.** O conteúdo do nível 2 é desenhado
*dentro* da caixa do produto, em escala minúscula. Clicar não troca de tela: anima o
`viewBox` até aquela caixa preencher a viewport. O detalhe já estava lá — nada aparece,
você só chega perto. É a diferença entre cair dentro e trocar de slide.

Três coisas decidem se fica bom:

1. **LOD por escala.** Cada camada de texto tem um par `escala_min`/`escala_max`; a
   opacidade interpola nas bordas. Sem isso, 714 labels sobrepostos no nível 1 —
   ilegível e lento.
2. **Layout determinístico.** Posições calculadas no Python por empacotamento em grade
   aninhada, ordenado por chave. **Nunca force-directed:** posição diferente a cada run
   faz o diff do arquivo commitado virar ruído puro.
3. **Caminho de volta.** Breadcrumb clicável, `Esc` sobe um nível, wheel dá zoom livre,
   arrastar dá pan. Sem isso o usuário se perde no nível 3.

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
- borda **grossa** = SPOF; ícone de aviso = sem retry
- moldura pontilhada = VM
- caixa **acinzentada** = existe no código mas nenhuma seta chega (candidata a morta)

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
