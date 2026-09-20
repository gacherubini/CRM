---
gatilho: Bradesco sai com captcha_login / "Erro ao tentar verificar o reCAPTCHA" e voce vai trocar de IP, limpar sessao, mexer no navegador ou no timing do grecaptcha
produto: motor-simulacao
custo: uma noite inteira, um proxy residencial contratado e 24 tentativas de login queimadas no portal
fonte: infra
verificado_em: 2026-09-19
---
# O reCAPTCHA do Bradesco: cinco suspeitos ELIMINADOS por medicao — nao refaca

Em 19/09 o Bradesco logou 16 vezes entre 01:06 e 14:16 e virou. Da rodada das
14:42 em diante, **toda** tentativa morre na tarja vermelha "Erro ao tentar
verificar o reCAPTCHA", com CPF e senha ja preenchidos.

Nao e captcha visual. E reCAPTCHA **v3 puro** (`api.js?render=`, chave
`6LdjHLYrAAAAAFitXimO6O8Onh3hogINT5Pb0b8c`, wrapper `ng-recaptcha` com
`onload=ng2recaptchaloaded`). **Nao e Enterprise** — conferido na pagina.

**A causa raiz NAO foi encontrada.** O que este learning entrega e a lista do que
ja foi descartado, cada item com experimento. Nao repita nenhum.

## Os cinco eliminados

| # | Suspeito | Como caiu |
|---|---|---|
| 1 | IP de datacenter | worker apontado para saida residencial BR (45.238.41.48, Embu das Artes/SP, AS268311 Dconnect, `hosting:false`). Mesma tarja, mesmos 13 s. O `_conferir_ip_de_saida` passou, entao o trafego saiu mesmo pelo proxy |
| 2 | Cookie de reputacao na sessao salva | `MOTOR_STORAGE_STATE_DIR` apontado para diretorio vazio; a rodada saiu `sessao_fria` de verdade, navegador sem cookie nenhum. Mesma tarja |
| 3 | Ambiente da VM / navegador pontuado como robo | sonda contra a demo do Google, **rodando dentro do worker**: `score 0.9`. Com SwiftShader, 2 nucleos, Linux e IP do Fly. O Google da nota de humano ao nosso worker |
| 4 | Clique antes do grecaptcha ficar pronto | medido na propria pagina do Bradesco: `execute` aparece em 1682 ms, `ready()` dispara em 1679 ms. **GAP de -3 ms.** Nao existe janela; os 400 ms fixos do driver sobram |
| 5 | Token que nao nasce | `grecaptcha.execute()` da chave deles chamado a mao, **de dentro do worker**: token de 2404 caracteres em 224 ms, zero requisicao falhada. Identico ao resultado na maquina do dono |

Controle que fecha a conta: o dono logou a mao no mesmo portal, em janela normal
**e** anonima, e entrou. O banco esta de pe.

## O que isso deixa de pe

O token nasce e o navegador tem nota de humano. Logo a falha esta **depois da
geracao**: ou o token nao chega direito no POST, ou chega e o backend do Bradesco
recusa.

Uma distincao que ainda nao foi testada: as sondas exercitaram a **API crua** do
Google. A pagina usa o wrapper `ng-recaptcha`, que tem estado de prontidao
proprio e pode recusar mesmo com o `grecaptcha` embaixo funcionando. Testar o
wrapper exige submeter o formulario, ou seja, gastar login.

Proximo passo desenhado em `docs/fila/2026-09-19-instrumentar-falha-de-login-dos-drivers.md`.

## Ferramentas que sobraram prontas

Duas sondas que medem **sem gastar login**, versionadas porque foram o que
impediu de reconstruir a imagem no chute:

- `motor-simulacao/scripts/probe_recaptcha_score.py` — nota do reCAPTCHA v3
  contra a demo do Google, mais WebGL, UA e nucleos;
- `motor-simulacao/scripts/probe_recaptcha_bradesco.py` — `grecaptcha.execute()`
  contra a chave do Bradesco na pagina **publica** de login (nao digita CPF nem
  senha, nao submete).

As duas rodam no worker pela receita de
[[2026-09-12-fly-ssh-console-comando-complexo-via-stdin]], com `xvfb-run -a`
porque o Xvfb do entrypoint so vive enquanto o worker processa.

## Regras que saem daqui

- **Nao contrate proxy para resolver isto.** Proxy residencial resolveu o
  Fontecred (bloqueio Cloudflare por ASN, esse sim de rede) e nao encostou no
  Bradesco. Ver [[2026-09-13-dataimpulse-sticky-egress-bradesco]].
- **Meça antes de reconstruir.** A aposta em "SwiftShader derruba a nota" estava
  errada e teria custado uma imagem nova com Chrome de verdade. A sonda custou
  10 minutos.
- **Orcamento de login e real:** 24 tentativas no Bradesco em 19/09.
  [[2026-09-04-portal-do-banco-desativa-login-repetido]] mostra banco desativando
  acesso no quarto login do dia. Toda hipotese nova tem de ser testavel sem login,
  ou esperar.
- **Teste gratis antes de qualquer investimento:** uma rodada fria no dia
  seguinte. Pontuacao de reCAPTCHA tem componente temporal e o portal virou
  depois de 16 logins no mesmo dia.
- **Se nada disso resolver:** login humano plantado, para o driver nunca encostar
  no reCAPTCHA — o Omni ja vive assim (19 `login_pulado` em 19/09). Bloqueio
  conhecido: sem volume no worker o arquivo morre com a Machine
  ([[2026-09-13-storage-state-morre-no-rootfs-efemero-do-fly]]).

## Duas pontas soltas honestas

**`MOTOR_WARM_SESSION=0` na Machine nao produziu rodada fria.** O evento
`sessao_quente` saiu mesmo assim, e ele so e emitido dentro de
`if config.WARM_SESSION:` (`app/processamento.py:1138`). A config da Machine dizia
`0`, conferida tres vezes. Sem explicacao. O contorno que funciona e apontar
`MOTOR_STORAGE_STATE_DIR` para diretorio vazio.

**Nunca foi verificado que o Bradesco mexeu na pagina deles por volta das 14:20.**
A virada de horario e fato (ultimo login bom 14:16, primeira falha 14:42, sem
deploy nosso entre 12:25 e 14:51); a causa dela e suposicao.
