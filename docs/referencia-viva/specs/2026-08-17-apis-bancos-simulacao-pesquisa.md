# APIs oficiais de simulação de CDC veículo — pesquisa (2026-08-17)

Pesquisa contra fontes primárias (portal do desenvolvedor do próprio banco, spec OpenAPI
publicada pelo banco, normativo do BCB). Blog e post de LinkedIn só aparecem quando
explicitamente marcados como fonte secundária.

Escopo: o que existe hoje de API HTTP oficial para uma **revenda/lojista** simular
parcela e taxa de financiamento de veículo, e o que é preciso para obter acesso —
para decidir se dá para sair do Playwright em `motor-simulacao/`.

---

## Resumo executivo

Dá para sair do Playwright **em parte, e não hoje mesmo**. Dos quatro provedores em
produção, **dois têm API oficial de simulação documentada publicamente: Banco Pan e BV**.
Nos dois casos a doc é pública, a API cobre simulação de parcela/taxa (não só consulta de
contrato), e existe sandbox — mas a credencial só sai com **aprovação comercial do banco**
(gerente comercial no Pan; contrato de parceria no BV). Ou seja: o bloqueio não é técnico,
é comercial. **Santander e Bradesco não têm** API de financiamento de veículo no catálogo
público do developer portal — Santander tem imobiliário e "Usecasa", Bradesco tem só
débitos veiculares/cobrança/Pix; para esses dois o RPA continua sendo o único caminho
conhecido. **Itaú, BB, Caixa, Sicredi, Sicoob**: nada de simulação de CDC veículo no
catálogo público. **Open Finance não resolve** — as APIs de crédito são leitura de
operações já contratadas e portabilidade de contrato existente, não cotação de CDC novo.
O caminho mais rápido para cobertura ampla é um **hub multibanco** (FANDI, Credere,
Autoconf, AutoCerto), que já é correspondente e vende integração pronta.
CNPJ + site destravam o cadastro no sandbox e a conversa comercial; o que ainda falta é
**contrato/credenciamento com cada banco**, **certificado digital para mTLS** (obrigatório
no BV, ICP-Brasil ou GlobalSign) e **certificação Febraban da equipe** quando houver
originação de proposta (Res. CMN 4.935, art. 16).

---

## Tabela por banco

| Banco | Tem API de simulação de CDC veículo? | Link da doc | Como obter acesso | Auth | Sandbox | Confiança | Fonte |
|---|---|---|---|---|---|---|---|
| **Banco Pan** | **Sim** — `POST /openapi/veiculos/v1/simulacao`, além de `GET .../preanalise` e catálogo de veículo (marcas/modelos/versões) | [developers.bancopan.com.br/documentacao/financiamento-veiculos](https://developers.bancopan.com.br/documentacao/financiamento-veiculos) | E-mail para `bancopanprd@service-now.com`, assunto `[OPENAPI-ACESSO] – ConcessaoDeAcesso`, anexando **aprovação do gerente comercial Pan responsável pela loja**, termo de aceite assinado e formulário de cadastro ([ZIP oficial](https://developers.bancopan.com.br/assets/docs/financiamento-veiculos/documentos-financiamento-veiculos.zip)) | `APIKEY` + `SECRET_KEY` → `Basic base64(apikey:secretkey)` em `POST /veiculos/v0/tokens` (rate limit 5/min) | **Sim** — sandbox primeiro, produção depois da homologação | **Alta** | [portal Pan](https://developers.bancopan.com.br/), [FAQ Pan](https://developers.bancopan.com.br/suporte/faq) |
| **BV (banco BV / BV Financeira)** | **Sim** — jornada F&I completa: pré-análise → pré-simulação → condições de financiamento → **precificação online** (é aqui que a simulação acontece) → ajuste de valores → originação | Portal: [developers-sandbox.bvopen.com.br/apis](https://developers-sandbox.bvopen.com.br/apis) · API "Parceiros F&I": [/api/62](https://developers-sandbox.bvopen.com.br/api/62) · "Parceiros F&I - Digitais": [/api/63](https://developers-sandbox.bvopen.com.br/api/63) · OpenAPI 3.1 aberto: [fandi_openapi_3.yaml](https://developers-sandbox.bvopen.com.br/sites/default/files/apidoc_specs/fandi_openapi_3.yaml) | Cadastro self-service no portal → cria App → pega Consumer Key/Secret de **sandbox** (grátis). Produção **só com contrato de parceria** assinado. Canal comercial: ["Seja Um Parceiro"](https://developers-sandbox.bvopen.com.br/) / [parceiro.bv.com.br](https://parceiro.bv.com.br/) | **OAuth2 client_credentials** (`POST /token`; sandbox `https://apige-uat-sbx.bvopen.com.br/oauth/sandbox/v1/jwt`) **+ mTLS obrigatório**. Produção exige certificado **SSL v10 ICP-Brasil** (sob a CA "Autoridade Certificadora Raiz Brasileira v10") **ou GlobalSign EV/OV**. Homologação aceita certificado autogerado assinado pelo BV | **Sim** — servidor de homologação `https://apige-uat-sbx.bancobv.com.br` | **Alta** | spec OpenAPI publicada pelo próprio BV (linkada acima) |
| **Santander** | **Não** (no catálogo público). Categoria "Credit" tem só *Credit limit inquiry* (capital de giro), *Real Estate Credit* e *Usecasa* (imóvel em garantia). "Vehicle Debt" é IPVA/multa/licenciamento. "Digital Corban" é pagamento de contas, não originação de crédito | [developer.santander.com.br/api-library](https://developer.santander.com.br/api-library) · catálogo completo no [sitemap](https://developer.santander.com.br/sitemap.xml) | n/a para veículo. O canal do lojista é o app/portal **Financiamento Lojista** e **Santander Financiamentos +Negócios** — produto, não API | n/a | n/a | **Alta** (catálogo público conferido item a item) | [api-library](https://developer.santander.com.br/api-library), [sitemap](https://developer.santander.com.br/sitemap.xml) |
| **Bradesco** | **Não** no catálogo público. Categorias públicas: Ágora Investimentos, **Vehicle Debts**, Receivables, Pix, Conciliation, Payments. Nada de financiamento/CDC | [developers.bradesco.com.br](https://developers.bradesco.com.br/) · [/categories](https://developers.bradesco.com.br/categories) | Portfólio completo **atrás de login** ("Log in to access our full portfolio") — não deu para confirmar o que existe lá dentro | n/a | n/a | **Média** — o catálogo público não tem; o catálogo logado **não foi verificado** | [developers.bradesco.com.br](https://developers.bradesco.com.br/) |
| **Itaú** | **Não** no catálogo público. Produtos: Pix, **Consignado**, Recuperação de crédito, Iniciação de pagamentos, **Corban Digital**, Garantias, Banco Tesoureiro, Fundos, Câmbio, Open Finance. Nenhum de veículo/CDC | [devportal.itau.com.br/nossas-apis](https://devportal.itau.com.br/nossas-apis) | Doc detalhada exige login; Corban Digital fica em `/baas/#/catalog/home-product/p/corban` (autenticado) | não confirmado (login) | não confirmado | **Média-alta** para "não tem veículo"; **baixa** para o conteúdo do Corban Digital | [devportal.itau.com.br](https://devportal.itau.com.br/nossas-apis) |
| **Banco do Brasil** | **Não**. Catálogo público é Cobrança, Pix, Arrecadação, BB Pay, **Débitos Veiculares** (tributo, não financiamento) | [bb.com.br/site/developers](https://www.bb.com.br/site/developers/) · [API Débitos Veiculares](https://www.bb.com.br/site/developers/api-debitos-veiculares/) | n/a | n/a | n/a | **Média-alta** (portal BB bloqueia acesso automatizado; catálogo levantado por índice de busca no próprio domínio) | [bb.com.br/site/developers](https://www.bb.com.br/site/developers/) |
| **Caixa** | **Não confirmado** — portal fora do ar (HTTP 504 via Azion) nas tentativas de 2026-08-17 | [desenvolvedores.caixa.gov.br](https://desenvolvedores.caixa.gov.br/) · [explorer](https://desenvolvedores.caixa.gov.br/apiresources/explorer) | não confirmado | não confirmado | não confirmado | **Baixa** | tentativa direta (504) |
| **Safra / Safra Financeira** | **Não confirmado** — não achei developer portal público. Existe integração de simulador Safra **dentro de plataformas de terceiros** (ex.: AutoCerto), o que é indício de API/canal B2B fechado | Site do produto: [safrafinanceira.com.br](https://www.safrafinanceira.com.br/) · indício: [AutoCerto FAQ — Simulador Safra](https://autocerto.com/Faq/simulador-de-financiamento-(safra)/59/detalhes) (fonte secundária) | Comercial/parceria — não documentado publicamente | não confirmado | não confirmado | **Baixa** | ver links |
| **Daycoval** | **Não confirmado** — sem developer portal público de crédito veicular | [daycoval.com.br/credito-para-voce/veiculos](https://www.daycoval.com.br/credito-para-voce/veiculos/) | não confirmado | n/a | n/a | **Baixa** | ver link |
| **Omni Financeira** | **Não confirmado** — existe "área do parceiro"/lojista (portal web), não API documentada | [omni.com.br/produtos/financiamento-de-carro](https://www.omni.com.br/produtos/financiamento-de-carro/) | Credenciamento de lojista pelo canal comercial | n/a | n/a | **Baixa** | ver link |
| **Sicredi** | **Não** — catálogo público tem só APIs de **Open Data** (Produtos e Serviços, Canais de Atendimento), exigidas pelo BCB | [developer.sicredi.com.br — Catálogo de APIs](https://developer.sicredi.com.br/api-portal/pt-br/content/catalogo-de-apis) | n/a | n/a | tem sandbox das Open Data | **Alta** | link acima |
| **Sicoob** | **Não** — catálogo: Cobrança Bancária, Cobrança Pagamentos, Conta Corrente, Convênios Pagamentos, Investimentos RDC, Open Finance Iniciação, Pix Pagamentos, Pix Recebimentos, Poupança, SPB Transferências | [developers.sicoob.com.br/portal/apis](https://developers.sicoob.com.br/portal/apis) | Cadastro no portal; criar app exige **ter conta no Sicoob** | credencial por app | produção direta | **Alta** | link acima |
| **Banco Master** | **Não confirmado** — não achei developer portal público | — | — | — | — | **Baixa** ("não achei" honesto) | — |
| **Crefisa** | **Não confirmado** — não achei developer portal público | — | — | — | — | **Baixa** ("não achei" honesto) | — |
| **Fontecred (Fontecred SCD S.A.)** | **Não confirmado** — não achei doc pública de API. Aparece como SCD parceira em plataformas de terceiros | [fontecred.com.br](https://www.fontecred.com.br/) | Canal comercial / parceria | não confirmado | não confirmado | **Baixa** | ver link |

### Detalhe do BV (o achado mais forte)

Os endpoints abaixo estão na spec OpenAPI 3.1 que o **próprio BV publica sem login**
([fandi_openapi_3.yaml](https://developers-sandbox.bvopen.com.br/sites/default/files/apidoc_specs/fandi_openapi_3.yaml)),
título `Guia de Integração – Parceiros F&I - APIs`, versão 1.0.5:

```
POST /token                                                  (OAuth2 client_credentials)
POST /pre-analyze-vehicles/v2/pre-analysis-vehicle-financing  (pré-análise, SCR)
POST /partners/v1/pre-simulation                              (parceiros digitais)
POST /partner-funding/v1/financing-conditions                 (parceiros F&I: tabelas/taxas)
POST /pricing-online/v1/pricing-online-fandis                 (SIMULAÇÃO: parcelas, PMT, entrada mínima)
POST /price-adjustment/v1/calculate-values-adjusted           (recálculo com seguros, IOF/ICMS)
POST /certified-agent/v1/agents                               (agentes certificados do parceiro)
POST /origination-proposal/v3/origination-proposals           (originação da proposta)
GET  /cvg-api/v2/{categorias|marcas|modelos|versoes}          (catálogo de veículo, Molicar/FIPE)
```

Pontos que importam para o `motor-simulacao/`:

- A etapa de simulação de fato é **`pricing-online`**. Ela devolve `installmentMaximumValue`
  (parcela máxima pela política de crédito), `minimumEntryValue` e `minimumEntryValuebyTerm`
  — ou seja, dá para montar contraproposta sem tentativa-e-erro.
- Identificação do veículo por **código Molicar ou código FIPE**.
- **Webhook**: o parceiro precisa expor uma URL (mais chave) e cadastrar no BV para receber
  status de protocolo/proposta. Isso é novo em relação ao modelo de polling do RPA.
- A confirmação da hipótese de backlog: a URL antiga
  `developers-des.bancovotorantim.com.br/documentation/iniciar-simulacao-financiamento-v4`
  **não resolve mais em DNS** (era ambiente `des`, de desenvolvimento). O portal vivo é
  `developers-sandbox.bvopen.com.br`, e o equivalente da "Iniciar Simulação Financiamento
  Veículo (V4)" hoje é a **API de Pré-Análise** (`pre-analysis-vehicle-financing`), que é
  descrita como "iniciar simulação a partir de CPF/CNPJ e grupo de categoria do veículo".
  *(Inferência minha ao comparar a descrição indexada da URL antiga com a spec atual.)*
- Existe uma variante **BB Zero KM Leves**: para concessionária, cliente correntista do BB,
  a simulação inteira roda no Banco do Brasil por trás da API do BV. Não serve para revenda
  de usados.

### Detalhe do Pan

Fluxo confirmado na doc: `POST /veiculos/v0/tokens` → `GET /openapi/veiculos/v0/lojas/{idLoja}/preanalise`
→ **`POST /openapi/veiculos/v1/simulacao`** → `POST /openapi/veiculos/v0/gravarSimulacao`
→ `POST /openapi/veiculos/v0/propostas/{numeroProposta}` → formalização
(`GET /veiculos/v0/formalizador/{idLoja}/{cpf}/{numeroProposta}/links`).

Existe `GET /veiculos/v0/lojas?cnpj={cnpj}` — a **loja precisa estar cadastrada no Pan**
com o CNPJ para virar `idLoja`. FAQ oficial, verbatim:

> "Qualquer um pode usar as APIs do PAN? **Por enquanto só estamos liberando o acesso para
> os parceiros que já tem uma relação comercial com o Pan.**"
> "Como solicitar acesso à Open API? **Entre em contato com seu Gerente Comercial** e peça
> o acesso das APIs que ele irá te orientar sobre os próximos passos."

Autenticação é **Basic (APIKEY:SECRET_KEY em base64)** trocado por token — **não** é
OAuth2 client_credentials nem mTLS. Mais simples que o BV.

---

## Agregadores / hubs multibanco

Este é o mercado real: empresas que já são correspondentes credenciadas em vários bancos e
revendem **uma** integração. Nenhuma delas publica documentação de API aberta — todas exigem
contato comercial. Preços e cobertura abaixo vêm de páginas das próprias empresas ou de
imprensa especializada (marcado).

| Hub | O que é | Bancos cobertos | API pública documentada? | Modelo comercial | Fonte |
|---|---|---|---|---|---|
| **FANDI** | Se apresenta como "líder absoluto em plataforma multibanco"; simulador web + integrador multibanco + ERP. Mais de 3.000 concessionárias, ~1 milhão de veículos financiados | "Financeiras integradas" (lista no site, sem doc técnica) | **Não** — só "APIs integradas aos sistemas dos clientes" como feature | Não publicado; contato comercial | [fandi.com.br](https://fandi.com.br/) |
| **Credere** | Motor multibanco embutível; tem widget em `embed.meucredere.com.br` e simulador por loja em `app.meucredere.com.br/simulador/loja/{id}` | Itaú, BV, Pan, Bradesco, Santander, Honda, Creditas (+ Safra em integração) — **fonte secundária** | **Não achei** doc pública de API REST. O que existe publicamente é o embed/white-label | Mensalidade citada em ~**R$ 690/mês por loja** — **fonte secundária** (Finsiders) | [meucredere.com.br](https://www.meucredere.com.br/); cobertura e preço: [Finsiders](https://finsidersbrasil.com.br/reportagem-exclusiva-fintechs/credere-atrai-grandes-varejistas-de-veiculos-e-receita-cresce-35x/) |
| **Autoconf** | DMS de revenda com "simulador de financiamento multibancos" | Não listado publicamente | **Não** | SaaS | [autoconf.com.br](https://autoconf.com.br/blog/simulador-de-financiamento-multibancos/) |
| **AutoCerto** | DMS de revenda; simulador que "envia proposta e retorna resultado em segundos" — cita Safra nominalmente | Safra confirmado; outros não listados | **Não** | SaaS por plano | [autocerto.com](https://autocerto.com/), [FAQ Simulador Safra](https://autocerto.com/Faq/simulador-de-financiamento-(safra)/59/detalhes) |
| **Boom Sistemas** | DMS; integra **Credere** por dentro | Via Credere | **Não** | SaaS | [boomsistemas.com.br](https://boomsistemas.com.br/blog/post/simulacao-multibanco-aumentar-vendas-revenda-veiculos) |
| **Cockpit / Pro Cockpit (grupo Webmotors/Santander)** | CRM + anúncios + **Simulador de Financiamento Santander** embutido; proposta vai direto para o Santander e é acompanhada no "+Negócios" | **Só Santander** | **Não** — é plugin dentro do produto, não API para terceiros | SaaS (Webmotors) | [ajuda.cockpit.com.br](https://ajuda.cockpit.com.br/hc/pt-br/articles/5576088779156-Como-utilizar-o-Simulador-de-Financiamento-Santander-via-Plugin-Pro-Cockpit) |
| **Creditas** | Tem a **melhor doc pública** de todas — mas o produto é **Auto Equity / Home Equity** (veículo *em garantia*, refinanciamento), **não CDC de compra** | Creditas (balcão próprio) | **Sim, pública**: [developers.creditas.com.br](https://developers.creditas.com.br/docs) — inclui `GET /simulations` ("Simulação Fria") e `/offers` ("Simulação Quente"), webhook, OAuth. Tem até [llms.txt](https://developers.creditas.com.br/llms.txt) | Exige **contrato de intermediação assinado**; credencial vai por e-mail ao responsável técnico; staging → produção | [Guia de Integração Creditas](https://developers.creditas.com.br/docs) |

**Leitura minha (inferência):** o único caminho de API *self-service-ish* com doc aberta e
fluxo de onboarding escrito é a **Creditas** — mas ela não resolve CDC de compra de veículo.
Para CDC, os hubs são caixas-pretas comerciais: o valor deles é o credenciamento que você
não tem, não a tecnologia.

---

## Open Finance — veredito

**Não serve para simulação de CDC de veículo. Ponto.**

- O catálogo oficial de APIs está em
  [Especificações de APIs — Área do Desenvolvedor](https://openfinancebrasil.atlassian.net/wiki/spaces/OF/pages/17367659/Especifica+es+de+APIs).
  Os grupos são: **Dados Abertos (DA)**, **Dados Cadastrais e Transacionais (DC)**,
  **Serviços (SV)** e **Portabilidade de Crédito (PC)**.
- As APIs de crédito de dados são **leitura de operações já contratadas**. A do BV, publicada
  como espelho da spec do OFB, é explícita: *"API que retorna informações de operações de
  crédito do tipo financiamento, mantidas nas instituições transmissoras por seus clientes,
  incluindo dados como denominação, modalidade, número do contrato, tarifas, prazo,
  prestações, pagamentos, amortizações, garantias, encargos e taxas de juros remuneratórios."*
  ([BV Open — APIs públicas, pág. 3](https://developers-sandbox.bvopen.com.br/apis?page=2)).
  Isso é histórico de contrato, não cotação de operação nova.
- **Portabilidade de Crédito (PC)** move um contrato **existente** entre instituições
  (elegibilidade, pedido, cancelamento, dados para TED). Não cota um financiamento novo.
  Spec: [Portabilidade de Crédito](https://openfinancebrasil.atlassian.net/wiki/spaces/OF/pages/1002668073/Portabilidade+de+Cr+dito) ·
  [Informações Gerais PC v1.0.0](https://openfinancebrasil.atlassian.net/wiki/spaces/OF/pages/1141637139/Informa+es+Gerais+-+PC+Portabilidade+de+Cr+dito+-+CPC+-+v1.0.0)
- **Quem pode participar:** *"A regulamentação vigente do Open Finance permite a participação
  no ecossistema de instituições financeiras, instituições de pagamento e demais instituições
  **autorizadas a funcionar pelo Banco Central do Brasil** (art. 1º, Resolução Conjunta nº
  01/2020)."* — uma revenda **não** pode ser participante direta.
  ([Modelo de participação](https://openfinancebrasil.org.br/modelo-de-participacao/))
- O art. 36 da mesma Resolução Conjunta permite que uma instituição **autorizada** contrate
  parceria com **não autorizada** para compartilhar dados, com consentimento do cliente — e a
  autorizada responde diretamente pela parceria. É a porta pela qual agregadores de dados
  operam. Não é porta para simulação de CDC. (mesma fonte)

---

## Regulatório — correspondente bancário

Fonte primária: **Resolução CMN nº 4.935, de 29/07/2021** (dispõe sobre a contratação de
correspondentes no País). O texto integral está reproduzido em
[LegisWeb](https://www.legisweb.com.br/legislacao/?id=418036); PDF do DOU em
[poder360](https://static.poder360.com.br/2021/07/Resoluc%CC%A7a%CC%83o-CMN-n4.935-de-29_7_2021.pdf)
(é PDF de imagem, não extraível como texto). Análise de Impacto Regulatório do próprio BCB:
[Res CMN 4935 AIR — Correspondentes no País](https://www.bcb.gov.br/content/publicacoes/air/Res%20CMN%204935%20AIR_Correspondentes_no_Pais.pdf).

O que importa aqui:

- **Art. 3º** — *"O correspondente atua por conta e sob as diretrizes da instituição
  contratante, que assume inteira responsabilidade pelo atendimento prestado aos clientes e
  usuários por meio do contratado."* → **o correspondente não pede autorização ao BCB; quem
  contrata é o banco, e o banco responde.** Não existe "registro de correspondente" no BCB
  que a revenda tire sozinha.
- **Art. 4º** — podem ser contratados como correspondente "as sociedades, os empresários e as
  associações definidos na Lei nº 10.406/2002 (Código Civil)". Um CNPJ de revenda se encaixa.
- **Art. 12, inciso V** — entre as atividades contratáveis está a
  *"recepção e encaminhamento de propostas de operações de crédito e de arrendamento mercantil"*.
  É exatamente o que uma revenda faz quando envia ficha para o banco.
- **Art. 15** — teto de remuneração: até **6% do valor da operação** na contratação de crédito
  (3% em portabilidade), com pagamento pro rata temporis depois disso.
- **Art. 16** — *"A qualidade técnica do atendimento deve ser atestada por exame de
  certificação aplicado à equipe do correspondente que preste atendimento em operações de
  crédito e arrendamento mercantil."* O conteúdo cobre técnica da operação, regulamentação,
  **LGPD**, CDC, ética e ouvidoria.

**Simular exige tudo isso?** Inferência minha, com base na leitura acima: **simular sozinho,
não.** O art. 12 fala em *recepção e encaminhamento de propostas*; uma cotação que não vira
proposta encaminhada não é, por si, atendimento em operação de crédito. **Mas isso é teórico**
— na prática o banco não te dá credencial de API de simulação sem o contrato de
correspondente/parceiro, porque a simulação é o degrau 1 de uma esteira que termina em
originação (é literalmente assim que BV e Pan desenham a jornada). Então o requisito chega
junto, por contrato, não por norma isolada.

**Certificação Febraban:** a sigla certa para veículos/CDC é **FBB-130 ("Febraban Veículos e
CDC")**, não CA-600 — **CA-600 é ABECIP, de crédito imobiliário**. Não consegui abrir a
página oficial da Febraban (portal renderiza vazio para acesso automatizado); a atribuição da
FBB-130 a "veículos e CDC" vem de **fontes secundárias** de cursinho
([aprovabancarios](https://aprovabancarios.com/febraban/veiculos/)) e precisa ser confirmada
com o banco ou com a Febraban antes de virar decisão. O que é **primário** é o art. 16: existe
obrigação de certificação para quem atende operação de crédito.

---

## Caminho recomendado (CNPJ novo + site próprio)

Ordem sugerida. O que o CNPJ + site já destravam: cadastro em portal de desenvolvedor,
sandbox, e a conversa comercial (banco pede CNPJ e endereço digital). O que **não**
destravam: contrato, credencial de produção, certificado ICP-Brasil.

1. **Hoje, sem falar com ninguém — BV sandbox.**
   Cadastro self-service em [developers-sandbox.bvopen.com.br](https://developers-sandbox.bvopen.com.br/como-comecar):
   "Cadastre-se" → confirma e-mail → *Meus APPS* → *Add app* → seleciona o produto → sai
   Consumer Key / Consumer Secret. **Sem custo** ("Não há custo para testar as soluções BV
   Open Plus no ambiente de Sandbox"). Já dá para escrever o `ApiBankDriver` do BV contra o
   `fandi_openapi_3.yaml` e o servidor `apige-uat-sbx.bancobv.com.br`.
   Em paralelo, gerar CSR autoassinado e pedir a assinatura do BV para o mTLS de homologação
   (o passo a passo com o comando `openssl` está na própria spec).

2. **Hoje, por e-mail — Pan.**
   Você já tem relação com o Pan (dual-path no código). Pedir ao **gerente comercial Pan da
   loja** a aprovação por e-mail e mandar para `bancopanprd@service-now.com`, assunto
   `[OPENAPI-ACESSO] – ConcessaoDeAcesso`, com o termo de aceite + formulário do
   [ZIP oficial](https://developers.bancopan.com.br/assets/docs/financiamento-veiculos/documentos-financiamento-veiculos.zip).
   Sandbox primeiro, produção depois. Esse é o caminho de **menor atrito técnico** de todos
   (Basic auth, sem mTLS).

3. **Semana 1–2 — abrir a conversa comercial do BV para produção.**
   [parceiro.bv.com.br](https://parceiro.bv.com.br/) / "Seja Um Parceiro" no portal.
   Pauta: contrato de parceria F&I, cadastro do webhook (URL + chave), e **qual certificado**
   eles aceitam. Perguntar explicitamente se para revenda de usados o caminho é "Parceiros
   F&I" ou "Parceiros F&I - Digitais" — os dois existem e a pré-simulação é só do segundo.

4. **Semana 2 — certificado digital.**
   O e-CNPJ A1 comum **não** basta para o BV: a exigência é **certificado SSL** ICP-Brasil v10
   (cadeia "Autoridade Certificadora Raiz Brasileira v10") ou GlobalSign EV/OV. Isso é
   certificado de servidor/aplicação, emitido por Serasa ou equivalente, com custo e prazo
   próprios. Vale pedir orçamento já, porque é o item de lead time mais longo.

5. **Semana 2–4 — cotar um hub para o que não tem API.**
   Santander e Bradesco não têm API pública de veículo. Se a cobertura desses dois for
   necessária, pedir proposta a **FANDI** e **Credere** (e, se o DMS já for um deles,
   **Autoconf** / **AutoCerto**). Pergunta obrigatória na primeira reunião, porque não está
   documentado em lugar nenhum: *"vocês expõem API REST para o meu backend, ou só
   iframe/white-label?"* — se for só embed, não substitui o `PlaywrightBankDriver`, só muda
   de tela.

6. **Enquanto isso, o que fica em RPA.**
   **Santander e Bradesco continuam em Playwright** — não há alternativa oficial conhecida.
   Fontecred idem, até confirmar com o comercial deles. Consequência prática: o plano de
   **IP residencial para o worker continua necessário**, só que para 2 provedores em vez de 4.
   Sugestão de sequência de migração (inferência minha):
   Pan (API já no código, formalizar credencial) → BV (API nova, maior ganho) → só então
   reavaliar Santander/Bradesco via hub.

---

## Lacunas — o que não deu para confirmar por fonte primária

Sendo honesto, isto é o que **não** foi verificado:

- **Bradesco:** o catálogo completo está atrás de login ("Log in to access our full
  portfolio"). Não posso afirmar que não existe API de financiamento de veículo lá dentro —
  só que **não está no catálogo público**.
- **Itaú — Corban Digital:** a doc do produto (`/baas/#/catalog/home-product/p/corban`) exige
  login. Não sei se cobre só consignado ou mais. O nome sugere consignado (é o produto que
  aparece ao lado na lista), mas é palpite.
- **Caixa:** portal `desenvolvedores.caixa.gov.br` devolveu **HTTP 504** em todas as
  tentativas de 2026-08-17. Zero informação obtida.
- **Banco Pan — corpo da API:** o portal responde **403 (Akamai)** a acesso direto deste
  ambiente. O conteúdo citado (endpoints, FAQ, fluxo de credencial) foi lido via proxy de
  texto `r.jina.ai` sobre as URLs oficiais do Pan. Os **paths e o texto do FAQ são confiáveis**,
  mas **não li o schema de request/response** de `POST /openapi/veiculos/v1/simulacao` — o
  detalhe está no [documentacao.zip](https://developers.bancopan.com.br/assets/docs/financiamento-veiculos/documentacao.zip)
  que não baixei. **Recomendo abrir esse ZIP antes de estimar o driver.**
- **BV — elegibilidade de revenda pequena:** a spec é pública e não impõe faturamento mínimo
  *no texto*, mas produção depende de "efetivação de um contrato de parceria". **Não achei**
  critério publicado de quem o BV aceita como parceiro F&I. Só a reunião comercial responde.
- **Preço/take rate dos hubs:** só o valor da Credere (~R$690/mês/loja) apareceu, e em
  **fonte secundária** (Finsiders). FANDI, Autoconf, AutoCerto e Boom não publicam preço.
- **Febraban:** não consegui ler a página oficial de certificação de correspondentes (portal
  renderiza vazio para acesso automatizado). A associação **FBB-130 → veículos/CDC** está
  apoiada só em fonte secundária. O art. 16 da 4.935 é primário; a sigla não.
- **Santander/Webmotors "Carbon":** procurei e **não achei** nada chamado "Carbon" como
  plataforma ou API. O que existe e foi confirmado é **Cockpit** (Webmotors) com simulador
  Santander embutido, e **Santander Financiamentos +Negócios** como portal do lojista.
  Se "Carbon" for nome interno ou de time, não tem pegada pública.
- **Safra, Daycoval, Omni, Master, Crefisa, Fontecred:** nenhum developer portal público
  encontrado. "Não achei" — não é o mesmo que "não existe"; pode ser canal fechado por
  credenciamento, que é o padrão desse mercado.
- **Texto integral da Res. 4.935:** o PDF oficial do DOU é imagem escaneada. Os artigos
  citados vieram de reprodução em LegisWeb. Antes de usar em contrato ou em decisão jurídica,
  confirmar no [Busca de Normas do BCB](https://www.bcb.gov.br/estabilidadefinanceira/buscanormas).
