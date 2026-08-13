# Análise de mercado e fit — Revy/HEVY

_Atualizado em 2026-08-09._ Documento **comercial/estratégico** (não é doc técnico).
Responde: as revendas de carro e moto no Brasil têm dores reais que o Revy resolve, e
o produto tem chance de vender contra o SaaS que elas já usam?

Evidência de origem (com URLs por afirmação):
- [`pesquisa-dores-concessionarias.md`](pesquisa-dores-concessionarias.md) — dores por categoria e por porte.
- [`pesquisa-saas-incumbentes.md`](pesquisa-saas-incumbentes.md) — DMS/CRM/financiamento que o mercado já roda e onde ficam as lacunas.

Complementa a [visão comercial](../README-COMERCIAL.md) e o vocabulário de domínio (`CONTEXT.md`).

---

## TL;DR — veredito

**Sim, há chance real de vender — mas não pelo motivo mais óbvio, e não em todos os portes.**
A intuição "as concessionárias já são avançadas, já têm SaaS pronto" está **certa no topo e
errada na base** — e a base é justamente quem o Revy mira (revendas de seminovos, moto-first,
pequenas a médias).

- O diferencial que **ninguém mais entrega** é a **atribuição de tráfego pago ponta-a-ponta**
  (anúncio Meta → Click-to-WhatsApp → venda → ROI). É o fosso.
- A **simulação de financiamento multibancos NÃO é inédita** (Credere, AutoConf, Boom já fazem);
  vira paridade, não manchete.
- **Beachhead recomendado:** média revenda de moto/seminovos (30–200 unidades) que já roda
  tráfego pago e financia venda. É onde os três diferenciais pagam juntos.

## 1. O mercado se parte em dois mundos

| Mundo | Quem | Sistema que já roda | Incumbência |
|---|---|---|---|
| **Topo** | ~8.400 concessionárias de **marca** (Fenabrave) | DMS pesado homologado por montadora — Linx (2.900+ clientes), Dealernet, Sisand, NBS | **Alta.** Trocar é caro e homologado; lucro real migrou ao pós-venda (margem ~0,9%) |
| **Base** | **~48–50 mil revendas** multimarca de usados + lojas de moto (Fenauto) | Sistema leve de loja (AutoConf, Boom, Revenda Mais) — ou planilha + WhatsApp solto | **Baixa.** Barreira de troca baixa; setor "dos menos desenvolvidos digitalmente" |

O Revy compete **no mundo de baixo, moto-first** (o formulário da landing pergunta "motos em
estoque: até 30 / 30–80 / 80–200 / +200"). É onde a saturação de SaaS quase não existe. As
~48 mil revendas de usados movimentam >R$1 trilhão/ano e são o segmento mais carente de automação.

## 2. Dores reais × o que o Revy faz (matriz de fit)

| Dor (com evidência) | Revy resolve? | Incumbente já resolve? | Veredito |
|---|---|---|---|
| **Resposta imediata 24/7 + follow-up.** 56% dos leads chegam fora do horário (McKinsey); responder em 5 min = 21x mais qualificação; lojas abandonam após 2–3 toques quando o ideal é 7–10 | **Sim** — bot WhatsApp white-label 24/7 + handoff na hora certa | Parcial — WhatsApp básico existe; AutoForce AutoPilot já tem SDR de IA | **Forte, mas contestado.** Edge: autônomo + white-label + amarrado ao financiamento |
| **Financiamento multibancos.** Simular banco a banco leva 30–40 min manuais; se 1 banco recusa, a venda é dada como perdida | **Sim** — Motor RPA faz fan-out real (Santander, Bradesco, PAN, Fontecred) | **Sim:** Credere (250+ redes), AutoConf e Boom já fazem fan-out multibanco | **Paridade, não vantagem.** Edge estreito: RPA **próprio, sem comissão de agregador**, cobrindo bancos fora das APIs (Fontecred) |
| **Organização de leads + atribuição da venda** (CPV, não só CPL). Contatos somem entre vários WhatsApps; ninguém sabe qual anúncio gerou qual venda | **Sim** — CRM + CTWA + Pixel/CAPI amarrando anúncio → conversa → venda → ROI | **Não. Ninguém** captura `ctwa_clid` nem propaga origem até a venda | **Este é o fosso.** Único "só nós fazemos isso" real |
| Estoque / vitrine / publicação multiportal | Tem | **Sim, forte** (40+ portais, commodity) | Table stakes — não diferencia |
| Metas / funil / produtividade | Tem | Sim (Syonet, CRMs verticais) | Paridade |
| **Moto-first** (cadastro, portais de 2 rodas, financiamento com dinâmica própria) | **Sim, explícito** | **Fraco** — sistemas "não contemplam motos" bem | Nicho real e defensável |

## 3. Chance de venda por porte

- **Pequena revenda (o grosso, ~48 mil lojas):** dor máxima (não têm sistema), barreira de troca
  mínima — **mas** baixa maturidade digital, sensibilidade a preço (piso R$199–399/mês) e fricção
  de onboarding (a loja precisa entregar **credenciais bancárias** ao Motor — barreira de
  confiança/segurança). Melhor fit de _valor_, pior de _vender/suportar_ em escala.
- **Média revenda (30–200 veículos, já roda tráfego e financia):** dor migrou para "ferramentas
  que não conversam". Tem verba, volume para valorizar atribuição + financiamento, e incumbência
  ainda baixa. **É aqui que os três diferenciais pagam juntos. Beachhead.**
- **Grande concessionária de marca:** DMS homologado, margem esmagada, compra complexa. O Revy
  **não substitui DMS** e não deve brigar de frente; entraria só como camada add-on
  (WhatsApp + atribuição). Não é a praia — e é onde "eles já têm tudo" realmente vale.

## 4. Riscos que podem furar a tese

1. **O RPA é o diferencial E a fragilidade.** Portais de banco mudam, têm anti-bot e reputação de
   IP (há histórico de Bradesco travando em "Analisando dados" e suspeita de IP de datacenter). Se
   quebra por banco × por loja, o custo de suporte explode. Confiabilidade do Motor **é** o produto.
2. **Financiamento multibanco está commoditizando.** Credere a ~R$690/loja/mês é o padrão; o
   "sem comissão" é bom, mas a comissão do agregador costuma ser paga pelo banco e **invisível ao
   lojista**. Não lidere a venda por aqui.
3. **Tráfego "done-for-you" é serviço, não SaaS.** Não escala como software e mistura o modelo.
4. **O fosso (atribuição) é copiável.** AutoForce/Followize podem capturar CTWA amanhã. Janela é agora.
5. **Método:** números macro (mercado, crédito, McKinsey) são de fontes primárias; parte das
   estatísticas granulares de conversão vem de blogs de fornecedores — bons para dimensionar a dor,
   não para prometer ROI.

## 5. Recomendação

- **ICP / ponta de lança:** média revenda de **seminovos moto-first (30–200 unidades)** que já
  investe em tráfego pago e financia venda.
- **Lidere pela ATRIBUIÇÃO** ("descubra qual anúncio gerou qual venda") — é o único ponto que
  ninguém mais faz. Financiamento e estoque entram como "e ainda faz tudo isso".
- **Ancore preço no tier alto** (~R$700–1.200/mês), justificado por atribuição + financiamento
  próprio + tráfego gerido — competitivo contra pagar Credere (~R$690) sozinho.
- **Blinde o Motor:** IP residencial, retry, observabilidade por banco. É o maior risco operacional.

**Uma linha:** o Revy vende não como "mais um sistema de loja", mas como **a única ferramenta que
amarra anúncio → WhatsApp → financiamento → venda → ROI para revendas de moto/seminovos de porte
médio** — segmento numeroso, mal atendido e de baixa barreira de troca. Não brigue de frente com o
DMS das grandes concessionárias.

## Fontes

Fontes primárias-chave: Fenauto, Fenabrave, McKinsey (varejo automotivo/response-time), B3/Trillia
(crédito), Sebrae. Concorrência: sites oficiais de Linx, Dealernet, Sisand, Syonet, AutoForce,
AutoConf, Boom, Revenda Mais, Credere. Lista completa com URLs e grau de confiança nos dois
arquivos de pesquisa citados no topo.
