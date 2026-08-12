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
2. **Aderência à cobertura** — quando uma ferramenta devolveu
   `com_dado < total`, a resposta citou isso? É a regra que nenhum modelo
   obedece de graça, e a que sustenta a confiança do dono no número.
3. **Latência por esforço** — quanto custa em segundos um turno que nunca
   chamou ferramenta ("low") contra um que chamou pelo menos uma ("high").

## Metas de aceite

| Métrica | Meta | Por quê |
|---|---|---|
| Acerto de tool-call | ≥ 90% | Errar a função = responder outra pergunta. |
| Aderência à cobertura | ≥ 95% | É a regra que sustenta a confiança no número. |
| Latência p95 (`low`) | ≤ 25s | Acima disso a espera da tela fica insustentável. |

O dono confirma estas metas antes do go-live — não são definitivas até lá.

## Se cair abaixo

Nesta ordem: **subir o esforço do turno** → endurecer o prompt → limitar
ferramentas oferecidas por turno. **Não trocar de modelo** — decisão do
dono, e não é um dos levers.

## Desvio conhecido: a flag `--esforco` não força o provedor

`executar_turno` (`app/loja/copiloto/runner.py`) não recebe um esforço
inicial de quem chama. O runner decide sozinho: todo turno começa em
`"low"`; assim que ele chama QUALQUER ferramenta, o esforço sobe para
`"high"` incondicionalmente antes da próxima chamada ao provedor — mesmo
que essa próxima chamada só produza o texto final, sem uma segunda
ferramenta. Não existe hoje uma pergunta que use ferramenta e ainda assim
custe `"low"`.

Por isso a flag `--esforco low|high` deste script **não muda o
comportamento do provedor** — ela só rotula a rodada no relatório impresso.
A métrica 3 é calculada a partir do esforço que cada turno **de fato
atingiu** (observado por `_RegistradorEsforco`, que envolve o `llm` passado
e registra o parâmetro `esforco` de cada chamada), não a partir da flag.

Consequência prática para calibrar a política (§11): como toda pergunta com
ferramenta já roda em `"high"`, subir o "esforço do turno" como primeiro
lever de mitigação (ver seção acima) significa, na prática, subir o teto
(`max_iteracoes`, `deadline_segundos`, `teto_tokens` em
`executar_turno`) ou o `esforco_sugerido` por ferramenta — não uma flag de
runtime deste script. Se o dono quiser comparar `"low"` forçado versus
`"high"` forçado turno a turno, `executar_turno` precisaria ganhar um
parâmetro de esforço inicial explícito; isso está fora do escopo desta
tarefa (suíte de validação) e não foi alterado aqui para não arriscar os
testes já verdes de `app/loja/copiloto/runner.py`.

## Regressão

Rodar a suíte a cada atualização do provedor. É a única forma de detectar
quando o endpoint muda de comportamento sem aviso — risco real, dado que o
`DeepSeek-V4-Flash-0731` é recente.
