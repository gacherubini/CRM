"""Roteamento ortogonal de aresta que DESVIA de caixa. Stdlib apenas, puro.

Antes (Task 11) toda seta era "sai pela borda mais proxima, um cotovelo
duplo no meio, entra pela borda oposta". Dava segmento horizontal ou
vertical por construcao, mas nada impedia o meio do caminho de atravessar
a caixa de um terceiro: a seta Catalogo -> Estoque cortava o Chatbot inteiro
de lado a lado, e as duas `tcp` Loja/Control -> suite-pg desenhavam um
retangulo fantasma por cima da Loja. O dono olhou e disse que estava feio.

Aqui a seta anda numa GRADE DE CORREDORES: as retas verticais e horizontais
a `folga` de distancia de cada borda de cada obstaculo (mais as retas dos
dois pontos de porta). Um segmento entre dois pontos vizinhos da grade so
existe se nao cruzar o interior de nenhum obstaculo. Dijkstra com custo =
comprimento + `PENA_COTOVELO` por mudanca de direcao — menos dobra ganha de
caminho mais curto, porque uma seta com quatro dobras e' ilegivel mesmo
quando nao cruza nada.

Determinismo (o HTML e' commitado e `--verificar` compara byte a byte):
a grade sai de `sorted()`, os vizinhos sao visitados em ordem fixa e o heap
desempata por (custo, n_dobras, indice de insercao). Duas execucoes dao a
mesma polyline.

`arq_zoom.js` tem a MESMA conta em JavaScript (`rotear` la dentro), pra
seta acompanhar a caixa enquanto voce arrasta. Se mudar a regra aqui, mude
la — e' o preco de a seta seguir a mao.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass

Ponto = tuple[float, float]


@dataclass(frozen=True)
class Ret:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


# Quanto uma dobra custa, em unidades de cena. Calibrado no navegador: 90
# faz a seta preferir um corredor a mais em vez de zigue-zague, sem
# nunca escolher uma volta de 200 unidades so pra poupar uma dobra.
PENA_COTOVELO = 90.0

_LADO_OPOSTO = {"direita": "esquerda", "esquerda": "direita",
                "cima": "baixo", "baixo": "cima"}


def lado_saida(de: Ret, para: Ret) -> str:
    """Borda de `de` que olha pra `para`. A mesma regra de sempre: o eixo com
    maior distancia entre centros decide."""
    dx = para.cx - de.cx
    dy = para.cy - de.cy
    if abs(dx) >= abs(dy):
        return "direita" if dx >= 0 else "esquerda"
    return "baixo" if dy >= 0 else "cima"


def ponto_borda(c: Ret, lado: str, deslocamento: float) -> Ponto:
    if lado == "direita":
        return c.x + c.w, c.y + c.h / 2 + deslocamento
    if lado == "esquerda":
        return c.x, c.y + c.h / 2 + deslocamento
    if lado == "baixo":
        return c.x + c.w / 2 + deslocamento, c.y + c.h
    return c.x + c.w / 2 + deslocamento, c.y  # "cima"


def _afastar(p: Ponto, lado: str, folga: float) -> Ponto:
    x, y = p
    if lado == "direita":
        return x + folga, y
    if lado == "esquerda":
        return x - folga, y
    if lado == "baixo":
        return x, y + folga
    return x, y - folga


def _cruza(p1: Ponto, p2: Ponto, r: Ret, eps: float = 0.01) -> bool:
    """Segmento ortogonal contra o INTERIOR de um retangulo (borda nao
    conta — a grade passa a `folga` da borda, entao encostar e' impossivel,
    mas o teste por interior estrito e' o que deixa a regra honesta)."""
    (x1, y1), (x2, y2) = p1, p2
    if abs(y1 - y2) < eps:
        return (r.y + eps < y1 < r.y + r.h - eps) and not (
            max(x1, x2) <= r.x + eps or min(x1, x2) >= r.x + r.w - eps)
    if abs(x1 - x2) < eps:
        return (r.x + eps < x1 < r.x + r.w - eps) and not (
            max(y1, y2) <= r.y + eps or min(y1, y2) >= r.y + r.h - eps)
    return True  # diagonal nunca deveria chegar aqui


def _simplificar(pontos: list[Ponto]) -> list[Ponto]:
    """Tira ponto colinear: a grade produz muitos vertices no meio de um
    segmento reto, e o SVG nao precisa deles."""
    if len(pontos) < 3:
        return pontos
    saida = [pontos[0]]
    for i in range(1, len(pontos) - 1):
        (x0, y0), (x1, y1), (x2, y2) = saida[-1], pontos[i], pontos[i + 1]
        horizontal = abs(y0 - y1) < 0.01 and abs(y1 - y2) < 0.01
        vertical = abs(x0 - x1) < 0.01 and abs(x1 - x2) < 0.01
        if not (horizontal or vertical):
            saida.append(pontos[i])
    saida.append(pontos[-1])
    return saida


def _pontos_ortogonais(p1: Ponto, lado1: str, p2: Ponto) -> list[Ponto]:
    """O cotovelo duplo de sempre: e' o caminho quando nao ha obstaculo
    nenhum, e o plano B quando a grade nao acha caminho."""
    x1, y1 = p1
    x2, y2 = p2
    if lado1 in ("esquerda", "direita"):
        xm = (x1 + x2) / 2
        return [(x1, y1), (xm, y1), (xm, y2), (x2, y2)]
    ym = (y1 + y2) / 2
    return [(x1, y1), (x1, ym), (x2, ym), (x2, y2)]


def _relevantes(de: Ret, para: Ret, obstaculos: list[Ret], folga: float) -> list[Ret]:
    """So obstaculo que encosta na caixa envolvente das duas pontas (mais
    quatro folgas) entra na GRADE. O resto so' engordaria a grade: na Schema
    um banco tem 32 tabelas, e cada aresta olhando pras 32 fazia a geracao
    levar segundos. A colisao, essa, e' testada contra TODOS — um caminho
    que saia da caixa envolvente nao pode atravessar quem ficou de fora."""
    x0 = min(de.x, para.x) - folga * 4
    y0 = min(de.y, para.y) - folga * 4
    x1 = max(de.x + de.w, para.x + para.w) + folga * 4
    y1 = max(de.y + de.h, para.y + para.h) + folga * 4
    return [r for r in obstaculos
            if not (r.x + r.w < x0 or r.x > x1 or r.y + r.h < y0 or r.y > y1)]


def rotear(de: Ret, para: Ret, obstaculos: list[Ret],
           folga: float = 24.0, deslocamento: float = 0.0) -> list[Ponto]:
    """Polyline ortogonal de `de` ate `para` sem cruzar `obstaculos`.

    `obstaculos` NAO deve conter `de` nem `para` (nem ancestral delas —
    sair de dentro de uma moldura obriga a cruzar a moldura). Quem chama
    escolhe; aqui e' geometria pura.

    `deslocamento` espalha varias setas que saem da mesma borda, como antes.
    """
    lado_de = lado_saida(de, para)
    lado_para = _LADO_OPOSTO[lado_de]
    p1 = ponto_borda(de, lado_de, deslocamento)
    p2 = ponto_borda(para, lado_para, 0.0)

    def _dentro(r: Ret, c: Ret) -> bool:
        return (r.x >= c.x - 0.01 and r.y >= c.y - 0.01
                and r.x + r.w <= c.x + c.w + 0.01 and r.y + r.h <= c.y + c.h + 0.01)

    todos = [r for r in obstaculos if not _dentro(r, para) and not _dentro(r, de)]
    obs = _relevantes(de, para, todos, folga)
    simples = _pontos_ortogonais(p1, lado_de, p2)
    if not todos or not any(_cruza(a, b, r) for a, b in zip(simples, simples[1:]) for r in todos):
        return _simplificar(simples)

    # Portas afastadas da borda: o primeiro e o ultimo segmento sao sempre
    # perpendiculares a borda, saindo da caixa — e por isso nao podem
    # cruzar a propria caixa nem precisam estar na grade.
    a = _afastar(p1, lado_de, folga)
    b = _afastar(p2, lado_para, folga)

    xs = {a[0], b[0]}
    ys = {a[1], b[1]}
    for r in obs + [de, para]:
        xs.update((r.x - folga, r.x + r.w + folga))
        ys.update((r.y - folga, r.y + r.h + folga))
    xs_l = sorted(xs)
    ys_l = sorted(ys)
    ix = {x: i for i, x in enumerate(xs_l)}
    iy = {y: i for i, y in enumerate(ys_l)}

    # As proprias pontas tambem bloqueiam: sem isto o caminho podia
    # atravessar `de` pra sair pelo outro lado dela. E TODOS os obstaculos
    # bloqueiam, nao so os da grade — ver `_relevantes`.
    bloqueio = todos + [de, para]

    def livre(p: Ponto, q: Ponto) -> bool:
        return not any(_cruza(p, q, r) for r in bloqueio)

    inicio = (ix[a[0]], iy[a[1]])
    fim = (ix[b[0]], iy[b[1]])
    # Estado = (coluna, linha, direcao de chegada). A direcao entra no
    # estado porque o custo da dobra depende de por onde se chegou.
    DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
    melhor: dict = {}
    fila: list = []
    contador = 0
    heapq.heappush(fila, (0.0, 0, contador, inicio, None, None))
    anterior: dict = {}
    achado = None
    while fila:
        custo, dobras, _, no, direcao, veio_de = heapq.heappop(fila)
        chave = (no, direcao)
        if chave in melhor:
            continue
        melhor[chave] = custo
        anterior[chave] = veio_de
        if no == fim:
            achado = chave
            break
        cx, cy = no
        for d in DIRS:
            nx, ny = cx + d[0], cy + d[1]
            if not (0 <= nx < len(xs_l) and 0 <= ny < len(ys_l)):
                continue
            p, q = (xs_l[cx], ys_l[cy]), (xs_l[nx], ys_l[ny])
            if not livre(p, q):
                continue
            passo = abs(q[0] - p[0]) + abs(q[1] - p[1])
            dobra = 1 if (direcao is not None and direcao != d) else 0
            novo = custo + passo + PENA_COTOVELO * dobra
            prox = ((nx, ny), d)
            if prox in melhor:
                continue
            contador += 1
            heapq.heappush(fila, (novo, dobras + dobra, contador, (nx, ny), d, chave))

    if achado is None:
        return _simplificar(simples)

    caminho: list[Ponto] = []
    atual = achado
    while atual is not None:
        (cx, cy), _ = atual
        caminho.append((xs_l[cx], ys_l[cy]))
        atual = anterior[atual]
    caminho.reverse()
    return _simplificar([p1] + caminho + [p2])
