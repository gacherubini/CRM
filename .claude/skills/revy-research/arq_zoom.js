// Motor de zoom continuo. Nao sabe o que e um produto — so caixas e viewBox.
//
// Task 10: fabrica em vez de singleton. Com duas vistas (Arquitetura e
// Schema) na mesma pagina, cada uma tem o seu proprio <svg> e precisa do
// proprio estado (svg, base, atual, pilha, arrastando...) — um singleton
// faria as duas vistas dividirem zoom e historico de navegacao.
window.Zoom = {
  criar: function (elemento, opts) {
    var svg = elemento;
    var base, atual = null, anim = null, dur = 450, moveu = false;
    var saindo = null;   // foco anterior, vivo so enquanto a camera voa
    var pilha = [];   // caminho de volta: ids ja visitados

    // Task 11 — a tremida do rabisco (feTurbulence + feDisplacementMap) e'
    // em UNIDADES DE CENA, mas tem que parecer do MESMO TAMANHO NA TELA em
    // qualquer zoom. px_por_unidade escala linear com k (k = base.w/v.w,
    // viewBox encolhendo = mais px por unidade): px_por_unidade(k) = k *
    // px_por_unidade0, onde px_por_unidade0 e' medido UMA VEZ na visao
    // inicial (k=1). Daí:
    //   deslocamento em unidades = ALVO_PX / px_por_unidade(k)
    //                             = (ALVO_PX / px_por_unidade0) / k  ->  C1/k
    //   baseFrequency (ciclos/unidade) precisa CRESCER com k pro "grao" do
    //   ruido ficar constante em pixel: CICLOS_POR_PX * px_por_unidade(k)
    //                             = (CICLOS_POR_PX * px_por_unidade0) * k -> C2*k
    // Os dois constantes (C1, C2) saem de medir o svg UMA vez, nao de
    // reflow a cada quadro (getBoundingClientRect a cada frame custaria
    // caro — ver "custo" abaixo).
    var ALVO_PX_DESLOC = 2.2;    // tremida alvo, em pixel de tela: "levemente rabiscado"
    var CICLOS_POR_PX = 0.045;   // grao do ruido: ~1 ciclo a cada 22px de tela
    var pxPorUnidade0 = 1, c1 = 0, c2 = 0, medido_visivel = false;
    var filtroDesloc = document.getElementById("rabisco-deslocamento");
    var filtroTurb = document.getElementById("rabisco-turbulencia");
    var K_LIMIAR_FILTRO = 26; // acima disso a caixa e' grande na tela e a
    // tremida some visualmente — desliga o filtro (medido no navegador,
    // ver relatorio da Task 11: cena real ~1600 formas, 60fps parado,
    // ~45fps durante o voo SEM este corte, fluido com ele).

    // A vista que nao abre nasce com `hidden`, e um elemento em display:none
    // mede 0. Cair no `base.w` fazia px_por_unidade valer 1 em vez de ~0.15:
    // a tremida da vista Schema saia 7x menor que a da Arquitetura, e o grao
    // do ruido 7x mais fino. Enquanto a medida nao for tirada com o svg na
    // tela ela fica marcada como provisoria, e a primeira pintura visivel
    // remede.
    function medirPxPorUnidade() {
      var r = svg.getBoundingClientRect();
      medido_visivel = r.width > 0;
      pxPorUnidade0 = (r.width || window.innerWidth || base.w) / base.w;
      c1 = ALVO_PX_DESLOC / pxPorUnidade0;
      c2 = CICLOS_POR_PX * pxPorUnidade0;
    }

    function aplicarFiltro(k) {
      if (!medido_visivel) medirPxPorUnidade();
      if (filtroDesloc) filtroDesloc.setAttribute("scale", (c1 / k).toFixed(3));
      if (filtroTurb) filtroTurb.setAttribute("baseFrequency", (c2 * k).toFixed(5));
      svg.classList.toggle("k-alto", k > K_LIMIAR_FILTRO);
    }

    function vb(el) {
      var p = el.getAttribute("viewBox").split(/[ ,]+/).map(Number);
      return { x: p[0], y: p[1], w: p[2], h: p[3] };
    }
    function setVb(v) {
      svg.setAttribute("viewBox", v.x + " " + v.y + " " + v.w + " " + v.h);
      var k = base.w / v.w;
      aplicarLod(k);
      aplicarFiltro(k);
    }
    // cubic-bezier(.4,0,.2,1) — aproximacao por Newton nao vale a pena aqui.
    function suavizar(t) { return t < 0.5 ? 4*t*t*t : 1 - Math.pow(-2*t + 2, 3) / 2; }

    // Trava de linhagem. Escala sozinha nao basta: caixas irmas de tamanho
    // parecido tem k_min parecido, entao entrar no Chatbot abria o interior
    // do Portal ao lado — o nivel 1 deixava de ser escopo. O interior de um
    // no so pode acender se ele estiver no caminho do foco:
    //
    //   - o proprio foco, ou um ancestral dele  -> a trilha que voce desceu
    //   - um filho DIRETO do foco               -> um nivel de antecipacao,
    //     que e' o que mantem a sensacao de cair dentro em vez de piscar
    //
    // Sem foco (`atual` null) o foco e' a raiz, e os filhos diretos dela sao
    // os nos de topo (id sem ponto). E' por isso que a primeira tela mostra
    // as maquinas com os produtos dentro, e nada alem disso.
    //
    // Os ids sao caminhos pontuados (`app2037.chatbot-api.app.main.py`),
    // entao tudo isso e' teste de prefixo. O ponto no `dono + "."` e'
    // obrigatorio: sem ele `chatbot-api` casaria com `chatbot-apix`.
    function noCaminhoDe(foco, dono) {
      if (foco === dono) return true;
      if (foco && foco.indexOf(dono + ".") === 0) return true;
      var resto = null;
      if (foco === "") resto = dono;
      else if (dono.indexOf(foco + ".") === 0) resto = dono.slice(foco.length + 1);
      return resto !== null && resto.indexOf(".") === -1;
    }

    // Durante o voo vale a UNIAO das duas linhagens, a de onde voce saiu e a
    // de onde voce esta chegando. Sem isso o interior que fica para tras
    // apaga de uma vez no primeiro quadro, em vez de sair pela rampa de
    // escala junto com a camera — vira um estalo no meio da animacao.
    function naLinhagem(dono) {
      if (dono === null) return true;
      if (noCaminhoDe(atual || "", dono)) return true;
      return saindo !== null && noCaminhoDe(saindo || "", dono);
    }

    function aplicarLod(k) {
      // ENTRA: o interior do no aparece conforme voce se aproxima — e so se
      // ele estiver na linhagem do foco.
      var grupos = svg.querySelectorAll("[data-k-min]");
      for (var i = 0; i < grupos.length; i++) {
        var kmin = parseFloat(grupos[i].getAttribute("data-k-min"));
        // Rampa: invisivel em kmin, opaco em 1.6*kmin. Sem degrade fica piscando.
        var o = (k - kmin) / (kmin * 0.6);
        if (!naLinhagem(grupos[i].getAttribute("data-dono"))) o = 0;
        grupos[i].style.opacity = Math.max(0, Math.min(1, o));
        grupos[i].style.pointerEvents = o > 0.5 ? "auto" : "none";
      }
      // SAI: a face do no (o titulo grande, o resumo) some enquanto o interior
      // aparece. Sem isso o zoom so aumenta a fonte; com isso a tela TROCA de
      // conteudo no mesmo lugar, que e o efeito de cair dentro.
      //
      // A face obedece a MESMA trava: se o interior nao pode abrir, a face
      // nao pode sumir, senao a caixa do irmao fica vazia na tela.
      var faces = svg.querySelectorAll("[data-face-ate]");
      for (var j = 0; j < faces.length; j++) {
        var kmax = parseFloat(faces[j].getAttribute("data-face-ate"));
        var f = 1 - (k - kmax) / (kmax * 0.6);
        if (!naLinhagem(faces[j].getAttribute("data-dono"))) f = 1;
        faces[j].style.opacity = Math.max(0, Math.min(1, f));
      }
    }

    function caixaDe(id) {
      var el = svg.getElementById(id);
      if (!el) return null;
      var b = el.getBBox();
      var m = Math.max(b.width, b.height) * 0.08;   // respiro
      return { x: b.x - m, y: b.y - m, w: b.width + 2*m, h: b.height + 2*m };
    }

    function voar(destino, aoFim) {
      if (anim) cancelAnimationFrame(anim);
      var de = vb(svg), t0 = null;
      if (dur === 0) { setVb(destino); if (aoFim) aoFim(); return; }
      // Custo (Task 11): o primeiro corte, antes de mexer em qualquer outra
      // coisa, foi desligar o filtro DURANTE o voo — a camera anda rapido
      // demais pra tremida se notar quadro a quadro, e recalcular
      // feDisplacementMap em ~1600 formas a cada frame e' o que derrubava
      // fps. Religa quando a animacao assenta (aoFim).
      svg.classList.add("voando");
      function passo(ts) {
        if (t0 === null) t0 = ts;
        var t = Math.min(1, (ts - t0) / dur), e = suavizar(t);
        setVb({
          x: de.x + (destino.x - de.x) * e,
          y: de.y + (destino.y - de.y) * e,
          w: de.w + (destino.w - de.w) * e,
          h: de.h + (destino.h - de.h) * e
        });
        if (t < 1) anim = requestAnimationFrame(passo);
        else { anim = null; svg.classList.remove("voando"); if (aoFim) aoFim(); }
      }
      anim = requestAnimationFrame(passo);
    }

    // Fim do voo: solta a linhagem antiga e REPINTA. Sem o repintar, o
    // ultimo quadro da animacao continuaria valendo — a uniao das duas
    // linhagens ficaria congelada na tela e o irmao nao fecharia nunca.
    function assentar() {
      saindo = null;
      aplicarLod(base.w / vb(svg).w);
      // O foco mudou, entao quem "so atravessa" mudou junto.
      pintarArestas();
    }

    function voarPara(id) {
      var c = caixaDe(id);
      if (!c) return;
      if (atual !== id) { saindo = atual; pilha.push(atual); atual = id; }
      voar(c, assentar);
      anunciar();
    }

    function subir() {
      if (!pilha.length) return;
      saindo = atual;
      atual = pilha.pop();
      voar(atual ? caixaDe(atual) : base, assentar);
      anunciar();
    }

    function anunciar() {
      var el = svg.getElementById(atual);
      var t = el ? el.getAttribute("data-titulo") : "Revy";
      var ev = new CustomEvent("zoom:mudou", { detail: { id: atual, titulo: t } });
      svg.dispatchEvent(ev);
    }

    function acender(ids) {
      var dentro = {};
      for (var i = 0; i < ids.length; i++) dentro[ids[i]] = true;
      // O id de um produto vem prefixado pela VM ("app2037.chatbot-api"), mas o
      // fluxo cita o nome cru ("chatbot-api"). Sem casar por sufixo, so as VMs
      // acendiam e os produtos do caminho ficavam apagados.
      function noCaminho(id) {
        if (dentro[id]) return true;
        var corte = id.lastIndexOf(".");
        return corte > -1 && dentro[id.slice(corte + 1)] === true;
      }
      // Caixa fora do fluxo nao some: apaga. Sumir tira a referencia espacial e
      // o usuario perde onde estava.
      var todas = svg.querySelectorAll("[data-navegavel]");
      for (var j = 0; j < todas.length; j++) {
        todas[j].style.opacity = noCaminho(todas[j].id) ? "1" : "0.18";
      }
      var setas = svg.querySelectorAll("[data-aresta]");
      for (var s = 0; s < setas.length; s++) {
        var par = setas[s].getAttribute("data-aresta").split("->");
        setas[s].style.opacity =
          (noCaminho(par[0]) && noCaminho(par[1])) ? "1" : "0.12";
      }
    }

    function apagar() {
      var todas = svg.querySelectorAll("[data-navegavel],[data-aresta],[data-de]");
      for (var i = 0; i < todas.length; i++) todas[i].style.opacity = "";
      // Limpar o inline devolve TODA aresta ao padrao do CSS, inclusive a
      // enfase que nao veio de fluxo nenhum. Repinta.
      pintarArestas();
    }

    // ----------------------------------------------------------------
    // Enfase das arestas (30/08, 2a leva). Duas regras, uma funcao so —
    // ter dois lugares escrevendo style.opacity na mesma seta e' como o
    // fluxo e o LOD ja brigaram uma vez.
    //
    //   1. Aresta INTERNA (mesmo produto) nasce apagada pelo CSS e acende
    //      quando o mouse esta numa das duas pontas. Vinte setas ligando
    //      dez componentes davam 43 travessias de caixa alheia mesmo com o
    //      layout por afinidade; e ninguem le as vinte de uma vez.
    //   2. Aresta ENTRE PRODUTOS apaga quando voce esta DENTRO de um no que
    //      ela apenas atravessa. A linha vermelha Loja->Motor cortando o
    //      interior aberto do Chatbot de ponta a ponta nao diz nada sobre o
    //      Chatbot — ela so estava no caminho.
    //
    // "Tocar" e' linhagem nos dois sentidos: a ponta esta dentro do foco
    // (Chatbot -> um componente dele) ou o foco esta dentro da ponta (voce
    // desceu num componente, e a aresta sai do produto inteiro).
    // ----------------------------------------------------------------
    var sob = null;   // id do no sob o mouse

    function dentroDe(id, raiz) {
      return id === raiz || id.indexOf(raiz + ".") === 0;
    }

    function pintarArestas() {
      // `[data-de]`, nao `[data-aresta]`: o rotulo tem que acender junto com
      // a seta, e ele nao pode carregar `data-aresta` (o valor tem um `>`
      // literal dentro, que quebra o regex de dois testes, e o atributo e' o
      // que um deles conta pra saber quantas arestas existem). Ver
      // `_marcas_da_aresta` em arq_render.py.
      var setas = svg.querySelectorAll("[data-de]");
      for (var i = 0; i < setas.length; i++) {
        var el = setas[i];
        var de = el.getAttribute("data-de"), para = el.getAttribute("data-para");
        if (de === null || para === null) continue;
        if (el.hasAttribute("data-interna")) {
          // PONTA EXATA, nao linhagem. Com `dentroDe` aqui, parar o mouse na
          // caixa do PRODUTO acendia as 20 de uma vez (toda aresta interna
          // esta dentro dele por definicao) — que foi exatamente a queixa: um
          // feixe de linhas no mesmo corredor, ilegivel. Grupo tambem
          // estourava: `workers` acendia 6. Agora a caixa sob o mouse tem que
          // SER a ponta, entao a pergunta que a pagina responde e' sempre a
          // mesma, em qualquer profundidade: "o que ESTA caixa chama, e quem
          // chama ela".
          el.style.opacity = (sob !== null && (de === sob || para === sob)) ? "1" : "";
        } else if (atual) {
          var toca = dentroDe(de, atual) || dentroDe(para, atual) ||
                     dentroDe(atual, de) || dentroDe(atual, para);
          el.style.opacity = toca ? "" : "0.10";
        } else {
          el.style.opacity = "";
        }
      }
    }

    // ================================================================
    // ARRASTAR (30/08, 4a leva). O layout automatico acerta a estrutura mas
    // nao adivinha o que voce quer ver perto do que; entao a caixa se move.
    //
    // Mover uma caixa e' mover DOIS grupos irmaos — a forma (<g id=chave>) e
    // o texto (<g data-texto-de=chave>) — porque o filtro de rabisco so pode
    // pegar a forma. Os filhos vao junto de graca: eles estao ANINHADOS
    // dentro dos dois grupos, entao um `transform` no pai leva a subarvore.
    //
    // As setas nao vao de graca. O tracado delas e' calculado em Python, na
    // geracao, e sai em coordenadas absolutas — entao arrastar sem recalcular
    // deixaria a seta apontando pro lugar velho. `recalcularArestas` refaz o
    // mesmo caminho de `_pontos_da_aresta` (arq_render.py), em JS, a cada
    // quadro do arrasto. Manter as duas contas iguais e' o preco de a seta
    // acompanhar a mao; se uma mudar, a outra tem que mudar junto.
    // ================================================================
    var CHAVE_STORAGE = "revy-arquitetura-posicoes";
    var movidos = {};          // chave -> {dx, dy}, so o que o humano mexeu
    var arrastandoCaixa = null;
    var LIMIAR_ARRASTO = 3;

    function lerSalvo() {
      try {
        var cru = window.localStorage.getItem(CHAVE_STORAGE);
        if (!cru) return {};
        var todo = JSON.parse(cru);
        return todo[svg.id] || {};
      } catch (e) { return {}; }   // modo anonimo, storage bloqueado: segue sem
    }
    function salvar() {
      try {
        var cru = window.localStorage.getItem(CHAVE_STORAGE);
        var todo = cru ? JSON.parse(cru) : {};
        todo[svg.id] = movidos;    // uma gaveta por vista; Schema tem a dela
        window.localStorage.setItem(CHAVE_STORAGE, JSON.stringify(todo));
      } catch (e) { /* sem storage: a posicao vale so nesta aba */ }
    }

    // O deslocamento de uma caixa e' o dela MAIS o dos ancestrais: mover o
    // grupo "Entra" move a Borda que esta dentro dele, e se voce depois
    // mover a Borda, os dois somam. Os ids sao caminhos pontuados, entao
    // "ancestral" e' teste de prefixo.
    function deslocamentoDe(id) {
      var dx = 0, dy = 0;
      for (var chave in movidos) {
        if (id === chave || id.indexOf(chave + ".") === 0) {
          dx += movidos[chave].dx; dy += movidos[chave].dy;
        }
      }
      return [dx, dy];
    }

    function geometriaDe(id) {
      var el = svg.getElementById(id);
      if (!el || !el.hasAttribute("data-x")) return null;
      var d = deslocamentoDe(id);
      return { x: parseFloat(el.getAttribute("data-x")) + d[0],
               y: parseFloat(el.getAttribute("data-y")) + d[1],
               w: parseFloat(el.getAttribute("data-w")),
               h: parseFloat(el.getAttribute("data-h")) };
    }

    function aplicarTransformes() {
      var formas = svg.querySelectorAll("[data-navegavel]");
      for (var i = 0; i < formas.length; i++) {
        var id = formas[i].id, m = movidos[id];
        var t = m ? "translate(" + m.dx + " " + m.dy + ")" : null;
        var par = svg.querySelector('[data-texto-de="' + cssEscape(id) + '"]');
        if (t) {
          formas[i].setAttribute("transform", t);
          if (par) par.setAttribute("transform", t);
        } else {
          formas[i].removeAttribute("transform");
          if (par) par.removeAttribute("transform");
        }
      }
    }

    // Os ids tem ponto e hifen; um seletor de atributo aceita isso entre
    // aspas, mas aspas dentro do valor nao. Nenhuma chave tem aspas hoje —
    // isto e' cinto de seguranca, nao remendo de bug conhecido.
    function cssEscape(v) { return String(v).replace(/"/g, '\\"'); }

    // ---- o mesmo roteamento de arq_render._pontos_da_aresta, em JS ----
    var LADO_OPOSTO = { direita: "esquerda", esquerda: "direita",
                        cima: "baixo", baixo: "cima" };
    var PASSO_SAIDA = 9.0;

    function ladoSaida(de, para) {
      var dx = (para.x + para.w / 2) - (de.x + de.w / 2);
      var dy = (para.y + para.h / 2) - (de.y + de.h / 2);
      if (Math.abs(dx) >= Math.abs(dy)) return dx >= 0 ? "direita" : "esquerda";
      return dy >= 0 ? "baixo" : "cima";
    }
    function pontoBorda(c, lado, off) {
      if (lado === "direita") return [c.x + c.w, c.y + c.h / 2 + off];
      if (lado === "esquerda") return [c.x, c.y + c.h / 2 + off];
      if (lado === "baixo") return [c.x + c.w / 2 + off, c.y + c.h];
      return [c.x + c.w / 2 + off, c.y];
    }
    function pontosOrtogonais(p1, lado1, p2) {
      if (lado1 === "esquerda" || lado1 === "direita") {
        var xm = (p1[0] + p2[0]) / 2;
        return [p1, [xm, p1[1]], [xm, p2[1]], p2];
      }
      var ym = (p1[1] + p2[1]) / 2;
      return [p1, [p1[0], ym], [p2[0], ym], p2];
    }

    function recalcularArestas() {
      var linhas = svg.querySelectorAll("polyline[data-i]");
      var pares = [], contagem = {};
      var i, k;
      // 1o passe: geometria e lado de saida, e quantas saem da MESMA borda
      for (i = 0; i < linhas.length; i++) {
        var el = linhas[i];
        var de = geometriaDe(el.getAttribute("data-de"));
        var para = geometriaDe(el.getAttribute("data-para"));
        if (!de || !para) { pares.push(null); continue; }
        var lado = ladoSaida(de, para);
        k = el.getAttribute("data-de") + "|" + lado;
        contagem[k] = (contagem[k] || 0) + 1;
        pares.push({ el: el, de: de, para: para, lado: lado, grupo: k,
                     i: el.getAttribute("data-i") });
      }
      // 2o passe: espalha em torno do centro da borda, na ordem de aparicao —
      // a mesma regra de `_offsets_de_saida`, e a mesma ordem, porque o DOM
      // esta na ordem em que o Python emitiu.
      var vistos = {};
      for (i = 0; i < pares.length; i++) {
        var p = pares[i];
        if (!p) continue;
        var n = contagem[p.grupo];
        var pos = (vistos[p.grupo] || 0);
        vistos[p.grupo] = pos + 1;
        var off = (pos - (n - 1) / 2) * PASSO_SAIDA;
        var p1 = pontoBorda(p.de, p.lado, off);
        var p2 = pontoBorda(p.para, LADO_OPOSTO[p.lado], 0);
        var pts = pontosOrtogonais(p1, p.lado, p2);
        var txt = "";
        for (k = 0; k < pts.length; k++) {
          txt += (k ? " " : "") + pts[k][0].toFixed(2) + "," + pts[k][1].toFixed(2);
        }
        p.el.setAttribute("points", txt);
        var rotulo = svg.querySelector('text[data-i="' + p.i + '"]');
        if (rotulo) {
          rotulo.setAttribute("x", ((pts[1][0] + pts[2][0]) / 2).toFixed(2));
          rotulo.setAttribute("y", ((pts[1][1] + pts[2][1]) / 2).toFixed(2));
        }
      }
    }

    function repintarTudo() {
      aplicarTransformes();
      recalcularArestas();
      pintarArestas();
    }

    function voltarAoAutomatico() {
      movidos = {};
      salvar();
      repintarTudo();
    }

    function posicoesMovidas() { return movidos; }

    base = vb(svg);
    dur = (opts && opts.dur !== undefined) ? opts.dur : 450;
    // prefers-reduced-motion: salta em vez de voar. Nao e enfeite — quem sente
    // enjoo de movimento nao consegue usar a pagina com a animacao ligada.
    if (window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches) dur = 0;

    svg.addEventListener("click", function (ev) {
      // Arrastar termina em click; sem esta guarda, todo pan tambem voava.
      if (moveu) return;
      var alvo = ev.target.closest("[data-navegavel]");
      if (alvo && alvo.id) voarPara(alvo.id);
    });
    document.addEventListener("keydown", function (ev) {
      // O keydown do Esc e no document: com duas instancias (uma por vista),
      // as duas ouvem o mesmo evento. Cada instancia so reage se o proprio
      // <svg> estiver visivel, senao apertar Esc na vista Schema tambem sobe
      // a arvore da vista Arquitetura, invisivelmente.
      //
      // `hasAttribute`, NAO a propriedade IDL `hidden`: achado no navegador
      // — neste Chrome o <svg> RAIZ nao implementa essa propriedade (le
      // `undefined`, escrever nela nao muda nada), so o atributo de fato
      // controla o CSS. Negar `undefined` da sempre true, entao o guard
      // nunca guardaria nada se testasse a propriedade em vez do atributo.
      if (ev.key === "Escape" && !svg.hasAttribute("hidden")) subir();
    });
    svg.addEventListener("wheel", function (ev) {
      ev.preventDefault();
      var v = vb(svg), f = ev.deltaY > 0 ? 1.12 : 1 / 1.12;
      var r = svg.getBoundingClientRect();
      var cx = v.x + (ev.clientX - r.left) / r.width * v.w;
      var cy = v.y + (ev.clientY - r.top) / r.height * v.h;
      setVb({ x: cx - (cx - v.x)*f, y: cy - (cy - v.y)*f, w: v.w*f, h: v.h*f });
    }, { passive: false });

    var arrastando = false, px = 0, py = 0;
    svg.addEventListener("pointerdown", function (ev) {
      arrastando = true; moveu = false; px = ev.clientX; py = ev.clientY;
      // Comecou em cima de uma caixa? Entao o arrasto move A CAIXA; comecou
      // no vazio, move a CAMERA. So decide no primeiro movimento — antes do
      // limiar isto ainda pode virar um clique, que navega.
      //
      // `closest` da a caixa mais INTERNA sob o cursor, que e' a que voce
      // enxerga: `aplicarLod` poe pointer-events:none no interior que ainda
      // nao abriu, entao um filho invisivel nunca rouba o arrasto do pai.
      var caixa = ev.target.closest("[data-navegavel]");
      arrastandoCaixa = (caixa && caixa.id) ? caixa.id : null;
      // NADA de setPointerCapture aqui. Capturar o ponteiro no <svg> faz o
      // `click` seguinte ter como alvo o proprio svg, e ai o
      // closest("[data-navegavel]") devolve null e o clique nunca navega.
    });
    svg.addEventListener("pointermove", function (ev) {
      if (!arrastando) return;
      // Limiar: mao tremida nao vira arrasto, senao o clique some.
      if (Math.abs(ev.clientX - px) + Math.abs(ev.clientY - py) > LIMIAR_ARRASTO) moveu = true;
      if (!moveu) return;
      var v = vb(svg), r = svg.getBoundingClientRect();
      // Pixel de tela -> unidade de cena. O viewBox encolhe conforme voce se
      // aproxima, entao o mesmo movimento de mao vale menos unidades: sem
      // esta conversao a caixa dispararia longe do cursor no zoom fechado.
      var dx = (ev.clientX - px) / r.width * v.w;
      var dy = (ev.clientY - py) / r.height * v.h;
      if (arrastandoCaixa) {
        var m = movidos[arrastandoCaixa] || { dx: 0, dy: 0 };
        movidos[arrastandoCaixa] = { dx: m.dx + dx, dy: m.dy + dy };
        repintarTudo();
      } else {
        setVb({ x: v.x - dx, y: v.y - dy, w: v.w, h: v.h });
      }
      px = ev.clientX; py = ev.clientY;
    });
    svg.addEventListener("pointerup", function () {
      if (arrastando && moveu && arrastandoCaixa) salvar();
      arrastando = false; arrastandoCaixa = null;
    });
    svg.addEventListener("pointerleave", function () {
      if (arrastando && moveu && arrastandoCaixa) salvar();
      arrastando = false; arrastandoCaixa = null;
      if (sob !== null) { sob = null; pintarArestas(); }
    });

    // `pointerover` borbulha (ao contrario de `pointerenter`), entao UM
    // ouvinte no <svg> cobre as ~1600 formas. Sair de uma caixa para o vazio
    // tambem dispara — o alvo passa a ser o fundo, `closest` devolve null, e
    // as internas apagam. Nada de setPointerCapture perto disto: capturar o
    // ponteiro no <svg> faz todo evento seguinte ter o svg como alvo.
    svg.addEventListener("pointerover", function (ev) {
      var alvo = ev.target.closest("[data-navegavel]");
      var id = alvo ? alvo.id : null;
      if (id !== sob) { sob = id; pintarArestas(); }
    });

    medirPxPorUnidade();
    setVb(base);
    // As posicoes que o humano moveu voltam ANTES da primeira pintura, senao
    // a pagina abre no layout automatico e salta pro arrumado no quadro
    // seguinte.
    movidos = lerSalvo();
    repintarTudo();

    return { elemento: svg, voarPara: voarPara, subir: subir,
             acender: acender, apagar: apagar,
             voltarAoAutomatico: voltarAoAutomatico,
             posicoesMovidas: posicoesMovidas,
             // Chamado por `mostrarVista` (arq_render.py) ao trocar de
             // vista: o filtro e' UM SO por documento, compartilhado entre
             // as duas cenas — sem isto, mostrar de novo uma vista deixaria
             // a tremida no k da OUTRA vista (a ultima que mexeu no filtro
             // compartilhado) ate o proximo pan/zoom desta.
             atualizarFiltro: function () { aplicarFiltro(base.w / vb(svg).w); } };
  }
};
