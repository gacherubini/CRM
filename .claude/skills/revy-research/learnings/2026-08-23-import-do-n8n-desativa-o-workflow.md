---
gatilho: subir workflow novo no n8n do Fly
produto: n8n
custo: um restart inteiro perdido
fonte: infra
verificado_em: nunca reconferido desde a migracao das memorias (2026-08-23)
---
# `import:workflow` DESATIVA, e `publish` nao religa

Sequencia que funciona (todos via
`fly machine exec <machine-id> "env HOME=/home/node n8n ..." -a n8n2037`):

1. `n8n import:workflow --input=<arquivo>` — **desativa o workflow ao importar**
   ("Deactivating workflow ..." no output, facil de nao notar);
2. `n8n publish:workflow --id=<id>` — publica a versao mas **nao** deixa ativo;
3. `n8n update:workflow --id=<id> --active=true` — **este** e o que ativa. O n8n avisa
   que esta deprecated e manda usar `publish`; nesta versao o publish sozinho nao liga.
   Ignore o aviso;
4. `fly apps restart n8n2037` — so entao o webhook registra.

Sem o passo 3 o webhook responde **404 para sempre**, mesmo depois de restart. Confira
com `n8n list:workflow --active=true` (o `list:workflow` puro mostra todos e nao
distingue).

**Preparar para o Fly:** o canonico usa nomes internos (`http://chatbot-api:8000`,
`http://evolution:8080`) e `"active": false`. Quem reescreve host, troca placeholder de
token e vira `active: true` e o `deploy/fly/3vm/prepare-workflow.ps1` — **que so trata o
`workflow-ai-nao-salvos.json`**. Workflow novo (o cloud, por exemplo) precisa das quatro
transformacoes na mao, senao sobe apontando para host que nao resolve. O `.gitignore`
cobre so os `*.ready.json`: gere o arquivo com token real **fora do repo**.
