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
      var todas = svg.querySelectorAll("[data-navegavel],[data-aresta]");
      for (var i = 0; i < todas.length; i++) todas[i].style.opacity = "";
    }

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
      // NADA de setPointerCapture aqui. Capturar o ponteiro no <svg> faz o
      // `click` seguinte ter como alvo o proprio svg, e ai o
      // closest("[data-navegavel]") devolve null e o clique nunca navega.
    });
    svg.addEventListener("pointermove", function (ev) {
      if (!arrastando) return;
      // Limiar: mao tremida nao vira arrasto, senao o clique some.
      if (Math.abs(ev.clientX - px) + Math.abs(ev.clientY - py) > 3) moveu = true;
      if (!moveu) return;
      var v = vb(svg), r = svg.getBoundingClientRect();
      setVb({ x: v.x - (ev.clientX - px) / r.width * v.w,
              y: v.y - (ev.clientY - py) / r.height * v.h, w: v.w, h: v.h });
      px = ev.clientX; py = ev.clientY;
    });
    svg.addEventListener("pointerup", function () { arrastando = false; });
    svg.addEventListener("pointerleave", function () { arrastando = false; });

    medirPxPorUnidade();
    setVb(base);

    return { elemento: svg, voarPara: voarPara, subir: subir,
             acender: acender, apagar: apagar,
             // Chamado por `mostrarVista` (arq_render.py) ao trocar de
             // vista: o filtro e' UM SO por documento, compartilhado entre
             // as duas cenas — sem isto, mostrar de novo uma vista deixaria
             // a tremida no k da OUTRA vista (a ultima que mexeu no filtro
             // compartilhado) ate o proximo pan/zoom desta.
             atualizarFiltro: function () { aplicarFiltro(base.w / vb(svg).w); } };
  }
};
