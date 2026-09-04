---
gatilho: clique do Playwright estoura timeout num elemento que existe e parece visivel
produto: motor-simulacao
custo: um diagnostico errado (supus overlay onde era clipping)
fonte: repo
verificado_em: 2026-09-04
---
# `is_visible()` responde True para conteudo recortado a `height: 0`

No go!PAN o driver esperava o modal de agente/operador com
`page.get_by_text("Configure seu agente").wait_for(state="visible")`. Passava. O clique
seguinte em `#certifiedAgent-value` estourava o timeout sem dizer por que — o elemento
resolvia, so nao era clicavel.

Minha primeira hipotese foi overlay por cima. Errada. O que o DOM mostrou:

    rect: {x: 431, y: 869, w: 504, h: 54}     # y=869 num viewport de 768
    quemEstaPorCima: (nada)                   # elementFromPoint fora da viewport
    ancestral .mahoe-modal__dialog: position=fixed  overflow=hidden/hidden  h=0

O dialogo continua no DOM quando fechado, com `height: 0` e `overflow: hidden`. O conteudo
mantem geometria propria — por isso `is_visible()` diz True — mas esta **recortado**.
Playwright checa visibilidade (display, visibility, opacity, bounding box) e **nao analisa
clipping por ancestral**. `scrollIntoView` tambem nao resolve: a altura do ancestral e zero.

Duas regras que sairam dai:

1. **Nao espere um modal auto-abrir.** O go!PAN abre com sessao fria e nao abre com
   `storage_state` quente — a primeira rodada do dia passa e a segunda nao. Abra pelo
   controle fixo da tela (no go!PAN, o botao "Agente e operador" do cabecalho).
2. **Para saber se um dialogo esta aberto, meça a altura dele**, nao pergunte ao titulo:

       page.evaluate("""() => {
           const d = document.querySelector('.mahoe-modal__dialog');
           return !!d && d.getBoundingClientRect().height > 0;
       }""")

Como achar isso rapido em qualquer portal: `getBoundingClientRect()` do alvo,
`document.elementFromPoint(centro)` e os `getComputedStyle` de uns 8 ancestrais
(`position`, `overflow`, altura). Se `elementFromPoint` devolve `null` ou outro elemento,
o alvo nao esta onde o Playwright vai clicar. Modelo em `scripts/_diag_pan_modal.py`
(fora do git por `scripts/_diag*.py`).

Primo deste: [`2026-08-23-driver-playwright-engole-o-clique-que-falha.md`] — la o clique
falhava e o `except: pass` escondia; aqui o clique nem era possivel e o sintoma era um
timeout mudo. Nos dois casos o codigo de erro final apontava para a tela errada.
