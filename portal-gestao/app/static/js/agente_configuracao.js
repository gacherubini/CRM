/* Configuração do agente por loja.
 *
 * A Loja é só tela: este arquivo lê o formulário, monta o JSON de `campos` e
 * manda para o chatbot, que valida, gera o prompt e devolve os conflitos. Nada
 * de texto de prompt é montado aqui — se estivesse, o navegador e o backend
 * divergiriam no primeiro campo novo.
 *
 * pytest não roda isto (já passou dois bugs no Copiloto): a verificação é no
 * navegador, com o portal local semeado.
 */
(() => {
  const form = document.getElementById('agente-config');
  if (!form) return;

  const csrf = form.dataset.csrf || '';
  const modo = form.dataset.modo || '1';
  const maxInstrucoes = Number(form.dataset.maxInstrucoes || 1000);
  const status = document.getElementById('agente-status');
  const promptEl = document.getElementById('agente-prompt');
  const conflitosEl = document.getElementById('agente-conflitos');
  const contadorEl = document.getElementById('agente-contador');
  const faqEl = document.getElementById('agente-faq');
  const faqVazioEl = document.querySelector('.agente-config-faq-vazio');

  const CONFLITO_TEXTO = {
    parcela: 'falar de parcela, taxa, juros, banco ou prazo com o cliente',
    insistir: 'insistir depois de o cliente recusar',
    dados: 'pedir renda ou placa ao cliente',
    estoque: 'afirmar disponibilidade sem consultar o estoque',
  };

  const val = (nome) => {
    const el = form.querySelector(`[name="${nome}"]`);
    return el ? el.value : '';
  };
  const marcado = (nome) => {
    const el = form.querySelector(`[name="${nome}"]`);
    return Boolean(el && el.checked);
  };
  const lista = (nome) =>
    val(nome)
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);
  const grupo = (nome) =>
    Array.from(form.querySelectorAll(`[data-grupo="${nome}"]:checked`)).map(
      (el) => el.value,
    );

  function horario() {
    const out = {};
    form.querySelectorAll('.agente-config-dia').forEach((linha) => {
      const aberto = linha.querySelector('[data-papel="dia-aberto"]');
      if (!aberto || !aberto.checked) return;
      const abre = linha.querySelector('[data-papel="abre"]');
      const fecha = linha.querySelector('[data-papel="fecha"]');
      // O backend exige HH:MM com zero à esquerda: "8:00" compara errado na
      // janela de horário e deixa o bot mudo o dia inteiro, sem erro nenhum.
      const dois = (v) => String(v || '').slice(0, 5).padStart(5, '0');
      out[linha.dataset.dia] = [dois(abre && abre.value), dois(fecha && fecha.value)];
    });
    return out;
  }

  function faq() {
    return Array.from(faqEl.querySelectorAll('.agente-config-faq-item'))
      .map((item) => ({
        pergunta: (item.querySelector('[data-papel="faq-pergunta"]').value || '').trim(),
        resposta: (item.querySelector('[data-papel="faq-resposta"]').value || '').trim(),
      }))
      .filter((par) => par.pergunta && par.resposta);
  }

  function campos() {
    const dados = {
      nome_loja: val('nome_loja').trim(),
      cidade: val('cidade').trim(),
      uf: val('uf').trim().toUpperCase(),
      endereco_completo: val('endereco_completo') === '1',
      endereco: val('endereco').trim(),
      entrega: val('entrega').trim(),
      horario: horario(),
      nome_agente: val('nome_agente').trim(),
      assume_ia: val('assume_ia'),
      tom: val('tom'),
      tratamento: val('tratamento'),
      escrita: val('escrita'),
      emoji: val('emoji'),
      tamanho_resposta: val('tamanho_resposta'),
      expressoes: lista('expressoes'),
      nunca_diga: lista('nunca_diga'),
      faq: faq(),
      oferece: grupo('oferece'),
      // `disabled` não entra em FormData e o select some do payload: no Modo 2 o
      // campo de fotos é lido do valor que veio do servidor, não do DOM vazio.
      fotos: val('fotos') || 'so_quando_pedir',
      sem_moto_anuncio: val('sem_moto_anuncio'),
      handoff: grupo('handoff'),
      cita_vendedor: val('cita_vendedor') === '1',
      agente_ativo: marcado('agente_ativo'),
      so_horario_comercial: marcado('so_horario_comercial'),
      instrucoes: val('instrucoes'),
    };
    // Só Modo 2 tem o interruptor na tela. No Modo 1 o valor guardado é
    // repassado como veio: mandar o default a partir de um campo que não existe
    // ligaria de volta o follow-up de uma loja que o desligou quando era Modo 2.
    dados.followup_ativo =
      modo === '2' ? marcado('followup_ativo') : form.dataset.followupAtivo === '1';
    return dados;
  }

  function contador() {
    if (!contadorEl) return;
    const n = val('instrucoes').length;
    contadorEl.textContent = String(n);
    contadorEl.parentElement.classList.toggle('agente-config-contador-cheio', n >= maxInstrucoes);
  }

  function mostrarConflitos(conflitos) {
    if (!conflitosEl) return;
    const itens = (conflitos || []).map((c) => CONFLITO_TEXTO[c] || c);
    if (!itens.length) {
      conflitosEl.hidden = true;
      conflitosEl.textContent = '';
      return;
    }
    conflitosEl.hidden = false;
    conflitosEl.textContent =
      'Isto conflita com uma regra do Revy e o agente vai ignorar: ' +
      itens.join('; ') +
      '. Você pode salvar assim mesmo.';
  }

  let pendente = null;
  let salvando = false;

  // `salvar` devolve se deu certo: Publicar leva o RASCUNHO ao ar, então
  // publicar depois de um autosave que falhou põe no ar o texto anterior — e o
  // lojista vê "Publicado" para uma edição que nunca foi salva.
  async function salvar() {
    if (salvando) return false;
    salvando = true;
    status.textContent = 'Salvando…';
    try {
      const r = await fetch('/app/loja/agente/configuracao.json', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csrf, campos: campos() }),
      });
      const corpo = await r.json().catch(() => ({}));
      if (!r.ok) {
        // 422 é campo inválido, não "texto proibido": o aviso de conflito nunca
        // bloqueia (spec §4.5).
        const quais = (corpo.campos || []).join(', ');
        status.textContent =
          r.status === 422
            ? `Não salvei: confira ${quais || 'os campos'}.`
            : corpo.message || 'Não foi possível salvar agora.';
        status.classList.add('agente-config-status-erro');
        return false;
      }
      status.classList.remove('agente-config-status-erro');
      status.textContent = 'Rascunho salvo.';
      if (promptEl && typeof corpo.prompt === 'string') promptEl.textContent = corpo.prompt;
      mostrarConflitos(corpo.conflitos);
      return true;
    } catch (e) {
      status.textContent = 'Sem conexão. O que você digitou ainda não foi salvo.';
      status.classList.add('agente-config-status-erro');
      return false;
    } finally {
      salvando = false;
    }
  }

  function agendar() {
    contador();
    status.classList.remove('agente-config-status-erro');
    status.textContent = 'Editando…';
    if (pendente) clearTimeout(pendente);
    pendente = setTimeout(salvar, 900);
  }

  function atualizarFaqVazio() {
    if (!faqVazioEl) return;
    faqVazioEl.hidden = faqEl.querySelectorAll('.agente-config-faq-item').length > 0;
  }

  document.getElementById('agente-faq-add')?.addEventListener('click', () => {
    const item = document.createElement('div');
    item.className = 'agente-config-faq-item';
    item.innerHTML =
      '<label>Quando perguntarem sobre<input data-papel="faq-pergunta" maxlength="120"></label>' +
      '<label>Responda exatamente<input data-papel="faq-resposta" maxlength="400"></label>' +
      '<button type="button" class="button ghost" data-papel="faq-remover">Remover</button>';
    faqEl.appendChild(item);
    atualizarFaqVazio();
    item.querySelector('[data-papel="faq-pergunta"]').focus();
  });

  faqEl?.addEventListener('click', (ev) => {
    const botao = ev.target.closest('[data-papel="faq-remover"]');
    if (!botao) return;
    botao.closest('.agente-config-faq-item').remove();
    atualizarFaqVazio();
    agendar();
  });

  form.addEventListener('input', agendar);
  form.addEventListener('change', agendar);
  form.addEventListener('submit', (ev) => ev.preventDefault());

  // Publicar leva o RASCUNHO ao ar. Uma edição na fila de autosave que não
  // chegasse antes publicaria o texto anterior — por isso o clique espera.
  document
    .querySelector('.agente-config-acoes form')
    ?.addEventListener('submit', async (ev) => {
      if (!pendente) return;
      ev.preventDefault();
      clearTimeout(pendente);
      pendente = null;
      if (await salvar()) ev.target.submit();
      // Falhou: o status já diz o que houve, e publicar poria no ar o texto
      // anterior — pior que não publicar, porque diz "Publicado".
    });

  // Restaurar sobrescreve o rascunho aberto. Confirmação antes, não depois.
  document.querySelectorAll('form[data-confirmar]').forEach((f) => {
    f.addEventListener('submit', (ev) => {
      if (!window.confirm(f.dataset.confirmar)) ev.preventDefault();
    });
  });

  // --- conversa de teste ---------------------------------------------------
  // O histórico vive só aqui, no navegador: a conversa de teste não entra em
  // Conversas, não vira lead e some quando o lojista sai da tela.
  const conversaEl = document.getElementById('agente-teste-conversa');
  const textoEl = document.getElementById('agente-teste-texto');
  const enviarEl = document.getElementById('agente-teste-enviar');
  const vazioEl = document.getElementById('agente-teste-vazio');
  // Mesmo formato de `historico_recente` do bot real
  // (`- [entrada] …` / `- [saida] …`, últimas 10): o prompt manda usar o
  // histórico como contexto, e um formato diferente aqui faria o preview
  // responder diferente do WhatsApp por um motivo que ninguém veria.
  const historico = [];
  const MAX_HISTORICO = 10;

  function bolha(quem, texto) {
    const li = document.createElement('li');
    li.className = 'agente-teste-bolha agente-teste-' + quem;
    li.textContent = texto;
    conversaEl.appendChild(li);
    if (vazioEl) vazioEl.hidden = true;
    li.scrollIntoView({ block: 'nearest' });
    return li;
  }

  async function testar() {
    const texto = (textoEl.value || '').trim();
    if (!texto || enviarEl.disabled) return;
    // Publica o rascunho pendente antes de testar: sem isso o lojista digita uma
    // regra, clica em Enviar e conversa com a versão anterior do próprio agente.
    if (pendente) {
      clearTimeout(pendente);
      pendente = null;
      if (!(await salvar())) return;
    }
    textoEl.value = '';
    bolha('cliente', texto);
    const esperando = bolha('agente', 'digitando…');
    esperando.classList.add('agente-teste-esperando');
    enviarEl.disabled = true;
    try {
      const r = await fetch('/app/loja/agente/configuracao/testar.json', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          csrf,
          texto,
          historico: historico.slice(-MAX_HISTORICO).join('\n'),
          turno: historico.length + 1,
          primeira_mensagem: historico.length === 0,
        }),
      });
      const corpo = await r.json().catch(() => ({}));
      esperando.classList.remove('agente-teste-esperando');
      if (!r.ok) {
        esperando.classList.add('agente-teste-erro');
        esperando.textContent = corpo.message || 'O teste não respondeu agora.';
        return;
      }
      esperando.textContent = corpo.resposta || '(sem resposta)';
      historico.push('- [entrada] ' + texto, '- [saida] ' + (corpo.resposta || ''));
    } catch (e) {
      esperando.classList.remove('agente-teste-esperando');
      esperando.classList.add('agente-teste-erro');
      esperando.textContent = 'Sem conexão com o teste.';
    } finally {
      enviarEl.disabled = false;
      textoEl.focus();
    }
  }

  enviarEl?.addEventListener('click', testar);
  textoEl?.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') {
      ev.preventDefault();
      testar();
    }
  });

  contador();
  atualizarFaqVazio();
})();
