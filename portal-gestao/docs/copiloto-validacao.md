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
— falha cedo com uma mensagem, em vez de bater 42 vezes num provedor sem
chave.

## As quatro métricas (medidas separadas, §11 + I6)

1. **Acerto de tool-call** — chamou a função certa? A cadeia encadeou certo?
2. **Aderência à cobertura** — nos casos em que a ferramenta chamada devolve
   `com_dado < total` (a estrutura `Cobertura` — ver `vendas_resumo`,
   `venda_origem` e `estoque_parado`), a resposta citou isso? É a regra que
   nenhum modelo obedece de graça, e a que sustenta a confiança do dono no
   número. Das 42 perguntas da fixture, 18 têm `exige_cobertura: true` e
   entram nesta métrica — ver "Casos elegíveis" abaixo.
3. **Latência por esforço** — quanto custa em segundos um turno partindo de
   `"low"` contra um partindo de `"high"` (`--esforco`, repassado como
   `esforco_inicial` para `executar_turno`).
4. **Números rastreáveis ao payload (I6)** — de todo número que a resposta
   apresenta como fato, quantos aparecem em algum payload que uma ferramenta
   devolveu NESTA conversa? As três métricas acima medem QUAL ferramenta foi
   chamada e se um texto no formato "N de M" apareceu — nenhuma delas olha
   se os números em si batem com o que a ferramenta realmente devolveu. Esta
   é a única que mede a promessa central do produto: o modelo nunca produz
   número de cabeça.

   **O que ela FAZ:** extrai todo literal numérico da resposta (moeda,
   percentual, decimal com vírgula, inteiro), normaliza formatação BR
   (`R$ 412.000,00` → `412000.00`, igual ao `Decimal` que os `to_dict()` do
   domínio serializam como string) e confere se cada um aparece em alguma
   folha numérica (recursiva — dict e lista aninhados) de algum payload de
   ferramenta chamada naquele turno. Exclui data (`12/08`), ano solto
   (`2026`) e ordinal (`1º`) — restatement de período, não claim de negócio.

   **O que ela NÃO FAZ (limite deliberado, não bug):** não prova que o
   número está CERTO — só que ele aparece em ALGUM lugar do payload. Se o
   modelo trocar receita por ticket médio mas os dois vierem da mesma
   ferramenta, esta métrica não pega — os dois números "existem" no payload.
   Também não distingue número de negócio de ID/telefone numérico dentro do
   payload (inclui-los só alarga o conjunto aceito, nunca aperta — viés
   deliberado a favor de falso negativo, nunca falso positivo, para que o
   gate nunca "grite lobo" numa resposta correta). É um PISO de sanidade —
   detecta número inventado do zero — não uma prova de resposta correta.

## Metas de aceite

| Métrica | Meta | Por quê |
|---|---|---|
| Acerto de tool-call | ≥ 90% | Errar a função = responder outra pergunta. |
| Aderência à cobertura | ≥ 95%, **medida só sobre os casos que exigem cobertura** (18 de 42 na fixture atual) | É a regra que sustenta a confiança no número; diluir no total dos 42 casos deixaria o gate incapaz de reprovar. |
| Latência p95 (`low`) | ≤ 25s | Acima disso a espera da tela fica insustentável. |
| Números rastreáveis ao payload | Sem meta definida ainda — reportada, não é gate de go-live até o dono decidir um piso | É métrica nova (I6); precisa de uma rodada real contra o provedor antes de virar critério de reprovação. |

O dono confirma estas metas antes do go-live — não são definitivas até lá.
`Relatorio.to_markdown()` sempre mostra o denominador da cobertura por
extenso (ex. "17/18 casos que exigiam cobertura") — nunca só a porcentagem —
para que a base do número nunca seja ambígua na leitura.

**O que a meta de 95% custa na prática, com honestidade sobre o denominador
(fix round 2):** com n=18, cada caso vale 1/18 ≈ 5,6 pontos percentuais. Um
único erro cai para 17/18 = 94,4% — **ainda abaixo** dos 95% pedidos. Ou
seja, mesmo com a amostra maior, a meta de 95% continua, na prática, exigindo
zero erros nos casos de cobertura; ela não abre uma folga de "1 erro
tolerado" a menos que o dono aceite baixar a meta para algo como ~94% ou
crescer a amostra ainda mais. O ganho real do fix round 2 não foi abrir
folga — foi sair de n=6 (só 7 valores possíveis: 0%, 16,7%, 33,3%, 50%,
66,7%, 83,3%, 100% — **nenhum valor entre 83,3% e 100%**, tornando a meta de
95% um gate de zero-tolerância disfarçado de tolerante) para n=18, onde o
relatório agora consegue diferenciar "1 erro isolado" (94,4%) de "sistema
ignora a Regra 4 com frequência" (ex. 5 erros → 72,2%) — a instrumentação
antes não distinguia essas duas situações de jeito nenhum.

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
que a ferramenta que eles disparam não tem como fornecer. Testar a Regra 8
para `roi_canais` é válido, mas é outra métrica; não foi adicionada aqui.

**Amostra (fix round 2):** restavam só 6 casos elegíveis (`v03`, `v04`,
`o02`, `o03`, `o04`, `e03`) — pequeno demais para o gate ter graduação real
(ver a nota de custo do erro acima). Foram adicionados mais 12 casos
coverage-bearing, todos direcionados às 3 ferramentas verificadas para
realmente produzirem `Cobertura`:
- `vendas_resumo` (margem/lucro): `v06`–`v09`.
- `venda_origem`, escopo periodo (só ele tem `Cobertura`; escopo "ultima"
  não tem): `o05`–`o08`.
- `estoque_parado` (`cobertura_data`): `e06`–`e09`.

Total agora: 18 casos elegíveis. Um modelo bem-comportado consegue tirar
100% nesta métrica com a fixture atual — nenhum caso pede uma citação que a
ferramenta correspondente não consegue fornecer.

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

## Turno com erro nunca conta como acerto (fix round 1 + round 2, finding 6)

Um turno que falha (deadline, provedor fora, teto de tokens...) nunca deve
contar como "respondeu certo" — nem no caso sem ferramenta esperada, onde
zero tool-calls por falha no meio do caminho não é a mesma coisa que zero
tool-calls por decisão correta. O primeiro fix (round 1) corrigiu
`avaliar_caso`, mas o caminho real de `rodar_validacao` reembrulhava o
`ResultadoTurno` num `SimpleNamespace` que listava só `texto`/`passos`, e
descartava `.estado` sem querer — o guard nunca disparava de fato no CLI ou
no gate real, só nos testes que construíam o objeto à mão. Corrigido no
round 2: o wrapper agora copia **todos** os campos do `ResultadoTurno` via
`vars(resultado)` em vez de listar campos nomeados, para que um campo novo
do dataclass nunca mais seja esquecido em silêncio.

## Regressão

Rodar a suíte a cada atualização do provedor. É a única forma de detectar
quando o endpoint muda de comportamento sem aviso — risco real, dado que o
`DeepSeek-V4-Flash-0731` é recente.
