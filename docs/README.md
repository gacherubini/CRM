# Docs

Três pastas. O agente não varre `docs/` — escolhe **uma**.

| Pasta | O que é | Quando abrir |
|---|---|---|
| [`fila/`](fila/README.md) | Trabalho que ainda produz código ou config | Implementar um card |
| [`referencia-viva/`](referencia-viva/) | Verdade atual (estado, as-built, specs, planos DONE) | Entender o que já existe |
| [`nao-plano/`](nao-plano/) | Marca, história, tutoriais, planos substituídos | Só se o humano pedir |

Regras do agente: [`../AGENTS.md`](../AGENTS.md). Brief de subagente: [`referencia-viva/agents/task-brief.md`](referencia-viva/agents/task-brief.md).

Plano novo → `fila/`. Spec ainda válida → `referencia-viva/specs/`. Plano feito que descreve o código → `referencia-viva/planos/`. Plano velho/substituído → `nao-plano/arquivados/`.

Quando um card entra no `main`, no mesmo PR: mover o arquivo, atualizar
`fila/README.md` e `referencia-viva/contexto-compacto.md`. Código vence o
bloco Status do plano.
