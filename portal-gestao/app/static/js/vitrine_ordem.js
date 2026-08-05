/* Grade da vitrine: reordenação local sem save automático. */
(function () {
  const form = document.querySelector("[data-vitrine-grid]");
  if (!form) return;

  const lista = document.getElementById("vitrine-lista");
  const campo = document.getElementById("vitrine-ordem-ids");
  const status = document.getElementById("vitrine-status");
  const btnSalvar = document.getElementById("vitrine-salvar");
  const btnDescartar = document.getElementById("vitrine-descartar");
  if (!lista || !campo) return;

  const initialOrder = (campo.dataset.initial || campo.value || "").trim();
  let dragging = null;
  let lastOverId = null;
  let rafPending = false;
  let pendingOver = null;

  function cards() {
    return Array.from(lista.querySelectorAll(".vitrine-card"));
  }

  function currentOrder() {
    return cards()
      .map((card) => card.getAttribute("data-id") || "")
      .filter(Boolean)
      .join(",");
  }

  function refreshBadges() {
    cards().forEach((card, index) => {
      const badge = card.querySelector("[data-pos]");
      if (badge) badge.textContent = String(index + 1);
    });
  }

  function syncField() {
    campo.value = currentOrder();
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
      // Ghost mais limpo em alguns browsers
      if (event.dataTransfer.setDragImage) {
        event.dataTransfer.setDragImage(card, card.clientWidth / 2, 40);
      }
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
    const left = event.target.closest(".vitrine-btn-up");
    const right = event.target.closest(".vitrine-btn-down");
    if (!left && !right) return;
    const card = event.target.closest(".vitrine-card");
    if (!card) return;
    event.preventDefault();
    moveCard(card, left ? -1 : 1);
  });

  if (btnDescartar) {
    btnDescartar.addEventListener("click", () => {
      const ids = initialOrder.split(",").filter(Boolean);
      const map = new Map(cards().map((c) => [c.getAttribute("data-id"), c]));
      ids.forEach((id) => {
        const card = map.get(id);
        if (card) lista.appendChild(card);
      });
      markIfChanged();
    });
  }

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
