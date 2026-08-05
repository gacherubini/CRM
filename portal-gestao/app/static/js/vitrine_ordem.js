/* Ordem na vitrine: drag-and-drop + ↑/↓ com save automático no drop. */
(function () {
  const form = document.querySelector("[data-vitrine-sortable]");
  if (!form) return;

  const lista = document.getElementById("vitrine-lista");
  const campo = document.getElementById("vitrine-ordem-ids");
  const status = document.getElementById("vitrine-status");
  if (!lista || !campo) return;

  let dragging = null;
  let saveTimer = null;

  function rows() {
    return Array.from(lista.querySelectorAll(".vitrine-row"));
  }

  function syncField() {
    campo.value = rows()
      .map((row) => row.getAttribute("data-id") || "")
      .filter(Boolean)
      .join(",");
  }

  function setStatus(text) {
    if (status) status.textContent = text || "";
  }

  function scheduleSave() {
    syncField();
    setStatus("Salvando…");
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      form.requestSubmit();
    }, 280);
  }

  function moveRow(row, delta) {
    const all = rows();
    const idx = all.indexOf(row);
    if (idx < 0) return;
    const target = idx + delta;
    if (target < 0 || target >= all.length) return;
    if (delta < 0) {
      lista.insertBefore(row, all[target]);
    } else {
      lista.insertBefore(all[target], row);
    }
    scheduleSave();
  }

  lista.addEventListener("dragstart", (event) => {
    const row = event.target.closest(".vitrine-row");
    if (!row) return;
    dragging = row;
    row.classList.add("is-dragging");
    try {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", row.getAttribute("data-id") || "");
    } catch (_) {}
  });

  lista.addEventListener("dragend", () => {
    if (dragging) dragging.classList.remove("is-dragging");
    lista.querySelectorAll(".drop-target").forEach((el) => el.classList.remove("drop-target"));
    dragging = null;
  });

  lista.addEventListener("dragover", (event) => {
    event.preventDefault();
    const row = event.target.closest(".vitrine-row");
    if (!row || row === dragging) return;
    lista.querySelectorAll(".drop-target").forEach((el) => el.classList.remove("drop-target"));
    row.classList.add("drop-target");
    const rect = row.getBoundingClientRect();
    const before = event.clientY < rect.top + rect.height / 2;
    if (before) {
      lista.insertBefore(dragging, row);
    } else {
      lista.insertBefore(dragging, row.nextSibling);
    }
  });

  lista.addEventListener("drop", (event) => {
    event.preventDefault();
    lista.querySelectorAll(".drop-target").forEach((el) => el.classList.remove("drop-target"));
    if (dragging) dragging.classList.remove("is-dragging");
    dragging = null;
    scheduleSave();
  });

  lista.addEventListener("click", (event) => {
    const up = event.target.closest(".vitrine-btn-up");
    const down = event.target.closest(".vitrine-btn-down");
    if (!up && !down) return;
    const row = event.target.closest(".vitrine-row");
    if (!row) return;
    event.preventDefault();
    moveRow(row, up ? -1 : 1);
  });

  form.addEventListener("submit", () => {
    syncField();
    setStatus("Salvando…");
  });

  syncField();
})();
