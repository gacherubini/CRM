---
gatilho: driver de banco demorando no login, ou escolher o wait_until de um page.goto
produto: motor-simulacao
custo: 90s por simulacao do Santander, escondidos dentro de "o portal e lento"
fonte: repo
verificado_em: 2026-09-07
---
# `wait_until="networkidle"` cobra o timeout inteiro quando o portal nao cala

O Santander levava 136s por simulacao. Dentro disso, **96s eram so o login** — e o
driver tem apenas 4,8s de espera fixa no arquivo todo, entao nao era `sleep`.

Era isto, em `santander.py:441`:

    page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)

`networkidle` espera 500ms sem nenhuma requisicao. Portal com chat, analytics,
long-poll ou WebSocket **nunca** fica quieto, entao a condicao nao acontece e o goto
so termina no timeout — `BROWSER_TIMEOUT_MS`, que e **90_000**. O `except` embaixo
recarregava a pagina, e a soma dava os 96s. Trocado por `domcontentloaded` mais a
espera do proprio campo de login: **96s -> 6s**, e a simulacao inteira 136s -> 46s.

O Pan ja sabia disso desde julho (`pan_portal.py:407`: "go!PAN mantem conexoes
abertas (chat/analytics): networkidle NUNCA estabiliza"). A licao existia no repo e
nao tinha sido aplicada nos outros tres drivers.

Bradesco e Fontecred tinham o mesmo `goto`. Neles a rede cala e hoje nao custa nada —
mas os dois carregavam no proprio comentario a frase "networkidle expira mas a sessao
ja esta pronta", ou seja, o caminho de **sessao quente** (o comum em producao) pagava
os 90s. Os tres foram para `domcontentloaded`; quem decide sessao quente e
`_portal_autenticado`, que ja roda depois do try.

Regra: **`networkidle` so serve para pagina estatica.** Em portal de banco, carregue
com `domcontentloaded` e espere o elemento de que voce precisa. O elemento e a
condicao real; a rede quieta e um proxy que nunca chega.

Mesma familia, no Motrix: 13 esperas fixas somando 49s no pior caso, uma depois de
cada clique. Viraram `_aguardar_condicao(page, condicao, timeout)`, que devolve assim
que a tela responde — 48s -> 17s. Dormir um numero e pagar o pior caso toda vez.

Rodada de 07/09 00:38 depois das duas mudancas: Fontecred 62s, Pan 38s, Bradesco 53s,
Santander 46s, Motrix RECUSA 17s. Antes: 62 / 35 / 56 / 136 / 48.
