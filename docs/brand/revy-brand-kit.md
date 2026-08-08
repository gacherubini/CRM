# Revy — Brand Kit

**Versão:** 2.0 · **Grafia oficial:** Revy (não Revvy)  
**Atualizado:** 2026-08-08  
**Uso:** identidade visual, tom de voz, nomenclatura de produto e copy padrão da suíte.

> **O que mudou na v2.0** — a seção 4 (identidade visual) foi refeita. A v1.0 mandava usar
> **Inter**, listava uma paleta que não estava em produção e citava uma cor "Signal" que a
> própria tabela não definia. O produto usa **Hanken Grotesk** desde julho. Também entrou o
> acento verde `#1f4d3a` e a marca passou a ter geometria vetorial de verdade.
> Nome, tagline, personalidade, tom de voz, templates de WhatsApp, nomenclatura e compliance
> **não mudaram**. Decisões e escopo técnico: `docs/superpowers/specs/2026-08-08-identidade-visual-revy-design.md`.

---

## 1. Marca em uma página

| | |
|---|---|
| **Nome** | Revy |
| **Pronúncia** | *RÉ-vi* (como “rev” + “i”) |
| **Origem** | *Revenda* + *velocity* — operação da loja em ritmo comercial |
| **Categoria** | Sistema operacional da revenda (WhatsApp, simulação, estoque, vitrine, painel) |
| **Promessa** | A loja se move mais rápido, sem perder o controle |
| **Público** | Dono/gerente de revenda (compra) · vendedor (uso diário) · cliente final no WhatsApp (experiência white-label) |
| **Não somos** | CRM genérico · robô engraçadinho · banco · “aprovação mágica de crédito” |

### Tagline oficial
**A revenda no ritmo certo.**

### Alternativas aprovadas
- Do WhatsApp à parcela, sem freio.
- Simula. Organiza. Fecha.
- Operação da loja, em tempo real.

### Elevator pitch (15s)
> Revy é o sistema da revenda: atende no WhatsApp, simula financiamento nos bancos da loja, organiza estoque e vitrine, e entrega o vendedor na hora certa — com o dono enxergando venda, meta e origem.

### Manifesto (1 parágrafo)
> Revy existe pra loja não perder lead no WhatsApp nem tempo no portal do banco. Atende, simula de verdade, organiza estoque e entrega o vendedor na hora certa — com o dono enxergando venda, meta e origem. Rápido no cliente. Sério no crédito. No controle da revenda.

---

## 2. Personalidade

### Persona
**Co-piloto da loja** — ágil, objetivo, confiável. Não é mascote infantil nem consultor bancário frio.

| Traço | Comportamento |
|---|---|
| **Rápido** | Mensagens curtas; status explícito |
| **Preciso** | Confirma antes de gravar ou simular |
| **Honesto** | Não inventa taxa; erro de banco é dito com clareza |
| **Parceiro do time** | Cede ao humano (handoff / auto-pausa) |
| **Sem teatro** | Pouco emoji; zero hype de “IA revolucionária” |

### É Revy / Não é Revy

| É Revy | Não é Revy |
|---|---|
| “Confirma pra eu seguir?” | Pressão agressiva de fechamento |
| “3 opções dos bancos da loja” | “Você já está aprovado” |
| “Time humano assumiu” | Bot insistindo após handoff |
| Métricas e status no painel | Dashboard enfeitado sem venda real |
| Multi-produto plugável | Monólito mágico |

### Arquétipos
- Primário: **Sage** (clareza, competência)
- Secundário: **Everyman** (acessível pro vendedor e pro cliente BR)

---

## 3. Tom de voz

### Princípios de copy
1. Português brasileiro claro — sem corporativês gringo.
2. Frases curtas. Uma ideia por bolha no WhatsApp.
3. Números e resumos em destaque; confirmação antes de ação irreversível.
4. Nunca prometa aprovação de crédito.
5. No B2B (dono): mais “sistema e operação”. No B2C (cliente): mais “assistente da loja”.

### Vocabulário preferido
simular · condições · parcela · entrada · prazo · estoque · vitrine · confirmar · time da loja · handoff · origem · meta · venda

### Vocabulário a evitar
aprovado com certeza · melhor do Brasil · IA revolucionária · pipeline (no cliente final) · lead scoring (no WA) · jargão de CRM gringo

### Templates de mensagem (WhatsApp)

**Saudação (white-label da loja)**
> Oi! Sou o assistente da *{Loja}*. Posso simular o financiamento ou te ajudar com o estoque. O que você prefere?

**Pedido de dado**
> Pra simular com precisão, preciso do CPF e da data de nascimento. Pode enviar?

**Confirmação antes de simular**
> Resumo: {veiculo} · R$ {valor} · entrada R$ {entrada} · {prazo}x.  
> Confirma pra eu buscar as condições?

**Aguardando motor**
> Buscando condições nos bancos da loja… Isso pode levar alguns instantes.

**Resultado**
> Pronto. {n} opções encontradas. Quer que eu chame um vendedor da loja?

**Handoff**
> Vou te passar pro time agora. Eles já veem o que conversamos.

**Erro de banco / timeout**
> Não consegui retornar com esse banco agora. Posso tentar de novo ou chamar alguém da loja.

**Cadastro de veículo (grupo do estoque)**
> Veículo montado:  
> {marca} {modelo} {ano} · R$ {valor} · placa {placa}  
> Confirma o cadastro?

**Imagem fora do grupo do estoque**
> Não enviar resposta. A mensagem é ignorada silenciosamente.

### Tom no Painel (B2B)
- Labels curtos: *Em andamento*, *Concluída*, *Falhou*, *Bot pausado*
- Empty states honestos: *Nenhuma venda no período — não inventamos números.*
- CTAs: *Nova simulação*, *Confirmar venda*, *Publicar na vitrine*

### Assinatura / bio
- **WhatsApp (perfil da loja):** `{Loja} · atendimento`  
- **WhatsApp (se brand Revy visível):** `{Loja} · Revy`  
- **LinkedIn / site B2B:** `Revy — a revenda no ritmo certo`  
- **Email assunto pitch:** `Revy: WhatsApp + simulação + estoque na mesma operação`

---

## 4. Identidade visual

### 4.1 Paleta

Base **preto e branco**. O verde é acento de marca — nunca cor de status. Status tem família
própria. Regra que vale em toda a suíte: **cor nunca vem sozinha**, sempre acompanha forma
(ponto, ícone) e palavra escrita.

#### Preto e neutros

| Token | Claro | Escuro | Uso |
|---|---|---|---|
| `--paper` | `#f9f9f9` | `#0a0a0a` | Fundo da página |
| `--surface` | `#ffffff` | `#111111` | Painel, card, cabeçalho da vitrine |
| `--surface-raised` | `#f4f2f1` | `#161616` | Sidebar |
| `--surface-soft` | `#efeceb` | `#1a1a1a` | Hover |
| `--ink` | `#1b1b1b` | `#f5f5f5` | Texto principal — **o preto da marca** |
| `--ink-soft` | `#57514f` | `#a3a3a3` | Texto secundário |
| `--ink-muted` | `#6b625f` | `#949494` | Texto apagado |
| `--line` | `#ded8d9` | `#2a2a2a` | Borda, separador |
| `--line-strong` | `#cdc6c4` | `#3a3a3a` | Borda de controle |

> **O modo escuro é dos painéis.** Revy Loja e Revy Control têm os dois temas. **O site e a
> vitrine pública são sempre claros** — foto de veículo sobre fundo escuro não é terreno para
> descobrir na cara do cliente. Para criativo: peça padrão em fundo claro. Fundo escuro é
> escolha de arte de uma peça específica, com o verde 300 e a marca reversa — não um tema do produto.

#### Verde de marca — escala completa

Criativo precisa de mais que um tom: fundo, texto sobre fundo e realce.

| Passo | Hex | Uso |
|---|---|---|
| 900 | `#0f2b20` | Fundo de anúncio |
| **700** | **`#1f4d3a`** | **Acento no modo claro** |
| 500 | `#2f7355` | Hover, série de gráfico |
| **300** | **`#7fbfa3`** | **Acento no modo escuro** |
| 100 | `#dfeee7` | Tint, faixa |

O acento **muda de passo entre os temas, e isso não é opcional**: `#1f4d3a` sobre fundo
`#0a0a0a` dá contraste de 1,6:1 — ilegível.

#### Status

| Estado | Claro | Escuro |
|---|---|---|
| Aguardando | `#8a6d1d` | `#d9b04a` |
| Em atendimento | `#57514f` | `#a3a3a3` |
| Proposta | `#1f4d3a` | `#7fbfa3` |
| Ganho / sucesso | `#0d7a4f` | `#3ecf8e` |
| Perdido | `#6b625f` | `#949494` |
| Falha | `#b42318` | `#f97066` |
| WhatsApp (canal, não marca) | `#25d366` | `#25d366` |

**Proibido:** laranja neon, gradiente "IA", glow colorido em card, azul de fintech genérica,
e usar o verde de marca como se fosse sinal de sucesso.

#### Onde ficam os tokens

Fonte única: `shared/brand/revy-tokens.css`, copiado para os quatro front-ends.
Não edite as cópias.

### 4.2 Tipografia

| Papel | Família | Onde |
|---|---|---|
| **Interface** | [Hanken Grotesk](https://fonts.google.com/specimen/Hanken+Grotesk) 400–700 | Painel, catálogo, corpo do site — tudo que é para trabalhar |
| **Frase de marca** | [Newsreader](https://fonts.google.com/specimen/Newsreader) 300 | Frase do login, manchete do site, criativo |
| **Dados** | ui-monospace / Consolas | Placa, telefone, ID |

A serifa entra **só onde a marca fala**. Dentro do painel ela atrapalha quem está trabalhando,
e no preço do catálogo ela prejudica leitura rápida — preço é Hanken com
`font-variant-numeric: tabular-nums`.

### 4.3 Logo

#### O símbolo

Monograma **R** vazado em quadrado de canto arredondado. Desenhado em **geometria vetorial**
(`<path>`), sem depender de nenhuma fonte instalada.

> **A v1.0 deste kit descrevia um símbolo que nunca foi desenhado** ("corte em diagonal / risca
> de velocidade") e os arquivos entregues eram `<text font-family="Inter…">` — letra viva, que
> muda de forma conforme a máquina e não tem contorno para levar a impresso ou a Canva.
> A v2.0 substitui todos eles.

```svg
<rect width="40" height="40" rx="9" fill="#1b1b1b"/>
<path d="M15.5 30V13h6.8a4.3 4.3 0 0 1 0 8.6h-6.8" fill="none" stroke="#fff"
      stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M21 21.6 27 30" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"/>
```

#### A marca é preta. Sempre.

Nada de verde no símbolo. Em fundo claro, quadrado `#1b1b1b` com R branco. Em fundo escuro,
quadrado `#000000` com R claro **e um fio de 1px `rgba(255,255,255,.16)`**, para não desaparecer
sobre a sidebar `#161616`.

#### Assinatura

**Nome + descritor**: "Revy" com "GESTÃO DE REVENDA" embaixo, em caixa-alta espaçada.

Dois usos que não competem:
- **Símbolo sozinho** — favicon, avatar de WhatsApp, sidebar do painel. Onde só cabe um quadrado.
- **Assinatura completa** — login, cabeçalho do catálogo, rodapé de criativo. Onde há largura
  para dizer o que a empresa faz a quem nunca ouviu falar.

#### Arquivos

| Arquivo | Uso |
|---|---|
| `assets/revy-mark.svg` | Símbolo, fundo claro |
| `assets/revy-mark-reverse.svg` | Símbolo, fundo escuro |
| `assets/revy-wordmark.svg` | "Revy" em contorno |
| `assets/revy-signature.svg` | Wordmark + descritor |
| `assets/revy-signature-reverse.svg` | Idem, fundo escuro |
| `assets/favicon.svg` · `favicon-32.png` · `apple-touch-icon-180.png` | Derivados do símbolo |

#### Clear space
Mínimo = altura do "R" do wordmark em todos os lados.

#### Tamanhos mínimos
| Contexto | Mínimo |
|---|---|
| Assinatura digital | 96 px de largura |
| Símbolo isolado | 24 × 24 px |
| Favicon | 32 × 32 |
| Avatar WhatsApp | 192 × 192 (símbolo centralizado, ~60% do quadro) |

#### Usos proibidos
- Pintar o símbolo de verde, ou de qualquer cor que não seja o preto e sua reversa
- Distorcer, rotacionar "por estilo", aplicar sombra 3D
- Contornar com stroke aleatório
- Preto sobre preto ou branco sobre branco sem o fio de contraste
- Recompor o wordmark digitando "Revy" numa fonte qualquer — use o arquivo
- Animar com bounce

### 4.4 Iconografia e UI
- Ícones: linha 2px, cantos arredondados (estilo Lucide / Phosphor), 17px na navegação
- Raio: **3px** em controle (botão, campo, chip), **8px** em item de menu, **12px** em painel e card
- Botão primário: preto sólido, texto na cor do papel, caixa-baixa. Sem caixa-alta espaçada.
- Sombra: quase nenhuma no claro (`0 1px 2px rgba(27,20,20,.05)`), nenhuma no escuro —
  lá a separação vem da superfície, não da sombra
- Estado em lista: ponto de 7px na cor do estado + palavra. Estados terminais (Ganho, Perdido)
  não recebem ponto — o destaque é de quem exige ação
- KPI: um rótulo curto e o número. Sem linha de explicação embaixo
- Densidade do painel: confortável (revenda, não terminal de trading)

### 4.5 Fotografia e arte
- Preferir: oficina limpa, vitrine, celular na mão do vendedor, detalhe de painel — **pessoas reais de loja BR**
- Evitar: stock de aperto de mão em escritório de vidro, robô 3D, “IA roxa com cérebro neon”
- Overlay de marketing: gradiente `--ink`→transparente; CTA em preto sólido, ou no verde 700
  quando o fundo for foto clara

---

## 5. Nomenclatura de produto

### Nome mestre
**Revy**

### Módulos (nome de produto)

| Código interno | Nome de produto | Uma linha |
|---|---|---|
| `chatbot-api` + n8n/Evolution | **Revy Atende** | Conversa no WhatsApp |
| `motor-simulacao` | **Revy Simula** | Condições multi-banco |
| `estoque-api` | **Revy Estoque** | Veículos, placa, fotos |
| `catalogo-publico` | **Revy Vitrine** | Catálogo público + CTA |
| `portal-gestao` | **Revy Painel** | Vendedor, dono, metas, tráfego |
| Meta Pixel / CAPI | **Revy Tráfego** | Conversões e ads |

### Pacotes comerciais (sugestão)

| Pacote | Inclui | Pitch |
|---|---|---|
| **Revy Atende** | Chat + estoque lite + cadastro WA | Atendimento e cadastro no WhatsApp |
| **Revy Financia** | Atende + Simula | Simulação multi-banco no chat |
| **Revy Loja** | Estoque + Vitrine | Operação de estoque e site |
| **Revy Completo** | Tudo + Painel + Tráfego | Operação ponta a ponta |

### White-label
- Cliente final **não precisa** ver o nome Revy.
- Padrão recomendado: *“assistente da {Loja}”* no WhatsApp; **Revy** só no contrato, painel e marketing B2B.
- Rodapé opcional da Vitrine: `Powered by Revy` (toggle por loja).

### Domínios e handles (reserva sugerida)
- `revy.com.br` / `userevy.com` / `getrevy.app`
- `@userevy` (Instagram/X) · `revy` no GitHub org quando houver

---

## 6. Aplicações

### WhatsApp
| Elemento | Spec |
|---|---|
| Nome do perfil | `{Loja}` ou `{Loja} · Revy` |
| Foto | Símbolo em fundo preto (quadrado, símbolo central ~60%) |
| Mensagens | Tom da seção 3; máx. ~4 linhas por bolha quando possível |
| Listas / botões | Preferir opções claras a texto longo |

### Revy Painel
- Sidebar em `--surface-raised`, distinta do papel. Item ativo com fundo `--brand-tint`,
  borda `--brand-line`, barra de 3px à esquerda e ícone no acento
- KPI: rótulo curto em `--ink-muted`, número grande em Hanken com `tabular-nums`
- Tabela: mono para placa, telefone e ID. Linha de ~34px
- Estado: ponto colorido + palavra

### Revy Vitrine
- Hero limpo, **preço legível em Hanken com `tabular-nums`** — nunca serifa
- Card de veículo: superfície própria, foto 16:10, preço em destaque, dados em pastilhas
- CTA “Falar no WhatsApp” em preto sólido; o verde `#25d366` só aparece como cor de canal
- Mobile-first; foto do veículo em primeiro plano

### Pitch deck / one-pager (estrutura)
1. Problema: lead some no WhatsApp; simulação no portal do banco é lenta  
2. Revy: Atende → Simula → Estoque/Vitrine → Painel  
3. Prova: multi-banco, handoff, venda com CAPI  
4. Pacotes e próximo passo  

### E-mail de cold (dono de loja)
```
Assunto: Revy — simular financiamento sem sair do WhatsApp

Oi {nome},

Hoje o lead chega no WhatsApp e a simulação mora no portal do banco.
A Revy junta os dois: o assistente da loja coleta os dados, busca condições
e avisa o vendedor na hora — com estoque e painel se você quiser a suíte.

Se fizer sentido, te mostro em 15 min com a operação de vocês em mente.

Abs,
{seu nome}
```

---

## 7. Legal e compliance de comunicação

- Não usar logotipos de bancos como se fossem parceria endossada sem autorização.
- Não afirmar “crédito aprovado” — só “condições / simulação / opções”.
- LGPD: consentimento e finalidade claros antes de dados sensíveis.
- Token CAPI, senhas de portal de banco e chaves **nunca** em material de marketing nem screenshot sem máscara.

---

## 8. Checklist de entrega de marca

- [x] Nome e grafia fixados: **Revy**
- [x] Tagline oficial
- [x] Personalidade e tom de voz + templates WA
- [x] Nomenclatura de módulos e pacotes
- [x] Paleta, escala do verde e família de status (v2.0)
- [x] Tipografia decidida: Hanken na interface, Newsreader na marca (v2.0)
- [x] Símbolo desenhado em geometria vetorial (v2.0)
- [ ] **Símbolo exportado** para `assets/` — os SVGs atuais ainda são `<text>` em Inter
- [ ] **Wordmark convertido em contorno** — precisa de FontForge/Inkscape/Figma; é o único item
      que não fecha só com código
- [ ] Favicon SVG + PNG 32/180
- [ ] `shared/brand/revy-tokens.css` criado e sincronizado nos quatro front-ends
- [ ] Tokens aplicados em `site`, `catalogo-publico`, `portal-gestao` e `revy-trafego`
- [ ] `docs/brand/preview.html` e `index.html` regerados (hoje mostram a paleta da v1.0)
- [ ] Domínio e @ registrados

---

## 9. Arquivos deste kit

```
docs/brand/
  revy-brand-kit.md          ← este documento (a fonte)
  assets/                    ← marca em contorno vetorial
  index.html                 ← LEGADO v1.0: paleta e fonte antigas
  preview.html               ← LEGADO v1.0: tokens antigos
  portal-mock.html           ← LEGADO v1.0
  instagram-logo.html        ← LEGADO v1.0
  hero-animacao-prompts.md
shared/brand/
  revy-tokens.css            ← tokens canônicos, copiados para os quatro front-ends
  sync-tokens.py
```

**Os quatro HTML marcados como legado mostram a paleta e a fonte da v1.0.** Não use como
referência até serem regerados; este documento é a fonte.

### Referência de estrutura (Attio → Revy)

| Padrão Attio | Tradução Revy |
|---|---|
| Headline conceitual (“agentic revenue”) | “Bem-vindo à revenda em ritmo.” |
| Product stage (UI cards no hero) | WhatsApp Atende + card Simula multi-banco |
| “Team amplified / agents dig” | Atende + handoff; simulação real; estoque/vitrine |
| Pipeline kanban | Funil loja: lead → simulou → vendedor → venda |
| Universal context | Contexto da loja (contratos entre módulos) |
| Agentic revenue CTA | “A revenda no ritmo certo roda na Revy.” |

Personalidade **não** copia tom gringo de GTM SaaS: português BR, sem prometer aprovação de crédito, white-label no WhatsApp.

---

*Revy — a revenda no ritmo certo.*
