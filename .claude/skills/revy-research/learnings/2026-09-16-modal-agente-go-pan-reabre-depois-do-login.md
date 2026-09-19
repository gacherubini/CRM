---
gatilho: go!PAN sai com campo_nao_encontrado e o print da falha mostra o modal "Configure seu agente certificado e operador"
produto: motor-simulacao
custo: sim de 16/09 ficou aguardando_intervencao com o formulario atras do modal; classificacao errada, sem pista no codigo do resultado
fonte: repo
verificado_em: 2026-09-16
---
# O modal de agente/operador do go!PAN abre DEPOIS da checagem pos-login

Em 16/09 (sim c1ba9a9a) o print do `login_confirmado` mostrava a tela
`/captura/inicio` normal (CPF visivel, sem modal) e, ~22s depois, o print da
falha mostrava o modal "Configure seu agente certificado e operador" por cima,
com os dois combos VAZIOS e o Salvar desabilitado. O evento `agente_definido` ja
tinha sido registrado 1s apos o login: o modal abriu **depois** da checagem do
driver, no meio do preenchimento, e o passo seguinte morreu em
`campo_nao_encontrado` (resultado `aguardando_intervencao`), sem dizer qual campo
nem que havia um modal na tela.

O README do produto diz "com sessao quente o portal NAO abre o modal sozinho;
abra pelo botao do cabecalho" — abrir pelo botao continua certo, mas nao basta:
a abertura tardia e uma **corrida**. A defesa ficou em tres camadas
(`app/motor/pan_portal.py`):

- `_primeiro_visivel` trata o modal antes de acusar `campo_nao_encontrado`
  (retenta a busca depois);
- `_passo_cliente` e `_passo_veiculo` re-checam no inicio de cada passo;
- sem nome configurado (`MOTOR_PAN_AGENTE_CERTIFICADO`/`MOTOR_PAN_OPERADOR`
  vazios) o Salvar fica desabilitado: o caminho e FECHAR por Escape/X
  (`_fechar_modal_agente`), nunca clicar Salvar;
- se nao fechar de jeito nenhum, sai `pan_modal_agente_nao_fechou`.

Diagnostico so pelo blob do evento (migration `0013_evento_screenshot_blob`): o
`codigo_erro` do resultado nao carrega a causa e o log do worker morre com a
Machine. Primo: [[2026-09-13-print-e-har-sem-acesso-ao-worker]].

**19/09 — a defesa reabria o modal a cada passo e derrubava o PAN.** Com nome
configurado, `_configurar_agente_operador` era chamado no pos-login, no
`_passo_cliente` e no `_passo_veiculo` e, achando o modal fechado, **abria de novo
para "escolher sempre"**. A 2a/3a gravacao estourava: o `get_by_role("button",
name="Salvar")` resolveu para ZERO no instante do clique (re-render do Angular) e o
clique queimou os 10s ate o timeout (probe de 19/09). Sem nome configurado, o
fechamento por Escape/X tambem nao achava o X — era o `pan_modal_agente_nao_fechou`
de producao. Correcao em `app/motor/pan_portal.py`:

- flag por rodada `_agente_operador_definido` (resetada em `simular`, porque o
  driver vive como **singleton** em `REAL_DRIVERS`) para nao reabrir o modal;
- `_clicar_salvar` ancora no `button.mahoe-button:has-text('Salvar')` (o
  `get_by_role` por nome acessivel e instavel sob re-render) e repete ate o modal
  fechar, em vez de um unico clique de 10s.

O **caminho de fechar** (loja sem nome configurado, que e o caso de producao —
nao ha secret nem env da maquina) tambem estava quebrado pelo mesmo tipo de erro:
procurava `button.close` e `aria-label*='echar'/'lose'`, mas o X real e
`<mahoe-nav-button class="mahoe-modal__button-modal--close" icon="close">`
(**traco DUPLO** no modifier) — nenhum seletor casava e saia
`pan_modal_agente_nao_fechou`. Agora ancora nesse class e espera a animacao de
fechamento em vez de cravar 400ms. Validado no diag local com o modal forcado
aberto sem nome configurado.

Validado no probe local: `login -> agente_definido -> dados_preenchidos ->
simulacao_enviada -> RECUSA credito_recusado` em 44s — **com e sem** as envs de
agente/operador (o caminho de Salvar e o de Fechar, os dois).
