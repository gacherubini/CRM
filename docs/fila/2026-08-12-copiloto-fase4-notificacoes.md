# Copiloto de Vendas — Fase 4: notificações no shell e alerta de preço fora da faixa

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tirar o alerta proativo de dentro da tela do Copiloto e colocá-lo onde o lojista está — um sino no topo do shell, visível de Vendas, Estoque ou de onde ele estiver — e acrescentar a 7ª regra: veículo com preço fora da faixa da FIPE.

**Architecture:** Nada de motor novo. A Fase 1 já construiu o motor proativo completo — tabela `copiloto_sinal`, seis regras determinísticas, worker, dedupe, cooldown e resolução automática — e `CopilotoSinal` já é, campo a campo, um registro de notificação (`severidade`, `titulo`, `detalhe`, `acao_sugerida_json`, `estado` em `novo|visto|dispensado|resolvido`). O que falta é **superfície**: hoje `contar_sinais_novos()` é chamado só dentro de `copiloto_home` e a contagem morre ali. Esta fase injeta a contagem no contexto do shell (`template_extras`), desenha o sino e o painel, e transforma "novo tipo de notificação" em "nova regra" — que o motor já sabe processar.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, Jinja2 + JS vanilla, pytest.

**Pré-requisito:** Fase 1 implementada e verde (motor de sinais). As Tasks 1–3 e 5 **não** dependem da Fase 3. A Task 4 depende do `FipeClient` da Fase 3 e só pode ser executada depois dela.

**Ordem em relação à Fase 3 (duas colisões conhecidas, resolvidas por ordem — não por conteúdo):**
1. **Migration.** A Fase 3 cria `0021_copiloto_acoes`; esta fase cria a sua própria (`CopilotoSinalVisto`, Task 0). Se as duas assumirem `0020_copiloto_conversa_turno` como pai — o que acontece se rodarem em paralelo —, nasce head dupla do Alembic. A Task 0 já manda conferir `alembic heads` em vez de assumir número (ver Migration, abaixo); o reforço aqui é que essa conferência só faz sentido **depois** de a Fase 3 estar mergeada, não antes. Uma migration vira pai da outra; elas não podem nascer irmãs.
2. **`app/web/loja_copiloto.py`** é modificado pela Fase 3 (rotas de ação e desfazer), por esta fase (rotas de notificação, Task 3) e possivelmente pela Fase 5. Não há incompatibilidade de conteúdo entre as três — só exige que as fases entrem em ordem: **3 → 4 → 5 → 6**.

**Decisões do dono (2026-08-12):**
- Notificação **só dentro do painel**. Nada de WhatsApp nem e-mail nesta fase — sem custo de envio, sem regra de horário, sem opt-out para desenhar.
- Superfície é **sino no cabeçalho, visível de qualquer tela**, não uma página escondida no menu.

## Global Constraints

- **O motor não muda.** Regra nova é função pura em `sinais.py` que devolve `SinalCandidato`; o worker, o dedupe e o cooldown da Fase 1 cuidam do resto. Se uma task quiser mexer em `sinais_store.py`, algo está errado no desenho.
- **`template_extras()` roda em toda renderização do shell.** Uma query de contagem sem cache ali é imposto em cada page view do produto inteiro. A contagem tem de ser cacheada (reusar `CacheTTL` de `app/loja/copiloto/cache.py`) e tem de degradar para "sem badge" se a query falhar — o sino nunca pode derrubar uma página que não é dele.
- **Gate-duplo vale para o sino, com a MESMA constante que governa a seção.** Ele só existe quando `REVY_LOJA_SHELL_ENABLED` + `REVY_LOJA_COPILOTO_ENABLED` + entitlement `Module.COPILOTO` da loja + papel em `PAPEIS_GESTAO_COPILOTO` (`app/loja/copiloto/tipos.py:18` — dono, gerente e admin_plataforma; **não** `ROLES_GESTAO` de `app/loja/types.py:32`, que não inclui admin_plataforma). Esconder no template não é autorização: a rota do painel carrega o gate inteiro, igual às rotas da Fase 2. **Quem vê o sino é exatamente quem `_pode()` (`app/web/loja_copiloto.py:81`) deixa entrar na seção — uma constante só.** Duas definições de "quem tem acesso ao Copiloto" é como o sino e a página passam a discordar: um `admin_plataforma` abriria a página inteira e não veria aviso nenhum — sintoma que aparece como "notificação fantasma" ou "não recebo aviso", caro de diagnosticar porque a causa fica numa constante errada, não numa lógica quebrada. Isso não muda quem tem acesso na prática além disso: vendedor continua fora.
- **Copiloto continua só de gestão** (decisão do dono, 2026-08-12: "só pra gestão por enquanto"). O "por enquanto" é literal e a Task 5 prepara o terreno: o catálogo guarda a audiência de cada regra, hoje toda `gestao`. No dia em que o vendedor entrar, muda-se o catálogo — não o gate, não as rotas, não o worker. **Regra sem audiência declarada é tratada como `gestao` (fail-closed), nunca como pública**, e um teste trava isso. O motivo de fail-closed importa: `estoque_parado` mostra capital preso, `margem_incompleta` é sobre custo e `meta_em_risco` mostra meta — o ledger da Fase 1 já tinha parqueado esse vazamento como adormecido justamente porque a seção era só de gestão. Um default público reabriria isso em silêncio.
- **Visto é por pessoa; dispensar é da loja.** `copiloto_sinal` não tem `usuario_id`, e por isso hoje "visto" é coletivo — o dono quer o contrário (decisão de 2026-08-12). Isso exige tabela nova (Task 0). A assimetria é proposital: **visto** significa "eu li", então é de quem leu; **dispensar** significa "esse alerta não procede", que é um juízo sobre o alerta em si — se fosse pessoal, cada gestor teria de dispensar separadamente o mesmo alerta falso. A tela precisa dizer isso em texto, senão o comportamento parece inconsistente.
- **Nunca inventar número.** O alerta de FIPE só existe quando a FIPE respondeu. FIPE fora → nenhum sinal, e o alerta de tempo parado (que não depende dela) continua. Nada de "provavelmente acima do mercado".
- **Design system.** Vale a constraint escrita no plano F2: folha real em `app/static/css/app.css`, paleta em `app/static/css/revy-tokens.css`, toda cor/raio/fonte em `var(--token)`, classe nova escopada, reusar `.button`/`.sr-only`/`.chip-list` antes de inventar. O sino aparece em **todas** as telas do shell — um erro de contraste aqui aparece no produto inteiro.
- **Sem PII.** Título e detalhe do sinal são agregados e referências de entidade, nunca nome ou telefone de cliente.
- **Comandos** (de `portal-gestao/`): `python -m pytest -q` · `python -m alembic upgrade head`
- Commit por task; `git diff --check` + `git status --short` no fim.

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `app/loja/copiloto/notificacoes.py` | Contagem cacheada + catálogo de tipos (rótulo e ícone por regra). |
| `app/web/loja_shell.py` | **(modificado)** `template_extras` passa a injetar `copiloto_nao_vistos`. |
| `app/templates/base.html` | **(modificado)** sino e painel na `.topbar-actions`. |
| `app/static/css/app.css` | **(modificado)** bloco `.notif-*`, só com tokens. |
| `app/web/loja_copiloto.py` | **(modificado)** rotas `notificacoes.json`, `notificacoes/{id}/visto`, `notificacoes/{id}/dispensar`. |
| `app/loja/copiloto/sinais.py` | **(modificado)** `regra_preco_fora_da_faixa` (Task 4, depende da F3). |
| `app/copiloto_sinais_job.py` | **(modificado)** passa a FIPE ao avaliar a loja (Task 4). |

---

### Task 0: `copiloto_sinal_visto` — visto por pessoa

**Files:**
- Modify: `portal-gestao/app/models.py`
- Create: `portal-gestao/alembic/versions/00XX_copiloto_sinal_visto.py`
- Modify: `portal-gestao/app/loja/copiloto/sinais_store.py`
- Test: `portal-gestao/tests/test_copiloto_sinais_store.py`

**Interfaces:**
- Produz: `CopilotoSinalVisto` (`sinal_id`, `usuario_id`, `visto_em`), único por par;
- `marcar_visto(db, loja_slug, sinal_id, usuario_id) -> bool` **muda de assinatura** (ganha `usuario_id`);
- `contar_sinais_novos(db, loja_slug, usuario_id) -> int` **muda de assinatura**;
- `dispensar(db, loja_slug, sinal_id)` **não muda** — dispensar segue sendo da loja.

**Por que tabela e não coluna:** "visto" é uma relação N-para-N entre sinal e pessoa. Coluna em `copiloto_sinal` só conseguiria guardar um leitor.

**Atenção às assinaturas que mudam:** `contar_sinais_novos` e `marcar_visto` já têm chamadores na Fase 1/2 (`app/web/loja_copiloto.py`). Achar todos e atualizar; não deixar sobrecarga com `usuario_id` opcional, porque um default silencioso aqui vira "contagem de outra pessoa" sem ninguém perceber.

**Migration:** `down_revision` é a head vigente no momento da execução — conferir com `alembic heads`, não assumir número.

- [ ] **Step 1: Escrever o teste que falha** — dois usuários da mesma loja: A marca visto, a contagem de A cai e a de **B não**; dispensar sumiu para os dois; marcar visto duas vezes não duplica linha; visto de sinal de outra loja não é aceito.
- [ ] **Step 2: Rodar e ver falhar**
- [ ] **Step 3: Implementar**
- [ ] **Step 4: Rodar e ver passar** — mais `alembic upgrade head` e suíte inteira, porque as assinaturas mudaram.
- [ ] **Step 5: Commit**

---

### Task 1: Contagem no contexto do shell, cacheada e à prova de falha

**Files:**
- Create: `portal-gestao/app/loja/copiloto/notificacoes.py`
- Modify: `portal-gestao/app/web/loja_shell.py`
- Test: `portal-gestao/tests/test_copiloto_notificacoes_shell.py`

**Interfaces:**
- Consome: `contar_sinais_novos` (Task 0, já com `usuario_id`), `CacheTTL` (`cache.py`), `Module`, `PAPEIS_GESTAO_COPILOTO` (`app/loja/copiloto/tipos.py:18` — a mesma constante que `_pode()` usa para a seção inteira).
- Produz: `contar_nao_vistos(db, loja_slug, usuario_id) -> int` (cacheado, TTL curto); `invalidar_contagem(loja_slug, usuario_id=None)`; `template_extras` passa a devolver `copiloto_nao_vistos: int | None`.

**A chave do cache inclui o usuário**, porque a contagem agora é pessoal (Task 0). Cachear só por loja devolveria a contagem do sócio — e `invalidar_contagem(loja_slug)` sem usuário precisa limpar todas as entradas daquela loja, senão o worker criar um sinal novo não reflete para ninguém até o TTL virar.

**Por que cache aqui é obrigatório e não otimização:** `template_extras` (`loja_shell.py:91`) roda em **toda** renderização do shell. Uma contagem sem cache adiciona uma query por page view em Vendas, Estoque, Atendimento — telas que não têm nada a ver com o Copiloto. TTL curto (30–60s) é suficiente: um alerta que aparece um minuto depois não muda a vida de ninguém; uma query a mais em cada tela, sim.

**Degradação:** se a contagem levantar, `template_extras` devolve `copiloto_nao_vistos = None` e a página renderiza **sem badge**. O sino é acessório; ele nunca pode ser o motivo de um 500 na tela de Vendas. Logar a exceção em `warning` — não engolir em silêncio (foi achado I2 da revisão final da F1).

**Gate:** devolver `None` — não `0` — quando o shell está desligado, quando o módulo não está no entitlement da loja, ou quando o papel não está em `PAPEIS_GESTAO_COPILOTO`. `None` significa "não tem sino"; `0` significa "tem sino, zerado". A distinção importa para o template.

- [ ] **Step 1: Escrever o teste que falha**

Cobrir: (a) gestor de loja com entitlement vê a contagem real; (b) vendedor recebe `None`; (c) loja sem o módulo recebe `None` mesmo com papel certo; (d) uma exceção na contagem devolve `None` e **não** propaga; (e) a segunda chamada dentro do TTL não vai ao banco (contar queries ou espionar a função); (f) `invalidar_contagem` força releitura.

- [ ] **Step 2: Rodar e ver falhar**
- [ ] **Step 3: Implementar**
- [ ] **Step 4: Rodar e ver passar** — e rodar a suíte inteira, porque `template_extras` é caminho comum de todo o shell.
- [ ] **Step 5: Commit**

---

### Task 2: O sino e o painel no cabeçalho

**Files:**
- Modify: `portal-gestao/app/templates/base.html`
- Modify: `portal-gestao/app/static/css/app.css`
- Test: `portal-gestao/tests/test_copiloto_notificacoes_shell.py`

**Onde exatamente:** dentro de `.topbar-actions` (`base.html:160`), antes dos botões de ação existentes. O sino é um `<button>` com contador; clicar abre um painel ancorado. Fechado por padrão; fecha no `Esc` e no clique fora.

**O que o painel mostra por sinal:** severidade, título, detalhe, quando surgiu, e — quando houver — o link da ação sugerida (`acao_sugerida_json`). Mais dois botões: **Marcar como visto** e **Dispensar**.

**A frase que precisa estar na tela:** o painel diz, em texto pequeno, que os alertas são **da loja**, que marcar como visto vale **só para quem marcou** (Task 0 — tabela `copiloto_sinal_visto`) e que dispensar tira o alerta **para todo mundo**. Sem isso, dois sócios discutem sobre alerta que "sumiu sozinho" quando na verdade só um dos dois marcou como visto.

**Estado vazio honesto:** sem alerta, o painel diz que não há nada a tratar agora — não inventa conteúdo nem some do cabeçalho.

**Acessibilidade:** o botão tem `aria-label` com a contagem em texto ("3 notificações não vistas"), o painel usa `aria-live="polite"`, e o badge numérico não pode ser o único portador da informação.

**Design:** só tokens. Severidade usa `--danger`/`--warn`/`--ok`, nunca hex. Verificar nos dois temas — `revy-tokens.css` tem bloco `[data-theme="dark"]`, e este componente aparece em toda tela do produto.

- [ ] **Step 1: Escrever o teste que falha** — renderização: sino presente para gestor com entitlement; ausente para vendedor; ausente para loja sem o módulo; badge não aparece quando a contagem é `None`; a frase sobre "alerta da loja" está no HTML.
- [ ] **Step 2: Rodar e ver falhar**
- [ ] **Step 3: Implementar**
- [ ] **Step 4: Rodar e ver passar** — conferir `grep -nE "#[0-9a-fA-F]{3,6}|rgba?\(" ` no bloco novo do CSS: tem de voltar vazio.
- [ ] **Step 5: Commit**

---

### Task 3: Rotas do painel — listar, marcar visto, dispensar

**Files:**
- Modify: `portal-gestao/app/web/loja_copiloto.py`
- Test: `portal-gestao/tests/test_copiloto_notificacoes_rotas.py`

**Interfaces:**
- `GET /app/loja/copiloto/notificacoes.json` → `{itens: [...], nao_vistos: n}`
- `POST /app/loja/copiloto/notificacoes/{sinal_id}/visto`
- `POST /app/loja/copiloto/notificacoes/{sinal_id}/dispensar`

**Reusar, não reescrever:** `listar_sinais_abertos`, `marcar_visto(db, loja_slug, sinal_id, usuario_id)` (assinatura já com `usuario_id` — mudou na Task 0) e `dispensar(db, loja_slug, sinal_id)` já existem em `sinais_store.py` e já recebem `loja_slug` obrigatório. Nenhuma função nova de domínio nesta task.

**Segurança — o ponto onde este projeto já sangrou duas vezes:** as três rotas carregam o gate completo, incluindo `check_module_access(request, usuario, db, Module.COPILOTO)` **server-side**. `loja_slug` vem da sessão, nunca do corpo ou da query. `sinal_id` é entrada do cliente e nunca autoriza nada sozinho — o escopo por loja é feito no `WHERE`, que as funções da Fase 1 já fazem. Os dois POST exigem CSRF, com teste negativo para **cada um** (na Fase 2 faltou o teste de um dos POST e passou batido até a revisão final).

**Invalidar o cache:** todo POST que muda estado chama `invalidar_contagem(loja_slug)` da Task 1 — senão o badge fica teimando por até um TTL depois de o lojista limpar tudo.

- [ ] **Step 1: Escrever o teste que falha** — incluindo: sinal de outra loja devolve 404/não encontrado; POST sem CSRF é recusado nas duas rotas e **não** muda estado no banco; entitlement ausente bloqueia as três rotas mesmo com papel certo; o badge zera após dispensar.
- [ ] **Step 2: Rodar e ver falhar**
- [ ] **Step 3: Implementar**
- [ ] **Step 4: Rodar e ver passar**
- [ ] **Step 5: Commit**

---

### Task 4: 7ª regra — preço fora da faixa da FIPE

> **Depende da Fase 3.** Não executar antes de `app/clients/fipe.py` e `consultar_fipe_do_veiculo` existirem e estarem verdes.

**Files:**
- Modify: `portal-gestao/app/loja/copiloto/sinais.py`
- Modify: `portal-gestao/app/copiloto_sinais_job.py`
- Test: `portal-gestao/tests/test_copiloto_sinais.py`

**Interfaces:**
- Produz: `regra_preco_fora_da_faixa(veiculos_com_fipe, *, folga_alta, folga_base, dias_parado_min) -> list[SinalCandidato]`

**Assinatura de função pura, como as outras seis:** a regra **não** chama a FIPE. Ela recebe uma lista já resolvida de `(veiculo, valor_fipe)` e decide. Quem busca é o worker. Isso mantém a regra testável sem rede, igual às seis da Fase 1.

**Quando o sinal existe — dois gatilhos, porque acima da FIPE é normal** (decisão do dono, 2026-08-12: *"na FIPE é normal estar acima"*). Alertar em qualquer centavo acima seria ruído em cima do estoque inteiro. Então:

1. **Muito acima, sozinho:** preço ≥ FIPE × (1 + `folga_alta`). Aqui o preço destoa o suficiente para valer aviso mesmo em veículo recém-cadastrado.
2. **Acima + encalhado:** preço ≥ FIPE × (1 + `folga_base`) **e** parado há mais de `dias_parado_min` dias. Sozinha, nenhuma das duas condições merece alerta; juntas, são a definição de dinheiro dormindo.

Severidade maior no caso 2 — preço alto em veículo que acabou de entrar é decisão comercial; preço alto em veículo parado há meses é capital preso.

**Os três valores vêm de env e ainda NÃO estão decididos** (`PORTAL_COPILOTO_FIPE_FOLGA_ALTA`, `PORTAL_COPILOTO_FIPE_FOLGA_BASE`, `PORTAL_COPILOTO_FIPE_DIAS_PARADO`). O dono quer calibrar com estoque real na mão, e é a decisão certa: limiar de preço é conhecimento de mercado, não de engenharia. Os defaults do código são ponto de partida para calibrar, **não** recomendação — escrever isso no comentário para ninguém tratá-los como verdade. Como saem de env, ajustar não exige deploy de código.

**Quando o sinal NÃO existe, e isto é metade da regra:**
- FIPE indisponível para aquele veículo → **nenhum sinal**. Não existe "provavelmente caro".
- Mais de um candidato no matching da FIPE → **nenhum sinal**. A Fase 3 é explícita: a FIPE nunca adivinha, e um sinal proativo é ainda pior lugar para adivinhar do que uma resposta de chat, porque ninguém perguntou nada.
- Preço **abaixo** da FIPE → nenhum sinal nesta fase. Pode ser estratégia de giro; alertar sobre isso seria opinar sobre a operação do dono.

**Custo, que é a razão de o worker precisar de teto:** a FIPE é API comunitária sem SLA. Consultar todo o estoque a cada ciclo é abuso e vai tomar rate limit. O worker consulta um teto por ciclo (config `PORTAL_COPILOTO_FIPE_POR_CICLO`, default 10), priorizando veículo parado há mais tempo, e apoia-se no cache de 6h da Fase 3. Sem isso, esta regra derruba a FIPE para todo mundo.

**`entidade_ref` é o id do veículo** — o dedupe e o cooldown da Fase 1 então funcionam sem mudança nenhuma no store.

- [ ] **Step 1: Escrever o teste que falha** — acima da tolerância vira sinal; dentro da tolerância não; FIPE indisponível não; matching ambíguo não; abaixo da FIPE não; severidade sobe quando também está parado; `entidade_ref` é o id do veículo.
- [ ] **Step 2: Rodar e ver falhar**
- [ ] **Step 3: Implementar** — regra pura primeiro, depois o teto e a priorização no worker.
- [ ] **Step 4: Rodar e ver passar**
- [ ] **Step 5: Commit**

---

### Task 5: Catálogo de tipos — para o próximo alerta ser configuração

**Files:**
- Modify: `portal-gestao/app/loja/copiloto/notificacoes.py`
- Test: `portal-gestao/tests/test_copiloto_notificacoes_shell.py`

**O problema que isto resolve:** hoje o rótulo de cada regra está espalhado. Quando entrar a 8ª regra, alguém vai ter de caçar template, painel e tela do Copiloto. Esta task cria um mapa único `regra -> (rótulo, ícone, severidade padrão)` e faz painel e tela lerem dele.

**A regra que um teste trava:** toda regra registrada em `sinais.py` tem entrada no catálogo, e uma regra sem entrada cai num rótulo genérico — **nunca** no nome cru da função. É a mesma disciplina que a Fase 2 aplicou aos rótulos de passo do chat (`copiloto.html`), e pelo mesmo motivo: nome de função vazando para a tela do lojista é vazamento de implementação.

- [ ] **Step 1: Escrever o teste que falha** — o teste itera as regras conhecidas e exige entrada no catálogo; uma regra fictícia desconhecida devolve o rótulo genérico e não o nome da função.
- [ ] **Step 2: Rodar e ver falhar**
- [ ] **Step 3: Implementar**
- [ ] **Step 4: Rodar e ver passar**
- [ ] **Step 5: Commit**

---

## Verificação antes de fechar a fase

- Suíte inteira verde a partir de `portal-gestao/`.
- Sino conferido nos **dois** temas (claro e escuro) — é componente de toda tela.
- `grep` no bloco CSS novo não acha `#`, `rgb(` nem `rgba(`.
- Com o módulo desligado no entitlement da loja: sino ausente **e** as três rotas respondendo 403/404 com acesso direto.
- Com a FIPE fora: nenhum sinal de preço, e os alertas das outras seis regras continuam aparecendo.
- `git diff --check` e `git status --short` limpos.

## O que esta fase deliberadamente não faz

- **Não notifica fora do painel.** Sem WhatsApp, sem e-mail. Decisão do dono em 2026-08-12; quando entrar, precisa de regra de frequência, janela de horário e opt-out — nada disso está desenhado aqui.
- **`copiloto_sinal.estado` continua da loja — só o "visto" virou por pessoa.** A Task 0 desta fase criou `copiloto_sinal_visto` (tabela nova, `sinal_id` + `usuario_id`) exatamente para tornar o **visto** individual, por decisão do dono (2026-08-12): cada gestor marca como visto por si, e o cache/badge do sino reflete só a leitura de quem está logado. **Dispensar** continua sendo da loja inteira — muda `estado` em `copiloto_sinal`, o mesmo campo que todo mundo lê, então um gestor dispensar vale para os demais. `copiloto_sinal` em si não ganhou `usuario_id`; a relação pessoa-sinal mora inteira na tabela nova.
- **Não alerta preço abaixo da FIPE.** Ver Task 4.
