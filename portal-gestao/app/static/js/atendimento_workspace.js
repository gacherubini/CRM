/**
 * Workspace de atendimento (Revy Loja): envio sem reload + poll com after_id.
 *
 * Contrato poll: GET .../mensagens.json?canal_id=&after_id=
 * Contrato envio: POST .../mensagem com Accept: application/json
 *   → { ok, mensagem: {id, direcao, texto, criada_em}, bot_ativo, duplicada }
 *
 * Degrada gracefully: form clássico ainda funciona sem JS (303 redirect).
 */
(function () {
  "use strict";

  var root = document.getElementById("atendimento-workspace");
  if (!root) return;

  var thread = root.querySelector("[data-thread]");
  var form = root.querySelector("[data-composer-form]");
  var textarea = root.querySelector("[data-composer-text]");
  var submitBtn = root.querySelector("[data-composer-submit]");
  var flash = root.querySelector("[data-composer-flash]");
  var emptyEl = root.querySelector("[data-thread-empty]");

  var pollUrl = root.getAttribute("data-poll-url") || "";
  var canalId = root.getAttribute("data-canal-id") || "";
  var pollMs = parseInt(root.getAttribute("data-poll-ms") || "4000", 10);
  if (!isFinite(pollMs) || pollMs < 2000) pollMs = 4000;

  var knownIds = Object.create(null);
  var lastId = null;
  var pollTimer = null;
  var sending = false;

  function formatHorario(iso) {
    if (!iso) return "";
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return String(iso);
      var dd = String(d.getDate()).padStart(2, "0");
      var mm = String(d.getMonth() + 1).padStart(2, "0");
      var hh = String(d.getHours()).padStart(2, "0");
      var mi = String(d.getMinutes()).padStart(2, "0");
      return dd + "/" + mm + " " + hh + ":" + mi;
    } catch (e) {
      return String(iso);
    }
  }

  function nearBottom(el, threshold) {
    if (!el) return true;
    var thr = threshold == null ? 80 : threshold;
    return el.scrollHeight - el.scrollTop - el.clientHeight <= thr;
  }

  function scrollToBottom(force) {
    if (!thread) return;
    if (force || nearBottom(thread)) {
      thread.scrollTop = thread.scrollHeight;
    }
  }

  function setFlash(msg, kind) {
    if (!flash) return;
    flash.textContent = msg || "";
    flash.hidden = !msg;
    flash.className = "composer-flash" + (kind ? " " + kind : "");
  }

  function registerBubble(el) {
    var id = el.getAttribute("data-msg-id");
    if (id) {
      knownIds[id] = true;
      lastId = id;
    }
  }

  function appendMensagem(msg, opts) {
    if (!thread || !msg) return null;
    var id = msg.id || null;
    if (id && knownIds[id]) return null;

    if (emptyEl) {
      emptyEl.hidden = true;
    }

    var stick = opts && opts.forceScroll ? true : nearBottom(thread);
    var bolha = document.createElement("div");
    bolha.className = "bolha " + (msg.direcao === "saida" ? "saida" : "entrada");
    if (id) {
      bolha.setAttribute("data-msg-id", id);
      knownIds[id] = true;
      lastId = id;
    }
    bolha.appendChild(document.createTextNode(msg.texto || "—"));
    var small = document.createElement("small");
    small.textContent = formatHorario(msg.criada_em);
    bolha.appendChild(small);
    thread.appendChild(bolha);
    if (stick) {
      thread.scrollTop = thread.scrollHeight;
    }
    return bolha;
  }

  function seedFromDom() {
    if (!thread) return;
    var bolhas = thread.querySelectorAll(".bolha[data-msg-id]");
    for (var i = 0; i < bolhas.length; i++) {
      registerBubble(bolhas[i]);
    }
  }

  function buildPollUrl() {
    if (!pollUrl) return "";
    var u = pollUrl;
    var parts = [];
    if (canalId) parts.push("canal_id=" + encodeURIComponent(canalId));
    if (lastId) parts.push("after_id=" + encodeURIComponent(lastId));
    if (parts.length) {
      u += (u.indexOf("?") >= 0 ? "&" : "?") + parts.join("&");
    }
    return u;
  }

  function pollOnce() {
    if (!pollUrl) return;
    if (document.visibilityState === "hidden") return;
    var url = buildPollUrl();
    fetch(url, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (res) {
        if (!res.ok) return null;
        return res.json();
      })
      .then(function (data) {
        if (!data || !data.ok || !Array.isArray(data.mensagens)) return;
        for (var i = 0; i < data.mensagens.length; i++) {
          appendMensagem(data.mensagens[i]);
        }
        if (data.last_id && !lastId) {
          lastId = data.last_id;
        }
      })
      .catch(function () {
        /* silencioso: próximo ciclo tenta de novo */
      });
  }

  function startPoll() {
    stopPoll();
    if (!pollUrl) return;
    pollTimer = setInterval(pollOnce, pollMs);
  }

  function stopPoll() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function newIdempotencyKey() {
    try {
      if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    } catch (e) {}
    return "portal-" + Date.now() + "-" + Math.random().toString(36).slice(2, 10);
  }

  function ensureIdemField() {
    if (!form) return null;
    var input = form.querySelector('input[name="idempotency_key"]');
    if (!input) {
      input = document.createElement("input");
      input.type = "hidden";
      input.name = "idempotency_key";
      form.appendChild(input);
    }
    if (!input.value) input.value = newIdempotencyKey();
    return input;
  }

  function onSubmit(ev) {
    if (!form || !textarea) return;
    if (sending) {
      ev.preventDefault();
      return;
    }
    var texto = (textarea.value || "").trim();
    if (!texto) {
      ev.preventDefault();
      setFlash("Informe um texto válido.", "warn");
      return;
    }
    // Progressive enhancement: se fetch indisponível, form clássico.
    if (typeof fetch !== "function") return;

    ev.preventDefault();
    sending = true;
    if (submitBtn) submitBtn.disabled = true;
    setFlash("");

    var idem = ensureIdemField();
    var body = new FormData(form);
    if (idem && !body.get("idempotency_key")) {
      body.set("idempotency_key", idem.value);
    }

    fetch(form.action, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: body,
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { status: res.status, data: data };
        });
      })
      .then(function (pack) {
        var data = pack.data || {};
        if (!data.ok) {
          var msg =
            (data.message && data.message !== data.error
              ? data.message
              : null) ||
            ({
              texto: "Informe um texto válido.",
              sessao: "Sessão expirada. Atualize a página.",
              canal: "Canal WhatsApp inativo — envio bloqueado.",
              conversa: "Conversa não encontrada.",
              envio: "Não foi possível enviar agora.",
              scope: "Atendimento fora do seu escopo.",
              perm: "Sem permissão para enviar.",
            }[data.error] ||
              "Não foi possível enviar a mensagem.");
          setFlash(msg, "warn");
          return;
        }
        if (data.mensagem) {
          appendMensagem(data.mensagem, { forceScroll: true });
        }
        textarea.value = "";
        if (idem) idem.value = newIdempotencyKey();
        setFlash(data.duplicada ? "Mensagem já enviada." : "Mensagem enviada.", "ok");
        // Atualiza badge de bot se existir no DOM
        var botBadge = document.querySelector("[data-bot-status]");
        if (botBadge && data.bot_ativo === false) {
          botBadge.textContent = "Pausado (humano)";
          botBadge.className = "status em_atendimento";
        }
      })
      .catch(function () {
        setFlash("Não foi possível enviar a mensagem agora.", "warn");
      })
      .finally(function () {
        sending = false;
        if (submitBtn) submitBtn.disabled = false;
        if (textarea) textarea.focus();
      });
  }

  function onKeydown(ev) {
    if (!textarea || ev.key !== "Enter") return;
    if (ev.shiftKey) return; // quebra de linha
    if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
    ev.preventDefault();
    if (form && typeof form.requestSubmit === "function") {
      form.requestSubmit();
    } else if (form) {
      form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    }
  }

  seedFromDom();
  scrollToBottom(true);

  if (form) {
    ensureIdemField();
    form.addEventListener("submit", onSubmit);
  }
  if (textarea) {
    textarea.addEventListener("keydown", onKeydown);
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") {
      stopPoll();
    } else {
      pollOnce();
      startPoll();
    }
  });

  startPoll();
})();
