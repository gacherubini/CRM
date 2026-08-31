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
   nunca acima dele. Corrigido em 30/08 (2a leva) com um PISO de 1.6: sem
   ele, um pai que domina a cena (app2037 e 97% da largura) faz a formula
   sair abaixo do zoom inicial (k=1), e o interior de todo produto ja abre
   no primeiro quadro. O piso e seguro porque a cena deixou de ser uma tira
   dominada por um unico filho (ver `_grade` abaixo) — se algum pai ainda
   ficar pequeno demais para o piso, o defeito e o empacotamento, nao o
   piso (`test_o_limiar_e_alcancavel_clicando_no_pai` continua de pe).

Stdlib apenas. Determinismo total: toda ordem vem de chave ja ordenada por
`arq_modelo` (nunca `set` sem `sorted()`), nada de forca dirigida — o HTML e
commitado, entao posicao instavel vira ruido no diff do git.
"""
from __future__ import annotations

import math
import math
from dataclasses import dataclass, replace

from arq_modelo import Modelo, No, Vm

# Quanto uma aresta que anda para TRAS na fila custa a mais que uma que anda
# para frente (`_ordem_por_afinidade`). 3 foi o menor valor que poe os quatro
# estagios do Chatbot em ordem de fluxo — com 1 (sem pena) a ordenacao so
# olha proximidade e "Sai" pode nascer antes de "Entra".
PENA_DE_VOLTA = 3

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
    """Empacota `tamanhos` (`[(w, h), ...]`) em prateleiras (shelf packing),
    mirando a proporcao de tela ~16:10, pra que a cena nunca vire uma tira
    de 5:1 (filhos com larguras muito diferentes faziam a antiga grade
    `ceil(sqrt(n))` colunas ficar larguissima).

    `largura_alvo = sqrt(area total * 2.8)`. O fator comecou em 1.6 (mira
    literal ~16:10), mas o empacotamento e RECURSIVO — cada nivel encaixa
    os filhos do nivel de baixo, que ja saiu um pouco mais alto que o
    proprio alvo, e o desvio composto de nivel em nivel deixava a cena
    real (`_frescor.json` + `arquitetura.py`) com razao 0.96 (mais alta
    que larga). 2.8 foi medido contra o modelo real ate cair dentro da
    meta (razao entre 1.0 e 2.2 — ver `test_a_cena_nao_e_uma_tira`) E manter
    o limiar de app2037 alcancavel (ver `FRACAO_MIN_VM` em `dispor()`: os
    dois numeros foram calibrados juntos, um 2.0 mais "redondo" deixava o
    piso de VM vazia entrar na mesma prateleira de app2037 de um jeito que
    NUNCA satisfazia `test_o_limiar_e_alcancavel_clicando_no_pai`).

    Percorre os itens NA ORDEM DE ENTRADA (unica fonte de posicao —
    determinismo sem `sorted()` aqui dentro, porque quem chama ja entrega
    em ordem de chave), acumulando numa linha; quando o proximo item
    estouraria `largura_alvo`, quebra a linha. Uma linha nunca fica vazia —
    um item maior que o alvo sozinho ocupa a linha inteira. Linhas se
    alinham pelo topo; a altura de cada linha e a do item mais alto dela.

    Devolve `(largura_total, altura_total, [(x, y), ...])`, posicoes na
    mesma ordem de `tamanhos`.
    """
    n = len(tamanhos)
    if n == 0:
        return 0.0, 0.0, []

    area = sum(w * h for w, h in tamanhos)
    largura_alvo = math.sqrt(area * 2.8) if area > 0 else 0.0

    linhas: list[list[int]] = []
    linha_atual: list[int] = []
    largura_linha = 0.0
    for i, (w, h) in enumerate(tamanhos):
        acrescida = largura_linha + (MARGEM if linha_atual else 0.0) + w
        if linha_atual and acrescida > largura_alvo:
            linhas.append(linha_atual)
            linha_atual = [i]
            largura_linha = w
        else:
            linha_atual.append(i)
            largura_linha = acrescida
    if linha_atual:
        linhas.append(linha_atual)

    posicoes: list[tuple[float, float]] = [(0.0, 0.0)] * n
    largura_total = 0.0
    y = 0.0
    for linha in linhas:
        x = 0.0
        alt_linha = 0.0
        for idx in linha:
            w, h = tamanhos[idx]
            posicoes[idx] = (x, y)
            x += w + MARGEM
            alt_linha = max(alt_linha, h)
        largura_total = max(largura_total, x - MARGEM)
        y += alt_linha + MARGEM
    altura_total = y - MARGEM

    return largura_total, altura_total, posicoes


def _indice_dono(caminhos: list[str], ponta: str) -> int | None:
    """Qual irmao contem esta ponta de aresta? Irmaos sao disjuntos, entao no
    maximo um casa. `ponta` e' caminho pontuado no espaco do MODELO
    (`chatbot-api.workers.followup`), sem o prefixo da VM."""
    for i, c in enumerate(caminhos):
        if ponta == c or ponta.startswith(c + "."):
            return i
    return None


def _ordem_por_afinidade(caminhos: list[str], arestas: tuple[tuple[str, str], ...]) -> list[int]:
    """Permutacao dos irmaos que poe lado a lado quem fala com quem.

    O empacotamento (`_grade`) le a ordem de entrada e so ela; a ordem vinha
    alfabetica, que nao tem relacao nenhuma com quem chama quem. O resultado
    medido no navegador em 30/08: das 20 arestas internas do Chatbot, 16
    atravessavam caixa alheia, 75 travessias no total — e os pares mais
    conversados (`workers`->`atendimento`, `atendimento`->`provisionamento`)
    estavam em pontas opostas do tabuleiro, com o maior grupo do produto
    plantado no meio do caminho. Roteamento com desvio contornaria bem um
    layout que nao deveria ter esse formato; e' mais barato dar ao
    empacotamento uma ordem que ja nasce sem a travessia.

    Minimiza `sum(peso[i][j] * custo(posicao[j] - posicao[i]))` — o arranjo
    linear ponderado, com DIRECAO — por subida de encosta: troca dois irmaos
    de lugar enquanto alguma troca diminuir o custo, partindo da ordem
    alfabetica.

    O peso e' dirigido e andar para tras custa `PENA_DE_VOLTA` vezes mais que
    andar para frente. Sem isso a ordenacao so sabia PROXIMIDADE: ela punha
    quem conversa lado a lado, mas nada a impedia de deixar o estagio "Sai"
    antes do "Entra" — foi exatamente o que ela fez na primeira tentativa com
    os grupos por estagio do Chatbot, e a pagina ficava lendo de tras para a
    frente. Com a pena, a fila sai na ordem do fluxo sozinha, a partir do
    dado: nada de lista de nomes cravada no codigo.

    Medido no modelo real (as 20 arestas internas do Chatbot, contando
    travessia de caixa que nao e' ponta nem ancestral de ponta):

        ordem alfabetica (o que havia)   75 travessias, 16 arestas sujas
        vizinho mais proximo             58 travessias, 13 arestas sujas
        subida de encosta                43 travessias, 13 arestas sujas
        vizinho mais proximo + subida    52 travessias, 12 arestas sujas

    A ultima linha e' o motivo de nao haver semente esperta aqui. Comecar
    pelo vizinho mais proximo — o passo obvio, e o que eu tinha escrito
    primeiro — poe a Borda HTTP (que fala com quase todos) no comeco da
    fila, e a subida termina num otimo local PIOR que partindo do
    alfabetico. Semente boa para o primeiro passo nao e' semente boa para o
    resultado; se alguem for "melhorar" isto com uma semente, meca de novo.

    Nao e' otimo (arranjo linear minimo e' NP-dificil) e nao precisa ser —
    precisa ser melhor que alfabetico e ser sempre o mesmo. O custo de uma
    troca e' calculado por DELTA, em O(n): so os termos das duas pontas
    trocadas mudam. Recalcular o custo inteiro seria O(n^2) por troca e
    O(n^4) por volta, o que e' irrelevante nos 10 componentes de hoje e
    deixaria de ser se alguem modelasse um produto com cem.

    Determinismo, que aqui nao e' detalhe (o HTML e' commitado e
    `gerar_arquitetura.py --verificar` compara byte a byte): a varredura de
    trocas tem ordem fixa, aceita a primeira que melhora, e todo desempate
    cai no indice de entrada, que ja vem ordenado por chave de
    `arq_modelo.carregar`. Sem aresta nenhuma entre os irmaos — o caso de
    todo produto que ainda nao tem componente, e da vista Schema inteira,
    que nao tem aresta por decisao — devolve a identidade, entao a pagina
    fora do Chatbot nao se mexe.
    """
    n = len(caminhos)
    if n < 3:
        return list(range(n))

    # DIRIGIDO: peso[i][j] conta so as arestas que vao de i PARA j.
    peso = [[0] * n for _ in range(n)]
    for de, para in arestas:
        i = _indice_dono(caminhos, de)
        j = _indice_dono(caminhos, para)
        if i is None or j is None or i == j:
            continue
        peso[i][j] += 1

    # Sem nenhuma aresta entre os irmaos, nenhuma troca melhora nada e a
    # subida devolveria a identidade de qualquer jeito — o atalho e' so pra
    # deixar essa garantia explicita, que e' o que mantem a pagina inteira
    # fora do Chatbot (e a vista Schema, sem aresta por decisao) parada.
    if not any(any(linha) for linha in peso):
        return list(range(n))

    ordem = list(range(n))

    # Subida de encosta por troca de pares. `posicao[k]` = onde o irmao k
    # esta na fila; o delta de trocar as posicoes a e b so envolve os pesos
    # das duas pontas contra o resto (o termo entre elas nao muda, a
    # distancia |a-b| e' a mesma depois da troca).
    posicao = [0] * n
    for p, k in enumerate(ordem):
        posicao[k] = p

    def custo(d: int) -> int:
        """Distancia na fila, mais cara quando a seta anda para tras."""
        return d if d > 0 else -d * PENA_DE_VOLTA

    def delta(a: int, b: int) -> int:
        u, v = ordem[a], ordem[b]
        d = 0
        for k in range(n):
            if k == u or k == v:
                continue
            p = posicao[k]
            d += peso[u][k] * (custo(p - b) - custo(p - a))
            d += peso[k][u] * (custo(b - p) - custo(a - p))
            d += peso[v][k] * (custo(p - a) - custo(p - b))
            d += peso[k][v] * (custo(a - p) - custo(b - p))
        # O par trocado entre si TAMBEM muda, ao contrario do caso simetrico:
        # inverter u e v inverte o sentido da aresta entre os dois na fila.
        d += peso[u][v] * (custo(a - b) - custo(b - a))
        d += peso[v][u] * (custo(b - a) - custo(a - b))
        return d

    # Teto de voltas: a subida so anda quando ha melhora ESTRITA, entao ela
    # termina sozinha. O teto e' cinto de seguranca contra um empate ciclico
    # que eu nao tenha previsto — travar a geracao seria pior que uma ordem
    # um pouco pior.
    for _ in range(100):
        melhorou = False
        for a in range(n):
            for b in range(a + 1, n):
                if delta(a, b) < 0:
                    ordem[a], ordem[b] = ordem[b], ordem[a]
                    posicao[ordem[a]], posicao[ordem[b]] = a, b
                    melhorou = True
        if not melhorou:
            break
    return ordem


def banda_titulo(largura_conteudo: float, proporcao: float = 0.08) -> float:
    """Altura reservada para o titulo, no topo da caixa.

    Era a constante `ALTURA_TITULO` (34 unidades) em qualquer profundidade,
    enquanto a fonte do titulo cresce com a caixa e chega a 85 num produto: o
    titulo simplesmente nao cabia na propria faixa, e caia por cima dos
    filhos, que comecam logo abaixo dela. Como face e interior fazem crossfade
    (as duas rampas se cruzam em 50/50), isso nao e um quadro — e um intervalo
    inteiro de zoom com titulo e conteudo sobrepostos.

    A faixa sai da largura do CONTEUDO, que ja esta calculada quando esta
    funcao e chamada — nao da altura da caixa, que ainda nao existe.
    """
    return max(ALTURA_TITULO, largura_conteudo * proporcao)


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


def _dispor_no(no: No, chave_completa: str, nivel: int,
               arestas: tuple[tuple[str, str], ...] = (),
               caminho: str | None = None) -> tuple[Caixa, list[Caixa]]:
    """Devolve a caixa do proprio `no` (pai=None — quem chama decide o pai)
    mais a lista achatada de TODOS os descendentes, com coordenadas ja
    absolutas dentro do frame local deste no (offset 0,0 no canto do no).

    `caminho` e' a chave no espaco do MODELO (`chatbot-api.canais`), que e'
    onde as pontas de aresta vivem; `chave_completa` e' a mesma coisa com o
    prefixo da VM (`app2037.chatbot-api.canais`), que e' o id no SVG. Os dois
    andam juntos porque so o primeiro casa com `Aresta.de`/`Aresta.para` e so
    o segundo e' unico quando um produto aparece em duas VMs.
    """
    caminho = no.chave if caminho is None else caminho

    filhos = list(no.filhos)
    ordem = _ordem_por_afinidade([caminho + "." + f.chave for f in filhos], arestas)
    sub_filhos = [
        (chave_completa + "." + filhos[i].chave,)
        + _dispor_no(filhos[i], chave_completa + "." + filhos[i].chave, nivel + 1,
                     arestas, caminho + "." + filhos[i].chave)
        for i in ordem
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

    if not sub_filhos and not sub_itens:
        # Componente folha escrito a mao pode nao ter conteudo NENHUM: na
        # vista Arquitetura ele E' o conteudo, e o inventario nao sabe dele
        # (nao e' rota, nem worker, nem flag). Sem um piso vindo do proprio
        # texto, a caixa nasce so das margens — 49 unidades de largura, fonte
        # 2,7 — e vira um retangulo anonimo ao lado dos irmaos cheios. Foi
        # assim que 'Conversa e lead', 'Saida WhatsApp', 'Agente por loja',
        # 'Simulacao humana' e 'Projecao do Control' apareceram sem nome.
        largura_conteudo = max(largura_conteudo, ITEM_W, len(no.titulo) * 9.0)
        altura_conteudo = max(altura_conteudo, ITEM_H * 4)

    banda = banda_titulo(largura_conteudo)
    largura_total = MARGEM * 2 + largura_conteudo
    altura_total = banda + MARGEM * 2 + altura_conteudo

    origem_x = MARGEM
    origem_y_filhos = banda + MARGEM
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


# Area do produto: comprimida pela raiz, nao proporcional a contagem.
#
# O tamanho de uma caixa emerge do empacotamento do que ela contem, entao a
# Loja (154 entradas) nascia com ~8x a area do Catalogo (15). Na visao de
# escopo isso vira um vazio grande e titulos de 20px ao lado de 7px: e' peso
# demais para um sinal que o desenho ja da pela ordem. Com area proporcional
# a raiz, a ORDEM se mantem — Loja continua maior que Chatbot — e a razao
# entre a maior e a menor cai de ~8x para ~3x.
#
# A escala e' aplicada a SUBARVORE inteira (a caixa e todos os descendentes,
# que vivem em coordenadas relativas ao frame dela), nunca so a moldura: sem
# isso o conteudo vazaria para fora da propria caixa. Os limiares de LOD nao
# precisam de ajuste — sao derivados de largura_cena/largura_pai depois
# disto, entao acompanham sozinhos.
AREA_REFERENCIA = 900_000.0


def _comprimir(caixa: Caixa, descendentes: list[Caixa]) -> tuple[Caixa, list[Caixa]]:
    area = caixa.w * caixa.h
    if area <= 0:
        return caixa, descendentes
    alvo = math.sqrt(area * AREA_REFERENCIA)
    s = math.sqrt(alvo / area)
    if abs(s - 1.0) < 1e-9:
        return caixa, descendentes
    escalada = replace(caixa, w=caixa.w * s, h=caixa.h * s)
    return escalada, [
        replace(d, x=d.x * s, y=d.y * s, w=d.w * s, h=d.h * s)
        for d in descendentes
    ]


def _dispor_vm(vm: Vm, por_chave: dict[str, No], nivel: int,
               arestas: tuple[tuple[str, str], ...] = ()) -> tuple[Caixa, list[Caixa]]:
    """Devolve a caixa da VM (moldura, sem preenchimento — ver arq_render) e
    a lista achatada dos produtos que ela contem (e seus descendentes), com
    coordenadas absolutas dentro do frame local da VM.

    Um produto listado em duas VMs (ex.: portal-gestao roda em `app2037` e
    tem schema em `suite-pg`) e desenhado DENTRO DE CADA UMA — e o mesmo
    fato de blast radius, sob dois angulos de infra diferentes — com chave
    prefixada pela VM (`app2037.portal-gestao` vs `suite-pg.portal-gestao`)
    pra nao colidir. `arq_render` resolve qual copia uma aresta usa.
    """
    contidos = [chave for chave in vm.contem if chave in por_chave]
    contidos = [contidos[i] for i in _ordem_por_afinidade(contidos, arestas)]
    sub = [
        _comprimir(*_dispor_no(por_chave[chave], f"{vm.chave}.{chave}", nivel + 1,
                               arestas, chave))
        for chave in contidos
    ]
    largura_conteudo, altura_conteudo, posicoes = _grade(
        [(caixa.w, caixa.h) for caixa, _ in sub])

    banda = banda_titulo(largura_conteudo, 0.02)
    largura_total = MARGEM * 2 + largura_conteudo
    altura_total = banda + MARGEM * 2 + altura_conteudo
    if not sub:
        # VM sem produto (motor2037, n8n2037, evolution2037): ainda precisa
        # de espaco pro nome + nota nao ficarem cortados.
        largura_total = max(largura_total, ITEM_W + MARGEM * 2)

    origem_x, origem_y = MARGEM, banda + MARGEM
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


def _aplicar_posicoes(caixas: list[Caixa],
                      a_mao: dict[str, tuple[float, float]]) -> list[Caixa]:
    """Soma os deslocamentos escritos a mao (`arquitetura.POSICOES`).

    O layout automatico acerta a estrutura e nao adivinha o que o dono quer
    ver perto do que. Ele arrasta a caixa na pagina, exporta, e cola o bloco
    em `arquitetura.py` — dali em diante a posicao e' DADO, versionada e
    commitada junto do resto, e `gerar_arquitetura.py --verificar` volta a
    valer. Sem isso, arrastar so vivia no localStorage de uma maquina.

    Deslocamento, nao coordenada absoluta: a caixa continua sendo colocada
    pelo empacotamento e so ANDA a partir dali. Assim, acrescentar um
    componente novo nao invalida o que ja foi arrumado a mao — a vizinhanca
    inteira se move junto e o ajuste continua valendo em cima dela.

    Mover um pai leva a subarvore (o filho vive em coordenada absoluta, nao
    relativa), e um deslocamento no filho SOMA ao do pai — a mesma regra do
    `deslocamentoDe` em arq_zoom.js, e as duas precisam continuar iguais.
    """
    if not a_mao:
        return caixas
    movidas = []
    for c in caixas:
        dx = dy = 0.0
        for chave, (mx, my) in sorted(a_mao.items()):
            if c.chave == chave or c.chave.startswith(chave + "."):
                dx += mx
                dy += my
        movidas.append(replace(c, x=c.x + dx, y=c.y + dy) if (dx or dy) else c)
    return movidas


def dispor(modelo: Modelo, grupos: tuple[Vm, ...],
           a_mao: dict[str, tuple[float, float]] | None = None) -> Cena:
    """`grupos` e o nivel 1 da cena: `modelo.vms` pra vista Arquitetura,
    `modelo.bancos` pra vista Schema (Task 9) — quem chama escolhe, porque
    so quem filtrou o modelo (`arq_modelo.filtrar`) sabe qual das duas vistas
    esta desenhando. Nada mais no empacotamento muda entre as duas vistas.

    modelo.nos ja vem ordenado por chave (arq_modelo.carregar itera
    `sorted(nos)`) — a ordem de construcao aqui e, portanto, ja
    deterministica; nao ha necessidade de reordenar por conta propria.

    A VM/banco e o novo nivel 1: uma Caixa tipo "vm" por item de `grupos`,
    envolvendo os produtos do seu `contem`. Produto que nao esta em nenhum
    grupo fica solto, no mesmo nivel — nao existe hoje nos dados reais (as
    seis produtos vivem em app2037), mas o modelo precisa aceitar.
    """
    a_mao = a_mao or {}
    por_chave_no = {no.chave: no for no in modelo.nos}
    contidos: set[str] = set()
    for vm in grupos:
        contidos.update(vm.contem)

    # `grupos` ja vem ordenado por chave (arq_modelo.carregar faz
    # `sorted(vms)`/`sorted(bancos)`, e `filtrar` preserva a ordem porque so
    # filtra o `contem`, nunca reordena os grupos).
    # As pontas de aresta vivem no espaco do modelo (sem prefixo de VM); o
    # layout so precisa de quem-com-quem, nunca do protocolo.
    arestas = tuple((a.de, a.para) for a in modelo.arestas)

    raizes = [_dispor_vm(vm, por_chave_no, 1, arestas) for vm in grupos]
    soltos = [no for no in modelo.nos if no.chave not in contidos]
    raizes += [_dispor_no(no, no.chave, 1, arestas, no.chave) for no in soltos]

    # VM sem produto (motor2037, n8n2037, evolution2037, suite-pg) saia do
    # _dispor_vm mal maior que o texto do titulo — um selo de 238x82 ao lado
    # de uma VM de 18824. Piso: no MINIMO 12% da maior VM em cada eixo, pra
    # ficar clicavel e legivel no nivel 1. So VM, nunca no solto (que ja tem
    # seu proprio tamanho de conteudo).
    #
    # Na pratica uso 30%, nao o minimo de 12%: com so 4 VMs vazias ao lado
    # de app2037 (que domina a area), 12% deixa a soma das 4 pequena demais
    # pra desafogar app2037 — o piso de k_min (1.6, defeito A) nunca fica
    # alcancavel para os filhos diretos de app2037 (cena/app2037.w ficava
    # ~1.50, abaixo de 1.6). 30% resolve com folga sem violar "no minimo
    # 12%" (test_vm_vazia_tem_tamanho_visivel so exige >=). Calibrado junto
    # com o 2.8 de `_grade`: os dois mudam quantas VMs cabem na mesma
    # prateleira de app2037, e so a combinacao dos dois fecha a conta.
    FRACAO_MIN_VM = 0.30
    larguras_vm = [c.w for c, _ in raizes if c.tipo == "vm"]
    alturas_vm = [c.h for c, _ in raizes if c.tipo == "vm"]
    piso_w = max(larguras_vm) * FRACAO_MIN_VM if larguras_vm else 0.0
    piso_h = max(alturas_vm) * FRACAO_MIN_VM if alturas_vm else 0.0
    raizes = [
        (replace(c, w=max(c.w, piso_w), h=max(c.h, piso_h)) if c.tipo == "vm" else c, desc)
        for c, desc in raizes
    ]

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
        # Piso 1.6: sem ele, um pai que domina a cena (app2037 e 97% da
        # largura) faz `0.6 * cena/pai` sair menor que o zoom inicial (k=1)
        # e o interior ja abre no primeiro quadro. Voce tem que entrar em
        # algo antes do interior dela abrir.
        k = round(max(1.6, 0.6 * (largura / pai.w)), 4) if pai.w else 0.0
        finais.append(replace(c, k_min=k, k_face=k))

    finais = _aplicar_posicoes(finais, a_mao)
    finais.sort(key=lambda c: c.chave)
    return Cena(caixas=tuple(finais), largura=largura, altura=altura)
