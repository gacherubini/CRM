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

App: `site2037` · região `gru`

```powershell
cd site
fly deploy --app site2037 --remote-only
```

URL: https://site2037.fly.dev

Autostop ligado (custa pouco em idle).

## Relação com o monorepo

| Pasta | Papel |
|---|---|
| `site/` | Marketing Revy (este site) |
| `docs/brand/` | Brand kit, mocks, prompts de animação |
| `portal-gestao/` | App do painel (mesmo visual light Revy) |

Quando gerar `hero.mp4` / `hero-poster.jpg`, coloque em `site/assets/`.
