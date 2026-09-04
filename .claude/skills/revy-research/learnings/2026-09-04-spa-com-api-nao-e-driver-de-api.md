---
gatilho: achar API JSON atrás do portal de um banco e querer trocar Playwright por HTTP
produto: motor-simulacao
custo: uma tarde de reconhecimento no Motrix e no BV para chegar em "não dá"
fonte: repo
verificado_em: 2026-09-04
---
# Ver JSON na aba Network não quer dizer que existe API para você

O repo é API-first, então a primeira pergunta de banco novo é sempre "tem API?". Em 04/09
os dois candidatos responderam **sim, e ainda assim não**.

**Motrix.** SPA sobre `api-joinbank.ukam.io/v3`. `POST /v3/auth/sign-in` com
`{accessId, password, type:"app", stayConnected:true}` devolve `{user, token, expires}`,
token de ~24h. Limpo, versionado, sem captcha. Assinei por `httpx` e todo GET seguinte deu
401. A causa apareceu ao capturar os headers reais do browser: junto do `authorization`
vai um `x-version-<sufixo>` no formato `<timestamp>.<sha256>`, assinado pelo JS da página.
Sem ele, 401. Testei o token em seis formatos de `Authorization` antes de olhar os headers
— chutar custou seis requisições e nenhuma informação.

**BV.** Portal Angular sobre REST same-origin (`ppar-base-dealer-simulador-rs`), com
`POST /api/auth/v2/login`, `/api/security/token/csrf` e `/api/integration/jwt`. Login por
HTTP puro esbarra em três camadas de uma vez: Akamai Bot Manager (`/akam/13/pixel_*` mais
POSTs de sensor em path ofuscado), reCAPTCHA Enterprise invisível, e a senha cifrada em RSA
com chave vinda de `/api/criptografia/publickey/obterchave`.

A regra que sai daí: **API interna de SPA não é API de parceiro.** Reproduzir assinatura de
request ou sensor de bot manager é contornar controle anti-automação, quebra a cada build
do banco, e não é o que "API-first" quer dizer. `ApiBankDriver` é para contrato publicado
com credencial emitida para a loja — o caso do Pan. Todo o resto é `PlaywrightBankDriver`.

O que a descoberta ainda vale: o `/v3/menus` do Motrix entregou o mapa de navegação inteiro
(`/loan-simulations/menu`, `/loan-simulations`), e navegar por URL é muito mais firme do
que clicar numa sidebar colapsável. Ler a rede para **descobrir para onde ir** compensa;
ler a rede para **substituir o browser** não compensou em nenhum dos dois.

Como decidir rápido em banco novo, sem repetir a tarde:

1. Existe portal do desenvolvedor com auto-cadastro e a loja consegue credencial? Então é
   API de verdade.
2. O menu do portal logado tem seção de integração/API/token? (No BV: não tem nenhuma.)
3. Caso contrário é Playwright — e o tempo é melhor gasto no driver do que na rede.

Ver também [[2026-09-04-portal-do-banco-desativa-login-repetido]]: cada rodada desse
reconhecimento custa um login, e login é recurso escasso.
