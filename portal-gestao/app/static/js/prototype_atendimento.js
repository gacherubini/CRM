/* DESCARTÁVEL. Nenhum fetch, POST ou armazenamento persistente. */
(() => {
  const root = document.querySelector('[data-prototype]');
  if (!root) return;
  const names = { A: 'Conversa e contexto', B: 'Conversa em foco', C: 'Ficha de trabalho' };
  const state = { variant: root.dataset.variant, bot: 'Pausado (humano)', responsavel: 'Rafael Demo', etapa: 'Em atendimento', mensagens: 6, enviosSimulados: 0, ultimaAcao: 'Demonstração iniciada' };
  const feedback = root.querySelector('[data-feedback]');
  const actionDialog = root.querySelector('[data-action-dialog]');
  const detailDialog = root.querySelector('[data-details-dialog]');
  let feedbackTimer;
  if (window.matchMedia('(max-width: 760px)').matches) {
    root.querySelector('.pa-c .pa-disclosure[open]').open = false;
  }

  function showState() {
    root.querySelector('[data-state]').textContent = JSON.stringify({ ...state, canal: 'WhatsApp da loja · conectado', interesse: 'Yamaha Fazer FZ25 · 2024 · Azul', origem: 'Instagram · Fazer para o dia a dia', venda: 'Sem venda registrada', persistencia: false }, null, 2);
    root.querySelectorAll('[data-bot]').forEach(el => { el.textContent = state.bot; });
    root.querySelectorAll('[data-owner]').forEach(el => { el.textContent = state.responsavel; });
    root.querySelectorAll('[data-owner-email]').forEach(el => { el.textContent = state.bot === 'Ativo' ? 'Sem responsável' : 'rafael@example.invalid'; });
    root.querySelectorAll('[data-handoff]').forEach(el => { el.textContent = state.bot === 'Ativo' ? 'Assumir atendimento' : 'Devolver ao bot'; });
    root.querySelectorAll('[data-handoff-hint]').forEach(el => { el.textContent = state.bot === 'Ativo' ? 'Ao assumir, o bot para de responder e você vira o responsável.' : 'O bot está pausado. Você responde por este contato.'; });
  }
  function announce(text) {
    state.ultimaAcao = text;
    feedback.textContent = `Demonstração: ${text}`;
    feedback.hidden = false;
    clearTimeout(feedbackTimer);
    feedbackTimer = setTimeout(() => { feedback.hidden = true; }, 6500);
    showState();
  }
  function switchVariant(key) {
    state.variant = names[key] ? key : 'A';
    root.dataset.variant = state.variant;
    root.querySelectorAll('[data-panel]').forEach(el => { el.hidden = el.dataset.panel !== state.variant; });
    root.querySelectorAll('[data-switch]').forEach(el => { el.setAttribute('aria-current', String(el.dataset.switch === state.variant)); });
    root.querySelector('[data-variant-label]').textContent = `${state.variant} · ${names[state.variant]}`;
    const url = new URL(location.href);
    url.searchParams.set('variant', state.variant);
    history.replaceState(null, '', url);
    const thread = root.querySelector(`[data-panel="${state.variant}"] [data-thread]`);
    thread.scrollTop = thread.scrollHeight;
    showState();
  }
  function cycle(step) {
    const keys = Object.keys(names);
    switchVariant(keys[(keys.indexOf(state.variant) + step + keys.length) % keys.length]);
  }
  root.querySelectorAll('[data-cycle]').forEach(el => el.addEventListener('click', () => cycle(Number(el.dataset.cycle))));
  root.querySelectorAll('[data-switch]').forEach(el => el.addEventListener('click', event => { event.preventDefault(); switchVariant(el.dataset.switch); }));
  window.addEventListener('popstate', () => switchVariant(new URL(location.href).searchParams.get('variant')));
  document.addEventListener('keydown', event => {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || document.querySelector('dialog[open]')) return;
    if (event.target.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"])')) return;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault(); cycle(event.key === 'ArrowLeft' ? -1 : 1);
    }
  });
  root.querySelectorAll('[data-send-form]').forEach(form => {
    form.addEventListener('submit', event => {
      event.preventDefault();
      const field = form.elements.mensagem;
      const text = field.value.trim();
      if (!text) return;
      root.querySelectorAll('[data-thread]').forEach(thread => {
        const bubble = document.createElement('div');
        bubble.className = 'pa-message saida';
        const paragraph = document.createElement('p');
        paragraph.textContent = text;
        const note = document.createElement('small');
        note.textContent = 'Você · Agora · Envio simulado';
        bubble.append(paragraph, note); thread.append(bubble); thread.scrollTop = thread.scrollHeight;
      });
      root.querySelectorAll('[data-send-form] textarea').forEach(el => { el.value = ''; });
      state.bot = 'Pausado (humano)'; state.responsavel = 'Rafael Demo';
      state.mensagens++; state.enviosSimulados++;
      announce('mensagem adicionada à conversa local. Nenhuma mensagem enviada.');
      field.focus();
    });
    form.elements.mensagem.addEventListener('keydown', event => {
      if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); form.requestSubmit(); }
    });
    form.elements.mensagem.addEventListener('input', event => {
      root.querySelectorAll('[data-send-form] textarea').forEach(el => { if (el !== event.target) el.value = event.target.value; });
    });
  });
  root.querySelectorAll('[data-handoff]').forEach(button => button.addEventListener('click', () => {
    state.bot = state.bot === 'Ativo' ? 'Pausado (humano)' : 'Ativo';
    state.responsavel = state.bot === 'Ativo' ? 'Fila (sem responsável)' : 'Rafael Demo';
    announce(state.bot === 'Ativo' ? 'devolução ao bot simulada. Nenhuma integração acionada.' : 'atendimento assumido somente nesta página.');
  }));
  root.querySelectorAll('[data-stage-form]').forEach(form => form.addEventListener('submit', event => {
    event.preventDefault(); state.etapa = form.elements.etapa.value;
    root.querySelectorAll('[name="etapa"]').forEach(el => { el.value = state.etapa; });
    announce(`etapa alterada para “${state.etapa}” somente nesta página.`);
  }));
  root.querySelector('[data-open-details]').addEventListener('click', () => detailDialog.showModal());
  root.querySelectorAll('[data-close-dialog]').forEach(el => el.addEventListener('click', () => el.closest('dialog').close()));

  const actionContent = {
    simulation: ['Nova simulação', 'Marina Demo · (00) 00000-0142', 'Yamaha Fazer FZ25 · 2024 · Azul', 'O celular já estaria preenchido. A consulta aos bancos não é executada neste protótipo.'],
    sale: ['Nova venda', 'Lead selecionado: Marina Demo', 'Interesse: Yamaha Fazer FZ25', 'Aqui começaria o registro de uma venda. Nenhuma venda foi criada.'],
    lead: ['Ficha do lead', 'Marina Demo · (00) 00000-0142', 'Origem: Fazer para o dia a dia · Instagram', 'Primeiro contato: 09/09, às 10:12', 'Interesse: Yamaha Fazer FZ25 · 2024 · Azul'],
    history: ['Histórico da conversa', '09/09 · 10:12 — Primeiro contato pelo anúncio da Fazer.', '09/09 · 10:14 — Bot encaminhou a simulação para atendimento humano.', '09/09 · 10:17 — Rafael Demo assumiu. Bot pausado.'],
    list: ['Lista de atendimento', 'Marina Demo — Aguardando simulação humana', 'Bruno Demo — Em atendimento', 'Carla Demo — Novo contato', 'Somente a conversa da Marina está disponível neste estudo. Feche para continuar comparando.'],
  };
  function openAction(key) {
    const content = actionContent[key];
    actionDialog.querySelector('h2').textContent = content[0];
    const body = actionDialog.querySelector('[data-action-body]');
    body.replaceChildren();
    for (const text of content.slice(1)) { const p = document.createElement('p'); p.textContent = text; body.append(p); }
    if (key === 'lead') { const p = document.createElement('p'); p.textContent = `Etapa atual: ${state.etapa}`; body.append(p); }
    state.ultimaAcao = `${content[0]}: prévia demonstrativa`; showState(); actionDialog.showModal();
  }
  root.querySelectorAll('[data-action]').forEach(el => el.addEventListener('click', () => openAction(el.dataset.action)));
  // A navegação do shell real também fica dentro da demonstração.
  document.addEventListener('click', event => {
    const anchor = event.target.closest('a[href]');
    if (!anchor || anchor.closest('[data-prototype]')) return;
    event.preventDefault();
    announce(`“${anchor.textContent.trim() || 'Navegação'}” pertence ao shell; continue comparando A, B e C.`);
  });
  document.addEventListener('submit', event => {
    if (!event.target.closest('[data-prototype]')) { event.preventDefault(); announce('ação do shell indisponível neste estudo.'); }
  }, true);
  switchVariant(state.variant);
})();
