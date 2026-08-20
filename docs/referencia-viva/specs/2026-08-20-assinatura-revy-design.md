# A assinatura `// Revy` — marca em vigor (2026-08-20)

As-built da marca que substituiu o símbolo Bloco. Vale nos **quatro front-ends**.

A spec de identidade de 08/08
([`2026-08-08-identidade-visual-revy-design.md`](2026-08-08-identidade-visual-revy-design.md))
continua valendo para **paleta, fontes, forma e componentes** — este documento
substitui só a parte de marca dela.

---

## 1. O que mudou, e o que não

O dono trouxe um kit de marca em 20/08. **Ele não trouxe cor nova**: papel
`#F9F9F9`, papel fundo `#EFECEB`, tinta `#1B1B1B`, verde `#1F4D3A`, verde claro
`#7FBFA3` e texto de apoio `#57514F` já eram, um a um, os tokens de
`shared/brand/revy-tokens.css`. Hanken Grotesk e Newsreader idem.

O que ele trouxe foi a **assinatura**: duas barras inclinadas mais a palavra em
**Chivo 900**. Ela aposenta o quadrado de canto arredondado com o "R" vazado.

| | Antes (08/08) | Agora (20/08) |
|---|---|---|
| Símbolo | quadrado `rx=9` com o R vazado a `stroke` | duas barras inclinadas, em contorno |
| Palavra | Hanken Grotesk 700 | **Chivo 900** |
| Descritor | "GESTÃO DE REVENDA" sob o nome | não existe |
| Cor | preta sempre; `#000000` + fio de 1px no escuro | **`currentColor`** |
| Origem | `docs/nao-plano/brand/assets/` | `shared/brand/assets/` |

**O `currentColor` é a decisão que mais economiza código.** A marca fica tinta no
tema claro e branca no escuro sem nenhuma regra por tema — as três linhas
`[data-theme="dark"] .brand-mark …` que existiam nos dois `app.css` só para o
quadrado preto não sumir na barra lateral escura morreram junto com o quadrado.

## 2. Decisões do dono

| Pergunta | Decisão |
|---|---|
| Peso da palavra | **Chivo 900**, confirmado depois de comparar 900/800/700/600/500 lado a lado |
| Quem assina a barra lateral do **Revy Loja** | o **ícone** `//R` assina, o nome da **loja** fica no comando, e a assinatura inteira vai no **rodapé** da barra |
| Barra lateral do **Revy Control** | assinatura inteira + "Control" — ali não há nome de loja disputando o topo |
| Vitrine pública (**catálogo**) | a loja continua no topo com a própria inicial; a Revy assina no rodapé, no lugar do "Powered by Revy" |
| Linguagem editorial dos criativos | entra **só no catálogo**. O site já é editorial e é export de ferramenta — ver §6 |

**Por que o topo da barra lateral não é da Revy:** é a tela que o lojista usa o dia
inteiro, e ali ele se reconhece pelo nome da própria loja. Trocar *Moto Prime* por
*Revy* tira a loja da própria casa. Rodapé é onde plataforma assina.

## 3. Geometria — medida, não estimada

Tudo em múltiplos da **altura de caixa alta** (a altura de tinta do "R"), que é a
única medida estável entre o PNG do kit e a fonte. Medido pixel a pixel em
`logo-revy-tinta.png` e `icone-barras-r-tinta.png`.

| Medida | Valor |
|---|---|
| Altura das barras | **1,1756 ×** a caixa alta |
| Inclinação | **15,0°** |
| Quanto descem abaixo da linha de base | **0,0789** caixa alta |
| Respiro barras → R, na **assinatura** | **0,3513** caixa alta |
| Respiro barras → R, no **ícone** | **0,1649** caixa alta |
| Entreletras | **−0,03em** |
| Caixa alta do Chivo 900 | **0,69em** |

Os dois respiros são **diferentes de propósito**: na assinatura as barras precisam
ler como elemento separado da palavra; no ícone elas fecham para formar uma marca
compacta. Não unifique.

O Chivo 900 puro sai **~3% mais largo** que o PNG do kit — o export tem uma
compressão leve. Vir da fonte é o que mantém a marca nítida e recolorível; os 3%
não se veem em 16–20px.

## 4. Como a marca é produzida

Nunca desenhe à mão. **Gera e distribui:**

```bash
python shared/brand/build_marca.py   # baixa o Chivo 900, extrai contorno, compõe
python shared/brand/sync_marca.py    # distribui para os 4 front-ends
```

Origem canônica: `shared/brand/assets/`. Dez arquivos, em dois grupos:

| Grupo | Arquivos | Cor | Onde entra |
|---|---|---|---|
| **Herdam a cor** | `revy-bars`, `revy-icon`, `revy-wordmark`, `revy-signature` | `currentColor` | **inline** no HTML, via `{% include %}` |
| **Tinta cravada** | `revy-icon-tinta`, `revy-icon-branco`, `revy-signature-tinta`, `revy-signature-branca`, `favicon`, `icone-app` | hex | favicon, ícone de app, `<img>` do site |

**Por que inline e não `<img>`:** num `<img>` o `currentColor` resolve para preto e a
marca some no tema escuro. Só inline ele pega a cor do tema. É por isso que os SVG
que herdam cor vão para `templates/marca/` e não para `static/`.

Destinos em `DESTINOS_MARCA` (`shared/brand/tokens.py`). `test_copias_em_dia` guarda
a sincronia, igual ao dos tokens.

## 5. Onde a marca aparece

| Front-end | Topo | Rodapé | Favicon |
|---|---|---|---|
| **Revy Loja** | ícone `//R`, 27px, + nome da loja | assinatura, 13px | sim |
| **Revy Control** | assinatura, 19px, + "Control" | — | sim |
| **Catálogo** | inicial e nome **da loja** | "Feito com" + assinatura | sim |
| **Telas de entrada** (6) | assinatura, 24px e 26px | — | sim |
| **Site** | `<img>` 104px | `<img>` 124px | sim |

As larguras do site foram escolhidas para a **letra** ficar do tamanho de antes: a
assinatura é mais larga que o wordmark porque ganhou as barras.

## 6. O site não recebe a linguagem editorial — só a marca

`site/index.html` é **export de ferramenta de design**: cada elemento carrega
`style=` com hex cravado e classes geradas (`x1`, `x2`…). O `site/README.md`
documenta que um export novo sobrescreve o arquivo. Qualquer mudança de tipografia
ou layout feita à mão ali **morre no próximo export** e vira mais um item permanente
na lista de "reaplicar à mão".

E o site já é editorial: Newsreader no hero, papel `#f9f9f9`, chips em mono. Ele não
precisava da linguagem — precisava da assinatura, que é troca de arquivo e sobrevive.

## 7. Invariantes

- **Contorno, nunca fonte viva.** `test_marca.py` recusa `<text>` e `font-family`
  em qualquer arquivo da marca. A regra nasceu em 08/08 e continua: o arquivo vai
  para impresso, Canva e favicon, onde a fonte pode não existir.
- **A marca não é verde.** Tinta ou branca; nunca o acento.
- **Barra nunca mais fina que a letra.** Se algum dia o peso do Chivo mudar, a
  largura da barra tem que acompanhar a haste — a razão é 0,427 × a haste.
- **Mexeu no `assets/`? Rode o `sync_marca.py`.** Senão `test_copias_em_dia` cai.
- **Mexeu no `app.css`? Suba o `?v=`** em *todos* os templates que o carregam —
  as seis telas de auth têm o seu próprio, separado do `base.html`.

## 8. Armadilhas pagas

- **O Google Fonts devolve os `@font-face` em ordem crescente de peso.** Casar peso
  com URL por posição, contra uma lista decrescente, troca 900 por 500 **em
  silêncio**. Case pelo `font-weight:` do bloco. (O sintoma é a haste engrossar
  quando o peso diminui.)
- **`test_template_nao_carrega_cor_propria` e o hook de design varrem o arquivo
  inteiro, comentário incluído.** Citar um hex ou escrever a tag de imagem dentro de
  um comentário Jinja quebra o teste. Reescreva o comentário; não afrouxe a regra.
- **Pasta de assets órfã mata teste em silêncio.** `docs/brand/assets` sumiu numa
  reorganização do `docs/` e deixou `test_marca.py` com 14 falhas por semanas. Os
  assets agora moram ao lado de quem os gera.
- **O símbolo antigo estava inline em seis telas de auth**, fora de qualquer
  `base.html`. Grep por template de barra lateral não acha.
- **O site não retorna 404.** Qualquer caminho inexistente em `revyapp.com.br`
  responde 200 com HTML de fallback — o que engana quem tenta confirmar que um
  arquivo saiu do ar. Comportamento anterior a esta mudança.

---

## Estado

LIVE em 20/08/2026. Commit `3072b73`; `app2037` v153 e `revyapp.com.br` no
Cloudflare Pages.
