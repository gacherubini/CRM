# Brief de subagente

O agente principal preenche isto **antes** de disparar o filho.
Sem os sete campos, não dispara. O filho não relê `AGENTS.md`, contexto nem a fila.

Cole no prompt do subagente, sem preâmbulo (“leia o repo e…”).

```markdown
## Objetivo
<uma frase: o que fica pronto no fim>

## Produto
<pasta: chatbot-api | motor-simulacao | estoque-api | portal-gestao | revy-trafego | catalogo-publico | site | n8n>

## Arquivos que pode tocar
- <path>
- <path>

## Invariantes desta tarefa
- <regra que, se quebrada, o trabalho é revertido>

## Não faça
- <o erro óbvio neste domínio>

## Como saber que acabou
Rodar: `<comando a partir da pasta do produto>`
Esperado: <PASS / exit 0 / o que observar>

## Docs permitidos
- <no máximo 3 paths; se for plano longo, só a Task N + Global Constraints>

## Docs proibidos
- docs/nao-plano/
- <outros que o filho não deve abrir nesta tarefa>
```

Se o card em `docs/fila/` tem mais de ~200 linhas, **não** aponte o arquivo inteiro.
Cole no brief o bloco Global Constraints e a Task N (checkboxes + files + testes).
