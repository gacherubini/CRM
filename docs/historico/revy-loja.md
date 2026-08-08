# Histórico — Revy Loja (`portal-gestao`)

Contexto que saiu de `portal-gestao/README.md`.

## Aquisição 2026-08-08 — "Por onde as pessoas chegam"

A seção **"De onde veio o resultado"** (`/app/loja/vendas`) passou a ter dois blocos. A
tabela de campanhas responde *quanto cada campanha custou e rendeu*; o bloco novo responde
*por onde as pessoas entraram* — Anúncio, Link direto, Procurou no WhatsApp.

- **Guard próprio, e é o ponto da mudança.** A tabela de campanhas depende da API do Revy
  responder. O bloco novo tem como fonte o lead do Chatbot, então **continua renderizando
  com a fonte de mídia offline** — que é justamente quando o lojista mais quer saber por
  onde entrou gente. A `<section>` abre se **qualquer um** dos dois tiver conteúdo.
- **Agrupa por `ctwa_source_type`, não por `origem`.** `origem` está errada em 10 leads
  antigos e não será corrigida retroativamente; `source_type` é o dado cru da Meta e está
  certo. O painel nasce correto sem tocar em uma linha do banco.
- Comparação em `casefold`: o valor real em produção é `FB_Ads`, com maiúsculas.
- Dentro de "Anúncio", uma nota conta quantos leads estão **sem identificação de
  campanha**. É o que explica, na própria tela, por que a soma das campanhas não bate com
  o total de "Anúncio" — sem esse número o lojista vê a diferença e não descobre a causa.
- Lead sem `criada_em` fica **fora** do total: virar "Não identificado" incharia o balde
  com lead antigo e faria o percentual mentir.
- Permanece atrás de `pode_ver_aquisicao` (dono/gerente). Custo de integração zero: nenhum
  campo, endpoint ou contrato novo.

Sobre a venda que aparece na linha da campanha: quem decide isso é o Revy
(`docs/historico/revy-control.md` → "Atribuição de venda no ROI"). Essa linha é o **seu
relatório**, e não a atribuição da Meta — a compra só chega ao Gerenciador de Anúncios
pelo Purchase CAPI, que depende de `ctwa_clid` no lead. Os dois números podem divergir
legitimamente.

## Triagem de UX 2026-08-07 — o que mudou na interface

Decisões e itens **recusados** em `docs/2026-08-07-triagem-revisao-ux-loja-control.md`.

| Tela | Mudança |
|---|---|
| Vendas › **Resultado** (era "Visão geral") | Rodapé "Atalhos" para telas legadas removido; bloco "Pendências" só aparece quando há pendência; números do funil abrem `/app/loja/atendimento` filtrado. |
| Vendas › **Atendimento** | Coluna **"Aguardando há"** (helper `tempo_relativo()` em `app/main.py`, sobre `atualizada_em`); badge de canal migrou do `<style>` inline para `app.css` com tokens — no tema claro ele era branco sobre branco. |
| Vendas › **Agente** | Redesenhada: barra dividida "só com o agente" × "transferidos", série diária preenchida do dia 1 até hoje (`montar_visao_agente` em `app/loja/routes.py` — o Chatbot só devolve dias com conversa). Ícone próprio no menu. |
| Estoque › **Situação do estoque** (era "Visão geral") | Painéis "Cadastro › Pendências" e "Reservas e vendas recentes" removidos; texto sem jargão de API/shell. |
| Estoque › **Vitrine** (era "Ordem na vitrine") | Passou a reunir a ordenação **e** a configuração do catálogo (WhatsApp do CTA + link), que morava em Ajustes › Números de WhatsApp. O POST `/app/loja/whatsapp/catalogo` redireciona para `/app/loja/estoque/vitrine#catalogo-wa`. |
| Topbar | Páginas do shell declaram `page_title`; sem isso o `if/elif` de `base.html` não cobre `/app/loja/*` e a topbar escreve "Ajustes". |

## Piloto de flags em prod

Evolução do portal para o shell operacional **Revy Loja** (Vendas + Estoque). Com flags
desligadas a UI legada permanece idêntica. Em prod `app2037` o piloto liga shell,
entitlements, atendimento e WhatsApp por secrets; redirect legado permanece off.
Detalhe: `docs/2026-08-02-provisionamento-loja-entitlements.md`.
