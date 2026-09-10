/* Filtro de periodo com date-picker proprio em pt-BR.
 *
 * Por que existe: o popup nativo do <input type="date"> sai no idioma do
 * aparelho (ingles, no aparelho do dono). Este script troca cada par
 * inicio/fim por campos que abrem um calendario com rotulos fixos em
 * portugues. Vale para o Resultado e para todo filtro legado com os mesmos
 * names: cada <form> com o par ganha seu proprio popup.
 *
 * Enhancement progressivo: sem JS, os <input type="date" name="inicio|fim">
 * continuam nativos e o form submete igual. Com JS, os originais viram
 * type="hidden" (mesmos names, valores ISO AAAA-MM-DD) e o visivel e so
 * DD/MM/AAAA + popup. Backend e query string nao mudam.
 *
 * Rotulos (meses/dias) sao arrays fixos abaixo; nunca usar API de locale do
 * navegador (Intl, toLocaleString) para texto visivel.
 */
(function () {
  "use strict";

  var MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"
  ];
  /* Semana começa na segunda, como no calendário de parede brasileiro. */
  var DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];

  var ROTULOS = { inicio: "De", fim: "Até" };

  function pad2(n) {
    return (n < 10 ? "0" : "") + n;
  }

  function toISO(y, m, d) {
    return y + "-" + pad2(m) + "-" + pad2(d);
  }

  function parseISO(valor) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec((valor || "").trim());
    if (!m) return null;
    var y = parseInt(m[1], 10);
    var mo = parseInt(m[2], 10);
    var d = parseInt(m[3], 10);
    if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
    var conf = new Date(y, mo - 1, d);
    if (conf.getFullYear() !== y || conf.getMonth() !== mo - 1 || conf.getDate() !== d) {
      return null;
    }
    return { y: y, m: mo, d: d };
  }

  function formatBR(iso) {
    var p = parseISO(iso);
    if (!p) return "";
    return pad2(p.d) + "/" + pad2(p.m) + "/" + p.y;
  }

  function diasNoMes(y, m) {
    return new Date(y, m, 0).getDate();
  }

  /* getDay() é domingo=0; aqui segunda=0. Só aritmética, sem locale. */
  function deslocamentoPrimeiraSemana(y, m) {
    return (new Date(y, m - 1, 1).getDay() + 6) % 7;
  }

  function rotuloDia(y, m, d) {
    return d + " de " + MESES[m - 1] + " de " + y;
  }

  /* Cada form com o par inicio/fim ganha seu popup; sem o par, nada muda. */
  function melhorarForm(form) {
    var origInicio = form.querySelector('input[type="date"][name="inicio"]');
    var origFim = form.querySelector('input[type="date"][name="fim"]');
    if (!origInicio || !origFim) return;
    var orig = { inicio: origInicio, fim: origFim };

  form.setAttribute("data-periodo-melhorado", "true");

  var visivel = {};
  var ordem = ["inicio", "fim"];
  var i;
  for (i = 0; i < ordem.length; i++) {
    (function (chave) {
      var campo = orig[chave];
      campo.setAttribute("type", "hidden");
      var mostra = document.createElement("input");
      mostra.setAttribute("type", "text");
      mostra.setAttribute("readonly", "readonly");
      mostra.setAttribute("autocomplete", "off");
      mostra.setAttribute("inputmode", "none");
      mostra.setAttribute("spellcheck", "false");
      mostra.className = "periodo-visivel";
      mostra.setAttribute("data-periodo-alvo", chave);
      mostra.setAttribute("aria-haspopup", "dialog");
      mostra.setAttribute("aria-expanded", "false");
      mostra.setAttribute("aria-label", ROTULOS[chave] + " (dia, mês e ano)");
      mostra.value = formatBR(campo.value);
      mostra.placeholder = "dd/mm/aaaa";
      campo.parentNode.insertBefore(mostra, campo.nextSibling);
      visivel[chave] = mostra;
    })(ordem[i]);
  }

  /* --- popup único, reaproveitado pelos dois campos --- */
  var popup = document.createElement("div");
  popup.className = "periodo-calendario";
  popup.setAttribute("role", "dialog");
  popup.setAttribute("aria-label", "Escolher data");
  popup.hidden = true;
  form.appendChild(popup);

  var estado = { alvo: null, y: 0, m: 1 };

  var elTitulo = document.createElement("p");
  elTitulo.className = "periodo-cal-titulo";
  elTitulo.setAttribute("aria-live", "polite");

  var btnAnt = document.createElement("button");
  btnAnt.type = "button";
  btnAnt.className = "periodo-cal-nav";
  btnAnt.setAttribute("aria-label", "Mês anterior");
  btnAnt.textContent = "‹";

  var btnProx = document.createElement("button");
  btnProx.type = "button";
  btnProx.className = "periodo-cal-nav";
  btnProx.setAttribute("aria-label", "Próximo mês");
  btnProx.textContent = "›";

  var btnHoje = document.createElement("button");
  btnHoje.type = "button";
  btnHoje.className = "periodo-cal-hoje";
  btnHoje.textContent = "Hoje";

  var btnFechar = document.createElement("button");
  btnFechar.type = "button";
  btnFechar.className = "periodo-cal-fechar";
  btnFechar.setAttribute("aria-label", "Fechar calendário");
  btnFechar.textContent = "Fechar";

  var cabecalho = document.createElement("div");
  cabecalho.className = "periodo-cal-cabecalho";
  cabecalho.appendChild(btnAnt);
  cabecalho.appendChild(elTitulo);
  cabecalho.appendChild(btnProx);

  var gradeSemana = document.createElement("div");
  gradeSemana.className = "periodo-cal-semana";
  gradeSemana.setAttribute("aria-hidden", "true");
  for (i = 0; i < DIAS_SEMANA.length; i++) {
    var dw = document.createElement("span");
    dw.textContent = DIAS_SEMANA[i];
    gradeSemana.appendChild(dw);
  }

  var grade = document.createElement("div");
  grade.className = "periodo-cal-grade";
  grade.setAttribute("role", "group");
  grade.setAttribute("aria-label", "Dias do mês");

  var rodape = document.createElement("div");
  rodape.className = "periodo-cal-rodape";
  rodape.appendChild(btnHoje);
  rodape.appendChild(btnFechar);

  popup.appendChild(cabecalho);
  popup.appendChild(gradeSemana);
  popup.appendChild(grade);
  popup.appendChild(rodape);

  function diaSelecionado() {
    if (!estado.alvo) return null;
    return parseISO(orig[estado.alvo].value);
  }

  function focarDia(d) {
    var btn = grade.querySelector('[data-dia="' + d + '"]');
    if (btn) btn.focus();
  }

  function render() {
    var y = estado.y;
    var m = estado.m;
    var mesMin = MESES[m - 1];
    var mesTit = mesMin.charAt(0).toUpperCase() + mesMin.slice(1);
    elTitulo.textContent = mesTit + " de " + y;
    grade.setAttribute("aria-label", MESES[m - 1] + " de " + y);
    while (grade.firstChild) grade.removeChild(grade.firstChild);

    var sel = diaSelecionado();
    var hoje = new Date();
    var hojeY = hoje.getFullYear();
    var hojeM = hoje.getMonth() + 1;
    var hojeD = hoje.getDate();

    var desloc = deslocamentoPrimeiraSemana(y, m);
    var k;
    for (k = 0; k < desloc; k++) {
      var vazio = document.createElement("span");
      vazio.className = "periodo-cal-vazio";
      vazio.setAttribute("aria-hidden", "true");
      grade.appendChild(vazio);
    }
    var total = diasNoMes(y, m);
    for (k = 1; k <= total; k++) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "periodo-cal-dia";
      btn.textContent = String(k);
      btn.setAttribute("data-dia", String(k));
      btn.setAttribute("aria-label", rotuloDia(y, m, k));
      if (y === hojeY && m === hojeM && k === hojeD) {
        btn.classList.add("e-hoje");
      }
      if (sel && sel.y === y && sel.m === m && sel.d === k) {
        btn.classList.add("e-selecionado");
        btn.setAttribute("aria-pressed", "true");
      }
      (function (dia) {
        btn.addEventListener("click", function () {
          escolher(dia);
        });
      })(k);
      grade.appendChild(btn);
    }
  }

  function abrir(chave) {
    estado.alvo = chave;
    var atual = parseISO(orig[chave].value);
    var hoje = new Date();
    estado.y = atual ? atual.y : hoje.getFullYear();
    estado.m = atual ? atual.m : hoje.getMonth() + 1;
    render();
    popup.hidden = false;
    visivel.inicio.setAttribute("aria-expanded", chave === "inicio" ? "true" : "false");
    visivel.fim.setAttribute("aria-expanded", chave === "fim" ? "true" : "false");
    var sel = diaSelecionado();
    if (sel && sel.y === estado.y && sel.m === estado.m) {
      focarDia(sel.d);
    } else {
      focarDia(Math.min(hoje.getDate(), diasNoMes(estado.y, estado.m)));
    }
  }

  function fechar(devolverFoco) {
    if (popup.hidden) return;
    popup.hidden = true;
    visivel.inicio.setAttribute("aria-expanded", "false");
    visivel.fim.setAttribute("aria-expanded", "false");
    if (devolverFoco && estado.alvo && visivel[estado.alvo]) {
      visivel[estado.alvo].focus();
    }
    estado.alvo = null;
  }

  function escolher(d) {
    if (!estado.alvo) return;
    var chave = estado.alvo;
    orig[chave].value = toISO(estado.y, estado.m, d);
    visivel[chave].value = formatBR(orig[chave].value);
    fechar(true);
  }

  function mudarMes(delta) {
    var m = estado.m + delta;
    var y = estado.y;
    while (m < 1) { m += 12; y -= 1; }
    while (m > 12) { m -= 12; y += 1; }
    estado.m = m;
    estado.y = y;
    render();
  }

  btnAnt.addEventListener("click", function () { mudarMes(-1); });
  btnProx.addEventListener("click", function () { mudarMes(1); });
  btnFechar.addEventListener("click", function () { fechar(true); });
  btnHoje.addEventListener("click", function () {
    var hoje = new Date();
    estado.y = hoje.getFullYear();
    estado.m = hoje.getMonth() + 1;
    render();
    escolher(hoje.getDate());
  });

  var j;
  for (j = 0; j < ordem.length; j++) {
    (function (chave) {
      var campo = visivel[chave];
      campo.addEventListener("click", function () { abrir(chave); });
      campo.addEventListener("focus", function () {
        if (popup.hidden) abrir(chave);
      });
      campo.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " " || ev.key === "ArrowDown") {
          ev.preventDefault();
          abrir(chave);
        }
      });
    })(ordem[j]);
  }

  grade.addEventListener("keydown", function (ev) {
    if (popup.hidden || !estado.alvo) return;
    var ativo = document.activeElement;
    if (!ativo || !ativo.hasAttribute("data-dia")) {
      if (ev.key === "Escape") { ev.preventDefault(); fechar(true); }
      return;
    }
    var dia = parseInt(ativo.getAttribute("data-dia"), 10);
    var total = diasNoMes(estado.y, estado.m);
    if (ev.key === "ArrowLeft") {
      ev.preventDefault();
      if (dia > 1) focarDia(dia - 1);
    } else if (ev.key === "ArrowRight") {
      ev.preventDefault();
      if (dia < total) focarDia(dia + 1);
    } else if (ev.key === "ArrowUp") {
      ev.preventDefault();
      focarDia(Math.max(1, dia - 7));
    } else if (ev.key === "ArrowDown") {
      ev.preventDefault();
      focarDia(Math.min(total, dia + 7));
    } else if (ev.key === "Home") {
      ev.preventDefault();
      focarDia(1);
    } else if (ev.key === "End") {
      ev.preventDefault();
      focarDia(total);
    } else if (ev.key === "PageUp") {
      ev.preventDefault();
      if (ev.shiftKey) { estado.y -= 1; } else { mudarMes(-1); return; }
      render();
      focarDia(Math.min(dia, diasNoMes(estado.y, estado.m)));
    } else if (ev.key === "PageDown") {
      ev.preventDefault();
      if (ev.shiftKey) { estado.y += 1; } else { mudarMes(1); return; }
      render();
      focarDia(Math.min(dia, diasNoMes(estado.y, estado.m)));
    } else if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      escolher(dia);
    } else if (ev.key === "Escape") {
      ev.preventDefault();
      fechar(true);
    } else if (ev.key === "Tab") {
      fechar(false);
    }
  });

  popup.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") {
      ev.preventDefault();
      fechar(true);
    }
  });

  document.addEventListener("click", function (ev) {
    if (popup.hidden) return;
    var t = ev.target;
    if (popup.contains(t)) return;
    if (t === visivel.inicio || t === visivel.fim) return;
    fechar(false);
  });

  document.addEventListener("focusin", function (ev) {
    if (popup.hidden) return;
    var t = ev.target;
    if (popup.contains(t)) return;
    if (t === visivel.inicio || t === visivel.fim) return;
    if (t && form.contains(t) && (t.tagName === "BUTTON" || t.tagName === "A" || t.tagName === "INPUT")) {
      fechar(false);
    }
  });
  }

  var forms = document.querySelectorAll("form");
  var f;
  for (f = 0; f < forms.length; f++) {
    melhorarForm(forms[f]);
  }
})();
