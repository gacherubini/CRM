---
gatilho: verificar por script uma opacidade que voce acabou de mudar, e ler o valor errado
produto: .claude/skills/revy-research
custo: um conserto que funcionava, declarado quebrado, e uma investigacao atras da causa errada
fonte: repo
verificado_em: 2026-08-30
---
# `getComputedStyle` devolve o meio da transição, não o valor final

**Gatilho:** você mudou uma opacidade por script e foi conferir se pegou —
`getComputedStyle(el).opacity` — e leu o valor **antigo**.

Não é bug e não é cache. Se o elemento tem `transition: opacity .15s`, o valor
computado durante a rampa é o valor **animado do instante**, não o alvo. Ler
logo depois de escrever devolve algo próximo do valor de origem, e um teste do
tipo `opacity > 0.5` reprova um conserto que está funcionando perfeitamente.

Aconteceu ao verificar as arestas internas do mapa de arquitetura: o hover
acendia as setas certas, mas a leitura dizia que nenhuma tinha acendido.
Perdi a investigação procurando defeito no ouvinte de `pointerover`, no
`closest`, no seletor — tudo estava certo.

```javascript
// mente durante 150ms
el.dispatchEvent(new PointerEvent("pointerover", {bubbles: true}));
getComputedStyle(el).opacity;            // "0", e o alvo era "1"

// nao mente: o inline e' o que o codigo de fato escreveu
(el.getAttribute("style") || "").includes("opacity: 1");
```

Três saídas, em ordem de preferência para verificação automatizada:

1. **Leia o atributo `style` inline.** É exatamente o que o seu código
   escreveu, sem interpolação nenhuma no meio.
2. **Corte a transição** antes de medir (`*{transition:none !important}`) —
   é o que o gerador de recorte faz, e é obrigatório de qualquer forma: em
   aba de segundo plano a rampa nem avança, então o screenshot pegaria um
   quadro parado no meio.
3. Se precisar mesmo do computado, espere a transição acabar
   (`transitionend`) — mas em aba de segundo plano esse evento pode não vir.

Vale para qualquer propriedade animável, não só `opacity`. Irmão das outras
armadilhas de verificar SVG no navegador:
[`2026-08-30-hidden-nao-esconde-svg.md`](2026-08-30-hidden-nao-esconde-svg.md)
e [`2026-08-30-setpointercapture-no-svg-engole-o-clique.md`](2026-08-30-setpointercapture-no-svg-engole-o-clique.md).
