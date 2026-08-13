# Revy — site marketing

Landing pública da marca, alinhada ao design em `docs/nao-plano/brand/`.

## Abrir local

```powershell
# Windows
start site\index.html
```

Ou sirva a pasta `site/` em qualquer static host (Vercel, Cloudflare Pages, Fly static, nginx).

## Estrutura

O site é um **export estático do design tool** (pasta, não mais arquivo único):

```
site/
  index.html      # landing — HTML pré-renderizado (conteúdo aparece SEM JS), SEO/OG nativo
  assets/         # og.jpg (preview 1200x630), poster-1..7.jpg (capas das cenas), logos, revy-tokens.css
  demos/          # 01..07 — cenas animadas, embutidas em <iframe> lazy pelo index
  README.md
```

## Formato e atualização (a cada novo export)

O design tool passou a exportar em **formato estático de produção**: o `index.html` traz o
**conteúdo pré-renderizado no HTML** (aparece com o JavaScript desligado) e já inclui `lang`,
`title`, `meta description` e Open Graph. **Não rode nenhum injetor de SEO aqui** — o antigo
`apply-seo.mjs` foi **aposentado**; injetar por cima duplicaria as tags.

As **animações** continuam sendo bundles pesados (~1,27 MB cada, React/Babel transpilando no
navegador), embutidas em `<iframe>` com `loading="lazy"` — carregam só quando entram na tela. O
carregamento inicial é leve; a pasta toda soma ~9 MB se rolar o site inteiro.

**Ao trazer um export novo** (de `.../dist/static/`, com o caminho em `$S`):

```bash
cp "$S/index.html"    site/index.html
cp "$S/assets/"*      site/assets/
cp "$S/demos/"*.html  site/demos/
# corrige o host do og:image/canonical enquanto revy.com.br nao existe:
sed -i 's#https://revy\.com\.br/#https://app2037.fly.dev/site/#g' site/index.html
```

> **Pendências conhecidas** (audit 2026-08-09): og:image/canonical vêm apontando pro domínio
> **revy.com.br**, ainda não registrado — por isso o `sed` acima (quando o domínio existir e
> servir o site, ele deixa de ser necessário). Faltam também `<main>`, `<form>` de verdade no
> contato e `prefers-reduced-motion`. Detalhe do rebuild: `docs/fila/2026-08-09-plano-site-rebuild-html-estatico.md`.

## Deploy Fly.io

No path **3-VM**, o site vai **dentro do bundle** `app2037` (nginx edge), não como app
isolado. Ver `deploy/fly/3vm/README.md`.

```powershell
# raiz do monorepo
fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false
```

URL pública: `https://app2037.fly.dev/site/`. O `Dockerfile.app` copia **`site/index.html`,
`site/assets/` e `site/demos/`** para `/srv/site/html` (nginx `:8081`); os `<iframe>` das cenas
usam caminhos relativos (`demos/...`), que resolvem certo atrás do proxy do edge.

> App monólito legado `site2037` foi removido do inventário.

## Relação com o monorepo

| Pasta | Papel |
|---|---|
| `site/` | Marketing Revy (este site) |
| `docs/nao-plano/brand/` | Brand kit, mocks, prompts de animação |
| `portal-gestao/` | App do painel (mesmo visual light Revy) |

Os assets do site (og.jpg, poster-1..7.jpg, logos) vêm no próprio export, em `site/assets/`.
