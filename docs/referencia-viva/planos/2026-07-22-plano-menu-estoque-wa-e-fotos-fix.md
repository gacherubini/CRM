# Plano — Menu de estoque WA + fixes de foto/cadastro (sessão 2026-07-21/22)

> **Status:** IMPLEMENTADO na `main` (código + hotpatch prod).  
> **Próximo eixo:** **E2E humano** — (1) testar menu/cadastro de ponta a ponta; (2) depois chatbot com clientes novos.  
> **Commits relevantes:** `aca96c9`, `983f140`, `6892917` (+ base 3-VM / roteamento).  
> **Apps:** `app2037` (chatbot no bundle), `n8n2037`, `evolution2037`, `suite-pg`.

## Goal

Operação de estoque pelo WhatsApp da equipe (menu) + cadastro/fotos estáveis em produção Fly 3-VM, sem misturar com o fluxo de vendas (IA só contato novo).

## O que foi feito (checklist)

### Produto / API

- [x] Menu de estoque no WA para número **autorizado**: gatilho `cadastro` / `menu` / `estoque`
  - 1 Cadastrar · 2 Ver · 3 Editar · 4 Despublicar · 5 Vendido · 0 Sair
- [x] State machine `operacao_modo` + `operacao_ctx` em `numeros_autorizados` (migration **0009**)
- [x] Opções 2–5 determinísticas (sem LLM); opção 1 → modo cadastrar → LLM só extrai campos e chama tool
- [x] Cadastro via `POST /v1/operacao/veiculos` + 409 placa → reabre sessão de fotos
- [x] Fotos: `POST /webhook/operacao/veiculos/foto` → Evolution `getBase64` → Estoque upload → catálogo
- [x] Sessão de fotos ~10 min (placa na legenda na 1ª; depois pode omitir)
- [x] Gate n8n: `bot_ativo=false` **não** bloqueia menu/cadastro da equipe; só bloqueia IA de cliente
- [x] Handoff de serviço não derruba staff; reativa bot se staff no menu

### Bugs corrigidos nesta rodada

| Sintoma | Causa | Fix |
|---|---|---|
| Foto “não vai” / `tamanho de imagem inválido` | Evolution devolve `size.fileLength` como Long `{low,high,unsigned}`; `int()` falhava | `parse_tamanho_declarado` em foto/áudio |
| Foto zero / ConnectError | `CHATBOT_IMAGE_EVOLUTION_URL` em flycast; app bundle não resolvia bem | URL **HTTPS** pública `https://evolution2037.fly.dev` + apikey |
| `1` duas vezes no menu (1ª ia pro LLM genérico) | Mesmo celular em **3 linhas** (`51…`, `5551…` sem 9, `55519…`); modo divergia | Sync de sessão em todas variantes + merge de duplicados; “1” de novo reexplica modo |
| Mensagem fraca pós-cadastro | Não pedia legenda | Textos: foto **com placa na legenda**; prompt n8n alinhado |

### Ops / deploy

- [x] Secrets imagem/áudio Evolution no `app2037`
- [x] Workflow n8n atualizado (gate controle + prompt cadastro + foto)
- [x] Hotpatch prod + restart `chatbot` / n8n quando necessário
- [x] Código na **main** (sem secrets em git)

## Problemas conhecidos / riscos (não reabrir sem evidência)

1. **E2E menu/cadastro ainda não fechado de ponta a ponta pelo dono** após os últimos fixes (menu 1× + foto com legenda + listar/editar/despublicar/vender).
2. **E2E cliente novo** (IA vendas, estoque, simulação, handoff) **não validado** nesta rodada.
3. **Hotpatch vs imagem Docker:** parte do código foi aplicada via sftp no `/srv/chatbot`; um `fly deploy` limpo da imagem 3-VM deve reaplicar a partir da `main` para não perder hotpatch.
4. **Telefone autorizado:** cadastrar **uma** forma canônica (preferir `55` + DDD + 9 dígitos). O código sincroniza variantes, mas duplicar no Portal ainda polui.
5. **Áudio:** sem URL/token de transcritor HTTP homologado → fallback pede texto.
6. **Restore drill** volume/banco Estoque ainda pendente (não bloqueia demo).
7. **n8n logs “User attempted to access workflow without permissions”** se abrir editor com user sem role — irrelevante ao runtime webhook.
8. **Não reintroduzir flycast** para download de mídia no chatbot do bundle 3-VM sem testar DNS interno de novo.

## Próximos steps (ordem)

### Step A — Testar de fato o menu / cadastro (eixo loja / equipe)

Número autorizado, WhatsApp da loja (`loja1`):

1. `menu` → aparece menu completo.
2. `1` **uma vez** → “Modo cadastrar” + aviso de **foto com placa na legenda**.
3. Uma linha: `Honda CG 160 2018 21900 18mil km ABC1X23` → confirma cadastro + pede foto com legenda.
4. Envia **foto** com legenda `ABC1X23` → “Foto adicionada…”.
5. Segunda foto sem legenda (dentro de 10 min) → também grava.
6. `2` listar; `3` editar preço/km; `4` despublicar (confirma SIM); `5` vender; `0` sair.
7. Conferir no catálogo público / admin estoque que publicado/foto batem.

Se falhar: logs `fly logs -a app2037` (linhas `foto de veículo`, `roteamento`) + n8n execuções.

### Step B — Depois: chatbot com clientes (eixo demo vendas)

Contato **não salvo** (`isSaved === false`), bot ativo:

1. Mensagem de interesse → IA responde (Gemini).
2. Consulta estoque / placa.
3. Fluxo simulação (coleta + handoff; **não** vazar parcelas no chat).
4. Contato **salvo** não autorizado → bot **ignora** (não atende).
5. Número autorizado fora do menu → ignora texto normal; só `menu`/`cadastro` abre operação.

### Step C — Hardening residual (quando A+B ok)

- [ ] Deploy imagem limpa 3-VM a partir da `main` (eliminar dependência de hotpatch).
- [ ] Homologar transcritor de áudio.
- [ ] Restore drill volume mídia + Postgres.
- [ ] Um número autorizado canônico por pessoa no Portal.

## Arquivos-chave

| Área | Path |
|---|---|
| Menu / roteamento | `chatbot-api/app/operacao.py` |
| Foto Evolution | `chatbot-api/app/vehicle_photo.py` |
| Áudio (mesmo size Long) | `chatbot-api/app/audio.py` |
| Workflow | `n8n/workflow-ai-nao-salvos.json` |
| Ops 3-VM | `deploy/fly/3vm/` |
| Go-live | `docs/referencia-viva/go-live-chatbot.md` |

## Fora de escopo desta sessão

- Drivers bancários / Playwright.
- Google Conversions (eixo G).
- Redesign Portal.
- Reescrever stack 3-VM (já operando).
