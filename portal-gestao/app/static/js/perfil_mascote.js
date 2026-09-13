/* Perfil: prévia imediata da foto + mascote-bichinho arrastável no canto.
   Sem backend e sem fetch: a posição do mascote vive em localStorage e todo
   o resto é DOM local. Falha fechada — sem JS a tela segue enviando os dois
   formulários do jeito antigo. */
(function () {
  "use strict";

  var LIMITE_BYTES = 2 * 1024 * 1024;
  var CHAVE_POS = "revy-mascote-pos";
  var LIMIAR_ARRASTO_PX = 6;
  var MARGEM_TELA_PX = 8;
  var PASSO_TECLADO_PX = 16;

  function $(seletor, raiz) {
    return (raiz || document).querySelector(seletor);
  }

  /* Prévia imediata do arquivo: mostra na linha do upload, na foto em
     destaque e no mascote antes mesmo de enviar. Validação espelha o
     backend (JPG/PNG/WEBP até 2 MB) só para não prometer o que vai cair. */
  function iniciarPrevia() {
    var entrada = $("[data-perfil-arquivo]");
    if (!entrada) return;
    var nome = $("[data-perfil-arquivo-nome]");
    var previa = $("[data-perfil-previa-img]");
    var erro = $("[data-perfil-foto-erro]");
    var heroi = $("[data-perfil-hero]");
    var mascoteArte = $("[data-mascote-arte]");

    function mostrarErro(texto) {
      if (erro) {
        erro.textContent = texto;
        erro.hidden = false;
      }
      if (nome) nome.textContent = "Nenhuma foto escolhida";
      if (previa) {
        previa.removeAttribute("src");
        previa.hidden = true;
      }
    }

    entrada.addEventListener("change", function () {
      if (erro) {
        erro.textContent = "";
        erro.hidden = true;
      }
      var arquivo = entrada.files && entrada.files[0];
      if (!arquivo) {
        if (nome) nome.textContent = "Nenhuma foto escolhida";
        return;
      }
      var tipo = (arquivo.type || "").toLowerCase();
      var tipoOk =
        tipo === "image/jpeg" || tipo === "image/png" || tipo === "image/webp";
      if (!tipoOk) {
        entrada.value = "";
        mostrarErro("Formato de foto inválido (use JPG, PNG ou WEBP).");
        return;
      }
      if (arquivo.size > LIMITE_BYTES) {
        entrada.value = "";
        mostrarErro("A foto excede o limite de 2 MB. Escolha uma imagem menor.");
        return;
      }
      if (nome) nome.textContent = arquivo.name;
      var leitor = new FileReader();
      leitor.onload = function () {
        var url = String(leitor.result || "");
        if (!url) return;
        if (previa) {
          previa.src = url;
          previa.hidden = false;
        }
        // A <img> do herói sai sozinha (onerror) quando não há foto: se ela
        // já se removeu, recria para a prévia aparecer em destaque também.
        if (heroi) {
          var imgHeroi = $("[data-perfil-hero-img]", heroi);
          if (!imgHeroi) {
            imgHeroi = document.createElement("img");
            imgHeroi.setAttribute("data-perfil-hero-img", "");
            imgHeroi.alt = "";
            imgHeroi.decoding = "async";
            heroi.insertBefore(imgHeroi, heroi.firstChild);
          }
          imgHeroi.src = url;
          imgHeroi.onerror = null;
        }
        if (mascoteArte) {
          mascoteArte.textContent = "";
          var imgMascote = document.createElement("img");
          imgMascote.src = url;
          imgMascote.alt = "";
          mascoteArte.appendChild(imgMascote);
        }
      };
      leitor.readAsDataURL(arquivo);
    });
  }

  /* O mascote acompanha o bichinho marcado na grade, antes de salvar. */
  function iniciarEspelhoAvatar() {
    var grade = $("[data-avatar-grade]");
    var mascoteArte = $("[data-mascote-arte]");
    if (!grade || !mascoteArte) return;
    grade.addEventListener("change", function (evento) {
      var alvo = evento.target;
      if (!alvo || !alvo.matches || !alvo.matches("[data-avatar-radio]")) return;
      var rotulo = alvo.closest("[data-avatar-opcao]");
      var arte = rotulo && $("[data-avatar-arte]", rotulo);
      if (!arte) return;
      // Foto marcada? O upload limpa o preset no servidor; aqui o mascote
      // só espelha a grade — a foto nova chega pela prévia acima.
      mascoteArte.innerHTML = arte.innerHTML;
    });
  }

  function lerPosicaoSalva() {
    try {
      var cru = localStorage.getItem(CHAVE_POS);
      if (!cru) return null;
      var pos = JSON.parse(cru);
      if (
        !pos ||
        !isFinite(pos.left) ||
        !isFinite(pos.top)
      ) {
        return null;
      }
      return pos;
    } catch (e) {
      return null;
    }
  }

  function salvarPosicao(left, top) {
    try {
      localStorage.setItem(CHAVE_POS, JSON.stringify({ left: left, top: top }));
    } catch (e) {
      /* Modo privado sem storage: arrastar segue funcionando na sessão. */
    }
  }

  function esquecerPosicao() {
    try {
      localStorage.removeItem(CHAVE_POS);
    } catch (e) {
      /* Nada a fazer: o padrão (canto) já vale. */
    }
  }

  function prenderNaTela(left, top, largura, altura) {
    var maxLeft = Math.max(MARGEM_TELA_PX, window.innerWidth - largura - MARGEM_TELA_PX);
    var maxTop = Math.max(MARGEM_TELA_PX, window.innerHeight - altura - MARGEM_TELA_PX);
    return {
      left: Math.min(Math.max(MARGEM_TELA_PX, left), maxLeft),
      top: Math.min(Math.max(MARGEM_TELA_PX, top), maxTop),
    };
  }

  function aplicarPosicao(mascote, left, top) {
    mascote.style.left = left + "px";
    mascote.style.top = top + "px";
    mascote.style.right = "auto";
    mascote.style.bottom = "auto";
  }

  /* Arrastar por Pointer Events (mouse, touch e caneta no mesmo caminho) +
     teclado (setas movem, duplo-clique volta ao canto). Clique simples —
     sem arrasto — leva à escolha de avatar. */
  function iniciarMascote() {
    var mascote = $("[data-mascote]");
    if (!mascote) return;

    var salva = lerPosicaoSalva();
    if (salva) {
      var ret = mascote.getBoundingClientRect();
      var presa = prenderNaTela(salva.left, salva.top, ret.width || 60, ret.height || 60);
      aplicarPosicao(mascote, presa.left, presa.top);
    }

    var destinoId = mascote.getAttribute("data-mascote-destino");
    function irAoDestino() {
      if (!destinoId) return;
      var destino = document.getElementById(destinoId);
      if (!destino) return;
      var reduzMovimento =
        window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      destino.scrollIntoView({
        behavior: reduzMovimento ? "auto" : "smooth",
        block: "center",
      });
      if (destino.focus) destino.focus({ preventScroll: true });
    }

    var arrastando = false;
    var moveu = false;
    var inicioX = 0;
    var inicioY = 0;
    var baseLeft = 0;
    var baseTop = 0;

    mascote.addEventListener("pointerdown", function (evento) {
      if (evento.button !== undefined && evento.button !== 0) return;
      arrastando = true;
      moveu = false;
      inicioX = evento.clientX;
      inicioY = evento.clientY;
      var ret = mascote.getBoundingClientRect();
      baseLeft = ret.left;
      baseTop = ret.top;
      try {
        mascote.setPointerCapture(evento.pointerId);
      } catch (e) {
        /* Sem captura: o arrasto segue até o pointerup mesmo assim. */
      }
      evento.preventDefault();
    });

    mascote.addEventListener("pointermove", function (evento) {
      if (!arrastando) return;
      var dx = evento.clientX - inicioX;
      var dy = evento.clientY - inicioY;
      if (!moveu && Math.hypot(dx, dy) < LIMIAR_ARRASTO_PX) return;
      moveu = true;
      mascote.setAttribute("data-arrastando", "1");
      var ret = mascote.getBoundingClientRect();
      var presa = prenderNaTela(baseLeft + dx, baseTop + dy, ret.width, ret.height);
      aplicarPosicao(mascote, presa.left, presa.top);
    });

    function terminarArrasto(evento) {
      if (!arrastando) return;
      arrastando = false;
      mascote.removeAttribute("data-arrastando");
      if (!moveu) {
        irAoDestino();
        return;
      }
      var ret = mascote.getBoundingClientRect();
      salvarPosicao(ret.left, ret.top);
      if (evento && evento.cancelable) evento.preventDefault();
    }

    mascote.addEventListener("pointerup", terminarArrasto);
    mascote.addEventListener("pointercancel", function () {
      arrastando = false;
      mascote.removeAttribute("data-arrastando");
    });
    // O clique sintético após arrasto não pode disparar a navegação.
    mascote.addEventListener(
      "click",
      function (evento) {
        if (moveu) {
          evento.stopPropagation();
          evento.preventDefault();
          moveu = false;
        }
      },
      true
    );
    mascote.addEventListener("dblclick", function () {
      mascote.style.left = "";
      mascote.style.top = "";
      mascote.style.right = "";
      mascote.style.bottom = "";
      esquecerPosicao();
    });
    mascote.addEventListener("keydown", function (evento) {
      var dx = 0;
      var dy = 0;
      if (evento.key === "ArrowLeft") dx = -PASSO_TECLADO_PX;
      else if (evento.key === "ArrowRight") dx = PASSO_TECLADO_PX;
      else if (evento.key === "ArrowUp") dy = -PASSO_TECLADO_PX;
      else if (evento.key === "ArrowDown") dy = PASSO_TECLADO_PX;
      else return;
      evento.preventDefault();
      var ret = mascote.getBoundingClientRect();
      var presa = prenderNaTela(ret.left + dx, ret.top + dy, ret.width, ret.height);
      aplicarPosicao(mascote, presa.left, presa.top);
      salvarPosicao(presa.left, presa.top);
    });
    window.addEventListener("resize", function () {
      var ret = mascote.getBoundingClientRect();
      var presa = prenderNaTela(ret.left, ret.top, ret.width, ret.height);
      if (presa.left !== ret.left || presa.top !== ret.top) {
        aplicarPosicao(mascote, presa.left, presa.top);
        salvarPosicao(presa.left, presa.top);
      }
    });
  }

  iniciarPrevia();
  iniciarEspelhoAvatar();
  iniciarMascote();
})();
