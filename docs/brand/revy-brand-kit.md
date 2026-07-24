# Revy — Brand Kit

**Versão:** 1.0 · **Grafia oficial:** Revy (não Revvy)  
**Atualizado:** 2026-07-14  
**Uso:** identidade visual, tom de voz, nomenclatura de produto e copy padrão da suíte.

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

### 4.1 Paleta (v1.1 — monocromática, sem laranja “IA”)

Direção: preto / branco / cinza. Status só em verde/âmbar/vermelho neutros.

| Token | Hex | Uso |
|---|---|---|
| Ink / ação | `#0A0A0A` | Texto, botões primários, wordmark no claro |
| Paper | `#FFFFFF` | Fundo modo claro (padrão do portal) |
| Soft | `#FAFAFA` / `#F5F5F5` | Sidebar, KPI, hover |
| Line | `#E8E8E8` | Bordas finas |
| Muted | `#6B6B6B` | Texto secundário |
| Ok | `#0D7A4F` | Sucesso |
| Warn | `#8A6D1D` | Atenção |
| Danger | `#B42318` | Erro |

**Modo escuro:** fundo `#0A0A0A`, superfície `#111`, texto `#F5F5F5`, bordas `#2A2A2A`.

**Proibido:** laranja neon, gradiente “IA”, glow colorido em cards.

#### CSS tokens

```css
:root, [data-theme="light"] {
  --ink: #0a0a0a;
  --paper: #ffffff;
  --soft: #f5f5f5;
  --line: #e8e8e8;
  --muted: #6b6b6b;
  --ok: #0d7a4f;
  --warn: #8a6d1d;
  --danger: #b42318;
}
```

### 4.2 Tipografia

| Papel | Família | Uso |
|---|---|---|
| **UI + marketing** | [Inter](https://fonts.google.com/specimen/Inter) 400–700 | Tudo (wordmark, portal, landing) |
| **Mono (opcional)** | ui-monospace / IBM Plex Mono | Placa, IDs |

Logo = **wordmark “Revy”** em Inter 600. Mark “R” só quando precisar de favicon/avatar.

### 4.3 Logo

#### Arquivos
| Arquivo | Uso |
|---|---|
| `assets/revy-logo-full-dark.svg` | Wordmark + marca em fundo claro |
| `assets/revy-logo-full-light.svg` | Wordmark + marca em fundo escuro |
| `assets/revy-mark.svg` | Símbolo só (favicon, avatar, app icon base) |
| `assets/revy-wordmark.svg` | Só texto “Revy” |
| `preview.html` | Painel visual do kit no browser |

#### Conceito da marca (símbolo)
Monograma **R** estilizado com um **corte em diagonal / risca de velocidade** — sugere movimento da revenda sem desenhar moto/carro (escopo pode ser multi-veículo).

#### Clear space
Mínimo = altura do “R” do wordmark em todos os lados.

#### Tamanhos mínimos
| Contexto | Mínimo |
|---|---|
| Wordmark digital | 88 px de largura |
| Mark isolado | 24 × 24 px |
| Favicon | 32 × 32 (mark simplificado) |
| Avatar WhatsApp | 192 × 192 (mark centralizado em Ink ou Signal) |

#### Usos proibidos
- Distorcer, rotacionar “por estilo”, adicionar sombra 3D barata
- Contornar o logo com stroke aleatório
- Colocar Signal sobre Signal ou Paper sobre Paper sem contraste
- Trocar Signal por verde-banco ou azul “fintech genérico”
- Animar o logo com bounce exagerado

#### Versões de cor do logo
1. **Primary:** mark Signal + wordmark Ink (fundo Paper)
2. **Inverse:** mark Signal + wordmark Paper (fundo Ink)
3. **Mono ink:** tudo Ink (documentos B&W)
4. **Mono paper:** tudo Paper (sobre foto escura)
5. **Signal only mark:** favicon / badge

### 4.4 Iconografia e UI
- Ícones: linha 1.5–2 px, cantos levemente arredondados (estilo Lucide / Phosphor)
- Radius padrão: **12px** cards, **8px** inputs/buttons
- Sombra: quase nenhuma; preferir borda Mist ou elevação sutil `0 8px 24px rgba(11,15,20,0.08)`
- Densidade do painel: confortável (revenda, não terminal de trading)

### 4.5 Fotografia e arte
- Preferir: oficina limpa, vitrine, celular na mão do vendedor, detalhe de painel — **pessoas reais de loja BR**
- Evitar: stock de aperto de mão em escritório de vidro, robô 3D, “IA roxa com cérebro neon”
- Overlay de marketing: gradiente Ink→transparente + CTA Signal

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
| Foto | Mark em fundo Ink (quadrado, mark central ~60%) |
| Mensagens | Tom da seção 3; máx. ~4 linhas por bolha quando possível |
| Listas / botões | Preferir opções claras a texto longo |

### Revy Painel
- Sidebar Ink ou Paper com item ativo em Signal (barra ou texto)
- KPI cards: número em Display/Space Grotesk, label Muted
- Tabela: mono para placa e valores

### Revy Vitrine
- Hero limpo, preço legível, CTA Signal “Falar no WhatsApp”
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
- [x] Paleta + tokens CSS
- [x] Tipografia
- [x] Logos SVG + preview HTML
- [x] Nomenclatura de módulos e pacotes
- [ ] Favicon PNG 32/180 (exportar do mark quando for pro ar)
- [ ] Domínio e @ registrados
- [ ] Aplicar tokens no `portal-gestao` / `catalogo-publico` (quando priorizar UI)

---

## 9. Arquivos deste kit

```
docs/brand/
  index.html                 ← landing (estrutura inspirada em Attio + personalidade Revy)
  revy-brand-kit.md          ← este documento
  preview.html               ← painel visual de tokens/UI
  assets/
    revy-mark.svg
    revy-wordmark.svg
    revy-logo-full-dark.svg  ← para fundo claro
    revy-logo-full-light.svg ← para fundo escuro
```

Abrir no browser:
```text
docs/brand/index.html     → marketing / personalidade
docs/brand/preview.html   → tokens e UI kit
```

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
