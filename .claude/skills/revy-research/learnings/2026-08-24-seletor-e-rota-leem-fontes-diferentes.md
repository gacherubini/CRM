---
gatilho: mexer em multi-loja, no seletor de lojas ou em quem pode trocar de loja
produto: portal-gestao
custo: metade das lojas do seletor recusando acesso, com erro mudo na tela
fonte: repo
verificado_em: 2026-08-24
---
# O seletor e a rota de troca precisam ler a MESMA fonte de membership

O `<select>` de lojas do shell da Loja era montado por `resolve_store_and_entitlements`,
que monta o actor **com** as memberships vindas do Control — três lojas, no caso do dono.
O `POST /app/loja/selecionar` montava o actor com `_actor_for(usuario)`, **sem** o Control:
só `usuario.loja_slug`, uma loja.

Resultado: **duas das três opções do próprio seletor sempre falhavam**, e a única que
"funcionava" era a loja em que a pessoa já estava. O sintoma parece permissão quebrada —
não é. O dado estava certo: três vínculos `state='ativo'`, cargo `dono`. Era o POST que se
recusava a ler a fonte que a tela usou para desenhar.

Fonte única agora: `control_memberships_for` (`app/web/loja_shell.py`), usada pelos dois.

**Cuidado ao unificar:** agora que a rota confia no port do Control, ele precisa filtrar o
cargo por `ROLES_OPERACIONAIS` (feito em `app/loja/control_projection.py`). Sem isso, um
vínculo gravado como `admin_plataforma` viraria acesso de loja pela porta dos fundos —
contra a escolha deliberada de `app/loja/identity.py:22`, onde `admin_plataforma`
**não** é cargo operacional da Loja.

Detalhe que dobrou o tempo de diagnóstico: o `?erro=` do redirect não era renderizado em
lugar nenhum. A pessoa voltava para `/app` com uma query string e nenhuma explicação. Se
você criar um `?erro=` novo, renderize junto.

## Terceira ocorrencia, 29/08: a tela de Atendimento usa DOIS clientes

O historico e o envio da mesma tela falam com o chatbot por portas diferentes:

- `GET`  -> `main.get_chatbot_client(request)` — recebe o `Request` e resolve o
  token com `settings.chatbot_token_para(slug_da_sessao)`;
- `POST` -> `loja/routes.get_human_messaging_port()` — **nao recebia o
  `Request`** e usava `settings.chatbot_token`, o global.

Em producao isso dava GET 200 e POST 404 na mesma conversa, com o mesmo
`canal_id`: o chatbot resolvia `ctx.loja_id` pelo token, o canal pertencia a
loja da sessao e o token apontava para outra, entao
`_canal_id_opcional_por_instance` devolvia "instancia nao reconhecida".

**O 404 foi sorte — ele falhou fechado.** Se o token fixo pertencesse a uma loja
que *tem* aquele canal, o portal mandaria a mensagem pela loja errada, sem erro
nenhum. E o mesmo vazamento que `chatbot_token_para` existe para estancar (foi
assim que a `teste` mostrou os 1104 atendimentos da `moto-center`).

**A regra:** toda dependencia que fala com o chatbot precisa do `Request`.
Dependencia sem `Request` num deploy multi-loja e um vazamento esperando o
token certo. Procure por `Depends(` que devolva cliente do chatbot e nao receba
`Request` — cada uma e uma candidata.
