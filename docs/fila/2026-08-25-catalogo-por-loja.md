# Catálogo do bot é cego para loja — três saídas, uma decisão

**Produto:** `estoque-api` (dono do dado) + `chatbot-api` (consumidor) + `n8n`.
**Bloqueio:** nenhum. É decisão do dono, não pesquisa.
**Urgência:** só morde com **duas ou mais lojas no Modo 2**. Hoje o piloto tem uma.

## O buraco

`GET /v1/config/catalogo-bot` (`chatbot-api/app/main.py:1270`) responde o link do catálogo
que o bot manda quando o cliente pede para ver as motos. Ela **não lê `ctx.loja_id`**: quem
responde é `InventoryWriteClient.obter_loja()` (`app/inventory.py:461`), que bate em
`/v1/loja` do Estoque com **um bearer global**.

`/v1/loja` no Estoque é escopado pelo **token** (`ctx.loja_id`). Com um token só, toda loja
recebe o catálogo da loja daquele token. Sem erro, sem log: o cliente da loja B recebe o
link da vitrine da loja A.

**`instance` não conserta.** Aceitar o parâmetro aqui daria a impressão de estar resolvido
sem mudar de onde o dado vem — o erro descrito em
`learnings/2026-08-24-instance-nao-conserta-toda-rota.md`.

## Por que não foi consertado junto com o agente por loja

Porque as três saídas custam coisas diferentes, e nenhuma é detalhe de implementação.

### (a) O Estoque expõe `catalogo_url` na rota pública por slug

`GET /public/v1/lojas/{slug}` já existe e o chatbot já a consome por slug
(`HttpInventoryProvider.buscar`). Faltam **quatro linhas** em `_loja_publica`
(`estoque-api/app/main.py:632`).

**O que trava:** há um teste afirmando o contrário — `assert "catalogo_url" not in pub`
(`estoque-api/tests/test_publico.py`), e o comentário do código diz *"URL do bot não
precisa no HTML público"*. É minimização de dado num endpoint **não autenticado e
cacheado**, escolhida de propósito. Virar isso é reverter uma decisão registrada.

**O argumento a favor:** é literalmente a URL que o bot manda para qualquer cliente que
pedir. Não é segredo — é link de vitrine.

**O argumento contra:** hoje é preciso conversar com o bot para receber; depois, basta
adivinhar um slug para enumerar o catálogo de qualquer loja.

**Custo:** ~4 linhas + 1 teste invertido + o chatbot passando a ler por slug.

### (b) O Estoque ganha credencial de integração

Espelha o que o `chatbot-api` fez na spec §6.2 do Modo 2: `CredencialServico.loja_id`
vira **nullable**, nasce o papel `integracao`, e uma rota por slug autenticada passa a
existir para quem não tem loja.

**Custo:** migration + mudança no `get_contexto` + rota nova + a pergunta de segurança
"que credencial pode ler qualquer loja?", que é a parte cara. É card de verdade.

**A favor:** é a resposta certa se o Estoque for ganhar mais consumidores multi-loja.
Hoje ele tem um.

### (c) O chatbot guarda a URL

O `chatbot-api` já tem config por loja (`agente_config`). O link vira mais um campo do
formulário.

**Custo:** quase zero — um campo, um gerador, uma linha na tela.

**Contra, e é o que pesa:** vira **segunda fonte de verdade** para a mesma URL. O lojista
já a edita em Revy Loja → Catálogo, que escreve no Estoque. Duas caixas com o mesmo
conteúdo divergem no primeiro dia em que alguém edita uma só, e o suporte vira "mas eu
mudei lá".

## Recomendação

**(a)**, com o teste invertido no mesmo commit e o motivo escrito onde o antigo estava.
O dado é público por natureza — é o link que o bot entrega a quem pedir — e o custo das
outras duas é desproporcional ao problema (uma loja Modo 2 hoje).

Se o dono achar que enumerar catálogo por slug incomoda, então (b), e aí é card de
credencial no Estoque, não este.

**(c) não**, a menos que o dono queira mesmo o link editável junto do agente — e aí a
decisão é tirar o campo da tela de Catálogo, não ter os dois.

## Como saber que acabou

- `cd chatbot-api && .\\.venv\\Scripts\\python.exe -m pytest tests -q` (macOS: `.venv/bin/python`)
- `cd estoque-api && .\\.venv\\Scripts\\python.exe -m pytest tests -q`
- teste novo: duas lojas com catálogos diferentes, cada credencial recebe o seu.
- `n8n/validate_workflow_cloud.py`: `/v1/config/catalogo-bot` sai da lista de exceções de
  `instance` (`ROTAS_QUE_EXIGEM_INSTANCE`) e o `enviar_link_catalogo1` passa a mandá-la.
- o comentário de "dívida" some do docstring da rota e da §8 do spec do agente por loja.
