---
gatilho: screenshot do navegador (extensao Claude in Chrome) nao reflete a acao que acabou de rodar
produto: .claude/skills/revy-research
custo: meia hora cacando um bug de zoom que nao existia
fonte: externo
verificado_em: 2026-09-01
---
# A foto da extensão do Chrome mostra o quadro **anterior** — tire duas

**Gatilho:** você clicou, esperou, tirou screenshot, e a tela está igual à de
antes do clique. Conclui que o clique não fez nada.

Não concluiu certo. Em 01/09 o clique num produto do `arquitetura.html` "não
voava": a trilha no cromo já dizia `Chatbot API`, o `viewBox` lido por JS já era
o da caixa, mas a foto mostrava o nível 1. A segunda foto, tirada sem nenhuma
ação no meio, mostrava o zoom. A captura devolve o último quadro *composto*, e
uma animação por `requestAnimationFrame` que acabou de assentar ainda não está
nele.

Regra prática num `browser_batch`: **duas capturas seguidas** depois de uma
ação animada, e confie na segunda. E antes de caçar bug no código, leia o
estado por `javascript_tool` (`getAttribute("viewBox")`, `style.opacity`) — o
DOM não mente, a foto atrasa.

Dois outros atalhos do mesmo dia:

- `file://` não abre pela extensão ("unparseable URL"); sirva a pasta com
  `python3 -m http.server 8765 --bind 127.0.0.1` e abra por `http://127.0.0.1`.
  O servidor morre quando a sessão do Bash fecha — `nohup ... &` segura.
- `localStorage` não é legível pelo `javascript_tool` (SecurityError), mas a
  página lê normalmente: o que você arrastou numa visita anterior volta na
  próxima. O botão **automático** (ou `Zoom.voltarAoAutomatico()`) limpa.

Ver [`2026-08-23-copiloto-so-se-verifica-no-navegador.md`](2026-08-23-copiloto-so-se-verifica-no-navegador.md).
