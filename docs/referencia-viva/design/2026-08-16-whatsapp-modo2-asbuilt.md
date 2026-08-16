# Modo 2 (central Cloud API) — as-built em 2026-08-16

Spec: [`../specs/2026-08-12-whatsapp-dois-modos-design.md`](../specs/2026-08-12-whatsapp-dois-modos-design.md).
Este arquivo diz **o que existe no `main`**, não o que foi planejado. Onde houver
divergência com a spec, a spec é o alvo e este documento é o placar.

## O buraco que este dia fechou

O Modo 2 foi construído em 13–14/08 e mergeado em 16/08 com a **metade da
distribuição** pronta (rodízio, oferta, trava, handoff, follow-up) e **sem a
metade do atendimento**. Na prática, com a flag ligada e uma loja em Modo 2:

- o cliente escrevia para a central,
- a mensagem era gravada no banco,
- **ninguém respondia**, e
- **nenhum vendedor era chamado, nunca.**

Causa: o `n8n-cloud` era um transporte de **4 nós** (recebe da Meta, repassa,
fim). A §5.9 pede *"cópia do fluxo atual (`workflow-ai-nao-salvos.json`) trocando
Evolution por Graph API — não um bot novo"*. Não havia IA em lugar nenhum: o
`chatbot-api` não tem Gemini/OpenAI/LangChain, e a ferramenta `solicitar_handoff`
— o elo que abre o rodízio — só existia no workflow do Modo 1, apontando para a
Evolution.

O validador do workflow **aprovava** esse estado: ele cravava o formato de 4 nós.
Um validador que sanciona o stub é pior que nenhum, porque dá aval.

## Placar por seção da spec

| Spec | Peça | Estado |
|---|---|---|
| §5.1 | Bot atende o cliente na central | ✅ agente no `n8n-cloud` (fork de 20 nós) |
| §5.2 | Gatilho *simulação pronta* | ✅ via `solicitacoes-simulacao-humana` |
| §5.2 | Gatilho *simulação falhou* | ✅ mesmo caminho, `motivo=simulacao_falhou` |
| §5.2 | Gatilho *cliente pede humano* | ✅ `POST /v1/operacao/handoff-humano` |
| §5.3 | Rodízio, ponteiro, 10 min, uma volta | ✅ `rodizio.py` + worker |
| §5.4 | Silêncio pós-handoff, re-notificação | ✅ `pos_handoff.py` |
| §5.5 | Vendedor × cliente por variantes | ✅ |
| §5.7 | "Peguei" = clique, primeiro vence | ✅ trava idempotente |
| §5.8 | Control escolhe o modo | ✅ `whatsapp_modo` por loja |
| §5.9 | Fork do fluxo atual | ✅ gerado, 20 nós |
| §5.9 | Debounce 40 s | ✅ herdado |
| §5.9 | Follow-up 30 min + 1 h | ✅ prazos e regras |
| §5.9 | Classificação das 6 etapas | ⚠️ **só `so_oi`** |
| §5.9 | Recusa não cutuca | ❌ **não existe** |
| §5.10 | Mídia pelo Graph, `language: pt` | ✅ |
| §5.10 | Transcrição só no Modo 2 | ✅ |
| §5.10 | VAD / baixa confiança → fallback | ❌ **não existe** |
| §5.11 | Simulação que falha | ✅ |
| §6.1 | 200 imediato + dedup por `wamid` | ✅ |
| §6.1 | "Processar depois" (retry) | ✅ `cloud_evento_falho` + worker |
| §6.2 | Segredo da Meta só no chatbot | ✅ validador recusa vestígio |

## O fork é gerado, não escrito à mão

`n8n/fork_cloud_workflow.py` monta o `workflow-cloud.json` a partir do
`workflow-ai-nao-salvos.json`. O AI Agent, o Gemini, a memória e as ferramentas
saem **byte-a-byte iguais** — um fork escrito à mão vira outro bot na primeira
divergência, que é o que a §5.9 proíbe. Mudou o Modo 1? Rode de novo e commite.

O gerador **recusa referência órfã** (`$('Nó')` apontando para nó que ficou para
trás). Foi ele que pegou, na primeira execução, o `AI Agent1` citando
`Registrar mensagem e ler handoff1` e o `Gate resposta mais recente1` citando
`Gate somente nao salvos1` — o erro que um fork por recorte comete calado e só
aparece em produção. Resolvido com **dois nós-ponte de mesmo nome**, em vez de
reescrever o agente.

### O que muda do Modo 1 para o Modo 2

| | Modo 1 | Modo 2 |
|---|---|---|
| Entrada | webhook Evolution | dois webhooks Meta (GET verificação, POST `rawBody`) |
| Assinatura | — | conferida no chatbot, sobre o corpo cru |
| Saída | `sendText` Evolution | `POST /v1/operacao/responder` no chatbot |
| `solicitar_handoff` | avisa a equipe pela Evolution | **abre o rodízio** |
| Gate virgem/salvo | isSaved na Evolution | não se aplica (central é só-bot, §5.9) |
| Grupo de estoque | sim | não (grupo é Modo 1) |

Fora do fork **de propósito**: `enviar_foto_veiculo` (manda mídia pela Evolution;
a central precisaria de envio de imagem pelo Graph, que não existe) e
`cadastrar_veiculo` (grupo de estoque). `enviar_link_catalogo` cobre "quero ver
as motos" — o bot manda o **link**, não as fotos.

## O que falta (dívida conhecida, em ordem de risco)

**1. VAD / baixa confiança no áudio (§5.10) — o mais urgente.**
A própria spec chama de *"o risco real, não o WER"*: o Whisper **inventa frase
plausível** em áudio mudo ou só com ruído, e aqui o bot **age** em cima da
transcrição. Um áudio de 2 s de moto passando pode virar uma frase inventada e o
bot responde àquilo. A spec manda: sem voz detectada não vai ao provider;
transcrição vazia ou suspeita cai no fallback "manda por texto". Hoje vai tudo
direto ao provider e o texto volta sem filtro.

**2. Recusa não cutuca (§5.9, regra 5).**
Cliente que responde "valeu", "não precisa" ainda leva os dois toques do
follow-up. Não há nada no `chatbot-api` sobre recusa.

**3. Classificação das etapas do follow-up (§5.9).**
`classificar_etapa` devolve sempre `"so_oi"`. A tabela das 6 etapas existe com os
textos exatos da spec, mas cinco são código morto: quem parou no anúncio ou no
catálogo recebe *"e aí amigo, ainda tá aí?"*. Depende do estado do intake, que
ainda não existe — está isolado numa função só para o intake plugar depois.

**4. Foto de moto no Modo 2.**
Precisa de envio de imagem pelo Graph + rota no chatbot.

## Onde mexer

| O quê | Arquivo |
|---|---|
| Gerar o workflow | `n8n/fork_cloud_workflow.py` |
| Invariantes do workflow | `n8n/validate_workflow_cloud.py` |
| Gate único do Modo 2 | `chatbot-api/app/rodizio.py::loja_opera_modo2` |
| Gatilhos do handoff | `chatbot-api/app/handoff_gatilhos.py` |
| Follow-up (prazos e textos) | `chatbot-api/app/followup_job.py` |
| Áudio (download, transcrição) | `chatbot-api/app/audio.py` |
| Retry do inbound | `chatbot-api/app/cloud_retry.py` |
| Workers do Modo 2 | `chatbot-api/app/modo2_workers.py` |

**Nunca edite `n8n/workflow-cloud.json` à mão** — o validador compara com o que o
gerador produz e sai com código 1. Ajuste o gerador e rode.

## Estado operacional

Flag `CHATBOT_WHATSAPP_MODO2_ENABLED=1` no `app2037` desde 16/08. O gate é
fail-closed em três condições (§6.3): flag, loja operacional e projeção
`whatsapp_modo == "2"` vinda do Control. **Nenhuma loja tem essa projeção**, então
os workers sobem e não tocam em nada. O piloto ainda precisa das credenciais da
Meta (`META_APP_SECRET`, verify token, `GRAPH_TOKEN`, `phone_number_id`) e da
reimportação do workflow no n8n.

Import do workflow: ver a armadilha em
[`../../../deploy/fly/3vm/README.md`](../../../deploy/fly/3vm/README.md) —
`import:workflow` **desativa** o workflow e `publish:workflow` não reativa; só
`update:workflow --active=true` liga.
