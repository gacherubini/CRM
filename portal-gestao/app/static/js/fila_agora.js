/* Agora no rodízio — countdown no navegador, recarga só quando o estado muda.
 *
 * O prazo é o real, gravado pelo motor em cada oferta (data-prazo). O tique
 * corre aqui a cada segundo; o polling a cada 20s só compara a assinatura do
 * estado.json e recarrega quando algo mudou (oferta nova, assumida, expirada
 * ou fila editada). Sem data-agora na página, não faz nada.
 */
(function () {
  "use strict";

  var PAINEL = document.querySelector("[data-agora]");
  if (!PAINEL) return;

  function formatarDecorridos(segundos) {
    segundos = Math.max(0, Math.floor(segundos));
    if (segundos < 60) return "há " + segundos + " s";
    var minutos = Math.floor(segundos / 60);
    if (minutos < 60) return "há " + minutos + " min";
    return "há " + Math.floor(minutos / 60) + " h " + String(minutos % 60).padStart(2, "0") + " min";
  }

  function formatarRestante(segundos) {
    segundos = Math.max(0, Math.floor(segundos));
    return Math.floor(segundos / 60) + ":" + String(segundos % 60).padStart(2, "0");
  }

  function tique() {
    var agora = Date.now();
    PAINEL.querySelectorAll("[data-oferta]").forEach(function (el) {
      var criado = el.getAttribute("data-criado");
      var prazo = el.getAttribute("data-prazo");
      var decorridoEl = el.querySelector("[data-decorrido]");
      var restanteEl = el.querySelector("[data-restante]");
      var barraEl = el.querySelector("[data-barra]");
      if (criado && decorridoEl) {
        var criadoMs = Date.parse(criado);
        if (!isNaN(criadoMs)) {
          decorridoEl.textContent = formatarDecorridos((agora - criadoMs) / 1000);
        }
      }
      if (!prazo || !restanteEl) return;
      var prazoMs = Date.parse(prazo);
      if (isNaN(prazoMs)) return;
      var restanteS = (prazoMs - agora) / 1000;
      if (restanteS <= 0) {
        restanteEl.textContent = "passando…";
        el.classList.add("apertado");
        if (barraEl) barraEl.style.width = "100%";
        return;
      }
      restanteEl.textContent = formatarRestante(restanteS);
      el.classList.toggle("apertado", restanteS < 60);
      if (barraEl && criado) {
        var criadoMs2 = Date.parse(criado);
        var total = prazoMs - criadoMs2;
        if (!isNaN(criadoMs2) && total > 0) {
          var pct = Math.min(Math.max((agora - criadoMs2) / total, 0), 1) * 100;
          barraEl.style.width = pct.toFixed(0) + "%";
        }
      }
    });
  }

  tique();
  window.setInterval(tique, 1000);

  /* Polling: a primeira resposta é a linha de base; recarrega só na mudança.
   * Falha de rede não derruba o countdown — tenta de novo no próximo ciclo. */
  var url = PAINEL.getAttribute("data-estado-url");
  var base = null;
  function sondar() {
    if (!url || document.hidden) return;
    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (resposta) {
        if (!resposta.ok) return null;
        return resposta.json();
      })
      .then(function (estado) {
        if (!estado || !estado.assinatura) return;
        if (base === null) {
          base = estado.assinatura;
          return;
        }
        if (estado.assinatura !== base) window.location.reload();
      })
      .catch(function () {});
  }
  window.setInterval(sondar, 20000);
})();
