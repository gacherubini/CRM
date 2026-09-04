---
gatilho: logar num portal bancário por script, ou repetir um login que acabou de funcionar
produto: motor-simulacao
custo: o login do BV desativado no meio do reconhecimento, e o card do BV parado
fonte: repo
verificado_em: 2026-09-04
---
# O quarto login do dia desativa o acesso — mesmo com a senha certa

Reconhecimento do portal do parceiro BV em 04/09/2026. Três rodadas de `_diag_bv.py`, cada
uma abrindo um browser novo e logando do zero. As três entraram. A quarta respondeu:

> **Atenção** — Usuário ou senha inválidos, tente novamente!
> Caso ainda não consiga acessar, acione seu Gerente de Relacionamento e solicite a
> ativação do login.

A senha estava certa: tinha funcionado dez minutos antes, e o `.env.local` não mudou. O que
mudou foi a contagem. "Solicite a ativação do login" não é texto de senha errada — é texto
de acesso **desativado**, e só o gerente do banco reverte.

Não sei dizer se o gatilho foi a frequência, sessões simultâneas do lado do servidor, ou
política de acesso ocioso. O que dá para afirmar: três logins em dez minutos foram
suficientes, e o custo de descobrir de novo é alto demais para valer o experimento.

Duas regras que saíram daí, já aplicadas em `scripts/_diag_bv.py` e `_diag_motrix.py`:

1. **Todo script que loga grava `storage_state` e reusa.** Um login por dia, não um por
   rodada. No Motrix isso levou o reconhecimento inteiro (menu, API, wizard, ofertas) a
   caber em dois logins.
2. **Senha recusada = pare.** Sem retry, sem "talvez agora vá". A segunda tentativa é
   justamente a que desativa. Os dois diags imprimem `LOGIN RECUSADO. PARANDO.` e saem;
   o `MotrixDriver` levanta `IntervencaoNecessaria("credencial_invalida")` em vez de
   tentar outra vez.

Vale para qualquer portal bancário, não só o BV. O Motrix aguentou quatro logins sem
reclamar, o que não prova nada sobre o quinto.

Primo deste: [[2026-09-04-probe-todos-roda-os-bancos-de-uma-vez]] — lá a sessão quente é
economia de tempo; aqui é o que impede de queimar a credencial da loja.
