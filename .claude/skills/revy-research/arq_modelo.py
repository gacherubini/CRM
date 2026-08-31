"""Funde arquitetura.py + _frescor.json + decisoes/ num Modelo. Stdlib apenas.

Nao importa `app` de produto nenhum (AGENTS.md secao 5).

O modelo e RECURSIVO: um `No` pode ter `filhos`, sem profundidade fixa (dict
`dentro` no dict cru). So a RAIZ de NOS e cobrada contra o `_frescor.json` —
e la que moram os nomes de produto. Sub-no e estrutura de dominio (um canal
por loja, um worker, um modulo), nao produto, entao nao teria como existir
no frescor. A validacao de `decisoes/` vale em qualquer profundidade.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path

from varredura import Entrada


class ReferenciaMorta(Exception):
    """O arquitetura.py cita algo que nao existe mais.

    Erro, nunca aviso: referencia morta em silencio e exatamente como este
    arquivo apodreceria. Mesmo espirito do saude.citacoes_mortas.
    """


@dataclass(frozen=True)
class No:
    chave: str
    titulo: str
    papel: str
    vm: str | None = None
    termo: str | None = None
    modulo: str | None = None
    decisoes: tuple[str, ...] = ()
    spof: bool = False
    spof_porque: str | None = None
    # Vocabulario TECNICO de forma (31/08). O `papel` diz de que dominio a
    # caixa e' (conversa, venda, banco); `forma` diz o que ela E'
    # tecnicamente — fila, worker, cache, browser. Sao perguntas diferentes,
    # e a forma responde a segunda ANTES de voce ler o texto. Vazio = o
    # retangulo de sempre.
    forma: str = ""
    entradas: tuple[Entrada, ...] = ()
    filhos: tuple["No", ...] = ()
    auto: bool = False


@dataclass(frozen=True)
class Aresta:
    de: str
    para: str
    protocolo: str = "http"
    sincrono: bool = True
    retry: bool = False
    inferida: bool = False


@dataclass(frozen=True)
class Vm:
    chave: str
    tipo: str = "fly-machine"
    contem: tuple[str, ...] = ()
    nota: str = ""
    # Task 11 (a pele): so pra grupo com `contem` vazio — a forma interna
    # que a vocabulario de forma desenha quando nao ha produto Revy dentro
    # (worker Playwright do proprio Motor, n8n, evolution-api). `roda` e' o
    # rotulo (sai da `nota` que ja existia, nunca inventado); `terceiro`
    # escolhe elipse (software de terceiro) vs retangulo (software Revy).
    roda: str = ""
    terceiro: bool = False


@dataclass(frozen=True)
class Passo:
    no: str
    faz: str
    protocolo: str | None = None
    sincrono: bool = True


@dataclass(frozen=True)
class Fluxo:
    chave: str
    titulo: str
    passos: tuple[Passo, ...] = ()
    invariante: str | None = None


@dataclass(frozen=True)
class Modelo:
    nos: tuple[No, ...] = ()
    arestas: tuple[Aresta, ...] = ()
    vms: tuple[Vm, ...] = ()
    # Grupos de topo da vista Schema (Task 9) — mesma forma de `vms`, banco
    # em vez de maquina Fly. Vazio por padrao pra nao quebrar quem monta um
    # Modelo a mao sem se importar com Schema (a maioria dos testes antigos).
    bancos: tuple[Vm, ...] = ()
    fluxos: tuple[Fluxo, ...] = ()
    sha: str = ""


def _entradas_de(inventario: dict, produto: str) -> list[Entrada]:
    # sorted() aqui e no resto do modulo: layout deve ser determinstico, e a
    # ordem do JSON nao e contrato.
    brutas = inventario.get(produto, [])
    achatadas = [
        Entrada(secao=e["secao"], chave=e["chave"], simbolo=e["simbolo"],
                arquivo=e["arquivo"], linha=e["linha"])
        for e in brutas
    ]
    return sorted(achatadas, key=lambda e: (e.secao, e.chave, e.arquivo))


def _coletar_modulos(bruto: dict, caminho: tuple) -> list:
    """Lista `(modulo, caminho_do_no)` pra todo no do bruto que declara
    `modulo`, em qualquer profundidade. `caminho` vazio = a raiz do produto.

    Um no sem `modulo` (grupo de dominio, tipo "canais" ou "workers") nao
    entra aqui — mas isso NAO bloqueia os filhos dele, que sao percorridos
    do mesmo jeito. E assim que um sub-no sem modulo proprio deixa passar
    a competicao ate os netos.
    """
    resultado = []
    modulo = bruto.get("modulo")
    if modulo:
        resultado.append((modulo, caminho))
    dentro = bruto.get("dentro") or {}
    for subchave in dentro:
        resultado.extend(_coletar_modulos(dentro[subchave], caminho + (subchave,)))
    return resultado


def _designar_por_caminho(pool: list[Entrada], bruto_raiz: dict) -> dict:
    """Devolve `{caminho_do_no: [Entrada, ...]}` pra uma arvore inteira.

    Prefixo mais especifico (mais longo) ganha — e assim que
    `app/control/google_ads` (o sub-no) fica com a entrada em vez de
    `app/control/` (o pai dele) quando os dois casam o mesmo arquivo.
    Nada casando: fica na raiz (`caminho == ()`), nunca preso num
    intermediario sem `modulo`. `sorted()` no desempate por tamanho garante
    ordem deterministica mesmo com dois `modulo` do mesmo tamanho.
    """
    candidatos = sorted(
        _coletar_modulos(bruto_raiz, ()),
        key=lambda mc: (-len(mc[0]), mc[1]),
    )
    designacao: dict = {(): []}
    for e in pool:
        alvo = ()
        for modulo, caminho in candidatos:
            if e.arquivo.startswith(modulo):
                alvo = caminho
                break
        designacao.setdefault(alvo, []).append(e)
    return designacao


def _construir_no(chave: str, bruto: dict, caminho: tuple, designacao: dict,
                   pasta_decisoes: Path) -> No:
    decisoes = tuple(bruto.get("decisoes") or ())
    for d in decisoes:
        if not (pasta_decisoes / d).exists():
            raise ReferenciaMorta(
                f"no '{chave}' cita a decisao '{d}', que nao existe em decisoes/"
            )

    dentro = bruto.get("dentro") or {}
    filhos = tuple(
        _construir_no(subchave, dentro[subchave], caminho + (subchave,),
                      designacao, pasta_decisoes)
        for subchave in sorted(dentro)
    )
    entradas_aqui = tuple(sorted(
        designacao.get(caminho, []),
        key=lambda e: (e.secao, e.chave, e.arquivo),
    ))

    return No(
        chave=chave,
        titulo=bruto["titulo"],
        papel=bruto["papel"],
        vm=bruto.get("vm"),
        termo=bruto.get("termo"),
        modulo=bruto.get("modulo"),
        decisoes=decisoes,
        spof=bool(bruto.get("spof")),
        spof_porque=bruto.get("spof_porque"),
        forma=bruto.get("forma", ""),
        entradas=entradas_aqui,
        filhos=filhos,
    )


def _pilha_auto(entradas: list, nivel: int, chave_prefixo: str) -> list:
    """Constroi, recursivamente, a subarvore diretorio/arquivo pro que sobrou
    sem `modulo` casado a mao. `entradas` aqui todas compartilham o caminho
    ate `nivel` (exclusive).

    Colapso: enquanto TODAS as entradas tiverem o MESMO segmento em `nivel`
    e NENHUMA terminar exatamente ali (ainda ha caminho pela frente), avanca
    sem criar caixa pro segmento — e assim que `app/a/b/c.py` sozinho vira
    UM no (`c.py`), nao tres aninhados, e que um `modulo` que so cobre um
    arquivo (`app/followup_job.py`) nao aninha nada. So cria no quando ha
    DIVERGENCIA (mais de um segmento distinto) ou quando o segmento e' a
    ultima parte do caminho (nome de arquivo).
    """
    while True:
        primeiro = None
        todas_iguais = True
        alguma_termina = False
        for e in entradas:
            partes = e.arquivo.split("/")
            idx = min(nivel, len(partes) - 1)
            seg = partes[idx]
            if primeiro is None:
                primeiro = seg
            elif seg != primeiro:
                todas_iguais = False
            if idx == len(partes) - 1:
                alguma_termina = True
        if todas_iguais and not alguma_termina:
            nivel += 1
            continue
        break

    grupos: dict = {}
    for e in entradas:
        partes = e.arquivo.split("/")
        idx = min(nivel, len(partes) - 1)
        grupos.setdefault(partes[idx], []).append(e)

    filhos = []
    for seg in sorted(grupos):
        grupo = grupos[seg]
        # Sem prefixo vazio virando ".seg": o caminho do pai e
        # concatenado pelo arq_layout, entao repetir a chave do produto
        # aqui inflava todo id com o nome do produto duas vezes.
        chave = f"{chave_prefixo}.{seg}" if chave_prefixo else seg
        termina_todas = all(
            nivel >= len(e.arquivo.split("/")) - 1 for e in grupo
        )
        if termina_todas:
            filhos.append(No(
                chave=chave, titulo=seg, papel="arquivo", auto=True,
                entradas=tuple(sorted(
                    grupo, key=lambda e: (e.secao, e.chave, e.arquivo))),
            ))
        else:
            sub = _pilha_auto(grupo, nivel + 1, chave)
            filhos.append(No(
                chave=chave, titulo=seg, papel="modulo", auto=True,
                filhos=tuple(sorted(sub, key=lambda n: n.chave)),
            ))
    return filhos


def _construir_arvore_auto(entradas: list) -> tuple["No", ...]:
    """Constroi a floresta de nos automaticos do ZERO a partir de uma lista
    chata de entradas — nivel 0, sem prefixo de chave. Extraido pra ser
    reusado tanto por `_com_auto` (carregar) quanto por `filtrar` (Task 9),
    que precisa refazer os nos automaticos depois de podar secao: podar a
    arvore automatica antiga em vez de reconstrui-la deixa diretorio vazio
    pra tras (ver docstring de `filtrar`).

    `_pilha_auto` entra em loop infinito com lista vazia (o `while True`
    nunca acha `alguma_termina` numa lista sem elemento) — por isso a guarda
    aqui, no unico lugar que chama `_pilha_auto` de fora.
    """
    if not entradas:
        return ()
    return tuple(sorted(_pilha_auto(list(entradas), 0, ""), key=lambda n: n.chave))


def _com_auto(no: No) -> No:
    """Aplica a regra dos nos automaticos em toda a arvore (pos-ordem): um
    no com `modulo` escrito a mao ja tem dono, fica intocado. Um no SEM
    `modulo` que sobrou com entradas (hoje, so a raiz do produto — ver
    `_designar_por_caminho`) ganha a subarvore derivada do caminho, e suas
    proprias `entradas` esvaziam.
    """
    filhos = tuple(_com_auto(f) for f in no.filhos)
    if no.modulo or not no.entradas:
        return replace(no, filhos=filhos)
    auto_filhos = _construir_arvore_auto(list(no.entradas))
    todos = tuple(sorted(filhos + auto_filhos, key=lambda n: n.chave))
    return replace(no, entradas=(), filhos=todos)


def _entradas_da_arvore(no: No) -> list:
    """Achata `entradas` de `no` e de toda a subarvore abaixo dele, em
    ordem de visita. Usado por `filtrar` pra recolher o que uma subarvore
    automatica continha antes de refaze-la com a secao filtrada."""
    acc = list(no.entradas)
    for f in no.filhos:
        acc.extend(_entradas_da_arvore(f))
    return acc


def _todos_os_caminhos(nos, prefixo: str = "") -> set:
    """Todo endereco valido de nó, em qualquer profundidade, no formato
    pontuado que as arestas usam (`chatbot-api.workers.cloud-retry`).

    Os automaticos entram junto: eles sao endereçaveis do mesmo jeito, e
    proibir uma aresta de apontar pra um arquivo especifico seria uma regra
    sem motivo.
    """
    caminhos = set()
    for no in nos:
        caminho = f"{prefixo}.{no.chave}" if prefixo else no.chave
        caminhos.add(caminho)
        caminhos |= _todos_os_caminhos(no.filhos, caminho)
    return caminhos


def _construir_grupos(bruto: dict, conhecidos: set, rotulo: str) -> list:
    """Constroi `[Vm, ...]` a partir de um dict cru no formato de `VMS`/
    `BANCOS` (chave, tipo, contem, nota), validando que todo `contem` cite
    um no que existe. Reusado por `carregar` pros dois grupos de topo (VMs
    da Arquitetura, bancos da Schema) — o formato e identico, so muda o
    `rotulo` que entra na mensagem de erro ("vm" ou "banco").
    """
    grupos = []
    for chave in sorted(bruto or {}):
        b = (bruto or {})[chave]
        for dentro in b.get("contem", ()):
            if dentro not in conhecidos:
                raise ReferenciaMorta(
                    f"{rotulo} '{chave}' contem '{dentro}', que nao esta em NOS"
                )
        grupos.append(Vm(chave=chave, tipo=b.get("tipo", "fly-machine"),
                          contem=tuple(sorted(b.get("contem", ()))),
                          nota=b.get("nota", ""),
                          roda=b.get("roda", ""),
                          terceiro=bool(b.get("terceiro", False))))
    return grupos


def carregar(raiz: Path, frescor: dict, nos: dict,
             arestas: list = (), vms: dict = None,
             fluxos: dict = None, bancos: dict = None) -> Modelo:
    inventario = frescor.get("inventario", {})
    pasta_decisoes = Path(__file__).resolve().parent / "decisoes"

    construidos = []
    for chave in sorted(nos):
        bruto = nos[chave]
        if chave not in inventario:
            raise ReferenciaMorta(
                f"no '{chave}' nao existe no _frescor.json. "
                f"Produtos conhecidos: {', '.join(sorted(inventario))}"
            )
        pool = _entradas_de(inventario, chave)
        designacao = _designar_por_caminho(pool, bruto)
        raiz_no = _construir_no(chave, bruto, (), designacao, pasta_decisoes)
        construidos.append(_com_auto(raiz_no))

    conhecidos = {n.chave for n in construidos}
    # Aresta pode terminar numa VM, nao so num produto: "portal-gestao fala TCP
    # com suite-pg" e uma seta, nao contencao. Modelar isso como `contem` fazia
    # a arvore inteira do produto ser desenhada uma vez por VM.
    #
    # E pode terminar num SUB-NO, endereçado pelo caminho pontuado
    # (`chatbot-api.workers.cloud-retry`). Sem isso nao existe diagrama DENTRO
    # de um produto: so daria pra ligar produto a produto, e entrar num
    # produto continuaria mostrando caixas sem relacao nenhuma entre elas.
    # `arq_render._resolver_produto` ja casa por sufixo em qualquer
    # profundidade; era so a validacao de carga que parou na raiz.
    conhecidos_e_vms = _todos_os_caminhos(construidos) | set(vms or {})
    feitas = []
    for a in arestas or ():
        for ponta in ("de", "para"):
            if a[ponta] not in conhecidos_e_vms:
                raise ReferenciaMorta(
                    f"aresta {a['de']} -> {a['para']} usa '{a[ponta]}', "
                    "que nao e caminho de no em NOS (em nenhuma profundidade) "
                    "nem chave de VMS"
                )
        feitas.append(Aresta(
            de=a["de"], para=a["para"],
            protocolo=a.get("protocolo", "http"),
            sincrono=a.get("sincrono", True),
            retry=a.get("retry", False),
            inferida=a.get("inferida", False),
        ))
    feitas.sort(key=lambda a: (a.de, a.para, a.protocolo))

    maquinas = _construir_grupos(vms, conhecidos, "vm")
    bancos_construidos = _construir_grupos(bancos, conhecidos, "banco")

    caminhos = []
    for chave in sorted(fluxos or {}):
        b = (fluxos or {})[chave]
        passos = tuple(Passo(no=p["no"], faz=p["faz"],
                             protocolo=p.get("protocolo"),
                             sincrono=p.get("sincrono", True))
                       for p in b.get("passos", ()))
        caminhos.append(Fluxo(chave=chave, titulo=b["titulo"], passos=passos,
                              invariante=b.get("invariante")))

    return Modelo(nos=tuple(construidos), arestas=tuple(feitas),
                  vms=tuple(maquinas), bancos=tuple(bancos_construidos),
                  fluxos=tuple(caminhos), sha=frescor.get("sha", ""))


def _filtrar_arvore(no: No, secoes: frozenset) -> No:
    """Devolve `no` com so as `entradas` cuja `secao` esta em `secoes`, em
    qualquer profundidade.

    Um filho `auto=True` nao e podado no lugar: a subarvore automatica
    inteira e achatada (`_entradas_da_arvore`) e RECONSTRUIDA do zero
    (`_construir_arvore_auto`) a partir das entradas que sobraram do
    filtro. Podar a arvore automatica antiga em vez de refaze-la deixaria
    diretorio cujo conteudo inteiro foi filtrado pendurado como caixa
    vazia — exatamente o "no auto derivado do caminho do arquivo" que a
    Task 8 existe pra evitar.

    Filhos escritos a mao (`auto=False`) recursam normalmente; ficar sem
    conteudo e problema de `_podar`, nao daqui.
    """
    entradas_filtradas = tuple(e for e in no.entradas if e.secao in secoes)

    filhos_manuais = [f for f in no.filhos if not f.auto]
    filhos_auto = [f for f in no.filhos if f.auto]

    novos_manuais = [_filtrar_arvore(f, secoes) for f in filhos_manuais]

    novos_auto: tuple[No, ...] = ()
    if filhos_auto:
        entradas_auto = []
        for f in filhos_auto:
            entradas_auto.extend(_entradas_da_arvore(f))
        entradas_auto_filtradas = [e for e in entradas_auto if e.secao in secoes]
        novos_auto = _construir_arvore_auto(entradas_auto_filtradas)

    filhos_novos = tuple(sorted(novos_manuais + list(novos_auto),
                                key=lambda n: n.chave))
    return replace(no, entradas=entradas_filtradas, filhos=filhos_novos)


def _podar(no: No, manter_manuais: bool) -> No | None:
    """Regra 3 de `filtrar`. Devolve `None` quando o no inteiro sai.

    `manter_manuais` separa dois casos que a regra unica confundia:

    - **Vista Arquitetura (`True`)**: um componente escrito a mao E' o
      conteudo. "Canal Cloud (Meta)" nao tem entrada no inventario nenhuma
      — o inventario so conhece rota, worker, flag e template, e um canal
      nao e nada disso — mas a existencia dele e' justamente a afirmacao que
      a vista faz. Podar por ausencia de entrada apagava a camada de
      intencao inteira: os componentes estavam escritos em `arquitetura.py`
      desde a Task 3 e nunca chegaram a virar caixa. Era esse o motivo de
      entrar num produto mostrar arvore de arquivos.
    - **Vista Schema (`False`)**: aqui o conteudo E' a entrada (modelo,
      migration). Manter no vazio encheria a vista de moldura sem tabela
      dentro, e `catalogo-publico` (zero modelo, zero migration) tem mesmo
      que sumir dela.

    Um no `auto=True` nunca chega vazio aqui: ele so existe porque
    `_construir_arvore_auto` foi chamado com entradas de verdade (lista
    vazia devolve `()`, nunca um No).
    """
    filhos_podados = []
    for f in no.filhos:
        if f.auto:
            filhos_podados.append(f)
            continue
        podado = _podar(f, manter_manuais)
        if podado is not None:
            filhos_podados.append(podado)

    novo = replace(no, filhos=tuple(sorted(filhos_podados, key=lambda n: n.chave)))
    if manter_manuais:
        return novo
    if not novo.auto and not novo.entradas and not novo.filhos:
        return None
    return novo


def filtrar(modelo: Modelo, secoes: frozenset,
            manter_manuais: bool = False) -> Modelo:
    """Devolve um `Modelo` NOVO (funcao pura — os dataclasses sao frozen,
    nada aqui muta o `modelo` recebido) contendo so as entradas cuja
    `secao` esta em `secoes`.

    Regras, nesta ordem (ver Task 9 / docs/fila/2026-08-30-arquitetura-viva.md):

    1. Em todo no, em qualquer profundidade, mantem so as `entradas` cuja
       `secao` esta em `secoes` (`_filtrar_arvore`).
    2. Os nos automaticos (Task 8) sao refeitos do zero a partir das
       entradas que sobraram — nao apenas podados (`_construir_arvore_auto`
       reusada de `_com_auto`, ver o docstring dela pro porque).
    3. `_podar`, governado por `manter_manuais`. Com `False` (vista Schema),
       um no escrito a mao sem `entradas` e sem filho com conteudo sai do
       modelo, e um no de raiz que caia nessa regra sai tambem — e o caso do
       `catalogo-publico` (zero `modelo`/`migration`). Com `True` (vista
       Arquitetura), componente escrito a mao fica mesmo sem entrada: ali ele
       E' o conteudo. Ver o docstring de `_podar`.
    4. `arestas` e `fluxos` que citem um no podado saem junto.
    5. `vms` e `bancos`: o `contem` de cada grupo perde as chaves podadas.
       Um grupo que fica com `contem` vazio CONTINUA no modelo — `motor2037`
       e `n8n2037` ja sao legitimamente vazios hoje (ver a `nota` deles em
       `arquitetura.py`), e a vista Schema depende do mesmo comportamento
       pra bancos como `motor-db` que podem ficar sem produto.

    NAO valida secao desconhecida aqui. Essa checagem mora em
    `gerar_arquitetura.py` (`_avisar_secoes_desconhecidas`), que e quem
    enxerga as duas vistas (`SECOES_ARQUITETURA` + `SECOES_SCHEMA`) juntas
    antes de decidir se uma secao do inventario nao caiu em nenhuma delas —
    aqui dentro so se conhece o conjunto que a chamada corrente pediu, o que
    faria toda secao fora dele (inclusive a da OUTRA vista) soar como
    desconhecida.
    """
    filtrados = [_filtrar_arvore(no, secoes) for no in modelo.nos]
    podados = [_podar(no, manter_manuais) for no in filtrados]
    nos_novos = tuple(n for n in podados if n is not None)

    chaves_removidas = {no.chave for no in modelo.nos} - {n.chave for n in nos_novos}

    arestas_novas = tuple(
        a for a in modelo.arestas
        if a.de not in chaves_removidas and a.para not in chaves_removidas
    )
    fluxos_novos = tuple(
        f for f in modelo.fluxos
        if not any(p.no in chaves_removidas for p in f.passos)
    )
    vms_novas = tuple(
        replace(v, contem=tuple(c for c in v.contem if c not in chaves_removidas))
        for v in modelo.vms
    )
    bancos_novos = tuple(
        replace(b, contem=tuple(c for c in b.contem if c not in chaves_removidas))
        for b in modelo.bancos
    )

    return replace(modelo, nos=nos_novos, arestas=arestas_novas,
                    vms=vms_novas, bancos=bancos_novos, fluxos=fluxos_novos)


# --------------------------------------------------------------------------
# Contagem de flag (31/08) — a parede que sobrou depois da `template` sair.
# --------------------------------------------------------------------------

_ROLLOUT_OFF = re.compile(r"\(default: (?:0|'')\)$")

# Abaixo disto a lista ainda se le, e ler as duas flags do Motor vale mais
# que contar ate dois. Acima, vira parede: o `config.py` do Control chegava a
# 42 fichas empilhadas numa coluna so.
LIMIAR_FLAG = 4


def agrupar_flags(modelo: "Modelo", limiar: int = LIMIAR_FLAG) -> "Modelo":
    """Troca uma pilha de `flag` por UMA ficha que conta.

    O dono olhou o `config.py` do Control — 59 fichas de env empilhadas — e
    disse que aquilo tinha que ser mostrado de outra forma. E' o mesmo caso
    da `rota` e da `template`: a parede responde QUAIS existem, e esta pagina
    pergunta como as partes se falam.

    O rotulo diz duas coisas, e nao uma, porque o extrator mente um pouco: a
    secao se chama `flag`, mas o que ele emite e' TODA variavel de ambiente —
    `REVY_TRAFEGO_TIMEZONE` esta no meio. Das 59 do Control, so 19 sao flag
    de rollout de verdade (`default: 0` ou `''`). Escrever "59 flags, todas
    default OFF" seria uma mentira que o desenho afirma sozinho; entao o
    rotulo separa as duas contas, e e' justamente a segunda que interessa a
    invariante do AGENTS.md secao 5 (rollout nasce OFF no codigo).

    Funcao pura, como `filtrar`: devolve um `Modelo` novo. O dado inteiro
    continua em `mapa/<produto>.md`.
    """
    return replace(modelo, nos=tuple(_agrupar_flags_no(n, limiar)
                                     for n in modelo.nos))


def _agrupar_flags_no(no: "No", limiar: int) -> "No":
    flags = [e for e in no.entradas if e.secao == "flag"]
    filhos = tuple(_agrupar_flags_no(f, limiar) for f in no.filhos)
    if len(flags) < limiar:
        return replace(no, filhos=filhos)

    resto = tuple(e for e in no.entradas if e.secao != "flag")
    off = sum(1 for e in flags if _ROLLOUT_OFF.search(e.chave))
    rotulo = f"{len(flags)} env"
    if off:
        rotulo += f" · {off} rollout OFF"
    arquivos = {e.arquivo for e in flags}
    # Um arquivo so: vale nomear (quase sempre `app/config.py`). Varios: o
    # numero, porque listar tres caminhos e' voltar a ser a parede.
    onde = arquivos.pop() if len(arquivos) == 1 else f"{len(arquivos)} arquivos"
    # `linha=0` e' o combinado com `arq_layout._caixa_item`: ficha sintetica
    # nao tem linha, e o subtitulo sai sem o `:0`.
    contagem = Entrada(secao="flag", chave=rotulo, simbolo=rotulo,
                       arquivo=onde, linha=0)
    return replace(no, entradas=resto + (contagem,), filhos=filhos)


# --------------------------------------------------------------------------
# Task 14 — a vista Schema vira mapa CONCEITUAL de banco.
# --------------------------------------------------------------------------

def como_mapa_conceitual(modelo: "Modelo", relacoes: dict,
                         colunas: dict | None = None) -> "Modelo":
    """Reescreve a vista Schema: uma caixa por TABELA, ligadas por FK.

    Antes daqui a Schema era a arvore de arquivo outra vez, e pior que a da
    Arquitetura: o Chatbot abria com 28 caixas de migration de UMA ficha cada
    (as tais que "abrem vazias") e as 19 tabelas espremidas como pilulas
    dentro de uma caixa chamada `models_db.py`. Nao dava pra ver o que um
    mapa de banco existe pra mostrar — quem aponta pra quem, e quantos.

    Agora cada tabela e' uma caixa e cada FK e' uma seta ROTULADA com a
    cardinalidade que o SQLAlchemy ja declarava (`extratores.relacoes`).

    As 28 migrations viram UMA caixa com a contagem e o head. Elas sao
    HISTORIA de como o schema chegou aqui, nao a forma dele — e a pergunta
    desta vista e' a forma. O `mapa/<produto>.md` continua listando todas.

    Funcao pura, no mesmo molde de `filtrar` e `agrupar_flags`.
    """
    nos_novos = []
    arestas_novas: list[Aresta] = []
    for no in modelo.nos:
        tabelas, migrations = _colher(no)
        if not tabelas and not migrations:
            nos_novos.append(no)
            continue
        por_tabela = _colunas_por_tabela((colunas or {}).get(no.chave, ()))
        filhos = [
            No(chave=t.chave, titulo=t.chave, papel="tabela",
               termo=f"{t.arquivo}:{t.linha}", auto=True,
               entradas=por_tabela.get(t.chave, ()))
            for t in sorted(tabelas, key=lambda e: e.chave)
        ]
        if migrations:
            nomes = sorted(e.chave for e in migrations)
            filhos.append(No(
                chave="migrations", titulo="migrations", papel="migration",
                auto=True,
                termo=f"{len(nomes)} até {nomes[-1]}"))
        nos_novos.append(replace(no, filhos=tuple(filhos), entradas=()))
        arestas_novas.extend(_arestas_de_relacao(
            no.chave, relacoes.get(no.chave, ()), {t.chave for t in tabelas}))
    return replace(modelo, nos=tuple(nos_novos), arestas=tuple(arestas_novas))


def _colunas_por_tabela(colunas) -> dict:
    """`{tabela: (Entrada, ...)}` com uma ficha por atributo.

    O dono olhou uma caixa de tabela vazia e disse "isso nao diz nada pra
    mim" — e estava certo: um mapa conceitual sem os atributos e' uma lista
    de nomes de tabela com setas.

    A ficha usa `simbolo` como subtitulo (via `arq_layout._caixa_item`), e nao
    o `arquivo:linha` de sempre. E' a unica secao que faz isso, e faz porque
    o que interessa numa coluna e' o TIPO e o papel dela (PK, FK, nulo) — o
    arquivo e' o mesmo pra todas as colunas da tabela, e repeti-lo 48 vezes
    dentro de `leads` nao ajudaria ninguem. A tabela ja carrega o
    `arquivo:linha` no proprio termo.

    A ordem e' a do ARQUIVO, nunca alfabetica: quem escreveu o modelo pos a
    PK primeiro e os carimbos de tempo no fim, e isso e' informacao.
    """
    saida: dict = {}
    for c in colunas:
        marcas = []
        if c["pk"]:
            marcas.append("PK")
        if c["fk_para"]:
            marcas.append(f"FK {c['fk_para']}")
        if c["unico"] and not c["pk"]:
            marcas.append("único")
        if c["nulo"]:
            marcas.append("nulo")
        detalhe = " · ".join([c["tipo"] or "?"] + marcas)
        saida.setdefault(c["tabela"], []).append(Entrada(
            secao="coluna", chave=c["nome"], simbolo=detalhe,
            arquivo=c["arquivo"], linha=c["linha"]))
    return {t: tuple(v) for t, v in saida.items()}


def _colher(no: "No") -> tuple[list, list]:
    """Todas as entradas de `modelo` e de `migration` da subarvore, em duas
    listas. Recursivo porque hoje elas estao enterradas na arvore de
    diretorio (`app > models_db.py`, `alembic > versions > ...`)."""
    tabelas = [e for e in no.entradas if e.secao == "modelo"]
    migrations = [e for e in no.entradas if e.secao == "migration"]
    for f in no.filhos:
        t, m = _colher(f)
        tabelas.extend(t)
        migrations.extend(m)
    return tabelas, migrations


def _arestas_de_relacao(produto: str, relacoes, tabelas: set) -> list:
    """Uma seta por FK, com a cardinalidade no rotulo.

    Descarta relacao cuja ponta nao virou caixa (tabela declarada num arquivo
    que a varredura nao le, ou FK apontando pra fora do produto): seta pro
    vazio e' pior que seta ausente — e' a mesma regra da camada de
    componente.

    `sincrono=True` sempre: aqui a seta nao fala de execucao, fala de forma.
    Tracejado nesta vista diria "assincrono", que nao quer dizer nada sobre
    uma chave estrangeira.
    """
    vistas = set()
    saida = []
    for r in relacoes:
        de, para = r["de"], r["para"]
        if de not in tabelas or para not in tabelas or de == para:
            continue
        # Duas FK entre as mesmas tabelas (mensagens tem `loja_id` e
        # `canal_id`) dao UMA seta: o mapa conceitual responde "estas duas se
        # ligam, e quantos", e nao "por quantas colunas".
        alvo = r["cardinalidade"]
        if r["opcional"]:
            alvo = alvo.replace(":1", ":0..1")
        chave = (de, para, alvo)
        if chave in vistas:
            continue
        vistas.add(chave)
        saida.append(Aresta(de=f"{produto}.{de}", para=f"{produto}.{para}",
                            protocolo=alvo, sincrono=True, retry=True))
    return saida
