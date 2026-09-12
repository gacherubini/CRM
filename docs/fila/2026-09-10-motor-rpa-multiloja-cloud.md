# Motor RPA multiloja em cloud: hipóteses e alternativas

**Produto:** Motor de Simulação, `motor-simulacao/`.
**Atualizado em:** 11/09/2026.
**Status:** pesquisa e proposta arquitetural. Implementação, fornecedor, contratação e
piloto ainda não aprovados. O diagnóstico e a correção do Bradesco estão com outro agente.

## 1. Recomendação 100% cloud

**A melhor relação entre custo, isolamento do teste e trabalho operacional é manter o
worker on-demand no Fly e testar um ISP estático cloud para uma loja. Primeiro, a mesma
imagem roda no Fly atual com egress estático como controle. Se o Bradesco continuar sem
concluir, troca-se somente a saída para o ISP. Não comprar seis IPs antes desse teste.**

Hoje a operação tem **uma loja**. O desenho imediato atende essa loja e mede seu volume.
Os números de seis lojas são apenas uma projeção de expansão, não capacidade que precisa
ser contratada ou implementada agora.

O egress estático direto tem baixa chance de resolver o Bradesco: muda o endereço, mas
continua na rede de datacenter do Fly, onde ele nunca concluiu. O ISP cloud é a melhor
aposta porque muda a classe/ASN da saída sem trocar o browser, a imagem e o modelo
on-demand ao mesmo tempo. Ainda é hipótese; só o piloto cloud decide.

O Motor central mantém API, fila, credenciais e resultados. Os executores continuam
sendo parte do produto Motor, mas recebem apenas tarefas e segredos da própria loja.

```text
Motor central no Fly
  ├─ executor da loja A → ISP cloud fixo A → bancos
  └─ executor da loja B → ISP cloud fixo B → bancos

Cada executor: sessão própria, até 2 browsers, credenciais só da sua loja.
Saída: egress estático do Fly no controle; ISP brasileiro dedicado no teste seguinte.
```

A saída de rede, também chamada de *egress*, é o endereço que o banco vê quando o
browser acessa o portal. Ela pode ser contratada separadamente de onde o browser roda.
Por isso, **um IP por loja não exige uma VPS comprada por loja**.

A preferência pelo Fly aproveita a operação existente. Não há evidência de que trocar
para uma VPS resolveria o acesso bancário. Uma VPS continua sendo alternativa de
computação e isolamento caso custo, capacidade ou operação a justifiquem.

### Ordem de decisão

1. O outro agente corrige e verifica lease, tentativas limitadas e resultado terminal.
2. Rodar uma loja no Fly atual, com a mesma imagem/configuração e egress estático.
   Medir sessão fria e quente separadamente.
3. Se o Bradesco continuar sem concluir, usar a mesma imagem/configuração com um único
   ISP cloud por 24 h, após KYC e liberação escrita dos domínios.
4. Comparar saída direta e ISP por banco. Só expandir de uma para seis lojas se o ISP
   concluir o Bradesco e não regredir os demais.
5. Adotar APIs oficiais gradualmente nos bancos em que houver habilitação comercial.

Todo teste e toda produção deste card rodam em cloud. Não usar PC residencial nem máquina
da loja como executor ou controle. A API pública `/v1/simulacoes` permanece compatível.
O Motrix participa da solução; sua capacidade produtiva depende da validação e do rollout.

## 2. Ranking técnico e custo-benefício

| Opção | Chance técnica | Custo-benefício | Evidência em uma frase |
|---|---|---|---|
| **1. Fly on-demand + IPRoyal ISP** | **Melhor aposta** | **Melhor** | Mantém runtime conhecido e troca apenas a saída para IP ISP brasileiro dedicado; Bradesco ainda não foi provado nessa combinação |
| **2. Browserbase + IPRoyal ISP externo** | **Plausível, mas não provada** | **Médio** | Aceita proxy externo e Context persistente, mas muda também o browser gerenciado e custa mais que Fly no volume de referência |
| **3. Browserless + IPRoyal ISP externo** | **Plausível, mas não provada** | **Baixo em seis lojas** | Aceita proxy externo sem unidades adicionais, porém o plano para 12 browsers custa US$ 140/mês no anual antes do ISP |
| **4. Lightsail por loja + IPRoyal ISP** | **Plausível, mas não provada** | **Baixo** | O ISP pode resolver a rede, mas a VPS não acrescenta vantagem sobre Fly + ISP e fica ligada sem nova orquestração on-demand |
| Fly on-demand + egress estático | **Baixa chance de resolver Bradesco** | **Bom como controle** | Bradesco nunca concluiu no Fly; fixar um IP do mesmo ambiente de datacenter não corrige a classe/ASN da saída |
| Lightsail direto, compartilhado ou por loja | **Baixa chance de resolver Bradesco** | **Médio a baixo** | Troca o ASN de cloud, mas continua em IP de datacenter e custa mais para testar a hipótese de rede |
| API oficial + Playwright nos bancos restantes | **Melhor aposta quando houver contrato** | **Potencialmente melhor** | Remove RPA dos bancos habilitados, mas não há acesso comercial confirmado para todos |
| ProxyEmpire | **Incompatível até autorização escrita** | **Não comparar no ranking** | Os termos permitem suspender automação, apesar do produto anunciá-la, e os preços oficiais divergem |
| Oxylabs ISP de autosserviço | **Incompatível com a exclusividade exigida** | **Baixo** | O plano público compartilha IP com até três usuários e restringe bancos antes de aprovação |
| Bright Data | **Incompatível** | **Nenhum** | A política proíbe informação não pública atrás de login |
| PC residencial ou da loja | **Incompatível com a direção do dono** | **Fora do escopo** | Não é cloud; não entra em piloto nem produção |
| Proxy rotativo | **Incompatível** | **Nenhum** | Troca a identidade de rede entre sessões e não entrega IP exclusivo por loja |

A recomendação cloud não significa deixar todos os tenants no mesmo processo.
Machines/VMs separadas são uma forma de isolar executores. Compartilhar hosts físicos
exige cotas de CPU/RAM e uma fronteira de segurança adequada; contexto de browser sozinho
não protege as credenciais de outra loja contra comprometimento do executor.

## 3. O que sabemos e o que ainda é hipótese

### Quatro questões diferentes

| Questão | Evidência disponível | Consequência |
|---|---|---|
| Capacidade multiloja | Código usa fila e teto globais, com reserva por banco | Precisa de cotas e seleção de tarefas por loja |
| Loop do Bradesco | Outro agente relatou expiração de lease e descarte do resultado | Correção de software vem antes da avaliação de infraestrutura |
| Aceitação da rede pelo banco | Bradesco passou em rede residencial e nunca concluiu no Fly | Sustenta testar outra saída cloud, mas não prova que qualquer ISP será aceito |
| Sessão quente do Bradesco em cloud | O driver só salva `storage_state` depois de receber ofertas; esse ponto nunca foi atingido no Fly | Não atribuir ao modo quente um benefício ainda não observado nesse banco |

### Diagnóstico recebido do outro agente

Segundo o relato colado pelo dono em 10/09, o Bradesco conclui login e preenchimento,
fica em "Analisando dados..." e devolve `ofertas_demoraram` após 240 s. O lease de
300 s expira durante a execução com tentativas; a tarefa volta à fila e o resultado
é descartado por token antigo. O relato cita reinícios às 13:46, 13:56 e 14:01 UTC.

Esses eventos e logs não foram reconferidos por este agente de pesquisa. O dono deixou
diagnóstico e correção com outro agente. **Migrar o mesmo defeito para uma VPS não o
corrige.** Aumentar lease pode ser mitigação calculada sobre o tempo total; heartbeat
e recuperação de execução continuam necessários no desenho distribuído.

A causa da espera no portal permanece aberta. Sucesso residencial em 04/09 versus
falha cloud em 10/09 não isola a variável IP. O texto da tela também não identifica,
por si só, qual serviço interno do banco está esperando.

O reCAPTCHA considera sinais de IP, navegador e TLS. Sessão persistente reduz a
necessidade de login, mas não há garantia de que fará o score subir.
[Google, avaliação de acessos web](https://docs.cloud.google.com/recaptcha/docs/create-assessment-website).

A sessão quente está ligada por padrão. O estado é separado por cliente/provedor e
carregado no browser, mas cookies e tokens podem expirar ou ser invalidados pelo portal.
O banco também pode vincular a sessão ao IP, ASN ou localização. Portanto, sessão quente
não corrige reputação de rede, e trocar a saída pode invalidar o estado salvo. No piloto,
sessão fria e quente são séries distintas; não misturar seus resultados.

### O que outras empresas demonstram

A UiPath documenta saída estática para permitir integração com sistemas que aceitam
IPs cadastrados. É um padrão real de RPA cloud, sem comprovar acesso aos bancos da Revy.
[UiPath, outbound IP ranges](https://docs.uipath.com/orchestrator/automation-cloud/latest/user-guide/outbound-ip-ranges).

O caso Ramp usa browsers gerenciados para recibos em portais de comerciantes e compras
corporativas. É uso real em uma fintech, sem ser teste de login bancário brasileiro.
[Caso Ramp](https://www.browserbase.com/blog/case-study-ramp).

**Não encontramos nas fontes primárias consultadas uma operação equivalente que
comprove os seis portais funcionando continuamente com um fornecedor específico.**

## 4. Como escolher a saída de rede

### Opção A: IP estático do Fly

O Fly oferece egress estático por app e região a US$ 3,60/mês por par IPv4/IPv6.
O endereço persiste entre deploys e recriação de Machines. Isso é diferente do IP
público usado para receber chamadas na API.

Para afinidade por loja, avaliar um app por loja com um par de saída na região usada.
Alocar vários IPs ao mesmo app/região não faz esse roteamento: as Machines escolhem
entre os pares e não há seleção explícita por Machine nesse modelo. A aplicação de
egress pode ter atraso; conferir a saída real antes de habilitar tarefas.
[Fly, egress IPs](https://fly.io/docs/networking/egress-ips/).

IP fixo não remove uma restrição à faixa/ASN do provedor. IPs diferentes do mesmo
fornecedor também não isolam uma restrição aplicada ao ASN inteiro.

### Opção B: ISP brasileiro estático e exclusivo

O browser permanece no Fly e acessa os portais por um proxy contratado. Playwright
suporta proxy por browser ou contexto; essa configuração ainda precisa ser integrada
ao Motor. [Playwright, proxy](https://playwright.dev/python/docs/network#http-proxy).

A configuração futura deve manter a saída por loja, impedir fallback direto silencioso
se o proxy falhar e validar TLS até o banco, sem CA de interceptação do fornecedor.
O proxy vê metadados de rede; um serviço que hospeda o browser também processa o
conteúdo da sessão. São decisões diferentes sobre acesso de terceiros aos dados.

Um produto chamado ISP pode ser hospedado em datacenter e usar endereço registrado
em um provedor de internet. A categoria comercial não garante tratamento igual ao
de uma conexão doméstica. [Definição da Oxylabs](https://oxylabs.io/pricing/isp-proxies).

### Fornecedores pesquisados

Condições consultadas em 11/09/2026. Cobertura anunciada não equivale a estoque
contratável nem a aceitação pelos bancos.

| Fornecedor | Evidência útil | O que impede escolher agora |
|---|---|---|
| IPRoyal ISP | Publica Brasil, IP dedicado durante a assinatura, plano de 24 h e 30 dias; banco libera somente após verificação de identidade | Confirmar por escrito os seis domínios, estoque/ASN brasileiro, manutenção na renovação, preço final e acesso após KYC |
| ProxyEmpire static residential | Publica Brasil, IP exclusivo durante a assinatura, tráfego sujeito a soft cap de 100 GB/IP e planos mensais | Termos permitem suspender uso automatizado e negar domínios financeiros; páginas oficiais divergem sobre preço e cobrança de tráfego |
| Oxylabs ISP | Publica plano mínimo de 10 IPs por US$ 16/mês, tráfego sujeito a uso justo e consulta pré-compra para bancos | Autosserviço compartilha IP com até três usuários e a página de preço não confirma Brasil; não atende exclusividade comprovada |
| Bright Data | Tem rede residencial, mas sua política oficial proíbe coletar informação não pública, inclusive atrás de login | Incompatível com os portais autenticados deste card; retirar da seleção |
| Browserbase | Contexts persistentes, 200+ países e proxy externo | Proxy integrado declara acesso bancário menos confiável e variável por fornecedor; browser e proxy continuam sem IP exclusivo comprovado |
| Browserless | Playwright, estado persistente e proxy externo | Proxy próprio é sticky só durante a sessão; não comprova IP exclusivo permanente nem liberação dos bancos |

**IPRoyal é o primeiro candidato para confirmação comercial se precisarmos testar ISP.**
Sua página lista Brasil e preços iniciais de US$ 1,80/IP por 24 horas e US$ 2,70/IP
por 30 dias, sem cotação específica para IP brasileiro ou este uso. A ajuda informa
que bancos são bloqueados por padrão e exige verificação de identidade para acesso.
O guia informa 100 GB/mês/IP antes da redução de velocidade e permite manter o IP
ao estender a assinatura, desde que o endereço específico seja renovado.
[Produto ISP](https://iproyal.com/isp-proxies/),
[restrições bancárias](https://help.iproyal.com/en/articles/7222117-are-there-any-blocked-sites-or-ports-on-isp-proxies),
[preços](https://iproyal.com/pricing/static-residential-proxies/),
[franquia](https://iproyal.com/quick-start-guides/static-residential-proxies/).

**ProxyEmpire fica fora do ranking e pendente de autorização escrita.** A página do
produto publica Brasil entre os países disponíveis, IP exclusivo,
soft cap de 100 GB/IP e US$ 3,50/mês para um IP; mostra US$ 15 por cinco e US$ 29 por
dez. A tabela geral, porém, ainda publica US$ 2/IP mais custo de GB. Portanto não há
preço público coerente para seis IPs: usar no máximo US$ 29 como referência de compra
do pacote publicado de dez, não como cotação de seis. Os termos permitem que o
fornecedor peça identificação e aprove ou negue, a seu critério, acesso a domínios
financeiros. Também permitem suspender a conta por uso de robô ou processo automatizado,
apesar de a página do produto anunciar automação empresarial; o piloto exige autorização
escrita para este RPA. As vendas são finais e qualquer reembolso é discricionário.
[Produto e preços por pacote](https://proxyempire.io/static-residential-proxies/),
[tabela geral divergente](https://proxyempire.io/pricing-table/),
[Brasil](https://proxyempire.io/brazil-web-proxy/),
[termos, itens 4.4 e 8](https://proxyempire.io/terms-of-service/).

Oxylabs e Bright Data não entram no piloto atual. Na Oxylabs, consultar uma oferta
dedicada seria necessário em vez de presumir exclusividade no plano compartilhado;
bancos constam entre os alvos restritos. A política da Bright Data exclui informação
atrás de login, independentemente de preço.
[Oxylabs, produto e preços](https://oxylabs.io/pricing/isp-proxies),
[Oxylabs, restrições](https://developers.oxylabs.io/products/proxies/isp-proxies/restricted-targets),
[Bright Data, uso aceitável](https://brightdata.com/acceptable-use-policy).

### Confirmações antes de qualquer compra

Informar ao fornecedor os domínios dos portais e o uso de RPA autorizado pelos lojistas.
Confirmar exclusividade, localização/ASN, manutenção do IP na renovação, permissão dos
domínios após verificação, tráfego, preço, cancelamento e possibilidade de teste curto.
Guardar a resposta comercial e os termos vigentes usados na aprovação. Não enviar
senha, CPF, cookies ou prints para cotação. Nenhum fornecedor foi contatado nesta pesquisa.

Se nenhuma saída testada for aceita, buscar acesso reconhecido pelo banco, integração
oficial ou outra conectividade autorizada. Não multiplicar VPSs sem resolver essa pendência.

## 5. Piloto e critérios para avançar

**Pré-requisito:** o agente responsável verifica a correção do loop, tentativas limitadas
e persistência de resultado terminal. O piloto de infraestrutura não deve contar
reexecuções do mesmo job como falhas independentes de IP.

**O piloto é 100% cloud.** Usar uma loja, uma imagem e a mesma configuração de browser.
Não executar em PC residencial nem usar o resultado residencial como braço do teste.

| Etapa | O que validar | Critério de avanço |
|---|---|---|
| Controle no Fly atual | Após correção do loop, egress estático, saída real, mesma imagem/configuração e resultado terminal | Registrar cada banco em sessão fria e quente; não alterar driver durante a comparação |
| IPRoyal cloud por 24 h | KYC e seis domínios aprovados antes da compra; mesma imagem/configuração do controle | Repetir separadamente sessão fria e quente; diferença reproduzível atribuível à saída |
| Estabilidade | Um browser antes de dois; sessões frias/quentes e retomada após reinício | Gate operacional abaixo, sem desativar contas |
| Isolamento implementado | Seis lojas concorrentes com mocks, crash e perda de rede | Cotas, credenciais, suspensão e recuperação corretas |
| Expansão real | Uma, depois seis lojas; Motrix incluído | Métricas por loja/banco dentro dos objetivos antes de ampliar |

O piloto usa dados autorizados, sessões separadas por saída e artefatos protegidos.
Evitar logins simultâneos da mesma conta. Parar diante de senha recusada, captcha ou
bloqueio; não produzir carga de login apenas para atingir uma amostra.

O teste de 24 h responde apenas se vale iniciar a etapa de estabilidade. Não autoriza
comprar seis IPs. Se o ISP não fizer o Bradesco concluir sob a mesma configuração, parar
a hipótese de rede antes de migrar runtime ou multiplicar VMs.

Gate operacional proposto: pelo menos cinco dias úteis e 50 execuções por banco,
reaproveitando sessões e respeitando uso real. Se o uso for menor, estender o período.
Meta inicial: ≥98% de execução técnica sem intervenção, zero desativação de conta e
zero mistura de dados. Essa amostra não demonstra estatisticamente disponibilidade de 99%.

Recusa comercial conta como resposta do banco, não falha técnica. No Motrix, uma
resposta sem oferta não comprova o parser do painel de ofertas aprovadas.

### Objetivos de serviço, ainda sem SLA contratado

- p95 até 30 s da aceitação ao início de uma rodada sem rodada anterior na fila.
- p95 até 8 min para resultado terminal dos seis bancos, com resultados parciais
  disponibilizados assim que persistidos.
- Medir espera por tarefa separadamente: os últimos bancos não começam em 30 s.
- Testar espera total sob dez rodadas/h por loja antes de oferecer esse volume.
- Medir falhas e intervenções sobre todas as tentativas, junto da latência; publicar
  também indisponibilidade bancária.
- Recuperação de executor em até 15 min é objetivo preliminar, dependente de
  reposição, saída e sessão. Não há failover instantâneo projetado pelo preço de uma VM.

## 6. Capacidade e custos

A referência combina a rodada de 04/09, Fontecred 48 s, Pan 35 s, Bradesco 55 s,
Santander 136 s e Motrix 48 s, com a Omni em cerca de 120 s em 10/09. São
**442 browser-segundos por rodada de seis bancos**. É referência de custo, não requisito
nem p95. Volume real continua desconhecido.

### Volumes transparentes

Para `d` rodadas/dia/loja e 22 dias:

```text
rodadas_mês_loja = d × 22
browser_horas_loja = rodadas_mês_loja × 442 / 3.600
```

| Referência | Rodadas/dia/loja | Rodadas/mês/loja | Browser-h/mês, 1 loja | Browser-h/mês, 6 lojas |
|---|---:|---:|---:|---:|
| Baixo | 2 | 44 | 5,40 | 32,41 |
| Base | 10 | 220 | 27,01 | 162,07 |
| Alto | 30 | 660 | 81,03 | 486,20 |

Com dois browsers reservados por loja, a soma de 442 s tem limite inferior de 221 s
por rodada. A distribuição real entre os dois slots ainda não foi medida com a Omni.
Isso sugere pelo menos 3 min 41 s sem boot, retries ou espera, mas não prevê p95.

### Preços e regras usados

O runtime Fly atual usa `shared-cpu-2x`, 2 GB, `gru`, on-demand e idle stop de 60 s.
Na tabela oficial interativa, selecionando São Paulo (`gru`), essa Machine custa
US$ 0,0256/h, ou no máximo US$ 18,40 por 30 dias iniciada. A cobrança iniciada é por
segundo. Para representar a topologia atual por provedor com seis slots por rodada:

```text
machine_horas_loja = rodadas_mês_loja × (442 + 6 × 60) / 3.600
compute_Fly_loja = machine_horas_loja × US$ 0,0256
```

O termo `6 × 60` soma o idle dos seis workers. Boot, retries e timeouts não estão
medidos, então o compute real será maior. Se o desenho futuro consolidar bancos em
menos Machines, refazer a fórmula em vez de transportar este custo.

| Referência | Machine-h Fly, 1 loja | Compute Fly, 1 loja | Machine-h Fly, 6 lojas | Compute Fly, 6 lojas |
|---|---:|---:|---:|---:|
| Baixo | 9,80 | US$ 0,25 | 58,81 | US$ 1,51 |
| Base | 49,01 | US$ 1,25 | 294,07 | US$ 7,53 |
| Alto | 147,03 | US$ 3,76 | 882,20 | US$ 22,58 |

Custos fixos e excedentes:

- Fly static egress: US$ 3,60/mês por app/loja, cobrado por hora. Tráfego público saindo
  da América do Sul: US$ 0,04/GB. Um ISP externo substitui o static egress; não somar
  os dois.
- Fly parado: US$ 0,15/GB-mês de rootfs, proporcional ao tempo parado. O tamanho da
  rootfs usada por Machine não foi medido. Na topologia por provedor com seis Machines
  por loja, adicionar
  `6 × lojas × rootfs_GB × US$ 0,15 × fração_parada`.
- Fly Volume: US$ 0,15/GB-mês mesmo com a Machine parada. Se o desenho usar um volume
  de 1 GB por provedor para sessão, adicionar US$ 0,75/loja, ou US$ 4,50 para seis.
  Snapshots custam US$ 0,08/GB-mês após os primeiros 10 GB mensais gratuitos; contam
  dados gravados, não capacidade provisionada.
- IPRoyal ISP: preço inicial de US$ 1,80/IP por 24 h ou US$ 2,70/IP por 30 dias;
  100 GB/mês/IP antes de redução de velocidade. Brasil, KYC e bancos ainda precisam
  de confirmação. Todos os subtotais com ISP abaixo usam US$ 2,70/loja/mês.
- Browserbase Developer: mínimo de US$ 20/mês, 100 browser-h, 25 concorrentes e
  excedente de US$ 0,12/browser-h. A cobrança arredonda cada sessão por minuto; as
  seis durações de referência viram 9 minutos faturáveis por rodada, não 442 s.
  Há 1 GB de proxy e excedente de US$ 12/GB. A documentação não separa claramente
  essa medição para proxy externo; se ele for medido, adicionar
  `máx(0, proxy_GB - 1) × US$ 12` e confirmar antes da compra.
- Browserless: Prototyping custa US$ 25/mês no anual, inclui 20 mil unidades e dez
  browsers; Starter custa US$ 140/mês no anual, inclui 180 mil unidades e 40 browsers.
  As seis durações consomem `2 + 2 + 2 + 5 + 2 + 4 = 17` unidades por rodada. Proxy
  externo não consome unidades de proxy.
- Lightsail Linux/IPv4: 4 GB/2 vCPU custa até US$ 24/mês; 32 GB/8 vCPU, até
  US$ 164/mês. A cobrança é horária até esse teto. O plano inclui SSD e IPv4 público;
  é preciso criar e associar o IPv4 estático, sem custo adicional enquanto associado.
  Em São Paulo, a franquia é metade da tabela: 2 TB no plano de 4 GB e 3,5 TB no de
  32 GB. Excedente de saída custa US$ 0,15/GB.

Fontes: [Fly, preços de compute, rootfs, volumes, snapshots e rede](https://fly.io/docs/about/pricing/),
[Fly, cobrança de Machines](https://fly.io/docs/about/billing/#machine-billing),
[Fly, static egress](https://fly.io/docs/networking/egress-ips/),
[IPRoyal](https://iproyal.com/pricing/static-residential-proxies/),
[Lightsail, planos](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-bundles.html),
[Lightsail, IP estático](https://docs.aws.amazon.com/lightsail/latest/userguide/understanding-static-ip-addresses-in-amazon-lightsail.html),
[Lightsail, tráfego regional](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-faq-data-transfer-allowance.html),
[Browserbase](https://docs.browserbase.com/account/billing/plans) e
[Browserless](https://www.browserless.io/pricing).

### Subtotais mensais calculáveis

USD, antes de impostos. Não somam Motor/API/DB centrais, pois já existem e são comuns
a todas as opções. Fly inclui compute da fórmula e static egress **ou** ISP. Browserbase
e Browserless incluem o plano mínimo aplicável e um ISP por loja. Lightsail assume
instância ligada o mês inteiro porque não existe hoje orquestração on-demand fora do Fly;
com parada controlada, aplicar a cobrança horária até o teto.

| 1 loja | Baixo | Base | Alto | Chance de resolver Bradesco |
|---|---:|---:|---:|---|
| Fly on-demand + static egress | US$ 3,85 | US$ 4,85 | US$ 7,36 | **Baixa** |
| Fly on-demand + ISP | a partir de US$ 2,95 | a partir de US$ 3,95 | a partir de US$ 6,46 | **Melhor aposta, não provada** |
| Browserbase Developer + ISP | a partir de US$ 22,70 | a partir de US$ 22,70 | a partir de US$ 22,70 | **Plausível, não provada** |
| Browserless Prototyping + ISP | a partir de US$ 27,70 | a partir de US$ 27,70 | a partir de US$ 27,70 | **Plausível, não provada** |
| Lightsail 4 GB direto | US$ 24,00 | US$ 24,00 | US$ 24,00 | **Baixa** |
| Lightsail 4 GB + ISP | a partir de US$ 26,70 | a partir de US$ 26,70 | a partir de US$ 26,70 | **Plausível, não provada** |

| 6 lojas | Baixo | Base | Alto | Chance de resolver Bradesco |
|---|---:|---:|---:|---|
| Fly on-demand + static egress | US$ 23,11 | US$ 29,13 | US$ 44,18 | **Baixa** |
| Fly on-demand + ISP | a partir de US$ 17,71 | a partir de US$ 23,73 | a partir de US$ 38,78 | **Melhor aposta, não provada** |
| Browserbase Developer + 6 ISP | a partir de US$ 36,20 | a partir de US$ 47,96 | a partir de US$ 95,48 | **Plausível, não provada** |
| Browserless Starter + 6 ISP | a partir de US$ 156,20 | a partir de US$ 156,20 | a partir de US$ 156,20 | **Plausível, não provada** |
| Lightsail compartilhado 32 GB direto, 1 IP para 6 lojas | US$ 164,00 | US$ 164,00 | US$ 164,00 | **Baixa; não atende IP por loja** |
| Lightsail compartilhado 32 GB + 6 ISP | a partir de US$ 180,20 | a partir de US$ 180,20 | a partir de US$ 180,20 | **Plausível, não provada** |
| 6 Lightsail de 4 GB diretos | US$ 144,00 | US$ 144,00 | US$ 144,00 | **Baixa** |
| 6 Lightsail de 4 GB + 6 ISP | a partir de US$ 160,20 | a partir de US$ 160,20 | a partir de US$ 160,20 | **Plausível, não provada** |

Nos valores Browserbase para seis lojas, os tempos faturáveis são 39,6 h, 198 h e
594 h; as duas últimas colunas incluem overage acima de 100 h. No Browserless, os
volumes usam 4.488, 22.440 e 67.320 unidades, todos dentro do Starter. O Starter é
necessário para reservar 12 browsers; o Prototyping para em dez.

Os subtotais Fly não incluem rootfs, volume nem bytes de egress porque esses três
tamanhos não foram medidos. Adicionar as fórmulas acima. Os subtotais Browserbase
não incluem eventual cobrança de GB do proxy externo. Os valores ISP são preços
iniciais públicos, não cotação brasileira nem garantia de acesso bancário. O preço
do Lightsail compartilhado usa 32 GB para preservar a referência de 4 GB por dois
browsers; 16 GB custaria US$ 84/mês, mas a capacidade de CPU/RAM de nenhum dos dois
planos para 12 browsers foi medida. O cenário compartilhado direto é apenas comparativo:
seu único IP não satisfaz a saída fixa por loja.

### Sessão persistente nos runtimes gerenciados

Browserbase preserva Contexts até exclusão/invalidação; um Context por loja/site/login,
sem uso simultâneo. O portal ainda pode expirar cookies ou rejeitar mudança de rede.
Desligar replay não desliga Live View nem impede processamento dos dados pelo fornecedor.
[Contexts](https://docs.browserbase.com/platform/browser/core-features/contexts),
[replay](https://docs.browserbase.com/platform/browser/observability/session-replay),
[proxies e restrições](https://docs.browserbase.com/platform/identity/proxies).

Browserless persiste estado por até 7 dias no Prototyping e 30 no Starter; ao expirar,
remove os dados. URLs de sessão contêm token. O proxy externo mantém a saída escolhida,
mas estado persistente não torna um IP aceitável nem impede vínculo da sessão à rede.
[Estado e retenção](https://docs.browserless.io/baas/session-management/persisting-state),
[proxies](https://docs.browserless.io/baas/bot-detection/proxies).

### APIs oficiais

PAN anuncia API de simulação para parceiros; BV publica integração F&I com negociação
comercial. Adotar onde houver contrato e credenciais, reduzindo browsers dos bancos
substituídos. Não presumir acesso da Revy nem reproduzir APIs privadas dos portais.
[Parceiros PAN](https://www.bancopan.com.br/institucional/parceiro/),
[BV F&I](https://developers-sandbox.bvopen.com.br/api/62).

## 7. Arquitetura técnica para implementação futura

Esta seção descreve o desenho proposto, não código já entregue nem plano de execução.

### Contratos e isolamento

| Módulo | Responsabilidade |
|---|---|
| Motor central | API pública, fila, credenciais cifradas, projeção operacional, cotas e resultados |
| Cadastro de executores | Identidade revogável vinculada a loja, saída, versão e estado ativo/drenando/revogado |
| Executor por loja | Buscar tarefas por HTTPS, executar drivers, persistir sessão e reportar resultado |
| Controle de infraestrutura | Provisionar, atualizar e confirmar parada de Machines/VMs; credencial administrativa não vai ao executor |

O executor inicia HTTPS; não acessa Postgres nem recebe `MOTOR_ENCRYPTION_KEY`.
A autenticação determina `cliente_id`; o servidor não aceita a escolha de outra loja
pelo executor. Só a credencial e o payload necessários à tarefa chegam ao executor.

| Rota interna proposta | Comportamento |
|---|---|
| `POST /v1/internal/executor/tasks/claim` | Reserva uma tarefa da loja autorizada; retorna token, geração, prazo, payload e credencial do provedor |
| `POST /v1/internal/executor/tasks/{id}/heartbeat` | Renova posse válida ou instrui parar |
| `POST /v1/internal/executor/tasks/{id}/complete` | Valida e persiste resultado/estado atomicamente; reenvio idêntico recebe confirmação anterior |

Reaproveitar drivers com contexto sem DB e callbacks remotos de eventos. A API pública
não muda. Integração entre produtos continua por HTTP/evento versionado.

Sessão é segregada por loja/banco/conta/versão de credencial e saída. Validar sua
invalidação nas trocas. Proibir fallback de perfil entre lojas. Respostas com segredo
usam TLS, `Cache-Control: no-store` e nenhuma captura de corpos no proxy/APM.

Credenciais, CPF, cookies, HTML e screenshots com PII não entram no log comum. Volumes
e backups sensíveis são isolados e cifrados, com retenção definida. Artefatos de suporte
têm acesso restrito e auditado; não expor debugging do Chromium ou desktop remoto público.

### Reserva, heartbeat e recuperação

1. Uma transação trava cotas de loja/IP, conta e tarefa em ordem consistente. Confere
   suspensão, rota e vagas; atribui token e geração antes do commit. Aplicar dois browsers
   por loja/IP e um por conta, sem depender da contagem de wake.
2. Supervisor controla até dois subprocessos e a árvore de Chromium. Parâmetros
   preliminares: heartbeat de 20 s, lease renovável de 90 s e timeout de driver independente
   de 420 s. Validar em teste; definir prazo total finito incluindo tentativas e esperas.
3. Token/geração antigos não persistem resultado. Reservas só liberam capacidade após
   parada confirmada do browser. Resultado recebido antes de queda de rede pode ficar em
   spool local cifrado para reenviar conclusão sem refazer a simulação.
4. Lease vencido inicia recuperação. O executor deve abortar ao perder autorização.
   Se não houver confirmação, o controle central para e confirma a parada da VM antiga
   antes de reatribuir tarefa/conta. Sem confirmação, quarentena e alerta. Token no DB
   sozinho não impede o browser antigo de continuar agindo no banco.
5. Após parada confirmada, reencaminhar tarefa recuperável. Ação bancária com efeito
   incerto exige reconciliação/intervenção antes de retry. Não prometer execução exatamente
   uma vez no banco sem idempotência oferecida por ele.
6. Recusa comercial é resultado, sem retry. Senha recusada, captcha, MFA ou bloqueio
   interrompem a conta para intervenção. Falha transitória antes de efeito pode ter um
   retry com atraso. Suspensão impede novas reservas e instrui abortar no heartbeat;
   executor revogado não renova posse.

A recuperação favorece impedir sobreposição quando há dúvida sobre a execução antiga.
Isso pode prolongar indisponibilidade de uma loja; a falha do Motor/DB central continua
afetando todas.

### Provisionamento, deploy e rollback

Provisionar executores por template e inventário, com imagem Docker fixada por digest,
sessão persistente, supervisor e credencial individual. Cadastro inicial de uso único.
No Fly, seguir `deploy/fly/3vm/`; não usar os `fly.toml` legados dos produtos.

Deploy: drenar um executor canário, confirmar fim das tarefas, atualizar, verificar saúde
e retomar. Expandir por lotes, preservando saída e sessão. Rollback de software retorna
ao digest compatível anterior pelo mesmo inventário, sem editar servidores à mão.

Migração: nova flag default OFF e rota exclusiva por loja entre legado e executor HTTP.
O consumidor legado precisa excluir lojas migradas; desligar um slot global por banco
não faz isso. Drenar e confirmar parada antes de trocar rota. Motrix ganha capacidade
produtiva somente após validação.

Rollback para o pool legado `motor2037` restaura o teto global de dois e perde capacidade
multiloja. Não fazer fallback automático para IP não validado. Ao remover executor,
revogar identidade; ao encerrar loja, bloquear reservas, encerrar execução e aplicar
retenção às sessões/backups.

Observar por loja, banco, executor e versão: idade/profundidade da fila, duração de
tarefas/rodadas, logins frios/quentes, recusas, erros técnicos, captcha, intervenções,
tentativas, leases expirados, ocupação por IP/conta e executor offline. Usar IDs opacos,
sem CPF ou login em labels. Alertar ao perder heartbeats.

## 8. Referências do código e estado registrado

Leitura do código nesta pesquisa, sob `motor-simulacao/`. Linhas podem mudar após a
correção do outro agente; conferir o símbolo antes de implementar.

| Arquivo e linha | Situação observada |
|---|---|
| `app/servico.py:145` | Cria tarefas e faz commit antes do wake |
| `app/orquestrador.py:99` | Fila global, agrupamento por provedor e teto global |
| `app/orquestrador.py:116` | Contagem de vagas e marcação de wake sem lock único; sujeitas a corrida |
| `app/processamento.py:643` | Reserva condicional atômica por tarefa, sem filtro de loja/cota transacional de IP |
| `app/config.py:133` | Lease default de 300 s; `app/config.py:18` permite driver por 420 s |
| `app/processamento.py:900` | Renova lease antes de chamar driver, sem heartbeat visível durante essa chamada |
| `app/processamento.py:888` | `DriverContext` recebe DB; precisa ser separado para execução remota |
| `app/sessao_browser.py:26` | Helper preserva fallback legado por banco; não permitir compartilhamento entre lojas |
| `app/processamento.py:905` | Fluxo atual de tarefa usa path canônico de gravação; helper legado não prova vazamento |
| `app/main.py:144` e `app/provisioning.py` | Gate/projeção operacional existentes, a reaproveitar |
| `app/worker.py:93` | Worker drena e encerra após idle no modo on-demand |

Snapshot de produção informado no card original em 10/09, sem nova validação completa
nesta pesquisa: fan-out/autoscale ligados em `app2037`; quatro slots no `motor2037`,
em `gru`, para Fontecred, Bradesco, Santander e Pan, com imagem `v33`; Motrix sem slot.
Não assumir que esse snapshot continua atual após a atuação do outro agente.

## 9. Critérios de aceite e decisões pendentes

### Aceite da implementação futura

- Seis lojas iniciam seis bancos sem cruzar dados, credenciais ou sessões.
- A carga de uma loja não consome a capacidade reservada das outras.
- Limites de browser/IP/conta e reserva são aplicados atomicamente.
- Falha de executor, perda de rede e resultado atrasado não geram execução concorrente.
- Rodadas chegam a resultado terminal com tentativas limitadas.
- Suspensão/remoção bloqueia novas reservas no backend.
- Deploy em lote e rollback preservam o protocolo e a saída validada.
- Há medição real por banco, orçamento completo e métricas de suporte antes da expansão.

Verificação quando houver implementação:

- macOS: `cd motor-simulacao && .venv/bin/python -m pytest -q`.
- Windows: `cd motor-simulacao && .\.venv\Scripts\python.exe -m pytest -q`.
- Testar consumidores se houver alteração de contrato; aplicar migrations no produto
  correto; verificar diff/status e regenerar mapa se mudar rota/modelo/worker/migration/flag.

### O que ainda precisa ser decidido

| Decisão | Proposta para avaliação |
|---|---|
| Hospedagem | Manter Fly on-demand; reconsiderar VPS só com vantagem de custo/capacidade medida |
| Saída de rede | Egress estático como controle; IPRoyal ISP só se o piloto provar ganho e o uso for autorizado |
| Piloto | Uma loja, controle Fly e depois um ISP por 24 h; nunca PC residencial ou da loja |
| Volume e orçamento | Confirmar rodadas por hora no pico e custo máximo por loja |
| Acesso bancário | Confirmar políticas de RPA, APIs e eventual allowlisting com os bancos |
| Suporte | Definir responsável por captcha/MFA, recuperação e retenção de artefatos |
| Aprovação | Aprovar ou ajustar este desenho antes do plano de implementação |

Este documento autoriza a continuidade da discussão arquitetural. Não registra aprovação
de gasto, fornecedor, login de piloto, deploy ou implementação. A correção do Bradesco
permanece com o outro agente.

## 10. Checkpoint da discussão de 11/09

Decisões confirmadas pelo dono nesta conversa:

- A operação atual tem uma loja. Seis lojas são cenário futuro para comparação, não o
  tamanho do piloto nem uma necessidade atual de doze browsers.
- Piloto e produção serão 100% cloud. PC residencial ou da loja não entra nem como controle.
- Confiabilidade bancária vem antes do menor preço, mas a escolha precisa ter bom
  custo-benefício.
- O volume por loja ainda é desconhecido. Os cenários de 2, 10 e 30 rodadas/dia são apenas
  referências para comparar preços.
- O Bradesco concluiu localmente em rede residencial e nunca concluiu no Fly. Isso sustenta
  a hipótese de rede, mas ainda não prova que um ISP cloud será aceito.
- A comparação precisa mostrar o custo total separando runtime, saída de rede, persistência,
  tráfego e excedentes. Preço de proxy sozinho não é preço da solução.

Estado da análise:

- Melhor aposta atual: Fly on-demand com um ISP brasileiro estático e dedicado por loja.
- Controle cloud: Fly com static egress. É barato e necessário para comparação, mas tem
  baixa chance de resolver o Bradesco porque continua em rede de datacenter.
- Primeiro fornecedor a consultar: IPRoyal. O preço público parte de US$ 1,80 por 24 h e
  US$ 2,70 por 30 dias, mas Brasil, estoque, KYC, preço final e os seis domínios precisam
  de confirmação escrita.
- Browserbase com ISP externo é a segunda arquitetura a manter se operar o Chromium no Fly
  ficar difícil. Custa mais e acrescenta outro fornecedor processando as sessões bancárias.
- Browserless a US$ 25/mês aceita dez browsers concorrentes. Reservar doze browsers para
  seis lojas empurra a comparação para o plano de US$ 140/mês. Essa concorrência precisa
  ser confirmada depois de medir o volume real.
- VPS por loja não resolve reputação de rede: seis Lightsail de 4 GB custam US$ 144/mês
  diretamente ou pelo menos US$ 160,20 com seis ISPs.
- ProxyEmpire, Oxylabs de autosserviço, Bright Data, proxy rotativo e PC residencial ficam
  fora do ranking atual pelos motivos registrados na seção 2.

Conclusão sobre sessão quente:

- `MOTOR_WARM_SESSION` vem ligado por padrão.
- O Motor separa o `storage_state` por loja/provedor e o carrega no browser.
- O Bradesco reconhece uma página já autenticada e não preenche CPF/senha novamente.
- O Bradesco só salva o `storage_state` depois de receber e interpretar as ofertas. Como
  nunca concluiu na cloud, não há prova ao vivo de que sua sessão quente funcione lá.
- O piloto deve medir sessões frias e quentes separadamente. Trocar a saída pode invalidar
  uma sessão existente se o banco vincular cookies ou tokens à rede.

Próximo objetivo:

1. Confirmar a correção de lease, retry e resultado terminal antes de medir infraestrutura.
2. Obter a cotação real da IPRoyal e a permissão escrita para os seis domínios bancários.
3. Rodar uma loja na cloud como controle, com static egress do Fly.
4. Rodar a mesma imagem e configuração com um ISP cloud durante 24 horas.
5. Só depois de aprovação técnica, medir cinco dias úteis e decidir a expansão para seis
   lojas.

## 11. Checkpoint de 12/09: o que foi feito e descoberto

### No ar (app2037 em `bbe2544`, motor2037 com os cinco workers na imagem nova)

- **Lease com heartbeat** (`ff87808`). O worker renova `reservada_ate` a cada
  `MOTOR_TASK_HEARTBEAT_SECONDS` (20 s) numa sessão própria enquanto o driver roda. Falha de
  banco no heartbeat faz rollback e loga. Tarefa de worker morto volta à fila no máximo
  `MOTOR_TASK_MAX_REQUEUES` vezes — **2, decisão do dono** — e depois encerra
  `falhou`/`tentativas_esgotadas`, com resultado `erro` e evento.
- **Proxy de saída do browser, desligado** (`3368160`). `MOTOR_PROXY_URL`
  (`http://usuario:senha@host:porta`) vai para o `chromium.launch` e restringe o WebRTC a
  UDP via proxy. `MOTOR_PROXY_EXPECTED_IP` abre `api.ipify.org` pelo browser antes do portal;
  IP diferente ou sem resposta para como `aguardando_intervencao`, sem retry. SOCKS5 com
  senha é recusado. Provado com Chromium real contra proxy local com senha.
- **Espera do Bradesco** (`bbe2544`). Workers de banco com `MOTOR_OFERTAS_TIMEOUT_MS=360000`,
  `MOTOR_DRIVER_TIMEOUT_SECONDS=480` e `MOTOR_TASK_LEASE_SECONDS=480`.
- Suite do Motor: 329 testes verdes.

### Descobertas

- **Os workers de banco nunca receberam o `[env]` do `fly.worker.toml`** e o `fly deploy` não
  os atualiza (sem process group). O Bradesco rodava com lease **300 s** (default do código),
  não os 480 s do toml. Parte do loop de 10/09 era config, não só código. Procedimento em
  `.claude/skills/revy-research/learnings/2026-09-12-fly-deploy-nao-atualiza-worker-por-banco.md`.
- **Revisão do fix de lease** (agente revisor): continuam em aberto a vida sem teto do
  heartbeat se a thread principal travar, o browser que segue rodando depois de perder a
  posse, e testes num SQLite de conexão única (`StaticPool`) que não exercitam lock de Postgres.
  Só 4 dos 12 testes originais falhavam no código antigo.
- **IPRoyal na prática:** a verificação de identidade só libera depois de **US$ 10 gastos**.
  O onboarding empurra o Residential por GB (rotativo, errado para nós). O pedido certo é
  `dashboard.iproyal.com/me/products/static-residential-proxies/create-order` → Dedicated.
  Preços vistos para 1 IP dedicado: 24 h US$ 2,00; 30 dias US$ 4,00; 60 dias US$ 7,60;
  90 dias US$ 10,80 (os três primeiros lidos com a página atualizando). Com país escolhido
  aparece "fraud score": Premium custa +35% e só garante score zero num provedor (IPQS,
  Scamalytics, IP Data), sem garantia sobre reCAPTCHA ou WAF do banco.
- **Outros fornecedores (12/09):** Decodo não tem ISP no Brasil e só libera banco no
  residencial rotativo — fora. Webshare não lista Brasil no ISP — fora. Proxy-Seller vende
  ISP com IP exclusivo e reembolso/troca nas primeiras 24 h, termos sem bloqueio explícito a
  banco, mas não confirma operadora nem preço do Brasil — candidato barato, perguntar no chat.
  SpyderProxy ISP BR US$ 3,90/dia, sem informação sobre banco.
- **Como o mercado resolve:** FANDI (integra Itaú, Bradesco, Santander, Safra e bancos de
  montadora) e Autoconf ("integração direta via API") usam integração oficial com o banco,
  não RPA de portal. Santander tem portal de parceiros (`developer.santander.com.br/parceiros`,
  403 sem login). Não foi encontrada API pública do Bradesco Financiamentos.

### Próximos passos

1. **Rodada de controle, US$ 0:** uma simulação do Bradesco no Fly sem proxy, com a espera
   de 360 s. Concluiu → proxy desnecessário. Travou de novo → IP vira o suspeito principal.
2. Só se travar: proxy barato e curto (Proxy-Seller dentro das 24 h de reembolso, após
   perguntar no chat) ou IPRoyal Standard 90 dias (US$ 10,80, libera a verificação).
   Não comprar nada antes da rodada de controle.
3. Em paralelo, a via definitiva: pedir API/integração ao comercial de cada banco da loja e
   cotação ao FANDI e ao Autoconf. RPA com proxy fica como ponte, não como destino.
