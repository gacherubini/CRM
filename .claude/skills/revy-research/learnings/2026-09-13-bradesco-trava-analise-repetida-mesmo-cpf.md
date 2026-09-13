---
gatilho: ofertas_demoraram no Bradesco e voce vai culpar o IP, o driver ou o timeout
produto: motor-simulacao
custo: 9 probes de 10min queimados em sequencia pelo mesmo motivo evitavel
fonte: repo
verificado_em: 2026-09-13
---
# Repetir a mesma simulacao TRAVOU a analise 9x — hipotese lider, nao prova

Probe 10x do Bradesco no IP residencial em 13/09/2026 (logs em
`/tmp/probe-bradesco-10x/run-{1..10}.log`, mesma maquina; a pasta e efemera):

| run | resultado | detalhe |
|---|---|---|
| 1 | OK em 95s | login frio, ofertas em ~51s |
| 2–10 | `ofertas_demoraram` 9x | "Analisando dados" os 600s inteiros, fluxo identico ao run 1 ate `simulacao_enviada` |

Mesmo CPF, mesmos dados, ~100min. O run 2 comecou 10s depois do fim do run 1 —
mesma janela, mesmo IP, fluxos identicos no log (login em ~9s nos dois) — entao
NAO e IP, driver, modal, caminho de sessao nem deriva de horario entre run 1 e 2.
Hipotese lider: **o banco trava a analise quando o mesmo cliente e simulado em
sequencia** (throttle de velocidade por CPF, lado do portal/SCR). Rival nao
descartada: lentidao do banco iniciada por coincidencia as ~18:11 e sustentada
por 1h40. n=1 de run limpo nao prova; experimento discriminante pendente: 1 probe
com CPF diferente (OK rapido = throttle confirmado; trava = e o banco/a hora) ou
1 probe com o mesmo CPF apos horas de descanso.

**Confirmado 13/09 ~20:00:** 1 probe com CPF diferente (mesma maquina, mesmo IP,
mesmo codigo, 8min apos o run 10 travar) → OK em 227s, ofertas em ~3min
(`run-cpf2.log`). A rival "banco lento desde as 18:11" morreu: o banco responde
bem para CPF novo na mesma janela. E throttle por repeticao do CPF.

**Reviravolta ~20:02 (`run-cpf1-allow.log`):** CPF batido DE NOVO, mas com o dono
clicando **Allow no prompt de geolocalizacao** do browser → OK em 55s, ofertas em
10 SEGUNDOS, 14min apos o run 10 travar 600s. O run com CPF novo tambem teve
Allow clicado. Mecanismo candidato: sessao sinalizada (velocidade/IP) cai em
revisao estendida que so destrava com sinal de localizacao; sem ela, a analise
nunca volta (timeout). O driver NUNCA concede geolocalizacao (sem
`grant_permissions` em `playwright_base.py`) — no Fly/headless ela jamais e
dada. Pendente o teste separador: CPF batido **Provado ~20:07 (`run-geo-auto.log`):** `grant_permissions(["geolocation"])` +
`set_geolocation` no contexto (sem clique humano, prompt nem aparece) com CPF
batido → OK em 51s, **ofertas em 2 SEGUNDOS**, minutos apos 9 travas de 600s com
o mesmo CPF. O grant substitui o Allow clicado. Implementado em
`playwright_base.py:aplicar_geolocalizacao` (default OFF via
`MOTOR_GEO_LATITUDE/LONGITUDE`); teste em `test_config_browser.py`. Para o
worker do Fly falta definir as coords da saida (gru) como env da machine.

Tres corolarios:

1. **Retry de `ofertas_demoraram` com o mesmo payload queima 10min a toa.**
   As tentativas 2 de `e185f834`, `d3a36175` e `f63b57b6` em prod repetiram o mesmo
   codigo pelo mesmo motivo. Espacar ou nao retuitar vale mais que aumentar timeout.
2. **Captcha zerou no residencial (0/10, nenhum `captcha_login`), mas oferta nao.**
   IP residencial resolve o login, nao a analise. Uma hipotese, um experimento cada.
3. **Medir repetido envenena o poco.** A bateria 10x provou o captcha zerado no run 1
   e depois mediu o throttle, nao o IP. Para latencia de oferta, 1 probe frio por
   CPF/dia; o resto e o banco se defendendo.

Primos: [[2026-09-04-portal-do-banco-desativa-login-repetido]] — la o banco desativa
o login repetido, aqui ele congela a analise repetida; [[2026-09-12-recusa-antes-do-erro-generico-na-espera]]
— a espera que distingue recusa de demora continua valendo, o que muda e nao repetir.
