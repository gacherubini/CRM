---
gatilho: mexer no prompt do bot, no systemMessage ou na config do agente por loja
produto: n8n
custo: uma loja se apresentando como outra, ou o nucleo Revy deixando de prevalecer
fonte: repo
verificado_em: 2026-08-25
---
# O prompt do bot virou duas metades, e a ordem entre elas é a segurança

Desde 25/08 o `systemMessage` do `AI Agent1` é **expressão**, e o que o modelo lê é:

1. **operação do atendimento** — literal no `workflow-ai-nao-salvos.json`: jornada de
   catálogo, uso das ferramentas, anti-alucinação, tratamento de anúncio. Igual para toda
   loja.
2. **`{{ $('Gate config do agente1').first().json.promptAgente }}`** — identidade,
   personalidade, FAQ, regras e instruções **daquela loja**, vindas de
   `GET /v1/agente/config`, e terminando no **núcleo Revy**.

Três consequências que não se adivinham lendo o JSON:

- **Nada pode ser colado depois do slot.** O núcleo só prevalece porque é o último bloco;
  um rodapé, marca d'água ou debug depois dele desliga o mecanismo inteiro.
  `validate_workflow.py` reprova, e o `test_agente_prompt_migrado_do_n8n.py` guarda o
  outro lado.
- **Nome, cidade e tom de loja não voltam para o template.** O validador reprova
  `vitor motos` e `limeira` — era exatamente assim que a segunda loja se apresentaria
  como a primeira.
- **Regra de estilo que o formulário cobre não pode ficar genérica.** "não use
  exclamações" ficou no template por engano e passou a contradizer a loja que escolhe
  "pontuação normal" — e a higienização da saída, que respeita a escolha. Antes de
  escrever uma regra de tom no template, veja se ela já é campo em
  `chatbot-api/app/agente_prompt.py`.

E o prompt padrão vive **duas vezes**: no gerador do chatbot e como constante JS no
`Gate config do agente1` (fallback para quando a rota falha). `python -m
scripts.sincronizar_fallback_n8n` no `chatbot-api` reescreve a cópia; um teste reprova a
divergência.

Ver [[2026-08-23-o-prompt-do-bot-mora-no-n8n]] e [[2026-08-23-workflow-cloud-e-gerado]].
