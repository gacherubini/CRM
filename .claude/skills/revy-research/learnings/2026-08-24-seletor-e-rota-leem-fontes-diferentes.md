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
