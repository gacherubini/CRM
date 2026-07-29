# Domínio comercial da Revy

A Revy atende lojas de veículos e permite que profissionais autorizados operem
suas atividades comerciais e de aquisição.

## Language

**Loja**:
Cliente comercial da Revy e unidade de isolamento, configuração e contratação.
_Avoid_: Organização, tenant, conta cliente

**Pessoa Revy**:
Identidade canônica reconhecida uma única vez no ecossistema, podendo receber acesso ao
Revy Control e/ou cargos em Lojas sem misturar as permissões dessas superfícies.
_Avoid_: Usuário global, conta de uma organização

**Usuário da Loja**:
Pessoa Revy vinculada a uma ou mais lojas para
acessar os módulos contratados no Revy Loja, podendo acumular cargos diferentes em cada loja.
_Avoid_: Cliente, membro da organização

**Cargo na Loja**:
Responsabilidade atribuída a um usuário no contexto de uma loja, como dono, gerente
ou vendedor; um usuário pode acumular mais de um cargo na mesma loja.
_Avoid_: Papel global, cargo da organização

**Admin Revy**:
Usuário com autoridade global para administrar lojas, módulos contratados, cargos
e vínculos de tráfego, além de acessar permanentemente todas as configurações técnicas
no Revy Control; suas ações são auditadas.
_Avoid_: Dono da loja, gestor de tráfego

**Gestor de Tráfego**:
Usuário autorizado a operar aquisição e atribuição de uma ou mais lojas, podendo
pertencer à equipe Revy, atuar de forma independente ou representar uma agência.
_Avoid_: Dono da loja, administrador global

**Gestor Responsável**:
Gestor de tráfego que responde principalmente pela aquisição e pelas integrações de
uma loja; cada loja possui no máximo um responsável ativo.
_Avoid_: Dono da loja, gestor exclusivo

**Gestor Colaborador**:
Gestor de tráfego adicional autorizado a trabalhar em uma loja que já possui um
gestor responsável, sem autoridade para desconectar integrações.
_Avoid_: Usuário da loja, agência

**Parceiro de Tráfego**:
Profissional independente ou agência externa que presta gestão de tráfego para
lojas autorizadas.
_Avoid_: Cliente Revy, proprietário da loja

**Vínculo de Tráfego**:
Autorização explícita que permite a um gestor de tráfego acessar uma loja.
_Avoid_: Propriedade da loja, acesso global

**Dono da Loja**:
Usuário com responsabilidade comercial por uma loja; o mesmo usuário pode ser dono
de várias lojas independentes.
_Avoid_: Dono da organização, proprietário de todas as lojas

**Visão Consolidada**:
Leitura agregada das lojas em que o usuário atua como dono, sem unir dados,
configuração, contratação ou cobrança entre elas.
_Avoid_: Organização, fusão de lojas

**Status da Loja**:
Estado do relacionamento operacional da loja com a Revy: rascunho, em configuração,
pronta, ativa, suspensa ou encerrada.
_Avoid_: Status da organização, situação do usuário

**Loja Suspensa**:
Loja cuja operação e novos processamentos estão interrompidos, mantendo todo o
histórico preservado.
_Avoid_: Loja excluída, loja encerrada

**Loja Encerrada**:
Loja cujo relacionamento com a Revy foi finalizado, com o histórico preservado.
_Avoid_: Loja excluída, loja suspensa

**Estado Operacional Efetivo**:
Resultado mais restritivo entre o Status da Loja e o estado do Módulo Contratado,
usado para decidir se um novo efeito operacional pode ocorrer.
_Avoid_: Visibilidade do menu, situação da cobrança, status da integração

**Leitura Histórica**:
Consulta autorizada de fatos já registrados, permitida mesmo durante suspensão sem
reativar automações ou autorizar novas operações.
_Avoid_: Continuação da operação, replay automático

**Captura Passiva de Ingresso**:
Registro autenticado e deduplicado de um fato externo recebido durante suspensão,
sem criar atendimento, executar automação ou produzir saída externa.
_Avoid_: Atendimento ativo, descarte do webhook, replay automático

**Ativação da Loja**:
Confirmação do Admin Revy de que uma loja tecnicamente pronta pode iniciar sua
operação. Requisitos obrigatórios bloqueiam a ativação; alertas aceitos ficam auditados.
_Avoid_: Cadastro da loja, criação da loja, ativação automática

**Integração da Loja**:
Vínculo entre a Revy e uma conta externa que o gestor já está autorizado a acessar.
A Revy não cria a conta externa nem administra o acesso do gestor a ela.
_Avoid_: Login da loja, gestão de credenciais externas, conta criada pela Revy

**Configuração Estrutural da Loja**:
Definição de pessoas, cargos, módulos contratados, gestores, integrações técnicas e
canais da loja, administrada no Revy Control.
_Avoid_: Operação da equipe, atendimento, negociação

**Operação da Equipe**:
Distribuição e acompanhamento do trabalho comercial entre pessoas já vinculadas à
loja, realizada no Revy Loja sem criar contas ou alterar cargos estruturais.
_Avoid_: Cadastro estrutural de usuário, gestão de integração técnica

**Acesso Bancário**:
Credencial protegida de portal bancário usada pela Simulação Multibanco, administrada
somente por dono ou gerente dentro de Vendas no Revy Loja.
_Avoid_: Integração de tráfego, configuração do Revy Control, acesso do gestor de tráfego

**Integração Google Ads**:
Conexão técnica do Revy Control que lê aquisição e devolve eventos comerciais para
mensuração, sem criar, editar, pausar ou otimizar campanhas.
_Avoid_: Agência de tráfego, gerenciador de campanhas, configuração do Revy Loja

**Registro de Campanha**:
Representação interna de uma campanha externa usada para atribuição, gasto e resultado.
Não cria nem altera a campanha real na Meta, Google ou outra plataforma.
_Avoid_: Anúncio, campanha criada pela Revy, gerenciador de anúncios

**Número WhatsApp da Loja**:
Canal de WhatsApp vinculado permanentemente a uma única loja; uma loja pode possuir
vários números equivalentes, sem finalidade fixa e sem transferência entre lojas.
_Avoid_: Número do vendedor, número de um produto, número compartilhado ou transferível

**Estado do Número WhatsApp**:
Situação operacional de um número: pendente, conectado, desconectado ou inativo.
Números inativos preservam o histórico e não são apagados.
_Avoid_: Número excluído, situação da loja

**Provedor WhatsApp**:
Meio externo usado para conectar um número da loja à Revy; pode ser substituído sem
alterar a loja, a identidade do número ou seu histórico, com apenas um provedor ativo.
_Avoid_: Número WhatsApp, produto Revy, proprietário do número

**Revy Control**:
Aplicação administrativa e técnica usada por Admins Revy e gestores de tráfego para
controlar lojas, integrações e aquisição.
_Avoid_: Portal da loja, produto do vendedor

**Revy Loja**:
Aplicação operacional única usada por dono, gerente e vendedor, composta pelos módulos
contratados pela loja.
_Avoid_: Revy Control, conjunto de aplicativos separados

**Produto Revy**:
Solução comercial unificada entregue à loja por meio do Revy Loja, cuja contratação
pode combinar diferentes módulos.
_Avoid_: Cada recurso de IA, cada dashboard, cada integração

**Módulo Revy Loja**:
Área funcional habilitável dentro do Revy Loja. Existem somente dois módulos visíveis:
Vendas e Estoque.
_Avoid_: Aplicativo separado, feature isolada

**Módulo Vendas**:
Módulo do Revy Loja que centraliza a operação comercial em Visão geral e Atendimento.
Negociação, follow-ups, propostas, Simulação Multibanco, Chatbot e Seller AI ficam embutidos.
_Avoid_: Revy Sales, Revy Finance, aplicativo de IA separado

**Chatbot**:
Capacidade de Vendas que atende e qualifica o cliente pelo WhatsApp, solicita a Simulação
Multibanco e transfere a negociação ao vendedor.
_Avoid_: Concierge AI, produto separado, aprovador de financiamento

**Simulação Multibanco**:
Capacidade de Vendas que consulta vários bancos configurados para a mesma negociação e
compara os retornos. Condições definitivas e aprovação pertencem aos bancos.
_Avoid_: Revy Finance, módulo separado, aprovação da Revy

**Módulo Estoque**:
Módulo operacional do Revy Loja que reúne veículos, preços, fotos, disponibilidade e
catálogo público. Seus indicadores são determinísticos e não utilizam IA.
_Avoid_: Revy Inventory, Revy Catalog como aplicativo separado

**Capacidade Embutida**:
Recurso que amplia um módulo sem se tornar aplicação ou menu principal separado. No
desenho atual, Chatbot, Seller AI e Simulação Multibanco pertencem a Vendas.
_Avoid_: Produto independente, módulo obrigatório

**Módulo Contratado**:
Módulo Revy Loja habilitado para uma loja, com requisitos e estado próprios; sua
suspensão interrompe o funcionamento sem apagar os dados existentes.
_Avoid_: Produto global, aplicativo instalado, licença da organização

**Contrato da Loja**:
Relação comercial independente que define os módulos, capacidades opcionais, valores e
vigência de uma loja, sem agrupar contratos de outras lojas do mesmo dono.
_Avoid_: Contrato da organização, assinatura do usuário

**Situação da Cobrança**:
Registro administrativo da cobrança de uma loja, sem realizar o pagamento nem
suspender automaticamente sua operação.
_Avoid_: Sistema financeiro, pagamento automático, suspensão da loja
