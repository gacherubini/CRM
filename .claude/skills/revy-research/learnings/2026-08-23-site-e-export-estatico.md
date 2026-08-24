---
gatilho: reexportar ou editar o site de marketing
produto: site
fonte: repo
verificado_em: 2026-08-24
---
# `site/` e export estatico: nao ha o que "consertar" no HTML

Desde 09/08/2026 o `site/` e uma **pasta** exportada pelo design tool em formato estatico
de producao: `index.html` pre-renderizado (o conteudo aparece com o JavaScript desligado,
com `lang`, `title`, `description` e Open Graph nativos), mais `assets/` e `demos/`. O
`index.html` vem com `style=` cravado, entao **qualquer edicao de layout morre no proximo
export** — mude no design tool, nao no arquivo.

Duas armadilhas por export:

- **`apply-seo.mjs` foi aposentado** e deletado. O export ja traz SEO; rodar apply-seo por
  cima duplicaria as tags. Nao recriar.
- O tool escreve `og:image`, `og:url` e canonical apontando para o dominio que estava na
  fonte, que nem sempre e o dominio que serve o site. **Confira e corrija o host a cada
  export** (o site vive hoje em `revyapp.com.br`, no Cloudflare Pages, e nao no Fly).

Pendencia conhecida, que nao e bug de deploy: as animacoes ainda sao bundles pesados
(~1,27 MB cada, transpilando no navegador) embutidos em `<iframe loading=lazy>`; falta
a11y (`<main>`, form real no contato, `prefers-reduced-motion`).

Descoberta de passagem: o site **nao retorna 404** — caminho inexistente responde 200 com
HTML de fallback. Pode importar para SEO e para a verificacao da Meta.
