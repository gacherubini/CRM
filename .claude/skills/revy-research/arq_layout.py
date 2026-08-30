"""Layout recursivo da arquitetura: `Modelo` -> `Cena` de caixas posicionadas.

Reescrito em 30/08 depois do ensaio no navegador (ver
arq_zoom_demo.html e o proprio arq_zoom.js). As duas licoes daquele ensaio:

1. O layout e RECURSIVO — `_dispor_no` desenha o no e chama a si mesma para
   cada `no.filhos`, colocando o filho DENTRO da caixa do pai. Profundidade
   vem do modelo (arq_modelo.No.filhos), nunca de uma constante local.
2. O limiar de zoom (`k_min`/`k_face`) e DERIVADO, nunca fixo. Com um
   `K_MIN` constante, uma caixa que so alcanca `k=2.27` ao ser clicada fica
   com o interior invisivel para sempre porque o limiar (`3`, no bug real)
   nunca e alcancado. Por isso: `k_min = k_face = 0.6 * (largura_total /
   largura_do_pai)` — o mesmo numero que "clicar no pai" de fato atinge,
   nunca acima dele.

Stdlib apenas. Determinismo total: toda ordem vem de chave ja ordenada por
`arq_modelo` (nunca `set` sem `sorted()`), nada de forca dirigida — o HTML e
commitado, entao posicao instavel vira ruido no diff do git.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from arq_modelo import Modelo, No, Vm

MARGEM = 24.0
ALTURA_TITULO = 34.0
ITEM_H = 13.0
ITEM_W = 190.0


@dataclass(frozen=True)
class Caixa:
    chave: str
    tipo: str          # "vm" | "no" | "item"
    titulo: str
    subtitulo: str
    x: float
    y: float
    w: float
    h: float
    pai: str | None
    nivel: int          # profundidade; 1 = raiz
    k_min: float = 0.0
    k_face: float = 0.0


@dataclass(frozen=True)
class Cena:
    caixas: tuple[Caixa, ...]
    largura: float
    altura: float


def _grade(tamanhos: list[tuple[float, float]]) -> tuple[float, float, list[tuple[float, float]]]:
    """Empacota `tamanhos` (`[(w, h), ...]`) numa grade `ceil(sqrt(n))`
    colunas, pra que o zoom nunca vire um corredor de 1 caixa de largura.

    Cada coluna/linha usa a maior celula que contem (layout tipo tabela);
    `MARGEM` separa as celulas. A ordem de entrada e a UNICA fonte de
    posicao — determinismo sem depender de nenhum `sorted()` aqui dentro,
    porque quem chama ja entrega os itens em ordem de chave.

    Devolve `(largura_total, altura_total, [(x, y), ...])`, posicoes na
    mesma ordem de `tamanhos`.
    """
    n = len(tamanhos)
    if n == 0:
        return 0.0, 0.0, []

    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)

    larg_col = [0.0] * cols
    alt_lin = [0.0] * rows
    for i, (w, h) in enumerate(tamanhos):
        col, lin = i % cols, i // cols
        larg_col[col] = max(larg_col[col], w)
        alt_lin[lin] = max(alt_lin[lin], h)

    x_col = [0.0] * cols
    acumulado = 0.0
    for c in range(cols):
        x_col[c] = acumulado
        acumulado += larg_col[c] + MARGEM
    largura_total = acumulado - MARGEM

    y_lin = [0.0] * rows
    acumulado = 0.0
    for r in range(rows):
        y_lin[r] = acumulado
        acumulado += alt_lin[r] + MARGEM
    altura_total = acumulado - MARGEM

    posicoes = [(x_col[i % cols], y_lin[i // cols]) for i in range(n)]
    return largura_total, altura_total, posicoes


def _caixa_item(no_chave: str, idx: int, entrada, nivel: int) -> Caixa:
    # chave = caminho completo do no + indice sequencial: unico globalmente
    # sem precisar sanitizar texto arbitrario da entrada (que pode conter
    # markup — ver test_escapa_o_que_viria_a_ser_markup em arq_render).
    return Caixa(
        chave=f"{no_chave}.item{idx}",
        tipo="item",
        titulo=entrada.chave,
        subtitulo=f"{entrada.arquivo}:{entrada.linha}",
        x=0.0, y=0.0, w=ITEM_W, h=ITEM_H,
        pai=no_chave, nivel=nivel,
    )


def _dispor_no(no: No, chave_completa: str, nivel: int) -> tuple[Caixa, list[Caixa]]:
    """Devolve a caixa do proprio `no` (pai=None — quem chama decide o pai)
    mais a lista achatada de TODOS os descendentes, com coordenadas ja
    absolutas dentro do frame local deste no (offset 0,0 no canto do no)."""

    sub_filhos = [
        (chave_completa + "." + filho.chave,) + _dispor_no(filho, chave_completa + "." + filho.chave, nivel + 1)
        for filho in no.filhos
    ]
    sub_itens = [
        (None, _caixa_item(chave_completa, idx, entrada, nivel + 1), [])
        for idx, entrada in enumerate(no.entradas)
    ]

    largura_filhos, altura_filhos, pos_filhos = _grade(
        [(caixa.w, caixa.h) for _, caixa, _ in sub_filhos])
    largura_itens, altura_itens, pos_itens = _grade(
        [(caixa.w, caixa.h) for _, caixa, _ in sub_itens])

    largura_conteudo = max(largura_filhos, largura_itens)
    altura_conteudo = altura_filhos
    if sub_itens:
        altura_conteudo += (MARGEM if sub_filhos else 0.0) + altura_itens

    largura_total = MARGEM * 2 + largura_conteudo
    altura_total = ALTURA_TITULO + MARGEM * 2 + altura_conteudo

    origem_x = MARGEM
    origem_y_filhos = ALTURA_TITULO + MARGEM
    origem_y_itens = origem_y_filhos + altura_filhos + (MARGEM if sub_filhos else 0.0)

    descendentes: list[Caixa] = []
    for (_, caixa_filho, desc_filho), (dx, dy) in zip(sub_filhos, pos_filhos):
        bx, by = origem_x + dx, origem_y_filhos + dy
        descendentes.append(replace(caixa_filho, x=bx, y=by, pai=chave_completa))
        for d in desc_filho:
            descendentes.append(replace(d, x=d.x + bx, y=d.y + by))

    for (_, item, _), (dx, dy) in zip(sub_itens, pos_itens):
        descendentes.append(replace(item, x=origem_x + dx, y=origem_y_itens + dy))

    caixa_no = Caixa(
        chave=chave_completa, tipo="no", titulo=no.titulo,
        subtitulo=(no.termo or no.papel), x=0.0, y=0.0,
        w=largura_total, h=altura_total, pai=None, nivel=nivel,
    )
    return caixa_no, descendentes


def _dispor_vm(vm: Vm, por_chave: dict[str, No], nivel: int) -> tuple[Caixa, list[Caixa]]:
    """Devolve a caixa da VM (moldura, sem preenchimento — ver arq_render) e
    a lista achatada dos produtos que ela contem (e seus descendentes), com
    coordenadas absolutas dentro do frame local da VM.

    Um produto listado em duas VMs (ex.: portal-gestao roda em `app2037` e
    tem schema em `suite-pg`) e desenhado DENTRO DE CADA UMA — e o mesmo
    fato de blast radius, sob dois angulos de infra diferentes — com chave
    prefixada pela VM (`app2037.portal-gestao` vs `suite-pg.portal-gestao`)
    pra nao colidir. `arq_render` resolve qual copia uma aresta usa.
    """
    sub = [
        _dispor_no(por_chave[chave], f"{vm.chave}.{chave}", nivel + 1)
        for chave in vm.contem
        if chave in por_chave
    ]
    largura_conteudo, altura_conteudo, posicoes = _grade(
        [(caixa.w, caixa.h) for caixa, _ in sub])

    largura_total = MARGEM * 2 + largura_conteudo
    altura_total = ALTURA_TITULO + MARGEM * 2 + altura_conteudo
    if not sub:
        # VM sem produto (motor2037, n8n2037, evolution2037): ainda precisa
        # de espaco pro nome + nota nao ficarem cortados.
        largura_total = max(largura_total, ITEM_W + MARGEM * 2)

    origem_x, origem_y = MARGEM, ALTURA_TITULO + MARGEM
    descendentes: list[Caixa] = []
    for (caixa, desc), (dx, dy) in zip(sub, posicoes):
        bx, by = origem_x + dx, origem_y + dy
        descendentes.append(replace(caixa, x=bx, y=by, pai=vm.chave))
        for d in desc:
            descendentes.append(replace(d, x=d.x + bx, y=d.y + by))

    caixa_vm = Caixa(
        chave=vm.chave, tipo="vm", titulo=vm.chave, subtitulo=vm.nota,
        x=0.0, y=0.0, w=largura_total, h=altura_total,
        pai=None, nivel=nivel,
    )
    return caixa_vm, descendentes


def dispor(modelo: Modelo) -> Cena:
    # modelo.nos ja vem ordenado por chave (arq_modelo.carregar itera
    # `sorted(nos)`) — a ordem de construcao aqui e, portanto, ja
    # deterministica; nao ha necessidade de reordenar por conta propria.
    #
    # A VM e o novo nivel 1: uma Caixa tipo "vm" por `modelo.vms`, envolvendo
    # os produtos do seu `contem`. Produto que nao esta em nenhuma VM fica
    # solto, no mesmo nivel das VMs — nao existe hoje nos dados reais (as
    # seis produtos vivem em app2037), mas o modelo precisa aceitar.
    por_chave_no = {no.chave: no for no in modelo.nos}
    contidos: set[str] = set()
    for vm in modelo.vms:
        contidos.update(vm.contem)

    # modelo.vms ja vem ordenado por chave (arq_modelo.carregar faz
    # `sorted(vms)`).
    raizes = [_dispor_vm(vm, por_chave_no, 1) for vm in modelo.vms]
    soltos = [no for no in modelo.nos if no.chave not in contidos]
    raizes += [_dispor_no(no, no.chave, 1) for no in soltos]

    largura, altura, posicoes = _grade([(c.w, c.h) for c, _ in raizes])

    caixas: list[Caixa] = []
    for (caixa, desc), (dx, dy) in zip(raizes, posicoes):
        caixas.append(replace(caixa, x=dx, y=dy))
        for d in desc:
            caixas.append(replace(d, x=d.x + dx, y=d.y + dy))

    # Segundo passe: o limiar so pode ser calculado depois de conhecer a
    # largura da cena inteira. Caixas de nivel 1 (sem pai) ficam em 0.0 —
    # arq_render omite o atributo quando o valor e 0, entao elas nunca
    # brigam com o Zoom.acender da Task 7.
    por_chave = {c.chave: c for c in caixas}
    finais = []
    for c in caixas:
        if c.pai is None or c.pai not in por_chave:
            finais.append(c)
            continue
        pai = por_chave[c.pai]
        k = round(0.6 * (largura / pai.w), 4) if pai.w else 0.0
        finais.append(replace(c, k_min=k, k_face=k))

    finais.sort(key=lambda c: c.chave)
    return Cena(caixas=tuple(finais), largura=largura, altura=altura)
