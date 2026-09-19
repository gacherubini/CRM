---
gatilho: print de diagnostico do driver mostra a tela errada, ou a resposta do portal existe e nao aparece no screenshot
produto: motor-simulacao
custo: duas rodadas de login ate achar (a print mostrava o formulario, nao a recusa)
fonte: repo
verificado_em: 2026-09-19
---
# A resposta do portal pode estar visivel mas fora da area fotografada

Motrix, sim real de 19/09: o driver classificava `credito_recusado` e o evento
`ofertas_lidas` gravava a print. A imagem mostrava o formulario do passo 2, sem o
aviso. O texto estava no DOM e o parser o lia — mas a tela nao.

O `.ajin-error` ("Nao ha oferta de credito...") respondia:

    is_visible()          -> True
    getBoundingClientRect -> x=211 y=683 w=936 h=24
    elementFromPoint      -> DIV.mat-mdc-dialog-surface (o proprio dialog)

O aviso nasce abaixo da dobra do dialog: visivel para o Playwright, oculto atras
do `mat-mdc-dialog-surface` para quem olha. `page.screenshot(full_page=True)` nao
"abre" o scroll interno do modal, entao a recusa nao aparecia e a ultima imagem
seguia sendo o formulario pre-simulacao.

O que resolveu: `scroll_into_view_if_needed()` no alvo **antes** de fotografar
(`MotrixDriver._trazer_resposta_para_a_tela`). Na mesma rodada a print passou a
mostrar o texto vermelho. A ordem importa: rolar depois do screenshot nao adianta.

Regra: print de diagnostico nao prova o que a pagina mostra se o alvo nao estiver
no scroll visivel — e `is_visible()` do Playwright nao conta clipping nem oclusao
(primo de `2026-09-04-is-visible-mente-com-modal-recortado`).

Receita barata: `getBoundingClientRect` + `elementFromPoint(centro)` do alvo. Se
`elementFromPoint` devolver o `mat-mdc-dialog-surface` (ou qualquer outro
elemento), o alvo esta oculto — role ate ele antes de decidir ou fotografar.
