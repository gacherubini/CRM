---
gatilho: portal bancário recusa fora de horário comercial, ou mostra produto desabilitado após o login
produto: motor-simulacao
custo: um login frio do BV gasto num domingo (13/09/2026) para descobrir uma regra de horário
fonte: repo
verificado_em: 2026-09-13
---
# BV: produto Veículos só abre em horário comercial — e avisa num modal, não no login

Tentativa única e fria em 13/09/2026 (domingo, 16:30) via `scripts/_diag_bv.py
--fase entrar`, com a credencial válida do `.env.local`. Resultado **diferente**
das recusas anteriores (04/09: "usuário ou senha inválidos… solicite a
ativação"; 10/09: spinner eterno no stealth):

> **Atenção** — O Produto Veículos está desabilitado estando disponível
> somente em horário comercial, para acesso fora dessa regra favor utilizar o
> login com CPF Monitorado. [Ok, entendi]

A recusa continua não sendo a credencial. Há **dois gates independentes**:

1. **Anti-bot (persistente).** Sensor Akamai BM ativo e
   `GET …/ppar-base-dealer-simulador-rs/api-security/user` → **403** para o
   Chromium automatizado — igual ao diagnóstico de 10/09. O `POST
   …/api/auth/v2/login` saiu sem resposta registrada.
2. **Horário do produto (novo).** O modal acima é regra de negócio do portal,
   não erro de senha: fora do horário comercial, este tipo de login não abre o
   Veículos. A saída é outro tipo de credencial ("login com CPF Monitorado").

Regra que sai daí: **antes de gastar um login-robô, teste manual no navegador
do dono.** Se o mesmo modal aparece no browser normal, o gate é de horário e
não de bot — custo zero, sem contaminar score Akamai nem contagem de logins.
Só faz sentido tentar robô em dia útil, em horário comercial — e mesmo assim o
403 anti-bot continua valendo.

Vale para qualquer portal com produto por janela de atendimento, não só o BV.
