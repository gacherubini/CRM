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

    function vb(el) {
      var p = el.getAttribute("viewBox").split(/[ ,]+/).map(Number);
      return { x: p[0], y: p[1], w: p[2], h: p[3] };
    }
    function setVb(v) {
      svg.setAttribute("viewBox", v.x + " " + v.y + " " + v.w + " " + v.h);
      aplicarLod(base.w / v.w);
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
        // Rampa: invisivel em kmin, opaco em 1.3*kmin. Sem degrade fica
        // piscando. Era 1.6: com o layout de 01/09 (produtos mais largos que
        // altos, viewport 2:1) o voo pra dentro do Chatbot assentava em
        // k = 1.5*kmin e a face ficava a 16% por cima do interior, pra sempre.
        var o = (k - kmin) / (kmin * 0.3);
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
        var f = 1 - (k - kmax) / (kmax * 0.3);
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
        var o = noCaminho(todas[j].id) ? "1" : "0.18";
        todas[j].style.opacity = o;
        // O texto vive num <g> irmao (camada sem filtro, por cima): apagar
        // so a forma deixava o titulo preto em cima da caixa esmaecida.
        var par = svg.querySelector('[data-texto-de="' + cssEscape(todas[j].id) + '"]');
        if (par) par.style.opacity = o;
      }
      var setas = svg.querySelectorAll("[data-aresta]");
      for (var s = 0; s < setas.length; s++) {
        var par = setas[s].getAttribute("data-aresta").split("->");
        setas[s].style.opacity =
          (noCaminho(par[0]) && noCaminho(par[1])) ? "1" : "0.12";
      }
    }

    function apagar() {
      var todas = svg.querySelectorAll("[data-navegavel],[data-texto-de],[data-aresta],[data-de]");
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

    // ---- o mesmo roteamento de arq_rotas.py, em JS ----
    // Grade de corredores a `FOLGA` de cada borda de cada obstaculo, Dijkstra
    // com pena por dobra. Se mudar a regra la, mude aqui — e' o preco de a
    // seta acompanhar a caixa enquanto voce arrasta.
    var LADO_OPOSTO = { direita: "esquerda", esquerda: "direita",
                        cima: "baixo", baixo: "cima" };
    var PASSO_SAIDA = 9.0;
    var FOLGA = 24.0 * 0.6;
    var PENA_COTOVELO = 90.0;

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
    function afastar(p, lado, f) {
      if (lado === "direita") return [p[0] + f, p[1]];
      if (lado === "esquerda") return [p[0] - f, p[1]];
      if (lado === "baixo") return [p[0], p[1] + f];
      return [p[0], p[1] - f];
    }
    function pontosOrtogonais(p1, lado1, p2) {
      if (lado1 === "esquerda" || lado1 === "direita") {
        var xm = (p1[0] + p2[0]) / 2;
        return [p1, [xm, p1[1]], [xm, p2[1]], p2];
      }
      var ym = (p1[1] + p2[1]) / 2;
      return [p1, [p1[0], ym], [p2[0], ym], p2];
    }
    function cruza(p, q, r) {
      var eps = 0.01;
      if (Math.abs(p[1] - q[1]) < eps) {
        return (r.y + eps < p[1] && p[1] < r.y + r.h - eps) &&
          !(Math.max(p[0], q[0]) <= r.x + eps || Math.min(p[0], q[0]) >= r.x + r.w - eps);
      }
      if (Math.abs(p[0] - q[0]) < eps) {
        return (r.x + eps < p[0] && p[0] < r.x + r.w - eps) &&
          !(Math.max(p[1], q[1]) <= r.y + eps || Math.min(p[1], q[1]) >= r.y + r.h - eps);
      }
      return true;
    }
    function dentroDeRet(r, c) {
      return r.x >= c.x - 0.01 && r.y >= c.y - 0.01 &&
             r.x + r.w <= c.x + c.w + 0.01 && r.y + r.h <= c.y + c.h + 0.01;
    }
    function simplificar(pts) {
      if (pts.length < 3) return pts;
      var saida = [pts[0]];
      for (var i = 1; i < pts.length - 1; i++) {
        var a = saida[saida.length - 1], b = pts[i], c = pts[i + 1];
        var h = Math.abs(a[1] - b[1]) < 0.01 && Math.abs(b[1] - c[1]) < 0.01;
        var v = Math.abs(a[0] - b[0]) < 0.01 && Math.abs(b[0] - c[0]) < 0.01;
        if (!(h || v)) saida.push(b);
      }
      saida.push(pts[pts.length - 1]);
      return saida;
    }
    function rotear(de, para, obstaculos, off) {
      var ladoDe = ladoSaida(de, para), ladoPara = LADO_OPOSTO[ladoDe];
      var p1 = pontoBorda(de, ladoDe, off), p2 = pontoBorda(para, ladoPara, 0);
      var x0 = Math.min(de.x, para.x) - FOLGA * 2, y0 = Math.min(de.y, para.y) - FOLGA * 2;
      var x1 = Math.max(de.x + de.w, para.x + para.w) + FOLGA * 2;
      var y1 = Math.max(de.y + de.h, para.y + para.h) + FOLGA * 2;
      var obs = [];
      for (var i = 0; i < obstaculos.length; i++) {
        var r = obstaculos[i];
        if (r.x + r.w < x0 || r.x > x1 || r.y + r.h < y0 || r.y > y1) continue;
        if (dentroDeRet(r, para) || dentroDeRet(r, de)) continue;
        obs.push(r);
      }
      var simples = pontosOrtogonais(p1, ladoDe, p2), k;
      var limpo = true;
      for (k = 0; k < simples.length - 1 && limpo; k++) {
        for (i = 0; i < obs.length; i++) if (cruza(simples[k], simples[k + 1], obs[i])) { limpo = false; break; }
      }
      if (!obs.length || limpo) return simplificar(simples);

      var a = afastar(p1, ladoDe, FOLGA), b = afastar(p2, ladoPara, FOLGA);
      var xs = {}, ys = {};
      xs[a[0]] = 1; xs[b[0]] = 1; ys[a[1]] = 1; ys[b[1]] = 1;
      var todos = obs.concat([de, para]);
      for (i = 0; i < todos.length; i++) {
        r = todos[i];
        xs[r.x - FOLGA] = 1; xs[r.x + r.w + FOLGA] = 1;
        ys[r.y - FOLGA] = 1; ys[r.y + r.h + FOLGA] = 1;
      }
      var xsL = Object.keys(xs).map(Number).sort(function (m, n) { return m - n; });
      var ysL = Object.keys(ys).map(Number).sort(function (m, n) { return m - n; });
      var ix = {}, iy = {};
      for (i = 0; i < xsL.length; i++) ix[xsL[i]] = i;
      for (i = 0; i < ysL.length; i++) iy[ysL[i]] = i;
      var bloqueio = obs.concat([de, para]);
      function livre(p, q) {
        for (var j = 0; j < bloqueio.length; j++) if (cruza(p, q, bloqueio[j])) return false;
        return true;
      }
      var inicio = ix[a[0]] + "," + iy[a[1]], fim = ix[b[0]] + "," + iy[b[1]];
      var DIRS = [[1, 0], [-1, 0], [0, 1], [0, -1]];
      // Fila de prioridade simples (lista ordenada por insercao): a grade
      // tem no maximo algumas dezenas de nos, entao busca linear basta.
      var fila = [{ custo: 0, no: inicio, dir: -1, de: null }];
      var melhor = {}, anterior = {}, achado = null;
      while (fila.length) {
        var mi = 0;
        for (i = 1; i < fila.length; i++) if (fila[i].custo < fila[mi].custo) mi = i;
        var atual = fila.splice(mi, 1)[0];
        var chave = atual.no + "|" + atual.dir;
        if (melhor[chave] !== undefined) continue;
        melhor[chave] = atual.custo;
        anterior[chave] = atual.de;
        if (atual.no === fim) { achado = chave; break; }
        var cxy = atual.no.split(",").map(Number);
        for (var d = 0; d < 4; d++) {
          var nx = cxy[0] + DIRS[d][0], ny = cxy[1] + DIRS[d][1];
          if (nx < 0 || ny < 0 || nx >= xsL.length || ny >= ysL.length) continue;
          var p = [xsL[cxy[0]], ysL[cxy[1]]], q = [xsL[nx], ysL[ny]];
          if (!livre(p, q)) continue;
          var passo = Math.abs(q[0] - p[0]) + Math.abs(q[1] - p[1]);
          var dobra = (atual.dir !== -1 && atual.dir !== d) ? 1 : 0;
          var prox = nx + "," + ny;
          if (melhor[prox + "|" + d] !== undefined) continue;
          fila.push({ custo: atual.custo + passo + PENA_COTOVELO * dobra, no: prox, dir: d, de: chave });
        }
      }
      if (achado === null) return simplificar(simples);
      var caminho = [];
      var cur = achado;
      while (cur !== null) {
        var partes = cur.split("|")[0].split(",").map(Number);
        caminho.push([xsL[partes[0]], ysL[partes[1]]]);
        cur = anterior[cur];
      }
      caminho.reverse();
      return simplificar([p1].concat(caminho, [p2]));
    }

    // Irmaos das duas pontas, fora as pontas e os ancestrais delas — a mesma
    // regra de `arq_render._obstaculos`.
    function paiDe(id) { var c = id.lastIndexOf("."); return c === -1 ? "" : id.slice(0, c); }
    function obstaculosDe(idDe, idPara) {
      var pais = {}; pais[paiDe(idDe)] = 1; pais[paiDe(idPara)] = 1;
      var formas = svg.querySelectorAll("[data-navegavel]");
      var saida = [];
      for (var i = 0; i < formas.length; i++) {
        var id = formas[i].id;
        if (!pais[paiDe(id)]) continue;
        if (id === idDe || id === idPara) continue;
        if (idDe.indexOf(id + ".") === 0 || idPara.indexOf(id + ".") === 0) continue;
        var g = geometriaDe(id);
        if (g) saida.push(g);
      }
      return saida;
    }

    function meioDoMaiorSegmento(pts) {
      var melhor = -1, mx = pts[0][0], my = pts[0][1];
      for (var i = 0; i < pts.length - 1; i++) {
        var comp = Math.abs(pts[i + 1][0] - pts[i][0]) + Math.abs(pts[i + 1][1] - pts[i][1]);
        if (comp > melhor) { melhor = comp; mx = (pts[i][0] + pts[i + 1][0]) / 2; my = (pts[i][1] + pts[i + 1][1]) / 2; }
      }
      return [mx, my];
    }

    function recalcularArestas() {
      // Ordenadas por `data-i` (a ordem de `resolvidas` no Python), nao pela
      // ordem do DOM: as arestas com dono vivem em <g> proprios, entao o DOM
      // ja nao segue o indice — e o espalhamento na borda depende da ordem.
      var linhas = Array.prototype.slice.call(svg.querySelectorAll("polyline[data-i]"));
      linhas.sort(function (m, n) { return parseInt(m.getAttribute("data-i"), 10) - parseInt(n.getAttribute("data-i"), 10); });
      var pares = [], contagem = {};
      var i, k;
      // 1o passe: geometria e lado de saida, e quantas saem da MESMA borda
      for (i = 0; i < linhas.length; i++) {
        var el = linhas[i];
        var idDe = el.getAttribute("data-de"), idPara = el.getAttribute("data-para");
        var de = geometriaDe(idDe);
        var para = geometriaDe(idPara);
        if (!de || !para) { pares.push(null); continue; }
        var lado = ladoSaida(de, para);
        k = idDe + "|" + lado;
        contagem[k] = (contagem[k] || 0) + 1;
        pares.push({ el: el, de: de, para: para, idDe: idDe, idPara: idPara, grupo: k,
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
        var pts = rotear(p.de, p.para, obstaculosDe(p.idDe, p.idPara), off);
        var txt = "";
        for (k = 0; k < pts.length; k++) {
          txt += (k ? " " : "") + pts[k][0].toFixed(2) + "," + pts[k][1].toFixed(2);
        }
        p.el.setAttribute("points", txt);
        var meio = meioDoMaiorSegmento(pts);
        var rotulo = svg.querySelector('text[data-i="' + p.i + '"]');
        if (rotulo) {
          rotulo.setAttribute("x", meio[0].toFixed(2));
          rotulo.setAttribute("y", (meio[1] + 8 * 0.36).toFixed(2));
        }
        var ponta = svg.querySelector('path[data-ponta][data-i="' + p.i + '"]');
        if (ponta && pts.length >= 2) {
          var a2 = pts[pts.length - 2], b2 = pts[pts.length - 1];
          var ddx = b2[0] - a2[0], ddy = b2[1] - a2[1], comp = Math.hypot(ddx, ddy) || 1;
          var ux = ddx / comp, uy = ddy / comp;
          var tam = parseFloat(ponta.getAttribute("data-tam")) || 8;
          var bx = b2[0] - ux * tam, by = b2[1] - uy * tam, ox = -uy * tam * 0.45, oy = ux * tam * 0.45;
          ponta.setAttribute("d", "M" + b2[0].toFixed(2) + "," + b2[1].toFixed(2) +
            " L" + (bx + ox).toFixed(2) + "," + (by + oy).toFixed(2) +
            " L" + (bx - ox).toFixed(2) + "," + (by - oy).toFixed(2) + " Z");
        }
        var pilula = svg.querySelector('rect[data-i="' + p.i + '"]');
        if (pilula) {
          var rw = parseFloat(pilula.getAttribute("data-rw")), rh = parseFloat(pilula.getAttribute("data-rh"));
          pilula.setAttribute("x", (meio[0] - rw / 2).toFixed(2));
          pilula.setAttribute("y", (meio[1] - rh / 2).toFixed(2));
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

    setVb(base);
    // As posicoes que o humano moveu voltam ANTES da primeira pintura, senao
    // a pagina abre no layout automatico e salta pro arrumado no quadro
    // seguinte.
    movidos = lerSalvo();
    repintarTudo();

    return { elemento: svg, voarPara: voarPara, subir: subir,
             acender: acender, apagar: apagar,
             voltarAoAutomatico: voltarAoAutomatico,
             posicoesMovidas: posicoesMovidas };
  }
};
