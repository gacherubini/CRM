# Varredura de marca — a identidade chega a todas as telas (2026-08-08)

Sequência de `2026-08-08-identidade-visual-revy-design.md`. Aquele spec decidiu a marca e
produziu os tokens; este leva a decisão às ~76 telas dos painéis, saneando a base de CSS que
ainda desenha a maioria delas.

O plano de execução vive em `docs/superpowers/plans/2026-08-08-varredura-marca-todas-as-telas.md`.

**Não redefine nada de marca.** Cor, forma, tipo e regras de uso continuam sendo os do spec
anterior e de `docs/brand/revy-brand-kit.md` v2.0. Aqui só se decide *como* aquilo alcança o
produto inteiro.

---

## 1. O problema

A identidade entrou como **camada no fim** dos dois `app.css` (linha 2059 na Loja, 2149 no
Control). A camada vence no cascade e por isso o que ela toca mudou. O que ela não toca —
a maior parte do arquivo, e portanto a maior parte das telas — continua no sistema antigo.

### 1.1 O arquivo canônico de tokens não pinta nada

`base.html` carrega `revy-tokens.css` e **depois** `app.css`. O `app.css` reabre `:root` e
redeclara 20 dos 40 tokens canônicos. Mesma especificidade, mais tarde no arquivo: o `app.css`
vence, sempre.

| | Loja | Control |
|---|---|---|
| Tokens canônicos redeclarados no `app.css` | 20 | 20 |
| Tokens canônicos que sobrevivem ao cascade | 20 | 20 |
| Desses, quantos alguma regra de fato usa | ~5 | ~5 |

Anulados: `--brand`, `--brand-strong`, `--brand-ink`, `--brand-tint`, `--brand-line`, `--ink`,
`--ink-soft`, `--ink-muted`, `--paper`, `--surface`, `--surface-raised`, `--surface-soft`,
`--line`, `--line-strong`, `--radius`, `--shadow`, `--green`, `--amber`, `--red`, `--online`.

Consequência: **editar `shared/brand/revy-tokens.css` não muda os painéis.** A promessa de fonte
única do spec anterior não está de pé para Loja e Control — vale só para site e catálogo, que não
têm `app.css` reabrindo `:root`.

O teste de sincronia atual não pega isso porque compara as quatro cópias com o canônico, e as
quatro cópias estão corretas. Ninguém compara o canônico com **quem realmente pinta**. A prova de
que o buraco já custou: o âmbar do modo escuro divergiu — `#e3b341` no `app.css` contra `#d9b04a`
no canônico — e passou despercebido.

### 1.2 Duas decisões nunca chegaram ao produto

| Decisão registrada | O que está no código |
|---|---|
| Botão **reto**, raio 3px, borda 1px | `.button { border-radius: 8px }`. A camada trocou só a cor do primário; a forma nunca foi tocada |
| Estado = **Ponto**: círculo de 7px na cor do estado + palavra em `--ink-soft` | Virou pílula `999px` com bolinha dentro — parente do "chip sólido" que foi testado e **rejeitado** |

Ambas confirmadas em escopo pelo dono em 08/08, ao aprovar o desenho desta varredura.

### 1.3 O vocabulário novo está praticamente sem uso

| Token | Usos na Loja | Usos no Control |
|---|---|---|
| `--st-wait` / `--st-live` / `--st-prop` / `--st-won` | 1 / 1 / 1 / 1 | 3 / 1 / 1 / 3 |
| `--st-lost` | 0 | 0 |
| `--ok`, `--warn`, `--danger`, `--whatsapp`, `--font-data` | 0 cada | 0 cada |
| `--radius-ctl` / `--radius-nav` / `--radius-srf` | 3 de 66 `border-radius` | 3 de 63 |

O que está no lugar deles é o vocabulário genérico anterior: `--green` (22 usos na Loja, 29 no
Control), `--amber` (21 / 23), `--red` (16 / 26), `--online` (3 / 0), `--radius` (11 / 10),
`--accent` (3 / 0).

Enquanto `.status` pintar por `--green`, a regra "o acento nunca é texto de status" não tem como
valer: `Proposta` e `Ganho` continuam saindo da mesma variável.

### 1.4 A boa notícia

Os dois arquivos **declaram exatamente o mesmo conjunto de variáveis**, e só uma (`--sc`) tem
valor diferente. Loja e Control divergiram em regras, não em vocabulário — então quase toda
tarefa é a mesma edição nos dois arquivos, e a divergência é detectável por teste.

E os templates estão limpos: das 76 telas, cor crua aparece só nas 5 de autenticação (onde é
legítima — elas aplicam o tema antes do CSS carregar) e em 2 `<style>` inline. **O trabalho é
quase todo CSS.**

---

## 2. As decisões desta rodada

Fechadas com o dono em 08/08.

| Pergunta | Decisão |
|---|---|
| Profundidade | **Varredura de marca.** Levar o sistema decidido a toda tela. Nenhuma informação sai do lugar, nenhum fluxo muda |
| Estratégia de CSS | **Sanear a base no lugar.** Reescrever as regras antigas para usarem os tokens e apagar a camada do fim. Loja e Control seguem em arquivos separados |
| Fatiamento | **Por peça de interface.** Cada tarefa varre os dois arquivos de uma vez |

### Por que não unificar os dois `app.css` agora

Foi considerado e descartado. Loja e Control já seguiram caminhos próprios em dezenas de regras;
unificar exigiria eleger um vencedor em cada uma, e aí telas mudariam de aparência sem intenção —
exatamente o que "varredura, não redesenho" exclui. Esta rodada deixa os dois arquivos com o
mesmo vocabulário e as mesmas peças, que é o pré-requisito de uma unificação futura.

### Por que não continuar empilhando na camada do fim

Foi considerado e descartado. Manteria duas verdades disputando cada seletor, deixaria o diff
ilegível e devolveria o problema na próxima tela nova.

---

## 3. Arquitetura: uma verdade por arquivo

Quatro movimentos. Os três primeiros são pré-requisito do quarto — varrer peça por peça com dois
`:root` brigando significaria consertar cada peça duas vezes.

### 3.1 Devolver autoridade ao canônico

Apagar do `:root` do `app.css` os 20 tokens que já existem em `revy-tokens.css`. A partir daí,
`shared/brand/revy-tokens.css` passa a pintar os quatro front-ends de verdade.

Como os valores hoje coincidem (menos o âmbar escuro), a remoção é visualmente neutra por
construção — e a única diferença real, o âmbar, é corrigida para o valor canônico.

### 3.2 Separar marca de layout

As 23 variáveis locais restantes se dividem em dois destinos:

| Grupo | Variáveis | Destino |
|---|---|---|
| **Escala de layout** | `--space-1..9`, `--text-xs..display`, `--text-metric`, `--gutter`, `--page-inline`, `--ico`, `--sc` | **Ficam locais** no `app.css`. Não são marca: são ritmo e densidade de painel. Um teste passa a garantir que Loja e Control não divirjam nelas |
| **Resquício do sistema antigo** | `--accent`, `--accent-soft`, `--radius` | **Eliminadas.** `--accent: #1b1b1b` é o "preto como acento" que o verde substituiu; `--radius: 12px` é o raio único de antes do sistema 3/8/12 |

Reescrita dos usos: `--accent` → `--ink` ou `--brand` conforme o papel (3 usos, todos na Loja);
`--radius` → `--radius-srf` (11 na Loja, 10 no Control).

### 3.3 Aposentar os apelidos genéricos

`revy-tokens.css` carrega hoje cinco apelidos que existem só para o `app.css` antigo continuar
funcionando: `--green`, `--amber`, `--red`, `--online`, `--radius`. Cada uso migra para o nome
semântico e, no fim, os apelidos saem do canônico.

| Apelido | Substituto |
|---|---|
| `--green` como "deu certo / conectado" | `--ok` |
| `--green` como cor de estado de domínio | a família `--st-*` correspondente |
| `--amber` | `--warn` (estado de alerta) ou `--st-wait` (estado de fila) |
| `--red` | `--danger` |
| `--online` | `--whatsapp` |
| `--radius` | `--radius-srf` |

O corte entre `--ok/--warn/--danger` e `--st-*` segue a regra 2 do spec anterior: `--st-*` é
estado de **registro** (lead, veículo, loja, simulação); `--ok/--warn/--danger` é resultado de
**operação** (conectou, falhou, expirou).

### 3.4 Matar a camada do fim

Cada regra da camada volta para o bloco da peça a que pertence. O arquivo readquire uma seção
por peça, e quem abrir `.button` vê a regra inteira num lugar só — em vez de duas regras a 1.500
linhas de distância disputando o mesmo seletor.

Ao fim, `rg -n "Camada Revy 2026"` não retorna nada.

---

## 4. As peças

Inventário real: 234 classes-raiz e 733 regras na Loja; 201 e 684 no Control. Agrupadas em nove
peças (1–9), mais a fundação (0) e as superfícies específicas de cada produto (10–11).

| # | Peça | Classes principais | O que muda |
|---|---|---|---|
| 0 | **Fundação** | `:root` e a camada do fim | §3.1–3.4 |
| 1 | **Botão** | `button`, `link-button`, `action-links`, `action-stack` | Raio 3px, borda 1px, caixa-baixa. Hierarquia primário / secundário / ghost / danger explícita |
| 2 | **Campo e formulário** | `form-layout`, `form-grid`, `stack-form`, `option-group`, `filter-bar`, `slug-field`, mais `input/select/textarea` | Raio 3px, borda `--line-strong`, foco em `--brand` |
| 3 | **Estado** | `status` (71 regras na Loja, 64 no Control), `status-pill`, `status-chip`, `canal-badge`, `integ-pill` | Forma **Ponto**; família `--st-*`; terminais (`Ganho`, `Perdido`) sem ponto colorido |
| 4 | **Painel e card** | `panel`, `panel-heading`, `panel-body`, `panel-vitrine`, `operations-card`, `integration-card`, `action-panel`, `funil-summary-card`, `empty` | Raio 12px, `--surface`, `--shadow`. A superfície sempre contrasta com o papel |
| 5 | **Tabela e lista** | `vehicle-row`, `vehicle-cell`, `thread`, `integ-row`, `integ-subitem`, `overview-list`, `rowlink`, `readiness-item` | Linha de ~34px, separador `--line`, hover `--surface-soft`. Placa, telefone e ID em `--font-data` |
| 6 | **Número e gráfico** | `metric`, `metric-grid`, `revy-results` (36 regras em cada), `funil-*`, `split-legend`, `dashboard-*`, `day-col` | Rótulo curto + valor, **sem linha de apoio**; `tabular-nums`; série de gráfico em `--green-500` |
| 7 | **Navegação e shell** | `nav-link`, `brand-mark`, `sidebar`, `topbar`, `control-tab`, `page-heading`, `section-title`, `eyebrow`, `environment`, `avatar` | Item de menu em raio 8px; o resto absorve a camada do fim sem mudar de aparência |
| 8 | **Alerta, faixa e vazio** | `alert`, `revy-alert-strip`, `sim-status-banner`, `handoff-bar`, `empty`, `revy-onboarding` | `--ok` / `--warn` / `--danger`; ícone acompanha o tema |
| 9 | **Autenticação** | `login-*`, `convite_aceitar`, `senha_esqueci`, `senha_redefinir` | Frase em Newsreader, painel da história sempre preto. As cores cruas do `<head>` continuam — são o anti-flash — mas passam a citar os valores canônicos |
| 10 | **Específicas da Loja** | `vitrine-card`, `vehicle-photo`, `composer`, `sim-step`, `funil-time-grid`, `roi-insights` | Herdam as peças 1–8; só o que sobrar de avulso |
| 11 | **Específicas do Control** | `google-step`, `danger-zone`, `next-steps`, `integration-stats`, `readiness-item` | Idem |

**Ordem:** 0 primeiro; depois 1→8 da peça mais compartilhada para a mais específica, para que
cada tarefa encontre menos surpresa que a anterior; 9 a 11 por último.

---

## 5. Verificação

### 5.1 Guardas automáticas

Cada uma nasce falhando na tarefa que a introduz e passa a proteger o resto do trabalho.

| Guarda | O que impede |
|---|---|
| **Nenhum token canônico é redeclarado no `app.css`** | Que o canônico volte a ser decorativo |
| **A escala de layout é idêntica entre Loja e Control** | Que os painéis divirjam de novo em ritmo e densidade |
| `rg` não acha `border-radius` literal fora de `50%` e `--radius-*` | Quarto valor de raio |
| `rg` não acha `var(--accent`, `var(--radius)`, `var(--green)`, `var(--amber)`, `var(--red)`, `var(--online)` | Volta do vocabulário genérico |
| `rg -n "Camada Revy 2026"` vazio | Que a camada do fim renasça |
| Contraste AA para todo par texto/superfície, **nos dois temas** | Regressão de legibilidade |
| `#1f4d3a` nunca aparece sob fundo escuro | O bug de 1,6:1 |

### 5.2 Conferência visual

Ao fim de cada peça, no app rodando, **nos dois temas**. Telas-testemunha, escolhidas por
concentrarem o maior número de peças:

- **Loja:** login · Atendimento (fila + conversa) · Vendas → Visão · Estoque → lista · Ajustes → Integrações
- **Control:** Visão geral · Lojas → lista · Loja → detalhe · Aquisição/ROI

### 5.3 Suítes

`portal-gestao`, `revy-trafego` e `shared/brand/tests`, rodando a partir da pasta certa.

---

## 6. Não-objetivos

- **Não redesenhar tela.** Nada de mover informação, mudar fluxo ou alterar o que a tela mostra.
- **Não mexer nos 13 itens recusados** em `docs/2026-08-07-triagem-revisao-ux-loja-control.md`.
- **Não unificar os dois `app.css`** (§2). Esta rodada prepara o terreno; a unificação é outra.
- **Não mexer em espaçamento e hierarquia.** O problema de "gaps" que o dono viu nas prévias
  continua em fila separada — foi explicitamente deixado fora ao escolher "varredura de marca".
- **Não tocar em template a não ser onde a peça exige** (classe renomeada, `<small>` de KPI que
  sai, `<span>` de marca que vira SVG).
- **Não tocar em Python, n8n, Fly, migrations ou contrato HTTP.**
- **Não mexer em site e catálogo** além de reverificar: já foram convertidos em `a99d04f`.

---

## 7. Riscos

| Risco | Mitigação |
|---|---|
| Apagar 20 tokens do `:root` despinta alguma tela | Os valores são idênticos ao canônico (menos o âmbar escuro, que está errado hoje). A guarda de redeclaração roda antes; a conferência visual nos dois temas fecha |
| `.status` tem 71 regras na Loja e 64 no Control — é a peça mais arriscada | Ganha tarefa própria, e o mapa apelido→semântico é decidido no spec (§3.3), não durante a edição |
| Migrar `--green` para `--ok` em 51 usos confunde estado de registro com resultado de operação | O corte está escrito em §3.3; cada uso é classificado antes de trocar |
| Diff enorme dificulta revisão | Uma peça por commit, com a busca de guarda no corpo da mensagem |
| Loja e Control divergirem no meio do caminho | Cada tarefa varre os dois arquivos; nenhuma fecha com só um lado feito |
| Trocar raio de 8px para 3px em botão deixa a interface mais dura | Foi a decisão de 08/08, testada em mockup navegável. Se desagradar ao ver rodando, muda em um token |
| Cache de CSS servindo folha antiga | O `?v=` de `base.html` sobe a cada peça |

---

## Referências

- `docs/superpowers/specs/2026-08-08-identidade-visual-revy-design.md` — a marca e os tokens
- `docs/brand/revy-brand-kit.md` v2.0 — versão para pessoas de fora
- `docs/2026-08-07-triagem-revisao-ux-loja-control.md` — o que não volta como proposta
- `PRODUCT.md` — front-end sem build; modo escuro é dos painéis; o verde nunca é status
