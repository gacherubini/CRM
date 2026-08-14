# Piloto do Modo 2 — fechamento — Implementation Plan

> **For agentic workers:** as Tasks 1–2 são código e seguem o ciclo TDB normal. As Tasks 3–6 são
> **operacionais** e exigem conta na Meta, terminal com Fly CLI e navegador. **Um agente não
> executa as Tasks 3–6** — elas são checklist do dono. Se você é um agente, faça 1–2 e pare.

**Goal:** Tirar o Modo 2 de "código pronto com flag OFF" para "piloto rodando numa loja", fechando
os dois débitos técnicos que sobraram e o que só pode ser feito à mão.

**Architecture:** nada de arquitetura nova. Dois consertos pontuais e um roteiro de configuração.

**Tech Stack:** Alembic/SQLite (Task 1), pytest (Task 2), Meta Business Suite e Graph API
(Tasks 3–4), n8n (Task 5), Groq (Task 6).

**Spec:** [`../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md`](../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md) — §8 (onboarding), §10 (smoke), §5.10 (transcrição).

## Estado ao abrir este card

Todo o código da Fase 1 está escrito e verde, com **todas as flags OFF**:
`CHATBOT_WHATSAPP_MODO2_ENABLED` e `REVY_CONTROL_WHATSAPP_MODO2_ENABLED`. Os sete planos
executados estão em [`../referencia-viva/planos/`](../referencia-viva/planos/).

Suítes na abertura: `chatbot-api` **420 passed**; `revy-trafego` **509 passed, 1 failed** (o
failed é a Task 2 aqui).

## Global Constraints

- **Nenhuma flag é ligada antes da Task 5** — não adianta ligar sem a central existir.
- **Ligar é por loja**, nunca global: `whatsapp_modo = 2` na ficha do Control, uma loja só.
- Nenhum segredo, token ou `.env` real no git ou no log. O token do System User vai para variável
  de ambiente/credencial, nunca para o JSON do workflow.
- Rodar testes a partir da pasta do produto: macOS `.venv/bin/python -m pytest -q`;
  Windows `.\.venv\Scripts\python.exe -m pytest -q`.

---

### Task 1: `alembic upgrade head` volta a rodar no SQLite do chatbot

**Files:**
- Modify: `chatbot-api/alembic/versions/0017_canal_id_conversas_msg.py`
- Test: `chatbot-api/tests/test_migrations_chain.py` (criar)

**Interfaces:**
- Produces: a chain completa aplicando de zero num SQLite limpo.

**O problema:** a `0017` usa `op.create_foreign_key` fora de `batch_alter_table`, e o SQLite não
suporta `ALTER` de constraint. Em Postgres funciona — por isso produção nunca reclamou. No
SQLite local a chain morre na `0017`, e **toda migration posterior nunca foi executada** de fato:
as 0020–0022 foram validadas à mão, uma a uma, em banco descartável.

**O cuidado:** a `0017` já foi aplicada em produção. Mudar o **corpo** dela não reexecuta nada
onde ela já rodou (o Alembic só olha a revisão registrada), mas mudar o `revision` ou o
`down_revision` quebraria a linha. **Não toque nos identificadores.**

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_migrations_chain.py
"""A chain tem que aplicar de zero. Sem isso, migration nova nunca é executada
de verdade — os testes montam o schema com create_all e não tocam no Alembic."""
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def test_chain_aplica_do_zero_em_sqlite(tmp_path):
    banco = tmp_path / "chain.db"
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=RAIZ,
        env={"PATH": "/usr/bin:/bin", "DATABASE_URL": f"sqlite:///{banco}"},
        capture_output=True,
        text=True,
    )
    assert resultado.returncode == 0, resultado.stderr[-2000:]
    assert banco.exists()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_migrations_chain.py -q`
Esperado: FAIL com `NotImplementedError: No support for ALTER of constraints in SQLite dialect`.

- [ ] **Step 3: Envolver as duas FKs em `batch_alter_table`**

Na `0017`, trocar cada `op.create_foreign_key(...)` solto pelo equivalente em modo batch:

```python
    with op.batch_alter_table("conversas") as batch:
        batch.create_foreign_key(
            "fk_conversas_canal_id", "whatsapp_canais", ["canal_id"], ["id"]
        )
```

Repetir para `mensagens`. **Manter os nomes das constraints exatamente como estão** — em Postgres
elas já existem com esse nome, e renomear criaria divergência entre ambientes. `revision` e
`down_revision` **não mudam**.

- [ ] **Step 4: Rodar e ver passar**

Run: `cd chatbot-api && .venv/bin/python -m pytest -q`
Esperado: suíte inteira verde, incluindo o teste novo.

- [ ] **Step 5: Conferir que Postgres não regrediu**

O modo batch em SQLite faz copy-and-move; em Postgres o Alembic emite `ALTER TABLE` normal. Se
houver um Postgres à mão, rode a chain nele também. Se não houver, **diga isso no relatório** — a
migration já está aplicada em produção, então o risco real é baixo, mas não é zero.

- [ ] **Step 6: Commit**

```bash
git add chatbot-api/alembic/versions/0017_canal_id_conversas_msg.py chatbot-api/tests/test_migrations_chain.py
git commit -m "fix(chatbot): 0017 usa batch_alter_table e a chain volta a rodar no SQLite"
```

---

### Task 2: O teste de outbox que enfileira `motor` duas vezes

**Files:**
- Modify: `revy-trafego/tests/test_control_provisioning_outbox.py`
- Possivelmente: `revy-trafego/app/control/provisioning_hooks.py`

**O problema:** `test_process_pending_falha_marca_failed_e_incrementa_attempts` faz `.one()` sobre
os itens de destino `motor` e encontra **dois**. Os hooks enfileiram `motor` no `create` e de novo
no `configure`, porque `DEFAULT_PROVISIONING_TARGETS` inclui `motor` nas duas etapas.

Falha **desde antes** do trabalho do Modo 2 — verificado rodando o mesmo teste num worktree do
commit anterior.

**A pergunta que decide a correção, e que você precisa responder antes de escrever código:**
enfileirar `motor` duas vezes é **bug** ou **comportamento correto**?

- Se for correto (o outbox é idempotente por `event_id` e a segunda entrada é benigna), o teste é
  que está errado: troque `.one()` por `.first()` ou filtre pela etapa, e explique no docstring.
- Se for bug (o `configure` não devia reenfileirar o que o `create` já mandou), o conserto é no
  hook, e o teste está certo. Nesse caso confira se algum outro teste depende da duplicata.

**Não escolha pelo que dá menos trabalho.** Leia `provisioning_hooks.py` e o `event_id` do
envelope antes de decidir, e registre a decisão no commit.

- [ ] **Step 1: Ler `provisioning_hooks.py` e `provisioning_outbox.py` e decidir**
- [ ] **Step 2: Aplicar a correção escolhida (teste OU hook, não os dois)**
- [ ] **Step 3:** `cd revy-trafego && .venv/bin/python -m pytest -q` → **510 passed, 0 failed**
- [ ] **Step 4: Commit**, com a mensagem explicando qual das duas leituras você adotou e por quê.

---

> Daqui para baixo é **checklist do dono**. Nenhum agente executa.

### Task 3: A conta do Revy na Meta

Nada aqui depende de terceiros. **Criar não é verificar**: criar o portfólio é grátis, leva
minutos e só precisa de uma conta pessoal do Facebook. A verificação (CNPJ, site com razão social
e telefone batendo, domínio) só é necessária para tirar loja do dev mode e para virar Tech
Provider — não bloqueia o piloto.

**Não use a conta da loja cliente.** Funciona para uma loja e cobra caro depois: o app, o token e
o App Review passariam a morar num ativo que não é seu, e na segunda loja o modelo quebra.

- [ ] **Step 1:** Criar o **Business Portfolio do Revy** em `business.facebook.com`. Anotar o
      `Business ID` — é o número que o lojista vai precisar.
- [ ] **Step 2:** Criar o **app do Revy** em `developers.facebook.com`, com o produto WhatsApp
      habilitado. Anotar `App ID` e **App Secret**.
- [ ] **Step 3:** Criar um **System User** no Business Suite, dar permissão de WhatsApp e gerar o
      **token permanente**. ⚠️ O token que aparece na tela do app vale **24 h** — se plugar ele, o
      piloto funciona hoje e morre amanhã de manhã sem erro óbvio.
- [ ] **Step 4:** Pegar o **número de teste** do dev mode e cadastrar os destinatários. São
      **5 no total**: reserve 1 para o cliente de teste e até 3 para vendedores.
- [ ] **Step 5:** Guardar em variável de ambiente do `chatbot-api`, nunca no git:
      `CHATBOT_GRAPH_TOKEN`, `CHATBOT_META_APP_SECRET`, `CHATBOT_META_VERIFY_TOKEN` (string que
      você inventa), `CHATBOT_GRAPH_PHONE_NUMBER_ID`.

### Task 4: O template com botão

O template vive **na WABA**, não no app — então cada loja nova tende a precisar do seu. Confirme
isso no piloto antes de prometer prazo de ativação a cliente.

- [ ] **Step 1:** Submeter um template **Utility** com **botão de resposta rápida**, com as
      variáveis do §5.7 (nome do vendedor; veículo e resultado da simulação quando houver).
      **Sem `wa.me` no corpo** — o contato só vai depois do clique.
- [ ] **Step 2:** Esperar aprovação e anotar o nome em `CHATBOT_GRAPH_TEMPLATE_OFERTA`.
- [ ] **Step 3:** Se reprovar, ler o motivo antes de reescrever: conteúdo transacional costuma
      passar; o risco é ser reclassificado como Marketing, que custa ~10x mais (§9).

### Task 5: Publicar e ativar o `n8n-cloud`

Estes são os dois steps que ficaram abertos no card 3.

- [ ] **Step 1:** Apontar o webhook do app da Meta para a URL do `n8n-cloud` e completar a
      verificação (`hub.challenge`). Se falhar, o `hub.verify_token` do app e o
      `CHATBOT_META_VERIFY_TOKEN` estão diferentes.
- [ ] **Step 2:** Publicar o workflow por `n8n/update_live_workflow.js`, como o `n8n-baileys`.
- [ ] **Step 3:** **Ativar pelo botão "Publish" na UI.** `active=1` no banco **não** registra o
      webhook — o workflow aparece ativo e a URL responde 404.
- [ ] **Step 4: O teste que decide tudo.** Mandar um POST assinado à mão:

```bash
CORPO='{"object":"whatsapp_business_account","entry":[]}'
SEG='<o mesmo CHATBOT_META_APP_SECRET>'
ASSIN="sha256=$(printf '%s' "$CORPO" | openssl dgst -sha256 -hmac "$SEG" | sed 's/^.* //')"
curl -i -X POST "https://<host-n8n>/webhook/whatsapp-cloud" \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: $ASSIN" \
  --data "$CORPO"
```

Esperado `200`. Se vier **401**, o corpo chegou alterado ao chatbot: o problema está no `rawBody`
do nó Webhook ou no `contentType: raw` do HTTP Request, e **em nenhum outro lugar**. Não saia
procurando no HMAC.

### Task 6: Provider de transcrição

- [ ] **Step 1:** Criar conta na Groq e gerar chave.
- [ ] **Step 2:** `CHATBOT_AUDIO_TRANSCRIPTION_URL=https://api.groq.com/openai/v1/audio/transcriptions`
      e `CHATBOT_AUDIO_TRANSCRIPTION_TOKEN=<chave>`. O modelo é `whisper-large-v3` (não o `turbo`:
      a diferença de custo é ruído e o turbo perde acurácia em pt).
- [ ] **Step 3:** Mandar um áudio real e conferir a transcrição. Depois **desligar o provider** e
      confirmar que o cliente recebe o fallback pedindo texto — nunca ficar mudo.
- [ ] **Step 4:** Juntar ~30 áudios reais de cliente (rua, ruído, sotaque), com 2–3 **mudos ou só
      ruído**, e conferir se alucina. Se o pt-BR decepcionar, trocar é mudar duas variáveis de
      ambiente — o plano B é AssemblyAI, que exige adaptador.

### Task 7: Ligar o piloto, numa loja só

- [ ] **Step 1:** `REVY_CONTROL_WHATSAPP_MODO2_ENABLED=1` no Control.
- [ ] **Step 2:** `CHATBOT_WHATSAPP_MODO2_ENABLED=1` no chatbot.
- [ ] **Step 3:** Na ficha da **loja piloto** no Control, escolher **central Cloud (modo 2)**.
      Conferir que a versão da loja subiu — sem o bump, a projeção monotônica descarta o evento e
      o chatbot fica no modo 1 **sem erro nenhum aparecer**.
- [ ] **Step 4:** No Portal da loja, cadastrar a **fila de vendedores** (nome + número + ordem).
      Sem fila, todo lead cai direto em `aguardando`.
- [ ] **Step 5:** Rodar o smoke do §10 ponta a ponta: cliente → bot → simulação → rodízio →
      clique trava → handoff.
- [ ] **Step 6:** Conferir que as **outras lojas continuam no Modo 1** — nenhuma delas tem
      `whatsapp_modo = 2` projetado, então o gate as bloqueia. É o teste real do gate de três
      cláusulas.

---

## O que este card não cobre

- **Fase 2** (Tech Provider, embedded signup **v4** — o v2 sai do ar em 15/10/2026, billing por
  loja): spec §11, não é piloto.
- **Toda a metade do dono da loja** (§5.8 e §2): faixa "N sem vendedor", filtro Aguardando, card
  de 7 dias no Agente, e o **sino 1:1 com botão Peguei**. Nada disso existe, e o buraco é maior do
  que "falta UI":
  - o `chatbot-api` **não expõe rota nenhuma de oferta** — `oferta_lead` vive no banco dele e
    nunca sai, então o Portal não tem como saber quem é `oferecido_a` nem o que está `aguardando`;
  - `criar_sinal_direcionado` e `transferir_sinal` (plano `wa-modo2-1`) **não têm chamador**: a
    capacidade de endereçar o sino existe e ninguém a usa. O sino não toca para o vendedor.
  - **Consequência que não é cosmética:** o dono escolheu a faixa na Loja **no lugar** do resumo
    por WhatsApp às 19h. Sem a faixa, o fallback que ele escolheu não existe em forma nenhuma —
    lead que ninguém pega **some**, e ninguém é avisado.

  O piloto roda assim (o caminho do WhatsApp é completo), mas rodar sem isso significa aceitar que
  lead perdido é invisível. Card próprio, atravessando os dois produtos.
- **Pacote pós-clique completo** e **VAD antes da transcrição**: declarados como pendentes dentro
  dos planos executados.
