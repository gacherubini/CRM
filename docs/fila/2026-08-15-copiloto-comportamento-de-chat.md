# Copiloto de Vendas — comportamento de chat profissional

> **Para agentes:** SUB-SKILL OBRIGATÓRIA: use `superpowers:subagent-driven-development`
> (recomendado) ou `superpowers:executing-plans` para executar tarefa a tarefa.
> Os passos usam checkbox (`- [ ]`).

**Goal:** fazer o Copiloto se comportar como assistente de verdade (streaming,
markdown, erro honesto, composer vivo) sem redesenhar a tela nem trocar a
identidade Revy.

**Architecture:** três frentes independentes. (1) Apresentação: um renderizador
de markdown restrito, escrito à mão em nós de DOM, inline no template — o
front-end do Portal não tem build nem dependência de runtime. (2) Percepção de
tempo: a tela passa a acumular texto em vez de substituir, e o provedor passa a
transmitir por SSE gravando `texto_parcial` a cada ~400 ms; a coluna, a
migration e a rota já existem e hoje só são usadas no caminho de falha.
(3) Honestidade de estado: o polling tolera falha transitória em vez de declarar
derrota, e erro ganha forma e palavra além da cor.

**Tech Stack:** FastAPI + Jinja2 renderizado no servidor, JS baunilha inline,
CSS próprio com tokens de `shared/brand/revy-tokens.css`, httpx, pytest.

**Spec:** `.impeccable/critique/2026-08-15T21-52-27Z__portal-gestao-app-templates-loja-copiloto-html.md`
(crítica de 2026-08-15, 20/40 — 2 P0 e 5 P1). Contexto de produto: `PRODUCT.md`.

## Global Constraints

- **Sem build, sem dependência de runtime.** Nada de React, Vite, Tailwind, nem
  biblioteca de markdown carregada na página. `PRODUCT.md` → "Capabilities and
  Constraints".
- **Nunca `innerHTML` em conteúdo do Copiloto.** Só `document.createElement` +
  `textContent`. A disciplina existente está documentada em
  `copiloto.html:189-202` e é o que fecha o XSS do cartão de ação.
- **Só tokens de marca** (`--surface`, `--brand`, `--ink`, `--line`, `--danger`,
  `--warn`, `--ok`). `app.css` não reabre `:root`.
- **Raio só 3px/8px/12px** (`--radius-ctl`/`--radius-nav`/`--radius-srf`). Um
  quarto valor quebra `shared/brand/tests/test_app_css.py`.
- **Verde é acento de marca, nunca cor de status.** Erro é `--danger`.
- **Cor nunca comunica sozinha** — todo estado leva forma **e** palavra.
  Compromisso vinculante de `PRODUCT.md` → "Accessibility & Inclusion".
- **Escopo é comportamento, não cromo.** NÃO mexer nesta leva: cabeçalho do
  painel, os três avisos "números vêm das ferramentas", os avatares ✦, a barra
  de hint do composer. Decisão do dono em 2026-08-15.
- **Os 13 itens de UX recusados em 2026-08-07 não voltam**
  (`docs/referencia-viva/2026-08-07-triagem-revisao-ux-loja-control.md`).
- **Testes rodam da pasta do produto:**
  `cd portal-gestao && .venv/Scripts/python.exe -m pytest -q`.
  Baseline desta branch: **541 passed** em `-k copiloto`.
- **Mudou `app.css` → sobe o `?v=` em `base.html`** (hoje `v13`, vai para `v14`).
  Sem isso a produção serve CSS velho — já quebrou o redesenho do Copiloto em
  2026-08-14.
- **Sem secret, token ou `.env` real no git ou no log.**

## Strings que os testes existentes travam (não renomear)

`tests/test_copiloto_tela_chat.py` faz asserção literal sobre o HTML da página.
Preserve, com o mesmo texto e a mesma ordem:

- `corpo.set('pergunta', pergunta)` **antes** de `campo.value = ''` e **antes**
  de `definirPendente(true)`
- a função `definirPendente`
- `id="copiloto-enviar"`, `name="pergunta"`
- `class="chip" data-pergunta=` presente no GET de `/app/loja/copiloto`
- `/app/loja/copiloto/turno/` e `/app/loja/copiloto/perguntar` presentes na página
- a palavra `Fontes` num turno concluído
- a string `None` **nunca** aparece no HTML
- `Fraunces`, `copiloto-body`, `copiloto-page` **nunca** aparecem

## File Structure

| Arquivo | Responsabilidade nesta leva |
|---|---|
| `portal-gestao/app/loja/copiloto/prompt.py` | contrato de formato da resposta (markdown restrito) |
| `portal-gestao/app/templates/loja/copiloto.html` | markup do chat + todo o JS (renderizador, polling, composer) |
| `portal-gestao/app/templates/loja/copiloto_hoje.html` | plural real, severidade com palavra |
| `portal-gestao/app/static/css/app.css:3115-3492` | blocos de markdown, erro com forma, sidebar que rola, severidade |
| `portal-gestao/app/templates/base.html:12` | bump do `?v=` |
| `portal-gestao/app/loja/copiloto/port.py` | contrato `ao_texto` no `LLMPort` e no `LLMFake` |
| `portal-gestao/app/clients/deepseek.py` | SSE do provedor (compatível OpenAI) |
| `portal-gestao/app/loja/copiloto/runner.py` | repasse do callback, sem lógica nova |
| `portal-gestao/app/copiloto_turnos_job.py` | gravação de `texto_parcial` com throttle |

Tarefas 1–7 são front-end + prompt e não dependem do backend. A Tarefa 8
(streaming real) é a única que toca provedor/worker, e depende da Tarefa 2 já
ter feito a tela acumular em vez de substituir.

---

### Task 1: Markdown ponta a ponta

O prompt hoje **proíbe** markdown (`prompt.py:44`) porque a tela renderiza com
`textContent`. Soltar o prompt sem o renderizador faz a tela mostrar
`**Receita total:**` literal — as duas metades andam juntas, num commit só.

**Files:**
- Modify: `portal-gestao/app/loja/copiloto/prompt.py:44-55` *(já aplicado)*
- Modify: `portal-gestao/tests/test_copiloto_prompt.py:96-116` *(já aplicado)*
- Modify: `portal-gestao/app/templates/loja/copiloto.html`
- Modify: `portal-gestao/app/static/css/app.css` (bloco do Copiloto)
- Test: `portal-gestao/tests/test_copiloto_markdown.py` (criar)

**Interfaces:**
- Produces: `renderizarMarkdown(texto, alvo)` no JS inline — limpa `alvo` e
  anexa nós de bloco. Usada pela Tarefa 2 (streaming) a cada tick e pelo
  `DOMContentLoaded` para as respostas que o Jinja já desenhou.
- Produces: `.copiloto-resposta` passa de `<p>` para `<div>` (bloco não pode
  viver dentro de `<p>`). A classe e o `::before` do avatar continuam iguais.

- [ ] **Step 1: Escrever o teste que falha**

Criar `portal-gestao/tests/test_copiloto_markdown.py`:

```python
"""A tela renderiza um subconjunto de markdown em nós de DOM.

O contrato tem DUAS pontas e elas têm que casar: o prompt promete ao modelo
que negrito/lista/tabela aparecem formatados (prompt.py, FORMATO_RESPOSTA), e
o renderizador do template é quem cumpre. Se alguém ampliar um lado sem o
outro, a marcação nova vaza literal na bolha do dono.
"""
from conftest import login

from app.db import SessionLocal
from app.loja.copiloto.conversas import concluir_turno, criar_turno


def _ligar(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "1")


def _usuario_id():
    from app.models import Usuario

    db = SessionLocal()
    try:
        return db.query(Usuario).filter(Usuario.email == "dono@loja.test").one().id
    finally:
        db.close()


def test_pagina_traz_o_renderizador_de_markdown(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    html = client.get("/app/loja/copiloto").text
    assert "function renderizarMarkdown" in html


def test_renderizador_nunca_usa_innerhtml(client, monkeypatch):
    """Invariante de segurança: o Copiloto monta DOM com createElement +
    textContent. innerHTML reabriria o XSS que o cartão de ação fechou."""
    _ligar(monkeypatch)
    login(client)
    html = client.get("/app/loja/copiloto").text
    assert "innerHTML" not in html


def test_resposta_e_um_bloco_e_nao_um_paragrafo(client, monkeypatch):
    """Lista e tabela não podem viver dentro de <p> — o parser do navegador
    fecha o parágrafo sozinho e o CSS do avatar (::before) perde a âncora."""
    _ligar(monkeypatch)
    login(client)
    db = SessionLocal()
    try:
        turno = criar_turno(
            db, loja_slug="loja-teste", usuario_id=_usuario_id(),
            pergunta="ranking?",
        )
        concluir_turno(
            db, turno, resposta="- Ana: 3\n- Bruno: 2", passos=[],
            tokens_entrada=10, tokens_saida=5, custo_estimado="0.001",
        )
        conversa_id = turno.conversa_id
    finally:
        db.close()
    html = client.get(f"/app/loja/copiloto?conversa_id={conversa_id}").text
    assert '<div class="copiloto-resposta"' in html
    assert '<p class="copiloto-resposta"' not in html
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd portal-gestao && .venv/Scripts/python.exe -m pytest tests/test_copiloto_markdown.py -q
```
Esperado: 3 FAILED (`renderizarMarkdown` não existe; a resposta ainda é `<p>`).

- [ ] **Step 3: Trocar `<p class="copiloto-resposta">` por `<div>` no template**

Em `copiloto.html`, no laço `{% for turno in turnos %}`, as quatro variantes da
resposta viram `div`. O `data-md` marca quais o JS deve renderizar no load:

```html
{% if turno.estado == 'erro' %}
<div class="copiloto-resposta erro">{{ turno.resposta or 'Não consegui responder desta vez.' }}</div>
{% elif turno.estado == 'cancelado' %}
<div class="copiloto-resposta muted">{{ turno.resposta or 'Pergunta cancelada.' }}</div>
{% elif turno.resposta %}
<div class="copiloto-resposta" data-md>{{ turno.resposta }}</div>
{% else %}
<div class="copiloto-resposta muted">Ainda processando esta pergunta…</div>
{% endif %}
```

E em `bloco()`, no JS: `var r = document.createElement('div');`

- [ ] **Step 4: Escrever o renderizador**

Inserir no `<script>` do `copiloto.html`, antes de `bloco()`:

```js
  // Markdown restrito: negrito, lista, lista numerada e tabela. Nada mais.
  // O prompt (prompt.py, FORMATO_RESPOSTA) promete exatamente este conjunto
  // ao modelo — ampliar um lado sem o outro faz a marcação nova vazar
  // literal na bolha. Tudo por createElement/textContent: innerHTML aqui
  // reabriria o XSS que o cartão de ação fechou.
  function inline(texto, pai) {
    // Só **negrito**. Um asterisco duplo sem par fecha voltando a ser texto.
    var partes = String(texto).split('**');
    partes.forEach(function (parte, i) {
      if (!parte) { return; }
      if (i % 2 === 1 && i < partes.length - 1) {
        var forte = document.createElement('strong');
        forte.textContent = parte;
        pai.appendChild(forte);
      } else {
        pai.appendChild(document.createTextNode((i % 2 === 1 ? '**' : '') + parte));
      }
    });
  }

  function celulas(linha) {
    return linha.replace(/^\||\|$/g, '').split('|').map(function (c) {
      return c.trim();
    });
  }

  function renderizarMarkdown(texto, alvo) {
    while (alvo.firstChild) { alvo.removeChild(alvo.firstChild); }
    var linhas = String(texto || '').split('\n');
    var i = 0;
    while (i < linhas.length) {
      var linha = linhas[i];
      if (!linha.trim()) { i++; continue; }

      // Tabela: | a | b |  /  |---|---|  /  linhas
      if (linha.trim().indexOf('|') === 0 && i + 1 < linhas.length &&
          /^\s*\|[\s:|-]+\|\s*$/.test(linhas[i + 1])) {
        var tabela = document.createElement('table');
        var thead = document.createElement('thead');
        var trh = document.createElement('tr');
        celulas(linha.trim()).forEach(function (c) {
          var th = document.createElement('th');
          inline(c, th);
          trh.appendChild(th);
        });
        thead.appendChild(trh);
        tabela.appendChild(thead);
        var tbody = document.createElement('tbody');
        i += 2;
        while (i < linhas.length && linhas[i].trim().indexOf('|') === 0) {
          var tr = document.createElement('tr');
          celulas(linhas[i].trim()).forEach(function (c) {
            var td = document.createElement('td');
            inline(c, td);
            tr.appendChild(td);
          });
          tbody.appendChild(tr);
          i++;
        }
        tabela.appendChild(tbody);
        alvo.appendChild(tabela);
        continue;
      }

      // Lista com marcador ou numerada
      var ehItem = /^\s*[-*]\s+/.test(linha);
      var ehNum = /^\s*\d+\.\s+/.test(linha);
      if (ehItem || ehNum) {
        var lista = document.createElement(ehNum ? 'ol' : 'ul');
        while (i < linhas.length) {
          var atual = linhas[i];
          var casa = ehNum ? /^\s*\d+\.\s+/.exec(atual) : /^\s*[-*]\s+/.exec(atual);
          if (!casa) { break; }
          var li = document.createElement('li');
          inline(atual.slice(casa[0].length), li);
          lista.appendChild(li);
          i++;
        }
        alvo.appendChild(lista);
        continue;
      }

      // Parágrafo: linhas seguidas até a próxima linha em branco.
      var p = document.createElement('p');
      var primeira = true;
      while (i < linhas.length && linhas[i].trim() &&
             !/^\s*[-*]\s+/.test(linhas[i]) && !/^\s*\d+\.\s+/.test(linhas[i]) &&
             linhas[i].trim().indexOf('|') !== 0) {
        if (!primeira) { p.appendChild(document.createElement('br')); }
        inline(linhas[i], p);
        primeira = false;
        i++;
      }
      alvo.appendChild(p);
    }
  }
```

- [ ] **Step 5: Renderizar o que o Jinja já desenhou**

No fim do IIFE, junto do `rolarParaFim()` que já existe:

```js
  // As respostas de conversa antiga chegam como texto cru dentro do div
  // (progressive enhancement: sem JS o dono ainda lê o texto, com asterisco).
  Array.prototype.forEach.call(
    mensagens.querySelectorAll('.copiloto-resposta[data-md]'),
    function (el) { renderizarMarkdown(el.textContent, el); }
  );
```

- [ ] **Step 6: CSS dos blocos**

Em `app.css`, logo depois de `.copiloto-resposta.erro` (linha ~3297):

```css
/* Markdown restrito renderizado pelo template (negrito, lista, tabela).
   pre-wrap sai do container e vai só no paragrafo: em <ul>/<table> ele
   transformaria a indentacao do proprio markup em espaco visivel. */
.copiloto-resposta p { margin: 0 0 var(--space-3); white-space: pre-wrap; }
.copiloto-resposta > :last-child { margin-bottom: 0; }
.copiloto-resposta ul,
.copiloto-resposta ol { margin: 0 0 var(--space-3); padding-left: var(--space-5); }
.copiloto-resposta li { margin: 0 0 var(--space-1); line-height: 1.6; }
.copiloto-resposta strong { font-weight: 600; color: var(--ink); }
.copiloto-resposta table {
  width: 100%;
  margin: 0 0 var(--space-3);
  border-collapse: collapse;
  font-size: var(--text-sm);
}
.copiloto-resposta th,
.copiloto-resposta td {
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--line);
  text-align: left;
  vertical-align: top;
}
.copiloto-resposta th { color: var(--ink-soft); font-weight: 600; }
/* Numero em tabela alinha e tabula: preco de coluna nunca serifa nem
   proporcional (brand kit v2.0, "Tipografia decidida"). */
.copiloto-resposta td:not(:first-child) { font-variant-numeric: tabular-nums; }
```

`.copiloto-resposta` mantém `white-space: pre-wrap` na regra original? **Não** —
remover de lá (linha ~3280), porque agora quem quebra linha é o `<p>`.

- [ ] **Step 7: Rodar os testes**

```bash
cd portal-gestao && .venv/Scripts/python.exe -m pytest tests/test_copiloto_markdown.py tests/test_copiloto_prompt.py tests/test_copiloto_tela_chat.py -q
```
Esperado: tudo PASS.

- [ ] **Step 8: Commit**

```bash
git add portal-gestao/app/loja/copiloto/prompt.py portal-gestao/tests/test_copiloto_prompt.py \
        portal-gestao/tests/test_copiloto_markdown.py portal-gestao/app/templates/loja/copiloto.html \
        portal-gestao/app/static/css/app.css
git commit -m "feat(copiloto): renderiza markdown restrito e solta a amarra do prompt"
```

---

### Task 2: A tela acumula em vez de substituir, e revela progressivamente

Entrega o ganho de percepção **sem tocar no provedor**: mesmo com a resposta
chegando inteira de uma vez, ela aparece sendo escrita em vez de piscar pronta.
Quando a Tarefa 8 ligar o SSE, este mesmo código passa a mostrar streaming real.

**Files:**
- Modify: `portal-gestao/app/templates/loja/copiloto.html` (`acompanhar`, `terminar`)
- Test: `portal-gestao/tests/test_copiloto_markdown.py` (acrescentar)

**Interfaces:**
- Consumes: `renderizarMarkdown(texto, alvo)` da Tarefa 1.
- Produces: `revelar(alvo, textoAlvo)` — guarda o texto pretendido em
  `alvo.dataset.textoAlvo` e avança um cursor por `requestAnimationFrame`.
  A Tarefa 8 chama exatamente esta função com os pedaços do SSE.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar em `tests/test_copiloto_markdown.py`:

```python
def test_pagina_revela_a_resposta_progressivamente(client, monkeypatch):
    """A resposta não pode aparecer de uma vez: 10-45s de 'Pensando…' e um
    bloco de texto piscando é o que faz o Copiloto parecer formulário lento."""
    _ligar(monkeypatch)
    login(client)
    html = client.get("/app/loja/copiloto").text
    assert "function revelar" in html
    assert "requestAnimationFrame" in html
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd portal-gestao && .venv/Scripts/python.exe -m pytest tests/test_copiloto_markdown.py -q -k progressiv
```
Esperado: FAIL.

- [ ] **Step 3: Implementar `revelar`**

No `<script>`, depois de `renderizarMarkdown`:

```js
  // Revelacao progressiva. O servidor manda o texto acumulado ate agora
  // (texto_parcial durante o streaming, resposta no fim); esta funcao so
  // controla o quanto disso ja esta na tela. Cursor por elemento: dois
  // turnos nunca compartilham estado.
  var VELOCIDADE_REVELACAO = 3; // chars por frame ~ 180/s a 60fps
  function revelar(alvo, textoAlvo) {
    alvo.dataset.textoAlvo = textoAlvo;
    if (alvo.dataset.revelando === '1') { return; }
    alvo.dataset.revelando = '1';
    function passo() {
      var meta = alvo.dataset.textoAlvo || '';
      var visivel = parseInt(alvo.dataset.cursor || '0', 10);
      if (visivel >= meta.length) {
        alvo.dataset.revelando = '0';
        return;
      }
      var proximo = Math.min(meta.length, visivel + VELOCIDADE_REVELACAO);
      alvo.dataset.cursor = String(proximo);
      var colado = pertoDoFim();
      renderizarMarkdown(meta.slice(0, proximo), alvo);
      if (colado) { rolarParaFim(); }
      requestAnimationFrame(passo);
    }
    requestAnimationFrame(passo);
  }

  // Fim do turno: nao deixa a revelacao pela metade.
  function revelarTudo(alvo) {
    var meta = alvo.dataset.textoAlvo || '';
    if (!meta) { return; }
    alvo.dataset.cursor = String(meta.length);
    renderizarMarkdown(meta, alvo);
  }
```

- [ ] **Step 4: Trocar a substituição pelo `revelar` no polling**

Em `acompanhar()`, o trecho `alvo.textContent = dados.texto` vira:

```js
          if (dados.texto) { revelar(alvo, dados.texto); }
```

E em `terminar()`, antes do tratamento de erro, `revelarTudo(alvo);`.

- [ ] **Step 5: Rodar os testes**

```bash
cd portal-gestao && .venv/Scripts/python.exe -m pytest tests/ -q -k copiloto
```
Esperado: 544+ passed, 0 failed.

- [ ] **Step 6: Commit**

```bash
git add portal-gestao/app/templates/loja/copiloto.html portal-gestao/tests/test_copiloto_markdown.py
git commit -m "feat(copiloto): resposta e revelada progressivamente em vez de piscar pronta"
```

---

### Task 3: Um indicador só, dentro do slot da mensagem

Hoje `bloco()` cria uma bolha vazia com avatar (`min-height: 34px` +
`::before`) e, ao mesmo tempo, `#copiloto-pensando` aparece fora do container
de scroll. São dois indicadores simultâneos, um deles um fantasma vazio.

**Files:**
- Modify: `portal-gestao/app/templates/loja/copiloto.html`
- Modify: `portal-gestao/app/static/css/app.css:3308-3337`
- Test: `portal-gestao/tests/test_copiloto_markdown.py` (acrescentar)

**Interfaces:**
- Produces: `.copiloto-resposta.pensando` — o mesmo div da resposta ganha a
  classe enquanto o passo corre, e a perde no primeiro caractere de texto.
  O `<p id="copiloto-pensando">` sai do DOM.

- [ ] **Step 1: Escrever o teste que falha**

```python
def test_indicador_de_pensando_vive_dentro_da_lista_de_mensagens(client, monkeypatch):
    """Bolha vazia com avatar + legenda flutuante fora do scroll = dois
    indicadores para um estado só."""
    _ligar(monkeypatch)
    login(client)
    html = client.get("/app/loja/copiloto").text
    assert 'id="copiloto-pensando"' not in html
    assert "copiloto-resposta pensando" in html or "classList.add('pensando')" in html
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd portal-gestao && .venv/Scripts/python.exe -m pytest tests/test_copiloto_markdown.py -q -k indicador
```
Esperado: FAIL.

- [ ] **Step 3: Remover o parágrafo solto do template**

Apagar a linha `<p id="copiloto-pensando" class="copiloto-pensando" hidden>Pensando…</p>`
e a variável `var pensando = document.getElementById('copiloto-pensando');`.

- [ ] **Step 4: O passo vira o conteúdo do próprio slot**

```js
  // O passo real ("consultando vendas…") vive DENTRO do slot da resposta:
  // um indicador so, no lugar onde o texto vai nascer. Sai no primeiro
  // caractere que chega do provedor.
  function mostrarPasso(alvo, rotulo) {
    if (alvo.dataset.textoAlvo) { return; } // ja tem texto: nao regride
    alvo.classList.add('pensando');
    alvo.textContent = rotulo;
  }
  function limparPasso(alvo) {
    alvo.classList.remove('pensando');
  }
```

Em `acompanhar()`:

```js
          if (dados.texto) {
            limparPasso(alvo);
            revelar(alvo, dados.texto);
          } else {
            mostrarPasso(alvo, descrever(dados.passos));
          }
```

Em `form.addEventListener('submit', ...)`, trocar as duas linhas de `pensando`
por `mostrarPasso(alvo, 'Pensando…');`. Em `terminar()`, `limparPasso(alvo);`.

- [ ] **Step 5: CSS — a animação migra para a classe**

Substituir o bloco `.copiloto-pensando` (linhas ~3308-3337) por:

```css
/* Estado "pensando" do proprio slot da resposta: o avatar ::before pulsa e o
   texto e o passo real (rotulos_passo no template), nunca spinner mudo — a
   pergunta pode levar 10-30s. */
.copiloto-resposta.pensando { color: var(--ink-muted); font-style: italic; }
.copiloto-resposta.pensando::before {
  animation: copiloto-pulse 1.1s ease-in-out infinite;
}
@keyframes copiloto-pulse { 0%, 100% { opacity: .4; } 50% { opacity: 1; } }
@media (prefers-reduced-motion: reduce) {
  .copiloto-resposta.pensando::before { animation: none; }
}
```

- [ ] **Step 6: Rodar os testes**

```bash
cd portal-gestao && .venv/Scripts/python.exe -m pytest tests/ -q -k copiloto
```

- [ ] **Step 7: Commit**

```bash
git commit -am "fix(copiloto): um indicador de pensando so, dentro do slot da mensagem"
```

---

### Task 4: Composer não trava, e enviar vira parar

`definirPendente(true)` desabilita textarea + botão + chips: o foco cai no
`body` e o dono não consegue nem rascunhar a próxima pergunta. A guarda real
(um turno em voo por vez) continua necessária — muda o **como**.

**Files:**
- Modify: `portal-gestao/app/templates/loja/copiloto.html`
- Modify: `portal-gestao/app/static/css/app.css` (bloco do composer)
- Test: `portal-gestao/tests/test_copiloto_markdown.py` (acrescentar)

- [ ] **Step 1: Escrever o teste que falha**

```python
def test_composer_continua_editavel_durante_o_turno(client, monkeypatch):
    """Travar o campo derruba o foco no body e impede rascunhar a proxima
    pergunta. A guarda de um-turno-por-vez passa a ser no submit."""
    _ligar(monkeypatch)
    login(client)
    html = client.get("/app/loja/copiloto").text
    assert "campo.disabled = pendente" not in html
    assert "emVoo" in html


def test_textarea_cresce_com_o_texto(client, monkeypatch):
    """rows=1 + resize:none sem auto-grow faz a pergunta longa rolar dentro
    de uma linha. O max-height: 9rem do CSS hoje e codigo morto."""
    _ligar(monkeypatch)
    login(client)
    html = client.get("/app/loja/copiloto").text
    assert "function ajustarAltura" in html
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd portal-gestao && .venv/Scripts/python.exe -m pytest tests/test_copiloto_markdown.py -q -k "composer or textarea"
```
Esperado: 2 FAILED.

- [ ] **Step 3: Reescrever `definirPendente`**

O nome fica (teste existente trava). O corpo muda: o campo continua vivo, o
botão de enviar vira **parar**.

```js
  // Um turno em voo por vez. Antes isto desabilitava o textarea inteiro — o
  // foco caia no body e o dono nao podia nem rascunhar a proxima pergunta.
  // Agora a guarda e no submit (emVoo) e o botao de enviar vira parar, como
  // em qualquer chat serio. Precisa ser desligado em TODO caminho terminal,
  // inclusive falha de rede, senao o composer trava em "parar" para sempre.
  var emVoo = false;
  function definirPendente(pendente) {
    emVoo = pendente;
    enviar.classList.toggle('parando', pendente);
    enviar.setAttribute('aria-label', pendente ? 'Parar' : 'Perguntar');
    enviar.disabled = pendente ? false : !campo.value.trim();
    Array.prototype.forEach.call(chipsInterativos, function (chip) {
      chip.disabled = pendente;
    });
  }
```

- [ ] **Step 4: O submit respeita `emVoo`; o botão para quando em voo**

No começo do handler de submit, depois do `evento.preventDefault()`:

```js
    if (emVoo) { return; }
```

E o clique no botão, quando em voo, para em vez de enviar — reaproveitando o
handler que o botão "Parar" já tinha:

```js
  enviar.addEventListener('click', function (evento) {
    if (!emVoo) { return; } // submit normal segue seu caminho
    evento.preventDefault();
    pararTurno();
  });
```

Extrair o corpo do listener de `cancelar` para `function pararTurno()` e manter
o botão `#copiloto-cancelar` como está (ele continua no HTML e continua
funcionando — não é cromo novo, é o mesmo controle).

- [ ] **Step 5: Auto-grow do textarea**

```js
  // O CSS ja tem max-height: 9rem; sem isto aqui ele era codigo morto e a
  // pergunta longa rolava dentro de uma linha.
  function ajustarAltura() {
    campo.style.height = 'auto';
    campo.style.height = campo.scrollHeight + 'px';
  }
  campo.addEventListener('input', function () {
    ajustarAltura();
    if (!emVoo) { enviar.disabled = !campo.value.trim(); }
  });
```

Chamar `ajustarAltura()` depois de `campo.value = ''` no submit e depois de
`campo.value = chip.getAttribute('data-pergunta')`.

- [ ] **Step 6: Botão começa desabilitado**

No HTML, `<button class="copiloto-enviar" type="submit" id="copiloto-enviar" disabled ...>`.

CSS do estado "parando" (quadrado de parar, sem ícone novo — só a forma):

```css
.copiloto-enviar.parando { background: var(--ink-soft); }
.copiloto-enviar.parando svg { display: none; }
.copiloto-enviar.parando::after {
  content: "";
  width: 10px;
  height: 10px;
  border-radius: var(--radius-ctl);
  background: var(--surface);
}
```

- [ ] **Step 7: Rodar os testes**

```bash
cd portal-gestao && .venv/Scripts/python.exe -m pytest tests/ -q -k copiloto
```

- [ ] **Step 8: Commit**

```bash
git commit -am "fix(copiloto): composer segue editavel e enviar vira parar durante o turno"
```

---

### Task 5: Polling que não mente

`.catch(function () { terminar(alvo, null); })` — uma sondagem com 500 ms de
soluço declara "Não consegui responder desta vez." enquanto o worker segue
rodando e a resposta vai cair no banco. Um F5 mostraria a resposta que a tela
disse não existir.

**Files:**
- Modify: `portal-gestao/app/templates/loja/copiloto.html`
- Test: `portal-gestao/tests/test_copiloto_markdown.py` (acrescentar)

- [ ] **Step 1: Escrever o teste que falha**

```python
def test_polling_tolera_falha_transitoria(client, monkeypatch):
    """Uma sondagem falha nao pode declarar derrota: o worker segue rodando e
    a resposta vai cair no banco. Declarar erro ai e mentir para o dono."""
    _ligar(monkeypatch)
    login(client)
    html = client.get("/app/loja/copiloto").text
    assert "FALHAS_ATE_DESISTIR" in html
    assert "continua sendo processada" in html
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd portal-gestao && .venv/Scripts/python.exe -m pytest tests/test_copiloto_markdown.py -q -k polling
```

- [ ] **Step 3: Implementar tolerância**

```js
  // Rede pisca. Antes, UMA sondagem falha matava a resposta e mostrava
  // "nao consegui" — mentira: o worker segue rodando e a resposta cai no
  // banco (um F5 mostraria). Tolera falhas seguidas e, ao desistir, diz a
  // verdade em vez de inventar uma derrota.
  var FALHAS_ATE_DESISTIR = 5;
  var falhasSeguidas = 0;

  function desistirDoPolling(alvo) {
    clearInterval(timer);
    limparPasso(alvo);
    definirPendente(false);
    revelarTudo(alvo);
    var aviso = document.createElement('p');
    aviso.className = 'copiloto-aviso';
    aviso.textContent = 'Perdi a conexão. A resposta continua sendo processada — recarregue em alguns segundos.';
    var recarregar = document.createElement('button');
    recarregar.className = 'button ghost';
    recarregar.type = 'button';
    recarregar.textContent = 'Recarregar';
    recarregar.addEventListener('click', function () { window.location.reload(); });
    aviso.appendChild(document.createTextNode(' '));
    aviso.appendChild(recarregar);
    alvo.parentNode.appendChild(aviso);
  }
```

No `.then` do fetch de polling, `falhasSeguidas = 0;` na primeira linha. E o
`.catch` vira:

```js
        .catch(function () {
          falhasSeguidas += 1;
          if (falhasSeguidas >= FALHAS_ATE_DESISTIR) { desistirDoPolling(alvo); }
        });
```

- [ ] **Step 4: Rodar os testes**

```bash
cd portal-gestao && .venv/Scripts/python.exe -m pytest tests/ -q -k copiloto
```

- [ ] **Step 5: Commit**

```bash
git commit -am "fix(copiloto): sondagem falha nao declara derrota de uma resposta que existe"
```

---

### Task 6: Erro com forma, palavra e saída

`.copiloto-resposta.erro { color: var(--danger) }` comunica só por cor — viola
o compromisso vinculante de `PRODUCT.md` ("cor nunca comunica sozinha") — e não
oferece nenhuma saída.

**Files:**
- Modify: `portal-gestao/app/templates/loja/copiloto.html`
- Modify: `portal-gestao/app/static/css/app.css:3297`
- Test: `portal-gestao/tests/test_copiloto_markdown.py` (acrescentar)

- [ ] **Step 1: Escrever o teste que falha**

```python
def test_erro_tem_palavra_e_saida_nao_so_cor(client, monkeypatch):
    """PRODUCT.md, compromisso vinculante: cor nunca comunica sozinha."""
    _ligar(monkeypatch)
    login(client)
    db = SessionLocal()
    try:
        turno = criar_turno(
            db, loja_slug="loja-teste", usuario_id=_usuario_id(), pergunta="e ai?",
        )
        turno.estado = "erro"
        turno.resposta = "O provedor não respondeu."
        db.commit()
        conversa_id = turno.conversa_id
    finally:
        db.close()
    html = client.get(f"/app/loja/copiloto?conversa_id={conversa_id}").text
    assert "Não deu certo" in html
    assert "Tentar de novo" in html
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd portal-gestao && .venv/Scripts/python.exe -m pytest tests/test_copiloto_markdown.py -q -k erro
```

- [ ] **Step 3: Template — rótulo e botão**

```html
{% if turno.estado == 'erro' %}
<div class="copiloto-resposta erro">
  <p class="copiloto-erro-rotulo"><span aria-hidden="true">!</span> Não deu certo</p>
  <p>{{ turno.resposta or 'Não consegui responder desta vez.' }}</p>
  <button type="button" class="button ghost" data-repergunta="{{ turno.pergunta }}">Tentar de novo</button>
</div>
```

- [ ] **Step 4: JS — refazer a pergunta**

No delegado de clique que já existe em `document`:

```js
    if (alvo.dataset && alvo.dataset.repergunta) {
      campo.value = alvo.dataset.repergunta;
      ajustarAltura();
      enviar.disabled = false;
      if (typeof form.requestSubmit === 'function') {
        form.requestSubmit();
      } else {
        form.dispatchEvent(new Event('submit', { cancelable: true }));
      }
      return;
    }
```

O mesmo bloco montado em JS, para os dois `.catch` do submit. Substitui o par
`alvo.className = 'copiloto-resposta erro'; alvo.textContent = ...` que hoje
existe duplicado nos dois caminhos:

```js
  // Mesmo desenho do erro que o Jinja monta no primeiro carregamento: rotulo
  // com palavra, mensagem e saida. Cor sozinha nao comunica (PRODUCT.md).
  function marcarErro(alvo, mensagem, pergunta) {
    alvo.classList.remove('pensando');
    alvo.className = 'copiloto-resposta erro';
    while (alvo.firstChild) { alvo.removeChild(alvo.firstChild); }

    var rotulo = document.createElement('p');
    rotulo.className = 'copiloto-erro-rotulo';
    var marca = document.createElement('span');
    marca.setAttribute('aria-hidden', 'true');
    marca.textContent = '!';
    rotulo.appendChild(marca);
    rotulo.appendChild(document.createTextNode(' Não deu certo'));

    var corpoErro = document.createElement('p');
    corpoErro.textContent = mensagem;

    var repetir = document.createElement('button');
    repetir.type = 'button';
    repetir.className = 'button ghost';
    repetir.dataset.repergunta = pergunta;
    repetir.textContent = 'Tentar de novo';

    alvo.appendChild(rotulo);
    alvo.appendChild(corpoErro);
    alvo.appendChild(repetir);
  }
```

Os dois `.catch` viram
`marcarErro(alvo, resposta.dados.message || 'Não consegui enviar sua pergunta.', pergunta);`
e `marcarErro(alvo, 'Não consegui enviar sua pergunta.', pergunta);`.

- [ ] **Step 5: CSS**

```css
/* Erro nunca so por cor (PRODUCT.md, compromisso vinculante): rotulo com
   palavra + marca de forma, e uma saida. */
.copiloto-resposta.erro { color: var(--ink); }
.copiloto-erro-rotulo {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0 0 var(--space-2);
  color: var(--danger);
  font-weight: 600;
  font-size: var(--text-sm);
}
.copiloto-erro-rotulo span {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border: 1px solid var(--danger);
  border-radius: var(--radius-ctl);
  font-size: var(--text-xs);
}
.copiloto-aviso {
  margin: var(--space-2) 0 0;
  color: var(--ink-muted);
  font-size: var(--text-sm);
}
```

- [ ] **Step 6: Rodar os testes e commitar**

```bash
cd portal-gestao && .venv/Scripts/python.exe -m pytest tests/ -q -k copiloto
git commit -am "fix(copiloto): erro ganha palavra, forma e botao de tentar de novo"
```

---

### Task 7: Copiar, `aria-live` no escopo certo, chips no vazio, Fontes legível, sidebar que rola

Os P2 agrupados: são todos no mesmo template/CSS e um revisor os aceitaria ou
rejeitaria em bloco.

**Files:**
- Modify: `portal-gestao/app/templates/loja/copiloto.html`
- Modify: `portal-gestao/app/static/css/app.css`
- Test: `portal-gestao/tests/test_copiloto_markdown.py` (acrescentar)

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_aria_live_esta_na_lista_de_mensagens_nao_na_secao_inteira(client, monkeypatch):
    """Com aria-live na <section>, o leitor de tela rele cabecalho, chips e
    composer a cada sondagem — e a resposta inteira do comeco a cada 700ms."""
    _ligar(monkeypatch)
    login(client)
    html = client.get("/app/loja/copiloto").text
    assert '<section class="copiloto-thread" aria-live="polite">' not in html
    assert 'id="copiloto-mensagens" aria-live="polite"' in html


def test_resposta_tem_botao_de_copiar(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    db = SessionLocal()
    try:
        turno = criar_turno(
            db, loja_slug="loja-teste", usuario_id=_usuario_id(), pergunta="quanto?",
        )
        concluir_turno(
            db, turno, resposta="Você vendeu 2.", passos=[],
            tokens_entrada=10, tokens_saida=5, custo_estimado="0.001",
        )
        conversa_id = turno.conversa_id
    finally:
        db.close()
    html = client.get(f"/app/loja/copiloto?conversa_id={conversa_id}").text
    assert "data-copiar" in html


def test_fontes_nao_mostra_enum_cru(client, monkeypatch):
    """runner.py devolve status ok|erro|indisponivel. 'consultando vendas — ok'
    poe palavra de maquina na cara do dono."""
    _ligar(monkeypatch)
    login(client)
    db = SessionLocal()
    try:
        turno = criar_turno(
            db, loja_slug="loja-teste", usuario_id=_usuario_id(), pergunta="vendas?",
        )
        concluir_turno(
            db, turno, resposta="Duas.",
            passos=[{"ferramenta": "vendas_resumo", "argumentos": {},
                     "status": "indisponivel", "resumo": ""}],
            tokens_entrada=10, tokens_saida=5, custo_estimado="0.001",
        )
        conversa_id = turno.conversa_id
    finally:
        db.close()
    html = client.get(f"/app/loja/copiloto?conversa_id={conversa_id}").text
    assert "indisponivel" not in html
    assert "indisponível" in html
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd portal-gestao && .venv/Scripts/python.exe -m pytest tests/test_copiloto_markdown.py -q -k "aria or copiar or fontes"
```
Esperado: 3 FAILED.

- [ ] **Step 3: `aria-live` migra de escopo**

`<section class="copiloto-thread">` perde o atributo;
`<div id="copiloto-mensagens" aria-live="polite">` ganha.

- [ ] **Step 4: Botão copiar**

No template, dentro do turno com resposta:

```html
<button type="button" class="copiloto-copiar" data-copiar aria-label="Copiar resposta">Copiar</button>
```

JS, no delegado de clique:

```js
    if (alvo.dataset && alvo.dataset.copiar !== undefined) {
      var corpoResposta = alvo.closest('.copiloto-turno').querySelector('.copiloto-resposta');
      navigator.clipboard.writeText(corpoResposta.textContent.trim()).then(function () {
        alvo.textContent = 'Copiado';
        setTimeout(function () { alvo.textContent = 'Copiar'; }, 1600);
      });
      return;
    }
```

Em `criarCartao`/`terminar`, anexar o mesmo botão ao turno concluído via JS.

- [ ] **Step 5: Rótulos de status em Fontes**

No topo do template, junto de `rotulos_passo`:

```jinja
{% set rotulos_status = {
  'ok': 'consultado',
  'erro': 'falhou',
  'indisponivel': 'indisponível'
} %}
```

E a linha vira:
`{{ rotulos_passo.get(passo.ferramenta, 'consultando dados') }} — {{ rotulos_status.get(passo.status, passo.status) }}`

- [ ] **Step 6: Chips só no estado vazio**

Mover o bloco `{% if resumo.chips %}` para **dentro** de
`<div class="copiloto-boas-vindas">`, preservando `class="chip" data-pergunta=`
(o teste `test_sugestoes_sao_botoes_com_a_pergunta` faz asserção literal e
carrega a página sem conversa, então continua passando). No JS, `bloco()` já
remove `[data-copiloto-vazio]` — os chips saem junto, que é o comportamento
desejado.

- [ ] **Step 7: Sidebar que rola**

```css
/* Sem isto a lista transborda o grid de altura fixa a partir de ~20 conversas. */
.copiloto-historico { min-height: 0; }
.copiloto-historico ul { overflow-y: auto; min-height: 0; }
```

- [ ] **Step 8: CSS do botão copiar**

```css
.copiloto-copiar {
  align-self: flex-start;
  margin-left: calc(34px + var(--space-3));
  border: 0;
  background: transparent;
  padding: 0;
  color: var(--ink-muted);
  font: inherit;
  font-size: var(--text-xs);
  cursor: pointer;
}
.copiloto-copiar:hover { color: var(--ink); text-decoration: underline; }
.copiloto-copiar:focus-visible { outline: 2px solid var(--brand); outline-offset: 2px; }
```

- [ ] **Step 9: Rodar os testes e commitar**

```bash
cd portal-gestao && .venv/Scripts/python.exe -m pytest tests/ -q -k copiloto
git commit -am "fix(copiloto): copiar resposta, aria-live no escopo, chips no vazio, fontes legivel"
```

---

### Task 8: Streaming real do provedor (SSE)

O P0 de maior impacto e o de maior risco. Depende da Tarefa 2 (a tela já
acumula). O contrato do `LLMPort` ganha um callback **opcional** — com
`ao_texto=None` o caminho atual continua byte a byte idêntico, que é o que
mantém os 541 testes existentes verdes.

**Files:**
- Modify: `portal-gestao/app/loja/copiloto/port.py:66-104`
- Modify: `portal-gestao/app/clients/deepseek.py`
- Modify: `portal-gestao/app/loja/copiloto/runner.py:194-197`
- Modify: `portal-gestao/app/copiloto_turnos_job.py:120-132`
- Test: `portal-gestao/tests/test_copiloto_streaming.py` (criar)

**Interfaces:**
- Produces: `LLMPort.completar(..., ao_texto: Callable[[str], None] | None = None)`.
  O client chama `ao_texto(acumulado_desta_chamada)` a cada delta de conteúdo.
- Produces: `executar_turno(..., ao_texto=None)` repassa sem lógica própria.
- Consumes: `atualizar_progresso(db, turno, texto_parcial=...)` — já existe em
  `conversas.py:80-89`.

**Nota de comportamento conhecida:** se uma rodada de tool-call emitir texto
antes das ferramentas, `texto_parcial` mostra esse preâmbulo e depois é
substituído pela resposta final. Com este prompt isso é raro. Não tratar agora.

- [ ] **Step 1: Escrever o teste que falha**

Criar `portal-gestao/tests/test_copiloto_streaming.py`:

```python
"""Streaming SSE do provedor (wire compatível com OpenAI).

Sem ``ao_texto`` o client tem que continuar fazendo POST normal — é isso que
mantém o resto da suíte verde e o caminho de produção inalterado até o worker
optar por streaming.
"""
import httpx

from app.clients.deepseek import DeepSeekClient
from app.loja.copiloto.port import MensagemLLM

SSE = (
    'data: {"choices":[{"delta":{"content":"Você "},"index":0}]}\n\n'
    'data: {"choices":[{"delta":{"content":"vendeu "},"index":0}]}\n\n'
    'data: {"choices":[{"delta":{"content":"2."},"index":0,"finish_reason":"stop"}]}\n\n'
    'data: {"choices":[],"usage":{"prompt_tokens":100,"completion_tokens":8}}\n\n'
    "data: [DONE]\n\n"
)


def _client(handler):
    return DeepSeekClient(
        "https://provedor.test", "chave", "modelo-x",
        transport=httpx.MockTransport(handler),
    )


def test_streaming_entrega_pedacos_e_o_texto_final():
    vistos = []

    def handler(request):
        assert httpx.Request is not None
        import json as _json
        assert _json.loads(request.content)["stream"] is True
        return httpx.Response(200, text=SSE,
                              headers={"content-type": "text/event-stream"})

    resposta = _client(handler).completar(
        [MensagemLLM(papel="user", conteudo="quanto vendi?")], [],
        ao_texto=vistos.append,
    )
    assert resposta.texto == "Você vendeu 2."
    assert vistos == ["Você ", "Você vendeu ", "Você vendeu 2."]
    assert resposta.tokens_entrada == 100
    assert resposta.tokens_saida == 8
    assert resposta.finish_reason == "stop"


def test_sem_callback_continua_sem_stream():
    """Caminho de produção atual: nenhum byte de comportamento muda enquanto
    o worker não pedir streaming."""
    def handler(request):
        import json as _json
        assert "stream" not in _json.loads(request.content)
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })

    assert _client(handler).completar(
        [MensagemLLM(papel="user", conteudo="oi")], []
    ).texto == "ok"


def test_streaming_monta_tool_call_por_indice():
    sse = (
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1",'
        '"function":{"name":"vendas_resumo","arguments":"{\\"per"}}]},"index":0}]}\n\n'
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
        '"function":{"arguments":"iodo\\":\\"mes\\"}"}}]},"index":0,'
        '"finish_reason":"tool_calls"}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request):
        return httpx.Response(200, text=sse,
                              headers={"content-type": "text/event-stream"})

    resposta = _client(handler).completar(
        [MensagemLLM(papel="user", conteudo="vendas?")], [], ao_texto=lambda _: None
    )
    assert len(resposta.tool_calls) == 1
    assert resposta.tool_calls[0].nome == "vendas_resumo"
    assert resposta.tool_calls[0].argumentos == {"periodo": "mes"}
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd portal-gestao && .venv/Scripts/python.exe -m pytest tests/test_copiloto_streaming.py -q
```
Esperado: FAILED (`completar()` não aceita `ao_texto`).

- [ ] **Step 3: Ampliar o contrato em `port.py`**

Em `LLMPort` e em `LLMFake.completar`, acrescentar o parâmetro (o Fake ignora,
mas precisa aceitar para não quebrar quem passar):

```python
        ao_texto: Callable[[str], None] | None = None,
```

Importar `Callable` de `typing`. No `LLMFake`, registrar em `self.chamadas`
que houve callback: `"streaming": ao_texto is not None`.

- [ ] **Step 4: Implementar o SSE no client**

Em `montar_payload`, aceitar `stream: bool = False` e, quando `True`,
acrescentar ao corpo:

```python
    if stream:
        corpo["stream"] = True
        # Sem isto o provedor nao manda usage no fim do stream e o turno
        # perde a contabilidade de token (teto_tokens do runner ficaria cego).
        corpo["stream_options"] = {"include_usage": True}
```

Em `DeepSeekClient.completar`, quando `ao_texto is not None`, trocar o
`client.post` por `client.stream(...)` e montar a resposta:

```python
    def _consumir_stream(
        self, resposta: httpx.Response, ao_texto: Callable[[str], None]
    ) -> RespostaLLM:
        """Monta RespostaLLM a partir do SSE. Deltas de tool_call chegam
        fatiados e SEM repetir id/nome — a montagem é por ``index``, nunca
        por ordem de chegada."""
        texto = ""
        finish = ""
        entrada = saida = 0
        parciais: dict[int, dict[str, str]] = {}
        for linha in resposta.iter_lines():
            if not linha.startswith("data:"):
                continue
            dado = linha[5:].strip()
            if dado == "[DONE]":
                break
            try:
                pedaco = json.loads(dado)
            except ValueError as exc:
                raise RespostaLLMInvalida("chunk SSE inválido") from exc
            uso = pedaco.get("usage") or {}
            if uso:
                entrada = int(uso.get("prompt_tokens") or 0)
                saida = int(uso.get("completion_tokens") or 0)
            for escolha in pedaco.get("choices") or []:
                if escolha.get("finish_reason"):
                    finish = str(escolha["finish_reason"])
                delta = escolha.get("delta") or {}
                if delta.get("content"):
                    texto += delta["content"]
                    ao_texto(texto)
                for tc in delta.get("tool_calls") or []:
                    slot = parciais.setdefault(
                        int(tc.get("index") or 0), {"id": "", "nome": "", "args": ""}
                    )
                    if tc.get("id"):
                        slot["id"] = str(tc["id"])
                    funcao = tc.get("function") or {}
                    if funcao.get("name"):
                        slot["nome"] = str(funcao["name"])
                    if funcao.get("arguments"):
                        slot["args"] += funcao["arguments"]
        chamadas = tuple(
            ToolCall(id=s["id"], nome=s["nome"], argumentos=parse_argumentos(s["args"]))
            for _, s in sorted(parciais.items())
        )
        return RespostaLLM(
            texto=texto or None,
            tool_calls=chamadas,
            tokens_entrada=entrada,
            tokens_saida=saida,
            finish_reason=finish,
        )
```

**Regra de retry:** o laço de tentativas só pode repetir enquanto nenhum byte
de corpo foi lido. `client.stream` entrega o status antes do corpo, então
checar `resposta.status_code` dentro do `with` e sair para o retry sem
consumir; depois que `_consumir_stream` começou, não repete.

- [ ] **Step 5: Repassar no runner**

`executar_turno` ganha `ao_texto: Callable[[str], None] | None = None` e passa
adiante em `llm.completar(...)` (linha ~195). Nenhuma outra lógica muda.

- [ ] **Step 6: Gravar `texto_parcial` com throttle no worker**

Em `copiloto_turnos_job.py`, antes do `executar_turno`:

```python
    # A cada delta gravaria uma transacao por token. 0.4s e o passo que a
    # sondagem de 700ms do front consegue consumir sem escrever a toa.
    INTERVALO_PARCIAL = 0.4
    ultimo_flush = [0.0]

    def _on_texto(parcial: str) -> None:
        marca = time.monotonic()
        if marca - ultimo_flush[0] < INTERVALO_PARCIAL:
            return
        ultimo_flush[0] = marca
        atualizar_progresso(db, turno, texto_parcial=parcial)
```

e `ao_texto=_on_texto` na chamada. Importar `time` e `atualizar_progresso` se
ainda não estiverem no módulo.

- [ ] **Step 7: Rodar a suíte inteira**

```bash
cd portal-gestao && .venv/Scripts/python.exe -m pytest -q
```
Esperado: baseline (541 em `-k copiloto`) + os novos, 0 failed.

- [ ] **Step 8: Commit**

```bash
git add portal-gestao/app/loja/copiloto/port.py portal-gestao/app/clients/deepseek.py \
        portal-gestao/app/loja/copiloto/runner.py portal-gestao/app/copiloto_turnos_job.py \
        portal-gestao/tests/test_copiloto_streaming.py
git commit -m "feat(copiloto): streaming SSE do provedor grava texto_parcial durante o turno"
```

---

### Task 9: Tela Hoje — plural real e severidade visível

`{{ sinais_novos }} novo(s)` e `veículo(s) parado(s)` são o tell nº1 de
ferramenta interna em português. E `severidade-{{ sinal.severidade }}` é classe
morta: o CSS só define `.copiloto-notif-item.severidade-*` (linhas 3624-3626),
então um sinal **crítico é idêntico a um info**.

**Files:**
- Modify: `portal-gestao/app/templates/loja/copiloto_hoje.html:20,113`
- Modify: `portal-gestao/app/static/css/app.css` (bloco `.copiloto-sinal`)
- Test: `portal-gestao/tests/test_copiloto_hoje_texto.py` (criar)

- [ ] **Step 1: Escrever o teste que falha**

```python
"""Plural real e severidade que se vê."""
import re
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "app/templates/loja/copiloto_hoje.html"
CSS = Path(__file__).resolve().parents[1] / "app/static/css/app.css"


def test_template_nao_usa_plural_entre_parenteses():
    texto = TEMPLATE.read_text(encoding="utf-8")
    assert "(s)" not in texto


def test_severidade_do_sinal_tem_regra_de_css():
    """A classe existe no template desde a F4; sem regra, critico e info sao
    visualmente identicos."""
    css = CSS.read_text(encoding="utf-8")
    assert re.search(r"\.copiloto-sinal\.severidade-critico", css)
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd portal-gestao && .venv/Scripts/python.exe -m pytest tests/test_copiloto_hoje_texto.py -q
```
Esperado: 2 FAILED.

- [ ] **Step 3: Plural real no template**

```jinja
{% if sinais_novos %}<span class="muted">{{ sinais_novos }} {{ 'novo' if sinais_novos == 1 else 'novos' }}</span>{% endif %}
```

```jinja
<p><strong>{{ resumo.parado.total }}</strong>
  {{ 'veículo parado' if resumo.parado.total == 1 else 'veículos parados' }} há mais de
  {{ resumo.parado.dias_min }} dias — {{ formatar_brl(resumo.parado.capital_preso) }} de capital preso.</p>
```

- [ ] **Step 4: Severidade com forma e palavra**

Template — a palavra entra junto do título:

```jinja
<strong>{{ sinal.titulo }}</strong>
<span class="copiloto-sinal-grau">{{ rotulos_severidade.get(sinal.severidade, sinal.severidade) }}</span>
```

com `{% set rotulos_severidade = {'critico': 'Crítico', 'atencao': 'Atenção', 'info': 'Informativo'} %}`
no topo do arquivo.

CSS — barra lateral na cor do grau, mesmo padrão do sino:

```css
/* Severidade nunca so por cor: a barra acompanha a palavra no template. */
.copiloto-sinal { padding-left: var(--space-3); border-left: 3px solid var(--line); }
.copiloto-sinal.severidade-critico { border-left-color: var(--danger); }
.copiloto-sinal.severidade-atencao { border-left-color: var(--warn); }
.copiloto-sinal.severidade-info { border-left-color: var(--line-strong); }
.copiloto-sinal-grau {
  margin-left: var(--space-2);
  color: var(--ink-muted);
  font-size: var(--text-xs);
  text-transform: uppercase;
  letter-spacing: .04em;
}
```

- [ ] **Step 5: Rodar os testes e commitar**

```bash
cd portal-gestao && .venv/Scripts/python.exe -m pytest tests/ -q -k copiloto
git commit -am "fix(copiloto): plural real e severidade visivel na tela Hoje"
```

---

### Task 10: Fechamento — altura, mobile e cache-bust

**Files:**
- Modify: `portal-gestao/app/static/css/app.css:3125-3138`
- Modify: `portal-gestao/app/templates/base.html:12`

- [ ] **Step 1: `dvh` e sidebar que não empilha antes do chat**

```css
.copiloto-layout {
  /* dvh, nao vh: no celular a barra de endereco do navegador faz 100vh
     estourar a viewport e empurrar o composer para fora da tela. */
  height: calc(100dvh - 9rem);
}
@media (max-width: 768px) {
  /* O historico vinha ANTES do chat no fluxo: no celular o dono via a lista
     de conversas primeiro e rolava para achar a conversa aberta. */
  .copiloto-layout { grid-template-columns: 1fr; height: auto; }
  .copiloto-historico { order: 2; }
  .copiloto-thread { order: 1; }
}
```

- [ ] **Step 2: Bump obrigatório do cache-bust**

`base.html:12` → `<link rel="stylesheet" href="/static/css/app.css?v=v14">`

Sem isto a produção serve o CSS de antes e nada desta leva aparece. Já
aconteceu em 2026-08-14.

- [ ] **Step 3: Suíte inteira do produto**

```bash
cd portal-gestao && .venv/Scripts/python.exe -m pytest -q
```

- [ ] **Step 4: Verificação de higiene**

```bash
git diff --check
git status --short
```

- [ ] **Step 5: Commit**

```bash
git commit -am "fix(copiloto): dvh no layout, chat antes do historico no celular, app.css v14"
```

---

## Fora de escopo nesta leva (registrado, não esquecido)

- **Cromo** — cabeçalho duplicado do painel, os três avisos repetidos, os
  quatro ✦, a barra de hint permanente. Excluídos por decisão do dono
  (2026-08-15): esta leva é comportamento.
- **Sidebar com agrupamento por data, renomear, apagar e buscar.** Exige rota
  e query novas (`CopilotoConversa.atualizada_em` já existe, o resto não).
  Vale um card próprio.
- **Timestamp por mensagem e editar pergunta.** Mesma razão.
- **Preâmbulo de tool-call sobrescrito pela resposta final** (ver nota da
  Tarefa 8).
