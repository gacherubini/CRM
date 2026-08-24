---
gatilho: testar envio de convite ou de e-mail
produto: portal-gestao / revy-trafego
fonte: repo
verificado_em: 2026-08-24
---
# Backend `console` devolve 200 e ninguem recebe nada

O envio de e-mail e uma camada agnostica com backend `console` para dev, que **so loga**.
No caminho feliz o convite responde **200 e ninguem recebe** — sucesso enganoso identico ao
de um envio real. Conferir por status HTTP nao prova entrega; so a caixa de entrada prova.

Na outra ponta, o cliente HTTP do Control colapsa **qualquer** nao-2xx numa unica excecao
de indisponibilidade, entao a mensagem "nao foi possivel enviar o convite" cobre tres
causas diferentes: dono ja vinculado a outra loja (**409**), e-mail estourando (**502**) e
o caso feliz que nao entrega. Ao depurar, bata direto no endpoint interno e olhe o status
cru antes de mexer em codigo.

Consertar o 409 nao entrega e-mail: SMTP em producao e pre-requisito a parte.
