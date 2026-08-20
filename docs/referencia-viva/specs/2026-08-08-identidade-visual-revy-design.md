# Identidade visual Revy — unificar site, catálogo, Loja e Control (2026-08-08)

Decisão de design fechada com o dono em 08/08. Define a marca, os tokens e as regras
que passam a valer nos **quatro front-ends**, e o escopo do que muda em cada um.

O material para pessoas de fora (agência, designer, quem faz criativo) é
`docs/nao-plano/brand/revy-brand-kit.md` v2.0 — este spec é a versão para quem mexe no código.

> ## ⚠️ A marca desta spec foi aposentada em 20/08/2026
>
> **A paleta, as fontes, a forma e as regras de componente continuam valendo** — são
> as que estão em produção. O que morreu foi o **símbolo**: o quadrado de canto
> arredondado com o "R" vazado, junto com a assinatura "Revy / GESTÃO DE REVENDA"
> e todo o inventário de arquivos da §6.
>
> No lugar entrou a assinatura `// Revy` do kit do dono: duas barras inclinadas
> mais a palavra em Chivo 900. **Leia
> [`2026-08-20-assinatura-revy-design.md`](2026-08-20-assinatura-revy-design.md)
> antes de tocar em qualquer coisa de marca.**
>
> Seções mortas: a linha **Símbolo**, **Comportamento do símbolo** e **Assinatura**
> da §2, e a **§6 inteira**. O resto desta spec é as-built.
>
> O plano de execução
> ([`planos/2026-08-08-identidade-visual-revy.md`](../planos/2026-08-08-identidade-visual-revy.md))
> **fica onde está**: a camada de tokens que ele descreve é o código em produção.
> Mas ele traz o `build_marca.py` antigo colado por dentro — leia o aviso no topo
> dele antes de copiar qualquer coisa de lá.

---

## 1. O problema

Uma varredura nos quatro front-ends encontrou **quatro sistemas visuais que não concordam
entre si**, e um problema de marca maior que qualquer um deles.

| Front-end | Fonte | Preto | Papel | Modo escuro |
|---|---|---|---|---|
| `site/index.html` | Hanken Grotesk | `#1b1b1b` | `#f9f9f9` | não tem |
| `portal-gestao` (Loja) | Hanken Grotesk | `#1b1b1b` | `#f9f9f9` | tem |
| `revy-trafego` (Control) | Hanken Grotesk | `#1b1b1b` | `#f9f9f9` | tem |
| `catalogo-publico` | **Inter** | **`#0a0a0a`** | **`#ffffff`** | **não tem** (`color-scheme: light` fixo) |
| `site/assets/*.svg` (logo) | **Inter, não carregada** | **`#0A0A0A`** | — | — |

Achados que motivam este trabalho:

1. **O logo não é um logo.** `revy-mark.svg`, `revy-wordmark.svg` e as variantes são
   `<text font-family="Inter…">` — letra viva desenhada pelo navegador, não contorno vetorial.
   O SVG não carrega a Inter junto. Em máquina sem Inter, **a forma do "R" muda**. No painel,
   o "R" é um `<span class="brand-mark">` em Hanken Grotesk — uma terceira forma. E, como não
   há contorno, **não existe arquivo para levar a Meta Ads, Canva, adesivo de vitrine ou impresso**.
2. **A vitrine que o cliente final vê é a mais desalinhada.** O catálogo usa Inter e branco puro
   enquanto o resto usa Hanken e off-white. É exatamente a tela que entra no anúncio.
3. **O acento é um azul de SaaS colado por cima.** `--brand: #1f6feb` entrou como camada no fim
   dos dois `app.css` (a partir da linha 2058 no Portal), sobre uma base preto-e-branco.
4. **O botão não existe como peça única.** No site é caixa-alta, borda 2px, raio 9px,
   `letter-spacing: .12em`. No painel é caixa-baixa, raio 12px, sem borda. Nada em comum.
5. **Duas folhas já divergiram**: `portal-gestao/app/static/css/app.css` (2939 linhas) e
   `revy-trafego/app/static/css/app.css` (2574 linhas) são cópias que seguiram caminhos próprios.
6. **`docs/nao-plano/brand/revy-brand-kit.md` v1.0 descreve outro produto** — manda usar Inter, lista uma
   paleta que não está em lugar nenhum e cita uma cor "Signal" que a própria tabela não define.

---

## 2. As decisões

Fechadas pelo dono ao longo de quatro rodadas de mockup navegável.

| Peça | Decisão |
|---|---|
| ~~**Símbolo**~~ | ~~**Bloco** — quadrado de canto arredondado com o "R" vazado~~ · **APOSENTADO 20/08**, ver [spec da assinatura](2026-08-20-assinatura-revy-design.md) |
| ~~**Comportamento do símbolo**~~ | ~~Preta sempre; `#000000` no escuro com fio de 1px~~ · **APOSENTADO** — a assinatura nova usa `currentColor` e o fio deixou de existir junto com o quadrado |
| ~~**Assinatura**~~ | ~~Nome + descritor: "Revy" sobre "GESTÃO DE REVENDA"~~ · **APOSENTADA** — o kit não tem descritor |
| **Preto da marca** | `#1b1b1b` (o de produção; aposenta `#0a0a0a` do catálogo e do logo) |
| **Acento** | **Verde racing `#1f4d3a`**, no lugar do azul `#1f6feb` |
| **Fonte de interface** | **Hanken Grotesk** — mantida; aposenta Inter no catálogo |
| **Fonte da frase de marca** | **Newsreader** (peso 300) |
| **Botão** | **Reto** — raio 3px, caixa-baixa, borda de 1px; primário em preto sólido |
| **Menu lateral** | O de hoje: fundo `--brand-tint`, borda `--brand-line`, barra de 3px à esquerda, ícone no acento |
| **Estado na fila** | **Ponto** — círculo de 7px na cor do estado + palavra em `--ink-soft` |
| **Número (KPI)** | Rótulo curto + número grande, **sem linha de explicação embaixo** |
| **Card de veículo** | **Vitrine** — cartão com superfície própria, preço em destaque, dados em pastilhas |
| **Densidade de tabela** | **Média** — linha de ~34px |

### Escolhas que foram descartadas e por quê

- **Archivo como fonte de título** — chegou a ser escolhida e depois revertida pelo dono:
  duas famílias de interface aumentam o custo de carregamento sem ganho dentro do painel.
  Newsreader entrou no lugar, mas **só na frase de marca**, não na interface.
- **Chip de estado sólido** — testado e rejeitado: numa fila de 40 linhas vira mosaico colorido.
- **Acento azul `#1f6feb`** — contradiz a base preto-e-branco.
- **Painel sem caixa** (direção "Ficha") — testado e rejeitado: as superfícies precisam
  contrastar com o papel, que é o que dá profundidade no modo escuro.

---

## 3. Tokens canônicos

Fonte única: `shared/brand/revy-tokens.css` (ver §5). Os valores de neutro são **os que já estão
em produção** — este trabalho não mexe neles, só os torna iguais nos quatro front-ends.

### 3.1 Neutros

| Token | Claro | Escuro | Papel |
|---|---|---|---|
| `--paper` | `#f9f9f9` | `#0a0a0a` | Fundo da página |
| `--surface` | `#ffffff` | `#111111` | Painel, card, cabeçalho da vitrine |
| `--surface-raised` | `#f4f2f1` | `#161616` | Sidebar |
| `--surface-soft` | `#efeceb` | `#1a1a1a` | Hover de menu e de linha de tabela |
| `--ink` | `#1b1b1b` | `#f5f5f5` | Texto principal |
| `--ink-soft` | `#57514f` | `#a3a3a3` | Texto secundário |
| `--ink-muted` | `#6b625f` | `#949494` | Texto apagado (AA nos dois fundos) |
| `--line` | `#ded8d9` | `#2a2a2a` | Borda de painel, separador de linha |
| `--line-strong` | `#cdc6c4` | `#3a3a3a` | Borda de controle |
| `--shadow` | `0 1px 2px rgba(27,20,20,.05)` | `none` | Elevação |

### 3.2 Acento

Escala derivada do `#1f4d3a`, necessária porque criativo precisa de fundo, texto sobre fundo e realce:

| Passo | Hex | Uso |
|---|---|---|
| 900 | `#0f2b20` | Fundo de anúncio |
| 700 | `#1f4d3a` | **Acento no claro** |
| 500 | `#2f7355` | Hover, série de gráfico |
| 300 | `#7fbfa3` | **Acento no escuro** |
| 100 | `#dfeee7` | Tint, faixa |

| Token | Claro | Escuro |
|---|---|---|
| `--brand` | `#1f4d3a` | `#7fbfa3` |
| `--brand-strong` | `#1a4231` | `#9ed0ba` |
| `--brand-ink` | `#ffffff` | `#0a0a0a` |
| `--brand-tint` | `rgba(31,77,58,.09)` | `rgba(127,191,163,.14)` |
| `--brand-line` | `rgba(31,77,58,.32)` | `rgba(127,191,163,.34)` |

`#1f4d3a` tem contraste de **1,6:1** sobre `#0a0a0a` — ilegível. Por isso o acento sobe para o
300 no escuro. Não é escolha estética: é a única forma de manter a mesma família com contraste.

### 3.3 Estado

| Token | Claro | Escuro | Estado |
|---|---|---|---|
| `--st-wait` | `#8a6d1d` | `#d9b04a` | Aguardando |
| `--st-live` | `#57514f` | `#a3a3a3` | Em atendimento |
| `--st-prop` | `#1f4d3a` | `#7fbfa3` | Proposta |
| `--st-won` | `#0d7a4f` | `#3ecf8e` | Ganho |
| `--st-lost` | `#6b625f` | `#949494` | Perdido |
| `--ok` | `#0d7a4f` | `#3ecf8e` | Sucesso, conectado |
| `--warn` | `#8a6d1d` | `#d9b04a` | Alerta |
| `--danger` | `#b42318` | `#f97066` | Falha |
| `--whatsapp` | `#25d366` | `#25d366` | Cor de canal, não de marca |

### 3.4 Forma e tipografia

| Token | Valor | Uso |
|---|---|---|
| `--radius-ctl` | `3px` | Botão, campo, chip, pastilha |
| `--radius-nav` | `8px` | Item de menu lateral |
| `--radius-srf` | `12px` | Painel, card, foto |
| `--font-ui` | `'Hanken Grotesk', 'Segoe UI', system-ui, sans-serif` | Toda a interface |
| `--font-brand` | `'Newsreader', Georgia, serif` | Frase de marca, manchete, criativo |
| `--font-data` | `ui-monospace, 'Consolas', monospace` | Placa, telefone, ID |

---

## 4. Regras de uso

Quatro invariantes. Se uma tela quebrar alguma, ela está errada — não a regra.

1. **Cor nunca vem sozinha.** Todo estado tem forma (ponto) *e* palavra escrita. Quem não
   distingue as duas cores continua lendo a tela.
2. **O acento nunca é texto de status.** `--brand` marca navegação, foco e ênfase de estrutura.
   Status usa a família `--st-*`. É isso que impede `#1f4d3a` (Proposta) e `#0d7a4f` (Ganho)
   de virarem a mesma coisa.
3. **Um rótulo por número.** KPI é rótulo curto + valor. A linha de explicação embaixo sai —
   era ela que fazia três camadas de texto entregarem um número só.
4. **Superfície sempre contrasta com o papel.** Sidebar, painel e card têm cor própria.
   Achatar tudo no mesmo tom mata a profundidade, principalmente no escuro.

### Onde cada fonte entra

| Superfície | Fonte | Por quê |
|---|---|---|
| Painel (Loja, Control) | Hanken Grotesk | Densidade, número tabular, leitura longa |
| Frase do login | Newsreader | Único momento de marca dentro do produto |
| Manchete do site | Newsreader | É onde a personalidade paga |
| Modelo e **preço** do catálogo | Hanken Grotesk | Preço precisa de tabular; serifa atrapalha leitura rápida |
| Criativo de anúncio | Newsreader | Manchete curta em corpo grande |

### Estados terminais não recebem chip

`Ganho` é ✓ + palavra; `Perdido` é texto apagado. Nenhum dos dois ganha ponto colorido.
O orçamento de destaque vai para quem exige ação — um cliente esperando há três horas
importa mais que uma venda fechada semana passada.

---

## 5. A camada compartilhada

Hoje existem quatro cópias divergentes. A correção precisa impedir que divirjam de novo.

**Arquivo canônico:** `shared/brand/revy-tokens.css` — só `:root` e `[data-theme="dark"]`,
sem regra de componente. Nada mais entra nele.

**Distribuição por cópia verificada**, não por import em tempo de execução:

```
shared/brand/revy-tokens.css          ← fonte única, editável
  → portal-gestao/app/static/css/revy-tokens.css
  → revy-trafego/app/static/css/revy-tokens.css
  → catalogo-publico/app/static/css/revy-tokens.css
  → site/assets/revy-tokens.css
```

Um script (`shared/brand/sync-tokens.py`) copia e um teste falha se alguma cópia divergir
do canônico.

**Por que cópia e não import HTTP:** cada produto é um deploy independente (Fly apps
separados) e cada um tem banco e migrations próprios — a regra do repositório é integrar por
contrato, nunca por dependência direta. Uma folha de estilo buscada de outro serviço em runtime
criaria um modo de falha novo (o Control fora do ar despintaria o catálogo) para resolver um
problema que uma cópia verificada resolve sem risco.

**O que continua duplicado:** as regras de componente de Loja e Control. Unificá-las é um
trabalho separado e maior — este spec só garante que os **valores** sejam os mesmos.

---

## 6. A marca: arquivos a produzir ⚠️ SEÇÃO MORTA

> **Nada nesta seção existe mais.** Os seis arquivos abaixo foram apagados em
> 20/08/2026 e a pasta que os guardava (`docs/nao-plano/brand/assets/`) deixou de ser
> a origem — a marca agora nasce em `shared/brand/assets/`, gerada por
> `build_marca.py` e distribuída por `sync_marca.py`. Inventário em vigor na
> [spec da assinatura](2026-08-20-assinatura-revy-design.md).
>
> Mantida aqui só para explicar por que os `<text>` do `site/assets/` foram jogados
> fora: a regra "contorno, nunca fonte viva" nasceu nesta seção e continua valendo.

O entregável mais importante para criativo. Todos em geometria vetorial, sem dependência de fonte.

| Arquivo | Conteúdo |
|---|---|
| `docs/nao-plano/brand/assets/revy-mark.svg` | Símbolo Bloco, `#1b1b1b`, R vazado em branco |
| `docs/nao-plano/brand/assets/revy-mark-reverse.svg` | Símbolo para fundo escuro, `#000000` + fio `rgba(255,255,255,.16)` |
| `docs/nao-plano/brand/assets/revy-wordmark.svg` | "Revy" em Hanken Grotesk **convertido em contorno** |
| `docs/nao-plano/brand/assets/revy-signature.svg` | Wordmark + descritor "GESTÃO DE REVENDA" |
| `docs/nao-plano/brand/assets/revy-signature-reverse.svg` | Idem, para fundo escuro |
| `docs/nao-plano/brand/assets/favicon.svg` + `favicon-32.png` + `apple-touch-icon-180.png` | Derivados do símbolo |

Os cinco SVGs atuais em `site/assets/` são substituídos. Eles não são recuperáveis: `<text>`
não tem contorno para converter.

**Geometria do símbolo** (viewBox `0 0 40 40`):

```svg
<rect width="40" height="40" rx="9" fill="#1b1b1b"/>
<path d="M15.5 30V13h6.8a4.3 4.3 0 0 1 0 8.6h-6.8" fill="none" stroke="#fff"
      stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M21 21.6 27 30" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"/>
```

**O wordmark é gerado em código.** `fontTools` (4.63, já no venv do `portal-gestao`) converte
"Revy" em Hanken Grotesk 700 para contorno com `SVGPathPen`: baixa o TTF estático do Google
Fonts, extrai os glifos, aplica `Transform(1, 0, 0, -1, x, 0)` para inverter o eixo Y e emite
os `<path>`. Verificado em 08/08: saem 4 subcaminhos, ~1,1 KB de dados de path.

Duas ressalvas: o TTF precisa vir com user-agent antigo (`Mozilla/4.0`), porque o woff2 exige
a extensão Brotli, que não está instalada; e o arquivo de peso 700 é o **segundo** da lista
retornada pelo CSS, não o primeiro.

---

## 7. Escopo por front-end

### 7.0 Quem tem modo escuro

Decisão do dono em 08/08: **o modo escuro é dos painéis, não das superfícies públicas.**

| Front-end | Temas |
|---|---|
| `site/` | **só claro** |
| `catalogo-publico/` | **só claro** |
| `portal-gestao/` (Loja) | claro + escuro |
| `revy-trafego/` (Control) | claro + escuro |

O arquivo de tokens continua definindo os dois blocos — quem é só claro simplesmente nunca
recebe `data-theme="dark"` e declara `color-scheme: light`. Isso mantém **um arquivo só** para
os quatro e evita a variante "tokens do público" x "tokens do painel", que voltaria a divergir.

Consequência prática para criativo: **peça de anúncio e vitrine são sempre claras.** Fundo
escuro em criativo é escolha de arte de uma peça específica, com o verde 300 e a marca reversa —
não um tema do produto.


### `site/` (landing)
- **Sempre modo claro** (ver §7.0). Continua sem `[data-theme]` e ganha `color-scheme: light` explícito.
- Tokens vêm de `revy-tokens.css`; o bloco `:root` inline sai.
- Manchetes passam para Newsreader; corpo continua Hanken.
- Botão perde caixa-alta e `letter-spacing: .12em`; vira reto de 3px.
- Logo passa a apontar para os SVGs novos.
- `--green: #25d366` vira `--whatsapp` e deixa de ser usado como cor de marca.

### `catalogo-publico/`
- **Sempre modo claro.** O `color-scheme: light` fixo **fica** — é decisão, não pendência.
  Foto de veículo sobre fundo escuro nunca foi testada e a vitrine não vai ser o lugar de
  descobrir isso.
- **Inter sai, Hanken entra.** É a mudança mais visível para o cliente final.
- `--ink` `#0a0a0a` → `#1b1b1b`; `--paper` `#ffffff` → `#f9f9f9`.
- Card de veículo redesenhado no padrão Vitrine.
- Preço continua em Hanken com `font-variant-numeric: tabular-nums`.

### `portal-gestao/` (Revy Loja)
- Azul `#1f6feb` → verde `#1f4d3a` / `#7fbfa3`. A camada da linha ~2058 troca de valores,
  não de estrutura.
- `.brand-mark` deixa de ser `<span>` com letra e passa a usar o SVG.
- Botões e campos para raio 3px; menu e painel ficam como estão.
- Chip de estado passa para o estilo Ponto.
- KPI perde a linha `<small>` de explicação.
- Frase do login em Newsreader; painel da história sempre preto.

### `revy-trafego/` (Revy Control)
- Mesmas trocas do Portal, na cópia dele do `app.css`.

---

## 8. Não-objetivos

- **Não unificar as regras de componente** de Loja e Control. Só os valores.
- **Não mexer nos 13 itens recusados** em `docs/referencia-viva/2026-08-07-triagem-revisao-ux-loja-control.md`.
  Em especial continuam onde estão: o card "Google Ads — Indisponível" (`L2`) e o
  "Simulações — em construção" no rodapé (`L6`).
- **Não redesenhar telas.** Este trabalho troca marca, cor, forma e tipo — não move informação
  nem muda fluxo. A única exceção é o card de veículo do catálogo, que nunca teve desenho próprio.
- **Não tocar em n8n, Fly, migrations ou contrato HTTP.**

---

## 9. Riscos

| Risco | Mitigação |
|---|---|
| Hanken Grotesk no catálogo muda o LCP (troca de webfont) | Medir antes e depois; ambas vêm do mesmo CDN, o peso é comparável |
| Token de tema escuro vazar para o catálogo ou o site | Os dois declaram `color-scheme: light` e nunca recebem `data-theme`; a conferência visual cobre |
| Newsreader é uma segunda família a carregar | Só nas superfícies de marca (login, site, criativo), nunca no painel |
| `--brand` trocado em dois `app.css` separados pode ficar meio-feito | O teste de sincronia de tokens pega divergência entre as cópias |
| Contraste do verde no escuro | Fixado pelo passo 300 (`#7fbfa3`); qualquer uso de `#1f4d3a` sobre fundo escuro é bug |
| `docs/nao-plano/brand/preview.html`, `index.html`, `portal-mock.html` ficam desatualizados | Marcados como legado no kit v2.0; regerar é trabalho separado |

---

## 10. Verificação

- Contraste AA conferido para `--ink-muted`, `--brand` e cada `--st-*` sobre a superfície
  em que aparecem — **nos dois temas no painel, só no claro no catálogo e no site**.
- Teste de sincronia: as quatro cópias de `revy-tokens.css` batem com o canônico.
- `rg -n "1f6feb|5a95ff"` não retorna nada fora de histórico.
- `rg -n "Inter"` não retorna nada em `catalogo-publico/`.
- Nenhum SVG de marca contém `<text>`.
- `rg -n "data-theme" catalogo-publico/ site/` não retorna nada.
- Suítes de `portal-gestao` e `revy-trafego` passando.
- Conferência visual: login, Resultado e fila **nos dois temas**; vitrine e site **só no claro**.

---

## Referências

- Mockups navegáveis das quatro rodadas (artifacts, 08/08) — direções, kit peça por peça,
  fidelidade ao app de hoje, marca e status.
- `docs/nao-plano/brand/revy-brand-kit.md` v2.0 — versão para pessoas de fora.
- `docs/referencia-viva/2026-08-07-triagem-revisao-ux-loja-control.md` — o que não pode voltar como proposta.
