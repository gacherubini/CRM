/* Grade da vitrine: reordenação local na página; ordem global no hidden field. */
(function () {
  const form = document.querySelector("[data-vitrine-grid]");
  if (!form) return;

  const lista = document.getElementById("vitrine-lista");
  const campo = document.getElementById("vitrine-ordem-ids");
  const status = document.getElementById("vitrine-status");
  const btnSalvar = document.getElementById("vitrine-salvar");
  const btnDescartar = document.getElementById("vitrine-descartar");
  const offsetInput = form.querySelector('input[name="offset"]');
  if (!lista || !campo) return;

  const offset = Math.max(0, parseInt(form.dataset.offset || "0", 10) || 0);
  const initialOrder = (campo.dataset.initial || campo.value || "").trim();
  let dragging = null;
  let lastOverId = null;
  let rafPending = false;
  let pendingOver = null;

  function cards() {
    return Array.from(lista.querySelectorAll(".vitrine-card"));
  }

  function fullIds() {
    return (campo.value || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function pageIds() {
    return cards()
      .map((card) => card.getAttribute("data-id") || "")
      .filter(Boolean);
  }

  /** Reaplica a ordem dos cards da página no array global. */
  function mergePageIntoGlobal() {
    const full = fullIds();
    const page = pageIds();
    if (!page.length) return full;
    const next = full.slice();
    // Garante que o recorte da página tem o tamanho certo
    const len = page.length;
    next.splice(offset, len, ...page);
    return next;
  }

  function syncField() {
    campo.value = mergePageIntoGlobal().join(",");
  }

  function refreshBadges() {
    cards().forEach((card, index) => {
      const badge = card.querySelector("[data-pos]");
      if (badge) badge.textContent = String(offset + index + 1);
    });
  }

  function setDirty(dirty) {
    if (btnSalvar) btnSalvar.disabled = !dirty;
    if (btnDescartar) btnDescartar.disabled = !dirty;
    form.classList.toggle("is-dirty", dirty);
    if (status) {
      status.textContent = dirty
        ? "Ordem alterada — clique em Salvar para publicar"
        : "Sem alterações";
    }
  }

  function markIfChanged() {
    syncField();
    refreshBadges();
    setDirty(campo.value !== initialOrder);
  }

  /**
   * Salva a ordem GLOBAL crua e navega para `targetOffset`.
   * Usa form.submit() de propósito: ele NÃO dispara o listener de submit,
   * então o merge por-página (mergePageIntoGlobal) não roda e não desfaz a
   * ordem global que acabamos de montar. O POST redireciona para a página alvo.
   */
  function saveGlobalOrder(order, targetOffset) {
    campo.value = order.join(",");
    if (offsetInput) offsetInput.value = String(Math.max(0, targetOffset || 0));
    if (status) status.textContent = "Salvando…";
    if (btnSalvar) btnSalvar.disabled = true;
    form.submit();
  }

  /** Traz o veículo para a frente da vitrine (posição 1), de qualquer página. */
  function moveToTop(card) {
    const id = card.getAttribute("data-id");
    if (!id) return;
    syncField(); // preserva rearranjos desta página antes de promover
    const full = fullIds().filter((x) => x !== id);
    full.unshift(id);
    saveGlobalOrder(full, 0); // salva e cai na página 1, com o item na frente
  }

  function moveCard(card, delta) {
    const all = cards();
    const idx = all.indexOf(card);
    if (idx < 0) return;
    const target = idx + delta;
    if (target < 0 || target >= all.length) return;
    if (delta < 0) {
      lista.insertBefore(card, all[target]);
    } else {
      lista.insertBefore(all[target], card);
    }
    markIfChanged();
  }

  function placeBefore(source, target) {
    if (!source || !target || source === target) return;
    const all = cards();
    const si = all.indexOf(source);
    const ti = all.indexOf(target);
    if (si < 0 || ti < 0) return;
    if (si < ti) {
      lista.insertBefore(source, target.nextSibling);
    } else {
      lista.insertBefore(source, target);
    }
  }

  lista.addEventListener("dragstart", (event) => {
    const card = event.target.closest(".vitrine-card");
    if (!card) return;
    dragging = card;
    lastOverId = null;
    card.classList.add("is-dragging");
    try {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", card.getAttribute("data-id") || "");
    } catch (_) {}
  });

  lista.addEventListener("dragend", () => {
    if (dragging) dragging.classList.remove("is-dragging");
    lista.querySelectorAll(".is-drop-over").forEach((el) => el.classList.remove("is-drop-over"));
    dragging = null;
    lastOverId = null;
    pendingOver = null;
    markIfChanged();
  });

  lista.addEventListener("dragover", (event) => {
    event.preventDefault();
    if (!dragging) return;
    const over = event.target.closest(".vitrine-card");
    if (!over || over === dragging) return;
    pendingOver = over;
    if (rafPending) return;
    rafPending = true;
    requestAnimationFrame(() => {
      rafPending = false;
      const target = pendingOver;
      pendingOver = null;
      if (!dragging || !target || target === dragging) return;
      const id = target.getAttribute("data-id");
      if (id && id === lastOverId) return;
      lastOverId = id;
      lista.querySelectorAll(".is-drop-over").forEach((el) => el.classList.remove("is-drop-over"));
      target.classList.add("is-drop-over");
      placeBefore(dragging, target);
      refreshBadges();
    });
  });

  lista.addEventListener("drop", (event) => {
    event.preventDefault();
    lista.querySelectorAll(".is-drop-over").forEach((el) => el.classList.remove("is-drop-over"));
    if (dragging) dragging.classList.remove("is-dragging");
    dragging = null;
    lastOverId = null;
    markIfChanged();
  });

  lista.addEventListener("click", (event) => {
    const top = event.target.closest(".vitrine-btn-top");
    const left = event.target.closest(".vitrine-btn-up");
    const right = event.target.closest(".vitrine-btn-down");
    if (!top && !left && !right) return;
    const card = event.target.closest(".vitrine-card");
    if (!card) return;
    event.preventDefault();
    if (top) {
      moveToTop(card);
      return;
    }
    moveCard(card, left ? -1 : 1);
  });

  if (btnDescartar) {
    btnDescartar.addEventListener("click", () => {
      // Recarrega a página limpa (ordem inicial do servidor).
      window.location.reload();
    });
  }

  // Paginação: com alterações não salvas, salva a ordem global e navega para a
  // página escolhida (sem confirm bloqueante e sem perder a ordem). Sem
  // alterações, deixa a navegação normal do link acontecer.
  form.querySelectorAll("[data-vitrine-page]").forEach((link) => {
    link.addEventListener("click", (event) => {
      syncField();
      if (campo.value === initialOrder) return; // nada a salvar
      event.preventDefault();
      let targetOffset = 0;
      try {
        const url = new URL(link.href, window.location.origin);
        targetOffset = parseInt(url.searchParams.get("offset") || "0", 10) || 0;
      } catch (_) {}
      saveGlobalOrder(fullIds(), targetOffset);
    });
  });

  form.addEventListener("submit", (event) => {
    syncField();
    if (campo.value === initialOrder) {
      event.preventDefault();
      setDirty(false);
      return;
    }
    if (status) status.textContent = "Salvando…";
    if (btnSalvar) btnSalvar.disabled = true;
  });

  setDirty(false);
  refreshBadges();
})();
