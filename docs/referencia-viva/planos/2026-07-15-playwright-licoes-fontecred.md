# Lições Playwright — Fontecred

> **Status em 2026-07-15:** driver Fontecred LIVE, validado localmente e no worker Fly/Xvfb.
> Produção `motor2037` versão 12, health passing; suíte do Motor com **147 testes verdes**.
> Ler junto com `2026-07-13-playwright-licoes-santander.md` antes de implementar outro banco.

## Escopo entregue

O segundo driver Playwright real do Motor automatiza o portal do lojista Fontecred:

1. login por e-mail e senha, ou reaproveitamento de `storage_state` válido;
2. confirmação do Dashboard autenticado;
3. fechamento do modal **COMUNICADOS**;
4. abertura de `clientes/criarComProposta`;
5. CPF, nascimento e celular;
6. resolução do veículo pela placa;
7. valor, entrada, prazo e autorização SCR;
8. envio da simulação, modal PEP e oferta de proteção;
9. leitura das parcelas e da entrada mínima devolvida pelo portal.

O Fontecred exige celular e placa. Ausência desses dados deve ser rejeitada antes de abrir o browser,
com códigos estáveis como `celular_obrigatorio` e `placa_obrigatoria`.

## Incidente e causa-raiz

### Sintoma visual enganoso

Os screenshots de falha mostravam o Dashboard com o modal COMUNICADOS aberto. A primeira hipótese foi
que o clique no `X` havia falhado. Isso ocorreu em um fluxo antigo, mas não explicava todos os jobs.

A timeline foi a evidência decisiva:

```text
browser_iniciando
browser_pronto
falha_inesperada
```

Como `login_confirmado` não aparecia, a exceção acontecia **antes** de `_fechar_comunicados`. Portanto,
o modal visível no screenshot era o estado final da página, não necessariamente a etapa que falhou.

### Diferença entre sessão fria e sessão quente

- No teste local, o `storage_state` estava expirado: o portal mostrou o formulário e o login normal
  passou.
- No worker, o `storage_state` continuava válido: navegar para `/login` redirecionava diretamente ao
  Dashboard com COMUNICADOS.
- O portal mantém conexões abertas. `goto(..., wait_until="networkidle")` podia expirar mesmo com o
  Dashboard pronto.
- Após o timeout, o driver tentava navegar novamente e procurar e-mail/senha numa tela já autenticada;
  essa procura expirava e virava `portal_falhou`.

**Regra permanente:** todo banco com sessão persistida deve testar separadamente:

1. login frio, com formulário;
2. login quente, com redirect automático;
3. `networkidle` expirado, mas marcador autenticado já visível.

Nunca trate timeout de navegação como prova de que a página não carregou.

## Correções aplicadas

### Reconhecimento pós-login

O driver considera a área autenticada quando encontra um destes sinais:

- URL fora de `/login`;
- título `COMUNICADOS` visível;
- título `Dashboard` visível.

Se `networkidle` expirar, ele verifica esses marcadores antes de navegar novamente. Quando a sessão já
está válida, pula os campos de credencial, espera o DOM e segue para o modal.

### Modal COMUNICADOS

O fechamento não é considerado concluído só porque `click()` ou `Escape` não levantou exceção.

Fluxo obrigatório:

1. esperar o título COMUNICADOS ficar visível;
2. tentar botão com nome `Fechar`;
3. tentar seletores Bootstrap 5 (`.btn-close`, `[data-bs-dismiss="modal"]`) e legados;
4. usar `Escape` como último fallback;
5. esperar o título ficar `hidden`;
6. verificar novamente `is_visible()`;
7. se persistir, retornar `comunicados_nao_fechou`.

### Navegação e ritmo

- A URL de Nova Proposta usa `wait_until="commit"` para não perder uma navegação que já começou.
- Depois do commit, o driver espera `domcontentloaded`, `document.readyState` e o campo CPF ficar
  visível e acionável.
- `click(trial=True)` confirma actionability sem alterar a tela.
- Nascimento, celular, placa, seleção do veículo e botão Simular têm esperas explícitas.
- Depois de Simular, o driver espera PEP, proteção, erro ou cards de parcela. A espera final continua
  responsável por estabilizar os cards.

Prefira marcador real da próxima etapa a sleeps longos. Uma pausa curta continua válida apenas para
animação visual ou debounce conhecido.

## Observabilidade obrigatória

O Fontecred registra etapas sanitizadas e prints protegidos por job:

```text
browser_iniciando
browser_pronto
login_confirmado
comunicados_fechados
proposta_aberta
dados_preenchidos
simulacao_enviada
ofertas_recebidas
parcelas_lidas
```

Falhas conhecidas usam `falha_portal`; exceções imprevistas usam `falha_inesperada` com somente o tipo
da exceção, nunca HTML, CPF, placa, e-mail ou senha. Screenshots ficam no diretório do job, passam por
RBAC/tenancy no Portal e seguem a retenção configurada.

Diagnóstico por sequência:

| Última etapa | Investigar primeiro |
|---|---|
| `browser_pronto` | navegação/login, sessão persistida, captcha, timeout de locator |
| `login_confirmado` | modal COMUNICADOS e overlay |
| `comunicados_fechados` | URL/menu da proposta e campo CPF |
| `proposta_aberta` | carregamento de CPF/nascimento/celular/placa |
| `dados_preenchidos` | botão Simular, PEP, SCR e proteção |
| `simulacao_enviada` | erro bancário, cards e parser |

Não diagnosticar apenas pelo screenshot: correlacionar sempre com a última etapa persistida.

## Validação que encerrou o incidente

O smoke foi executado dentro do próprio worker Fly, usando Chromium headed + Xvfb e o `storage_state`
persistido, sem preencher cliente e sem enviar proposta:

```text
PORTAL_AUTENTICADO=True
SESSAO_REUTILIZADA=ok
MODAL_ANTES=True
MODAL_DEPOIS=False
SMOKE_WORKER=ok
```

Depois disso, uma simulação real iniciada pelo usuário concluiu com sucesso.

Commits do endurecimento:

- `ce75e60` — fechamento do modal, navegação resiliente e timeline por etapa;
- `8ac4b92` — esperas por DOM/actionability e ritmo conservador;
- `1165690` — reconhecimento e reaproveitamento da sessão autenticada.

## Checklist para o próximo banco

1. Confirmar API antes de escolher RPA.
2. Mapear sessão fria, quente, expirada, captcha e credencial rejeitada.
3. Não usar `networkidle` como único sinal de sucesso.
4. Definir marcadores autenticados específicos do banco.
5. Registrar evento antes/depois de cada fronteira importante.
6. Para cada modal, validar `visible → ação → hidden`.
7. Esperar o próximo campo ficar visível e acionável antes de preencher.
8. Testar local headed e no mesmo Chromium/Xvfb da produção.
9. Fazer smoke sem proposta quando o objetivo for apenas login/modal.
10. Manter mensagens, logs e nomes de arquivos sem PII.
11. Validar retry: duas tentativas não podem esconder a etapa original da falha.
12. Só publicar após teste focado, suíte completa e health check do worker.

## Limitações ainda abertas

- Seletores do portal podem mudar sem aviso; timeline e screenshots são parte do contrato operacional.
- `testar-login` administrativo ainda é placeholder; o smoke e a simulação real continuam sendo a
  validação prática.
- API e worker ainda compartilham uma Machine de 2 GB.
- Fan-out por banco e workers sob demanda continuam planejados, não implementados.
- `storage_state` ainda depende do volume da Machine; object storage privado é necessário antes de
  escalar para múltiplos workers.

---

## Rodada de 2026-09-04 — três quebras empilhadas no mesmo driver

> Driver voltou a **OK** (53s, prazos 24/36/48). Achados de uma corrida local headed com
> `scripts/probe_todos.py`. Cada correção revelava a próxima falha: o driver seguia adiante
> sem verificar nada, então só o último passo reclamava.

### 1. O título do modal é `COMUNICADO`, singular, na tela de proposta

O regex era `^\s*COMUNICADOS\s*$` — plural, ancorado. No dashboard casa; em
`clientes/criarComProposta` o portal escreve **COMUNICADO**. Resultado: `_comunicados_visivel`
devolvia `False`, o driver registrava "comunicados fechados" sem ter clicado em nada, navegava
para a proposta e batia no overlay ao clicar no CPF. O código que saía era
`nova_proposta_falhou`, apontando para uma tela que tinha carregado normalmente.

Agora existe a constante `COMUNICADO_TITULO = r"^\s*COMUNICADOS?\s*$"`, usada nos quatro pontos
que antes repetiam o regex, e o modal é fechado **também** dentro de `_passo_nova_proposta`
(espera curta de 2,5s) — não só depois do login.

### 2. Placa com mais de uma versão abre um segundo modal

`FUV7G58` casa com três Yamaha FZ25 250 FAZER de FIPE diferente (827107-0, 827116-0, 827117-8),
e o portal abre **"Selecione o modelo correto para esta placa"** com um botão `Selecionar` por
linha. O driver não conhecia essa tela.

Regra aplicada: **primeira versão da lista**, a mesma que o dono já tinha definido para o
Bradesco (`bradesco.py:648`). Vale saber que as três têm FIPE diferente, então valor e parcela
mudam conforme a escolha — para placa de teste tanto faz, em produção é o valor do bem.

### 3. O sinal de "veículo resolvido" é `select#produto`, não um clique que não deu erro

O caminho antigo clicava na primeira "linha com botão" (`get_by_role("row")`) e tratava exceção
como `veiculo_nao_resolvido`. Essa lista de linhas **era o modal**. Depois que o modal passou a
ser tratado, sobram zero linhas, e o driver acusava `veiculo_nao_resolvido` com marca, ano e
produto já preenchidos na tela.

DOM real depois da placa resolver:

    #type_product   value='1'      sel='Moto'
    #used_product   value='0'      sel='Não'      (label "Veículo 0KM:")
    #brand          value='YAMAHA'
    #year_model     value='2021'
    #produto        value='8049'   sel='FZ25 250 FAZER FLEX'
    rows com botão: 0

`_confirmar_produto_resolvido` agora lê `#produto`. **`get_by_label("Selecione um produto")`
devolve string vazia** — o rótulo não está associado ao input, então esse caminho nunca serviria.

### 4. O checkbox LGPD/SCR nunca era marcado

O regex procurava `autoriza a consulta`. O texto do portal é *"**Autorizo** a Fontecred a
**consultar** e tratar meus dados em bases de crédito, inclusive SCR…"*. Nunca casou — e a
tentativa estava dentro de `except: pass`, num campo que é obrigação legal. O portal recusava o
Simular com o balão *"Marque esta caixa se deseja continuar"*, e o driver morria 90s depois no
botão, com código apontando para a tela errada.

`_marcar_autorizacao` tenta três estratégias e **confirma pelo `.checked` real**, achando o input
pelo texto ao redor (`i.closest('label')`), já que o rótulo não está associado. Sem confirmação,
falha com `autorizacao_scr_nao_marcada`.

### O que os quatro têm em comum

Nenhum passo lia de volta o que tinha escrito. `_passo_financiamento` rodou inteiro contra uma
tela bloqueada e registrou `dados_preenchidos` com o campo de valor vazio e o erro vermelho na
cara. É o padrão do commit `4879c47` (Bradesco, julho/2026), que na época não foi varrido nos
outros drivers. Hoje cada etapa lê de volta: `valor_venda_nao_aplicou`,
`modelo_placa_nao_escolhido`, `autorizacao_scr_nao_marcada`, `comunicados_nao_fechou`.

Efeito colateral bom: o trecho `proposta_aberta → dados_preenchidos` caiu de **188s para 10s**.
A lentidão era o modal segurando cada `wait_for` até o timeout.
