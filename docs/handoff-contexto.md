# Handoff técnico — suíte automotiva

> **Leia primeiro:** `docs/contexto-compacto.md` (eixos A–F + fonte da verdade).  
> Este arquivo: checkpoint operacional. Seções **“Checkpoint anterior”** = histórico — não
> reexecutar. Path Windows no rodapé de seções antigas: **ignorar** (workspace = root do git).
>
> **Checkpoint mais recente: 2026-07-21 (MVP Equipe + fluxo lead/venda/estoque · Fly OFF).**
> Escolher um eixo por sessão. **Não** religar Fly sem pedido explícito.

## Checkpoint mais recente — Equipe + fluxo operacional do MVP (2026-07-21)

> **Escopo:** Portal/Chatbot operacional. A simulação não foi alterada.

### Entregue

| Área | O que | Segurança / comportamento |
|---|---|---|
| Equipe | Lista, cria e edita gerente/vendedor; redefine senha; ativa/desativa sem excluir | RBAC dono/admin plataforma, CSRF, tenancy, e-mail imutável, contas protegidas |
| Leads | `PATCH /v1/leads/{id}/etapa` + seletor no Portal | allowlist de etapas, 404 entre lojas, vendedor autorizado |
| Registro de venda | Seletores de lead e veículo no lugar de IDs técnicos | referências validadas pela API da própria loja; fallback explícito se integração cair |
| Confirmação | Veículo vinculado é baixado como vendido no Estoque antes da confirmação local | conflito/offline mantém venda registrada; falha pós-baixa exige reconciliação explícita |
| Cancelamento | Cancela o registro comercial sem reabrir silenciosamente o veículo | mensagem orienta correção manual de inventário |

### Validação

- Portal: **194 testes verdes**; recorte Equipe/Leads/Vendas: **53 verdes**.
- `git diff --check` nos arquivos de código e compilação dos arquivos alterados: OK.
- Chatbot: testes novos adicionados; host local usa Python 3.9 e não importa modelos existentes
  que exigem Python 3.10+/3.12. A imagem oficial do serviço continua em Python 3.12.

### Próximo foco recomendado (simulação continua por último)

1. Go-live WhatsApp local: remover bypass de número no n8n, versionar header seguro do webhook e smoke E2E.
2. Remover/implementar o placeholder de Ajustes do Portal.
3. Playwright E2E do fluxo login → equipe → lead → venda → estoque.

---

## Checkpoint mais recente — tráfego pago + local-first + limpeza (2026-07-20)

> **Estado:** CRM campanhas/ROI em `main` (`8e7ec5f`). Fly lab **todas as machines paradas**
> (apps/volumes preservados). Desenvolvimento **local**. Docs/planos alinhados ao status real;
> removidos duplicata `docs/superpowers/`, scripts one-off de patch n8n, checklists Bradesco/Pan
> arquivados.

### Entregue

| Área | O que | Nota |
|---|---|---|
| Campanhas + ROI | Portal `/app/campanhas`, gastos, `/app/trafego/roi` (CPL/CPA/ROAS) | #3B T5 + E8 MVP |
| First/last touch | Chatbot migration `0006` + atribuição catálogo | fbclid/gclid |
| Pixel catálogo | ViewContent + propaga UTMs/click ids no CTA | além de PageView/Lead |
| Guia loja | `docs/trafego-pago-loja.md` | operação de mídia |
| Fly | `down-all` + restart n8n forçado | **OFF** — usar local |
| n8n | `n8n/workflow-ai-nao-salvos.json` | possível bypass teste `51980336365` |

### Aberto (não misturar na mesma PR)

1. **Eixo A:** go-live WA local (Evolution + n8n + chatbot + Gemini).
2. **Eixo C residual:** #3B Task 4 eventos de funil; CAPI match phone/fbclid fino.
3. **Eixo B/D:** smoke multi-banco local; warm session; não reabrir drivers sem falha nova.
4. **Eixo E/F:** E1 áudio, E6 fotos, polish site.

### Limpeza feita nesta rodada

- Removido espelho idêntico `docs/superpowers/plans/…`.
- Arquivados checklists DONE Bradesco/Pan em `docs/plans/_archive/`.
- Apagados scripts one-off: `deploy/fly/_patch_n8n_*`, `_find_sqlite.js`, diags tmp motor.
- Atualizados: `plans/README.md`, planos #3B/#6/tráfego/workers/warm, `contexto-compacto.md`.

### Segurança

- Não commitar `.env` / `deploy/fly/.env.production.local`.
- Prints de portal = PII — só dono/gerente.

---

## Checkpoint anterior — workers sob demanda, sim multi-banco, site hero (2026-07-15→16)

> **Estado:** implementado e deployado no Fly lab. Branch `main` em sync com `origin` no
> momento deste handoff. Workspace limpo (nada pendente de commit além deste doc).

### O que entregamos (ordem cronológica aproximada)

| Área | O que | Commits-chave |
|---|---|---|
| Fan-out multi-banco | Job-pai + `simulacao_provedores`; simulação consulta bancos com credencial sem escolher um a um | `f33240f` |
| Workers que dormem | Orquestrador always-on **512 MB** (`api,mock`); slots Playwright **2 GB** `stopped` sobem sob demanda (Fly Machines API) e param com idle | `d1d3d3d`, `1d7899c` |
| Form sim enxuto | Sem mock / natureza / renda / código veículo / prazo único / campos PAN API | `d21356b` |
| PAN no catálogo | PAN tratado como **playwright** (portal go!PAN), não API, nos acessos e fan-out | `af3cc30` |
| Registros multi-banco | Timeline em seções por banco | `db4249a` |
| Prints entre machines | Coluna `screenshot_conteudo` (bytea) — path local sozinho **não** serve na API de outra Machine | `db4249a`, `1e8561b` |
| Prints de verdade | Full-page PNG estourava teto → **JPEG q55** + bytes gravados no evento no momento da captura; teto 15 MB | `1e8561b` |
| Resultado UI | Ofertas **agrupadas por banco**; reabertura pelo histórico completa placa/prazos; timeout Motor 15 s | `1e8561b` |
| Celular no form | Campo obrigatório DDD+número → `pessoa.ddd` + `pessoa.celular` (completo) | `8a0d67b` |
| Site marketing | Hero cinematográfico com `site/assets/hero-poster.jpg` (moto + holograma), full-bleed escuro | `c79e37c` |

Migrations Motor: **0012** fan-out/tarefas/slots · **0013** `screenshot_conteudo`. Head esperado: **0013**.

### Fly lab (estado operacional agora)

| App | Papel | Nota |
|---|---|---|
| `motor2037` | Orquestrador + API | Process group `app`, **512 MB**, `MOTOR_ORCHESTRATOR_ONLY` / `WORKER_TIPOS=api,mock`, fan-out + autoscale secrets ON |
| machines workers | `motor-worker-{santander,fontecred,bradesco,pan}` | ~2 GB, entrypoint on-demand, restart on-failure, imagem alinhada ao último deploy do motor |
| `portal2037` | BFF + UI | Form com celular; registros por banco; resultado agrupado |
| `site2037` | Landing | Fora do `down-all.sh`; hero com poster; URL `https://site2037.fly.dev` |
| `suite-pg` | Postgres | DB `motor` etc. |

**Acordar workers:** `lifecycle` + inventário `worker_slots` (allowlist machine id por provedor). Wake **em paralelo** (`ThreadPoolExecutor`), não serial.

**Secrets relevantes (não imprimir valores):** `MOTOR_FANOUT_ENABLED`, `MOTOR_FLY_AUTOSCALE_ENABLED`, `FLY_API_TOKEN`, `MOTOR_MAX_BROWSER_WORKERS=4`, tokens Portal↔Motor.

### Evidência de bug que já corrigimos

1. **Prints sumidos:** eventos com `screenshot_path` em `/tmp/...` no worker e **0 blobs** no Postgres. API no orquestrador não vê o disco do worker → `tem_print=false`. Fix = blob JPEG no insert do evento + redeploy de **orquestrador e workers**.
2. **Resultados “não aparecem”:** última sim multi-banco (`parcial`) **tinha** 4 parcelas Santander no DB; Fontecred/Bradesco `celular_obrigatorio`. UI reforçada por banco; celular voltou no form.
3. **Site “versão errada”:** deploy estava com placeholder do storyboard sem arte; imagem do dono não estava em `site/assets/`.

### Form de simulação (contrato atual)

Campos: CPF, nascimento, **celular (DDD)**, CNH, categoria, placa, UF, finalidade, valor, zero km, entrada, prazos (lista).  
Payload Motor: `pessoa.{cpf,nascimento,cnh,ddd,celular}` + veículo/condições + `provedores` = bancos com credencial pronta.

### Drivers / regra de entrada (TXT Bradesco do dono)

- **Bradesco / Pan portal:** entrada **opcional** — só preencher se `> 0` (já no driver; codegen em `Downloads/Bradesco.txt` confirma fluxo + “12x Entrada mínima necessária” ignorável).
- **Não versionar** o TXT do dono — já teve senha Pan em claro → recomendar rotação se ainda for a senha de prod.
- Codegen Bradesco/PAN no TXT é **âncora de fluxo**, não redesign de site.

### Site / design (aberto)

- Landing live: hero dark com poster; seções produto/painel ainda no visual monocromático antigo.
- Dono começou a colar HTML Tailwind novo (`Revy | Acelerando as vendas da sua concessionária` + `cdn.tailwindcss.com`) — **incompleto** (só head parcial). `Downloads/desing.txt` chegou **vazio (0 bytes)**.
- Pasta Downloads “Motora” (dashboard SaaS laranja `#FF854F` / dark `#0A0F17`) é **outro produto/mock** — não aplicar no Revy sem confirmação.

### Próximos passos sugeridos (próximo agente)

1. **Validar ao vivo** sim multi-banco com celular: prints JPEG nos Registros (dono/gerente) + seções de resultado por banco.
2. Se o dono completar o HTML Tailwind da landing: substituir `site/index.html` (ou adaptar) e redeploy `site2037` **sem** commitar secrets.
3. Opcional: alinhar âncoras do codegen Bradesco/PAN se falhar ao vivo (Fechar modal simulação, “Busca placa”, etc.) — só com falha nova.
4. Não reabrir fan-out/orquestrador sem regressão; não misturar go-live WA + redesign site + novo banco na mesma PR.
5. Celular: se PAN API voltar a ser usada, avaliar enviar `celular` sem DDD separado do `ddd` (hoje manda completo nos portais).

### Segurança

- Nunca commitar `Downloads/*.txt` com credenciais.
- Prints de portal = PII na imagem — só dono/gerente; `Cache-Control: private, no-store`.

---

## Checkpoint anterior — Bradesco + Pan portal LIVE (2026-07-15)

> **Foco na época:** workers Playwright sob demanda (depois implementado no checkpoint acima).
> Não reabrir drivers sem evidência nova; ler as **três** lições Playwright.
### Entregue nesta sessão (dois bancos novos, validados ao vivo pelo dono)

- **Bradesco (Turbo Lojista)** — `BradescoDriver` Playwright. Commit
  `e57387e feat(motor): driver real Bradesco (Turbo Lojista) via Playwright`.
  - `app/motor/bradesco.py`, `REAL_DRIVERS["bradesco"]`, credencial CPF/senha em `providers.py`,
    URL em `config.py`. Entrada **opcional** (só se `> 0`). Multi-prazo `Nx de R$` (ignora
    "12x Entrada mínima necessária"). Smoke: `scripts/probe_bradesco.py`.
  - Descobertos ao vivo: interstitial **"Sua senha expira"** → clicar **"Trocar senha depois"**;
    modal **"diferentes versões para a placa"** → selecionar a **1ª** + Confirmar.
- **Pan portal (go!PAN)** — `PanPortalDriver` Playwright, **dual-path** com a API existente.
  Commits `b3a94b1` (fluxo/âncoras) e `fd1a31a` (leitura de ofertas).
  - `app/motor/pan_portal.py`; dispatcher `_pan_dispatch` em `drivers.py` escolhe **API** (config
    OpenAPI completa) ou **portal** (só usuario+senha). `providers.py`: campos de API viraram
    **opcionais** — a API existente **não** regrediu. Smoke: `scripts/probe_pan_portal.py`.
  - Smoke live OK: **48x R$ 800,00 / financiado 15.116,80 / entrada 6.783,20**; UF (RJ) testada.
  - Portal é Angular + web components `pan-mahoe`; a parcela ficava em componente **oculto**
    (`<app-custom-select>`/`[role=option]`) → lida via **`textContent`** + locator. Debug:
    `MOTOR_PAN_PORTAL_DEBUG=1` → `data/screenshots/pan_ofertas_debug.txt`.
  - **Lições completas:** `docs/plans/2026-07-15-playwright-licoes-pan-portal.md`.
- **Suíte do Motor: 183 verdes** (147 → +16 Bradesco +20 Pan portal). Planos dos dois bancos
  marcados **DONE** no header.

### Estado dos drivers reais (Task 12)

`santander`, `fontecred`, **`bradesco`** = Playwright. **`pan`** = dual-path (API OpenAPI **ou**
portal go!PAN por credencial). Todos gated por credencial cifrada (Portal → Acessos bancos).

### Próximo passo (workers que dormem)

Seguir `docs/plans/2026-07-14-plano1a-workers-playwright-sob-demanda.md`: uma simulação vira uma
tarefa por banco; workers Playwright pré-criados ficam `stopped`, sobem sob demanda via Machines
API e voltam a `stopped` após fila+idle. Bancos com API (pan API) usam pool leve sem browser.
Pré-requisito de escala: tirar screenshots/storage_state do Fly Volume único → object storage
privado antes de múltiplas Machines. **Deploy do motor com os 2 bancos novos ainda não foi feito**
(commitado no `main`; lembrar `fly deploy` usa a árvore local — commitar antes).

### Segurança

- Cadastrar Bradesco/Pan só via `PUT /v1/provedores/<banco>/credenciais` ou Portal 9A.
- Codegen do dono é local (`Downloads/Bradesco.txt`) — **não versionar**; continha senha do portal
  Pan em claro → **recomendar troca de senha** do portal.

---

## Checkpoint — front Revy + planos Bradesco / Pan portal (2026-07-15 noite)

### Entregue nesta sessão (docs + front)

- **Commit/push front:** `e40cfab feat(front): marca Revy no portal, catálogo e site marketing`
  - Portal: tema claro/escuro (`data-theme` + localStorage), Inter, nav “Dia a dia/Gestão”,
    wordmark Revy, login/listagens alinhados.
  - Catálogo: CSS/templates alinhados à marca.
  - `site/` versionado: landing marketing + `Dockerfile`/`fly.toml` app **`site2037`**.
- **Planos Motor (não implementados):**
  1. Bradesco Turbo Lojista — Playwright; entrada **opcional**; multi-prazo `Nx de R$`.
  2. Pan “Buscopan” — dual-path: mantém `PanDriver` API; novo `PanPortalDriver` se só
     usuario/senha; entrada **opcional**; falta HTML da tela de ofertas no codegen.
- Codegen do dono ficou em arquivo **local** (`Downloads/Bradesco.txt`) — **não versionar**.
  Continha senha em claro do portal Pan → **recomendar troca de senha** antes do smoke live.
- Mapa de bancos e `docs/plans/README.md` atualizados com os dois planos.

### Fly lab (estado operacional)

- Scripts: `bash deploy/fly/down-all.sh` (para machines; **não** apaga apps/volumes) e
  `bash deploy/fly/up-all.sh` (sobe + always-on backends).
- Apps da suíte no `down-all`: `portal2037`, `catalogo2037`, `motor2037`, `estoque2037`,
  `chatbot2037`, `n8n2037`, `evolution2037`, `suite-pg`.
- **`site2037` não está no `down-all.sh`** — se estiver ligado, parar à parte
  (`fly machine stop -a site2037` / listar machines) ou incluir no script em PR futuro.
- **Antes de desligar a noite:** o dono pediu confirmação explícita — não rodar `down-all`
  sem “sim, desliga”.

### Próximo agente (manhã / próximo foco Motor)

1. Implementar **Bradesco** task-by-task pelo plano (API gate → parsers → driver → REAL_DRIVERS → live).
2. Em paralelo (humano): salvar HTML anonimizado da **tela de ofertas Pan** (Task 0 do plano portal).
3. Depois Pan dual-path; não misturar no mesmo PR do Bradesco.
4. Não reabrir Fontecred sem evidência nova.
5. Fan-out workers sob demanda continua planejado, não bloqueante para 1 banco novo.

### Credenciais / segurança

- Cadastrar Bradesco/Pan só via `PUT /v1/provedores/<banco>/credenciais` ou Portal 9A.
- Nunca commitar o `.txt` de codegen nem colar senhas em issue/commit.

---

## Checkpoint anterior — Fontecred LIVE

### Estado entregue

- **Segundo driver real:** Santander e Fontecred estão `real: true`; PAN mantém a base API pronta,
  mas depende de contrato/credenciais.
- Fontecred automatiza login/sessão persistida, modal COMUNICADOS, Nova Proposta, cliente, placa,
  financiamento, SCR, PEP/proteção e leitura multi-prazo/entrada mínima.
- Validação pré-browser exige celular, placa, CPF, nascimento e valor; falhas usam códigos estáveis.
- Timeline Fontecred registra etapas do browser até parcelas, com prints protegidos por RBAC/tenancy.
- Motor: **147 testes verdes**, migrations head **0011**.
- Produção: `motor2037` **versão 12**, Machine 2 GB, Chromium headed + Xvfb, health **1/1 passing**.
- Usuário confirmou simulação Fontecred real concluída após o deploy final.

### Incidente Fontecred — resumo para continuidade

O screenshot mostrava Dashboard com COMUNICADOS aberto, mas havia duas causas diferentes:

1. o fechamento antigo não cobria Bootstrap 5 nem confirmava que o modal ficou oculto;
2. depois, o worker tinha `storage_state` válido e `/login` redirecionava direto ao Dashboard.
   `networkidle` expirava por conexões abertas e o driver procurava e-mail/senha numa tela já logada.

A timeline separou as causas. Quando a sequência era `browser_pronto → falha_inesperada`, sem
`login_confirmado`, a falha acontecia **antes** do clique no X. Não diagnosticar somente pelo print.

Correções permanentes:

- reconhecer sessão autenticada por URL fora de `/login`, `COMUNICADOS` ou `Dashboard`;
- após timeout de `networkidle`, checar se o portal já autenticou antes de recarregar;
- modal usa `visible → click/escape → hidden → is_visible`, incluindo `.btn-close` e
  `[data-bs-dismiss="modal"]`;
- navegação usa `commit` tolerante, seguida de `domcontentloaded`, `readyState`, locator visível e
  `click(trial=True)`;
- exceção inesperada registra somente o tipo na timeline, sem PII;
- testar separadamente sessão fria e sessão quente no Chromium/Xvfb de produção.

Smoke final executado no próprio worker, sem cliente e sem enviar proposta:

```text
PORTAL_AUTENTICADO=True
SESSAO_REUTILIZADA=ok
MODAL_ANTES=True
MODAL_DEPOIS=False
SMOKE_WORKER=ok
```

Detalhes e checklist para próximos bancos:
`docs/plans/2026-07-15-playwright-licoes-fontecred.md`.

### Git e deploy do checkpoint

- `ce75e60 fix(motor): estabiliza fluxo Fontecred` — modal, navegação e timeline.
- `8ac4b92 fix(motor): aguarda etapas do Fontecred` — DOM/actionability e ritmo conservador.
- `1165690 fix(motor): reutiliza sessao Fontecred` — sessão quente e diagnóstico sanitizado.
- `origin/main` e worktree estavam limpos após o deploy; health HTTP 200/passing.

### Próximo foco do Motor

1. Não reabrir o Fontecred sem evidência nova; usar timeline + lição específica.
2. Próximo banco continua **API-first**; confirmar contrato PAN/BV/Bradesco antes de Playwright.
3. Implementar `testar-login` real para validar credencial/sessão sem enviar proposta.
4. Implementar fan-out/workers sob demanda; storage state/prints precisam de storage privado antes de
   múltiplas Machines.

## Checkpoint anterior — observabilidade, PAN e produção (2026-07-14)

### Entregue no código

- **Registros por simulação:** timeline sanitizada, endpoints de eventos/print, botão pequeno
  **Registros** no Portal e tela de diagnóstico ao vivo.
- **Screenshots protegidos:** capturas em pontos úteis do Playwright, tenancy/RBAC, `no-store` e
  retenção de 7 dias. Se o browser não chega a abrir página, não há print possível.
- **Fim de job infinito:** timeout duro do driver em 240 s, lease de 300 s e evento final de erro.
- **Base Banco PAN via API:** `ApiBankDriver`, `PanDriver`, catálogo de campos e credenciais genéricas
  cifradas. Ainda exige contrato/credenciais reais do PAN para chamada live.
- **Santander:** Portal envia o provider canônico `santander` minúsculo; mock homônimo não sombreia o
  driver real.
- Migrations Motor: `0010` (credencial/config PAN) e `0011` (eventos/prints). Head atual: **0011**.
- Testes do checkpoint: **Motor 123 pass** e **Portal 152 pass**.

### Git e deploy

- `0758a9c feat(motor): adiciona registros ao vivo e base API Pan` — `origin/main`.
- `e55a3c9 fix(motor): reserva memoria para o Chromium` — `origin/main`.
- `motor2037`: migrations 0010/0011 aplicadas; API, worker e Xvfb ativos; health 1/1.
- `portal2037`: imagem com Registros publicada; health 1/1 e login público validado.

### Incidente diagnosticado e correção

- Job `42bba895-f0f6-44bb-9b7a-df34cc3e15fd` parou em `browser_iniciando` e foi finalizado por
  `timeout_driver`; não ficou infinito.
- Evidência do kernel na Machine de 512 MB: Chrome tentou alocar 536870912 bytes e recebeu
  `not enough memory for the allocation`.
- Motor foi aumentado de 512 MB para **2048 MB**. Após o restart: ~1968 MB totais, health OK e probe
  Chromium headed abriu em **34,41 s**.
- Produção atual ainda combina API+worker numa Machine **always-on de 2 GB**. Isso resolve o RPA,
  porém mantém RAM provisionada mesmo ociosa.

### Direção aprovada — workers por banco sob demanda

- Uma simulação vira uma tarefa por banco; resultados chegam incrementalmente.
- Workers Playwright são pré-criados, ficam `stopped`, iniciam em paralelo via Machines API e saem 0
  após fila + idle grace, voltando a `stopped`.
- PAN e outros bancos com API usam pool leve, sem browser de 2 GB.
- Começar com Santander 2 GB; testar canário de 1,5 GB somente após telemetria. 512 MB é inválido.
- Screenshots/storage state precisam sair do Fly Volume único para object storage privado antes de
  escalar para várias Machines.
- Implementação **não começou**; fonte de verdade é o plano novo citado no topo.

> As seções abaixo registram o checkpoint anterior. Números `108/148`, migration `0009` e Motor
> `512MB` são históricos e foram superados por este bloco.

## Checkpoint anterior 2026-07-14 (sessão #3B + fixes Motor + ops Fly)

Trabalho feito com 3 agentes paralelos em worktrees, integrado e testado no `main`:

- **Motor — 6 falhas pré-existentes CORRIGIDAS** (suíte 108 verde):
  - Mock `Santander` não é mais sombreado pelo driver real (`app/motor/drivers.py`: real registrado só
    como `"santander"` minúsculo; `"Santander"` fica só no mock).
  - 4 testes de migration voltaram a passar: `alembic/env.py` re-lê `DATABASE_URL` do ambiente **e
    normaliza** (`normalizar_database_url`) — satisfaz `monkeypatch.setenv` dos testes **e** o deploy Fly
    (a URL curta `postgres://` do Fly seria rejeitada pelo SQLAlchemy 2.x sem normalizar).
- **Portal #3B — Task 8 (CSV export)**: novo módulo `app/financeiro_calc.py` centraliza a agregação de
  vendas/metas/funil (usado pelo `financeiro_dashboard` **e** pelos CSVs → reconciliação garantida);
  novo `app/relatorios.py` (`/app/relatorios` + `.../vendas.csv|metas.csv|funil.csv`, dono/gerente via
  `pode_ver_relatorios`); nav em `base.html`.
- **Portal #3B — Metas por vendedor (UI)**: form com escopo loja/vendedor + select de vendedores,
  validação de sobreposição por escopo/vendedor, coluna Escopo na lista, atingimento individual no
  `/app/vendedor` (lucro fica oculto do vendedor). Sem migration (colunas `escopo`/`vendedor_email` já
  existiam desde `0002`).
- **Ops Fly**: `evolution2037` e `n8n2037` agora **sempre-ligados** (`auto_stop_machines=false`,
  `min_machines_running=1`). Descoberto que o Fly **migra máquinas de host** e cada migração **forka um
  volume** (deixando órfãos que são cobrados) — agravado por incidente de capacidade em GRU. Scripts em
  `deploy/fly/`: `up-all.sh`, `scale-check.sh`, `clean-orphan-volumes.sh`. **Não** usar keepalive de
  máquina ociosa (acelera os forks).

Testes pós-integração: **Motor 108** · **Portal 148** (128 + 9 metas + 11 relatórios).

## Checkpoint de deploy Fly.io — 2026-07-14

### Decisões do ambiente

- Organização `crm-419`, região `gru`, domínios `fly.dev`, uma Machine por aplicação.
- Loja `Moto Center`, slug `moto-center`, WhatsApp `5551980336365`, instância Evolution `loja1`.
- E-mail operacional/admin: `bielcheeeeee@gmail.com`.
- Modo **lab/economia máxima**, alvo informado de **US$10/mês**.
- Segredos/tokens/senhas gerados ficam em `deploy/fly/.env.production.local`, ignorado pelo Git.
  Nunca ler, imprimir, copiar para logs ou versionar esse arquivo.

### Recursos implantados

| Componente | App/recurso | Machine | Estado/configuração relevante |
|---|---|---|---|
| Motor | `motor2037` | `0807560c916d68` | API+worker; Flycast; **always-on (opção A)**; **512MB lab** (2048 p/ RPA) |
| Estoque | `estoque2037` | `287e35dbd147e8` | API+outbox na mesma Machine; privado/Flycast; **always-on (opção A)** |
| Chatbot | `chatbot2037` | `d8d1375a42e578` | privado/Flycast; **always-on (opção A)** — n8n não quebra no cold-start |
| Catálogo | `catalogo2037` | `0807560c916768` | público; autostop ok; volume `catalogo_data` |
| Portal | `portal2037` | `6837936c0d73d8` | público; autostop ok; volume `portal_data` |
| Evolution | `evolution2037` | `7847926f5d1758` | v2.3.7, 1 GB; **sempre-ligado** (autostop=false); volume `evolution_instances` |
| n8n | `n8n2037` | `0807564f9034e8` | v2.26.8, 1 GB; **sempre-ligado** (autostop=false); volume `n8n_data` |
| PostgreSQL | `suite-pg` | `d8946d2f320de8` | Postgres Flex 18.1; 256 MB; volume `pg_data`; ligado |
| Redis | `suite-redis` | Upstash | PAYG; usado pela Evolution |

O volume duplicado do Motor foi removido. Volumes persistentes restantes têm 1 GB e snapshots
agendados. Não criar segunda Machine/volume sem revisar o teto mensal.

### URLs e acessos

- Portal: `https://portal2037.fly.dev`
- Catálogo: `https://catalogo2037.fly.dev` (raiz redireciona para `/l/moto-center`)
- Evolution API: `https://evolution2037.fly.dev/`
- Evolution Manager: `https://evolution2037.fly.dev/manager`
- n8n: `https://n8n2037.fly.dev/` (cadastro inicial/login na própria raiz)
- Portal admin criado com o e-mail acima; senha apenas no arquivo local de segredos.
- Evolution `loja1` criada; conexão/mensagem recebida confirmada pelo usuário.

### Ajustes de deploy já aplicados

- `fly.toml` criados para os produtos e infraestrutura necessária.
- URLs `postgres://` normalizadas para SQLAlchemy/psycopg em Motor, Estoque e Chatbot.
- Motor e Estoque combinam API+worker/outbox para respeitar uma Machine por app.
- Portal e Catálogo corrigidos para CSS HTTPS; Uvicorn do Portal recebe proxy headers.
- Catálogo raiz redireciona para `moto-center`; CSS e página pública responderam 200.
- n8n subiu para 1 GB (512 MB não bastou) e usa `auto_stop_machines = "suspend"`.
- Portal exibiu o frontend Motora correto depois da correção de CSS.

### Estado do n8n/Evolution

- Workflow correto: `WhatsApp IA - Somente Nao Salvos` (18 nós), webhook `POST /webhook/whatsapp-ai`.
- A cópia importada foi preparada com Chatbot em `http://chatbot2037.flycast:8000`, Evolution em
  `https://evolution2037.fly.dev` e instância `loja1`.
- O GET manual no webhook retorna corretamente “not registered for GET”; o nó aceita **POST**.
- Usuário informou ter substituído `__CHATBOT_TOKEN__` nos sete Tool Code e configurado
  `X-Webhook-Token` nos dois nós que chamam `/webhook/mensagem`.
- Ainda **confirmar** no editor:
  1. credencial do `Google Gemini Chat Model1`;
  2. `apikey` Evolution em `Consultar contato na Evolution1`;
  3. `apikey` Evolution em `Responder WhatsApp1`.
- Webhook Evolution deve apontar para
  `https://n8n2037.fly.dev/webhook/whatsapp-ai`, evento `MESSAGES_UPSERT`.
- Entrega Evolution → n8n foi confirmada pelo usuário em 2026-07-14. Ainda falta teste E2E de resposta
  com outro número **não salvo**; mensagens `fromMe=true` representam atendente e pausam o bot.

### Autostop e custo observado

- **Opção A APLICADA no Fly (2026-07-14):** machines de `motor2037` / `estoque2037` /
  `chatbot2037` com `autostop=false`, `started`, checks **passing**. Health flycast OK entre eles.
  `fly.toml` atualizado no repo; redeploy completo falhou em `gru` por capacidade no
  `release_command` — config live via `fly machine update --autostop=off`.
- **Motor lab = 512MB** (antes 2048). RPA Santander: `fly machine update … --vm-memory 2048` e
  liberar RAM (parar Portal/Catálogo) se der `mem_overcommit_exceeded`.
- **Orçamento de memória da org:** ~4.3GB always-on (pg+3 backends 512 + n8n 1G + evo 1G).
  **Portal e Catálogo não cabem os dois started juntos** com essa config — um por vez (ou
  aumentar limite da org / reduzir n8n/evo).
- Portal validado HTTP **200** `/health/ready` com backends always-on.
- Custo sobe; teto US$10 do lab já flexibilizado.
- **Lab stop/start:** `deploy/fly/down-all.sh` (para machines) + `deploy/fly/up-all.sh`
  (PG → backends always-on → evo/n8n → portal; catálogo só com `--catalogo`).
  Stop/start **preserva** `autostop=off` nos backends; o `up-all` ainda reaplica.

### Dados e pendências funcionais

- Estoque: 1 loja, 2 veículos disponíveis, ambos `publicado=false`; publicar pelo Portal para aparecerem
  imediatamente no Catálogo. Catálogo lê a API pública do Estoque; não há importação separada.
- Motor: cliente/credenciais técnicas existem, mas não havia credencial bancária nem simulação no banco
  no checkpoint. Cadastrar banco em Portal → Acessos bancos para simulação real.
- Portal é o frontend principal; Motor e Estoque permanecem APIs privadas por segurança.

### Próximo passo operacional

1. Confirmar Gemini + duas chaves Evolution no workflow.
2. Publicar/salvar o workflow e manter o webhook `MESSAGES_UPSERT` ativo.
3. Acordar Evolution, confirmar `loja1` como `open`, enviar mensagem de outro número não salvo e revisar
   a Execution inteira até `Responder WhatsApp1`.
4. Publicar os veículos desejados no Portal e validar o Catálogo.
5. Só no go-live decidir Evolution always-on e revisar o orçamento.

## Estado em uma frase

Suíte **demo forte**: Motor com **Santander, Fontecred, Bradesco e Pan portal (go!PAN) LIVE**
fim-a-fim, histórico por usuário e Registros/prints por etapa. Pan é dual-path (API OpenAPI ou
portal por credencial). Chatbot/Estoque/Catálogo integram por HTTP. Transporte WhatsApp Evolution →
n8n confirmado, resposta IA ainda sem E2E completo. **Próximo foco: workers Playwright sob demanda
que dormem** (plano 2026-07-14) — não alterar os drivers reais sem ler as **três** lições Playwright
(Santander, Fontecred, Pan portal).

## Verificação

| Produto | Testes (aprox.) | Porta host típica |
|---|---:|---|
| Motor | **183 pass** | `:8000` |
| Chatbot | 88 | `:8001` |
| Estoque | 65 | `:8100` |
| Catálogo | 23 | `:8200` |
| Portal | **152 pass** | `:9000` |
| **Total** | **~475** | Evolution `:8080`, n8n `:5678` |

> **Histórico do checkpoint 2026-07-14:** as falhas abaixo foram resolvidas antes do Fontecred:
> `test_worker_conclui_com_cinco_provedores` / `test_persistencia_do_resultado_apos_worker` esperavam 5
> provedores mock e recebiam 4 — o driver real `Santander` (registrado sob `Santander` e `santander`)
> sombreava o mock homônimo e era derrubado sem credencial em `resolver_drivers`; agora o real registra só
> `"santander"`. Os 4 testes de migration falhavam por `NoSuchTableError` (o `env.py` do commit de deploy
> deixou de re-ler `DATABASE_URL`); restaurado o re-read **com normalização**. Suíte 108 verde.

```powershell
cd motor-simulacao; .\.venv\Scripts\python.exe -m pytest tests/ -q
cd ..\portal-gestao; .\.venv\Scripts\python.exe -m pytest tests/ -q
# Worker live:
cd ..\deploy\motor-standalone
docker compose exec -T motor-worker sh -c "pgrep -a Xvfb; pgrep -a python"
```

## Por produto (feito / falta)

### Motor (`motor-simulacao/`, `deploy/motor-standalone`)

- **Feito:**
  - Jobs async, worker/lease, auth+tenancy, cifra, CLI, mock de 5 bancos.
  - **Task 11** credenciais cifradas (Portal 9A).
  - **Task 12 — Santander e Fontecred LIVE:**
    - `SantanderDriver` + `PlaywrightBankDriver` (stealth, storage_state, screenshots).
    - Worker Docker: Chromium + **Xvfb headed** (`MOTOR_BROWSER_HEADLESS=0`), `shm_size: 1gb`.
    - Entrypoint limpa lock X órfão (`scripts/worker-entrypoint.sh`).
    - Multi-prazo parseado da tela real.
    - **Entrada necessária devolvida pelo banco** (`parse_entrada`): Santander calcula e a tela mostra;
      não é mais enviada como input (`_ajustar_entrada` removido). Novo campo `entrada` em
      `ResultadoDriver`/`ResultadoProvedor`/`ResultadoORM` (**migration 0008**) → exibido no Portal.
      Fallback financiado = valor − entrada(retornada).
    - **Fix skeleton** (`_passo_aguardar_simulacao`): espera o texto **real** do card (`Nx de`) com 2
      leituras estáveis, ignorando o skeleton de carregamento (causa do `parcelas_nao_encontradas`).
    - Códigos: `portal_bloqueado`, `portal_falhou`, `display_ausente`, `login_timeout`, etc.
    - `FontecredDriver`: login/sessão persistida, modal COMUNICADOS, Nova Proposta, cliente/placa,
      financiamento, PEP/proteção e parcelas reais; waits por DOM/actionability e timeline própria.
    - Lições Fontecred: `docs/plans/2026-07-15-playwright-licoes-fontecred.md`.
  - **Listagem `GET /v1/simulacoes`** (Task 16): filtros `status`/`solicitado_por`/`desde`/`ate` +
    paginação `limite`/`offset`, escopada por `cliente_id`; grava `solicitado_por` (header `X-Ator`) no
    create (**migration 0009**). `simulacao_resumo` não decifra payload (CPF omitido).
  - Processamento não deixa job eterno em `processando` (catch genérico + retry).
  - Migrations lineares até **head 0011** (0010 PAN → 0011 eventos/prints).
- **Falta:**
  - Próximos bancos reais, sempre API-first (ver reconhecimento + duas lições Playwright).
  - Multi-banco **paralelo** (1 Playwright por banco no mesmo job).
  - `testar-login` real (hoje **placeholder**).
  - **Task 10** revenda.

### Portal (`portal-gestao/`)

- **Feito:** auth/RBAC, estoque, leads, conversas, **9A Acessos bancos**, E10 Tráfego.
  - Simulação: form → **progresso HTMX** (`/app/simulacoes/job/{id}`) → resultado multi-prazo, com
    **coluna Entrada** (necessária, devolvida pelo Santander) e whitelist mantendo `entrada`.
  - **Histórico de simulações por usuário (Task 16):** rota `/app/simulacoes/historico` (default "minhas
    sims" por email; toggle "toda a loja" p/ dono/gerente), template `historico.html`, link no form.
    `MotorClient.listar_simulacoes` repassa token do servidor + `X-Ator`=email.
  - `MOTOR_URL` + **`MOTOR_TOKEN`** obrigatórios (sem token a tela Acessos fica vazia).
  - Alertas de erro com códigos legíveis (`resultado.html`).
  - **#3B Task 8 CSV export (FEITO):** `app/financeiro_calc.py` (agregação compartilhada,
    reconciliação garantida), `app/relatorios.py` (`/app/relatorios` + `vendas/metas/funil.csv`,
    dono/gerente via `pode_ver_relatorios`).
  - **#3B Metas por vendedor UI (FEITO):** escopo loja/vendedor no form, validação de sobreposição,
    atingimento individual no `/app/vendedor` (lucro oculto do vendedor).
- **Falta:** #3B **Task 4** (eventos do funil) e **Task 5** (campanhas/atribuição metadados);
  Playwright E2E; retry outbox CAPI. **Disparo** WhatsApp em massa / e-mail: esboço **#6 E11/E12**
  (não implementar sem priorizar; ver plano6).
  - **Nota histórico:** sims **anteriores** ao deploy têm `solicitado_por` nulo → não aparecem em "minhas
    sims"; dono vê no escopo "toda a loja". Novas sims populam normalmente.

### Chatbot / Estoque / Catálogo

- Sem mudança crítica nesta sessão. Chatbot: go-live WhatsApp ainda pendente
  (`docs/go-live-chatbot.md`). Estoque = fonte de verdade dos veículos. Catálogo: Pixel browser ok.

## Problemas duros desta sessão (resumo)

1. **Akamai** bloqueia headless_shell → headed + Xvfb.  
2. **Xvfb lock órfão** após restart → entrypoint limpa.  
3. **Material UI** sem placeholder → labels / `type=tel` / roles.  
4. **Falso positivo "Cliente"** na landing → marcadores pós-login específicos.  
5. **Modal simulações anteriores** + overlays Material → fechar X / Escape / aguardar loading.  
6. **Parser** de parcelas e "Valor liberado" no HTML quebrado.  
7. Hot-patch de `.py` exige **restart do worker** (import em memória).
8. **Fontecred `networkidle` enganoso:** sessão quente já estava no Dashboard, mas a navegação expirava.
9. **Screenshot não define a etapa:** modal aberto não significava que o clique no X havia rodado;
   ausência de `login_confirmado` mostrou falha anterior.
10. **Modal deve confirmar estado:** `visible → ação → hidden`, não apenas click sem exceção.
11. **Local ≠ worker:** sessão local expirada cobriu login frio; storage state válido do Fly revelou o
    caminho quente. Testar ambos no Chromium/Xvfb.

Detalhe operacional: lições **Santander** e **Fontecred** na pasta `docs/plans/`.

## Regras permanentes

- Workspace: `C:\Users\guilh\Documents\codigo\bot-whatsapp-financiamento`.
- Integrações **só HTTP**. Tokens só no servidor.
- **Nunca** ler/versionar `.env`, tokens Motor/Chatbot, Evolution, Gemini, chaves de cifra, senhas de portal.
- n8n versionado: placeholders. Ordem planos: `#0 → #1A → #4A → #2A → #5A → #3A/#3A.1 → #3B → #6` (+ #7 ops).
- Parcelas com nome de banco **sem** `real: true` = mock.
- Próximo banco Playwright: **API-first** — só robô se confirmar sem API.
- Roadmap #6 limpo em 2026-07-14: **E9 fora**; E2/E4/E7 adiados; **E13–E18** aprovados (notif,
  reserva, PDF, troco, onboarding, domínio); rejeitados C2/C5/C7/C8/C10/C12.

## Próximos passos

**Escolher um eixo** em `docs/contexto-compacto.md` (tabela A–E). Não seguir lista única abaixo
como ordem fixa — são atalhos por eixo:

| Eixo | Atalho |
|---|---|
| A Demo/WA | `docs/go-live-chatbot.md` + publicar estoque |
| B Multi-banco | Bradesco plano 2026-07-15 (lições antes); Pan após HTML ofertas |
| C CRM | #3B Task 4 → 5 |
| D Escala | fan-out workers (plano 2026-07-14) |
| E Dia a dia | E1 áudio / E6 fotos (#6) |

Task 16 histórico: **FEITO**. Fontecred/Santander: **não reabrir** sem evidência.

## Avisos operacionais

1. `MOTOR_TOKEN` no compose do Portal = mesmo token do cliente Motor.
2. Após editar `santander.py` / entrypoint no container: `docker compose restart motor-worker` e
   `pgrep Xvfb`.
3. Screenshots de falha: volume `motor_browser_data` → `/srv/data/screenshots/`.
4. Não usar `printenv` em containers com tokens.
5. Rebuild Docker pode falhar por DNS do Hub; hot-copy + restart é workaround válido em dev.
