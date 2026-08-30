---
gatilho: SVG interativo em que arrastar funciona mas clicar nao navega
produto: .claude/skills/revy-research
custo: uma investigacao inteira apontada para o lugar errado
fonte: repo
verificado_em: 2026-08-30
---
# setPointerCapture no `<svg>` engole todo clique, e o console não avisa

**Gatilho:** um SVG interativo em que arrastar funciona mas clicar não navega.

Ao dar pan num `<svg>` com `svg.setPointerCapture(ev.pointerId)` no `pointerdown`,
o `click` seguinte passa a ter **o próprio `<svg>` como `ev.target`**, não o
elemento clicado. Um `ev.target.closest("[data-navegavel]")` devolve `null`, a
navegação nunca acontece, e **nada aparece no console** — nem erro, nem aviso.
Chamar a mesma função pela API (`Zoom.voarPara("id")`) funciona perfeitamente,
o que aponta o dedo para o lugar errado durante a investigação.

O jeito certo é não capturar o ponteiro: acompanhe `pointermove` normalmente e
use um limiar (uns 3px) para separar arrasto de clique.

```javascript
svg.addEventListener("pointerdown", function (ev) {
  arrastando = true; moveu = false; px = ev.clientX; py = ev.clientY;
  // sem setPointerCapture
});
svg.addEventListener("click", function (ev) {
  if (moveu) return;                       // arrasto termina em click
  var alvo = ev.target.closest("[data-navegavel]");
  if (alvo && alvo.id) voarPara(alvo.id);
});
```

Achado em `arq_zoom.js` (`.claude/skills/revy-research/`) ao construir o mapa de
arquitetura navegável. Duas outras armadilhas do mesmo dia, no mesmo arquivo:

- **Limiar de LOD não pode ser constante.** Um `k_min` fixo em 3 numa caixa que
  só atinge `k=2.27` ao ser clicada deixa o interior invisível para sempre —
  você entra e não vê nada. Derive do layout: `0.6 * (largura_cena / largura_pai)`,
  com piso para o interior não abrir sozinho no zoom inicial.
- **Fonte tem que sair do tamanho da caixa, nunca do nível.** `font-size` 26 numa
  cena de 11 mil unidades de largura dá 3,6px na tela: nenhum nome era legível.

As três só apareceram abrindo a página no navegador. Ver
[`2026-08-23-copiloto-so-se-verifica-no-navegador.md`](2026-08-23-copiloto-so-se-verifica-no-navegador.md).
