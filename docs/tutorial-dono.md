# Manual do dono/gestor — Revy

Este guia explica como operar a loja no Revy do primeiro acesso ao acompanhamento de resultado. O sistema une estoque, catálogo, WhatsApp, leads, simulações, vendas, metas e medição de tráfego.

**Versão deste manual:** 21/07/2026, conferida com as telas e permissões atuais do projeto.

> **Em uma frase:** o Ads Manager cria e veicula anúncios; o Revy liga o link do anúncio ao lead, à venda e ao retorno financeiro. O WhatsApp gera oportunidade; o vendedor conclui o atendimento; o Portal registra o que realmente aconteceu.

### Termos importantes, sem complicação

| Termo | Explicação simples |
|---|---|
| **Lead** | Pessoa que demonstrou interesse. Lead não é venda. |
| **Funil** | Caminho do lead desde a entrada até a venda ou perda. |
| **UTM** | Etiqueta colocada no link para identificar a origem e a campanha do acesso. |
| **Pixel** | Código da Meta carregado no navegador do Catálogo para medir visita e clique. |
| **CAPI** | Envio de conversões do servidor do Revy para a Meta. No projeto atual, confirmações de venda podem gerar **Purchase**. |
| **ROI/ROAS** | Indicadores de retorno. No painel de tráfego, o principal é o ROAS: faturamento atribuído dividido pelo gasto de mídia. |
| **Handoff** | Transferência do atendimento do bot para uma pessoa. |

## 1. Visão do fluxo completo

~~~text
Anúncio ou catálogo com UTM
          ↓
Cliente clica e chama no WhatsApp
          ↓
Bot registra lead e coleta informações
          ↓
Vendedor assume → atualiza lead → simula
          ↓
Venda é registrada e confirmada
          ↓
Revy mostra funil, faturamento, metas e ROI
~~~

Para o resultado ser confiável, as quatro pontas precisam estar preenchidas: link com UTM, lead, venda vinculada ao lead e gasto lançado.

### O que cada serviço faz

| Serviço | Para que serve | O que a equipe percebe |
|---|---|---|
| **Portal de Gestão** | Reúne telas, permissões, vendas, metas, campanhas, financeiro e relatórios. | É o painel usado por dono, gerente e vendedor. |
| **Estoque** | Guarda veículos, preço, custo, status e publicação. | Alimenta o Portal e o Catálogo. |
| **Catálogo público** | Mostra ao cliente os veículos publicados e leva ao WhatsApp. | É a vitrine usada no link do anúncio. |
| **Chatbot/WhatsApp** | Registra conversas, leads, origem e handoff. | Atende a primeira mensagem e entrega o contato ao vendedor. |
| **Motor de Simulação** | Consulta as financeiras configuradas. | Retorna opções de parcela ou um erro de consulta. |
| **Meta Pixel/CAPI** | Mede eventos do Catálogo e envia conversões configuradas. | Ajuda a conferir e otimizar o tráfego na Meta. |

### Ordem segura para configurar uma loja nova

1. Abra **Ajustes** e confira se Estoque, Chatbot e Motor aparecem como configurados.
2. Cadastre os usuários em **Equipe**.
3. Cadastre e publique pelo menos um veículo em **Estoque**.
4. Autorize, se necessário, os telefones de cadastro em **Números de cadastro**.
5. Cadastre e teste as credenciais em **Acessos dos bancos**.
6. Configure Pixel e CAPI em **Tráfego**.
7. Crie a campanha no Revy e copie a UTM para o link do anúncio.
8. Faça o teste completo descrito na seção **Teste antes de investir**.

## 2. Primeiro acesso e controle da equipe

1. Entre no Portal com o usuário de **dono**.
2. Em **Equipe → Adicionar membro**, cadastre cada pessoa com nome, e-mail, papel e uma senha inicial de pelo menos 10 caracteres.
3. Entregue a senha inicial por um canal privado. O dono pode usar **Redefinir senha** quando necessário; não compartilhe a mesma conta entre funcionários.

| Papel | Pode fazer | Não pode fazer |
|---|---|---|
| **Dono** | Tudo: equipe, estoque, vendas, custos, financeiro, metas, bancos, tráfego, campanhas, ROI e relatórios. | — |
| **Gerente** | Estoque, vendas, confirmação, custos, metas, bancos, tráfego, campanhas, ROI e relatórios. | Criar ou manter equipe. |
| **Vendedor** | Leads/conversas permitidas, consultar estoque sem custo, registrar venda, simular e ver o próprio painel/metas aplicáveis. | Ver custos/lucro, confirmar venda, alterar tráfego, campanhas, bancos ou equipe. |

O e-mail do membro não pode ser alterado depois do cadastro, pois identifica vendas e metas. Revise usuários quando alguém entrar, mudar de função ou sair da loja. Use **Desativar** para bloquear o acesso sem apagar o histórico; não é possível desativar a própria conta.

### Mapa do menu do dono

| Grupo | Telas |
|---|---|
| **Dia a dia** | Visão geral, Leads, Conversas, Estoque, Vendas e Simulações. |
| **Gestão** | Funil, Financeiro, Relatórios, Tráfego, Campanhas, ROI e Metas. |
| **Configurações** | Acessos dos bancos, Números de cadastro, Equipe e Ajustes. |

No celular, toque em **Menu** para abrir a barra lateral. O botão **Simular** inicia uma simulação; o botão **+ Veículo** abre o cadastro de estoque. Use o ícone de tema para alternar claro/escuro e **Sair** ao encerrar uma sessão em aparelho compartilhado.

## 3. Estoque e catálogo: a base de tudo

O **Estoque** é a fonte oficial dos veículos. O Catálogo mostra apenas o que foi publicado pelo estoque.

### Cadastrar um veículo pelo Portal

1. Clique em **+ Veículo** ou em **Estoque → Cadastrar veículo**.
2. Informe tipo, marca, modelo, versão, ano/modelo, cor e placa quando houver.
3. Informe preço, quilometragem e código interno.
4. Informe o custo do veículo. Ele não aparece ao vendedor, mas é necessário para o lucro bruto ficar completo.
5. Se já houver uma imagem pública, informe a **URL da foto**. Para enviar uma galeria, use o fluxo de WhatsApp autorizado.
6. Quando estiver pronto para divulgar, clique em **Publicar no catálogo**.

Antes de salvar, confira especialmente placa, preço e custo. A placa identifica o veículo no fluxo de fotos; o preço aparece para a equipe e para o cliente; o custo alimenta o lucro bruto.

| Ação | Efeito |
|---|---|
| **Publicar no catálogo** | Deixa um veículo disponível visível na vitrine pública. |
| **Despublicar** | Retira o veículo do catálogo, sem apagar o cadastro. |
| **Reservar** | Sinaliza negociação em andamento; a equipe não deve prometer disponibilidade. |
| **Marcar vendido** | Baixa o veículo e o remove do catálogo. Use com cuidado. |

O caminho mais seguro ao fechar é: vendedor registra a venda com veículo e lead → dono/gerente confirma a venda. Assim estoque, financeiro, funil e tráfego recebem o mesmo resultado.

**Publicado** e **disponível** não são a mesma coisa. Publicação controla a vitrine; status controla a situação comercial. Um veículo só pode ser publicado quando está disponível.

### Fotos e cadastro pelo WhatsApp

Em **Números de cadastro**, adicione somente telefones da equipe que podem cadastrar veículo ou mandar fotos. O número precisa estar salvo na agenda da loja.

O operador autorizado envia **cadastro** ou **menu** e escolhe a opção:
1 cadastrar, 2 ver estoque, 3 editar (preço/km/cor), 4 despublicar, 5 marcar vendido, 0 sair.
No cadastro, envia os dados em uma mensagem, manda as fotos e pode voltar ao menu. Para anexar foto a veículo já existente, use a placa na legenda. Remova imediatamente o número de quem não faz mais parte da equipe. Nunca autorize clientes nesse recurso.

## 4. WhatsApp, bot e atendimento humano

O bot atende contatos não salvos, consulta estoque, registra lead e pode coletar dados para simulação. Ele **não informa automaticamente** parcelas, taxas ou banco ao cliente. Quando o vendedor entra, o atendimento vira humano.

O que é automático: registrar conversa/lead, conservar a origem recebida e responder conforme o fluxo configurado. O que depende da equipe: assumir no momento certo, atualizar a etapa, fazer a simulação, negociar e registrar a venda.

### Conferência diária

1. Abra **Conversas** e verifique atendimentos com **Bot ativo** e **Atendimento humano**.
2. Confirme que os vendedores assumiram rapidamente os contatos com intenção de compra.
3. Abra **Leads** e revise etapas paradas ou sem responsável.
4. Em **Funil**, acompanhe taxa de resposta, conversão e tempo de atendimento da coorte selecionada.

Se um vendedor mandar mensagem manual pelo WhatsApp, o bot pode pausar automaticamente naquele contato. A tela da conversa permite assumir e devolver o bot de forma explícita.

A ficha do lead mostra interesse, etapa, origem, primeira campanha (**first touch**) e última campanha (**last touch**). Essas informações não devem ser alteradas para “consertar” relatórios: elas registram o caminho real do cliente.

Padronize com a equipe o significado das etapas: **Novo**, **Em atendimento**, **Qualificado**, **Convertido** e **Perdido**. Converter a etapa não substitui registrar e confirmar a venda.

## 5. Financeiras e simulações

Em **Acessos dos bancos**, cadastre ou atualize os usuários e senhas dos portais de cada financeira. As senhas ficam cifradas no Motor de Simulação e não voltam em texto para a tela.

1. Atualize a credencial da financeira quando houver troca de senha.
2. Use **Testar login** após salvar para verificar a saúde do acesso.
3. Se houver falha recorrente, não peça ao vendedor para compartilhar senha: corrija o acesso nesta tela ou com o responsável técnico.

Vendedor, gerente e dono podem solicitar simulações conforme os bancos configurados. Revise o **Histórico de simulações** e os **Registros e prints** somente para tratar resultado, erro ou auditoria. A aprovação e a condição final são sempre da financeira.

Na simulação manual, a equipe escolhe os bancos e informa: CPF, nascimento, celular, CNH, categoria do veículo, placa, UF, finalidade comum/PCD, valor, zero km, entrada e prazos. Os prazos são separados por vírgula, por exemplo `12,24,36,48`. Consultar um banco por vez reduz tempo de espera e carga quando não for necessário comparar todos.

Dono e gerente podem filtrar o histórico entre **Só minhas** e **Toda a loja**. Os prints podem conter dados pessoais do portal bancário; abra apenas quando necessário e nunca envie para grupos.

## 6. Vendas, confirmação, financeiro e metas

O vendedor registra a venda, mas ela nasce como **registrada**. Dono ou gerente confirma.

### Conferir e confirmar uma venda

1. Abra **Vendas** e localize o registro pendente.
2. Confira descrição, preço final, veículo e, principalmente, o **lead vinculado**.
3. Confira o custo do veículo e, se houver, um custo direto nas categorias documentação, frete, comissão ou outros.
4. Clique em **Confirmar** somente depois da condição comercial definida pela loja.
5. Verifique se o veículo foi baixado do estoque e se a venda aparece no período correto.

Vincular o lead é essencial: sem ele, a venda pode entrar no financeiro, mas não será atribuída corretamente ao funil e à campanha.

Em **Financeiro**, escolha o período. A tela mostra apenas vendas confirmadas:

- **Vendas confirmadas:** quantidade real no período.
- **Faturamento:** soma dos preços de venda.
- **Lucro bruto:** preço de venda menos custo do veículo e custos diretos.

Se o lucro aparecer como **Incompleto**, há venda confirmada sem custo de veículo. Complete o dado antes de tomar decisões de margem.

Ao cancelar uma venda já confirmada, o registro comercial é cancelado, mas o veículo continua como vendido no Estoque por segurança. Se o negócio realmente voltou atrás, faça a correção de inventário de forma consciente; não confirme nem baixe o mesmo veículo duas vezes.

Em **Metas → Cadastrar meta**, defina escopo (loja ou vendedor), tipo, período e alvo. Há metas de quantidade, faturamento e lucro bruto. Não sobreponha metas iguais para o mesmo escopo/período; compare metas apenas com vendas confirmadas.

## 7. Tráfego pago: configuração inicial

Faça esta configuração uma vez por loja e revise quando trocar Pixel ou conta Meta. No Portal atual, o primeiro salvamento exige **Pixel ID e token CAPI**.

1. No Meta Events Manager, obtenha o **Pixel ID** e crie o **access token** da CAPI.
2. No Portal, abra **Tráfego**.
3. Cole o Pixel ID, o token CAPI e, apenas em teste, o **Test Event Code**.
4. Marque os eventos desejados: **PageView**, **Lead** e **Purchase**.
5. Salve.
6. Pronto: o **Catálogo puxa o Pixel ID sozinho** do Portal (por loja). Não precisa de secret no servidor. O Pixel é público e roda no navegador; o token CAPI fica somente no Portal, cifrado.

O **Test Event Code** serve somente para validação no Events Manager. Use durante o teste e retire depois, para não continuar marcando eventos reais como eventos de teste.

| Evento | Quando acontece |
|---|---|
| **PageView** | O cliente abre uma página do Catálogo no navegador. |
| **Lead** | O cliente usa o botão de WhatsApp no Catálogo. |
| **Purchase** | Uma venda é confirmada no Portal e o envio CAPI está habilitado. |

Depois, acompanhe o bloco **Status**:

- **Token CAPI: Configurado** confirma que o Portal guardou o token, sem exibi-lo;
- **Último Purchase** mostra se uma venda confirmada foi entregue, está pendente ou falhou;
- se houver pendências, use **Retentar envios** depois de revisar a configuração.

> O Revy não cria, publica, pausa ou cobra anúncios. Essas ações continuam no Meta Ads Manager, Google Ads, TikTok Ads ou plataforma escolhida.

Se o gerenciador de anúncios mudar de aparência, procure no anúncio o campo de **URL do site/destino**. É nesse endereço que deve entrar o link do Catálogo com UTM. Não use um destino diferente e direto para o WhatsApp se quiser preservar a atribuição criada pelo Catálogo.

## 8. Criar campanha e link rastreável

Antes de publicar qualquer anúncio, cadastre a campanha no Revy.

1. Entre em **Campanhas → Nova campanha**.
2. Dê um nome interno fácil de reconhecer, por exemplo **Seminovos Meta Julho**.
3. Escolha o canal, status e o período (opcional).
4. Preencha **utm_source**, **utm_medium** e, obrigatoriamente, **utm_campaign**.
5. Use nomes curtos, sem espaços e consistentes, por exemplo:

~~~text
utm_source=instagram
utm_medium=paid
utm_campaign=seminovos-julho
~~~

6. Salve e abra o detalhe da campanha.
7. Copie o trecho de link exibido em **Link com atribuição** e acrescente-o à URL do veículo publicado no catálogo.

Exemplo completo:

~~~text
https://SEU-CATALOGO/l/sua-loja/veiculos/ID-DO-VEICULO?utm_source=instagram&utm_medium=paid&utm_campaign=seminovos-julho
~~~

O significado dos campos:

| Campo | Exemplo | Uso |
|---|---|---|
| **Nome** | Seminovos Meta Julho | Identificação legível dentro do Portal. |
| **Canal** | Meta (Instagram/Facebook) | Plataforma ou origem geral. |
| **Status** | Ativa, Pausada ou Encerrada | Organização interna; não pausa o anúncio na plataforma. |
| **utm_source** | instagram | Fonte do acesso. |
| **utm_medium** | paid | Tipo de mídia. |
| **utm_campaign** | seminovos-julho | Chave principal que liga lead, venda e campanha. |
| **utm_content** | video-cg-vermelha | Opcional; diferencia anúncio/criativo. |
| **utm_term** | moto-financiada | Opcional; palavra ou segmentação. |

O valor de **utm_campaign** do anúncio deve ser idêntico ao cadastrado no Revy. Se houver diferença como **jul-2026** de um lado e **julho-2026** do outro, o lead ficará sem campanha e o ROI será incompleto.

## 9. Lançar o gasto da campanha

O Revy não importa gasto automaticamente neste momento. Copie o valor que o Ads Manager mostra e registre no Portal.

Você pode:

1. Abrir a campanha e usar **Lançar gasto** para inserir valor, data de referência e nota; ou
2. Abrir **Campanhas → Lançar gastos** para informar várias campanhas; ou
3. Baixar o modelo CSV do Revy, preenchê-lo e importá-lo na tela de gastos em lote.

O arquivo CSV não cria campanhas automaticamente: cadastre a campanha antes. Sem gasto registrado, leads e vendas podem aparecer, mas CPL, CPA e ROAS ficam em **—**.

No lançamento em lote, valor vazio pula aquela campanha. No CSV, use as colunas `utm_campaign;valor;referencia;nota`. Confira o histórico antes de lançar de novo: duplicar a mesma semana infla gasto, CPL e CPA e reduz o ROAS.

## 10. Ler ROI sem se enganar

Abra **ROI**, defina o período e escolha a atribuição:

| Indicador | Cálculo | Leitura simples |
|---|---|---|
| **CPL** | gasto ÷ leads atribuídos | quanto custou gerar um interessado rastreado. |
| **CPA** | gasto ÷ vendas atribuídas | quanto custou adquirir uma venda rastreada. |
| **ROAS** | faturamento atribuído ÷ gasto | retorno em receita; 5x significa R$ 5 faturados para cada R$ 1 de mídia. |
| **First touch** | primeira UTM do lead | crédito para a primeira campanha conhecida. |
| **Last touch** | última UTM do lead | crédito para o último contato/caminho conhecido; é o padrão. |

O painel mostra gasto, leads, vendas, faturamento e ROAS por campanha. Clique em uma campanha para ver gastos, funil atribuído, últimas vendas e o link com UTM.

ROAS usa **faturamento**, não lucro. Uma campanha pode ter ROAS alto e margem ruim se o custo do veículo, comissão ou outros custos forem altos. Leia o ROI junto com o painel **Financeiro**.

### Como decidir

1. Compare campanhas no mesmo período e com gasto lançado.
2. Veja primeiro se há leads; depois se os leads viram atendimento; por fim, se viram vendas.
3. Não pause campanha só porque o ROAS está **—**: isso normalmente significa gasto ausente, não venda zero.
4. Investigue campanha com muitos leads e poucas vendas: oferta, qualidade do atendimento, estoque e velocidade de resposta podem ser a causa.
5. Use o ROI como atribuição declarada, não como prova absoluta de causalidade. Um cliente pode ter visto mais de um canal antes de comprar.

## 11. Funil, visão geral e relatórios

### Visão geral

Use a **Visão geral** para revisar estoque, integração e o resumo operacional. O bloco de resultados do dono reúne gasto, leads, motos vendidas, ROAS, canais e alertas de medição.

### Funil

Em **Funil**, o período selecionado cria uma coorte: os leads que entraram naquele intervalo. A tela mostra resposta, etapas, conversão e tempos médios/medianos. “Sem base” significa que não há dados suficientes; não trate como zero.

### Relatórios

Em **Relatórios**, escolha o período e baixe CSVs de vendas confirmadas, metas e funil. Os filtros de vendedor e origem afetam apenas o CSV de funil. Para exportar o ROI, abra **ROI**, escolha período e first/last touch e clique em **Exportar CSV**. Os totais de vendas e metas devem bater com o Financeiro no mesmo período.

### Ajustes e saúde dos serviços

Em **Ajustes**, o dono confere os dados da conta e se Estoque, Chatbot, Motor e Meta/CAPI foram configurados. **Configurado** significa que o endereço/token existe no servidor; não garante sozinho que o serviço respondeu agora. Para validar de verdade, abra a tela correspondente e faça um teste funcional.

## 12. Teste antes de investir em anúncios

1. Abra o veículo publicado usando exatamente o link com UTM do anúncio.
2. Confirme que o Catálogo abriu o veículo correto.
3. Clique no botão de WhatsApp e envie uma mensagem de teste com um telefone que não seja da equipe.
4. Confira em **Conversas** e **Leads** se o contato apareceu.
5. Abra o lead e confirme se **First campaign** e **Last campaign** mostram o `utm_campaign` esperado.
6. Assuma a conversa pelo Portal para testar o handoff.
7. Registre venda de teste somente com procedimento controlado, para não misturar números reais nem baixar um veículo real.
8. No Events Manager, confirme PageView/Lead e, quando aplicável, Purchase.
9. Retire o **Test Event Code** e cancele os registros de teste conforme a regra da loja, preservando o estoque correto.
10. Lance o gasto real somente quando a campanha começar a veicular.

Se qualquer elo falhar, corrija antes de aumentar o orçamento. Um anúncio pode gerar mensagens mesmo com a medição quebrada.

## 13. Rotina recomendada

| Frequência | Rotina |
|---|---|
| Todos os dias | Conferir conversas, leads sem avanço, estoque reservado, vendas registradas e status do WhatsApp. |
| Semanalmente | Confirmar vendas, completar custos, revisar metas, lançar gastos sem duplicar valores, comparar funil e ROI. |
| Mensalmente | Exportar relatórios, fechar resultado, ajustar orçamento no Ads Manager e desativar campanhas encerradas. |
| Quando houver mudança | Revisar equipe, números autorizados, senha dos bancos, Pixel/CAPI e permissões. |

## 14. Diagnóstico rápido

| Sintoma | Causa mais provável | Próxima ação |
|---|---|---|
| Ads mostra mensagens, mas o Portal tem poucos leads | Link sem UTM, CTA direto no WhatsApp ou bot indisponível. | Teste o link publicado e revise a configuração do canal. |
| Lead aparece sem campanha | **utm_campaign** não bate com a campanha cadastrada. | Corrija o link do anúncio; não altere artificialmente o lead antigo. |
| Venda não entra no ROI | Venda sem lead vinculado, sem confirmação ou lead sem match de campanha. | Revise o registro da venda e o lead relacionado. |
| ROAS/CPL/CPA em **—** | Não há gasto lançado no período (ou não há base). | Lance o gasto e mantenha o período coerente. |
| Lucro incompleto | Há custo do veículo faltando. | Complete custo e custos diretos da venda. |
| Purchase pendente/falhou | Token, Pixel ou conexão Meta precisa de revisão. | Confira Tráfego e use **Retentar envios** quando corrigido. |
| Bot não responde | Workflow/canal pode estar parado ou o contato já está em atendimento humano. | Verifique Conversas, conexão do WhatsApp e o responsável técnico. |
| Serviço aparece configurado, mas a tela falha | A configuração existe, porém o serviço pode estar indisponível. | Teste a tela específica e informe ao suporte o horário e a mensagem do erro. |
| Simulação falha em um banco | Credencial vencida, portal alterado ou dado incompatível. | Em **Acessos dos bancos**, confira a saúde e use **Testar login**; tente outro banco sem inventar condição. |
| Gasto ficou maior do que no Ads Manager | O mesmo período pode ter sido lançado duas vezes. | Confira o histórico da campanha e padronize uma única frequência de lançamento. |

## 15. Segurança e LGPD

- Dê a cada pessoa um usuário individual; nunca use uma conta coletiva.
- Não envie CPF, nascimento, senhas bancárias ou token CAPI em grupos ou planilhas sem controle.
- O token CAPI e credenciais bancárias devem ser cadastrados somente nas telas próprias; o Revy os armazena cifrados e não os revela depois.
- Autorize para cadastro via WhatsApp apenas telefones de funcionários ativos e remova quem sair.
- Trate os dados dos clientes apenas para atendimento, venda e simulação necessários. Para solicitação administrativa de dados, siga o processo definido pela loja.

## 16. Checklist de fechamento do dono

- [ ] Usuários e números autorizados pertencem somente à equipe ativa.
- [ ] Veículos vendidos não estão publicados e reservas antigas foram revisadas.
- [ ] Vendas reais estão confirmadas com veículo e lead corretos.
- [ ] Custos dos veículos e custos diretos foram preenchidos.
- [ ] Gastos de mídia foram lançados uma única vez no período correto.
- [ ] Campanhas usam o mesmo `utm_campaign` do anúncio.
- [ ] Purchase não está pendente ou falhando em **Tráfego**.
- [ ] Funil, Financeiro e ROI foram analisados no mesmo intervalo de datas.
- [ ] Relatórios necessários foram exportados.
- [ ] Senhas, CPF e tokens não foram expostos fora das telas próprias.
