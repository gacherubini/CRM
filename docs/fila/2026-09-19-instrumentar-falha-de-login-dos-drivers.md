# Instrumentar a falha de login dos drivers — o erro tem de dizer o motivo

> **Status 2026-09-19: BACKLOG / NÃO IMPLEMENTADO.**
> Nasceu da investigação do reCAPTCHA do Bradesco em 19/09, que eliminou cinco
> suspeitos e não achou a causa porque **o motivo real nunca é gravado**.
> Contexto: [`2026-09-19-recaptcha-do-bradesco-cinco-suspeitos-eliminados.md`](../../.claude/skills/revy-research/learnings/2026-09-19-recaptcha-do-bradesco-cinco-suspeitos-eliminados.md).

## Objetivo

Quando o login de um portal falha, o banco de dados hoje guarda um código
genérico. O motivo — a resposta do backend do banco, o erro de console, a
exceção real — morre junto com a Machine.

A consequência já está medida: a noite de 19/09 foi gasta testando hipóteses
que uma linha de resposta HTTP teria respondido.

Depois disto, uma rodada de produção tem de ser suficiente para dizer **por
quê**, sem SSH, sem probe e sem hipótese.

## Quem recebe a instrumentação

Três drivers, cada um por um motivo concreto e já observado:

### 1. Bradesco — o caso que está aberto

Sai `captcha_login` com a tarja "Erro ao tentar verificar o reCAPTCHA". Já foi
provado que o token **nasce** (2404 caracteres em 224 ms dentro do worker) e que
o navegador tira **0.9** no reCAPTCHA v3. Falta saber o que o backend deles
responde ao POST de login.

O que capturar: status e trecho curto do corpo da resposta do POST de login,
mais os erros de console da página. A página usa o wrapper `ng-recaptcha`, cujo
estado de prontidão é próprio e só se exercita submetendo — é a única hipótese
viva e a única que exige login.

**Custo: uma rodada de produção.** É o ponto todo do card — trocar N tentativas
cegas por uma instrumentada.

### 2. Santander — a exceção real é jogada fora

`santander.py:383` captura `Exception` genérica, monta a mensagem
`falha no portal Santander: {tipo}: {detalhe}` e a embrulha em
`ErroTransitorio("portal_falhou", ...)`. No banco chega só `portal_falhou`.

O print das falhas de 19/09 é **branco puro** (6,9 KB): a página não carregou. Se
foi DNS, TCP, TLS ou timeout do `goto`, não dá para saber daqui — e o `goto`
ainda engole a exceção num `except: pass` (`santander.py:457`).

O que capturar: o tipo e a mensagem da exceção que hoje só existem em memória.

### 3. Fontecred — bloqueio de IP disfarçado de lentidão

Em 19/09 o portal devolveu a página da Cloudflare ("Sorry, you have been
blocked", Ray ID `a3dcabf918fdf191`). O driver classificou `login_timeout` e
queimou **253 s por rodada** fingindo que era demora.

Causa: `_assert_portal_acessivel` (`playwright_base.py:404`) só conhece as
assinaturas da **Akamai** (`Access Denied`, `errors.edgesuite`). A página da
Cloudflare não casa com nenhuma e passa batida.

O que fazer aqui é diferente dos outros dois: além de capturar, **ensinar o
detector** a reconhecer a Cloudflare e levantar `portal_bloqueado`. Isso é
compartilhado — vale para os seis drivers, porque o detector mora na base.

### Quem NÃO recebe

- **PAN** — desde 19/09 já sai `campo_nao_confere` com o campo e a contagem de
  caracteres. O erro já diz o motivo.
- **Omni** e **Motrix** — os códigos atuais (`omni_proposta_nao_encontrada`,
  `credito_recusado`) já apontam o lugar certo.

## Invariantes desta tarefa

- **Nunca** CPF, senha, token do reCAPTCHA ou cookie na mensagem do evento nem
  no log. Vale status, código de erro, tipo de exceção, contagem. O helper e o
  evento são lidos por humano no Portal.
- Corpo de resposta entra **truncado** e sanitizado, nunca HTML cru do portal —
  a regra do topo de cada driver ("nunca logar usuario/senha/CPF/celular") não
  abre exceção para diagnóstico.
- O evento já suporta blob (migration `0013_evento_screenshot_blob`); o caminho
  de gravação existe e não precisa de migration nova.
- Flag de rollout, se houver, nasce OFF.

## Como saber que acabou

```
cd motor-simulacao && .venv/bin/python -m pytest -q          # macOS
cd motor-simulacao && .\.venv\Scripts\python.exe -m pytest -q # Windows
```

Mais uma rodada real do Bradesco cujo evento `falha_portal` traga o status do
POST. Se continuar genérico, a instrumentação não cumpriu o objetivo.

## Antes de executar este card

Fazer o **teste grátis** primeiro: uma rodada fria do Bradesco em outro dia.
Pontuação de reCAPTCHA tem componente temporal e o portal virou depois de 16
logins no mesmo dia (24 tentativas no total em 19/09). Se passar sozinho, este
card continua valendo pelos itens 2 e 3, mas perde a urgência do item 1.
