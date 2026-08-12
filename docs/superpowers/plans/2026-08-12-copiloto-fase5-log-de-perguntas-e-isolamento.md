# Copiloto de Vendas — Fase 5: log de perguntas e isolamento no banco

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Duas coisas independentes que o dono pediu em 2026-08-12, ambas de infraestrutura e nenhuma de funcionalidade nova. **Parte A:** descobrir, com dado em vez de palpite, o que os donos perguntam e o Copiloto não sabe responder. **Parte B:** fazer o isolamento entre lojas parar de depender de o nosso código estar certo.

**As duas partes são independentes.** Podem ser executadas em qualquer ordem, ou uma sem a outra. Não há task da Parte B que dependa da Parte A.

**Pré-requisito:** Fase 2 implementada (é ela que grava `copiloto_turno`).

---

# Parte A — Log de perguntas sem resposta

**Por que agora, se o retorno é depois:** o relatório nasce vazio. Não há uso real ainda — a F2 não está mergeada e não há chave em produção. Ele é construído **antes** do go-live justamente para o dado acumular desde o primeiro dia; construir depois significa descobrir em três meses que não guardamos nada. A construção é agora, o retorno é depois, e essa assimetria é o motivo de existir.

**O dado já está gravado.** Cada pergunta é uma linha em `copiloto_turno` com `pergunta`, `resposta`, `erro_code`, `passos_json`, `tokens_entrada`, `tokens_saida`, `criado_em`, `concluido_em`. Nada de tabela nova nesta parte — o que falta é leitura.

## Audiência: decidida em 2026-08-12

**Quem lê:** a Revy, no **Revy Control** — o dono e os sócios-gestores. Propósito declarado: melhorar o Copiloto para todas as lojas.

Isso tem duas consequências que definem o desenho e não são negociáveis:

**1. Atravessa fronteira de produto.** O Control vive em `revy-trafego/app/web/control_ui.py`, produto separado com banco próprio; `copiloto_turno` está no `portal-gestao`. A regra da casa é explícita: *"Cada produto tem banco/migrations próprios. Não crie import Python entre produtos; integre por contrato HTTP/evento versionado."* Portanto o Control **não consulta a tabela** — o Portal expõe um endpoint e o Control consome.

**2. O contrato carrega a PERGUNTA, e o desenho tem de conter o risco.** Decisão do dono, revisada em 2026-08-12: o agregado não basta, porque o lojista não vai abrir uma tela de lacunas para reportar nada — para consertar o produto é preciso ler o que ele escreveu. Aceito. Mas a pergunta é texto livre e pode conter PII do cliente dele ("quanto o João Silva ainda me deve"), então o contrato é o mais estreito possível:

- **Só a `pergunta`. NUNCA a `resposta`.** A pergunta diz o que falta; a resposta contém o financeiro da loja — faturamento, margem, ranking de vendedor. Isso não ajuda a achar ferramenta faltando e é o dado mais sensível do turno. Um teste trava: o corpo da resposta do endpoint não pode conter nenhum campo `resposta` nem `texto_parcial`.
- **Só turnos classificados como lacuna** (`sem_ferramenta`, `fonte_vazia`, `morreu`). Conversa que deu certo não atravessa. Um teste trava isso também.
- **Sem identificador de usuário.** Interessa o que foi perguntado, não quem perguntou.
- **Acesso auditado** no Control, que já tem trilha.

Sob LGPD: o lojista é controlador do dado dos clientes dele e a Revy é operadora. Ler esse texto para desenvolver produto é finalidade que **precisa estar prevista nos termos do lojista** — item de contrato, não de código, e responsabilidade do dono. Registrado aqui porque o plano não pode fingir que a decisão é só técnica.

**A retenção (Task A3) passa a ser parte da proteção**, não higiene de banco: é ela que limita por quanto tempo esse texto existe.


## Global Constraints da Parte A

- **Nenhuma tabela nova, nenhuma migration.** Se uma task quiser criar tabela, o desenho está errado: o dado já está em `copiloto_turno`.
- **Escopo por loja continua valendo** em toda consulta interna do Portal. No endpoint de serviço, a loja é parâmetro explícito e auditável — é justamente a visão entre lojas que o Control precisa.
- **O relatório é leitura pura.** Não altera turno, não apaga, não marca nada.
- **Retenção esbarra aqui.** `copiloto_retencao_dias` está declarado desde a F2 e **nenhum job o aplica** — os turnos ficam para sempre. Um relatório que se apoia em histórico infinito é sintoma disso, não solução. A Task A3 trata.

### Task A1: Classificar por que um turno não respondeu

**Files:**
- Create: `portal-gestao/app/loja/copiloto/log_perguntas.py`
- Test: `portal-gestao/tests/test_copiloto_log_perguntas.py`

**Interfaces:**
- `classificar_turno(turno) -> str` devolvendo um de: `respondeu`, `morreu` (erro_code presente), `sem_ferramenta` (terminou pronto mas `passos_json` vazio), `fonte_vazia` (chamou ferramenta e ela voltou `vazio`/`indisponivel`), `cancelado`.
- `agrupar_lacunas(turnos) -> list[Lacuna]` com contagem por classe e, dentro de `sem_ferramenta`, por assunto.

**A classe que interessa é `sem_ferramenta`:** turno que terminou bem, sem chamar função nenhuma, é o modelo dizendo "não tenho como responder isso". É o sinal mais limpo de ferramenta faltando — melhor que `morreu`, que quase sempre é infraestrutura (deadline, provedor), não lacuna de produto.

**O que NÃO tentar:** classificar "respondeu mal". Exige julgamento e vai gerar número que ninguém confia. As quatro classes mecânicas bastam para priorizar.

- [ ] **Step 1: Escrever o teste que falha** — uma amostra com um turno de cada classe, incluindo `pronto` com `passos_json` vazio e `pronto` com ferramenta que voltou `indisponivel`.
- [ ] **Step 2: Rodar e ver falhar**
- [ ] **Step 3: Implementar** — funções puras sobre o objeto turno, sem I/O.
- [ ] **Step 4: Rodar e ver passar**
- [ ] **Step 5: Commit**

---

### Task A2: Endpoint agregado no Portal

**Files:**
- Modify: `portal-gestao/app/web/loja_copiloto.py` (ou rota de serviço própria — decidir)
- Test: `portal-gestao/tests/test_copiloto_log_perguntas_rota.py`

**Contrato:** `GET /api/copiloto/lacunas?inicio=&fim=` devolvendo, **por loja**: contagem por classe (`morreu`, `sem_ferramenta`, `fonte_vazia`, `cancelado`) e, para os turnos classificados como lacuna, a `pergunta` com a classe e a data.

**O que o corpo NUNCA pode conter, cada um travado por teste:** `resposta`, `texto_parcial`, identificador de usuário, e qualquer turno cuja classe seja `respondeu`. Estes três testes são a proteção inteira — se algum for afrouxado depois, a proteção some junto, então eles precisam de comentário dizendo por que existem.

**Autenticação:** é chamada de serviço (Control → Portal), não sessão de lojista. Seguir o padrão que o Portal já usa para os clients internos — conferir `app/clients/` e a credencial de serviço existente, **não** inventar esquema novo.

- [ ] **Step 1: Escrever o teste que falha** — inclui: o corpo nunca contém `resposta` nem `texto_parcial`; turno da classe `respondeu` não aparece; sem identificador de usuário; loja não solicitada não aparece; sem credencial de serviço é recusado.
- [ ] **Step 2: Rodar e ver falhar**
- [ ] **Step 3: Implementar**
- [ ] **Step 4: Rodar e ver passar**
- [ ] **Step 5: Commit**

---

### Task A2b: Consumo no Revy Control

**Files:**
- Create: client HTTP no `revy-trafego` para o endpoint do Portal
- Modify: `revy-trafego/app/web/control_ui.py` (tela)
- Test: no `revy-trafego`

**Auditoria:** registrar quem leu, usando a trilha que o Control já tem. É leitura de texto escrito pelo lojista — precisa deixar rastro.

**Regra que não pode ser quebrada:** nada de import Python entre produtos. O Control fala com o Portal por HTTP, com timeout e degradação — Portal fora deixa a tela dizer indisponível, e **nunca** zero, que é a disciplina que o produto inteiro já segue.

**Papel:** só os papéis de Control (dono e sócios-gestores da Revy). Não é tela de lojista.

- [ ] **Step 1: Escrever o teste que falha** — client com transporte falso; Portal fora → indisponível, não zero.
- [ ] **Step 2: Rodar e ver falhar**
- [ ] **Step 3: Implementar**
- [ ] **Step 4: Rodar e ver passar** — suíte do `revy-trafego`, a partir da pasta dele.
- [ ] **Step 5: Commit**

---

### Task A3: Expurgo por retenção

**Files:**
- Create/Modify: job de expurgo (avaliar reuso de `app/copiloto_sinais_job.py` como padrão de worker)
- Test: `portal-gestao/tests/test_copiloto_retencao.py`

**Por que entra aqui:** `settings.copiloto_retencao_dias` (default 90) existe desde a F2 e **ninguém o consome** — conversa e turno ficam no banco indefinidamente. É dívida nomeada na revisão final da F2. O relatório da Parte A torna isso pior, porque passa a haver motivo para olhar histórico antigo e deixá-lo crescer.

**Apagar o quê:** conversa e turnos mais velhos que a retenção. **Cuidado:** apagar o turno apaga a matéria-prima do relatório. Decidir e documentar — provavelmente guardar o agregado antes de apagar o texto, que resolve retenção e relatório de uma vez.

**Fail-safe:** expurgo é destrutivo. Rodar em lote pequeno, logar contagem, e nunca apagar sem filtro de loja e de data.

- [ ] **Step 1: Escrever o teste que falha** — turno dentro da janela sobrevive; fora da janela some; o agregado sobrevive ao expurgo do texto.
- [ ] **Step 2: Rodar e ver falhar**
- [ ] **Step 3: Implementar**
- [ ] **Step 4: Rodar e ver passar** — mais suíte inteira.
- [ ] **Step 5: Commit**

---

# Parte B — Isolamento no banco (RLS)

**O que muda:** hoje o isolamento entre lojas depende de **28 pontos** com `loja_slug` no modelo do Portal filtrarem corretamente. A revisão final da F2 rastreou o caminho do Copiloto e o achou hermético — mas isso é uma verificação de hoje, não uma garantia de amanhã. Com Row-Level Security, o banco recusa linha de outra loja mesmo que um `WHERE` seja esquecido: vira **um** lugar para acertar em vez de 28.

## Global Constraints da Parte B

- **Isso não substitui os filtros existentes.** É defesa em profundidade. Nenhuma task pode remover um `WHERE loja_slug` "porque agora tem RLS" — se o RLS for desligado por engano, o produto volta a vazar.
- **RLS é Postgres. Os testes rodam SQLite em memória** (`tests/conftest.py:7`). Consequência que precisa estar na cara de todo mundo: **a suíte atual não consegue provar que o RLS funciona.** Ou a fase entrega um teste com Postgres de verdade, ou entrega uma proteção que ninguém verificou — e o segundo caso é pior que não ter, porque gera confiança falsa.
- **A política é fail-closed.** Sem `app.loja_slug` definido, a política devolve **zero linhas**, nunca todas. Um default permissivo aqui transforma a proteção no seu oposto.
- **Escopo do papel:** somente-leitura. Escrita continua pelo caminho normal da aplicação — o Copiloto lê; quem escreve são as rotas de venda/estoque, que não fazem parte desta fase.

### Task B1: Papel somente-leitura e política RLS

**Files:**
- Create: migration/DDL das políticas (ou passo de ops documentado — decidir e justificar)
- Modify: `portal-gestao/app/db.py` (segunda engine/sessão para o caminho do Copiloto)
- Test: teste com Postgres real (ver constraint acima)

**Decisão a tomar e documentar:** política RLS via Alembic ou via passo de ops. Alembic mantém tudo versionado, mas exige que a migration rode com papel que possa criar política. Passo de ops é mais simples e mais fácil de esquecer. Escolher explicitamente.

**Como a loja entra na conexão:** `SET LOCAL app.loja_slug = ...` no início da transação, com o valor vindo **da sessão autenticada** — nunca de parâmetro de request. `SET LOCAL` (e não `SET`) porque precisa morrer com a transação; senão uma conexão reciclada do pool carrega a loja anterior, que é exatamente o vazamento que estamos evitando.

**Tabelas cobertas:** as que as consultas do Copiloto leem. Levantar a partir de `app/loja/copiloto/consultas_*.py`, não por chute.

- [ ] **Step 1: Escrever o teste que falha** — contra Postgres: com `app.loja_slug` da loja A, um `SELECT` sem `WHERE` não traz linha da loja B; **sem** a variável definida, não traz nada.
- [ ] **Step 2: Rodar e ver falhar**
- [ ] **Step 3: Implementar**
- [ ] **Step 4: Rodar e ver passar**
- [ ] **Step 5: Commit**

---

### Task B2: Ligar o caminho do Copiloto na sessão escopada

**Files:**
- Modify: `portal-gestao/app/web/loja_copiloto.py`, `portal-gestao/app/copiloto_turnos_job.py`
- Test: `portal-gestao/tests/test_copiloto_sessao_escopada.py`

**A costura já existe:** o worker recebe `db_factory` injetado (`copiloto_turnos_job.py:190`), então dá para passar uma fábrica que abre sessão escopada sem reescrever o worker. As rotas usam a dependência de sessão do app — mudar ali.

**O ponto de atenção:** o worker processa turnos de **várias** lojas no mesmo ciclo. Cada turno tem de rodar na sua própria transação com o seu próprio `SET LOCAL`. Reaproveitar uma transação entre turnos de lojas diferentes é o vazamento clássico deste desenho.

- [ ] **Step 1: Escrever o teste que falha** — dois turnos de lojas diferentes no mesmo ciclo; cada um só enxerga a sua loja.
- [ ] **Step 2: Rodar e ver falhar**
- [ ] **Step 3: Implementar**
- [ ] **Step 4: Rodar e ver passar** — mais suíte inteira.
- [ ] **Step 5: Commit**

---

## Verificação antes de fechar a fase

- Suíte inteira verde, e o teste de RLS rodando contra Postgres de verdade (não SQLite).
- Nenhum `WHERE loja_slug` removido — conferir no diff.
- Expurgo testado com janela curta, contagem no log, sem apagar fora do filtro.
- `git diff --check` e `git status --short` limpos.

## O que esta fase deliberadamente não faz

- **Não deixa o modelo escrever consulta.** RLS é pré-requisito para isso ficar seguro, não autorização para fazê-lo. Consulta livre continua fora de escopo, e o problema que sobra (definição errada — contar venda cancelada como faturamento) não é resolvido por isolamento nenhum.
- **Não separa o banco por loja.** Avaliado em 2026-08-12 e recusado: 28 pontos com `loja_slug`, agregações do Control entre lojas, migration a rodar N vezes e ~120ms de RTT por query já registrados no `deploy/fly/3vm/README.md`. RLS entrega o mesmo isolamento para este caso a uma fração do custo.
- **Não constrói o construtor tipado de consultas.** Depende do que a Parte A revelar.
