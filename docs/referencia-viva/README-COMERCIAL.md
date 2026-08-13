# Revy — visão comercial do produto

> Documento de direção comercial para referência futura. Não é uma especificação
> técnica nem representa funcionalidades já implementadas.

## Visão

A Revy será uma plataforma inteligente de vendas para revendas de motos e carros.

Ela conectará aquisição de leads, WhatsApp, estoque, vendedores, financiamento e
vendas para ajudar o empreendedor a:

- receber mais oportunidades qualificadas;
- responder mais rápido;
- converter mais leads em vendas;
- acompanhar a produtividade da equipe;
- identificar quais canais produzem receita e margem;
- reduzir oportunidades esquecidas e veículos parados.

## Posicionamento

> A Revy é a infraestrutura comercial inteligente da revenda.

A Revy não será vendida apenas como chatbot e não terá como atividade principal
operar tráfego pago. Seu papel será conectar os canais de aquisição ao processo
comercial e medir o caminho completo entre lead e venda.

O lançamento deve começar por lojas de motos, onde o produto atual está mais
maduro. A expansão para revendas de carros virá depois da validação comercial.

## Estrutura do produto

A Revy terá duas superfícies, com responsabilidades diferentes.

### Revy Control

Painel administrativo e técnico usado pelo Admin Revy e pelos gestores de tráfego.
Nele ficam cadastro e ativação de lojas, módulos contratados, integrações, aquisição,
saúde operacional e auditoria. Dono, gerente e vendedor não acessam esse painel.

O Control também concentra a configuração estrutural de pessoas e cargos, conexões
Meta/Google e números WhatsApp. Ele não contém conversas de venda nem credenciais dos
portais bancários.

### Revy Loja

Aplicação operacional única do dono, gerente e vendedor. Ela possui somente dois
módulos visíveis, habilitados conforme o contrato da loja.

Dentro dela, a equipe já provisionada é usada para distribuir leads e acompanhar a
operação. Contas e cargos estruturais são definidos no Control. Acessos bancários da
Simulação Multibanco permanecem protegidos em Vendas, disponíveis somente a dono e
gerente — nunca ao gestor de tráfego.

#### Vendas

Possui somente duas áreas visíveis:

- **Visão geral:** indicadores, leads aguardando resposta, vendas, pendências, alertas e
  recomendações.
- **Atendimento:** conversas, leads e clientes, histórico, responsável, situação da
  negociação, próxima ação, propostas e Simulação Multibanco.

O **Chatbot** atende, qualifica, coleta os dados, solicita a Simulação Multibanco e
transfere a negociação ao vendedor. O **Seller AI** resume, sugere respostas e recomenda
a próxima ação. Funil, Agenda, Simulação Multibanco e IA não aparecem como áreas
principais separadas.

Follow-ups, lembretes, visitas, propostas e o andamento da negociação continuam dentro
do cliente e do atendimento. A IA não pode inventar estoque, preço, condição financeira
ou aprovação, e o vendedor permanece responsável pela negociação.

Na **Simulação Multibanco**, os dados da negociação são enviados aos bancos configurados
e os retornos são apresentados para comparação. A Revy organiza as opções, mas as
condições definitivas e a aprovação continuam sendo responsabilidade dos bancos.
No fluxo atual, o Chatbot não envia automaticamente parcelas, taxas ou bancos ao cliente;
o vendedor recebe o resultado e conduz a apresentação das condições.

#### Estoque

Possui somente duas áreas visíveis:

- **Visão geral:** total de veículos, disponíveis, reservados, vendidos, estoque parado,
  procura e informações pendentes.
- **Veículos:** cadastro, fotos, preço, características, disponibilidade, clientes
  interessados e histórico.

O catálogo público é alimentado pelos veículos cadastrados. Estoque não utiliza IA;
seus indicadores são calculados diretamente a partir dos dados da operação.

### Infraestrutura e inteligência comercial

- A **camada de integração da Revy** conecta Meta, Google, WhatsApp, site, catálogo,
  marketplaces, formulários e outras fontes sem virar um terceiro produto visível.
- No Google Ads, a Revy conecta a conta autorizada, lê investimento e desempenho e
  devolve conversões comerciais para mensuração. Criação e otimização de campanhas
  continuam sendo trabalho do gestor diretamente no Google. O Registro de Campanha
  da Revy serve somente para atribuição, gasto e resultado.
- **Chatbot e Seller AI** aparecem somente dentro de Vendas; podem consultar dados do
  Estoque, mas não controlam nem alteram esse módulo.
- O dashboard deve ser bonito, responsivo e acionável, ligando aquisição, atendimento,
  estoque e venda para indicar o que fazer, não apenas mostrar números.

## Relação com gestores de tráfego

O tráfego poderá ser operado por:

- funcionário da própria loja;
- agência atual do cliente;
- gestor independente;
- parceiro recomendado pela Revy.

A Revy poderá conectar contas, medir resultados, atribuir vendas e gerar alertas e
relatórios automáticos. A operação diária de campanhas não será sua atividade principal.

Regra de produto:

> Se o valor cresce automaticamente pelo software, é produto. Se cada cliente
> exige trabalho humano diário da equipe Revy, está se tornando serviço de agência.

## Revy Partner

Revy Partner é uma possível embalagem comercial da visão de gestor do Revy Control,
não uma terceira aplicação nem uma entidade nova no domínio. Agências e gestores poderão
utilizar essa visão para várias lojas, contendo:

- campanhas e gastos;
- leads e oportunidades qualificadas;
- vendas atribuídas;
- CAC e ROAS;
- alertas e recomendações;
- relatórios automáticos.

Assim, agências se tornam parceiras e possíveis canais de venda da Revy.
Na primeira versão, isso não cria uma entidade Agência: cada profissional acessa as
lojas por vínculo individual e auditável no Revy Control.

## Perfis atendidos

- **Dono:** receita, margem, funil, equipe e estoque.
- **Gerente:** distribuição, SLA, oportunidades e produtividade.
- **Vendedor:** prioridades, conversas, tarefas, visitas e follow-ups.
- **Gestor de tráfego:** qualidade dos leads, vendas atribuídas e retorno.
- **Admin Revy:** lojas, planos, consumo, integrações e saúde operacional.

## Modelo comercial

A contratação é independente por loja e pode combinar:

- módulo Vendas;
- módulo Estoque;
- ambos os módulos;
- Chatbot, Seller AI e Simulação Multibanco, sempre embutidos em Vendas;
- integrações e faixas de volume de uso.

Possíveis fontes de receita:

- implantação;
- mensalidade por loja;
- usuários e números adicionais;
- consumo de WhatsApp e IA;
- capacidades opcionais e faixas adicionais de uso;
- integrações personalizadas;
- plano para parceiros.

Custos variáveis de WhatsApp, IA e infraestrutura não devem ser vendidos como uso
ilimitado sem política de franquia e excedente.

## Métrica principal

A Revy não deve otimizar somente a quantidade de leads.

> Métrica central: receita ou margem gerada por 100 leads recebidos.

Métricas auxiliares:

- tempo de resposta;
- taxa de qualificação;
- visitas e test-drives;
- simulações e propostas;
- conversão em venda;
- CAC e ROAS;
- margem por venda;
- dias do veículo no estoque;
- oportunidades recuperadas.

## Princípios permanentes

- A IA interpreta e recomenda; os serviços validam, autorizam e executam.
- Estoque, preço, permissões e resultados financeiros possuem fontes determinísticas.
- A plataforma deve provar resultado até a venda, não somente até o clique.
- Funcionalidades devem escalar sem crescimento proporcional da equipe Revy.
- Dados e acessos de cada empresa devem permanecer isolados.
- Automação sensível deve possuir auditoria, fallback e intervenção humana.
- O produto deve começar específico para revendas de motos antes de ampliar o mercado.

## Decisões ainda abertas

- política exata de visibilidade do vendedor;
- formato definitivo dos planos e preços;
- embalagem comercial da oferta para parceiros, sem criar Organização/Agência no domínio;
- primeira loja piloto;
- quais capacidades opcionais entram no primeiro contrato;
- limites detalhados entre sugestão da IA e aprovação humana.

## Próxima etapa

Os desenhos e planos técnicos canônicos agora são:

- [Revy Control — design](superpowers/specs/2026-07-29-revy-control-design.md) e
  [plano](plans/2026-07-29-plano-revy-control.md);
- [Revy Loja — design](superpowers/specs/2026-07-29-revy-loja-design.md) e
  [plano](plans/2026-07-29-plano-revy-loja.md).

A próxima etapa de produto é aprovar a política de visibilidade do vendedor e escolher
a primeira loja piloto. A implementação começa pelos baselines e gates de identidade,
não pelo Seller AI.
