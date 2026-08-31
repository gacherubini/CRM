"""Recorte de um produto, pra conferir o interior no navegador. Stdlib apenas.

    python3 -m http.server 8899 &
    python3 recorte_produto.py motor-simulacao
    # abra http://127.0.0.1:8899/recorte-motor-simulacao.html

POR QUE ISTO EXISTE, e nao "e' so dar zoom pelo DOM": a automacao de navegador
ve a aba em SEGUNDO PLANO. La `document.hidden` e' true, o
`requestAnimationFrame` nao roda e o compositor nao repinta — mexer no viewBox
pelo DOM muda o atributo e o screenshot volta do quadro antigo, sem erro
nenhum no console. So NAVEGACAO repinta. Entao o recorte ja nasce com o
viewBox no lugar.

E `data-k-min`/`data-face-ate` sao RENOMEADOS de proposito: sao os dois
atributos que o `arq_zoom.js` le pra decidir o nivel de detalhe, e sem
renomear eles o JS esconde o interior antes do primeiro quadro.

Efeito colateral esperado do recorte, que NAO e' defeito da pagina: com o LOD
desligado a face (titulo, subtitulo, selo SPOF) aparece JUNTO com o interior,
e as duas coisas se sobrepoem. Na pagina de verdade elas nunca convivem —
`k_face == k_min`, entao a face apaga no mesmo ponto em que o interior acende.
Nao "conserte" essa sobreposicao.

O que conferir no recorte: as caixas legiveis, e o subtitulo de cada uma
terminando no `arquivo:linha` SEM "…" no fim (termo cortado esconde a propria
prova, em silencio — `TestProvaCabeNaCaixa` guarda isso).

O hover nao da pra ver aqui: aresta interna nasce apagada e so acende sob o
mouse. Confira na pagina inteira, disparando o evento e lendo o atributo
`style` INLINE — `getComputedStyle(el).opacity` devolve o MEIO da transicao
(learnings/2026-08-30-getcomputedstyle-le-o-meio-da-transicao.md).
"""
import json
import re
import sys

sys.path.insert(0, ".")
from pathlib import Path
import arq_modelo, arq_layout, arquitetura, gerar_arquitetura

alvo = sys.argv[1]
vista = sys.argv[2] if len(sys.argv) > 2 else "arquitetura"
frescor = json.loads(gerar_arquitetura.FRESCOR.read_text(encoding="utf-8"))
completo = arq_modelo.carregar(
    Path("../../.."), frescor, arquitetura.NOS,
    arquitetura.ARESTAS + arquitetura.ARESTAS_INTERNAS,
    arquitetura.VMS, arquitetura.FLUXOS, arquitetura.BANCOS)
if vista == "schema":
    m = arq_modelo.como_mapa_conceitual(
        arq_modelo.filtrar(completo, arquitetura.SECOES_SCHEMA),
        frescor.get("relacoes", {}))
else:
    m = arq_modelo.agrupar_flags(arq_modelo.filtrar(
        completo, arquitetura.SECOES_ARQUITETURA, manter_manuais=True))
cena = arq_layout.dispor(m, m.vms, arquitetura.POSICOES)
caixa = next(c for c in cena.caixas if c.chave.endswith(alvo))
m = 4
vb = f"{caixa.x-m} {caixa.y-m} {caixa.w+2*m} {caixa.h+2*m}"

doc = open("arquitetura.html", encoding="utf-8").read()
i = doc.index(f'<svg id="mapa-{vista}"')
j = doc.index("</svg>", i) + 6
svg = doc[i:j]
# na pagina a vista inativa sai com `hidden`; no recorte ela E a vista
svg = svg.replace(" hidden>", ">", 1)
svg = re.sub(r'viewBox="[^"]*"', f'viewBox="{vb}"', svg, count=1)
svg = svg.replace("data-k-min", "x-k-min").replace("data-face-ate", "x-face-ate")
svg = svg.replace(f'<svg id="mapa-{vista}"',
                  f'<svg id="mapa-{vista}" width="1360" height="820"', 1)
est = doc[doc.index("<style>"):doc.index("</style>") + 8]
open(f"recorte-{vista}-{alvo}.html", "w", encoding="utf-8").write(
    "<!doctype html><meta charset=utf-8>" + est +
    "<body style='margin:0;background:#fff'>" + svg + "</body>")
print(f"recorte-{vista}-{alvo}.html  viewBox={vb}")
