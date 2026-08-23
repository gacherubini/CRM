---
gatilho: depurar driver Playwright de banco que termina em timeout
produto: motor-simulacao
custo: dois diagnosticos errados (IP e captcha)
---
# O `try/except: pass` engole o clique e o driver trava ate o timeout

No Bradesco, o resultado dizia `captcha_login` e a timeline mostrava sessao quente e login
confirmado — ou seja, o captcha nem era no login. A causa real, vista no screenshot do
evento de falha: o passo "Dados do veiculo" ficava com UF, placa e modelo **vazios**, o
botao Avancar seguia desabilitado e o driver esperava ate `TimeoutError` (~150 s).

Motivo no codigo: a selecao de UF e o preenchimento da placa estavam cada um em
`try/except: pass`. No Fly esses cliques falham por timing do Chromium sob Xvfb, o erro e
**engolido em silencio**, os campos ficam vazios e o fluxo segue ate estourar. Localmente,
headed, o mesmo passo preenchia e dava OK — a diferenca de ambiente escondia tudo.

Regras que sairam dai (commit `4879c47`, 20/07/2026): nunca `except: pass` em passo de
formulario; ler o valor de volta (`input_value`) para confirmar o que foi digitado; e
**falhar rapido** com erro transitorio + screenshot quando o botao nao habilita, em vez de
clicar num botao desabilitado por 90 s.

Erro de leitura a nao repetir: `codigo_erro` de tentativa tardia mente. Aquele
`captcha_login` so apareceu na 3a tentativa, depois de duas falhas martelarem o portal.
Olhe o screenshot do primeiro evento de falha, nao o codigo da ultima.
