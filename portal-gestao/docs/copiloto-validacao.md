# Validação do Copiloto antes do go-live

Rodar **com dados reais de uma loja piloto**, nunca com banco vazio: metade
das perguntas só faz sentido se houver venda, estoque e lead.

A suíte de testes (`tests/test_copiloto_validacao.py`) roda inteira contra
`LLMFake` — determinística, sem rede e sem chave. Ela valida a mecânica de
avaliação (acerto de tool-call, cobertura, latência) e serve de regressão de
CI. O comando abaixo é o único caminho que fala com o provedor de verdade, e
só deve rodar manualmente, contra uma loja piloto, no go-live:

```bash
cd portal-gestao
export REVY_LOJA_COPILOTO_LLM_KEY="..."   # nunca commitar, só no ambiente
./.venv/bin/python scripts/copiloto_validacao.py --esforco low --loja-slug <slug-da-piloto>
./.venv/bin/python scripts/copiloto_validacao.py --esforco high --loja-slug <slug-da-piloto>
```

`REVY_LOJA_COPILOTO_LLM_KEY` é um **secret** do `app2037` (nunca `[env]` no
`fly.toml`, nunca no repo). O script recusa rodar sem a variável configurada
— falha cedo com uma mensagem, em vez de bater 30 vezes num provedor sem
chave.

## As três métricas (medidas separadas, §11)

1. **Acerto de tool-call** — chamou a função certa? A cadeia encadeou certo?
2. **Aderência à cobertura** — nos casos em que a ferramenta chamada devolve
   `com_dado < total` (a estrutura `Cobertura` — ver `vendas_resumo`,
   `venda_origem` e `estoque_parado`), a resposta citou isso? É a regra que
   nenhum modelo obedece de graça, e a que sustenta a confiança do dono no
   número. Só as 6 perguntas da fixture cuja ferramenta esperada realmente
   produz `Cobertura` entram nesta métrica — ver "Casos elegíveis" abaixo.
3. **Latência por esforço** — quanto custa em segundos um turno partindo de
   `"low"` contra um partindo de `"high"` (`--esforco`, repassado como
   `esforco_inicial` para `executar_turno`).

## Metas de aceite

| Métrica | Meta | Por quê |
|---|---|---|
| Acerto de tool-call | ≥ 90% | Errar a função = responder outra pergunta. |
| Aderência à cobertura | ≥ 95%, **medida só sobre os casos que exigem cobertura** (6 de 30 na fixture atual) | É a regra que sustenta a confiança no número; diluir no total dos 30 casos deixaria o gate incapaz de reprovar. |
| Latência p95 (`low`) | ≤ 25s | Acima disso a espera da tela fica insustentável. |

O dono confirma estas metas antes do go-live — não são definitivas até lá.
`Relatorio.to_markdown()` sempre mostra o denominador da cobertura por
extenso (ex. "8/9 casos que exigiam cobertura") — nunca só a porcentagem —
para que a base do número nunca seja ambígua na leitura.

## Casos elegíveis para a métrica de cobertura (fix round 1, finding 3)

`_f_roi_canais` (`app/loja/copiloto/tools.py`) **nunca** devolve
`com_dado`/`total` — só `status` (`ok`/`parcial`/`indisponivel`) e
`detalhe_disponivel` (bool). Exigir uma citação "N de M" dela forçaria um
modelo bem-comportado a inventar uma proporção que a função não devolveu,
violando a Regra 1 do prompt ("só afirma número que veio de uma chamada de
função"). Isso é a Regra 8 do prompt ("quando um dado vier
indisponível/parcial, diga isso"), não a Regra 4 (cobertura
`com_dado < total`) — são regras diferentes, com vocabulário diferente, e
esta suíte mede só a Regra 4. Por isso os 3 casos de `roi_canais` na
fixture (`m02`, `m04`, `m05`) têm `exige_cobertura: false`: pedem uma coisa
que a ferramenta que eles disparam não tem como fornecer. Restam 6 casos
elegíveis (`v03`, `v04`, `o02`, `o03`, `o04`, `e03`), todos direcionados a
ferramentas que realmente produzem `Cobertura` — um modelo bem-comportado
consegue tirar 100% nesta métrica com a fixture atual. Testar a Regra 8
para `roi_canais` é válido, mas é outra métrica; não foi adicionada aqui.

## Se cair abaixo

Nesta ordem: **subir o esforço do turno** → endurecer o prompt → limitar
ferramentas oferecidas por turno. **Não trocar de modelo** — decisão do
dono, e não é um dos levers.

`Ferramenta.esforco_sugerido` (`app/loja/copiloto/tools.py`) existe como
metadado por ferramenta, mas **não é lido em lugar nenhum** — nem em
`runner.py`, nem em `schemas()`, nem em `despachar()`. Não é um lever: não
o recomende como remédio.

## `--esforco` agora é um lever de verdade (fix round 1, finding 5)

`executar_turno` (`app/loja/copiloto/runner.py`) ganhou o parâmetro
`esforco_inicial: EsforcoLLM = "low"` — aditivo, mantém os ~18 call sites
existentes (nenhum passava esforço) 100% retrocompatíveis. `--esforco`
deste script é repassado direto para lá.

O que muda de fato ao rodar `--esforco high` versus `--esforco low`:
- Perguntas **sem ferramenta** (resolvem numa única chamada): rodam
  inteiramente no esforço pedido.
- Perguntas **com ferramenta**: a PRIMEIRA chamada ao provedor roda no
  esforço pedido (o que pode até mudar acerto de tool-call, não só
  latência); a escalada automática do runner para `"high"` depois da 1ª
  ferramenta **continua acontecendo por cima disso, sem exceção** — a
  chamada que produz a resposta final de um turno com ferramenta sempre
  acaba em `"high"`, mesmo partindo de `"low"`.

A métrica 3 reporta o esforço que cada turno **de fato atingiu** na última
chamada (pedido + escalada, via `_RegistradorEsforco`), não só o valor de
`--esforco` — os dois podem divergir para turnos com ferramenta.

## Regressão

Rodar a suíte a cada atualização do provedor. É a única forma de detectar
quando o endpoint muda de comportamento sem aviso — risco real, dado que o
`DeepSeek-V4-Flash-0731` é recente.
