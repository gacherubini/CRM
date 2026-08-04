# Atribuição CTWA → campanha (lead nasce cedo + match por ad_id, depois Graph API)

Data: 2026-08-04
Status: design aprovado (dono), pronto para plano de implementação.
Handoff: o implementador é um **agente de código** (Claude Code). Ver
`docs/superpowers/specs/2026-08-04-atribuicao-ctwa-campanha-README.md` para tutoriais
do dono e ordem de execução.

## Ordem obrigatória

**Fase 1 primeiro, Fase 2 depois.** A Fase 1 entrega valor sozinha (atribuição
funcionando com cadastro manual de `ad_id`). A Fase 2 é montada por cima e é opcional
para a atribuição já funcionar. Nunca começar a Fase 2 antes da Fase 1 estar verde.

## Problema (diagnóstico do dia 1, 03/08/2026)

Dados lidos direto de produção (`suite-pg` = leads do Chatbot; SQLite do Revy = campanhas):

- O topo do funil funciona: cliques Click-to-WhatsApp (CTWA) chegam e o Pixel/CAPI estão
  configurados. Em 03/08: 31 conversas, 400 mensagens, 9 eventos `ctwa_auditoria` com `ad_id`.
- **0 leads criados no dia de teste.** Lead mais novo do banco = 27/07. O lead só nasce
  quando algo chama `POST /v1/leads` (n8n, no ponto de "simulação"); como o bot ainda não
  devolve simulação, o gatilho não disparou.
- **`meta_campaign_id` sempre nulo** nos leads (0 de 23). A referral do WhatsApp entrega só
  `meta_ad_id` (id do anúncio), nunca o id da campanha. O casador
  (`revy-trafego/app/campanhas.py:lead_casa_campanha`) casa por `utm_campaign`,
  `meta_campaign_id` ou `codigo_ctwa` — nunca por `ad_id`. Resultado: todo lead cai em
  "Sem campanha".
- `codigo_ctwa` das 2 campanhas está preenchido com a frase-convite inteira e idêntica →
  inútil e ambíguo. Descartado (não vamos depender de código na mensagem).

## Decisões (dono)

1. **Lead nasce na 2ª mensagem real do cliente** (não só na simulação). Escopo: conversas
   com sinal CTWA (originadas de anúncio). Conversas sem CTWA mantêm o comportamento atual.
2. **Casar lead ↔ campanha por `ad_id`** (Fase 1), cadastrado **anúncio por anúncio** numa
   **tabela filha** no Revy.
3. **Resolver `ad_id → campaign_id` via Graph API** (Fase 2), com token `ads_read`, para
   parar de cadastrar `ad_id` na mão.

## Fronteiras respeitadas

- Chatbot é dono de leads/conversas/mensagens/tracking CTWA (Postgres).
- Revy Tráfego é dono de campanhas, gastos, config Pixel/CAPI/Ads e do cálculo de ROI
  (SQLite no bundle). Puxa leads do Chatbot por HTTP (`GET /v1/leads`).
- Sem import Python entre produtos; integração só por contrato HTTP.
- Credenciais Meta (tokens) só no Revy, cifradas (`app/cripto.py`).

---

## FASE 1 — Lead cedo + match por ad_id (sem Meta API)

### 1A. Chatbot: criar o lead na 2ª mensagem do cliente

**Onde:** `chatbot-api/app/servico.py`, na função que persiste a mensagem e trata CTWA
(bloco `if not from_me and loja_operacional:` ~linha 778, logo após o tratamento de
touch/pendência CTWA das linhas 794-819).

**Sinais que já existem e serão reusados:**
- `primeira_mensagem` (linha 737-745): `True` se a mensagem atual é a 1ª entrada da conversa
  (calculado ANTES de gravar a msg atual). Logo, **entrada com `primeira_mensagem == False`
  = 2ª mensagem (ou mais) do cliente** = "respondeu de verdade".
- `_get_or_create_lead(db, loja_id, telefone)` (1585) — idempotente por telefone.
- `_vincular_tracking_pendente_ao_lead(db, loja_id, telefone, lead)` (1626) — move o tracking
  CTWA pendente da conversa para o lead.
- `registrar_lead(...)` (1651) — já faz get-or-create + vincula pendência.

**Regra nova (idempotente):** quando `not from_me` e `loja_operacional` e
`not primeira_mensagem` e a conversa tem sinal CTWA (tracking pendente **ou** um lead já
com origem de anúncio) e ainda **não existe lead** para o telefone → criar o lead
(etapa `"novo"`, origem `meta_ctwa`) reusando o caminho de `registrar_lead` /
`_vincular_tracking_pendente_ao_lead`. Não duplicar se o lead já existir. Um `POST /v1/leads`
posterior (n8n) deve continuar sendo upsert (já é, via `_get_or_create_lead`), sem duplicar.

**Escopo (decisão explícita):** só dispara para conversas com sinal CTWA. Evita encher o CRM
com conversas não originadas de anúncio. Se o dono quiser depois estender para toda conversa,
é troca de uma condição — deixar comentado no código.

**Observabilidade:** incluir um flag no retorno (ex.: `lead_criado_auto: true`) para o n8n/log.

**Testes (`chatbot-api/tests/`):**
- 1ª entrada CTWA → nenhum lead criado (comportamento atual preservado).
- 2ª entrada CTWA → lead criado, `origem=meta_ctwa`, `meta_ad_id` preenchido a partir da
  pendência.
- Idempotência: 3ª entrada e/ou `POST /v1/leads` depois → não cria lead duplicado.
- Conversa **sem** CTWA, 2ª entrada → nenhum lead automático (inalterado).

### 1B. Revy: casar por ad_id (tabela filha)

**Modelo/tabela** (`revy-trafego/app/models.py`): nova `CampanhaAnuncio`
`__tablename__ = "campanha_anuncios"`:
- `id` (str pk, `novo_id()`)
- `loja_slug` (str, index) — consistência multi-loja
- `campanha_id` (str, FK `campanhas.id`, index)
- `ad_id` (str) — guardado normalizado (só dígitos), index
- `criada_em`
- `UniqueConstraint(campanha_id, ad_id)`
- Relationship `Campanha.anuncios` (lazy) para o casador ler `campanha.anuncios`.

**Migration** (`revy-trafego/alembic/versions/`): próxima após `0013` (→ `0014_*`). Conferir
`alembic upgrade head` na pasta `revy-trafego`.

**Casador** (`revy-trafego/app/campanhas.py:lead_casa_campanha`): adicionar regra, após o
match por `meta_campaign_id`:

```
# Fase 1: ad_id manual (muitos anúncios → 1 campanha)
ad_ids_camp = {normalizar_meta_campaign_id(a.ad_id) for a in getattr(campanha, "anuncios", [])}
ad_ids_camp.discard(None)
lead_ad = normalizar_meta_campaign_id(
    (lead.get("meta_ad_id_first") if modo == "first" else lead.get("meta_ad_id"))
    or lead.get("meta_ad_id")
)
if ad_ids_camp and lead_ad and lead_ad in ad_ids_camp:
    return True
```

Reusa `normalizar_meta_campaign_id` (só dígitos) de `app/meta_ads_spend.py`. `calcular_roi_loja`
não muda de assinatura; as campanhas já vêm como objetos ORM com `.anuncios` disponível na
sessão. Testes passam objetos duck-typed com `.anuncios`.

**UI** (`revy-trafego/app/templates/campanhas/form.html` + rota de criar/editar campanha em
`app/main.py`): textarea "IDs de anúncio (um por linha)". No submit, parsear linhas, normalizar
(só dígitos, descartar vazios/duplicados) e sincronizar `campanha_anuncios` (inserir novos,
remover ausentes). No modo edição, pré-carregar os ad_ids existentes. Sem tocar em
`payload_form` (campo tratado à parte por ser multivalorado).

**Testes (`revy-trafego/tests/`):**
- Casador: lead com `meta_ad_id` na lista da campanha → casa; fora da lista → "Sem campanha";
  modo `first`/`last`; normalização (com/sem separadores).
- Migration `upgrade head`.
- Save do form: várias linhas → N registros; reeditar removendo uma linha → remove o registro.

### Resultado da Fase 1

O dono cadastra os `ad_id` de cada anúncio na campanha do Revy; os leads passam a nascer na
2ª mensagem já com `meta_ad_id`; o ROI passa a atribuir lead → campanha. Falta lançar gasto
(manual no Revy) para CPL/CPA/ROAS — fora do escopo de código, vai como passo operacional no
README.

---

## FASE 2 — Resolver ad_id → campaign_id via Graph API (2-C)

Objetivo: preencher automaticamente a campanha de cada `ad_id`, eliminando o cadastro manual
da Fase 1. Montada por cima da Fase 1; se o token faltar ou a Graph falhar, a Fase 1 continua
valendo (nunca derruba o ROI).

### 2.1 Config de token (Revy)

Reusar/estender `meta_ads_config` (`revy-trafego/app/models.py`, já existe com
`token_ciphertext`): guardar o token `ads_read` cifrado (`app/cripto.py`) por loja + o
`ad_account_id`. UI para salvar/testar o token (aba Tráfego). Nunca logar o token.

### 2.2 Cache de resolução

Nova tabela `meta_ad_campanha` (migration `0015_*`):
- `loja_slug`, `ad_id` (unique por loja), `meta_campaign_id`, `meta_campaign_nome`,
  `resolvido_em`, `erro` (nullable), `tentativas`.

### 2.3 Cliente Graph

`revy-trafego/app/clients/meta_graph.py`:
`resolver_campanha_do_anuncio(ad_id, token, *, timeout) -> (campaign_id, nome)`, chamando
`GET https://graph.facebook.com/vXX.0/{ad_id}?fields=campaign{id,name}`. Timeout curto,
erros sanitizados (sem token em log/exceção).

### 2.4 Worker assíncrono

`revy-trafego/app/meta_ad_resolver_job.py` (mesmo padrão de `meta_ads_spend_job.py` /
`meta_capi_job.py`), gated por env `REVY_TRAFEGO_AD_RESOLVER_ENABLED` (default OFF): coleta
os `ad_id` distintos vindos de `listar_leads()` que ainda não estão no cache (ou com `erro` +
backoff), resolve via Graph, faz upsert no cache. Respeita rate limit; **nunca** propaga
exceção para o fluxo.

### 2.5 Casador usa o cache

`calcular_roi_loja` recebe um `mapa_ad_campaign: dict[str, str]` (montado pelo Revy a partir do
cache). Nova regra no casador: se `mapa_ad_campaign.get(lead_ad) == normalizar(campanha.meta_campaign_id)`
→ casa. Mantém o casador puro/testável (recebe o mapa, não consulta banco).

**Testes:** cliente Graph com HTTP mockado (sem chamar Meta); worker resolve + cacheia +
trata erro; casador via `mapa_ad_campaign`; decifra do token.

---

## Verificação mínima (por produto alterado)

```powershell
cd chatbot-api
.\.venv\Scripts\python.exe -m pytest -q

cd ..\revy-trafego
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Concluir com `git diff --check` e `git status --short`.

## Fora de escopo

- Lançamento de gasto e conexão de spend automático (passo operacional, não código novo aqui).
- Bot devolver simulação ao cliente (eixo separado).
- Qualquer mudança em n8n/Fly além do necessário para o contrato.
