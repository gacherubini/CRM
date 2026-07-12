# Plano #3B — Dashboard do Dono, Vendas e Metas

> **Pré-requisito:** #3A. **Status 2026-07-12:** Tasks 1–3 e 6–7 parciais entregues (vendas, custos,
> metas de loja, `/app/financeiro`, `/app/vendedor`, funil inicial). Aberto: metas por vendedor UI,
> eventos externos de handoff, campanhas, CSV, reconciliação E2E (Tasks 4–5, 8–10).
> Credenciais de banco/portal ficam no **#3A Task 9A** + Motor #1A, não neste plano.
> Não inferir venda/lucro só a partir de mensagens/leads.

**Goal:** Dar ao dono e gerente visão confiável de vendas, metas, desempenho dos vendedores,
conversão, origem dos leads e lucro bruto.

## Definições

- **Venda:** registro confirmado, não simples mudança de lead para “ganho”.
- **Faturamento:** soma de `preco_venda` das vendas válidas no período.
- **Lucro bruto:** `preco_venda - custo_veiculo - custos_diretos`.
- **Conversão:** leads elegíveis que viraram venda / leads elegíveis recebidos no período, com
  metodologia exibida no dashboard.
- **Atingimento:** realizado / meta, respeitando o tipo da meta.
- **Lucro líquido:** fora do escopo até existir módulo contábil/despesas completo.

## Dados adicionais

- `vendas`: loja, lead, vendedor, veículo/referência, valores, data e status;
- `venda_custos_diretos`: documentação, frete, comissão e outros custos atribuíveis;
- `metas`: escopo loja/vendedor, tipo, período e valor;
- `campanhas`: canal, origem, UTMs, custo e período;
- `lead_atribuicoes`: vendedor e intervalo de responsabilidade;
- `lead_eventos`: primeira resposta, etapas, perda e ganho;
- `ajustes_comerciais`: cancelamento/estorno com motivo e auditoria.

## Tasks

### Task 1: Modelo de venda e permissões

Implementar criação, confirmação, cancelamento e correção auditada. Vendedor pode propor/registrar
conforme política; gerente/dono confirma valores sensíveis. Venda sempre pertence à mesma loja de
lead, vendedor e veículo referenciado.

**Aceite:** não é possível vincular entidades de lojas diferentes nem apagar venda confirmada.

### Task 2: Custos e lucro bruto

Registrar custo do veículo e custos diretos por categoria, com permissões próprias. Calcular em
`Decimal` no backend e rotular sempre como lucro bruto.

**Aceite:** testes cobrem venda, cancelamento, custo posterior autorizado e arredondamento.

### Task 3: Metas

Permitir meta por loja/vendedor e período, inicialmente:

- quantidade de vendas;
- faturamento;
- lucro bruto;
- conversão.

Impedir sobreposição ambígua do mesmo tipo/escopo/período ou definir prioridade explícita.

### Task 4: Eventos do funil

Registrar atribuição, primeira resposta, mudanças de etapa, perda e venda. Eventos recebidos do
Chatbot são idempotentes; ações manuais geram os mesmos tipos de evento.

**Aceite:** tempo de resposta e conversão são recalculáveis a partir do histórico.

### Task 5: Campanhas e atribuição

Cadastrar/importar campanha, origem, canal, UTM e custo. Primeira versão usa atribuição declarada:
`first_touch` e `last_touch`, exibidas separadamente. Não prometer causalidade automática.

### Task 6: Dashboard do vendedor

Mostrar somente dados autorizados:

- vendas e valor vendido no período;
- meta e atingimento;
- conversão própria;
- leads em aberto e tarefas;
- veículos vendidos, quando houver referência do Estoque.

### Task 7: Dashboard do dono/gerente

Mostrar:

- vendas, faturamento e lucro bruto;
- metas da loja e por vendedor;
- funil e conversão;
- tempo de primeira resposta;
- origem/campanha e custo por lead/venda quando houver custo;
- filtros por período, vendedor, origem e tipo de veículo.

Toda métrica exibe definição e período; dashboard vazio não inventa dados.

### Task 8: Relatórios e exportação

CSV de vendas, metas e funil com autorização e auditoria. Totais exportados devem reconciliar com
o dashboard para os mesmos filtros.

### Task 9: Testes de reconciliação

Criar cenário conhecido com múltiplos vendedores, cancelamento, reatribuição e campanhas. Validar
manualmente e por teste todas as fórmulas principais.

### Task 10: Operação standalone e integrada

Testar com dados manuais/CSV, depois com Chatbot e Estoque falsos. Nenhuma métrica básica de venda
depende da disponibilidade em tempo real de outro produto.

## Fora de escopo

- Contabilidade, impostos e lucro líquido.
- Automação de postagem/anúncios.
- Otimização automática de campanhas.
- Folha/comissionamento completo; custos diretos podem registrar comissão paga.

## Resultado

Dashboards do vendedor e do dono baseados em vendas registradas e fórmulas auditáveis, não em
estimativas derivadas apenas de conversas.
