# Arquitetura viva — plano de implementação

> **Para agentes:** SUB-SKILL OBRIGATÓRIA: use `superpowers:subagent-driven-development`
> (recomendado) ou `superpowers:executing-plans`. Os passos usam `- [ ]` para marcação.

**Goal:** transformar a arquitetura da Revy num HTML de zoom contínuo gerado a partir
do código, que se atualiza pelo mesmo comando que já regera o mapa.

**Architecture:** quatro camadas — três já existem no repo (`CONTEXT.md`, `decisoes/`,
`mapa/_frescor.json`) e uma é nova e escrita à mão (`arquitetura.py`). Um gerador em
três estágios com fronteira testável — `carregar` (funde e valida), `dispor` (layout
puro e determinístico), `render` (SVG + JS embutido) — produz um arquivo único
auto-contido.

**Tech Stack:** Python 3.9.6 **stdlib apenas** (`ast`, `json`, `dataclasses`, `pathlib`),
`unittest`, SVG + JavaScript sem biblioteca.

**Spec:** `docs/referencia-viva/specs/2026-08-30-arquitetura-viva-design.md` — leia
antes de começar. O plano argumenta a partir dele.

## Global Constraints

- **Stdlib apenas.** Sem `pyyaml`, sem `tomllib` (é 3.11+; aqui é 3.9.6), sem pytest,
  sem CDN. Se precisar de dependência, pare e pergunte.
- **Nunca `import app`** de produto nenhum (AGENTS.md §5). Tudo é lido como texto e
  parseado com `ast` — igual `gerar_mapa.py:1`.
- **Testes com `unittest`**, não pytest: não existe pytest neste Python.
  macOS `python3`, Windows `python` — esta pasta não tem `.venv`.
- **Layout determinístico.** Nada de força dirigida, nada de `set` iterado sem
  `sorted()`, nada de `hash()`. Duas execuções produzem bytes idênticos.
- **`arquitetura.html` é auto-contido:** nenhum `http://` ou `https://` fora de
  comentário. `file://` bloqueia `fetch()`, então o JSON vai embutido.
- **Sem segredo** no HTML gerado (AGENTS.md §5). O gerador só lê caminho e símbolo,
  nunca valor de env.
- Trabalhe sempre com `cwd = .claude/skills/revy-research/` — os módulos da pasta se
  importam pelo nome (`import cruzamentos`), como `gerar_mapa.py` já faz.

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `arquitetura.py` | **Dados à mão.** `NOS`, `ARESTAS`, `VMS`, `FLUXOS`. Nenhuma lógica. |
| `arq_zoom.js` | O motor de zoom. Só DOM e matemática, não sabe o que é um produto. |
| `arq_modelo.py` | `carregar()` — funde as 4 fontes, valida, devolve `Modelo`. |
| `arq_layout.py` | `dispor()` — `Modelo` → `Cena`. Puro, sem I/O. |
| `arq_render.py` | `render()` — `Cena` → string HTML. |
| `gerar_arquitetura.py` | CLI: `gerar()`, `main(argv)`, `--verificar`. |
| `test_gerar_arquitetura.py` | `unittest` de tudo acima. |
| `arquitetura.html` | Gerado e commitado, como `mapa/*.md` já é. |

Ordem das tasks ataca o risco primeiro: o zoom é a única parte cujo resultado só se
conhece no navegador, então ele vem antes do gerador que depende dele.

---

### Task 1: O motor de zoom, provado com caixas falsas

O risco do projeto inteiro mora aqui. Provar com 3 caixas de mentira custa uma hora;
descobrir depois de escrever o gerador custa o gerador.

**Files:**
- Create: `.claude/skills/revy-research/arq_zoom.js`
- Create: `.claude/skills/revy-research/arq_zoom_demo.html`

**Interfaces:**
- Consumes: nada.
- Produces: um objeto global `Zoom` com
  `Zoom.init(svg: SVGElement, opts: {dur: number}) -> void`,
  `Zoom.voarPara(id: string) -> void`,
  `Zoom.subir() -> void`.
  O SVG que ele controla deve ter `viewBox` e cada caixa navegável precisa de
  `id`, `data-pai` (id do pai, ausente na raiz) e `data-titulo`.
  Grupos de detalhe usam `data-k-min` (escala mínima em que ficam visíveis).
  `arq_render.py` (Task 5) vai emitir exatamente esses atributos.

- [ ] **Step 1: Escrever o motor de zoom**

Crie `arq_zoom.js`. O LOD é **por grupo**, nunca por elemento: atualizar opacidade de
714 nós a cada quadro trava; ~10 grupos não.

```javascript
// Motor de zoom continuo. Nao sabe o que e um produto — so caixas e viewBox.
(function () {
  var svg, base, alvo, atual, anim = null, dur = 450;
  var pilha = [];   // caminho de volta: ids ja visitados

  function vb(el) {
    var p = el.getAttribute("viewBox").split(/[ ,]+/).map(Number);
    return { x: p[0], y: p[1], w: p[2], h: p[3] };
  }
  function setVb(v) {
    svg.setAttribute("viewBox", v.x + " " + v.y + " " + v.w + " " + v.h);
    aplicarLod(base.w / v.w);
  }
  // cubic-bezier(.4,0,.2,1) — aproximacao por Newton nao vale a pena aqui.
  function suavizar(t) { return t < 0.5 ? 4*t*t*t : 1 - Math.pow(-2*t + 2, 3) / 2; }

  function aplicarLod(k) {
    var grupos = svg.querySelectorAll("[data-k-min]");
    for (var i = 0; i < grupos.length; i++) {
      var kmin = parseFloat(grupos[i].getAttribute("data-k-min"));
      // Rampa: invisivel em kmin, opaco em 1.6*kmin. Sem degrade fica piscando.
      var o = (k - kmin) / (kmin * 0.6);
      grupos[i].style.opacity = Math.max(0, Math.min(1, o));
      grupos[i].style.pointerEvents = o > 0.5 ? "auto" : "none";
    }
  }

  function caixaDe(id) {
    var el = svg.getElementById(id);
    if (!el) return null;
    var b = el.getBBox();
    var m = Math.max(b.width, b.height) * 0.08;   // respiro
    return { x: b.x - m, y: b.y - m, w: b.width + 2*m, h: b.height + 2*m };
  }

  function voar(destino, aoFim) {
    if (anim) cancelAnimationFrame(anim);
    var de = vb(svg), t0 = null;
    if (dur === 0) { setVb(destino); if (aoFim) aoFim(); return; }
    function passo(ts) {
      if (t0 === null) t0 = ts;
      var t = Math.min(1, (ts - t0) / dur), e = suavizar(t);
      setVb({
        x: de.x + (destino.x - de.x) * e,
        y: de.y + (destino.y - de.y) * e,
        w: de.w + (destino.w - de.w) * e,
        h: de.h + (destino.h - de.h) * e
      });
      if (t < 1) anim = requestAnimationFrame(passo);
      else { anim = null; if (aoFim) aoFim(); }
    }
    anim = requestAnimationFrame(passo);
  }

  function voarPara(id) {
    var c = caixaDe(id);
    if (!c) return;
    if (atual !== id) { pilha.push(atual); atual = id; }
    voar(c);
    anunciar();
  }

  function subir() {
    if (!pilha.length) return;
    atual = pilha.pop();
    voar(atual ? caixaDe(atual) : base);
    anunciar();
  }

  function anunciar() {
    var el = svg.getElementById(atual);
    var t = el ? el.getAttribute("data-titulo") : "Revy";
    var ev = new CustomEvent("zoom:mudou", { detail: { id: atual, titulo: t } });
    svg.dispatchEvent(ev);
  }

  function init(elemento, opts) {
    svg = elemento;
    base = vb(svg);
    atual = null;
    dur = (opts && opts.dur !== undefined) ? opts.dur : 450;
    // prefers-reduced-motion: salta em vez de voar. Nao e enfeite — quem sente
    // enjoo de movimento nao consegue usar a pagina com a animacao ligada.
    if (window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches) dur = 0;

    svg.addEventListener("click", function (ev) {
      var alvo = ev.target.closest("[data-navegavel]");
      if (alvo && alvo.id) voarPara(alvo.id);
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") subir();
    });
    svg.addEventListener("wheel", function (ev) {
      ev.preventDefault();
      var v = vb(svg), f = ev.deltaY > 0 ? 1.12 : 1 / 1.12;
      var r = svg.getBoundingClientRect();
      var cx = v.x + (ev.clientX - r.left) / r.width * v.w;
      var cy = v.y + (ev.clientY - r.top) / r.height * v.h;
      setVb({ x: cx - (cx - v.x)*f, y: cy - (cy - v.y)*f, w: v.w*f, h: v.h*f });
    }, { passive: false });

    var arrastando = false, px = 0, py = 0;
    svg.addEventListener("pointerdown", function (ev) {
      arrastando = true; px = ev.clientX; py = ev.clientY;
      svg.setPointerCapture(ev.pointerId);
    });
    svg.addEventListener("pointermove", function (ev) {
      if (!arrastando) return;
      var v = vb(svg), r = svg.getBoundingClientRect();
      setVb({ x: v.x - (ev.clientX - px) / r.width * v.w,
              y: v.y - (ev.clientY - py) / r.height * v.h, w: v.w, h: v.h });
      px = ev.clientX; py = ev.clientY;
    });
    svg.addEventListener("pointerup", function () { arrastando = false; });

    setVb(base);
  }

  window.Zoom = { init: init, voarPara: voarPara, subir: subir };
})();
```

- [ ] **Step 2: Escrever a demo com caixas falsas**

Crie `arq_zoom_demo.html`. Três níveis de mentira, só para sentir o voo. Este arquivo
é descartável e **não** vai para o git (é apagado no Step 5).

```html
<!doctype html>
<meta charset="utf-8">
<title>zoom — demo</title>
<style>
  html,body{margin:0;height:100%;background:#f9f9f9;font-family:system-ui}
  svg{width:100vw;height:100vh;display:block;cursor:grab}
  #trilha{position:fixed;top:12px;left:12px;background:#fff;padding:6px 12px;
          border:1px solid #ded8d9;border-radius:6px;font-size:13px}
</style>
<div id="trilha">Revy</div>
<svg id="mapa" viewBox="0 0 1000 600">
  <g id="app2037" data-navegavel data-titulo="app2037">
    <rect x="40" y="40" width="440" height="480" fill="#fff" stroke="#1f4d3a"/>
    <text x="60" y="80" font-size="24" fill="#1b1b1b">app2037</text>
    <g id="chatbot" data-navegavel data-titulo="Chatbot API">
      <rect x="70" y="110" width="380" height="180" fill="#efeceb" stroke="#cdc6c4"/>
      <text x="86" y="140" font-size="16">Chatbot API</text>
      <g data-k-min="3">
        <text x="86" y="170" font-size="6">POST /webhook/mensagem</text>
        <text x="86" y="182" font-size="6">GET /v1/agente/config</text>
        <text x="86" y="194" font-size="6">FollowupWorker</text>
      </g>
    </g>
    <g id="motor" data-navegavel data-titulo="Motor de Simulação">
      <rect x="70" y="320" width="380" height="160" fill="#efeceb" stroke="#cdc6c4"/>
      <text x="86" y="350" font-size="16">Motor</text>
      <g data-k-min="3">
        <text x="86" y="380" font-size="6">POST /v1/simulacoes</text>
        <text x="86" y="392" font-size="6">SPOF: Playwright single-flight</text>
      </g>
    </g>
  </g>
  <g id="n8n" data-navegavel data-titulo="n8n2037">
    <rect x="560" y="40" width="400" height="200" fill="#fff" stroke="#1f4d3a"/>
    <text x="580" y="80" font-size="24">n8n2037</text>
  </g>
</svg>
<script src="arq_zoom.js"></script>
<script>
  var svg = document.getElementById("mapa");
  svg.addEventListener("zoom:mudou", function (ev) {
    document.getElementById("trilha").textContent = ev.detail.titulo || "Revy";
  });
  Zoom.init(svg, {});
</script>
```

- [ ] **Step 3: Abrir no navegador e conferir os cinco comportamentos**

Rode:
```
open .claude/skills/revy-research/arq_zoom_demo.html          # macOS
start .claude\skills\revy-research\arq_zoom_demo.html         # Windows
```

Confira, um por um:
1. Clicar em `app2037` **voa** para dentro, não corta nem pisca.
2. Continuar clicando no Chatbot afunda mais um nível.
3. As três linhas pequenas (`data-k-min="3"`) aparecem **ao chegar perto**, com
   degradê — não ligam de uma vez.
4. `Esc` sobe um nível; a trilha no canto acompanha.
5. Roda do mouse dá zoom no ponteiro; arrastar move.

Se qualquer um falhar, **conserte aqui** — não siga em frente. Todo o resto do plano
assume que o voo funciona.

- [ ] **Step 4: Portão do dono**

Mostre a demo ao dono antes de continuar. Se a sensação estiver errada — rápido demais,
lento demais, respiro faltando — o ajuste é em `dur` e no `m` de `caixaDe()`, e é agora
que sai barato.

- [ ] **Step 5: Apagar a demo e commitar só o motor**

```bash
rm .claude/skills/revy-research/arq_zoom_demo.html
git add .claude/skills/revy-research/arq_zoom.js
git commit -m "feat(arquitetura): o motor de zoom, provado antes do gerador existir"
```

---

### Task 2: `arq_modelo.py` — funde as quatro fontes e recusa referência morta

**Files:**
- Create: `.claude/skills/revy-research/arq_modelo.py`
- Create: `.claude/skills/revy-research/test_gerar_arquitetura.py`

**Interfaces:**
- Consumes: `varredura.Entrada` (`varredura.py:31`, campos `secao, chave, simbolo,
  arquivo, linha`); `mapa/_frescor.json` no formato `{"sha": str,
  "inventario": {produto: [ {secao, chave, simbolo, arquivo, linha}, ... ]}}`.
- Produces:
  `ReferenciaMorta(Exception)`;
  dataclasses congeladas `No, Aresta, Vm, Passo, Fluxo, Modelo`;
  `carregar(raiz: Path, frescor: dict, nos: dict, arestas: list = (), vms: dict = None,
  fluxos: dict = None) -> Modelo`.
  Task 4 (`dispor`) e Task 5 (`render`) consomem `Modelo`.

- [ ] **Step 1: Escrever o teste que falha**

Crie `test_gerar_arquitetura.py`:

```python
import unittest
from pathlib import Path

import arq_modelo
import varredura


FRESCOR_FALSO = {
    "sha": "abc1234",
    "inventario": {
        "chatbot-api": [
            {"secao": "rota", "chave": "GET /health/live",
             "simbolo": "/health/live", "arquivo": "app/main.py", "linha": 523},
            {"secao": "worker", "chave": "FollowupWorker",
             "simbolo": "FollowupWorker", "arquivo": "app/followup_job.py",
             "linha": 64},
        ],
    },
}
NOS_FALSOS = {"chatbot-api": {"titulo": "Chatbot API", "papel": "conversa"}}


class TestCarregar(unittest.TestCase):
    def setUp(self):
        self.raiz = varredura.raiz_repo()

    def test_no_minimo_vira_modelo_com_as_entradas_do_frescor(self):
        m = arq_modelo.carregar(self.raiz, FRESCOR_FALSO, NOS_FALSOS)
        self.assertEqual(len(m.nos), 1)
        self.assertEqual(m.nos[0].titulo, "Chatbot API")
        self.assertEqual(len(m.nos[0].entradas), 2)

    def test_produto_que_nao_existe_no_frescor_falha_nomeando_o_produto(self):
        nos = {"produto-fantasma": {"titulo": "Fantasma", "papel": "nada"}}
        with self.assertRaises(arq_modelo.ReferenciaMorta) as ctx:
            arq_modelo.carregar(self.raiz, FRESCOR_FALSO, nos)
        self.assertIn("produto-fantasma", str(ctx.exception))

    def test_decisao_que_nao_existe_falha_nomeando_o_arquivo(self):
        nos = {"chatbot-api": {"titulo": "Chatbot API", "papel": "conversa",
                               "decisoes": ["2099-01-01-nunca-escrita.md"]}}
        with self.assertRaises(arq_modelo.ReferenciaMorta) as ctx:
            arq_modelo.carregar(self.raiz, FRESCOR_FALSO, nos)
        self.assertIn("2099-01-01-nunca-escrita.md", str(ctx.exception))

    def test_modelo_e_ordenado_por_chave_sempre(self):
        nos = {
            "chatbot-api": {"titulo": "B", "papel": "x"},
            "estoque-api": {"titulo": "A", "papel": "y"},
        }
        frescor = {"sha": "a", "inventario": {"chatbot-api": [], "estoque-api": []}}
        m = arq_modelo.carregar(self.raiz, frescor, nos)
        self.assertEqual([n.chave for n in m.nos], ["chatbot-api", "estoque-api"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

```
cd .claude/skills/revy-research && python3 -m unittest test_gerar_arquitetura -v
```
Esperado: `ModuleNotFoundError: No module named 'arq_modelo'`.

- [ ] **Step 3: Escrever `arq_modelo.py`**

```python
"""Funde arquitetura.py + _frescor.json + decisoes/ num Modelo. Stdlib apenas.

Nao importa `app` de produto nenhum (AGENTS.md secao 5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from varredura import Entrada


class ReferenciaMorta(Exception):
    """O arquitetura.py cita algo que nao existe mais.

    Erro, nunca aviso: referencia morta em silencio e exatamente como este
    arquivo apodreceria. Mesmo espirito do saude.citacoes_mortas.
    """


@dataclass(frozen=True)
class No:
    chave: str
    titulo: str
    papel: str
    vm: str | None = None
    termo: str | None = None
    decisoes: tuple[str, ...] = ()
    spof: bool = False
    spof_porque: str | None = None
    entradas: tuple[Entrada, ...] = ()


@dataclass(frozen=True)
class Aresta:
    de: str
    para: str
    protocolo: str = "http"
    sincrono: bool = True
    retry: bool = False
    inferida: bool = False


@dataclass(frozen=True)
class Vm:
    chave: str
    tipo: str = "fly-machine"
    contem: tuple[str, ...] = ()
    nota: str = ""


@dataclass(frozen=True)
class Passo:
    no: str
    faz: str
    protocolo: str | None = None
    sincrono: bool = True


@dataclass(frozen=True)
class Fluxo:
    chave: str
    titulo: str
    passos: tuple[Passo, ...] = ()
    invariante: str | None = None


@dataclass(frozen=True)
class Modelo:
    nos: tuple[No, ...] = ()
    arestas: tuple[Aresta, ...] = ()
    vms: tuple[Vm, ...] = ()
    fluxos: tuple[Fluxo, ...] = ()
    sha: str = ""


def _entradas_de(inventario: dict, produto: str) -> tuple[Entrada, ...]:
    # sorted() aqui e no resto do modulo: layout deve ser determinstico, e a
    # ordem do JSON nao e contrato.
    brutas = inventario.get(produto, [])
    achatadas = [
        Entrada(secao=e["secao"], chave=e["chave"], simbolo=e["simbolo"],
                arquivo=e["arquivo"], linha=e["linha"])
        for e in brutas
    ]
    return tuple(sorted(achatadas, key=lambda e: (e.secao, e.chave, e.arquivo)))


def carregar(raiz: Path, frescor: dict, nos: dict,
             arestas: list = (), vms: dict = None,
             fluxos: dict = None) -> Modelo:
    inventario = frescor.get("inventario", {})
    pasta_decisoes = Path(__file__).resolve().parent / "decisoes"

    construidos = []
    for chave in sorted(nos):
        bruto = nos[chave]
        if chave not in inventario:
            raise ReferenciaMorta(
                f"no '{chave}' nao existe no _frescor.json. "
                f"Produtos conhecidos: {', '.join(sorted(inventario))}"
            )
        decisoes = tuple(bruto.get("decisoes") or ())
        for d in decisoes:
            if not (pasta_decisoes / d).exists():
                raise ReferenciaMorta(
                    f"no '{chave}' cita a decisao '{d}', que nao existe em decisoes/"
                )
        construidos.append(No(
            chave=chave,
            titulo=bruto["titulo"],
            papel=bruto["papel"],
            vm=bruto.get("vm"),
            termo=bruto.get("termo"),
            decisoes=decisoes,
            spof=bool(bruto.get("spof")),
            spof_porque=bruto.get("spof_porque"),
            entradas=_entradas_de(inventario, chave),
        ))

    conhecidos = {n.chave for n in construidos}
    feitas = []
    for a in arestas or ():
        for ponta in ("de", "para"):
            if a[ponta] not in conhecidos:
                raise ReferenciaMorta(
                    f"aresta {a['de']} -> {a['para']} usa '{a[ponta]}', "
                    "que nao esta em NOS"
                )
        feitas.append(Aresta(
            de=a["de"], para=a["para"],
            protocolo=a.get("protocolo", "http"),
            sincrono=a.get("sincrono", True),
            retry=a.get("retry", False),
            inferida=a.get("inferida", False),
        ))
    feitas.sort(key=lambda a: (a.de, a.para, a.protocolo))

    maquinas = []
    for chave in sorted(vms or {}):
        b = (vms or {})[chave]
        for dentro in b.get("contem", ()):
            if dentro not in conhecidos:
                raise ReferenciaMorta(
                    f"vm '{chave}' contem '{dentro}', que nao esta em NOS"
                )
        maquinas.append(Vm(chave=chave, tipo=b.get("tipo", "fly-machine"),
                           contem=tuple(sorted(b.get("contem", ()))),
                           nota=b.get("nota", "")))

    caminhos = []
    for chave in sorted(fluxos or {}):
        b = (fluxos or {})[chave]
        passos = tuple(Passo(no=p["no"], faz=p["faz"],
                             protocolo=p.get("protocolo"),
                             sincrono=p.get("sincrono", True))
                       for p in b.get("passos", ()))
        caminhos.append(Fluxo(chave=chave, titulo=b["titulo"], passos=passos,
                              invariante=b.get("invariante")))

    return Modelo(nos=tuple(construidos), arestas=tuple(feitas),
                  vms=tuple(maquinas), fluxos=tuple(caminhos),
                  sha=frescor.get("sha", ""))
```

Nota: um passo de fluxo pode citar uma VM (`evolution2037`, `n8n2037`) que não é nó —
por isso `Passo.no` **não** é validado contra `NOS`. É deliberado.

- [ ] **Step 4: Rodar e ver passar**

```
cd .claude/skills/revy-research && python3 -m unittest test_gerar_arquitetura -v
```
Esperado: 4 testes, OK.

- [ ] **Step 5: Commitar**

```bash
git add .claude/skills/revy-research/arq_modelo.py \
        .claude/skills/revy-research/test_gerar_arquitetura.py
git commit -m "feat(arquitetura): o modelo funde as quatro fontes e recusa citacao morta"
```

---

### Task 3: `arquitetura.py` — a Revy de verdade

**Files:**
- Create: `.claude/skills/revy-research/arquitetura.py`
- Modify: `.claude/skills/revy-research/test_gerar_arquitetura.py` (acrescentar classe)

**Interfaces:**
- Consumes: `arq_modelo.carregar`.
- Produces: módulo com `NOS: dict`, `ARESTAS: list`, `VMS: dict`, `FLUXOS: dict`.
  Task 6 importa este módulo.

Antes de escrever, colete os fatos (não invente):

```bash
grep -E "^\[program|command=" deploy/fly/3vm/supervisord.conf
grep -nE "proxy_pass|location" deploy/fly/3vm/nginx-edge.conf
grep -H "^app" deploy/fly/3vm/fly.*.toml
ls .claude/skills/revy-research/decisoes/
sed -n '1,60p' AGENTS.md          # a tabela da secao 2 nomeia os produtos
```

Fatos já verificados e que devem aparecer: a `app2037` roda nginx, healthz, chatbot,
estoque, portal, revy-trafego, catalogo e motor via supervisord; o `nginx-edge.conf`
escuta `:8080` e roteia para chatbot `:8001`, estoque `:8002`, catálogo `:8003`,
motor `:8004`, portal `:9000`, tráfego `:9010`, healthz `:8099`; os apps Fly são
`app2037`, `motor2037`, `n8n2037`, `evolution2037` (mais `suite-pg`).

- [ ] **Step 1: Escrever o teste que falha**

Acrescente ao `test_gerar_arquitetura.py`:

```python
import json

import arquitetura


class TestArquiteturaReal(unittest.TestCase):
    def setUp(self):
        self.raiz = varredura.raiz_repo()
        frescor_path = (Path(__file__).resolve().parent / "mapa" / "_frescor.json")
        self.frescor = json.loads(frescor_path.read_text(encoding="utf-8"))

    def test_o_arquivo_real_carrega_sem_referencia_morta(self):
        m = arq_modelo.carregar(
            self.raiz, self.frescor, arquitetura.NOS,
            arquitetura.ARESTAS, arquitetura.VMS, arquitetura.FLUXOS)
        self.assertGreaterEqual(len(m.nos), 6)

    def test_todo_produto_do_frescor_tem_no(self):
        faltando = set(self.frescor["inventario"]) - set(arquitetura.NOS)
        self.assertEqual(faltando, set(), f"produto sem no: {faltando}")

    def test_app2037_carrega_seis_produtos(self):
        # O fato de infra que hoje nao esta desenhado em lugar nenhum: uma
        # maquina que cai leva seis coisas junto.
        self.assertEqual(len(arquitetura.VMS["app2037"]["contem"]), 6)

    def test_todo_no_tem_titulo_e_papel(self):
        for chave, no in arquitetura.NOS.items():
            self.assertIn("titulo", no, chave)
            self.assertIn("papel", no, chave)
```

- [ ] **Step 2: Rodar e ver falhar**

```
cd .claude/skills/revy-research && python3 -m unittest test_gerar_arquitetura -v
```
Esperado: `ModuleNotFoundError: No module named 'arquitetura'`.

- [ ] **Step 3: Escrever `arquitetura.py`**

Siga o schema da §4 do spec. Comece pelo esqueleto abaixo e **complete** com os fatos
que você coletou — os seis produtos do `_frescor.json`, as VMs, e ao menos os quatro
fluxos que o AGENTS.md §2 já nomeia (WhatsApp→Motor/Estoque, venda Loja→outbox→Control,
publicação de veículo, login). Ancore em cada nó as decisões de `decisoes/` que
governam aquele produto.

```python
"""Intencao da arquitetura: o que o codigo nao diz de si mesmo. Stdlib apenas.

Escrito a MAO. Muda quando a TOPOLOGIA muda, nao quando nasce uma rota.
Mesmo padrao do TESTES em gerar_mapa.py:39 — dict literal, comentado.

Nao ha YAML aqui de proposito: o Python do dono e 3.9.6, sem pyyaml, e
tomllib so existe no 3.11+.
"""
from __future__ import annotations

NOS: dict[str, dict] = {
    "chatbot-api": {
        "titulo": "Chatbot API",
        "papel": "conversa",
        "vm": "app2037",
        "decisoes": ["2026-08-13-whatsapp-dois-modos-sem-coexistencia.md"],
    },
    "motor-simulacao": {
        "titulo": "Motor de Simulação",
        "papel": "banco",
        "vm": "app2037",          # a API; o worker Playwright vive na motor2037
        "spof": True,
        "spof_porque": (
            "Playwright single-flight e o driver engole o clique que falha — ver "
            "learnings/2026-08-23-driver-playwright-engole-o-clique-que-falha.md"
        ),
    },
    # ... complete: estoque-api, portal-gestao, revy-trafego, catalogo-publico
}

ARESTAS: list[dict] = [
    {"de": "portal-gestao", "para": "revy-trafego",
     "protocolo": "outbox", "sincrono": False, "retry": True},
    # ... complete com o que cruzamentos.py NAO infere
]

VMS: dict[str, dict] = {
    "app2037": {
        "tipo": "fly-machine",
        "contem": ["catalogo-publico", "chatbot-api", "estoque-api",
                   "motor-simulacao", "portal-gestao", "revy-trafego"],
        "nota": "nginx-edge:8080 na frente, supervisord por tras",
    },
    # ... complete: motor2037, n8n2037, evolution2037, suite-pg
}

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
    # ... complete: venda-outbox, publicacao-veiculo, login
}
```

- [ ] **Step 4: Rodar e ver passar**

```
cd .claude/skills/revy-research && python3 -m unittest test_gerar_arquitetura -v
```
Esperado: 8 testes, OK. Se `ReferenciaMorta` disparar, o nome do produto ou da decisão
está errado — o erro traz o nome. Conserte o `arquitetura.py`, nunca o validador.

- [ ] **Step 5: Commitar**

```bash
git add .claude/skills/revy-research/arquitetura.py \
        .claude/skills/revy-research/test_gerar_arquitetura.py
git commit -m "feat(arquitetura): a camada de intencao, com as decisoes ancoradas nas caixas"
```

---

### Task 4: `arq_layout.py` — layout recursivo com limiares derivados

**Reescrita em 30/08.** A versão anterior tinha dois níveis fixos e `K_MIN` constante.
O protótipo no navegador provou os dois errados. Leia o §5 e o §6 do spec antes.

**Files:**
- Create: `.claude/skills/revy-research/arq_layout.py`
- Modify: `.claude/skills/revy-research/test_gerar_arquitetura.py`

**Interfaces:**
- Consumes: `arq_modelo.Modelo`, `arq_modelo.No` (recursivo: `No.filhos: tuple[No, ...]`,
  `No.entradas: tuple[Entrada, ...]`).
- Produces:
  `Caixa(chave, tipo, titulo, subtitulo, x, y, w, h, pai, nivel, k_min, k_face)` congelada;
  `Cena(caixas, largura, altura)` congelada;
  `dispor(modelo: Modelo) -> Cena`.
  `tipo` e um de `"vm" | "no" | "item"`. `nivel` e a profundidade (1 = raiz).

**As duas regras que o protótipo cobrou:**

1. **Recursão.** `_dispor_no(no, x, y, nivel)` desenha o nó e chama a si mesma para
   cada `no.filhos`, posicionando o filho DENTRO da caixa do pai. A profundidade vem
   do modelo, não de constante. As `no.entradas` (frescor) viram caixas `item` no fundo
   do nó, depois dos filhos.
2. **Limiar derivado, nunca constante.** Depois de conhecer `largura_total`, um segundo
   passe define, para cada caixa que tem pai:
   `k_min = k_face = 0.6 * (largura_total / largura_do_pai)`.
   `k_min` é onde o interior da caixa ENTRA; `k_face` é onde a face do PAI SAI — são o
   mesmo número de propósito: a troca acontece no mesmo intervalo. Caixas de nível 1
   ficam com `k_min = 0.0`. Use `dataclasses.replace` (a `Caixa` é congelada).
   Sem isso, uma caixa que só chega a `k=2.27` ao ser clicada, com limiar 3, fica
   invisível para sempre — você entra e não vê nada. Foi o bug real, achado no navegador.

**Constantes:** `MARGEM = 24.0`, `ALTURA_TITULO = 34.0`, `ITEM_H = 13.0`,
`ITEM_W = 190.0`. Grade quadrada (`ceil(sqrt(n))` colunas) para o zoom não virar corredor.

**Determinismo:** ordene tudo por chave; nada de `set` iterado sem `sorted()`, nada de
força dirigida. O HTML é commitado, então posição instável vira ruído no diff.

- [ ] **Step 1: Escrever os testes que falham**

```python
import arq_layout


class TestLayout(unittest.TestCase):
    def _modelo(self):
        raiz = varredura.raiz_repo()
        frescor = {"sha": "a", "inventario": {"chatbot-api": [
            {"secao": "worker", "chave": "FollowupWorker", "simbolo": "F",
             "arquivo": "app/followup_job.py", "linha": 64}]}}
        nos = {"chatbot-api": {"titulo": "Chatbot", "papel": "conversa", "dentro": {
            "canais": {"titulo": "Canais", "papel": "entrada", "dentro": {
                "loja-a": {"titulo": "WhatsApp loja A", "papel": "canal"}}}}}}
        return arq_modelo.carregar(raiz, frescor, nos)

    def test_e_deterministico_byte_a_byte(self):
        self.assertEqual(arq_layout.dispor(self._modelo()),
                         arq_layout.dispor(self._modelo()))

    def test_desce_ate_o_neto(self):
        niveis = {c.nivel for c in arq_layout.dispor(self._modelo()).caixas}
        self.assertIn(3, niveis, "o neto (loja-a) nao virou caixa")

    def test_filho_cabe_dentro_do_pai_em_todo_nivel(self):
        cena = arq_layout.dispor(self._modelo())
        por_chave = {c.chave: c for c in cena.caixas}
        for c in cena.caixas:
            if not c.pai or c.pai not in por_chave:
                continue
            p = por_chave[c.pai]
            self.assertGreaterEqual(c.x, p.x, c.chave)
            self.assertGreaterEqual(c.y, p.y, c.chave)
            self.assertLessEqual(c.x + c.w, p.x + p.w + 0.01, c.chave)
            self.assertLessEqual(c.y + c.h, p.y + p.h + 0.01, c.chave)

    def test_o_limiar_e_alcancavel_clicando_no_pai(self):
        # O bug real: k_min acima do k que clicar no pai atinge deixa o
        # interior invisivel para sempre.
        cena = arq_layout.dispor(self._modelo())
        por_chave = {c.chave: c for c in cena.caixas}
        for c in cena.caixas:
            if not c.pai or c.pai not in por_chave:
                continue
            k_do_pai_cheio = cena.largura / por_chave[c.pai].w
            self.assertLess(c.k_min, k_do_pai_cheio, f"{c.chave} nunca acende")

    def test_id_de_caixa_e_unico(self):
        chaves = [c.chave for c in arq_layout.dispor(self._modelo()).caixas]
        self.assertEqual(len(chaves), len(set(chaves)))
```

- [ ] **Step 2: Rodar e ver falhar**

```
cd .claude/skills/revy-research && python3 -m unittest test_gerar_arquitetura -v
```
Esperado: `ModuleNotFoundError: No module named 'arq_layout'`.

- [ ] **Step 3: Escrever `arq_layout.py`** conforme as regras acima.

- [ ] **Step 4: Rodar e ver passar** (mesmo comando; todos verdes).

- [ ] **Step 5: Commitar** com a mensagem
`feat(arquitetura): layout recursivo, com o limiar saindo do layout`.
Adicione nominalmente só `arq_layout.py` e `test_gerar_arquitetura.py`.

---

### Task 5: `arq_render.py` — o HTML, com o demo como alvo

**Reescrita em 30/08.** Existe um alvo visual já aprovado no navegador:
`.claude/skills/revy-research/arq_zoom_demo.html`. **Leia esse arquivo primeiro.** Ele é
o critério de aceite: o seu `render()` tem que produzir um HTML com a MESMA estrutura,
só que gerado a partir da `Cena` em vez de escrito à mão.

**Files:**
- Create: `.claude/skills/revy-research/arq_render.py`
- Modify: `.claude/skills/revy-research/test_gerar_arquitetura.py`

**Interfaces:**
- Consumes: `arq_layout.Cena`, `arq_layout.Caixa`, `arq_modelo.Modelo`, e o texto de
  `arq_zoom.js`.
- Produces: `render(cena: Cena, modelo: Modelo, js: str) -> str`.

**O contrato de atributos** que `arq_zoom.js` já lê (não invente outros):
`id`, `data-navegavel`, `data-titulo`, `data-k-min` (o interior ENTRA),
`data-face-ate` (a face do pai SAI), `data-aresta="de->para"`.

**A estrutura de cada caixa**, igual à do demo:

```
<g id="..." data-titulo="..." data-navegavel>
  <rect .../>
  <g data-face-ate="{c.k_face}">     titulo grande + subtitulo. SOME ao entrar.
  <g data-k-min="{c.k_min}">         os filhos e os itens. APARECEM ao entrar.
</g>
```

Emita `data-k-min` / `data-face-ate` **apenas quando o valor for > 0**. Nível 1 é sempre
visível, e se uma caixa navegável carregasse `data-k-min`, o `aplicarLod` (que escreve
opacity a cada quadro) brigaria com o `Zoom.acender` da Task 7 e o fluxo piscaria.

**Tamanho de fonte por nível:** o texto de um filho é desenhado nas coordenadas do pai,
então precisa encolher junto — use `fonte = 26 / (nivel ** 1.35)`, uma casa decimal, piso
de 1.5. É o que faz o texto ficar legível exatamente quando a caixa enche a tela. Confira
contra o demo, que usa 30 / 6.5 / 2.4 em três níveis.

**Cores:** de `shared/brand/revy-tokens.css`. Não invente paleta — o learning
`2026-08-23-tokens-de-marca-tem-fonte-unica.md` existe por isso.
`paper #f9f9f9`, `surface #ffffff`, `surface-soft #efeceb`, `ink #1b1b1b`,
`ink-soft #57514f`, `line #ded8d9`, `line-strong #cdc6c4`, `brand #1f4d3a`.

**SPOF** = `stroke-width` grosso na caixa. **Aresta assíncrona** = `stroke-dasharray`.
**Sem retry** = o rótulo `"· sem retry"` no meio da linha. Tudo com legenda na página,
como no demo.

**Escape:** todo texto por `html.escape`, e o JSON embutido com
`.replace("<", "\\u003c")` — `json.dumps` não escapa, e uma chave contendo `</script>`
sairia crua dentro do `<script>`.

- [ ] **Step 1: Escrever os testes que falham**

```python
import re

import arq_render


class TestRender(unittest.TestCase):
    def _html(self):
        raiz = varredura.raiz_repo()
        frescor = {"sha": "a", "inventario": {"chatbot-api": [
            {"secao": "worker", "chave": "FollowupWorker", "simbolo": "F",
             "arquivo": "app/followup_job.py", "linha": 64}]}}
        nos = {"chatbot-api": {"titulo": "Chatbot", "papel": "conversa", "dentro": {
            "canais": {"titulo": "Canais", "papel": "entrada"}}}}
        modelo = arq_modelo.carregar(raiz, frescor, nos)
        return arq_render.render(arq_layout.dispor(modelo), modelo, "/* js */")

    def test_e_auto_contido_sem_nenhuma_url_externa(self):
        sem_comentario = re.sub(r"<!--.*?-->", "", self._html(), flags=re.S)
        self.assertNotIn("http://", sem_comentario)
        self.assertNotIn("https://", sem_comentario)

    def test_emite_as_duas_rampas(self):
        html = self._html()
        self.assertIn("data-k-min=", html)
        self.assertIn("data-face-ate=", html)

    def test_caixa_navegavel_nao_carrega_data_k_min(self):
        # Senao o aplicarLod briga com o Zoom.acender e o fluxo pisca.
        for grupo in re.findall(r"<g [^>]*>", self._html()):
            if "data-navegavel" in grupo:
                self.assertNotIn("data-k-min", grupo, grupo)

    def test_o_arquivo_e_linha_chega_no_html(self):
        self.assertIn("app/followup_job.py:64", self._html())

    def test_escapa_o_que_viria_a_ser_markup(self):
        raiz = varredura.raiz_repo()
        frescor = {"sha": "a", "inventario": {"chatbot-api": [
            {"secao": "rota", "chave": "GET /a<b>&c", "simbolo": "x",
             "arquivo": "app/main.py", "linha": 1}]}}
        nos = {"chatbot-api": {"titulo": "C", "papel": "x"}}
        modelo = arq_modelo.carregar(raiz, frescor, nos)
        html = arq_render.render(arq_layout.dispor(modelo), modelo, "")
        self.assertNotIn("<b>", html)

    def test_o_js_entra_inteiro(self):
        self.assertIn("/* js */", self._html())

    def test_aresta_assincrona_sai_tracejada_e_marca_falta_de_retry(self):
        raiz = varredura.raiz_repo()
        frescor = {"sha": "a", "inventario": {"chatbot-api": [], "estoque-api": []}}
        nos = {"chatbot-api": {"titulo": "A", "papel": "x"},
               "estoque-api": {"titulo": "B", "papel": "y"}}
        arestas = [{"de": "chatbot-api", "para": "estoque-api",
                    "protocolo": "http", "sincrono": False, "retry": False}]
        modelo = arq_modelo.carregar(raiz, frescor, nos, arestas)
        html = arq_render.render(arq_layout.dispor(modelo), modelo, "")
        self.assertIn("stroke-dasharray", html)
        self.assertIn("sem retry", html)
```

- [ ] **Step 2: Rodar e ver falhar** (`ModuleNotFoundError: arq_render`).

- [ ] **Step 3: Escrever `arq_render.py`** conforme as regras e o demo.

- [ ] **Step 4: Rodar e ver passar.**

- [ ] **Step 5: Commitar** com a mensagem
`feat(arquitetura): o HTML, com as duas rampas e o demo como alvo`.
Adicione nominalmente só `arq_render.py` e `test_gerar_arquitetura.py`.

---

### Task 6: `gerar_arquitetura.py` — CLI, `--verificar`, e o HTML de verdade

**Files:**
- Create: `.claude/skills/revy-research/gerar_arquitetura.py`
- Create: `.claude/skills/revy-research/arquitetura.html` (gerado)
- Modify: `.claude/skills/revy-research/test_gerar_arquitetura.py`
- Modify: `AGENTS.md` (§6, a linha do mapa)
- Modify: `.claude/skills/revy-research/SKILL.md`

**Interfaces:**
- Consumes: `arquitetura` (Task 3), `arq_modelo.carregar`, `arq_layout.dispor`,
  `arq_render.render`, `arq_zoom.js`.
- Produces: `gerar(raiz: Path, destino: Path) -> None`; `main(argv: list[str]) -> int`.
  Mesmo contrato de `gerar_mapa.py:464`: `--verificar` sai 1 quando o arquivo
  commitado está velho.

- [ ] **Step 1: Escrever o teste que falha**

```python
import tempfile

import gerar_arquitetura


class TestCli(unittest.TestCase):
    def test_gerar_escreve_arquivo_nao_vazio(self):
        raiz = varredura.raiz_repo()
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "arquitetura.html"
            gerar_arquitetura.gerar(raiz, destino)
            self.assertGreater(len(destino.read_text(encoding="utf-8")), 5000)

    def test_gerar_duas_vezes_da_bytes_identicos(self):
        raiz = varredura.raiz_repo()
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.html", Path(tmp) / "b.html"
            gerar_arquitetura.gerar(raiz, a)
            gerar_arquitetura.gerar(raiz, b)
            self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_verificar_passa_com_o_html_commitado(self):
        # Se falhar: rode `python3 gerar_arquitetura.py` e commite o resultado.
        self.assertEqual(gerar_arquitetura.main(["--verificar"]), 0)
```

- [ ] **Step 2: Rodar e ver falhar**

```
cd .claude/skills/revy-research && python3 -m unittest test_gerar_arquitetura -v
```
Esperado: `ModuleNotFoundError: No module named 'gerar_arquitetura'`.

- [ ] **Step 3: Escrever `gerar_arquitetura.py`**

```python
"""Gera arquitetura.html a partir do codigo. Stdlib apenas.

Nao importa `app` de produto nenhum (AGENTS.md secao 5) — le o _frescor.json,
que gerar_mapa.py ja produziu, e a camada de intencao do arquitetura.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import arq_layout
import arq_modelo
import arq_render
import arquitetura
import varredura

PASTA = Path(__file__).resolve().parent
DESTINO = PASTA / "arquitetura.html"
FRESCOR = PASTA / "mapa" / "_frescor.json"
ZOOM = PASTA / "arq_zoom.js"


def montar(raiz: Path) -> str:
    frescor = json.loads(FRESCOR.read_text(encoding="utf-8"))
    modelo = arq_modelo.carregar(
        raiz, frescor, arquitetura.NOS, arquitetura.ARESTAS,
        arquitetura.VMS, arquitetura.FLUXOS)
    cena = arq_layout.dispor(modelo)
    return arq_render.render(cena, modelo, ZOOM.read_text(encoding="utf-8"))


def gerar(raiz: Path, destino: Path) -> None:
    destino.write_text(montar(raiz), encoding="utf-8")


def main(argv: list[str]) -> int:
    raiz = varredura.raiz_repo()
    if "--verificar" in argv:
        if not DESTINO.exists():
            print("DIVERGENCIA arquitetura.html nao existe")
            return 1
        if DESTINO.read_text(encoding="utf-8") != montar(raiz):
            print("DIVERGENCIA arquitetura.html esta velho - "
                  "rode sem --verificar e commite")
            return 1
        print("arquitetura confere com o codigo")
        return 0
    gerar(raiz, DESTINO)
    print(f"escrito {DESTINO.relative_to(raiz)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Gerar o HTML de verdade e abrir no navegador**

```
cd .claude/skills/revy-research && python3 gerar_arquitetura.py
open arquitetura.html          # macOS
```

Esta é a prova que teste não dá (learning
`2026-08-23-copiloto-so-se-verifica-no-navegador.md`). Confira:
1. O nível 1 mostra as VMs, e a `app2037` visivelmente contém seis produtos.
2. Clicar no Chatbot voa para dentro e as rotas ficam legíveis.
3. Chegar num item mostra `arquivo:linha` de verdade.
4. `Esc` volta.
5. Nada de texto sobreposto ilegível no nível 1 — se houver, ajuste `K_MIN` em
   `arq_layout.py`.

- [ ] **Step 5: Rodar a suíte inteira**

```
cd .claude/skills/revy-research && python3 -m unittest test_gerar_arquitetura -v
cd .claude/skills/revy-research && python3 -m unittest test_gerar_mapa -v
```
Esperado: ambas OK. A segunda garante que nada do que você acrescentou quebrou o mapa.

- [ ] **Step 6: Registrar o comando onde ele será lembrado**

Em `AGENTS.md` §6, a linha que hoje manda regerar o mapa passa a mandar os dois:

```
Mexeu em rota, modelo, worker, migration ou flag? Regere o mapa **e a arquitetura** e
commite junto com o código: `cd .claude/skills/revy-research && python gerar_mapa.py &&
python gerar_arquitetura.py` (Windows) ou `python3 ...` (macOS).
```

Em `SKILL.md`, acrescente ao bloco de comandos (perto da linha 68):

```
    python gerar_arquitetura.py             # regera arquitetura.html
    python gerar_arquitetura.py --verificar # so confere; sai 1 se estiver velho
```

- [ ] **Step 7: Commitar**

```bash
git add .claude/skills/revy-research/gerar_arquitetura.py \
        .claude/skills/revy-research/arquitetura.html \
        .claude/skills/revy-research/test_gerar_arquitetura.py \
        .claude/skills/revy-research/SKILL.md AGENTS.md
git diff --check
git commit -m "feat(arquitetura): o mapa navegavel entra no mesmo comando que ja regera o mapa"
```

---

---

### Task 7: A camada de fluxos — acender o caminho e apagar o resto

Sem isto, `FLUXOS` é carregado, validado e ignorado — e os itens 3 e 4 do pedido
original (fluxo de auth, fluxo crítico do produto) ficam sem resposta.

**Files:**
- Modify: `.claude/skills/revy-research/arq_render.py`
- Modify: `.claude/skills/revy-research/arq_zoom.js`
- Modify: `.claude/skills/revy-research/test_gerar_arquitetura.py`

**Interfaces:**
- Consumes: `arq_modelo.Fluxo`, `arq_modelo.Passo`, `arq_layout.Cena`.
- Produces: `arq_render._fluxos_html(cena, modelo) -> str` (o seletor + o overlay);
  em `arq_zoom.js`, `Zoom.acender(ids: string[]) -> void` e `Zoom.apagar() -> void`.

- [ ] **Step 1: Escrever o teste que falha**

```python
    def test_o_fluxo_vira_seletor_com_os_passos_em_ordem(self):
        raiz = varredura.raiz_repo()
        frescor = {"sha": "a", "inventario": {"chatbot-api": [],
                                              "motor-simulacao": []}}
        nos = {"chatbot-api": {"titulo": "Chatbot", "papel": "conversa"},
               "motor-simulacao": {"titulo": "Motor", "papel": "banco"}}
        fluxos = {"simular": {
            "titulo": "WhatsApp → simulação",
            "passos": [{"no": "chatbot-api", "faz": "interpreta"},
                       {"no": "motor-simulacao", "faz": "simula",
                        "sincrono": False}],
            "invariante": "a parcela nao volta ao cliente pelo bot"}}
        modelo = arq_modelo.carregar(raiz, frescor, nos, (), None, fluxos)
        html = arq_render.render(arq_layout.dispor(modelo), modelo, "")
        self.assertIn("WhatsApp → simulação", html)
        self.assertIn("a parcela nao volta ao cliente pelo bot", html)
        # a ordem dos passos e o conteudo do fluxo, nao pode sair alfabetica
        self.assertLess(html.index("interpreta"), html.index("simula"))

    def test_passo_pode_citar_vm_que_nao_e_no(self):
        # evolution2037 e n8n2037 aparecem em fluxo sem serem produto.
        raiz = varredura.raiz_repo()
        frescor = {"sha": "a", "inventario": {"chatbot-api": []}}
        nos = {"chatbot-api": {"titulo": "Chatbot", "papel": "conversa"}}
        fluxos = {"f": {"titulo": "T", "passos": [
            {"no": "evolution2037", "faz": "recebe"},
            {"no": "chatbot-api", "faz": "responde"}]}}
        m = arq_modelo.carregar(raiz, frescor, nos, (), None, fluxos)
        self.assertEqual(m.fluxos[0].passos[0].no, "evolution2037")
```

- [ ] **Step 2: Rodar e ver falhar**

```
cd .claude/skills/revy-research && python3 -m unittest test_gerar_arquitetura -v
```
Esperado: FAIL em `test_o_fluxo_vira_seletor_com_os_passos_em_ordem`
(`'WhatsApp → simulação' not found`). O segundo teste já passa — é a garantia de que
o comportamento deliberado da Task 2 continua valendo.

- [ ] **Step 3: Acrescentar o overlay em `arq_render.py`**

```python
def _fluxos_html(cena: Cena, modelo: Modelo) -> str:
    """Seletor de fluxo. A ordem dos passos e o conteudo — nunca ordenar."""
    if not modelo.fluxos:
        return ""
    botoes, dados = [], {}
    for f in modelo.fluxos:
        botoes.append(f'<button data-fluxo="{_e(f.chave)}">{_e(f.titulo)}</button>')
        dados[f.chave] = {
            "titulo": f.titulo,
            "invariante": f.invariante or "",
            "passos": [{"no": p.no, "faz": p.faz, "sincrono": p.sincrono}
                       for p in f.passos],
        }
    json_fluxos = (json.dumps(dados, ensure_ascii=False, sort_keys=True)
                   .replace("<", "\\u003c"))
    passos_html = "".join(
        f'<li>{_e(p.faz)} — <b>{_e(p.no)}</b>'
        f'{"" if p.sincrono else " <i>(fila)</i>"}</li>'
        for f in modelo.fluxos for p in f.passos)
    invariantes = "".join(f'<p class="inv">{_e(f.invariante)}</p>'
                          for f in modelo.fluxos if f.invariante)
    return (f'<div id="fluxos"><b>Fluxos</b> '
            f'{"".join(botoes)}<button data-fluxo="">limpar</button>'
            f'<ol id="passos" hidden>{passos_html}</ol>{invariantes}</div>'
            f'<script>var FLUXOS = {json_fluxos};</script>')
```

Emende `render()`: acrescente `{_fluxos_html(cena, modelo)}` logo depois da `<div
id="legenda">`, o CSS de `#fluxos` (mesma moldura de `#legenda`, ancorado em
`top:12px;right:12px`), e o ligamento:

```javascript
document.getElementById("fluxos").addEventListener("click", function (ev) {
  var chave = ev.target.getAttribute("data-fluxo");
  if (chave === null) return;
  if (!chave) { Zoom.apagar(); document.getElementById("passos").hidden = true; return; }
  Zoom.acender(FLUXOS[chave].passos.map(function (p) { return p.no; }));
  document.getElementById("passos").hidden = false;
});
```

- [ ] **Step 4: Acrescentar `acender`/`apagar` em `arq_zoom.js`**

Dentro da IIFE, antes do `window.Zoom = ...`:

```javascript
  function acender(ids) {
    var dentro = {};
    for (var i = 0; i < ids.length; i++) dentro[ids[i]] = true;
    // Caixa fora do fluxo nao some: apaga. Sumir tira a referencia espacial e
    // o usuario perde onde estava.
    var todas = svg.querySelectorAll("[data-navegavel]");
    for (var j = 0; j < todas.length; j++) {
      todas[j].style.opacity = dentro[todas[j].id] ? "1" : "0.18";
    }
    var setas = svg.querySelectorAll("[data-aresta]");
    for (var s = 0; s < setas.length; s++) {
      var par = setas[s].getAttribute("data-aresta").split("->");
      setas[s].style.opacity = (dentro[par[0]] && dentro[par[1]]) ? "1" : "0.12";
    }
  }

  function apagar() {
    var todas = svg.querySelectorAll("[data-navegavel],[data-aresta]");
    for (var i = 0; i < todas.length; i++) todas[i].style.opacity = "";
  }
```

E troque a última linha para:

```javascript
  window.Zoom = { init: init, voarPara: voarPara, subir: subir,
                  acender: acender, apagar: apagar };
```

**Atenção:** `aplicarLod` escreve `style.opacity` nos grupos `[data-k-min]` a cada
quadro. `acender` escreve nos `[data-navegavel]` e `[data-aresta]`, que são grupos
diferentes — não brigam. Se você fizer um elemento ter os dois atributos, o LOD ganha
e o fluxo pisca.

- [ ] **Step 5: Regerar o HTML ANTES de rodar a suite**

```
cd .claude/skills/revy-research && python3 gerar_arquitetura.py
```

A ordem importa: voce acabou de mudar `render()`, entao o `arquitetura.html` que a
Task 6 commitou ficou velho, e `test_verificar_passa_com_o_html_commitado` falharia.

- [ ] **Step 6: Rodar e ver passar, depois conferir no navegador**

```
cd .claude/skills/revy-research && python3 -m unittest test_gerar_arquitetura -v
open .claude/skills/revy-research/arquitetura.html
```
Esperado: 23 testes, OK.

Clique em "WhatsApp → simulação": só as caixas do caminho ficam acesas, as outras
apagam sem sumir, os passos aparecem em ordem e o invariante fica visível. "limpar"
devolve tudo.

- [ ] **Step 7: Commitar**

```bash
git add .claude/skills/revy-research/arq_render.py \
        .claude/skills/revy-research/arq_zoom.js \
        .claude/skills/revy-research/arquitetura.html \
        .claude/skills/revy-research/test_gerar_arquitetura.py
git commit -m "feat(arquitetura): o fluxo acende o caminho e apaga o resto"
```

---

### Task 8: os nós automáticos — detalhe até o último arquivo

**Acrescentada em 30/08**, depois de medir a distribuição real: 816 entradas caíram em
38 nós, mas mal. `portal-gestao` segurava 154 entradas soltas na raiz, `revy-trafego`
161, `chatbot-api` 115, e o nó `web` do Portal era um balde único de 136 — enquanto
`agente`, `midia`, `outbox`, `provisioning`, `clients`, `conversions` e `email` ficaram
vazios. Agrupar à mão não alcança 816 itens, e o dono pediu detalhe até as partes menores.

A correção: as entradas que **não** casam com nenhum `modulo` escrito à mão viram
sub-nós **derivados do caminho do arquivo**. `app/loja/vendas.py` vira o nó
`loja` → `vendas.py`. O `arquitetura.py` continua sendo a camada de domínio; a árvore
de arquivos vira a camada de baixo, de graça e sempre atualizada.

**Files:**
- Modify: `.claude/skills/revy-research/arq_modelo.py`
- Modify: `.claude/skills/revy-research/test_gerar_arquitetura.py`

**Interfaces:**
- Consumes: `No`, `carregar` (já existentes).
- Produces: `No` ganha o campo `auto: bool = False`. Nós derivados de caminho vêm com
  `auto=True`; nós escritos à mão continuam `False`. Nada mais muda de forma, então
  `arq_layout` e `arq_render` continuam funcionando sem alteração.

**A regra:**

Ao final de `carregar()`, para cada nó que sobrou com entradas, agrupe essas entradas
pelo `arquivo` e construa a subárvore de diretórios:

- O prefixo comum a todos (tipicamente `app/`) é descartado — não vira nó, seria uma
  caixa só envolvendo tudo.
- Cada diretório restante vira um `No` com `auto=True`, `papel="modulo"`,
  `titulo=` o nome do diretório.
- Cada arquivo vira um `No` com `auto=True`, `papel="arquivo"`,
  `titulo=` o nome do arquivo, e as entradas daquele arquivo em `entradas`.
- Diretório com um único filho colapsa no filho (`a/b/c.py` sozinho não gera três
  caixas aninhadas, gera uma).
- `chave` do nó automático = o caminho, prefixado pela chave do pai, para não colidir.
- Ordem por chave, sempre. Determinismo continua obrigatório.

**Não** aplique isso dentro de nós que já têm `modulo` casado à mão com poucas entradas —
a regra vale para o que sobrou, não para o que já tem dono.

- [ ] **Step 1: Escrever os testes que falham**

```python
class TestNosAutomaticos(unittest.TestCase):
    def _carrega(self, arquivos):
        raiz = varredura.raiz_repo()
        frescor = {"sha": "a", "inventario": {"chatbot-api": [
            {"secao": "rota", "chave": f"GET /{i}", "simbolo": f"s{i}",
             "arquivo": a, "linha": i + 1}
            for i, a in enumerate(arquivos)]}}
        nos = {"chatbot-api": {"titulo": "Chatbot", "papel": "conversa"}}
        return arq_modelo.carregar(raiz, frescor, nos)

    def _todos(self, no, acc=None):
        acc = acc if acc is not None else []
        acc.append(no)
        for f in no.filhos:
            self._todos(f, acc)
        return acc

    def test_diretorio_vira_no(self):
        m = self._carrega(["app/loja/vendas.py", "app/loja/metas.py",
                           "app/canais/whatsapp.py"])
        titulos = {n.titulo for n in self._todos(m.nos[0])}
        self.assertIn("loja", titulos)
        self.assertIn("canais", titulos)

    def test_arquivo_vira_folha_com_as_entradas(self):
        m = self._carrega(["app/loja/vendas.py", "app/loja/vendas.py"])
        folhas = [n for n in self._todos(m.nos[0]) if n.papel == "arquivo"]
        self.assertEqual(len(folhas), 1)
        self.assertEqual(len(folhas[0].entradas), 2)

    def test_nenhuma_entrada_fica_solta_na_raiz_do_produto(self):
        # E o defeito que motivou esta task: 154 entradas paradas no produto.
        m = self._carrega(["app/loja/vendas.py", "app/canais/whatsapp.py",
                           "app/main.py"])
        self.assertEqual(len(m.nos[0].entradas), 0)

    def test_diretorio_de_filho_unico_colapsa(self):
        m = self._carrega(["app/a/b/c.py"])
        auto = [n for n in self._todos(m.nos[0]) if n.auto]
        self.assertLessEqual(len(auto), 2, [n.chave for n in auto])

    def test_no_escrito_a_mao_nao_vem_marcado_como_auto(self):
        m = self._carrega(["app/main.py"])
        self.assertFalse(m.nos[0].auto)

    def test_continua_deterministico(self):
        a = self._carrega(["app/loja/vendas.py", "app/canais/whatsapp.py"])
        b = self._carrega(["app/canais/whatsapp.py", "app/loja/vendas.py"])
        self.assertEqual([n.chave for n in self._todos(a.nos[0])],
                         [n.chave for n in self._todos(b.nos[0])])
```

- [ ] **Step 2: Rodar e ver falhar**

```
cd .claude/skills/revy-research && python3 -m unittest test_gerar_arquitetura -v
```
Esperado: falha em `test_diretorio_vira_no` (`AssertionError: 'loja' not found`).

- [ ] **Step 3: Implementar** a regra acima em `arq_modelo.py`.

- [ ] **Step 4: Rodar e ver passar**, e depois medir contra o repo real:

```
cd .claude/skills/revy-research && python3 -c "
import json, arq_modelo, arquitetura, varredura
f = json.load(open('mapa/_frescor.json'))
m = arq_modelo.carregar(varredura.raiz_repo(), f, arquitetura.NOS,
                        arquitetura.ARESTAS, arquitetura.VMS, arquitetura.FLUXOS)
def anda(n, d=0, acc=None):
    acc = acc if acc is not None else []
    acc.append((d, n.chave, len(n.entradas)))
    for c in n.filhos: anda(c, d + 1, acc)
    return acc
soltas = sum(len(r.entradas) for r in m.nos)
tudo = [x for r in m.nos for x in anda(r)]
print('nos:', len(tudo), '| entradas:', sum(e for _, _, e in tudo),
      '| soltas na raiz:', soltas, '| profundidade:', max(d for d, _, _ in tudo))
"
```

Esperado: **`soltas na raiz: 0`**, número de nós na casa das centenas, e profundidade
maior que 3. Se ainda houver entrada solta, a regra não cobriu algum formato de caminho.

- [ ] **Step 5: Commitar** com a mensagem
`feat(arquitetura): os nos automaticos, o detalhe desce ate o arquivo`.
Adicione nominalmente só `arq_modelo.py` e `test_gerar_arquitetura.py`.

---

## Antes de dizer que acabou

- `python3 -m unittest test_gerar_arquitetura -v` — verde
- `python3 -m unittest test_gerar_mapa -v` — verde (nada quebrou)
- `python3 gerar_arquitetura.py --verificar` — sai 0
- `python3 gerar_mapa.py --verificar` — sai 0
- `git diff --check` e `git status --short` limpos
- `arq_zoom_demo.html` não existe mais
- Um fluxo acende no navegador e o "limpar" devolve tudo
- Nenhuma entrada do `_frescor.json` ficou solta na raiz de um produto
- O HTML abriu no navegador e você chegou num `arquivo:linha` de verdade

Não mexe em produto nenhum, então não há teste de produto a rodar, nem migration,
nem n8n, nem deploy.

## Fora de escopo

Painel Axiom (§13 do spec) — projeto irmão, spec próprio, começa por instrumentação.
