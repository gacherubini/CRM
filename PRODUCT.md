# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Dono/gerente da revenda — usuário nº1.** Quem compra a Revy e cobra resultado: visão geral,
  meta, venda confirmada, origem do lead. **Em conflito de design, a leitura do dono/gerente
  ganha** (decisão do dono, 2026-08-08).
- **Vendedor — uso diário.** Vive em Atendimento, fila, simulação e venda no Revy Loja.
  Trabalha na mesa da loja: **desktop/notebook é o aparelho principal**; o celular precisa
  funcionar, mas não dita a decisão (confirmado 2026-08-08).
- **Admin Revy e gestor de tráfego.** Operam o Revy Control: lojas, pessoas e cargos, módulos
  contratados, integrações técnicas e aquisição. O gestor pode ser da equipe Revy, independente
  ou de agência, e existe como responsável ou colaborador de uma loja.
- **Cliente final da loja.** Nunca é usuário de painel. Encontra a operação no WhatsApp e na
  Vitrine pública, em experiência white-label — não precisa ver o nome Revy.

Vocabulário canônico de todos esses papéis: [`CONTEXT.md`](CONTEXT.md).

## Product Purpose

Sistema operacional da revenda de veículos. A Revy atende o cliente no WhatsApp, simula
financiamento nos bancos da própria loja, organiza estoque e vitrine e entrega o vendedor na
hora certa — com o dono enxergando venda, meta e origem.

Sucesso: a loja não perde lead no WhatsApp nem tempo no portal do banco, e o dono confia no
número que vê no painel.

## Positioning

O mecanismo que um produto vizinho não copiaria honestamente:

- **Simulação nos bancos da própria loja.** O Motor executa os portais bancários reais
  (Santander, Fontecred, Bradesco, Pan) com as credenciais da loja. Não é marketplace de
  crédito, não é taxa de tabela, e condição definitiva e aprovação continuam sendo do banco.
- **WhatsApp white-label com handoff.** O cliente fala com o "assistente da {Loja}"; o bot cede
  ao humano e o vendedor assume vendo a conversa inteira.
- **A venda carrega a origem.** Venda confirmada no Revy Loja projeta evento no Revy Control,
  que devolve conversão à Meta (Pixel/CAPI) — atendimento, crédito e aquisição na mesma operação.

Não somos: CRM genérico, banco, robô engraçadinho, "aprovação mágica de crédito".

## Operating Context

- **WhatsApp é o lugar de trabalho real** do cliente e do vendedor; Evolution e n8n orquestram,
  o Chatbot é dono da conversa.
- **Estoque nasce por foto** em um grupo de WhatsApp da loja — o vendedor cadastra veículo pelo
  celular, não por formulário longo.
- **Portais bancários são lentos e falham.** Captcha, análise demorada e timeout são rotina; o
  produto tem de dizer o erro com clareza em vez de esconder.
- **Duas aplicações separadas por autoridade:** Revy Control (configuração estrutural: lojas,
  cargos, módulos, integrações) e Revy Loja (operação da equipe). A separação é de permissão,
  não de conveniência de menu.
- **Multi-loja com isolamento real.** Cada loja tem status próprio (rascunho, em configuração,
  pronta, ativa, suspensa, encerrada). Suspensão é gate de backend, não visibilidade de menu.
- **Um piloto em produção** (`app2037`), com flags e entitlements ligados por ops.

## Capabilities and Constraints

- **Só dois módulos visíveis no Revy Loja: Vendas e Estoque.** Chatbot, Simulação Multibanco e
  Seller AI são capacidades embutidas em Vendas — nunca aplicação ou menu principal separado.
- **Ownership fixo por serviço:** Estoque API é fonte única de veículos; Chatbot é dono de
  canais, leads, conversas e mensagens; Revy Loja é dono de vendas e metas; Motor é dono das
  credenciais e da execução bancária; Control é dono de lojas, acessos globais, cargos, módulos
  e integrações. Integração somente por HTTP/evento versionado — nunca import entre produtos.
- **Front-end sem build.** Todas as telas são Jinja renderizado no servidor sobre FastAPI, com
  CSS próprio (`app/static/css/app.css`) mais tokens copiados de `shared/brand/revy-tokens.css`.
  Não existe bundler, framework JS nem dependência externa carregada em runtime de página —
  qualquer proposta que exija React, Vite ou Tailwind está fora do que este produto pode receber.
- **Modo escuro é dos painéis.** Revy Loja e Revy Control têm os dois temas; site e vitrine
  pública são sempre claros (foto de veículo em fundo escuro não é terreno a descobrir na frente
  do cliente).
- **O resultado da simulação ainda chega ao cliente por humano** — o bot não devolve parcela.
- **Nunca prometer aprovação de crédito**, em nenhuma superfície. Empty state não inventa número.
- **13 propostas de UX foram recusadas pelo dono em 2026-08-07**
  ([`docs/2026-08-07-triagem-revisao-ux-loja-control.md`](docs/2026-08-07-triagem-revisao-ux-loja-control.md))
  e não devem voltar como ideia nova.
- **Abertos, não inventar:** Seller AI está adiado; os pacotes comerciais do brand kit são
  sugestão, não preço confirmado; domínio e @ ainda não registrados.

## Brand Commitments

Fonte vinculante: [`docs/brand/revy-brand-kit.md`](docs/brand/revy-brand-kit.md) v2.0.

- **Nome Revy** (nunca "Revvy"). Tagline oficial: *A revenda no ritmo certo.*
- **Tipografia decidida:** Hanken Grotesk na interface (tudo que é para trabalhar); Newsreader 300
  só onde a marca fala (frase do login, manchete, criativo); mono para placa, telefone e ID.
  Preço de catálogo é Hanken com `tabular-nums`, nunca serifa.
- **Base preto e branco.** O verde é acento de marca e **nunca cor de status**: `#1f4d3a` no
  claro, `#7fbfa3` no escuro (a troca de passo é obrigatória por contraste). Cor nunca comunica
  sozinha — sempre acompanha forma e palavra.
- **A marca é preta, sempre.** Símbolo é o monograma R em geometria vetorial; nada de verde,
  distorção, sombra 3D ou wordmark redigitado em outra fonte.
- **Proibido:** laranja neon, gradiente "IA", glow colorido em card, azul de fintech genérica,
  e usar o verde de marca como sinal de sucesso.
- **Tokens canônicos** em `shared/brand/revy-tokens.css`; as cópias nos quatro front-ends são
  sincronizadas, não editadas à mão.
- **Voz:** co-piloto da loja — PT-BR curto, status explícito, pouco emoji, zero hype de IA.
- **White-label:** o cliente final não precisa ver Revy; `Powered by Revy` na vitrine é toggle
  por loja.
- **Legado a ignorar:** `docs/brand/index.html`, `preview.html`, `portal-mock.html` e
  `instagram-logo.html` mostram a paleta e a fonte da v1.0 — não são referência.

## Evidence on Hand

- **Uma loja real em operação hoje** (piloto em `app2037`), com a suíte quase em produção. É um
  cliente funcionando — não existe base, volume agregado nem "várias lojas".
- **Autorização de nome, logo ou depoimento dessa loja: não confirmada.** Tratar como não
  autorizada até o dono liberar: nenhuma peça pode nomear a loja nem citar o resultado dela.
- **Nunca fabricar:** depoimento, logotipo de cliente, número de lojas, benchmark, tempo médio,
  taxa de conversão, preço público, ou parceria endossada com banco (logo de banco não implica
  parceria).
- **Assets e conteúdo reais disponíveis:** marca em `docs/brand/assets/` e `site/assets/`;
  tutoriais em PDF (`docs/tutorial-*`, `docs/setup-grupo-whatsapp-estoque.pdf`); one-pager
  comercial em `docs/README-COMERCIAL.md`; e o próprio produto, screenshotável nos quatro
  front-ends.

## Product Principles

1. **Honestidade vence conversão.** Nada de "aprovado", nada de dashboard bonito sem venda real,
   nenhum número que o dado não sustente.
2. **Em conflito, o dono/gerente ganha.** Leitura de resultado tem prioridade sobre densidade
   operacional; telas de operação servem o vendedor sem virar terminal de trading.
3. **No cliente final, a marca é da loja.** Revy aparece no B2B — contrato, painel, marketing.
4. **Fronteira por contrato.** Cada produto é dono do seu dado e integra por HTTP/evento
   versionado; nenhuma tela pode assumir dado de outro serviço como se fosse local.
5. **Decisão registrada não volta como proposta.** O que o dono recusou está documentado e
   permanece recusado.

## Accessibility & Inclusion

- Nenhum padrão formal (nível WCAG) foi estabelecido pelo dono — **decisão aberta**, não um "não".
- Compromisso já vinculante: **cor nunca comunica sozinha** — estado em lista é ponto na cor do
  estado *mais* a palavra escrita; o acento verde muda de passo entre temas porque `#1f4d3a`
  sobre `#0a0a0a` dá 1,6:1.
- O público não é técnico: dono de revenda e vendedor, sob pressão comercial, em desktop de loja.
  Rótulo curto e status explícito valem mais que affordance sutil.
