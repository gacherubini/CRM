---
gatilho: esconder um `<svg>` com hidden e ele continuar aparecendo
produto: .claude/skills/revy-research
custo: duas vistas sobrepostas na tela, sem erro no console
fonte: repo
verificado_em: 2026-08-30
---
# `hidden` não esconde um `<svg>`, por dois motivos independentes

**Gatilho:** você escondeu um `<svg>` com `hidden` e ele continua na tela.

Duas causas diferentes, e as duas mordem no mesmo dia:

**1. `svg{display:block}` ganha de `[hidden]`.** A regra padrão do navegador é
`[hidden]{display:none}`, e ela tem a mesma especificidade de qualquer seletor
de atributo — mas o seu `svg{display:block}` vem da folha do autor, que vence a
do navegador. O atributo fica lá, correto, e o elemento continua visível.
Precisa da regra explícita:

```css
svg{display:block}
svg[hidden]{display:none}
```

**2. `<svg>` não tem a propriedade IDL `hidden`.** `hidden` é definido em
`HTMLElement`; um `<svg>` é `SVGElement`, que não herda de `HTMLElement`. Então
`svgEl.hidden` lê `undefined` e `svgEl.hidden = true` só cria uma propriedade
JavaScript solta no objeto — sem nenhum efeito no atributo nem no DOM.

O sintoma pior é o segundo, porque ele **também quebra a leitura**: um guard do
tipo `if (!svg.hidden) ...` fica sempre verdadeiro, e aí um `keydown` no
`document` age nas duas vistas ao mesmo tempo, inclusive na invisível.

```javascript
// nao funciona em <svg>
svgEl.hidden = true;
if (!svgEl.hidden) { ... }

// funciona
svgEl.setAttribute("hidden", "");
svgEl.removeAttribute("hidden");
if (!svgEl.hasAttribute("hidden")) { ... }
```

Achado em `arq_render.py` e `arq_zoom.js` ao pôr duas vistas (Arquitetura e
Schema) no mesmo documento. **Nenhum dos dois deixa rastro no console.** Ver
[`2026-08-30-setpointercapture-no-svg-engole-o-clique.md`](2026-08-30-setpointercapture-no-svg-engole-o-clique.md)
e [`2026-08-23-copiloto-so-se-verifica-no-navegador.md`](2026-08-23-copiloto-so-se-verifica-no-navegador.md).
