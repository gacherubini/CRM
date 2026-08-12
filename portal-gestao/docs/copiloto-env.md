# Variáveis de ambiente do Copiloto de Vendas

Referência operacional das variáveis `REVY_LOJA_COPILOTO_*` e `PORTAL_COPILOTO_*`
realmente lidas pelo código do Copiloto (produto Revy Loja, `portal-gestao`).
Levantado direto do código (`rg -n "REVY_LOJA_COPILOTO|PORTAL_COPILOTO" app`), não
dos planos de fase — os planos em `docs/superpowers/plans/` descrevem a
implementação no momento em que foram escritos e podem ter ficado para trás depois
de correções. Nenhum valor de segredo aparece aqui — só nome e o que ele controla.

## Onde cada uma é lida

A maioria vive em `app/config.py` (`Settings`), lida uma vez no boot. **Duas
famílias de exceção não passam por lá** e valem a pena guardar de cabeça, porque
mudar o valor em produção exige reiniciar o processo do worker/rota do mesmo jeito,
mas o valor não aparece se você procurar só em `Settings`:

- **`PORTAL_COPILOTO_MAX_ACOES_HORA`** — lida direto via `os.getenv` dentro de
  `app/loja/copiloto/acoes.py` (`_max_acoes_hora()`), não em `app/config.py`. Foi
  deixada assim de propósito para o `monkeypatch` de teste conseguir mudá-la em
  runtime sem recriar `settings`; o efeito colateral é que quem procurar rate-limit
  do Copiloto em `Settings` não vai achar. **É uma inconsistência conhecida, não
  documentação faltando** — se for unificar em `app/config.py`, confirme que os
  testes que fazem `monkeypatch.setenv("PORTAL_COPILOTO_MAX_ACOES_HORA", ...)`
  continuam pegando o valor novo a cada chamada.
- **As variáveis dos workers em background** (`app/copiloto_sinais_job.py` e
  `app/copiloto_turnos_job.py`) e as duas lidas em `app/web/loja_copiloto.py` — são
  lidas via os helpers `env_flag`/`env_float`/`env_int` de
  `app/meta_ads_spend_job.py`, também fora de `app/config.py`. Esse padrão é
  compartilhado com outros workers do Portal (não é peculiaridade do Copiloto), mas
  tem a mesma consequência prática: não aparecem em `Settings`.

## Kill-switch e liga/desliga

| Variável | Default | O que muda na prática | Quando mexer |
|---|---|---|---|
| `REVY_LOJA_COPILOTO_ENABLED` | `0` (off) | Kill-switch **global** do módulo: com `0`, a seção Copiloto some do menu e as rotas em `app/web/loja_copiloto.py` respondem como desligadas — mesmo se a loja tiver o entitlement `Module.COPILOTO` liberado. Lida a **cada chamada** (não é snapshot de boot) em `app/config.py:revy_loja_copiloto_enabled()`; rotas, `app/loja/navigation.py` e os dois workers abaixo chamam essa função a cada ciclo, de propósito — para não existir o descasamento "rota abre, worker continua dormindo". | Ligar/desligar o produto inteiro no ambiente (ex.: `app2037`). Exige também `REVY_LOJA_SHELL_ENABLED=1` — o gate é duplo. |
| `PORTAL_COPILOTO_SINAIS_ENABLED` | `1` (on) — helper `env_flag` | Liga/desliga só o **worker de sinais proativos** (`app/copiloto_sinais_job.py`, regra determinística que gera os alertas — sem LLM). Snapshot no boot do processo (diferente do kill-switch acima). | Desligar o worker de sinais isoladamente (debug, incidente) sem tirar o Copiloto do ar para quem já está no chat. |
| `PORTAL_COPILOTO_TURNOS_ENABLED` | `1` (on) — helper `env_flag` | Liga/desliga só o **worker que processa as perguntas do chat** (`app/copiloto_turnos_job.py`). Com `0`, turnos ficam presos em `pendente` para sempre — a rota que abre o turno não depende deste flag. Snapshot no boot. | Mesma lógica do item acima, mas para o worker de turnos. Nunca desligar em produção sem também parar de aceitar perguntas novas (ou o dono fica esperando resposta que nunca chega). |

## Provedor de LLM (DeepSeek)

| Variável | Default | O que muda na prática | Quando mexer |
|---|---|---|---|
| `REVY_LOJA_COPILOTO_LLM_URL` | `https://api.deepseek.com` | Endpoint base do provedor (API compatível com OpenAI). | Trocar de endpoint/região do provedor. Não é troca de modelo — decisão do dono, ver `docs/copiloto-validacao.md`. |
| `REVY_LOJA_COPILOTO_LLM_KEY` | `""` (vazio) | **Secret.** Chave de autenticação do provedor. Sem ela o script de validação manual recusa rodar; em produção fica só como secret do `app2037` — nunca em `[env]` do `fly.toml`, nunca no repo. | Rotação de chave ou setup de ambiente novo. |
| `REVY_LOJA_COPILOTO_LLM_MODEL` | `DeepSeek-V4-Flash-0731` | Nome do modelo enviado em cada chamada. | Só por decisão explícita do dono — não é um lever de "melhorar qualidade" a critério do dev (ver "Se cair abaixo" em `docs/copiloto-validacao.md`). |
| `REVY_LOJA_COPILOTO_LLM_TIMEOUT` | `40` (segundos) | Timeout HTTP por chamada ao provedor. | Provedor lento/instável nos logs; ajustar com cautela — turno tem deadline própria (`PORTAL_COPILOTO_TURNO_DEADLINE_SECONDS`) que também limita isso. |
| `REVY_LOJA_COPILOTO_LLM_RETRIES` | `1` | Quantas vezes o client tenta de novo antes de desistir. | Ajuste fino de resiliência a falha transitória do provedor. |
| `REVY_LOJA_COPILOTO_HISTORICO_TOKENS` | `2000` | Teto de tokens do **bloco de histórico** enviado a cada turno (system prompt e retorno de ferramentas são separados e não entram nesta conta). | Calibrar custo/contexto conforme uso real acumular — o próprio código marca isto como "ponto de partida". |

## FIPE (fonte externa, read-only)

| Variável | Default | O que muda na prática | Quando mexer |
|---|---|---|---|
| `REVY_LOJA_COPILOTO_FIPE_URL` | `https://parallelum.com.br/fipe/api/v1` | Endpoint base da API FIPE (comunitária, sem SLA — não existe API oficial aberta). | Só se o provedor da API mudar ou sair do ar de forma permanente. |
| `REVY_LOJA_COPILOTO_FIPE_TIMEOUT` | `8` (segundos) | Timeout HTTP de cada chamada à FIPE. Estourar vira `indisponivel`, nunca um valor aproximado. | API respondendo devagar nos logs. |
| `REVY_LOJA_COPILOTO_FIPE_CACHE_SEGUNDOS` | `21600` (6h) | TTL do cache de **marca/modelo** (a tabela FIPE vira uma vez por mês; cachear reduz de 4 GETs para 2 por consulta, e para 1 quando o veículo já tem `fipe_codigo` salvo). O `/valor` **nunca** é cacheado — sempre fresco. | Reduzir ainda mais a exposição a rate limit não documentado do provedor comunitário. |

## Sinal "preço fora da faixa da FIPE" (regra 7)

Os três limiares abaixo são **calibragem de mercado, não de engenharia** — o dono
calibra com o estoque real na mão. Os defaults do código (`app/copiloto_sinais_job.py`)
são só o ponto de partida, **não** uma recomendação; por virem de env, ajustar não
exige deploy.

| Variável | Default | O que muda na prática | Quando mexer |
|---|---|---|---|
| `PORTAL_COPILOTO_FIPE_FOLGA_ALTA` | `0.30` (30%) | Caso 1 — preço >= FIPE × (1 + este valor) já dispara sozinho, mesmo em veículo recém-cadastrado. Severidade "atencao". | Estoque real mostrando que 30% acima ainda é comum na loja (subir o limiar) ou que já é destoante demais (descer). |
| `PORTAL_COPILOTO_FIPE_FOLGA_BASE` | `0.15` (15%) | Caso 2 — preço >= FIPE × (1 + este valor) **e** parado há `PORTAL_COPILOTO_FIPE_DIAS_PARADO` dias ou mais dispara com severidade "critico" (capital preso). Sozinho este limiar não dispara nada — só combinado com o de dias parado. | Mesma lógica do item acima, mas para o gatilho que também exige estar encalhado. |
| `PORTAL_COPILOTO_FIPE_DIAS_PARADO` | `60` | Quantos dias parado, junto com `FOLGA_BASE`, definem "capital preso" (caso 2). Mesmo piso usado pela regra 1 (`DIAS_ESTOQUE_PARADO`). | Ajustar o que a loja considera "encalhado" para efeito deste sinal. |
| `PORTAL_COPILOTO_FIPE_POR_CICLO` | `10` | Teto de veículos consultados na FIPE por rodada do worker de sinais — a FIPE é API comunitária sem SLA e consultar o estoque inteiro por ciclo queimaria rate limit para todo mundo. O worker prioriza quem está parado há mais tempo (`app/copiloto_sinais_job.py:_veiculos_com_fipe`) e se apoia no cache de 6h de marca/modelo (`REVY_LOJA_COPILOTO_FIPE_CACHE_SEGUNDOS`, acima) para cobrir o estoque em várias rodadas. | Estoque muito maior ou menor que o volume calibrado hoje; ou suspeita de abuso da API FIPE. |

**Quando o sinal NÃO existe** (metade da regra, não é bug se não aparecer): FIPE
indisponível para o veículo, matching ambíguo/não encontrado, ou preço abaixo da
FIPE (pode ser giro deliberado do dono) — nenhum destes casos gera sinal. A regra
pura (`regra_preco_fora_da_faixa` em `app/loja/copiloto/sinais.py`) não consulta a
FIPE; quem resolve `(veiculo, valor_fipe)` e aplica o teto é o worker.

## Ações com confirmação (banda, piso, desfazer)

| Variável | Default | O que muda na prática | Quando mexer |
|---|---|---|---|
| `PORTAL_COPILOTO_BANDA_PRECO_PCT` | `25` (%) | Banda máxima de variação de preço que `ajustar_preco` aceita propor, para mais ou para menos, em relação ao preço atual do veículo. Fora da banda → `AcaoRecusada`. | Dono decide apertar/afrouxar o quanto o Copiloto pode sugerir de mudança de preço num clique. |
| `PORTAL_COPILOTO_PRECO_MINIMO` | `1000` | Piso absoluto de preço — nenhuma ação de preço confirma abaixo disso, mesmo dentro da banda. | Ajustar para o piso real de venda da loja (evita R$ 1 "dentro da banda" de um veículo já muito barato). |
| `PORTAL_COPILOTO_DESFAZER_MINUTOS` | `30` | Janela, em minutos, em que uma ação executada pode ser desfeita pelo botão "Desfazer" no cartão. O prazo é gravado na linha (`CopilotoAcao.desfazer_ate`) no momento da execução, não recalculado na tela. | Ajustar quanto tempo de tolerância o dono tem para reverter um clique. |
| `PORTAL_COPILOTO_MAX_ACOES_HORA` | `20` | Rate-limit de quantas ações **a loja inteira** pode executar por hora — soma de todos os atores dela, não um contador por pessoa (`_checar_rate_limit`, `app/loja/copiloto/acoes.py:119-137`, filtra só por `loja_slug`). Conta TODA tentativa da última hora, inclusive as que falharam. **Lida direto em `app/loja/copiloto/acoes.py`, fora de `app/config.py`** — ver seção "Onde cada uma é lida" acima. | Suspeita de uso automatizado/abuso, ou piloto pedindo limite mais folgado. |

## Retenção e workers (turnos e sinais)

| Variável | Default | O que muda na prática | Quando mexer |
|---|---|---|---|
| `PORTAL_COPILOTO_RETENCAO_DIAS` | `90` | Contrato de retenção de conversas do Copiloto. **O job de purge ainda não existe** — hoje este valor não apaga nada sozinho; é a promessa para quando o job de limpeza for implementado. | Não mexer sem também implementar o purge — hoje é só documentação viva do contrato futuro. |
| `PORTAL_COPILOTO_TURNO_DEADLINE_SECONDS` | `45.0` | Deadline de um turno inteiro (pergunta → resposta), passado como `deadline_segundos` para `executar_turno` em `app/copiloto_turnos_job.py`. Estourar vira turno com erro, nunca fica pendurado. | Provedor de LLM consistentemente mais lento/rápido que 45s nos logs reais. |
| `PORTAL_COPILOTO_TURNO_TTL_SECONDS` | `180.0` | Janela de tempo considerada "turno em aberto" — usada em dois lugares: o worker de turnos (`app/copiloto_turnos_job.py`, TTL para reciclar turno `executando` órfão de processo morto) e a rota que abre turno novo (`app/web/loja_copiloto.py`, guarda de runaway contra `429`). As duas leituras são independentes (mesma env, dois `os.getenv` diferentes) — mudar o valor afeta as duas ao mesmo tempo. | Deploy no meio de perguntas deixando turno "preso" por tempo maior/menor que o esperado. |
| `PORTAL_COPILOTO_MAX_TURNOS_ABERTOS` | `2` | Quantos turnos `pendente`/`executando` (dentro da janela TTL acima) um usuário pode ter ao mesmo tempo antes da rota responder `429 Espere a resposta anterior terminar`. Guarda de *runaway*, não medidor comercial. | Ajustar tolerância a duplo clique / múltiplas abas do mesmo usuário. |
| `PORTAL_COPILOTO_TURNOS_INTERVAL_SECONDS` | `1.0` | Intervalo do laço do worker de turnos — de quanto em quanto tempo ele verifica se há turno `pendente` para processar. | Ajuste fino de responsividade vs. carga no banco. |
| `PORTAL_COPILOTO_TURNOS_LOTE` | `3` | Quantos turnos pendentes o worker pega por ciclo. | Ajuste fino de throughput sob pico de perguntas simultâneas. |
| `PORTAL_COPILOTO_SINAIS_INTERVAL_SECONDS` | `1800.0` (30 min) | Intervalo do laço do worker de sinais proativos (regras determinísticas: estoque parado, lead sem resposta, meta em risco etc.). | Sinais desatualizados demais / carga desnecessária recalculando com frequência alta. |
| `PORTAL_COPILOTO_SINAIS_INITIAL_DELAY_SECONDS` | `60.0` | Atraso antes da primeira rodada do worker de sinais após o boot do processo. | Coordenar com o tempo de boot do restante do Portal em ambientes mais lentos. |

## Não é env var, mas anda junto

- **Papel** e o **entitlement** `Module.COPILOTO` por loja não são variáveis de
  ambiente — são dados no banco. `REVY_LOJA_COPILOTO_ENABLED` é o interruptor do
  *deploy*; quem libera loja a loja é o entitlement. O gate de papel do Copiloto
  é `PAPEIS_GESTAO_COPILOTO` (`app/loja/copiloto/tipos.py:18`) — **não**
  `ROLES_GESTAO` (`app/loja/types.py:32`), que é o conjunto genérico de
  dono+gerente usado por outras seções da Revy Loja. `PAPEIS_GESTAO_COPILOTO`
  inclui os dois **e também `admin_plataforma`** — checar `_pode()`
  (`app/web/loja_copiloto.py:81-82`) contra `ROLES_GESTAO` faria um
  `admin_plataforma` autenticado receber 403 mesmo tendo acesso de verdade.
