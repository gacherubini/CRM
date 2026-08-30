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

    function aplicarLod(k) {
      // ENTRA: o interior do no aparece conforme voce se aproxima.
      var grupos = svg.querySelectorAll("[data-k-min]");
      for (var i = 0; i < grupos.length; i++) {
        var kmin = parseFloat(grupos[i].getAttribute("data-k-min"));
        // Rampa: invisivel em kmin, opaco em 1.6*kmin. Sem degrade fica piscando.
        var o = (k - kmin) / (kmin * 0.6);
        grupos[i].style.opacity = Math.max(0, Math.min(1, o));
        grupos[i].style.pointerEvents = o > 0.5 ? "auto" : "none";
      }
      // SAI: a face do no (o titulo grande, o resumo) some enquanto o interior
      // aparece. Sem isso o zoom so aumenta a fonte; com isso a tela TROCA de
      // conteudo no mesmo lugar, que e o efeito de cair dentro.
      var faces = svg.querySelectorAll("[data-face-ate]");
      for (var j = 0; j < faces.length; j++) {
        var kmax = parseFloat(faces[j].getAttribute("data-face-ate"));
        var f = 1 - (k - kmax) / (kmax * 0.6);
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
        else { anim = null; if (aoFim) aoFim(); }
      }
      anim = requestAnimationFrame(passo);
    }

    function voarPara(id) {
      var c = caixaDe(id);
      if (!c) return;
      if (atual !== id) { pilha.push(atual); atual = id; }
      voar(c);
      anunciar();
    }

    function subir() {
      if (!pilha.length) return;
      atual = pilha.pop();
      voar(atual ? caixaDe(atual) : base);
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

    setVb(base);

    return { elemento: svg, voarPara: voarPara, subir: subir,
             acender: acender, apagar: apagar };
  }
};
