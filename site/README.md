# Revy — site marketing

Landing pública da marca. **Este README é publicado junto com o site** (fica em
`revyapp.com.br/README.md`) — não escreva aqui nada que não possa ser lido por qualquer um.

## Onde vive

**`https://revyapp.com.br`** — Cloudflare Pages, projeto `revyapp`, por **direct upload**.

Saiu do bundle do Fly em 16/08/2026. Publicar o site **não é mais deploy do `app2037`**:
o `Dockerfile.app` não copia mais esta pasta, e o `/site` do edge virou 301 para cá.
Histórico e armadilhas: [`../docs/referencia-viva/design/2026-08-16-onboarding-meta-dominio-asbuilt.md`](../docs/referencia-viva/design/2026-08-16-onboarding-meta-dominio-asbuilt.md).

## Publicar

```bash
npx wrangler pages deploy site --project-name=revyapp --branch=main
```

**`--branch=main` não é opcional.** Sem ele o wrangler usa a branch git atual e o deploy vira
*preview* — sobe, responde num `<hash>.revyapp.pages.dev` e o domínio continua servindo a
versão anterior, sem erro nenhum. Já aconteceu.

Tudo o que está nesta pasta vai ao ar. `wrangler pages deploy` **não respeita `.assetsignore`**
(isso é de Workers Static Assets, não de Pages), então a única forma de não publicar um arquivo
é ele não estar aqui.

## Estrutura

```
site/
  index.html               # landing — HTML pré-renderizado (conteúdo aparece SEM JS), SEO/OG nativo
  privacidade.html         # servida em /privacidade
  termos.html              # servida em /termos
  exclusao-de-dados.html   # servida em /exclusao-de-dados
  assets/                  # og.jpg (1200x630), poster-1..7.jpg, marca, revy-tokens.css
  demos/                   # 01..07 — cenas animadas, embutidas em <iframe> lazy pelo index
```

**As URLs canônicas não têm `.html`.** O Pages responde 308 de `/privacidade.html` para
`/privacidade`. Links internos e `<link rel="canonical">` já usam a forma limpa — manter assim.

As três páginas legais existem porque a **Meta exige** as URLs de Política de Privacidade,
Termos e Exclusão de dados no cadastro do app. Elas descrevem o tratamento de dados que o
sistema realmente faz; ao mudar o que se coleta ou como se protege, elas mudam junto.

O rodapé traz **razão social, CNPJ, endereço e telefone**. Não remover: é a prova de
vínculo entre o site e a empresa que a verificação da Meta procura, e o CNPJ é novo e sem
nome fantasia.

**Isso deixou de ser teoria em 24/08/2026:** a verificação da empresa saiu `Verificada` —
CCMEI como documento único, confirmação pelo método **Email** em `contato@revyapp.com.br`,
um dia após submeter. O revisor compara o documento com os *Detalhes da empresa* do
portfólio e com **este rodapé**; o CCMEI escreve "RUA PAULISTA" por extenso e o rodapé
precisa continuar batendo letra a letra. Ao mexer em razão social, CNPJ, endereço ou
telefone daqui, saiba que está mexendo na prova de uma verificação já concedida — a Meta
revalida. Detalhes:
[`../docs/referencia-viva/design/2026-08-16-onboarding-meta-dominio-asbuilt.md`](../docs/referencia-viva/design/2026-08-16-onboarding-meta-dominio-asbuilt.md).

**Dois telefones no site, de propósito** (desde 23/08):

| Onde | Número | Por quê |
|---|---|---|
| bloco Contato e bloco de identidade das legais | `+55 19 99846-9808` | é o do cadastro do CNPJ — o revisor da Meta compara site e documento |
| botão flutuante e links `wa.me` | `5551980336365` | é por onde o lead fala com a Revy |

Parece incoerência e não é: apontar o botão de WhatsApp para um número que não tem WhatsApp
mataria a captação para ganhar uma linha de rodapé. Ao mudar o telefone do cadastro do CNPJ,
mude **o primeiro**; o `wa.me` só muda se o número comercial mudar.

## Ao trazer um export novo do design tool

O export vem em formato estático de produção: o `index.html` traz o conteúdo pré-renderizado
(aparece com JavaScript desligado) e já inclui `lang`, `title`, `meta description` e Open Graph.
**Não rode injetor de SEO** — o antigo `apply-seo.mjs` foi aposentado; injetar por cima duplica
as tags.

```bash
cp "$S/index.html"    site/index.html
cp "$S/assets/"*      site/assets/
cp "$S/demos/"*.html  site/demos/
```

Depois de copiar, **reaplicar à mão** o que o export sobrescreve:

- host de `canonical`, `og:url`, `og:image` e `twitter:image` → `https://revyapp.com.br/`
  (o export ainda emite `revy.com.br`, que é de terceiro — ver o as-built)
- rodapé: razão social, CNPJ, endereço e `contato@revyapp.com.br`
- links do rodapé para `/privacidade`, `/termos`, `/exclusao-de-dados`
- **a marca**: o export traz o símbolo antigo (quadrado preto com o R vazado).
  A marca em vigor desde 20/08/2026 é a assinatura `// Revy` — duas barras mais
  a palavra em Chivo 900. Os arquivos são **gerados**, não desenhados à mão:

  ```bash
  python shared/brand/build_marca.py   # gera o contorno a partir do Chivo 900
  python shared/brand/sync_marca.py    # distribui, site/assets incluído
  ```

  Depois de rodar, apagar de `assets/` qualquer `revy-mark.svg`,
  `revy-wordmark.svg` ou `revy-signature.svg` que o export tenha trazido de
  volta — eles são o símbolo aposentado, e **tudo o que fica nesta pasta vai
  ao ar**. No `index.html`, o `<img>` do topo e o do rodapé apontam para
  `assets/revy-signature-tinta.svg` (larguras 104px e 124px), e as quatro
  páginas usam `assets/favicon.svg` como ícone, não o `revy-mark.svg`.

As animações são bundles pesados (~1,27 MB cada, React/Babel transpilando no navegador), em
`<iframe loading="lazy"`, e carregam só ao entrar na tela. Carga inicial leve; a pasta soma
~9 MB se rolar o site todo.

Pendências de acessibilidade do rebuild de 09/08: faltam `<main>`, `<form>` de verdade no
contato e `prefers-reduced-motion`.

## Abrir local

```powershell
start site\index.html
```

Os `<iframe>` das cenas usam caminho relativo (`demos/...`), então abrir o arquivo direto
funciona.
