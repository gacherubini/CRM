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
