# Fly + RPA multi-banco: problema atual, opções e decisão

> **Data:** 2026-07-16  
> **Status:** ✅ **Decisão registrada** — implementar combo **B + D** + **padronizar login** (ver §10 e §11)  
> **Contexto:** Motor `motor2037` (orquestrador + workers Playwright sob demanda), Portal com seleção de bancos, drivers Santander / Fontecred / Bradesco / Pan portal.

**Leitura relacionada:**

- `docs/referencia-viva/handoff-contexto.md`, `docs/referencia-viva/contexto-compacto.md`
- Lições Playwright: Santander, Fontecred, Pan, Bradesco
- Este doc **não** substitui cotação comercial de agregadores (FANDI etc.)

---

## 1. Resumo executivo (1 parágrafo)

O Motor simula financiamento abrindo o **portal do lojista** com Playwright em machines Fly (Chromium headed + Xvfb). **Um banco por vez** costuma funcionar em ~100 s. **Vários bancos em paralelo** costumam falhar com `timeout_driver`, captcha/reCAPTCHA ou portal lento — não porque as machines compartilhem CPU, e sim porque o **egress é IP de datacenter** e o anti-bot (reCAPTCHA/WAF) trata várias sessões automáticas do mesmo “vizinho de rede” como risco.

**Decisão (2026-07-16):** (1) **máx. 2 bancos Playwright por vez** no Fly (reduz lag/carga de IP); (2) **sessão quente persistente** (`storage_state` fora do `/tmp`, sobrevive on-demand); (3) **padronizar** nos drivers: se **não** achar tela de login / já autenticado → **pular login** e ir direto à próxima fase, com evento claro na timeline.

---

## 2. Arquitetura atual (Fly)

```text
Portal / WhatsApp
       │
       ▼
motor2037 (orquestrador ~512 MB, always-on)
  · API + fan-out (1 tarefa por banco)
  · acorda workers em paralelo (MAX_BROWSER_WORKERS=4, FLY_START_BURST=4)
       │
       ├─ motor-worker-santander   ~2 GB  on-demand  stopped após idle
       ├─ motor-worker-fontecred   ~2 GB
       ├─ motor-worker-bradesco    ~2 GB  (+ storage_state injetado via files[])
       └─ motor-worker-pan         ~2 GB
```

| Peça | App / machine | Notas |
|---|---|---|
| Orquestrador | `motor2037` process `app` | Sem Chromium pesado |
| Workers | 4 machines no **mesmo app** | 1 provedor cada; `MOTOR_WORKER_ON_DEMAND=1` |
| Timeouts (deploy 2026-07-16) | Driver **420 s**, lease **480 s**, browser **90 s** | Antes driver 240 s estourava fácil |
| Portal | `portal2037` | Form com **checkbox por banco** (testar 1 a 1) |

**Importante:** cada worker é isolado em RAM/processo. O que **não** isola é o **IP de saída (egress)** na região `gru` — várias machines do mesmo org/região costumam sair por faixas de IP de **cloud**.

---

## 3. Problema atual (evidência)

### 3.1 Sintomas

| Sintoma | Código / log típico |
|---|---|
| Job multi-banco morre perto do teto de tempo | `timeout_driver`, `DriverDeadlineExceeded` (~240–270 s no período antigo; ainda risco com portal lento) |
| Login às vezes passa, fluxo trava depois | `login_confirmado` → depois falha / timeout |
| Bradesco login | Banner *“Erro ao tentar verificar o reCAPTCHA”* → `captcha_login` |
| 1 banco sozinho | Santander / Fontecred **concluída** em ~100 s (evidência 2026-07-16) |
| Local headed (rede residencial) | Login Bradesco **OK** + `storage_state` salvo |

### 3.2 O que **não** é a causa raiz

- “Machines diferentes compartilham a mesma CPU do Chromium” — **não** (1 browser por worker).
- “Só falta mais RAM no orquestrador 512 MB” — workers já são 2 GB.
- “Trocar de app Fly resolve captcha” — **não de forma confiável** (continua ASN/datacenter).

### 3.3 Causa raiz (consenso técnico + relatos de mercado)

1. **IP de datacenter** (Fly) com má reputação para reCAPTCHA v3 / WAF.  
2. **Paralelismo:** 4 Chromiums ≈ 4 automações no mesmo “bloco” de rede → score pior + portal mais lento.  
3. **Login frio** a cada job quando não há sessão válida (`storage_state` em `/tmp` some ao parar a machine).  
4. **Deadline do driver** vs duração real do fluxo quando o portal está sob pressão.

### 3.4 Evidência de jobs (amostra 6 h, 2026-07-16)

| Modo | Exemplo | Resultado |
|---|---|---|
| Só Fontecred | `21e83b24…` | **concluída** ~100 s |
| Só Santander | `0e620bed…` | **concluída** ~100 s |
| 4 bancos juntos | `cbd58064…`, `ff65d986…` | quase tudo **`timeout_driver`** / falha |
| Bradesco isolado (Fly) | `793651bd…` | **`captcha_login`** (sessão/IP) |

### 3.5 Mitigações já aplicadas

| Item | Status |
|---|---|
| `stealth=False` em portais com reCAPTCHA (Fontecred/Bradesco/Pan) | Feito |
| Espera `grecaptcha` + código `captcha_login` no Bradesco | Feito + deploy |
| Timeouts 420 / 480 / 90 s | Feito + deploy |
| Checkbox de bancos no Portal (1 por vez) | Feito + deploy |
| `storage_state` Bradesco injetado no worker (files[]) | Parcial (volátil; re-injetar se recriar machine) |
| Serializar / limitar paralelismo | **Decidido: máx. 2** (opção B) — ver §10–11 |
| Sessão quente persistente | **Decidido** (opção D) — ver §10–11 |
| Padronizar skip de login | **Decidido** — ver §11.1 |

---

## 4. Opções (catálogo — referência)

> As opções abaixo permanecem documentadas. A **escolha ativa** está na §10.

Legenda de esforço: **B** baixo · **M** médio · **A** alto.

### Opção A — Fila global (máx. 1 Playwright por vez no Fly)

**O quê:** orquestrador só acorda **1** worker Chromium no cluster; próximos bancos ficam `recebida` até o anterior terminar (contar também tarefas `processando`/`reservada`).

| | |
|---|---|
| **Resolve** | Rajada no mesmo IP; timeouts em massa no multi-banco |
| **Não resolve sozinho** | Captcha de login frio no Bradesco |
| **Tempo multi-banco** | ~4× (ex.: 4×2 min ≈ 8–12 min) |
| **Custo $** | ~0 (só tempo de machine) |
| **Esforço** | B |
| **Risco** | Baixo |

**Quando escolher:** estabilidade > “4 bancos em 2 minutos”.

---

### Opção B — Meio-termo (máx. 2 em paralelo + opcional stagger)

**O quê:** `MAX_BROWSER_WORKERS=2` e/ou atrasar o 2º wake em 30–60 s.

| | |
|---|---|
| **Resolve** | Parte da pressão de IP |
| **Não resolve** | Dia ruim de score; 2 ainda podem captcha |
| **Custo $** | ~0 |
| **Esforço** | B |
| **Risco** | Médio |

---

### Opção C — Só produto/UX (já parcialmente feito)

**O quê:** usuário escolhe bancos; default sugerido “1 banco”; aviso se marcar todos.

| | |
|---|---|
| **Resolve** | Debug e operação consciente |
| **Não resolve** | Quem marcar os 4 ainda quebra |
| **Custo $** | 0 |
| **Esforço** | B (copy/default) |
| **Risco** | Baixo na infra; alto se o uso real for sempre multi |

**Estado:** checkboxes no Portal **já deployados**.

---

### Opção D — Sessão quente persistente (`storage_state` de verdade)

**O quê:** após login OK, gravar cookies/localStorage por banco em **volume ou blob no Postgres (cifrado)**; worker carrega no boot; job **pula login** enquanto a sessão for válida.

| | |
|---|---|
| **Resolve** | Grande parte do reCAPTCHA de login e tempo de login |
| **Não resolve sozinho** | WAF no meio do fluxo se 4 IPs cloud em paralelo |
| **Custo $** | Volume 1 GB barato ou coluna bytea |
| **Esforço** | M |
| **Risco** | Médio (sessão expira → renovar local/manual) |

**Estado parcial:** Bradesco tem `files[]` com JSON local; **não** sobrevive bem a todo redeploy/ops sem processo de renovação.

---

### Opção E — Proxy residencial sticky (1 IP “casa” por banco)

**O quê:** cada worker Playwright sai pela internet via **proxy residencial BR sticky** (mesmo IP durante o job). O código continua no Fly; só o **IP que o banco vê** muda.

```text
Worker Fly  ──►  proxy residencial (sticky)  ──►  portal do banco
                      IP parece “casa”
```

| | |
|---|---|
| **Resolve** | Reputação de IP + paralelo com mais chance |
| **Não resolve sozinho** | Fingerprint/bot se o fluxo for agressivo demais |
| **Custo $** | Típico dezenas–centenas USD/mês (cotar) |
| **Esforço** | M |
| **Risco** | Médio (ToS bancos, custo, latência) |

**Não confundir com:** apps Fly separados (continua cloud) ou “solver” de captcha (2Captcha etc.).

---

### Opção F — Solver de captcha (API externa)

**O quê:** serviço resolve reCAPTCHA quando aparece.

| | |
|---|---|
| **Esforço** | M |
| **Risco** | **Alto** em portal bancário / ToS / compliance |
| **Recomendação** | **Não** como caminho principal do Revy |

---

### Opção G — Apps Fly separados por banco

**O quê:** `motor-bra`, `motor-san`, etc.

| | |
|---|---|
| **Resolve** | Isolamento operacional |
| **Não resolve** | Captcha de forma confiável (mesmo tipo de egress) |
| **Esforço** | A, baixo retorno no problema atual |
| **Recomendação** | Só se for organização, **não** como fix de captcha |

---

### Opção H — Agregador / API multibanco (FANDI, Autoconf, Credere, Creditas…)

**O quê:** parar (ou reduzir) RPA em 4 portais; 1 integração que já fala com vários bancos.

| | |
|---|---|
| **Resolve** | Captcha/IP no **seu** stack se for **API** |
| **Custo $** | Autoconf a partir de ~**R$ 299/mês** (DMS; simulador em planos maiores). FANDI **sem preço público** (enterprise). Creditas-like: **% da operação**. |
| **Esforço** | A (comercial + adapter) |
| **Risco** | Cobertura (Fontecred?), tabela, API real vs só UI |

Detalhe de preços e comparação com local: ver §6.

---

### Opção I — Rodar workers **localmente** (PC da loja / VPS residencial)

**O quê:** Chromium na rede residencial; Motor na cloud só orquestra **ou** tudo local.

| | |
|---|---|
| **Resolve** | IP (mesmo efeito do teste Bradesco local OK) |
| **Custo $** | Energia ~R$ 25–150/mês; hardware se já existe ≈ 0 |
| **Esforço** | M (túnel, always-on, segurança de credenciais) |
| **Risco** | PC desligado = simulação parada; suporte |

---

## 5. Combos (referência)

| Combo | Ideia | Estabilidade | Velocidade multi | Custo |
|---|---|---|---|---|
| **C + A** | UI + fila 1 Chromium | Alta | Lenta | Muito baixo |
| **C + A + D** | Fila + sessão quente | Muito alta | Lenta, mas cada job mais curto | Baixo |
| **C + B + D** ✅ **ESCOLHIDO** | Até **2** paralelos + sessão quente + login padronizado | Média–alta | Média | Baixo |
| **C + D + E** | Sessão + proxy sticky | Alta | Rápida (paralelo) | Médio–alto |
| **C + I** | Local para Playwright | Alta | Depende do PC | Baixo $ / ops |
| **H** | Agregador se comercial fechar | Alta (se API) | Rápida | Mensalidade / % |

**Fallback se B+D ainda falhar em produção:** reavaliar **A** (1 por vez) ou **E** (proxy).

---

## 6. Comparação de custo (ordem de grandeza)

| Caminho | Custo mensal típico | Observação |
|---|---|---|
| RPA **local** | R$ 0–150 (energia) | Melhor IP; você opera o host |
| RPA **Fly** (uso moderado) | ~US$ 10–40 motor/workers + resto da suíte | Infra barata; falha é qualidade, não fatura |
| Fly + **proxy resi** | Fly + US$ 30–150+ | Paralelo viável |
| **Autoconf** | A partir de **R$ 299**/mês + setup; simulador em planos maiores (~faixa R$ 400–1.200 mercado) | DMS inteiro, não só motor |
| **FANDI** | **Sob consulta** | Líder F&I; preço enterprise |
| **Creditas-like** | % da originação | Menos fixo, menos controle |
| Manutenção RPA (horas) | 8–40 h/mês × valor hora | Muitas vezes **>** mensalidade SaaS |

**Conclusão de custo:** o Fly **não** é o vilão da planilha. O vilão é **confiabilidade do RPA em cloud** vs **mensalidade/comissão de agregador** vs **horas de manutenção**.

---

## 7. Critérios de decisão (checklist)

Responda com o dono:

1. Multi-banco pode levar **8–12 min** se for estável? (sim → A; não → E ou H)  
2. Orçamento mensal extra para proxy: zero / até X?  
3. Aceita renovar sessão (login local/manual) 1× por dia ou semana? (sim → D)  
4. A loja **já paga** FANDI/Autoconf/outro? (sim → cotar API = H)  
5. Bancos obrigatórios: Santander, Bradesco, Fontecred, Pan — todos no agregador?  
6. Quem opera o PC se for local (I)?

---

## 8. Próximos passos (catálogo legado)

Implementação detalhada da decisão: **§11**. Opções não escolhidas (E/H/I) só se B+D falhar ou produto mudar.

---

## 9. O que **não** fazer agora (sem nova evidência)

- Reescrever todos os drivers do zero  
- Apps Fly separados como “solução de captcha”  
- Solver de captcha em produção bancária  
- Ligar `stealth=True` de novo em portais com reCAPTCHA (já quebrou Fontecred/Bradesco)  
- Proxy residencial (**E**) antes de medir B+D em produção  
- Agregador (**H**) sem cotação comercial

---

## 10. Decisão

| Campo | Valor |
|---|---|
| Data da decisão | **2026-07-16** |
| Escolhido (combo) | **C + B + D** + padronização de login (sessão quente) |
| Quem aprovou | Dono / sessão de produto (pedido explícito no chat) |
| Prazo de revisão | Após 1 semana de sims multi-banco em produção ou se captcha_rate continuar alto |
| Notas | Máx. **2** Chromiums Playwright simultâneos no cluster; sessão logada **persistente** (on-demand ok); se **não** achar tela de login → **pular** e seguir fluxo |

### 10.1 O que foi escolhido (em uma frase cada)

1. **Paralelismo 2 (B):** no máximo **dois** bancos Playwright rodando ao mesmo tempo no Fly — reduz lag e pressão de IP vs 4 juntos.  
2. **Sessão quente persistente (D):** `storage_state` salva **fora do `/tmp`**, sobrevive stop on-demand; jobs reabrem já logados quando a sessão ainda vale.  
3. **Login padronizado:** em **todos** os drivers Playwright, contrato único:  
   - se **já autenticado** (sem formulário de login / marcador de área logada) → **não** digitar senha; evento `login_pulado` / sessão quente; ir **direto** à próxima fase (Nova proposta, cliente, etc.);  
   - se **achar login** → login frio (grecaptcha quando couber) → `login_confirmado` → seguir.  
4. **UI (C):** manter checkbox de bancos no Portal (testar 1 ou N; N respeita teto 2 no orquestrador).

### 10.2 O que fica de fora por ora

- Proxy residencial (E)  
- Fila estrita 1 (A) — só se 2 ainda for instável  
- Agregador (H), local full (I), solvers (F)

---

## 11. Plano de implementação (decisão B + D + login)

> Ordem sugerida: **11.1 → 11.2 → 11.3** (login claro primeiro reduz confusão nos prints; sessão e teto 2 destravam produção).

### 11.1 Padronizar tela de login / sessão quente nos drivers

**Objetivo:** deixar **explícito e igual** em Santander, Fontecred, Bradesco e Pan portal.

**Contrato (todos os `*_passo_login` / fluxo live):**

```text
goto(login_url)  [com storage_state se existir]
  │
  ├─ portal JÁ autenticado?  (URL fora de /login OU marcador da área logada
  │                           OU ausência do campo de login — Pan)
  │     → NÃO preencher CPF/senha
  │     → evento: login_pulado / sessao_quente
  │     → return e seguir próxima fase (comunicados / nova proposta / …)
  │
  └─ tela de login presente
        → preencher credencial + reCAPTCHA se necessário
        → evento: login_confirmado
        → seguir próxima fase
```

**Tarefas:**

| # | Tarefa | Arquivos |
|---|---|---|
| 1.1 | Documentar o contrato em `playwright_base.py` (docstring da classe + helper opcional) | `app/motor/playwright_base.py` |
| 1.2 | `_passo_login` devolve `bool` ou enum: `True` = login frio, `False` = pulado | `bradesco.py`, `fontecred.py`, `santander.py`, `pan_portal.py` |
| 1.3 | Em `_simular_playwright`, emitir evento distinto: `login_pulado` vs `login_confirmado` | mesmos |
| 1.4 | Santander: hoje **não** checa sessão quente antes de preencher CPF — alinhar ao contrato | `santander.py` |
| 1.5 | Testes unitários com MagicMock: “já autenticado → não type senha”; “login frio → type” | `tests/test_*_driver.py` |

**Aceite:** timeline do Portal mostra `login_pulado` quando a sessão vale; com storage expirado mostra `login_confirmado` ou `captcha_login` / erro claro. **Nunca** ficar 45 s procurando textbox CPF numa tela já logada.

---

### 11.2 Sessão logada persistente (on-demand OK)

**Objetivo:** parar de depender só de `/tmp` + `files[]` one-shot.

**Desenho alvo:**

```text
Job termina OK / login OK
  → browser_ctx.storage_state() → bytes
  → grava persistente por (cliente_id?, provedor)  [ver decisão de storage]
Worker sobe (on-demand)
  → lê storage do provedor
  → escreve em MOTOR_STORAGE_STATE_DIR/<provedor>.json  (path local efêmero ok)
  → _new_context(storage_state=...)
  → fluxo 11.1 (provável login_pulado)
```

**Opções de storage (escolher na implementação; preferência em ordem):**

| Preferência | Onde | Prós | Contras |
|---|---|---|---|
| **1** | Blob cifrado no Postgres (por provedor / tenant) | Workers sem volume; multi-machine | Migration; tamanho JSON ~5–50 KB |
| **2** | Volume Fly por worker | Simples no path | 4 volumes; zona da machine |
| **3** | Só `files[]` no machine config | Rápido ops | Atualizar config a cada login; frágil |

**Tarefas:**

| # | Tarefa | Notas |
|---|---|---|
| 2.1 | Definir storage (recomendado: **Postgres cifrado** alinhado a credenciais) | Migration + model |
| 2.2 | API interna ou helper: `carregar_storage(provedor)` / `salvar_storage(provedor, bytes)` | Nunca logar cookies |
| 2.3 | Antes do browser: materializar arquivo local se blob existir | Entry do driver ou worker |
| 2.4 | Após login frio OK **e** após sim com sucesso: salvar de novo | Renova cookies |
| 2.5 | Se portal mandar de volta ao login: invalidar storage + evento | Evita loop com JSON podre |
| 2.6 | Runbook: renovar sessão (probe local headed → sobe storage) | `docs/` ou handoff |
| 2.7 | Secrets: path/arquivo **não** no git; RBAC se expor no Portal depois | |

**Aceite:** worker Bradesco (e depois os outros) sobe stopped → start → `login_pulado` sem captcha enquanto a sessão do portal for válida; após stop de 10 min e novo job, **ainda** quente se o blob/volume existir.

**On-demand:** machine desliga; **sessão continua no Postgres/volume** — confirma o modelo “fica logado mesmo on-demand”.

---

### 11.3 Máx. 2 bancos Playwright por vez (menos lag)

**Objetivo:** `MAX_BROWSER_WORKERS=2` **e** o orquestrador **contar tarefas em voo**, não só quantas acorda neste tick.

**Tarefas:**

| # | Tarefa | Arquivos |
|---|---|---|
| 3.1 | Default config `MAX_BROWSER_WORKERS=2` (env + `fly.toml` / secrets) | `config.py`, `fly.toml` |
| 3.2 | Em `acordar_workers`: `em_voo = count(processando|reservada|acordando_worker)` playwright; `livres = max(0, teto - em_voo)`; só acordar até `livres` | `orquestrador.py` |
| 3.3 | Tarefas que não couberem permanecem `recebida` (não “sumir”) | já parcial |
| 3.4 | `FLY_START_BURST=2` alinhado | env |
| 3.5 | Teste: 4 tarefas pendentes + 0 em voo → acorda 2; com 2 em voo → acorda 0 | `test_workers_ondemand.py` |
| 3.6 | Deploy orquestrador + workers; smoke multi-banco 4 bancos → ver 2+2 na timeline | Fly |

**Aceite:** sim com 4 bancos mostra no máximo 2 `browser_iniciando` sobrepostos; os outros começam depois que algum termina; taxa de `timeout_driver` cai vs baseline 4-wide.

**Tempo esperado multi-banco (4 bancos):** ~2 “ondas” × ~2–4 min ≈ **4–8 min** (melhor que 4 estourando timeout).

---

### 11.4 Ordem de PRs / commits sugerida

| PR | Escopo | Deploy |
|---|---|---|
| **PR1** | 11.1 Login padronizado + eventos + testes | Motor + workers |
| **PR2** | 11.3 Teto 2 + contagem em voo | Motor (orquestrador) + env |
| **PR3** | 11.2 Persistência storage_state | Motor + migration + workers |

(PR2 pode ir antes de PR3 se quiser alívio rápido de lag; PR1 evita confusão de “login” na timeline.)

---

### 11.5 Critérios de pronto (definição de done)

- [ ] Timeline distingue `login_pulado` vs `login_confirmado`  
- [ ] Santander/Fontecred/Bradesco/Pan seguem o mesmo contrato de login  
- [ ] No máx. 2 workers Playwright ativos no cluster  
- [ ] Sessão sobrevive a stop on-demand (teste: stop machine → start → sem login frio se cookie válido)  
- [ ] Suite de testes do Motor verde  
- [ ] Handoff/`contexto-compacto` atualizado com o novo padrão  

---

## Apêndice A — Glossário rápido

| Termo | Significado |
|---|---|
| **Egress** | IP com que o Fly “aparece” na internet ao acessar o portal |
| **reCAPTCHA v3** | Score invisível; baixo = erro de verificação / bloqueio |
| **storage_state** | JSON Playwright (cookies etc.) para reabrir logado |
| **Sticky proxy** | Mesmo IP residencial durante o job |
| **Fan-out** | 1 simulação pai → 1 tarefa por banco |
| **timeout_driver** | Motor matou o browser ao estourar `MOTOR_DRIVER_TIMEOUT_SECONDS` |

## Apêndice B — Comandos úteis (ops)

```powershell
# Machines do motor
fly machines list -a motor2037

# Logs
fly logs -a motor2037

# Health
# GET /health/ready no motor2037
```

Portal: simulação manual → marcar **um** banco para teste controlado.

---

*Documento gerado para alinhar produto, ops e engenharia. Atualizar a §10 quando houver decisão.*
