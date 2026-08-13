# README de handoff — Atribuição CTWA → campanha

Documento de entrega para o **agente de código** que vai implementar, e com os **tutoriais do
dono** (passos que não são código). Design completo em
[`2026-08-04-atribuicao-ctwa-campanha-design.md`](2026-08-04-atribuicao-ctwa-campanha-design.md).

## Regra de ouro: ordem

> **Fase 1 inteira e verde primeiro. Só depois a Fase 2.**

A Fase 1 já faz a atribuição funcionar (com cadastro manual de `ad_id`). A Fase 2 automatiza e
é opcional para a atribuição existir. Não iniciar Fase 2 com Fase 1 incompleta.

---

## Status atual (2026-08-04)

**Fase 1 — IMPLEMENTADA, testada e commitada.** Fase 2 — não iniciada (aguarda token Meta).

Branch: `feat/atribuicao-ctwa-campanha`. Commits da Fase 1 (após o commit dos docs `960ff56`):

| Commit | O que entrou |
|---|---|
| `62dbbf7` | Revy: tabela `campanha_anuncios` + migration `0014` (Task 1) |
| `c71da62` | Revy: match do lead por `ad_id` no casador (Task 2) |
| `cda9f68` | Revy: UI + sync pra cadastrar ad_ids na campanha (Task 3) |
| `4267008` | Chatbot: cria o lead na **2ª mensagem** de conversa CTWA (Task 4) |

Verificação (rodada manualmente, não só pelos agentes):
- Chatbot: `272 passed`.
- Revy: 6 testes novos verdes; suite completa `440 passed, 1 failed`.
- Alembic: head único `0014_campanha_anuncios`, `upgrade head` limpo.

⚠️ **A 1 falha é pré-existente, não é desta mudança.** É
`tests/test_control_provisioning_outbox.py::test_process_pending_falha_marca_failed_e_incrementa_attempts`
(`MultipleResultsFound`). Comprovado: o mesmo teste falha no `main` sem nenhuma alteração nossa
(provável incompatibilidade com o Python 3.14 do ambiente). Domínio sem relação com atribuição —
fila separada.

**Importante — ainda NÃO está valendo em produção.** O código está na branch, mas não foi
pushado nem deployado. `fly deploy` usa a árvore local commitada (ver memória do projeto), então
enquanto não houver deploy, o `app2037` continua rodando o código antigo. Para ir ao ar:

1. `git push -u origin feat/atribuicao-ctwa-campanha` (e merge quando quiser).
2. Deploy do `app2037` (bundle com Chatbot + Revy) — rodar migration `0014` (`alembic upgrade head`) no deploy.
3. **Cadastrar os `ad_id`** de cada anúncio nas campanhas Cauã/Pedro (Tutorial A + B abaixo).
4. **Lançar o gasto** do período (Tutorial D) para CPL/CPA/ROAS.

Depois disso: lead nasce na 2ª mensagem já com `meta_ad_id`, casa com a campanha pelo ad_id, e o
ROI para de jogar tudo em "Sem campanha". A **Fase 2** (resolução automática via Graph) entra
quando o token `ads_read` existir (Tutorial C + Tasks 5–8 do plano).

---

## Para o agente de código

### Contexto mínimo antes de tocar código
- Ler o design (link acima) e `CLAUDE.md` da raiz (mapa dos produtos e fronteiras).
- **Não** importar `app` de um produto em outro; integração só por HTTP.
- Cada produto tem venv e migrations próprias; rodar testes **de dentro da pasta do produto**.

### Fase 1 — arquivos a mexer
- **Chatbot** (`chatbot-api/`):
  - `app/servico.py` — criar lead na 2ª mensagem (bloco `if not from_me and loja_operacional:`,
    reusando `primeira_mensagem`, `_get_or_create_lead`, `_vincular_tracking_pendente_ao_lead`).
  - `tests/` — casos de 1ª msg, 2ª msg, idempotência, conversa sem CTWA.
- **Revy** (`revy-trafego/`):
  - `app/models.py` — modelo `CampanhaAnuncio` + relationship `Campanha.anuncios`.
  - `alembic/versions/0014_*.py` — cria `campanha_anuncios`.
  - `app/campanhas.py` — regra de match por `ad_id` em `lead_casa_campanha`.
  - `app/main.py` + `app/templates/campanhas/form.html` — textarea de ad_ids + sync.
  - `tests/` — matcher, migration, save do form.

### Fase 2 — arquivos a mexer (só depois)
- `revy-trafego/app/models.py` + `alembic/versions/0015_*.py` — cache `meta_ad_campanha`;
  guardar token `ads_read` cifrado (estender `meta_ads_config`).
- `revy-trafego/app/clients/meta_graph.py` — cliente Graph (novo).
- `revy-trafego/app/meta_ad_resolver_job.py` — worker (novo), gated por
  `REVY_TRAFEGO_AD_RESOLVER_ENABLED` (default OFF).
- `revy-trafego/app/campanhas.py` / `roi_calc.py` — casador usa `mapa_ad_campaign` do cache.
- `tests/` — cliente Graph mockado, worker, matcher via mapa, decifra do token.

### Como testar
```powershell
cd chatbot-api
.\.venv\Scripts\python.exe -m pytest -q

cd ..\revy-trafego
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m alembic upgrade head
```
Fechar com `git diff --check` e `git status --short`. Não commitar segredos/tokens.

### Pré-requisitos que dependem do dono
- Fase 1: os `ad_id` de cada anúncio (tutorial abaixo). Não bloqueia a implementação; bloqueia
  só o resultado no painel.
- Fase 2: um token Meta com `ads_read` (tutorial abaixo). Sem ele, entregar o código com o
  worker OFF e a Fase 1 ativa.

---

## Tutoriais do dono (não é código)

### Tutorial A — achar o `ad_id` de um anúncio (Fase 1)
1. Abra o **Gerenciador de Anúncios** (`adsmanager.facebook.com`).
2. Selecione a conta de anúncios certa (a mesma que rodou as campanhas MT-03).
3. Vá na aba **Anúncios** (o nível mais baixo: Campanhas › Conjuntos › **Anúncios**).
4. Ative a coluna de **ID do anúncio** (Colunas → Personalizar → procurar "ID do anúncio"),
   ou clique no anúncio e veja o **Identificação** nos detalhes.
5. Copie o número (ex.: `120252470707220341`). **É esse número**, não o da campanha nem o do
   conjunto.
6. Anote todos os `ad_id` de cada anúncio, agrupados por campanha (Cauã / Pedro).

### Tutorial B — cadastrar os `ad_id` na campanha do Revy (Fase 1, após a UI existir)
1. Painel Revy → **Campanhas** → abra a campanha (ex.: "MT03 - CAUÃ VENDAS").
2. No campo **"IDs de anúncio (um por linha)"**, cole um `ad_id` por linha (todos os anúncios
   daquela campanha).
3. Salvar. Repetir para cada campanha.
4. Toda vez que criar um **anúncio novo**, volte aqui e adicione o `ad_id` dele (a Fase 2
   elimina esse passo).

### Tutorial C — criar o token `ads_read` (Fase 2)
Caminho curto (você já tem Business Manager por causa do Pixel/CAPI):
1. `business.facebook.com` → **Configurações do Business**.
2. **Usuários** → **Usuários do sistema** → criar um (ou usar existente); tipo pode ser "Admin"
   ou "Funcionário".
3. **Adicionar ativos** → **Contas de anúncios** → selecionar sua conta → dar acesso de
   **leitura** (view performance).
4. **Gerar novo token** → escolher o **app** (o mesmo do CAPI, se houver) → marcar a permissão
   **`ads_read`** → gerar.
5. Copie o token e **guarde com segurança** (ele não reaparece). Cole na tela de config do
   Revy (Fase 2) — o Revy guarda cifrado.
6. Se travar na criação de conta "Meta for Developers", não é obrigatório criar uma nova: use o
   app/negócio que já existe. O erro "não foi possível enviar o email" costuma ser transitório
   (tentar de novo / usar e-mail já confirmado na conta).

### Tutorial D — lançar gasto (operacional, para CPL/CPA/ROAS)
1. Painel Revy → **Campanhas** → **Lançar gastos** (ou o lote).
2. Informe o valor gasto por campanha no período. Sem isso, o painel mostra leads/vendas mas
   deixa CPL/CPA/ROAS vazios e alerta "campanhas ativas sem gasto".

---

## Definição de pronto
- **Fase 1:** testes verdes nos dois produtos; migration `0014` aplica; ao cadastrar um `ad_id`
  numa campanha, um lead com aquele `meta_ad_id` aparece atribuído no ROI (não em "Sem
  campanha"); lead nasce na 2ª mensagem de uma conversa CTWA.
- **Fase 2:** worker OFF por padrão; com token e worker ON, um `ad_id` novo é resolvido para a
  campanha certa e o ROI atribui sem cadastro manual; falha de Graph não derruba o ROI.
