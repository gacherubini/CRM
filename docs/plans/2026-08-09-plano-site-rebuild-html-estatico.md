# Plano — Rebuild da landing como HTML estático

## Status

**EM GRANDE PARTE RESOLVIDO PELA FERRAMENTA (2026-08-09).** A ferramenta passou a exportar em
**formato estático de produção** (`dist/static/`: `index.html` **pré-renderizado** com conteúdo
visível sem JS + SEO/OG nativo, `assets/`, e `demos/` em `<iframe>` lazy). Essa versão está
**LIVE** no `app2037` e o `apply-seo.mjs` foi **aposentado** (o export já traz SEO). Fluxo de
atualização em `site/README.md`.

Sobra do rebuild manual, agora um BACKLOG menor: (a) as **animações** ainda são bundles pesados
(~1,27 MB cada, React/Babel transpilando no navegador) embutidos em iframe — o único ponto de
peso/jank que resta; (b) **a11y**: `<main>`, `<form>` de verdade no contato, `prefers-reduced-motion`.
Fazer só quando o site virar prioridade; para um piloto, a versão atual já resolve o essencial.

## Problema (por que arrumar um dia)

`site/index.html` é um **export de design tool** (`dc-runtime`): o arquivo é `.html`, mas por
dentro é ~2,5 MB onde **~97% é um bloco de JavaScript + assets** (o maior é um `image/svg+xml`
"compressed" de ~1 MB — o desenho vetorial da moto). A página **é montada no navegador em tempo
de execução** (transpila JSX na hora). Consequências medidas na crítica/audit de 2026-08-09
(`.impeccable/critique/2026-08-09T04-39-47Z__site-index-html.md`):

- **Sem SEO nativo / preview vazio** — mitigado hoje pelo `apply-seo.mjs`, mas é remendo por
  cima do export, não solução de raiz.
- **Peso + jank** — transpila 10 módulos JSX no browser (re-import 3–4×), satura a main thread,
  painéis grandes aparecem em branco durante o scroll. A compressão **já está no máximo**
  (Brotli do proxy do Fly: 2,59 → 1,94 MB), então o transfer não é o gargalo — é o SVG gigante
  da moto + o custo de CPU do runtime.

## Objetivo do rebuild

Reescrever a **mesma landing** como HTML/CSS estático de verdade: conteúdo (título, seções,
textos) **direto no HTML**, animações como CSS/JS leve, imagens otimizadas (a moto como
JPEG/WebP, não SVG de 1 MB). Ganhos: carrega instantâneo, sem jank, **SEO nativo** (aposenta o
`apply-seo.mjs`), e some a dependência do design tool para publicar.

## Escopo (é UMA página — bounded)

Preservar copy e marca (mode = **Persuade**; `docs/brand/revy-brand-kit.md`; tokens em
`shared/brand/revy-tokens.css`; site sempre claro). Seções a reproduzir:

1. Nav + hero (headline Newsreader, CTAs) + demo animado (chat WhatsApp + diagrama de fluxo).
2. Strip de lojas (reais e autorizadas — dono confirmou 2026-08-09).
3. "Quatro passos".
4. "Cinco telas" — tabs interativas com mockups do Revy Loja.
5. Tráfego pago (3 cards + gráfico "Resultado da campanha" **sem números**, como está — honesto).
6. "O que a Revy não faz" (seção escura).
7. Contato (form real: `<form>`, `<select>` nativo, submit — corrige os gaps de a11y do audit).

## Esforço (expectativa honesta)

Conteúdo/layout/copy é **rápido**. O trabalho real é **recriar os demos animados fielmente** —
a animação do chat, o diagrama de fluxo, os mockups do Revy Loja e as tabs interativas — e a
**responsividade** (mobile não era verificável no export atual). Por ser **uma página**, é
limitado, mas não é "minutos".

## Antes de começar

É trabalho de design de UI → passar pelo fluxo de brainstorming/impeccable. Insumos prontos:
o relatório de crítica+audit em `.impeccable/critique/`, o `PRODUCT.md` e este plano. Aproveitar
para resolver os itens de a11y do audit (lang, `<main>`, `<form>` real, `prefers-reduced-motion`)
que já vêm de graça num rebuild estático.

## Enquanto não fizer

Continuar exportando do design tool → `node site/apply-seo.mjs site/index.html` → commit →
`fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false`. Item nº1 de perf de baixo
custo, se quiser adiantar: **trocar a moto-SVG por foto otimizada no próprio design tool**
(~1 MB a menos + menos CPU), sem depender do rebuild.
