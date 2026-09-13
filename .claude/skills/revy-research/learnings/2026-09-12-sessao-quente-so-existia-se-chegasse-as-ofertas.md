---
gatilho: um banco cai em captcha/login frio logo depois de uma rodada que terminou em recusa, ou a sessão quente não é reusada
produto: motor-simulacao
custo: dois logins frios no Bradesco em sequência; o segundo levou reCAPTCHA
fonte: repo
verificado_em: 2026-09-12
---
# Sessão quente só existia se a rodada chegasse às ofertas

O Bradesco chamava `_salvar_storage` só no fim de `_simular_playwright`, depois
de `_resultados_de_html` e do parse das ofertas. Recusa de crédito
(`credito_recusado`) e timeout estouram antes disso. Então a rodada que fez
login certo mas terminou recusada não gravava `storage_state` nenhum, e a
seguinte entrava como `sessao_fria` (`app/processamento.py`) e refazia o login —
onde o reCAPTCHA é sorteado. Não era a sessão quente sendo ignorada: ela nunca
existiu.

Correção: `BradescoDriver._persistir_sessao` grava assim que
`_portal_autenticado` é verdadeiro, chamado logo após `_pular_troca_senha` e
também nos `except` — e só grava se autenticado, porque gravar fora do login
sobrescreveria uma sessão boa com lixo. Regressão:
`tests/test_bradesco_driver.py::test_simulacao_recusada_ainda_persiste_a_sessao_do_login`.

Primo: `2026-09-12-recusa-antes-do-erro-generico-na-espera` — a mesma rodada
recusada também saía como erro técnico até a sonda de recusa vir antes da espera.
