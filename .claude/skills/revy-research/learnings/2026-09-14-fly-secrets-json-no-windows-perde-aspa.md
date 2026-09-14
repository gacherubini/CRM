---
gatilho: setar secret JSON (mapa por loja) via fly secrets no Windows
produto: motor-simulacao
custo: mapas MOTOR/CHATBOT_TOKENS_JSON chegaram sem aspa, JSON inválido, fail-closed derrubou bancos e chatbot de todas as lojas
fonte: infra
verificado_em: 2026-09-14
---
# `fly secrets set` no PowerShell 5.1 come aspa dupla de dentro do valor

O PowerShell 5.1 remove `"` do interior de argumento ao repassar para exe
nativo. `fly secrets set -a app2037 "MAPA={"a":"tok"}"` chegou na máquina como
`{a:tok}` — JSON inválido, e o `motor_token_para` fail-closed desligou tudo.

Regras, todas verificadas com probe em 14/09:

1. Escapar como `\"` no valor em runtime (nunca literal no comando): 
   `($json -replace '"', '\"')`. Probe com `{"probe":"xy"}`: sem escape chega
   `{probe:xy}` (10 chars); com escape chega intacto (15 chars).
2. Conferir forma no servidor **sem exibir valor**: tamanho + `json.loads` +
   lista de chaves (slugs) + contagem de `"`. Nome de secret confere com
   `fly secrets list` (só nomes).
3. Mapa por loja é ler-fundir-escrever: ler o valor atual, fundir a entrada,
   setar, reler as chaves. Sobrescrever do zero derrubou `moto-center` do mapa
   em 14/09 (recuperado porque os tokens originais estavam no `.secrets.local`).
4. Segredo em comando vai por variável, nunca literal — e `2>$null` não esconde
   stdout; o que prova sem vazar é imprimir só chaves, tamanhos e status HTTP.
