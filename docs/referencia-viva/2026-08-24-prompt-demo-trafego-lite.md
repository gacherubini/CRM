# Prompt — `demos/trafego-revy-lite.html`

Formato "lite": um arquivo, sem build, ~20KB, contra os 1,27MB do
`07-trafego-pago.html` atual. **Sem janela macOS** — a cena vive direto sobre o fundo da
página.

---

Construa **um único arquivo HTML autocontido**, `trafego-revy-lite.html`, com uma animação
de ~11 segundos que termina congelada no último frame. Ele vai ser embutido num `<iframe>`
de proporção 16/9 numa landing page. Alvo de tamanho: **até ~20KB**. Sem build, sem
bundler, sem framework, sem JSX, sem dependência externa de JS. Só HTML + CSS + um
`<script>` de JavaScript puro no fim do `<body>`.

## O que a cena mostra

**Não desenhe moldura de janela**: nada de barra de título, semáforos coloridos ou borda
em volta. Os elementos aparecem soltos sobre o fundo transparente do palco, como se
fizessem parte da própria página. Quem carrega superfície são os cartões, cada um com o
seu fundo e a sua sombra discreta.

Composição em duas colunas, com respiro de 96px nas bordas do palco:

**Coluna esquerda (~30% da largura), sem caixa nenhuma:** uma manchete em serifada, bem
grande, em duas linhas — *"O anúncio não esfria."* — e abaixo um parágrafo curto: *"O
assistente da loja responde de madrugada e no domingo. O lead que o anúncio trouxe
continua na conversa — e a venda volta amarrada à campanha."*

**Coluna direita:** um fluxo em três nós que se acendem em sequência, e depois um cartão
de resultado.

1. Cartão **"Campanha no Meta / Click-to-WhatsApp"**, com uma etiqueta preta pequena
   `Anúncio` encostada no canto superior.
2. Uma linha fina conecta ao cartão **"Assistente da loja / Responde na hora, qualquer
   hora"**, que traz três chips de horário em fonte mono — `02:37`, `06:10`, `23:15` —
   que entram um de cada vez, com um leve atraso entre eles.
3. Da saída desse cartão desce uma pílula verde clara: **"nenhum lead esfria"**.
4. Por último, um cartão maior: **"Resultado da campanha / Seminovos · Meta · últimos 90
   dias"**, com um gráfico de linhas de duas séries que se **desenham da esquerda para a
   direita** (anime `stroke-dashoffset` num `<path>` SVG). A linha de cima, mais forte e
   com área preenchida translúcida embaixo, é **"Leads atribuídos"**; a de baixo, mais
   discreta, é **"Motos vendidas"**. As duas legendas aparecem na ponta direita de cada
   linha, cada uma com um pontinho, só depois que a respectiva linha termina de desenhar.

Fique à vontade para mudar a composição, os textos de apoio e o ritmo — não precisa
copiar pixel a pixel. O que **não** muda são as regras técnicas abaixo.

## Regras técnicas — estas são obrigatórias

### Palco e escala

```html
<div id="fit"><div id="stage"> … </div></div>
```

```css
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;overflow:hidden;background:transparent}
#fit{position:fixed;inset:0;overflow:hidden}
#stage{width:1920px;height:1080px;position:absolute;left:0;top:0;
       background:transparent;transform-origin:0 0;overflow:visible}
```

Tudo é desenhado em coordenadas de **1920×1080** e o palco inteiro é escalado por JS:

```js
var stage = document.getElementById('stage');
function fit() {
  var k = Math.min(innerWidth / 1920, innerHeight / 1080);
  stage.style.transform = 'translate(' + ((innerWidth - 1920 * k) / 2).toFixed(2) + 'px,' +
    ((innerHeight - 1080 * k) / 2).toFixed(2) + 'px) scale(' + k + ')';
}
addEventListener('resize', fit, { passive: true });
fit();
```

`html`, `body` e `#stage` são **transparentes de propósito**: a cena se funde ao fundo da
página que embute o iframe. Não pinte um retângulo de fundo em nenhum dos três.

### Superfícies

Sem janela, quem define profundidade são os cartões:

```css
.card{background:var(--surface);border:1px solid var(--line);border-radius:16px;
      box-shadow:0 2px 6px rgba(27,20,20,.05)}
```

Sombra discreta e só nos cartões. Se algum elemento precisar de sombra maior, garanta que
ele tenha respiro suficiente até a borda do palco — `#stage` é `overflow:visible`, mas o
`<iframe>` recorta em 1920×1080 de qualquer jeito.

### Paleta e tipografia — copie exatamente

```css
:root{
  --paper:#f9f9f9; --surface:#fff; --raised:#f4f2f1; --soft:#efeceb;
  --ink:#1b1b1b; --ink-soft:#57514f; --ink-muted:#6b625f;
  --line:#ded8d9; --line-strong:#cdc6c4;
  --g900:#0f2b20; --g700:#1f4d3a; --g500:#2f7355; --g100:#dfeee7; --wa:#25d366;
  --ui:'Hanken Grotesk','Segoe UI',system-ui,sans-serif;
  --ser:'Newsreader',Georgia,serif;
  --mono:ui-monospace,'SF Mono',Consolas,monospace;
}
```

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500&family=Newsreader:opsz,wght@6..72,300&display=swap" rel="stylesheet" />
```

**Escala de corpo — o ponto que mais quebra.** O palco de 1920px é exibido a ~1088px, ou
seja **56,7%**. Tudo encolhe. Dimensione em espaço de palco assim:

| Papel | px no palco | fica na tela |
|---|---|---|
| manchete serifada (`--ser`, weight 300) | 92–104px | 52–59px |
| número grande / destaque | 104px | 59px |
| título de cartão | 30px, weight 500 | 17px |
| corpo e parágrafo | 26–28px | 15–16px |
| rótulo mono maiúsculo (`letter-spacing:.1em`) | 20–22px | 11–12,5px |
| legenda de eixo / metadado | 21–24px | 12–13,6px |

**Nada abaixo de 20px no palco.** Abaixo disso vira textura, não texto.

### A linha do tempo

Um único `requestAnimationFrame`, uma função `render(T)` com `T` em segundos, e um helper
de tween. Nada de `setTimeout` encadeado, nada de `@keyframes` para o roteiro (CSS
transition só para hover, se houver).

```js
var DUR = 11;
var outCubic = function (p) { return 1 - Math.pow(1 - p, 3); };
var inOut = function (p) { return p < .5 ? 4*p*p*p : 1 - Math.pow(-2*p + 2, 3) / 2; };
function tw(t, a, b, s, e, f) {          /* valor de a→b entre os segundos s e e */
  if (t <= s) return a;
  if (t >= e) return b;
  return a + (b - a) * (f || inOut)((t - s) / (e - s));
}

function render(T) { /* posiciona TUDO a partir de T, sem estado acumulado */ }

if (matchMedia('(prefers-reduced-motion: reduce)').matches) { render(DUR); return; }

var t0 = 0;
function frame(now) {
  if (!t0) t0 = now;
  var T = (now - t0) / 1000;
  if (T >= DUR) { render(DUR); return; }   /* último frame e para */
  render(T);
  requestAnimationFrame(frame);
}
render(0);
requestAnimationFrame(frame);
```

Três coisas que caem dessa estrutura e são obrigatórias:

- **`render(T)` tem que ser pura em relação a `T`.** Chamar `render(6.3)` do nada precisa
  desenhar o frame de 6,3s. Nada de "avança um passo". É isso que permite gerar o poster
  congelando um instante exato, e conferir frame a frame sem gravar vídeo.
- **Congela no fim.** Depois de `DUR` a animação para de vez, sem loop e sem rAF pendurado.
- **`prefers-reduced-motion`** vai direto para `render(DUR)` e **não** agenda rAF. Não pode
  ficar em branco.

### Roteiro sugerido (11s)

| T | O que entra |
|---|---|
| 0,0–0,8 | manchete da esquerda sobe e aparece |
| 0,8–1,6 | parágrafo da esquerda |
| 1,6–2,4 | cartão "Campanha no Meta" + etiqueta `Anúncio` |
| 2,4–3,0 | a linha de conexão se estica até o segundo cartão |
| 3,0–3,8 | cartão "Assistente da loja" |
| 3,8–5,0 | os três chips de horário, escalonados ~0,35s entre si |
| 5,0–5,6 | pílula "nenhum lead esfria" |
| 5,6–6,4 | cartão "Resultado da campanha" entra |
| 6,4–9,2 | as duas linhas se desenham (a de baixo começa ~0,4s depois) |
| 9,2–10,2 | as duas legendas de ponta de linha |
| 10,2–11,0 | respiro, sem nada novo; congela |

Entradas: `opacity` de 0→1 em ~0,36s com `outCubic`, junto de `translateY` de 34px→0 em
~0,52s. Use `will-change:transform,opacity` nos elementos que se movem.

### Proibido

- Moldura de janela: barra de título, semáforos, borda externa.
- Qualquer `<script src>` externo, CDN, React, JSX ou transpilação em runtime.
- Imagem externa. Se precisar de arte, desenhe em SVG inline. Caminho relativo para
  `../assets/` só se o arquivo já existir.
- `alert`, `confirm` ou qualquer diálogo.
- Rolagem: `overflow:hidden` no `html,body`. A cena inteira cabe nos 1920×1080.
- Fundo opaco no `html`, no `body` ou no `#stage`.

### Como eu vou conferir

1. Abro em 1920×1080 e em ~500px de largura: a cena encolhe inteira, sem corte e sem
   barra horizontal.
2. Console limpo, zero 404.
3. Ligo `prefers-reduced-motion` e recarrego: cai direto no frame final, parado.
4. Congelo `render(T)` em vários T e confiro que cada frame é coerente.
5. Meço o corpo do texto na tela: nada ilegível a 56,7%.
