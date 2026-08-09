# Revy — site marketing

Landing pública da marca, alinhada ao design em `docs/brand/`.

## Abrir local

```powershell
# Windows
start site\index.html
```

Ou sirva a pasta `site/` em qualquer static host (Vercel, Cloudflare Pages, Fly static, nginx).

## Estrutura

```
site/
  index.html      # landing
  assets/         # logos, poster/vídeo do hero
  README.md
```

## SEO e preview social (rodar a CADA novo export)

O `index.html` é um bundle que **só renderiza via JavaScript** — sem tratamento, Google e os
scrapers de link (WhatsApp, Instagram, Facebook) recebem uma página vazia. O script
`apply-seo.mjs` injeta no `<head>` do export: `lang`, `meta description`, `canonical`,
Open Graph + Twitter Card (imagem de preview = `assets/hero-poster.jpg`) e troca o
`<noscript>` "requires JavaScript" por um fallback com o conteúdo real (hero + como funciona +
o que a Revy não faz). É **idempotente** e mexe só no `<head>`.

**Sempre que você trouxer um export novo do design tool, rode isto ANTES de commitar/deployar:**

```powershell
# depois de copiar o novo revy-site.html para site\index.html
node site\apply-seo.mjs site\index.html
```

Se pular esse passo, o próximo export volta a ficar invisível pro Google/preview.

## Deploy Fly.io

No path **3-VM**, o site vai **dentro do bundle** `app2037` (nginx edge), não como app
isolado. Ver `deploy/fly/3vm/README.md`.

```powershell
# raiz do monorepo
fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false
```

URL pública típica: `https://app2037.fly.dev` (path do site no edge).

> App monólito legado `site2037` foi removido do inventário.

## Relação com o monorepo

| Pasta | Papel |
|---|---|
| `site/` | Marketing Revy (este site) |
| `docs/brand/` | Brand kit, mocks, prompts de animação |
| `portal-gestao/` | App do painel (mesmo visual light Revy) |

Quando gerar `hero.mp4` / `hero-poster.jpg`, coloque em `site/assets/`.
