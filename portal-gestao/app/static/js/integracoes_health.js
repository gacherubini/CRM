/**
 * Painel de status das integrações (Meta / Google / WhatsApp).
 *
 * Compartilhado entre o Revy Control e a Revy Loja: o endpoint de health vem do
 * atributo `data-integ-endpoint` do container (`#integracoes-health`), então o
 * mesmo componente serve o detalhe da loja no Control e a página de Integrações
 * no shell da Loja (que proxya o Control server-side).
 *
 * Contrato do endpoint (nunca renderiza token — o backend não envia nenhum):
 *   { meta: {status, itens:[{kind, status, message}]},
 *     google: {...}, whatsapp: {...},
 *     checked_at, cache_ttl_seg }
 * status ∈ "connected" | "error" | "missing".
 *
 * Todo texto vindo do servidor é tratado como não confiável: o DOM é montado
 * com createElement/textContent (nunca innerHTML com string interpolada).
 */
(function () {
  "use strict";

  var KIND_LABELS = {
    pixel: "Pixel",
    capi: "CAPI",
    meta_ads: "Meta Ads",
    google_ads: "Google Ads",
    whatsapp: "WhatsApp",
  };

  var STATUS_CLASS = { connected: "ok", error: "err", missing: "off" };
  var STATUS_LABEL = {
    connected: "Conectado",
    error: "Com erro",
    missing: "Não configurado",
  };
  var STATUS_MARK = { connected: "✓", error: "✕", missing: "–" };

  var GROUPS = [
    { key: "meta", tile: "M", name: "Meta", sub: "Pixel · CAPI · Meta Ads" },
    { key: "google", tile: "G", name: "Google", sub: "Google Ads" },
    { key: "whatsapp", tile: "W", name: "WhatsApp", sub: null },
  ];

  function statusClass(status) {
    return STATUS_CLASS[status] || "off";
  }

  function statusLabel(status) {
    return STATUS_LABEL[status] || "Não configurado";
  }

  function statusMark(status) {
    return STATUS_MARK[status] || "–";
  }

  function itemLabel(item) {
    return KIND_LABELS[item.kind] || item.kind || "";
  }

  function itemMessage(item) {
    if (item.message) return item.message;
    if (item.status === "connected") return "Conectado";
    if (item.status === "missing") return "Não configurado";
    return "Falha na verificação";
  }

  function whatsappSub(group) {
    if (!group || group.status === "missing") return "nenhum número";
    var n = (group.itens || []).length;
    return n + (n === 1 ? " número" : " números");
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function buildChevron() {
    var ns = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(ns, "svg");
    svg.setAttribute("class", "integ-chev");
    svg.setAttribute("width", "16");
    svg.setAttribute("height", "16");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("fill", "none");
    svg.setAttribute("aria-hidden", "true");
    var path = document.createElementNS(ns, "path");
    path.setAttribute("d", "M6 4l4 4-4 4");
    path.setAttribute("stroke", "currentColor");
    path.setAttribute("stroke-width", "1.6");
    path.setAttribute("stroke-linecap", "round");
    path.setAttribute("stroke-linejoin", "round");
    svg.appendChild(path);
    return svg;
  }

  function buildSubItem(item) {
    var row = el("div", "integ-subitem " + statusClass(item.status));
    row.appendChild(el("span", "integ-mk", statusMark(item.status)));
    row.appendChild(el("span", "integ-sname", itemLabel(item)));
    row.appendChild(el("span", "integ-smsg", itemMessage(item)));
    return row;
  }

  function buildGroupRow(def, group) {
    var row = el("div", "integ-row");

    var btn = el("button", "integ-row-main");
    btn.type = "button";

    var names = el("span", "integ-names");
    names.appendChild(el("span", "integ-name", def.name));
    names.appendChild(
      el(
        "span",
        "integ-sub",
        def.key === "whatsapp" ? whatsappSub(group) : def.sub
      )
    );

    var pill = el("span", "integ-pill " + statusClass(group.status));
    pill.appendChild(el("span", "integ-dot"));
    pill.appendChild(document.createTextNode(statusLabel(group.status)));

    btn.appendChild(el("span", "integ-tile", def.tile));
    btn.appendChild(names);
    btn.appendChild(pill);
    btn.appendChild(buildChevron());

    btn.addEventListener("click", function () {
      row.classList.toggle("open");
    });

    var sub = el("div", "integ-subitens");
    (group.itens || []).forEach(function (item) {
      sub.appendChild(buildSubItem(item));
    });

    row.appendChild(btn);
    row.appendChild(sub);
    return row;
  }

  function formatChecked(isoString) {
    if (!isoString) return "";
    var checkedDate = new Date(isoString);
    if (isNaN(checkedDate.getTime())) return "";
    var minutes = Math.floor((Date.now() - checkedDate.getTime()) / 60000);
    if (minutes < 1) return "Verificado agora";
    return "Verificado há " + minutes + " min";
  }

  function init(section) {
    var lojaId = section.getAttribute("data-loja-id");
    var corpo = section.querySelector("[data-integ-corpo]");
    var checkedEl = section.querySelector("[data-integ-checked]");
    var testarBtn = section.querySelector("[data-integ-testar]");

    // Endpoint vem do template (Control: /control/...; Loja: /app/loja/...).
    // Fallback relativo só para dev/local sem prefixo.
    var endpoint =
      section.getAttribute("data-integ-endpoint") ||
      "/control/v1/lojas/" + encodeURIComponent(lojaId) + "/integracoes/health";

    if (!lojaId || !corpo) return;

    function render(data) {
      corpo.textContent = "";
      GROUPS.forEach(function (def) {
        var group = data[def.key];
        if (!group) return;
        corpo.appendChild(buildGroupRow(def, group));
      });
      if (checkedEl) checkedEl.textContent = formatChecked(data.checked_at);
    }

    function renderErro() {
      corpo.textContent = "";
      corpo.appendChild(
        el(
          "p",
          "integ-loading",
          "Não foi possível verificar agora — tente de novo"
        )
      );
    }

    function carregar(forcar) {
      var url =
        endpoint + (forcar ? (endpoint.indexOf("?") >= 0 ? "&" : "?") + "forcar=1" : "");
      return fetch(url, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      })
        .then(function (response) {
          if (!response.ok) throw new Error("http " + response.status);
          return response.json();
        })
        .then(render)
        .catch(renderErro);
    }

    if (testarBtn) {
      var originalLabel = testarBtn.textContent;
      testarBtn.addEventListener("click", function () {
        testarBtn.disabled = true;
        testarBtn.textContent = "";
        testarBtn.appendChild(el("span", "integ-spin"));
        testarBtn.appendChild(document.createTextNode(" Verificando…"));
        carregar(true).then(function () {
          testarBtn.disabled = false;
          testarBtn.textContent = originalLabel;
        });
      });
    }

    carregar(false);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var section = document.getElementById("integracoes-health");
    if (section) init(section);
  });
})();
