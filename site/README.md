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
