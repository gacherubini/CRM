# Plano #1A — Estabilidade do Bradesco Playwright

> **Status 2026-07-24: BACKLOG PRIORIZADO / NÃO IMPLEMENTADO.**
> Diagnóstico concluído no driver Bradesco atual. Este plano executa somente a fatia
> Bradesco do plano de [drivers Playwright resilientes](2026-07-21-plano-drivers-resilientes.md)
> e não autoriza solver de CAPTCHA, engenharia reversa de API privada ou mudança de
> regra financeira.

## Objetivo

Tornar o login e a simulação do Bradesco Turbo Lojista consistentes e
diagnosticáveis, reduzindo relogins desnecessários, estados falsos de sucesso e
repetições perigosas depois do envio da consulta.

O fluxo alvo deve:

1. reutilizar uma sessão válida e renovar uma sessão expirada de forma controlada;
2. confirmar cada etapa por estado observável, não por tempo fixo;
3. parar imediatamente quando um campo obrigatório não for aplicado;
4. nunca reenviar uma consulta financeira sem saber se a primeira foi recebida;
5. produzir diagnóstico sanitizado suficiente para corrigir uma falha sem reprodução
   às cegas.

## Escopo

Arquivos principais:

- `motor-simulacao/app/motor/bradesco.py`;
- `motor-simulacao/app/motor/playwright_base.py`;
- `motor-simulacao/app/sessao_browser.py`;
- `motor-simulacao/app/processamento.py`;
- `motor-simulacao/app/credenciais.py`;
- `motor-simulacao/tests/test_bradesco_driver.py`;
- novos testes de sessão, trace e fluxo de navegador sanitizado.

Fora do escopo:

- substituir o portal por API não documentada;
- contornar reCAPTCHA, WAF ou autenticação adicional;
- alterar entrada, prazo, versão do veículo ou qualquer decisão financeira;
- migrar Santander, Fontecred ou Pan no mesmo incremento;
- enviar DOM, trace, screenshot, cookie, CPF ou credencial a terceiros.

## Diagnóstico consolidado

### D1 — sessão válida é persistida tarde demais

O login é concluído antes da proposta, mas o `storage_state` só é gravado depois de
receber e interpretar as ofertas. Se qualquer etapa posterior falhar, a sessão
recém-autenticada é descartada e a próxima tentativa volta ao reCAPTCHA.

Evidência:

- login em
  [`bradesco.py`](../../motor-simulacao/app/motor/bradesco.py#L260);
- persistência somente ao final em
  [`bradesco.py`](../../motor-simulacao/app/motor/bradesco.py#L300);
- erro de persistência é silenciosamente ignorado em
  [`playwright_base.py`](../../motor-simulacao/app/motor/playwright_base.py#L193);
- `sessao_parece_quente` valida apenas existência/tamanho do arquivo em
  [`sessao_browser.py`](../../motor-simulacao/app/sessao_browser.py#L58).

Impacto: relogins frequentes, maior exposição a reCAPTCHA/WAF e perda de uma sessão
que estava válida.

### D2 — autenticação pode gerar falso positivo

`_portal_autenticado` considera autenticada qualquer URL que não contenha `/login`.
Uma página intermediária, erro, bloqueio ou redirecionamento incompleto pode ser
aceito como painel logado.

Evidência:

- regra atual em
  [`bradesco.py`](../../motor-simulacao/app/motor/bradesco.py#L446).

Impacto: a timeline registra `login_confirmado`, mas o próximo passo procura “Nova
proposta” em uma página que não é o painel.

### D3 — falhas obrigatórias são engolidas

O driver ignora falhas ao aguardar botão habilitado e carregamento do reCAPTCHA e
clica mesmo assim. Também trata seleção de UF, aceite, versão do veículo, confirmação
e valores como `best effort`.

Evidências:

- espera do login seguida de `except: pass` em
  [`bradesco.py`](../../motor-simulacao/app/motor/bradesco.py#L421);
- retorno `False` de `_preencher_placa` ignorado em
  [`bradesco.py`](../../motor-simulacao/app/motor/bradesco.py#L639);
- confirmação silenciosa em
  [`bradesco.py`](../../motor-simulacao/app/motor/bradesco.py#L822).

Impacto: o fluxo avança em estado inválido e falha depois com códigos genéricos como
`form_incompleto`, `portal_falhou` ou timeout.

### D4 — esperas e locators são frágeis

O fluxo usa `networkidle`, muitos `wait_for_timeout`, `locator.type()`, `force=True`
e `.first` em componentes repetidos do Angular Material. A busca JavaScript pelo
primeiro botão “Avançar” não está limitada à etapa ativa.

Evidências:

- navegação e tempos fixos em
  [`bradesco.py`](../../motor-simulacao/app/motor/bradesco.py#L388);
- campos de login e `.first` em
  [`bradesco.py`](../../motor-simulacao/app/motor/bradesco.py#L409);
- busca global do botão “Avançar” em
  [`bradesco.py`](../../motor-simulacao/app/motor/bradesco.py#L793);
- argumentos customizados do Chromium em
  [`playwright_base.py`](../../motor-simulacao/app/motor/playwright_base.py#L66).

Impacto: o mesmo código pode selecionar componente oculto ou antigo após um re-render
do Angular.

### D5 — retry repete o fluxo financeiro inteiro

O worker faz duas tentativas completas sem checkpoint de etapa, backoff ou distinção
entre “antes do envio” e “depois do envio”.

Evidência:

- retry em
  [`processamento.py`](../../motor-simulacao/app/processamento.py#L295).

Impacto: dois logins seguidos aumentam a pressão do anti-bot; uma falha após o envio
pode resultar em nova submissão da mesma consulta.

### D6 — concorrência não é protegida por credencial

Existe teto global de browsers, mas não uma exclusão explícita por
`(cliente_id, provedor)`. Se duas instâncias Bradesco processarem a mesma conta,
podem disputar a sessão e a gravação do mesmo state.

Impacto: invalidação de sessão no servidor, arquivos concorrentes e comportamento
intermitente difícil de reproduzir.

### D7 — testes e observabilidade não reproduzem o portal

Os testes atuais cobrem parsers, fixtures e chamadas com `MagicMock`, mas não
actionability, overlays, re-render, navegação, sessão expirada ou respostas de login.
O endpoint “testar login” ainda é placeholder.

Evidências:

- testes unitários sem navegador real em
  [`test_bradesco_driver.py`](../../motor-simulacao/tests/test_bradesco_driver.py#L90);
- placeholder em
  [`credenciais.py`](../../motor-simulacao/app/credenciais.py#L261).

## Referência oficial adotada

O desenho segue as recomendações oficiais do Playwright:

- [autenticar uma vez, aguardar URL/estado final e reutilizar o state](https://playwright.dev/docs/auth);
- [usar locators únicos e evitar `first()`/`nth()` como escape de strictness](https://playwright.dev/docs/locators);
- [aproveitar actionability automática](https://playwright.dev/docs/actionability);
- [não usar `networkidle` e tempos fixos como sinal de prontidão](https://playwright.dev/docs/api/class-page);
- [usar `fill()` ou `press_sequentially()` no lugar de `type()`](https://playwright.dev/python/docs/api/class-locator);
- [usar argumentos customizados do browser com cautela](https://playwright.dev/python/docs/api/class-browsertype);
- [reter trace de falha para inspecionar ações, DOM e rede](https://playwright.dev/python/docs/trace-viewer-intro).

`storage_state` cobre cookies, local storage e IndexedDB, mas não persiste
`sessionStorage`. A Fase 1 deve medir se o Bradesco guarda algum marcador relevante
ali antes de implementar persistência adicional.

## Arquitetura alvo

```text
Tarefa Bradesco
  │
  ├─ adquirir lock por (cliente_id, bradesco)
  ├─ carregar state canônico
  ├─ abrir portal
  │    ├─ painel confirmado por URL + marcador exclusivo
  │    │    └─ sessão quente
  │    └─ login visível
  │         ├─ preencher credencial
  │         ├─ aguardar resposta/estado real do login
  │         ├─ CAPTCHA visual → intervenção humana
  │         └─ painel confirmado → salvar state imediatamente
  ├─ máquina de estados da proposta
  │    ├─ pessoa confirmada
  │    ├─ veículo confirmado
  │    ├─ valores confirmados
  │    └─ fronteira de envio
  ├─ após envio: aguardar/recuperar; nunca repetir às cegas
  ├─ ler ofertas
  └─ renovar state + liberar lock
```

## Fase 0 — baseline e diagnóstico reproduzível

- [ ] Criar códigos de etapa: `login`, `pessoa`, `veiculo`, `valores`, `envio`,
  `ofertas`.
- [ ] Registrar, sem PII, URL normalizada, etapa, sessão fria/quente e código da
  falha.
- [ ] Habilitar trace `on-failure` apenas no canário Bradesco.
- [ ] Capturar `console`, `pageerror`, `requestfailed` e status das requisições
  relevantes, sem corpo ou cabeçalhos sensíveis.
- [ ] Executar baseline controlada com pelo menos:
  - sessão inexistente;
  - sessão válida;
  - sessão expirada;
  - login rejeitado;
  - reCAPTCHA/intervenção;
  - formulário com campo obrigatório ausente.
- [ ] Documentar taxa de sucesso por etapa e duração p50/p95 antes da alteração.

**Aceite:** toda falha do canário identifica a etapa e produz trace/screenshot
privados com retenção curta; nenhum segredo ou dado pessoal aparece em log/evento.

## Fase 1 — autenticação e sessão endurecidas

- [ ] Substituir `_portal_autenticado` por contrato explícito:
  - origem/rota permitida;
  - marcador exclusivo e visível do painel;
  - ausência do formulário de login e de mensagem de bloqueio.
- [ ] No login, aguardar a resposta real de autenticação ou o marcador final do
  painel, não apenas a existência de `grecaptcha.execute`.
- [ ] Tratar falha de botão desabilitado/reCAPTCHA como erro específico; nunca clicar
  depois de uma espera que falhou.
- [ ] Salvar o state imediatamente após confirmar o painel.
- [ ] Salvar novamente ao final de um fluxo estável para renovar cookies.
- [ ] Gravar state em arquivo temporário e fazer substituição atômica.
- [ ] Validar expiração/corrupção; state existente não significa sessão válida.
- [ ] Medir `sessionStorage`; persistir explicitamente somente se o login realmente
  depender dele.
- [ ] Implementar bootstrap headed/manual para desafio visual autorizado, salvando o
  state somente após o painel ser confirmado.
- [ ] Fazer o endpoint “testar login” verificar de verdade o painel sem iniciar uma
  proposta.

Testes:

- [ ] sessão quente pula preenchimento de senha;
- [ ] sessão expirada volta ao login frio;
- [ ] URL intermediária não conta como autenticada;
- [ ] erro ao gravar state gera evento e não passa silenciosamente;
- [ ] state é salvo após login mesmo se a etapa “pessoa” falhar depois.

**Aceite:** duas execuções consecutivas reutilizam o login enquanto a sessão do
portal estiver válida; uma falha posterior ao login não descarta o state renovado.

## Fase 2 — máquina de estados e ações verificáveis

- [ ] Criar uma raiz/âncora para cada etapa ativa do wizard.
- [ ] Trocar locators globais com `.first` por locators semânticos únicos e
  escopados à etapa/modal ativo.
- [ ] Usar `get_by_label` para CPF/senha quando o label acessível for estável.
- [ ] Trocar `type()` por `fill()`; usar `press_sequentially()` somente onde a máscara
  do campo exigir eventos de teclado.
- [ ] Remover `force=True` dos caminhos normais.
- [ ] Substituir `networkidle` e sleeps por:
  - `to_be_visible` / `to_be_enabled` / `to_be_checked`;
  - `to_have_value`;
  - URL/rota esperada;
  - resposta HTTP relevante;
  - marcador exclusivo da próxima etapa.
- [ ] Fazer UF, aceite, placa, versão, confirmação e valores retornarem sucesso
  verificável ou erro específico.
- [ ] Se `_preencher_placa` retornar falso, interromper na etapa `veiculo`.
- [ ] Na escolha de versão, validar que um radio foi selecionado antes de confirmar.
- [ ] Nas ofertas, contar somente cards visíveis dentro do container ativo.

Testes:

- [ ] fixture DOM com dois botões “Avançar”, um oculto e um ativo;
- [ ] checkbox visível não marcado;
- [ ] select de UF que re-renderiza;
- [ ] placa que perde o valor após `blur`;
- [ ] modal de versões ausente e presente;
- [ ] card de oferta oculto não conta como resultado.

**Aceite:** nenhuma etapa obrigatória usa `except: pass`; falhas retornam código e
etapa precisos antes de alcançar o próximo passo.

## Fase 3 — retry seguro, idempotência e concorrência

- [ ] Adquirir exclusão por `(cliente_id, bradesco)` antes de abrir o browser.
- [ ] Limitar o Bradesco a uma execução por credencial, mesmo com teto global maior.
- [ ] Serializar leitura/gravação do state da mesma credencial.
- [ ] Classificar etapas em:
  - pré-envio idempotente;
  - fronteira de envio;
  - pós-envio não repetível.
- [ ] Permitir retry automático somente antes da fronteira de envio.
- [ ] Aplicar backoff com jitter para erro transitório de abertura/login, sem loop
  agressivo.
- [ ] Depois do clique de envio, aguardar a resposta e registrar um identificador
  sanitizado quando o portal fornecer um.
- [ ] Se o resultado do envio for ambíguo, retornar `envio_indeterminado` e exigir
  reconciliação/intervenção; não iniciar nova proposta.
- [ ] Estender lease/checkpoint para impedir reenvio após restart do worker.

**Aceite:** zero submissões duplicadas nos testes de timeout, crash e retry; duas
simulações da mesma credencial não executam o portal simultaneamente.

## Fase 4 — browser, testes integrados e rollout

- [ ] Atualizar Playwright e o Chromium correspondente em branch/canário isolado; o
  projeto atual está em `playwright==1.49.*`.
- [ ] Rodar primeiro com os argumentos oficiais mínimos.
- [ ] Remover do Bradesco `ignore_default_args` e flags de stealth não comprovadas;
  reintroduzir somente uma flag por vez, com métrica.
- [ ] Comparar Chromium empacotado e canal Chrome autorizado no mesmo canário, sem
  trocar browser e lógica de formulário na mesma entrega.
- [ ] Criar uma fixture de navegador sanitizada para o wizard Angular.
- [ ] Criar smoke live gated que possa parar antes da fronteira de envio.
- [ ] Rodar canário em uma loja/credencial e concorrência 1.
- [ ] Observar no mínimo 20 execuções, incluindo sessão fria, quente e expirada.
- [ ] Expandir somente se não houver duplicidade e as falhas forem diagnosticáveis.

**Aceite:** suíte unitária/integrada verde; 20 execuções de canário sem duplicidade;
falhas conhecidas classificadas; rollback exercitado.

## Ordem de implementação sugerida

| Incremento | Conteúdo | Risco |
|---|---|---|
| 1 | Trace, códigos de etapa e baseline | baixo |
| 2 | Validação de login + state salvo imediatamente e de forma atômica | médio |
| 3 | Máquina de estados, locators e pós-condições | médio |
| 4 | Lock por credencial + retry pré/pós-envio | alto |
| 5 | Upgrade do Playwright/browser em canário | médio |
| 6 | “Testar login” real e runbook manual | baixo |

Não combinar o incremento 4 com upgrade de browser. Cada entrega deve ter flag ou
commit de rollback independente.

## Métricas e eventos

- `bradesco_etapa_iniciada` / `bradesco_etapa_concluida`;
- `sessao_quente_validada`;
- `sessao_expirada`;
- `sessao_gravada` / `sessao_gravacao_falhou`;
- `login_confirmado` / `login_rejeitado` / `captcha_login`;
- `campo_nao_aplicado`, com somente nome lógico e etapa;
- `envio_confirmado` / `envio_indeterminado`;
- `trace_capturado`;
- duração por etapa, sessão fria/quente e código de saída;
- contagem de tentativas antes e depois da fronteira de envio.

Nunca incluir CPF, celular, placa, senha, cookies, valores preenchidos, DOM ou corpo
de resposta nesses eventos.

## Rollout e rollback

Rollout:

1. testes offline;
2. smoke headed sem envio;
3. canário de uma credencial e concorrência 1;
4. sessão fria;
5. duas sessões quentes consecutivas;
6. sessão expirada;
7. execução completa autorizada;
8. 20 execuções observadas.

Rollback:

- desligar trace;
- restaurar o launcher anterior;
- manter concorrência Bradesco em 1;
- desabilitar retry automático do Bradesco;
- manter o state anterior somente se ele ainda passar pela validação nova;
- nunca fazer rollback removendo a proteção contra reenvio pós-submit.

## Critérios finais de conclusão

- [ ] Sessão é validada pelo painel, não apenas pelo path da URL.
- [ ] State é salvo imediatamente após login e com escrita atômica.
- [ ] Cada etapa confirma sua pós-condição antes de avançar.
- [ ] Não existem `except: pass` em ações obrigatórias.
- [ ] Não existem sleeps usados como único sinal de prontidão.
- [ ] Uma credencial Bradesco não é usada em paralelo.
- [ ] Retry nunca repete automaticamente uma consulta possivelmente enviada.
- [ ] Toda falha retorna etapa, código e diagnóstico sanitizado.
- [ ] “Testar login” faz autenticação/validação real sem abrir proposta.
- [ ] CAPTCHA visual continua sendo intervenção humana, sem solver.
