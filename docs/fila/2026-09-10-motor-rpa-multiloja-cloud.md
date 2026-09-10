# Motor RPA multiloja em cloud: recomendação e alternativas

**Produto:** Motor de Simulação, `motor-simulacao/`.
**Atualizado em:** 10/09/2026.
**Status:** pesquisa e proposta arquitetural. Implementação, fornecedor, contratação e
piloto ainda não aprovados. O diagnóstico e a correção do Bradesco estão com outro agente.

## 1. Solução proposta

**Recomendo manter o Motor no Fly, com executor, credenciais, sessões e capacidade
isolados por loja. Cada loja terá uma saída de rede estável, validada nos bancos.**

O Motor central mantém API, fila, credenciais e resultados. Os executores continuam
sendo parte do produto Motor, mas recebem apenas tarefas e segredos da própria loja.

```text
Motor central no Fly
  ├─ executor da loja A → saída fixa A → bancos
  └─ executor da loja B → saída fixa B → bancos

Cada executor: sessão própria, até 2 browsers, credenciais só da sua loja.
Saída: IP estático do Fly ou ISP brasileiro dedicado, conforme validação.
```

A saída de rede, também chamada de *egress*, é o endereço que o banco vê quando o
browser acessa o portal. Ela pode ser contratada separadamente de onde o browser roda.
Por isso, **um IP por loja não exige uma VPS comprada por loja**.

A preferência pelo Fly aproveita a operação existente. Não há evidência de que trocar
para uma VPS resolveria o acesso bancário. Uma VPS continua sendo alternativa de
computação e isolamento caso custo, capacidade ou operação a justifiquem.

### Ordem recomendada

1. O outro agente corrige e verifica lease, tentativas limitadas e resultado terminal.
2. Observar o acesso bancário depois dessa correção, sem atribuir o loop ao IP.
3. Validar uma saída estável no runtime cloud atual. Preferir saída direta do Fly se
   funcionar; comparar ISP brasileiro dedicado se houver necessidade de outra rede.
4. Após aprovação, implementar o isolamento multiloja e expandir de uma para seis lojas.
5. Adotar APIs oficiais gradualmente nos bancos em que houver habilitação comercial.

Nenhuma loja precisa manter PC ligado. A API pública `/v1/simulacoes` permanece compatível.
O Motrix participa da solução; sua capacidade produtiva depende da validação e do rollout.

## 2. Quais opções recomendo e quais deixaria para depois

| Opção | Minha avaliação | Quando faz sentido | Limitação principal |
|---|---|---|---|
| Fly com executores isolados e saída estática por loja | **Primeira escolha** | Bancos aceitam a saída direta e a capacidade medida atende | IP fixo continua sendo de datacenter; não garante aceitação |
| Fly com executores isolados e ISP brasileiro estático por loja | **Alternativa de conectividade a testar** | Um piloto comprova vantagem da outra saída | Depende de exclusividade, acesso bancário permitido e aceitação real |
| API oficial + Playwright nos bancos restantes | **Complemento recomendado** | A Revy/loja consegue credenciais e contrato adequados | Disponibilidade comercial não foi confirmada para todos os bancos |
| VPS dedicada por loja | **Opção secundária de infraestrutura** | Custo, recursos ou operação justificam sair do Fly | Pode repetir a restrição de datacenter e cria uma frota para administrar |
| Browser gerenciado | **Não escolheria agora** | Operar Chromium vira o principal custo e o fornecedor atende os requisitos | Restrições bancárias, IP entre sessões, retenção e acesso de terceiros aos dados |
| Pool compartilhado com scheduler de cluster próprio | **Adiar** | Uso medido justifica a complexidade e há economia demonstrável | Compartilhar CPU não garante capacidade nem isolamento entre lojas |
| PC na loja ou PC pessoal como produção | **Fora da solução escolhida pelo dono** | Pode servir a experimento separado, se solicitado | Depende de energia, internet e máquina ligada fora da cloud |
| Mais workers no pool atual ou proxy rotativo | **Não recomendo para este desenho** | Não atende, sozinho, aos requisitos deste card | Mantém problemas de cota/isolamento ou troca a saída entre sessões |

A recomendação cloud não significa deixar todos os tenants no mesmo processo.
Machines/VMs separadas são uma forma de isolar executores. Compartilhar hosts físicos
exige cotas de CPU/RAM e uma fronteira de segurança adequada; contexto de browser sozinho
não protege as credenciais de outra loja contra comprometimento do executor.

## 3. O que sabemos e o que ainda é hipótese

### Três questões diferentes

| Questão | Evidência disponível | Consequência |
|---|---|---|
| Capacidade multiloja | Código usa fila e teto globais, com reserva por banco | Precisa de cotas e seleção de tarefas por loja |
| Loop do Bradesco | Outro agente relatou expiração de lease e descarte do resultado | Correção de software vem antes da avaliação de infraestrutura |
| Aceitação da rede pelo banco | Há histórico de falhas cloud e sucesso residencial, em condições diferentes | Ainda não prova causa por IP nem valida fornecedor substituto |

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

### O que outras empresas demonstram

A UiPath documenta saída estática para permitir integração com sistemas que aceitam
IPs cadastrados. É um padrão real de RPA cloud, sem comprovar acesso aos bancos da Revy.
[UiPath, outbound IP ranges](https://docs.uipath.com/orchestrator/automation-cloud/latest/user-guide/outbound-ip-ranges).

O caso Ramp usa browsers gerenciados para recibos em portais de comerciantes e compras
corporativas. É uso real em uma fintech, sem ser teste de login bancário brasileiro.
[Caso Ramp](https://www.browserbase.com/blog/case-study-ramp).

**Não encontramos nas fontes primárias consultadas uma operação equivalente que
comprove os cinco portais funcionando continuamente com um fornecedor específico.**

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

Condições consultadas em 10/09/2026. Cobertura anunciada não equivale a estoque
contratável nem a aceitação pelos bancos.

| Fornecedor | Evidência útil | O que impede escolher agora |
|---|---|---|
| IPRoyal ISP | Anuncia Brasil, IP exclusivo e manutenção estática; documenta verificação de identidade para acesso bancário | Confirmar domínios, uso multiloja, estoque, ASN, renovação e preço final |
| Oxylabs ISP | Documenta restrições bancárias e consulta antes da compra | Oferta de autosserviço permite compartilhamento com até três usuários; exigir oferta dedicada e confirmar Brasil |
| Browserbase | Contexts persistentes e proxy externo | Proxies integrados restringem instituições financeiras; sem garantia identificada de IP permanente por loja |
| Browserless | Playwright, estado persistente, proxy externo e país `br` | Sticky vale durante a sessão; não comprova IP exclusivo permanente nem liberação dos bancos |

**IPRoyal é o primeiro candidato para confirmação comercial se precisarmos testar ISP.**
Sua página lista Brasil e preço inicial de US$ 2,70/IP por 30 dias, sem cotação específica
para este uso. A ajuda exige verificação de identidade para acessar bancos. O guia
informa franquia de 100 GB/mês/IP com redução de velocidade após o limite.
[Produto ISP](https://iproyal.com/isp-proxies/),
[restrições bancárias](https://help.iproyal.com/en/articles/7222117-are-there-any-blocked-sites-or-ports-on-isp-proxies),
[preços](https://iproyal.com/pricing/static-residential-proxies/),
[franquia](https://iproyal.com/quick-start-guides/static-residential-proxies/).

Para Oxylabs, consultar oferta dedicada em vez de presumir exclusividade no plano ISP
de autosserviço. [Produto e preços](https://oxylabs.io/pricing/isp-proxies),
[restrições](https://developers.oxylabs.io/documentation/pt-br/proxies/isp-proxies/restricted-targets).

### Confirmações antes de qualquer compra

Informar ao fornecedor os domínios dos portais e o uso de RPA autorizado pelos lojistas.
Confirmar exclusividade, localização/ASN, manutenção do IP na renovação, permissão dos
domínios após verificação, tráfego, preço e possibilidade de teste curto. Não enviar
senha, CPF, cookies ou prints para cotação. Nenhum fornecedor foi contatado nesta pesquisa.

Se nenhuma saída testada for aceita, buscar acesso reconhecido pelo banco, integração
oficial ou outra conectividade autorizada. Não multiplicar VPSs sem resolver essa pendência.

## 5. Piloto e critérios para avançar

**Pré-requisito:** o agente responsável verifica a correção do loop, tentativas limitadas
e persistência de resultado terminal. O piloto de infraestrutura não deve contar
reexecuções do mesmo job como falhas independentes de IP.

| Etapa | O que validar | Critério de avanço |
|---|---|---|
| Uma loja no runtime cloud atual | Saída real, IPv4/IPv6, sessões persistentes e resultado terminal | Execução observável sem loop; avaliar se outra saída é necessária |
| Comparação de saída, se necessária | Mesmo runtime/configuração; saída direta versus ISP autorizado | Diferença reproduzível por banco, sem confundir troca de rede com mudança de driver |
| Estabilidade | Um browser antes de dois; sessões frias/quentes e retomada após reinício | Gate operacional abaixo, sem desativar contas |
| Isolamento implementado | Seis lojas concorrentes com mocks, crash e perda de rede | Cotas, credenciais, suspensão e recuperação corretas |
| Expansão real | Uma, depois seis lojas; Motrix incluído | Métricas por loja/banco dentro dos objetivos antes de ampliar |

O piloto usa dados autorizados, sessões separadas por saída e artefatos protegidos.
Evitar logins simultâneos da mesma conta. Parar diante de senha recusada, captcha ou
bloqueio; não produzir carga de login apenas para atingir uma amostra.

Gate operacional proposto: pelo menos cinco dias úteis e 50 execuções por banco,
reaproveitando sessões e respeitando uso real. Se o uso for menor, estender o período.
Meta inicial: ≥98% de execução técnica sem intervenção, zero desativação de conta e
zero mistura de dados. Essa amostra não demonstra estatisticamente disponibilidade de 99%.

Recusa comercial conta como resposta do banco, não falha técnica. No Motrix, uma
resposta sem oferta não comprova o parser do painel de ofertas aprovadas.

### Objetivos de serviço, ainda sem SLA contratado

- p95 até 30 s da aceitação ao início de uma rodada sem rodada anterior na fila.
- p95 até 8 min para resultado terminal dos cinco bancos, com resultados parciais
  disponibilizados assim que persistidos.
- Medir espera por tarefa separadamente: os últimos bancos não começam em 30 s.
- Testar espera total sob dez rodadas/h por loja antes de oferecer esse volume.
- Medir falhas e intervenções sobre todas as tentativas, junto da latência; publicar
  também indisponibilidade bancária.
- Recuperação de executor em até 15 min é objetivo preliminar, dependente de
  reposição, saída e sessão. Não há failover instantâneo projetado pelo preço de uma VM.

## 6. Capacidade e custos

A referência local de 04/09 foi Fontecred 48 s, Pan 35 s, Bradesco 55 s,
Santander 136 s e Motrix 48 s: **322 browser-segundos por rodada**.

Seis lojas geram 30 tarefas. Com dois browsers globais, o limite inferior para esvaziar
o lote é 1.932 / 2 = 966 s, aproximadamente 16 min, antes de boot, retries e timeouts.

Com dois browsers reservados por loja, o limite inferior é 161 s por rodada.
Uma distribuição possível soma 171 s em um slot e 151 s no outro; sugere aproximadamente
três minutos sem overhead, sem prever p95. O teto aritmético é 22,4 rodadas/h por loja.
Santander, com uma execução por conta e 136 s, teria teto de 26,5/h nessa amostra.

Dimensionar inicialmente para até dez rodadas/h por loja, uma rodada ativa e as
demais em fila. Esses valores são hipóteses de capacidade a medir. Manter até dois
browsers por loja/IP e um por conta; não tratar esse teto como limite publicado dos bancos.

### Cenários de custo mensal

USD, antes de impostos. Valores de saída Fly são só egress; valores de VPS incluem
o plano indicado. **As colunas não são orçamentos equivalentes de solução completa.**

| Lojas | Browsers reservados no pico | Só egress Fly, a US$ 3,60/loja | VPS 4 GB, a US$ 24/loja | VPS 8 GB, a US$ 44/loja |
|---|---:|---:|---:|---:|
| 1 | 2 | US$ 3,60 | US$ 24 | US$ 44 |
| 6 | 12 | US$ 21,60 | US$ 144 | US$ 264 |
| 25 | 50 | US$ 90 | US$ 600 | US$ 1.100 |
| 100 | 200 | US$ 360 | US$ 2.400 | US$ 4.400 |

Fontes: [egress Fly](https://fly.io/docs/networking/egress-ips/) e
[planos Lightsail](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-bundles.html).

O total Fly depende das Machines, tempo ligado, RAM/CPU, volumes e tráfego medidos.
O total com ISP acrescenta IP exclusivo, tráfego/franquia e eventual plano mínimo.
Não foi obtida cotação válida de ISP brasileiro para os bancos da Revy. Proxy externo
pode substituir a saída estática Fly para o tráfego bancário; não somar ambos automaticamente.

Lightsail é referência de VPS, disponível em São Paulo desde junho de 2026. O plano
Linux/IPv4 de 4 GB tem 2 vCPU; medir pico de RAM, swap e CPU com dois Chromiums antes
de escolhê-lo. Associar static IP explicitamente; ele pode ser transferido para instância
substituta. Em São Paulo, a franquia de tráfego é metade da tabela geral.
[Região](https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-lightsail-aws-regions/),
[rede](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-faq-networking.html),
[franquia](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-faq-data-transfer-allowance.html).

Todos os cenários precisam incluir Motor/DB centrais, backup, monitoramento, suporte,
operação, câmbio, impostos e excedentes. Conferir cotas e disponibilidade de VMs/IPs antes
da expansão. Para 25 e 100 lojas, os recursos reservados crescem para 50 e 200 browsers;
compartilhar hosts não elimina esse custo no pico simultâneo.

### Custos e limitações de browsers gerenciados

Com dez rodadas/dia por loja em 22 dias, a referência consome aproximadamente
19,7 browser-horas/mês/loja: 118 h para seis, 492 h para 25 e 1.968 h para 100.
Além das horas, contratar concorrência, tráfego, estado persistente e saída adequada.

| Serviço | Preços consultados | Ressalva |
|---|---|---|
| Browserbase Developer / Startup | US$ 20 / 99 por mês; 100 / 500 h; 25 / 100 browsers; 1 / 5 GB de proxy | Excedentes: US$ 0,12 / 0,10 por hora e US$ 12 / 10 por GB; proxy integrado tem restrições bancárias |
| Browserless Prototyping / Starter / Scale | US$ 25 / 140 / 350 por mês, cobrados anualmente; 20 mil / 180 mil / 500 mil unidades; 10 / 40 / 100 browsers | Unidade de até 30 s por conexão; proxy residencial acrescenta 6 unidades/MB |

Fontes: [Browserbase](https://www.browserbase.com/pricing) e
[Browserless](https://www.browserless.io/pricing). No Browserless, arredondar por conexão;
arredondar apenas os 322 s totais subestima várias conexões curtas.

Browserbase preserva Contexts até exclusão/invalidação; um Context por loja/site/login,
sem uso simultâneo. Desligar replay não desliga Live View nem impede processamento dos
dados pelo fornecedor. [Contexts](https://docs.browserbase.com/platform/browser/core-features/contexts),
[replay](https://docs.browserbase.com/platform/browser/observability/session-replay),
[proxies e restrições](https://docs.browserbase.com/platform/identity/proxies).

Browserless oferece persistência de até 7/30/90 dias nesses planos; exclusão/expiração
remove o estado e replay vem desligado por padrão. URLs de sessão contêm token.
Sticky vale durante a sessão, sem comprovação de IP permanente por loja.
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

- Seis lojas iniciam cinco bancos sem cruzar dados, credenciais ou sessões.
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
| Hospedagem | Manter Fly; reconsiderar VPS com custo/capacidade medidos |
| Saída de rede | Direta estática se aceita; ISP dedicado somente se necessário e validado |
| Piloto | Uma loja, após correção do lease, antes de contratar a expansão |
| Volume e orçamento | Confirmar rodadas por hora no pico e custo máximo por loja |
| Acesso bancário | Confirmar políticas de RPA, APIs e eventual allowlisting com os bancos |
| Suporte | Definir responsável por captcha/MFA, recuperação e retenção de artefatos |
| Aprovação | Aprovar ou ajustar este desenho antes do plano de implementação |

Este documento autoriza a continuidade da discussão arquitetural. Não registra aprovação
de gasto, fornecedor, login de piloto, deploy ou implementação. A correção do Bradesco
permanece com o outro agente.
