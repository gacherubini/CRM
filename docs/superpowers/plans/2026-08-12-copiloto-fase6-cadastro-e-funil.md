# Copiloto de Vendas — Fase 6: ferramentas de cadastro e funil

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) ou superpowers:executing-plans para implementar task a task. Os passos usam checkbox (`- [ ]`).

**Goal:** Duas consultas que o dono pediu em 2026-08-12 e que hoje o Copiloto não responde, embora o dado já exista no produto: **quais veículos estão com cadastro incompleto** (sem foto, sem preço, sem campo obrigatório) e **como está o funil** — quantos leads entraram, quantos viraram atendimento, quantos viraram venda.

**Architecture:** Nada de motor novo, nada de tabela nova. São duas ferramentas no registro MCP-nativo da Fase 2 (`app/loja/copiloto/tools.py`), consumindo dado que já existe: o Estoque para cadastro, e o `funil_periodo` de `app/financeiro_calc.py` para conversão. O registro foi desenhado exatamente para isto — "acrescentar fonte vira configuração, não reescrita".

**Pré-requisito:** Fase 2 implementada (registro de ferramentas e runner).

**Fora de escopo, decidido em 2026-08-12:** simulação de financiamento. Foi avaliada e **retirada pelo dono**. O motivo técnico está registrado abaixo porque a tentação vai voltar.

> **Por que a simulação saiu.** A simulação real exige **CPF, data de nascimento e celular** do cliente (`app/web/simulacoes.py:129-152`), e a Fase 2 tem constraint global "Sem PII no prompt". CPF como parâmetro de ferramenta entra no contexto do modelo e é enviado ao provedor — hoje um terceiro. Existiria desenho seguro (o modelo passa `lead_id`, o servidor resolve o CPF e chama o Motor, e o CPF nunca toca o modelo), mas ele só simula para lead já cadastrado, e a simulação é RPA com Playwright que ultrapassa o deadline de 45s do turno — precisaria virar job assíncrono próprio. Custo alto para ganho incerto: **fora da v1**.

## Global Constraints

- **O LLM nunca produz número.** Vale integralmente: toda cifra vem do retorno tipado, e ambas as ferramentas devolvem `Cobertura` quando o dado for parcial.
- **`loja_slug` e papel nunca entram no schema.** Identidade vem do `CopilotoContexto`. Um teste da Fase 2 já trava isso para o registro inteiro — as ferramentas novas caem automaticamente sob ele, e é preciso conferir que continuam passando.
- **Fonte fora → `indisponivel`, nunca zero.** `cadastro_incompleto` depende do Estoque por HTTP. Estoque fora não é "zero veículos incompletos" — é "não sei agora". Mesmo tratamento que `estoque_parado` já dá.
- **Escopo de loja fail-closed no Estoque:** reusar `garantir_escopo_loja` como `consultas_estoque.py` já faz. Se o Estoque responder por outra loja, aborta.
- **Saída serializável em JSON.** O registro tem teste que percorre todas as ferramentas e faz `json.dumps` do retorno — cuidado com `Decimal` e `date`, que foi exatamente o defeito encontrado em `roi_canais` na Fase 2.
- **Design system**, se alguma tela mudar: tokens de `revy-tokens.css`, folha em `app/static/css/app.css`, nada de cor na mão.
- **Comandos** (de `portal-gestao/`): `python -m pytest -q`
- Commit por task; `git diff --check` + `git status --short` no fim.

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `app/loja/copiloto/consultas_cadastro.py` | `cadastro_incompleto` — o que falta para o veículo ficar publicável. |
| `app/loja/copiloto/consultas_funil.py` | `funil_resumo` — leads, atendimento, venda e conversão do período. |
| `app/loja/copiloto/tools.py` | **(modificado)** as duas ferramentas entram no `registro_padrao()`. |
| `app/loja/copiloto/prompt.py` | nada a fazer — o catálogo é gerado do registro. |

---

### Task 1: `cadastro_incompleto`

**Files:**
- Create: `portal-gestao/app/loja/copiloto/consultas_cadastro.py`
- Test: `portal-gestao/tests/test_copiloto_consultas_cadastro.py`

**Interfaces:**
- Consome: `EstoqueClient` (duck-typed `.listar`, `.obter_loja`), `CopilotoContexto`, `Cobertura`.
- Produz: `cadastro_incompleto(estoque, ctx, *, limite=20) -> CadastroIncompleto` com `.to_dict()`.

**O que conta como incompleto:** derivar do que a `estoque-api` exige para publicar, **não de uma lista inventada aqui**. Ler a validação real da `estoque-api` antes de escrever e espelhá-la; se ela mudar um dia, o Copiloto passa a mentir sobre o que falta. Documentar no módulo de onde a lista veio.

**Já existe uma regra de alerta parecida** — `regra_cadastro_incompleto` em `sinais.py`, da Fase 1. **Não duplicar a lógica:** ou a ferramenta reusa o mesmo critério, ou fica explícito por que diverge. Duas definições de "incompleto" no mesmo produto é como o painel e o chat passam a discordar.

**Saída:** total de incompletos, lista até o limite com id, descrição e **o que falta em cada um** — o valor está aí, não no número. Mais `Cobertura` quando o Estoque devolver página parcial.

- [ ] **Step 1: Escrever o teste que falha** — veículo completo não aparece; veículo sem foto aparece com o motivo; Estoque fora vira `indisponivel` (não zero); escopo de outra loja aborta; saída serializa em JSON.
- [ ] **Step 2: Rodar e ver falhar**
- [ ] **Step 3: Implementar**
- [ ] **Step 4: Rodar e ver passar**
- [ ] **Step 5: Commit**

---

### Task 2: `funil_resumo`

**Files:**
- Create: `portal-gestao/app/loja/copiloto/consultas_funil.py`
- Test: `portal-gestao/tests/test_copiloto_consultas_funil.py`

**Interfaces:**
- Consome: `funil_periodo` (`app/financeiro_calc.py:195`), `CopilotoContexto`, `Cobertura`.
- Produz: `funil_resumo(db, ctx, *, inicio=None, fim=None) -> FunilResumo` com `.to_dict()`.

**Reusar `funil_periodo`, não reimplementar.** Ele já é a definição de funil do produto e alimenta a tela. Se o Copiloto calcular por conta, o chat e o painel vão divergir — e o dono vai acreditar no que o chat disse.

**Cobertura importa aqui mais que na média:** conversão depende de atribuição, e atribuição é justamente onde falta dado (a Fase 1 já tem `regra_atribuicao_baixa` por isso). Se parte dos leads não tem origem, o número de conversão vale sobre um subconjunto — e a regra 4 obriga o modelo a dizer isso. Devolver `Cobertura` com `com_dado`/`total` é o que torna essa frase possível.

**Comparação com período anterior**, como `vendas_resumo` já faz — "conversão de 12%" sozinho não diz se melhorou.

- [ ] **Step 1: Escrever o teste que falha** — período com dado devolve as etapas e a conversão; período vazio vira `vazio` (não zero); leads sem origem reduzem `Cobertura`; comparação com período anterior; saída serializa em JSON.
- [ ] **Step 2: Rodar e ver falhar**
- [ ] **Step 3: Implementar**
- [ ] **Step 4: Rodar e ver passar**
- [ ] **Step 5: Commit**

---

### Task 3: Registrar as duas no `registro_padrao()`

**Files:**
- Modify: `portal-gestao/app/loja/copiloto/tools.py`
- Test: `portal-gestao/tests/test_copiloto_tools.py`

**Descrição da ferramenta é interface, não comentário.** É o texto que o modelo lê para decidir se chama. Escrever com as palavras que o dono usa — "sem foto", "não dá para publicar", "quantos leads viraram venda" — não com o nome do campo no banco.

**Conferir os testes que já existem no registro** e que passam a cobrir as novas automaticamente: nenhum schema expõe identidade; toda saída serializa; ferramenta desconhecida levanta; argumento de tipo errado cai no default.

- [ ] **Step 1: Escrever o teste que falha** — o registro passa a ter 8 ferramentas; despacho funciona para as duas novas.
- [ ] **Step 2: Rodar e ver falhar**
- [ ] **Step 3: Implementar**
- [ ] **Step 4: Rodar e ver passar** — mais suíte inteira.
- [ ] **Step 5: Commit**

---

## Verificação antes de fechar a fase

- Suíte inteira verde.
- Com o Estoque fora: `cadastro_incompleto` responde `indisponivel` e as outras ferramentas seguem funcionando.
- A definição de "incompleto" bate com a da `regra_cadastro_incompleto` da Fase 1 — ou a divergência está escrita e justificada.
- `git diff --check` e `git status --short` limpos.
