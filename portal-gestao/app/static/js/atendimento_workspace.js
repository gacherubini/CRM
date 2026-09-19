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

  // Horário de Brasília (mesmo fuso do formatar_horario do portal).
  function formatHorario(iso) {
    if (!iso) return "";
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return String(iso);
      var parts = new Intl.DateTimeFormat("pt-BR", {
        timeZone: "America/Sao_Paulo",
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).formatToParts(d);
      var get = function (type) {
        for (var i = 0; i < parts.length; i++) {
          if (parts[i].type === type) return parts[i].value;
        }
        return "";
      };
      return get("day") + "/" + get("month") + " " + get("hour") + ":" + get("minute");
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
    if (msg.tipo === "audio") {
      if (id) {
        var player = document.createElement("audio");
        player.controls = true;
        player.preload = "none";
        player.src = mediaUrl(id);
        bolha.appendChild(player);
      } else {
        bolha.appendChild(document.createTextNode("Áudio"));
      }
    } else {
      bolha.appendChild(document.createTextNode(msg.texto || "—"));
    }
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

  function mediaUrl(id) {
    // pollUrl = .../atendimento/<tel>/mensagens.json → .../atendimento/<tel>
    var base = pollUrl.replace(/\/mensagens\.json.*$/, "");
    return base + "/audio/" + encodeURIComponent(id);
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

  // ---- Áudio do Vendedor (só Modo 2; o servidor decide e o template esconde) ----
  function initAudio() {
    var audioRoot = root.querySelector("[data-audio]");
    if (!audioRoot || typeof MediaRecorder === "undefined") return;
    var startBtn = audioRoot.querySelector("[data-audio-start]");
    var stopBtn = audioRoot.querySelector("[data-audio-stop]");
    var cancelBtn = audioRoot.querySelector("[data-audio-cancel]");
    var sendBtn = audioRoot.querySelector("[data-audio-send]");
    var timeEl = audioRoot.querySelector("[data-audio-time]");
    var preview = audioRoot.querySelector("[data-audio-preview]");
    var statusEl = audioRoot.querySelector("[data-audio-status]");
    var url = audioRoot.getAttribute("data-audio-url") || "";
    var maxSeg = parseInt(audioRoot.getAttribute("data-audio-max") || "180", 10);
    if (!isFinite(maxSeg) || maxSeg <= 0) maxSeg = 180;

    var recorder = null;
    var chunks = [];
    var stream = null;
    var blob = null;
    var timer = null;
    var startedAt = 0;
    var audioSending = false;

    function setStatus(msg, kind) {
      if (!statusEl) return;
      statusEl.textContent = msg || "";
      statusEl.className = "muted" + (kind ? " " + kind : "");
    }
    function show(el, on) {
      if (el) el.hidden = !on;
    }
    function fmt(seg) {
      var m = Math.floor(seg / 60);
      var s = seg % 60;
      return m + ":" + (s < 10 ? "0" : "") + s;
    }
    function stopTracks() {
      if (!stream) return;
      stream.getTracks().forEach(function (t) {
        t.stop();
      });
      stream = null;
    }
    function reset() {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
      recorder = null;
      chunks = [];
      blob = null;
      if (preview) {
        preview.pause();
        preview.removeAttribute("src");
        preview.load();
      }
      show(startBtn, true);
      show(stopBtn, false);
      show(cancelBtn, false);
      show(sendBtn, false);
      show(preview, false);
      show(timeEl, false);
    }
    function start() {
      if (audioSending) return;
      setStatus("Pedindo o microfone…");
      navigator.mediaDevices
        .getUserMedia({ audio: true })
        .then(function (s) {
          stream = s;
          chunks = [];
          try {
            recorder = new MediaRecorder(s);
          } catch (e) {
            recorder = new MediaRecorder(s, { mimeType: "audio/webm" });
          }
          recorder.addEventListener("dataavailable", function (ev) {
            if (ev.data && ev.data.size) chunks.push(ev.data);
          });
          recorder.addEventListener("stop", function () {
            blob = new Blob(chunks, {
              type: (recorder && recorder.mimeType) || "audio/webm",
            });
            if (preview) preview.src = URL.createObjectURL(blob);
            show(preview, true);
            show(sendBtn, true);
            show(cancelBtn, true);
            stopTracks();
          });
          recorder.start();
          startedAt = Date.now();
          if (timeEl) timeEl.textContent = "0:00";
          show(timeEl, true);
          show(startBtn, false);
          show(stopBtn, true);
          setStatus("Gravando…");
          timer = setInterval(function () {
            var seg = Math.floor((Date.now() - startedAt) / 1000);
            if (timeEl) timeEl.textContent = fmt(seg);
            if (seg >= maxSeg) stop();
          }, 500);
        })
        .catch(function () {
          setStatus("Não foi possível acessar o microfone.", "warn");
        });
    }
    function stop() {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
      if (recorder && recorder.state !== "inactive") {
        try {
          recorder.stop();
        } catch (e) {}
      }
      show(stopBtn, false);
      setStatus("Revise e envie.");
    }
    function cancel() {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
      if (recorder && recorder.state !== "inactive") {
        try {
          recorder.stop();
        } catch (e) {}
      }
      stopTracks();
      reset();
      setStatus("");
    }
    function send() {
      if (!blob || audioSending) return;
      if (typeof fetch !== "function") {
        setStatus("Envio indisponível neste navegador.", "warn");
        return;
      }
      var csrf = form ? form.querySelector('input[name="csrf"]') : null;
      var canal = form ? form.querySelector('input[name="canal_id"]') : null;
      var body = new FormData();
      body.append("arquivo", blob, "voz.webm");
      if (csrf) body.append("csrf", csrf.value);
      if (canal) body.append("canal_id", canal.value);
      body.append("idempotency_key", newIdempotencyKey());
      body.append(
        "duracao_segundos",
        String(Math.max(1, Math.round((Date.now() - startedAt) / 1000)))
      );
      audioSending = true;
      if (sendBtn) sendBtn.disabled = true;
      setStatus("Enviando áudio…");
      fetch(url, {
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
            setStatus(data.message || "Não foi possível enviar o áudio.", "warn");
            return;
          }
          if (data.mensagem) appendMensagem(data.mensagem, { forceScroll: true });
          var botBadge = document.querySelector("[data-bot-status]");
          if (botBadge && data.bot_ativo === false) {
            botBadge.textContent = "Pausado (humano)";
            botBadge.className = "status em_atendimento";
          }
          reset();
          setStatus(data.duplicada ? "Áudio já enviado." : "Áudio enviado.", "ok");
        })
        .catch(function () {
          setStatus("Não foi possível enviar o áudio agora.", "warn");
        })
        .finally(function () {
          audioSending = false;
          if (sendBtn) sendBtn.disabled = false;
        });
    }

    if (startBtn) startBtn.addEventListener("click", start);
    if (stopBtn) stopBtn.addEventListener("click", stop);
    if (cancelBtn) cancelBtn.addEventListener("click", cancel);
    if (sendBtn) sendBtn.addEventListener("click", send);
  }

  seedFromDom();
  scrollToBottom(true);
  initAudio();

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
