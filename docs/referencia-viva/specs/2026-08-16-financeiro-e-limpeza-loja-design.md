# Módulo Financeiro, edição de venda e limpeza das telas da Loja

**Data:** 2026-08-16
**Status:** Design aprovado pelo dono — aguardando plano de implementação
**Produtos afetados:** `portal-gestao` (Revy Loja) e `revy-trafego` (Revy Control).
Sem banco novo entre produtos; tabelas novas **dentro** do banco do Portal, mais um
módulo novo no catálogo do Control. Integração segue por HTTP/evento versionado.
**Referências verificadas no código em 2026-08-16:** `portal-gestao/README.md` (armadilhas),
`docs/referencia-viva/2026-08-07-triagem-revisao-ux-loja-control.md` (13 itens recusados),
`portal-gestao/app/financeiro_calc.py` (matemática reusada),
`revy-trafego/app/control/portfolio.py` (catálogo de módulos).

---

## 1. Resultado desejado

Cinco entregas, decididas com o dono em 2026-08-16:

1. **Módulo Financeiro** na Revy Loja — quanto cada moto lucrou e se o mês pagou a
   estrutura. Ligado/desligado por loja no Revy Control, como qualquer módulo.
2. **Remover a página Hoje** do Copiloto.
3. **Limpar a página Resultado** — saem Metas/Atingimento e Pendências.
4. **Corrigir o bug do menu** — "Resultado" fica aceso quando se está em "Vendas da loja".
5. **Editar e apagar venda**, com o efeito propagado ao Control.

## 2. Ordem de execução

**4 → 2 → 3 → 5 → 1.**

O 5 vem antes do 1 de propósito: editar venda e lançar custo direto são a mesma
capacidade. O formulário de edição da venda é o único lugar onde preço, custo do veículo e
custos diretos são alterados; a tela do Financeiro **consome** esse formulário em vez de
construir um segundo. Fazer o 1 antes significaria escrever o mesmo formulário duas vezes.

---

## 3. Tópico 4 — bug do item ativo no menu

### O defeito

`app/templates/base.html:73-83` reimplementa em Jinja a regra de "qual item do menu está
ativo" que já existe em Python (`app/loja/navigation.py:245-269`). A cópia Jinja tem as
exceções de Estoque e Copiloto, mas **não** tem a de Vendas — que existe na fonte Python,
em `navigation.py:263`:

```python
# Mesmo caso em Vendas: Resultado não acende na lista de vendas.
if item.href == "/app/loja/vendas" and path != "/app/loja/vendas":
    return False
```

Como `/app/loja/vendas/lista` começa com `/app/loja/vendas`, o `startswith` de
`base.html:82` marca "Resultado" como ativo — ganhando classe `active` e `aria-current`.
É o "hover brilhoso" e o "parece sempre selecionado" relatados. O inverso não ocorre porque
`/app/loja/vendas/lista` não é prefixo de `/app/loja/vendas`.

### A correção

Não adicionar um `elif`. Expor `nav_item_is_active` como helper de template (o Portal já
registra helpers de template em `app/main.py`) e **apagar a cadeia `if/elif` inteira** de
`base.html:73-83`, deixando:

```jinja
{% set item_active = nav_item_is_active(item, path) %}
```

Uma fonte da verdade. O bug não pode voltar por divergência entre as duas cópias — que é
exatamente como ele nasceu.

### Como saber que acabou

Teste que renderiza o shell em `/app/loja/vendas/lista` e afirma que o único item com
`aria-current="page"` é "Vendas da loja". Repetir para `/app/loja/estoque/veiculos` e
`/app/loja/copiloto/hoje` — este último até o tópico 2 apagá-lo. Verificação visual no
navegador é obrigatória: `pytest` não executa o CSS nem o JS (ver
`docs/copiloto-validacao.md` e o histórico de dois bugs que passaram por isso em 15–16/08).

---

## 4. Tópico 2 — remover a página Hoje

### O que sai

- Rota `GET /app/loja/copiloto/hoje` (`app/web/loja_copiloto.py:228`) e a constante
  `_HOJE` (`:68`).
- Template `app/templates/loja/copiloto_hoje.html`.
- `NavItem` "Hoje" em `app/loja/navigation.py:70-76`.
- Ícone `/app/loja/copiloto/hoje` do dicionário `loja_icons` (`base.html:65`).
- A exceção de `nav_item_is_active` para `/app/loja/copiloto` (`navigation.py:266-267`)
  deixa de ter razão de existir — com um item só na seção, o prefixo não colide mais.
- Testes que exercitam a rota.

### O que fica, e por quê

`montar_resumo_hoje` (`app/loja/copiloto/resumo.py`) **permanece**: a tela de chat do
Copiloto a chama em `loja_copiloto.py:192` e usa `resumo.chips` nas boas-vindas
(`copiloto.html:52-54`). Remover o resumo quebraria o chat.

Os **Sinais** não ficam órfãos. Verificado: a UI de sinais com "Já vi" / "Dispensar"
existe em dois lugares — a página Hoje e o **sino do cabeçalho**
(`base.html:171-193`, alimentado por `GET /app/loja/copiloto/notificacoes.json` e as rotas
gêmeas `notificacoes/{id}/visto` e `notificacoes/{id}/dispensar` em
`loja_copiloto.py:382-440`). O sino cobre o caso de uso inteiro depois da remoção.

Consequência de navegação: a seção "Copiloto" passa a ter um item só.

---

## 5. Tópico 3 — limpar a página Resultado

Em `app/templates/loja/vendas_visao.html`, remover:

- **Metas / Atingimento** — bloco `bloco-metas`, linhas 68-97.
- **Pendências / "Ações do período"** — bloco `bloco-pendencias`, linhas 280-295.

Permanecem: Receita e vendas, Funil, Aquisição, e De onde veio o resultado.

Limpar também o que só existia para alimentar esses dois blocos no read model
(`app/loja/sales_overview.py`): as chaves `metas`, `metas_status` e `pendencias` do
`overview`. Não remover `formatar_brl` nem nada compartilhado.

A duplicação de Vendas/Receita/Margem que o dono percebeu se resolve pelo tópico 2 — era a
página Hoje mostrando os mesmos três números.

**Metas não somem do produto:** o cadastro em `/app/metas` continua existindo e
`metas_view_periodo` segue servindo o painel legado `/app/financeiro`. O que sai é a
exibição no Resultado.

---

## 6. Tópico 5 — editar e apagar venda

### 6.1 Regra de edição por status

| Status | Editável |
|---|---|
| `registrada` | tudo (nada saiu da Loja ainda) |
| `confirmada` | apenas valores: `preco_venda`, `custo_veiculo`, custos diretos |
| `cancelada` | nada |
| `excluida` | nada (não aparece) |

O meio-termo em `confirmada` não é conservadorismo gratuito. Na confirmação
(`app/main.py:1640-1647`) o sistema **tira um snapshot de atribuição** — `campanha_id_first`,
`campanha_id_last`, `utm_campaign_first/last`, via `aplicar_snapshot_venda` — e **baixa o
veículo do estoque**. Trocar o lead depois reescreveria a origem de uma venda que o Control
já contabilizou numa campanha; trocar o veículo deixaria uma moto baixada e outra não.
Valores, sim: é exatamente o que o trilho `venda_atualizada` foi construído para corrigir.

### 6.2 Quem pode

**Dono e gerente**, para editar e para apagar. Gate no backend, não no menu.

Vendedor **não** ganha nada novo: continua podendo registrar, confirmar (decisão do dono de
2026-08-07) e cancelar com motivo. Mexer em número que já foi para o Control é outra
categoria de poder.

### 6.3 Status novo `excluida`

`app/main.py:1350` (`STATUS_VENDA`) ganha `"excluida"`. A coluna `Venda.status` é
`String(20)` sem CheckConstraint (`app/models.py:119`), então o status em si não exige
migration. Exigem migration duas colunas novas em `vendas`:

- `excluida_por: String(320) NULL`
- `excluida_em: DateTime(timezone=True) NULL`

Semântica: `cancelada` é negócio desfeito — fato comercial, fica visível no histórico.
`excluida` é registro que nunca deveria ter existido — some da tela, permanece no banco
com autoria e data.

**Restrição global — a parte arriscada desta entrega.** Toda consulta sobre `Venda` precisa
ser auditada para excluir `status == "excluida"`. As que filtram por `status ==
"confirmada"` (como `calcular_metricas_vendas`, `financeiro_calc.py:143`) já estão
cobertas por construção. As que **listam sem filtro de status** não estão — a lista de
vendas do shell é o caso óbvio, e o plano de implementação deve varrer `query(Venda)` no
Portal inteiro em vez de confiar nesta lista.

### 6.4 Propagação ao Control

O trilho existe e é reusado, não reinventado:

```
edição/exclusão → venda.atualizada_em = agora()
                → enfileirar_venda_atualizada (revy_trafego_outbox.py:114)
                → outbox transacional cifrado (Fernet)
                → POST /v1/lojas/{slug}/eventos/venda-atualizada
                → projetar_venda (vendas_projection.py:81) atualiza VendaProjetada
```

Hoje só `executar_cancelamento_venda` (`app/main.py:1694`) usa esse trilho.

O `event_id` é `revy:{slug}:venda:{id}:{status}:{atualizada_em}` — cada edição bumpa
`atualizada_em` e gera um evento novo; `projetar_venda` descarta evento mais antigo que a
versão já projetada (`vendas_projection.py:86-90`). Edições fora de ordem não corrompem a
projeção.

**Mudança no Control.** `api_venda_atualizada` (`revy-trafego/app/api_v1.py:253`) hoje
responde **400** para qualquer status fora de `{"confirmada", "cancelada"}`. Precisa
aceitar `"excluida"` e dar a ela o mesmo tratamento que `cancelada` já recebe em
`api_v1.py:256-271`: projetar o novo status e marcar como `cancelled` os itens pendentes da
`MetaCapiOutbox` daquela venda.

**Não é preciso mexer nos leitores do Control.** Verificado: todos os consumidores de
`VendaProjetada` filtram `status == "confirmada"` — `control/dashboard.py:301,316,332` e
`financeiro_calc.py:82`. Uma venda que vira `excluida` sai sozinha de toda visão geral e de
todo ROI.

### 6.5 Meta / CAPI

Purchase já entregue à Meta **não se desfaz** — não existe API de retratação e o design não
tenta fingir que existe. O que o sistema garante: se o evento CAPI ainda não saiu, ele é
cancelado na outbox do Control antes do disparo. Apagar rápido evita o envio; apagar tarde
não.

Isso precisa estar **escrito na tela de confirmação da exclusão**, não só no spec. O dono
tem que saber que uma venda confirmada há uma semana já foi para a Meta.

---

## 7. Tópico 1 — módulo Financeiro

### 7.1 Módulo no catálogo (Revy Control)

Quatro pontos, mesmo caminho que o Copiloto percorreu em 2026-08-11:

| Onde | Mudança |
|---|---|
| `revy-trafego/app/control/portfolio.py:24` | `FINANCEIRO = "financeiro"` no `ModuleCode` |
| `revy-trafego/app/models.py:71` | CHECK `codigo IN ('vendas','estoque','copiloto','financeiro')` — **exige migration** |
| `revy-trafego/app/control/provisioning.py:86` | incluir `"financeiro"` no loop de módulos operacionais |
| semente | linha nova em `modulos_revy` (`codigo='financeiro'`, `nome='Financeiro'`) |

**A UI do Control não precisa de trabalho.** Verificado: `control_ui.py:2104` passa
`"module_options": tuple(ModuleCode)` e `loja_detail.html:293-303` itera o catálogo,
rotulando com `module_option.value | capitalize`. Adicionar ao enum faz o checkbox
"Financeiro" aparecer na aba Módulos & contrato de cada loja.

### 7.2 Entitlement e gate (Revy Loja)

| Onde | Mudança |
|---|---|
| `app/loja/types.py:20-25` | `FINANCEIRO = "financeiro"` no `Module` |
| `app/loja/types.py:64-72` | `financeiro_enabled: bool = False` no `EntitlementState` |
| `app/loja/entitlements.py:22-30, 52-59` | preencher em `fail_open` e `from_allows_processing` |
| `app/loja/permissions.py:38-49` | ramo de `FINANCEIRO` em `module_enabled` |
| `app/loja/navigation.py` | seção "Financeiro" |
| `app/config.py` | flag `REVY_LOJA_FINANCEIRO_ENABLED`, **default `0`** |

Gate triplo, igual ao Copiloto: flag de rollout **e** entitlement do módulo **e** papel de
gestão. Com qualquer um dos três desligado a seção não existe — nem no menu, nem nas rotas.

### 7.3 RBAC — inegociável

**Custo do veículo e lucro nunca aparecem para vendedor.** É a primeira armadilha do
`portal-gestao/README.md` e vale para toda superfície nova deste módulo: telas, JSON,
export. O gate é de backend (`pode_ver_financeiro`, `app/auth.py:85-86`, e
`require_module` + `require_roles`), nunca esconder item de menu.

### 7.4 Modelo de custo — dois níveis que não se misturam

**Decisão do dono:** despesa fixa **não é rateada** por moto.

**Nível 1 — por moto (lucro bruto).** `preco_venda − custo_veiculo − Σ custos_diretos`.
Já implementado em `lucro_bruto_venda` (`app/financeiro_calc.py:127-132`), e a tabela
`VendaCustoDireto` (`app/models.py:136-145`) já existe com as categorias
`documentacao`, `frete`, `comissao`, `outros` (`app/main.py:1349`).

O que falta hoje: só se lança **um** custo direto, e só no formulário de registro
(`app/main.py:1574-1576`). Frete que apareceu depois, comissão fechada na semana seguinte —
não há onde lançar, e por isso a margem aparece como "Incompleto". O tópico 5 resolve isso
ao dar CRUD de custos diretos no formulário de edição da venda.

**Nível 2 — o mês (lucro operacional).** `lucro bruto do mês − despesa fixa do mês`.
Sem vínculo com venda nenhuma.

**Por que não ratear.** Jogar estrutura em cima da unidade é *custeio por absorção* —
obrigatório para balanço, mas ruim para decisão: o lucro de uma moto passaria a depender de
quantas outras foram vendidas no mês, e mudaria retroativamente a cada venda nova. Uma moto
comprada a R$ 11 mil e vendida a R$ 12 mil pode aparecer como prejuízo e fazer o lojista
recusar um negócio que era bom. O Revy já tem a regra "fonte fora → indisponível, nunca
zero" para não fabricar cifra; rateio é a mesma armadilha com outra roupa.

**O que responde a intuição por trás do rateio:** ponto de equilíbrio (§7.6).

### 7.5 Despesas fixas — tabelas novas

Recorrente com ajuste pontual por mês. Competência é `String(7)` no formato `YYYY-MM` —
rótulo de mês, sem fuso e sem ambiguidade de primeiro/último dia.

```
DespesaFixaLoja
  id                 String(36) PK
  loja_slug          String(120) index
  categoria          String(40)          # aluguel, salarios, contador, energia, marketing, outros
  descricao          String(240)
  valor_mensal       Numeric(12,2)
  inicio_competencia String(7)           # 'YYYY-MM'
  fim_competencia    String(7) NULL      # NULL = vigente; última competência em que vale
  criada_em / atualizada_em

DespesaFixaAjuste
  id           String(36) PK
  despesa_id   FK -> despesa_fixa_loja.id
  competencia  String(7)
  valor        Numeric(12,2)
  criada_em
  UNIQUE (despesa_id, competencia)
```

Despesa fixa do mês *M* = soma, sobre as despesas cuja vigência cobre *M*
(`inicio_competencia <= M` e (`fim_competencia` nulo ou `>= M`)), do valor do ajuste daquele
mês quando existir, senão do `valor_mensal`. O ajuste corrige um mês sem tocar no cadastro.

**Sem campo `ativa`, de propósito.** Um booleano de ativação e uma competência final são
duas formas de dizer a mesma coisa, e discordariam mais cedo ou mais tarde. "Desativar" na
UI grava `fim_competencia` = mês corrente: o aluguel some de setembro em diante sem
apagar o que ele valia em agosto. Meses fechados continuam corretos quando alguém revisita
o passado — que é o ponto inteiro de guardar despesa por competência.

### 7.6 Cálculo do mês e ponto de equilíbrio

**Qual data define "venda do mês".** Existe divergência já no código: o Portal recorta o
período por `criada_em` (`financeiro_calc.py:144`) e o dashboard do Control por
`confirmada_em` (`control/dashboard.py:302`). O Financeiro usa **`criada_em`**, seguindo o
Portal. O motivo: duas telas da mesma Loja mostrando números diferentes para o mesmo mês é
pior do que a Loja e o Control recortarem diferente — o lojista compara Resultado com
Financeiro toda hora, e Control com Loja quase nunca. A divergência com o Control fica
registrada aqui e não é resolvida nesta entrega.

```
receita           = Σ preco_venda das vendas confirmadas do mês
custo_vendas      = Σ custo_veiculo
custos_diretos    = Σ custos diretos
lucro_bruto       = receita − custo_vendas − custos_diretos
despesa_fixa      = §7.5
lucro_operacional = lucro_bruto − despesa_fixa

margem_media      = lucro_bruto / qtd_vendas
ponto_equilibrio  = ceil(despesa_fixa / margem_media)     # em motos
```

**Regras de indisponibilidade — a parte que mais importa acertar.** Nenhum destes casos
produz zero nem estimativa:

| Situação | Comportamento |
|---|---|
| Alguma venda confirmada do mês sem `custo_veiculo` | Lucro bruto marcado **Incompleto** com o subtotal conhecido e a contagem de vendas sem custo (mesmo padrão de `vendas_visao.html:56-60`). Lucro operacional e ponto de equilíbrio ficam **indisponíveis** — não se calcula ponto de equilíbrio sobre margem parcial |
| Nenhuma venda no mês | Ponto de equilíbrio indisponível; a tela pede vendas, não mostra `0` |
| Nenhuma despesa fixa cadastrada | Lucro operacional = lucro bruto, com aviso explícito de que não há estrutura cadastrada; ponto de equilíbrio indisponível |
| `margem_media <= 0` (mês fechou no vermelho na margem bruta) | Ponto de equilíbrio **indisponível** — nenhuma quantidade de motos com margem negativa paga a estrutura. A tela diz isso em texto, não devolve `0` nem infinito |
| Venda excluída no mês | Fora de tudo: receita, custos, lucro, contagem e ponto de equilíbrio |

"Passou do ponto no dia N" é obtido acumulando o lucro bruto por data de confirmação até
cruzar a despesa fixa — só é exibido quando o lucro bruto do mês está completo.

### 7.7 As duas telas

```
Financeiro
├── Resultado financeiro   /app/loja/financeiro
└── Despesas fixas         /app/loja/financeiro/despesas
```

**Resultado financeiro** — seletor de mês; DRE do mês (receita, custo das vendas, custos
diretos, lucro bruto, despesa fixa, lucro operacional); ponto de equilíbrio com o estado
"vendidas N · passou dia D"; e a lista de motos vendidas no mês com preço, custo, diretos e
lucro de cada uma. Cada linha leva ao formulário de edição da venda (tópico 5) — é lá que os
custos são lançados.

**Despesas fixas** — CRUD do cadastro recorrente e o ajuste do mês selecionado.

O painel legado `/app/financeiro` **não é tocado** nesta entrega: continua fora do menu do
shell, servindo a UI legada. Reusa-se a matemática (`financeiro_calc.py`), não a tela.

---

## 8. Migrations

| Produto | Migration |
|---|---|
| `portal-gestao` | `vendas.excluida_por`, `vendas.excluida_em` |
| `portal-gestao` | tabelas `despesa_fixa_loja` e `despesa_fixa_ajuste` |
| `revy-trafego` | CHECK `ck_modulos_revy_codigo` com `'financeiro'` + semente em `modulos_revy` |

`alembic upgrade head` roda **na pasta do produto certo** — cada produto tem banco e
migrations próprios. Sem `create_all` no boot: falha de migração tem de impedir readiness.

## 9. Ordem de deploy

**Control antes da Loja**, por causa do tópico 5.

`api_venda_atualizada` recusa `excluida` com 400 até o Control subir. Se a ordem inverter,
o outbox toma 400, marca `failed` e reenvia com backoff exponencial até 1h de teto
(`revy_trafego_outbox.py:257-266`) — nenhum evento é perdido, mas o Control fica com
projeção desatualizada durante a janela. Subir o Control primeiro elimina a janela.

Deploy só por `deploy/fly/3vm/`. Os `fly.toml` nas pastas dos produtos apontam para apps
monolíticos já destruídos.

## 10. Testes

- **T4:** item ativo correto em `/app/loja/vendas/lista`; `nav_item_is_active` como única
  fonte; `test_loja_navigation.py::test_shell_nav_todos_os_itens_tem_icone` segue passando.
- **T2:** rota `/hoje` some (404); chat do Copiloto continua renderizando os chips; sino
  segue listando e dispensando sinais.
- **T3:** Resultado renderiza sem os dois blocos e sem quebrar quando `overview` não traz
  mais `metas`/`pendencias`.
- **T5:** matriz de edição por status; RBAC (vendedor recebe 403 em editar e apagar); venda
  excluída some de lista, totais, funil e financeiro; evento `venda_atualizada`
  enfileirado com o status novo; Control aceita `excluida`, projeta e cancela CAPI pendente;
  evento fora de ordem não sobrescreve versão mais nova.
- **T1:** entitlement por loja liga/desliga a seção; gate triplo; **vendedor não vê custo
  nem lucro em nenhuma rota do módulo**; despesa recorrente com e sem ajuste; e cada linha
  da tabela de indisponibilidade da §7.6 — especialmente a que suprime o ponto de equilíbrio
  quando a margem está parcial.

Testes rodam **a partir da pasta do produto** (`python -m pytest -q`), senão importam o
`app` errado. Consumidores do contrato HTTP alterado (§6.4) entram na mesma leva.

Verificação no navegador é obrigatória para T4, T3 e as telas do T1 — `pytest` não executa
CSS nem JS. Se `app.css` mudar, **subir o `?v=` do `base.html`**, senão a produção serve CSS
velho.

## 11. Fora de escopo

- Rateio de despesa fixa por moto (§7.4) — decidido contra.
- Despesa variável não vinculada a venda (comissão de terceiro, taxa de cartão avulsa).
- Regime de caixa, contas a pagar/receber, conciliação bancária, DRE fiscal.
- Exportação e relatório do Financeiro.
- Retratar Purchase já enviado à Meta (§6.5) — não existe.
- Qualquer um dos 13 itens de UX recusados pelo dono em 2026-08-07.
- `/app/financeiro` legado — permanece como está.
