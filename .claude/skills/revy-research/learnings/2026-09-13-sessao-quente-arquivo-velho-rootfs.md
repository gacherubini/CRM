---
gatilho: banco cai em captcha com sessao_quente logo após troca de rede, ou worker sem volume reusando sessão
produto: motor-simulacao
custo: logins escassos gastos reabrindo sessão nascida em outra rede
fonte: repo
verificado_em: 2026-09-13
---
# sessao_quente em boot zerado é arquivo velho no rootfs, não sessão válida

`sessao_parece_quente` (`app/sessao_browser.py:57`) só checa **arquivo existe e
tem mais de 2 bytes** — não valida nada no portal.

- `motor2037` **não tem volume** (`fly volumes list` vazio) e a imagem do worker
  **não carrega sessão** (`Dockerfile.worker` só dá `COPY` em `app/` e cria o
  dir vazio). Mesmo assim `sessao_quente` disparou segundos após boots zerados:
  o arquivo sobrevive no rootfs da máquina entre stop/start e tem linhagem de
  outra rede (era Fly-direto). Abrir sessão nascida em outra rede/IP é por si só
  gatilho de challenge — parte dos `captcha_login` pode vir daqui, não do IP atual.
- Antes de culpar o egresso, **invalide o arquivo velho e force um login frio
  limpo já na rede nova**. Se o frio passar e o morno falhar, era a linhagem.
- TTL são três relógios: (1) cookie de sessão do banco (server-side, desconhecido
  — mensurável contando `login_pulado` seguidos nos eventos); (2) amarração a
  rede/fingerprint (sticky com cliff de 120 min vs IP estático); (3) score v3,
  que **não é guardado** — é reavaliado a cada login, e sessão morna desvia do
  captcha *por não logar*. Arquivo não tem TTL; validade é server-side.
- Seed manual que presta: Chromium **idêntico ao do worker** (mesmo TLS/
  fingerprint), login humano uma vez, arquivo plantado no path canônico
  `{STORAGE}/{cliente_id}/{provedor}.json`. Não plante do Chrome do dia a dia.
