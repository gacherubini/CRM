# Mercado Livre — canal de publicação (design)

Data: 2026-08-17 · Produtos: **Estoque API** (`estoque-api`) e **Revy Control** (`revy-trafego`)
Estado: **desenhado, não implementado**
Depende de [`2026-08-17-publicacao-por-canal-design.md`](2026-08-17-publicacao-por-canal-design.md).

Calibrado contra o main em `ce36207`.

Entrou no escopo com a OLX, depois da pesquisa de 17/08 (§6.1 do esqueleto). Documentação
pública, sem homologação — mas, ao contrário da OLX, **tem gate comercial por loja e é o canal
mais exigente em dado do veículo de todos**.

---

## 1. O que torna o Mercado Livre diferente

Duas coisas, e as duas mexem no que a gente guarda:

**Placa e chassi são obrigatórios.** Para publicar veículo no MLB os dois atributos são
exigidos, e a placa precisa **corresponder** ao veículo anunciado (marca, modelo, ano, versão) —
o Mercado Livre verifica. É o único canal que cobra os dois.

**O vendedor precisa de pacote contratado.** Publicação de veículo exige um pacote de anúncios
contratado **diretamente com a equipe comercial** do Mercado Livre, com duração mensal a anual.
Sem pacote, não publica — e isso não é coisa que a Revy resolve por API.

---

## 2. Decisões tomadas

| # | Decisão | Por quê |
|---|---|---|
| M1 | `modo="api"`, síncrono por item | diferente da OLX, que é lote assíncrono |
| M2 | Placa **e** chassi viram requisito bloqueante deste canal | exigência do MLB, não escolha nossa |
| M3 | Conexão OAuth **por loja** | o token representa autorização de um vendedor a uma aplicação |
| M4 | `suporta_remocao=True`, `remove_ao_vender=True` | anúncio de classificado sai quando vende |
| M5 | A descrição vai em **chamada separada** | é assim que a API funciona (§4.2) |
| M6 | Lead e perguntas ficam **fora** desta spec | outro eixo, dono é o Chatbot |

---

## 3. Modelo de dados

### 3.1 Placa deixa de ser opcional — neste canal

`Veiculo.placa` já existe: `String(7)`, **nullable**, normalizada sem hífen, com unicidade
parcial `(loja_id, placa)` quando preenchida (`models_db.py`, migration `0005_veiculo_placa`).

O formato bate exatamente: o Mercado Livre aceita 7 caracteres sem hífen ou 8 com. O nosso é o
primeiro caso, sem conversão.

O que muda é só que `placa` e `chassi` entram em `Canal.requisitos()` deste canal. Moto sem um
dos dois fica `⊘ bloqueado` no Mercado Livre e publica normal em todo o resto.

> **Não tornar `placa` obrigatória no cadastro.** A tentação é forçar no formulário já que dois
> canais querem. Mas moto em consignação ou recém-chegada entra sem placa, e travar o cadastro
> por causa de um canal que a loja talvez nem use contraria o D5 do esqueleto. O bloqueio é do
> canal, sempre.

### 3.2 A placa não pode repetir

O Mercado Livre recusa placa já usada em outra publicação. A unicidade parcial `(loja_id, placa)`
que já existe cobre o caso normal; o que ela **não** cobre é a mesma moto anunciada por duas
lojas da mesma rede.

Isso não vira código agora — vira mensagem de erro traduzida (§4.4), porque é situação de dado
errado no mundo real, não de bug.

### 3.3 Conexão Mercado Livre

No Control, mesmo molde das conexões Meta e OLX. A aplicação é criada uma vez no DevCenter do
Mercado Livre; o **token representa a autorização de um vendedor específico** à aplicação, então
é um por loja.

| Coluna | Nota |
|---|---|
| `loja_id` | unique |
| `status` | `conectado` \| `expirado` \| `revogado` \| `erro` |
| `token_ciphertext` / `refresh_token_ciphertext` | cifrados por `app/cripto.py` |
| `seller_id` | o vendedor que autorizou |
| `conectada_em` / `atualizada_em` | |

---

## 4. Publicação

### 4.1 O item

`POST /items` com o token da loja. Campos que importam:

| Campo | Vem de |
|---|---|
| `category_id` | categoria de veículos do MLB; moto é subcategoria (§7) |
| `title` | gerado: marca, modelo, versão, ano |
| `price` | `preco` |
| `currency_id` | `BRL` |
| `channel` | **`marketplace`** — obrigatório para item de classificados |
| `attributes` | `PLACA`, `CHASSI` (M2), mais marca, modelo, ano, km, cor |
| `pictures` | `fotos` por `VeiculoFoto.ordem`, via `ESTOQUE_MEDIA_PUBLIC_BASE_URL` |

> **`channel: "marketplace"`.** A documentação é explícita: sem esse campo, publicar item de
> classificados dá erro. É o tipo de detalhe que custa uma tarde quando não está escrito.

O Mercado Livre **completa atributos sozinho** a partir do catálogo de veículos dele quando
reconhece o modelo. Isso é bom e tem um efeito colateral: o anúncio pode conter dado que a gente
não mandou. Não é divergência a corrigir.

### 4.2 A descrição vem depois

A descrição **não** vai no `POST /items`. Cria-se o item sem ela e depois:

```
POST /items/{item_id}/description
```

Duas chamadas para uma publicação. O `item_id` tem que ser guardado entre as duas — e é ele que
vira `id_externo`.

### 4.3 Atualizar e remover

`PUT /items/{item_id}` atualiza. Encerrar o anúncio é mudança de status do item, não `DELETE` de
recurso — o que é bom, porque preserva histórico do lado deles.

`remove_ao_vender=True`: moto vendida sai. Classificado com moto vendida gera contato irritado,
não alcance — o oposto do raciocínio de D1 para o Instagram.

### 4.4 Erro fala a língua do lojista

| Do Mercado Livre | Na tela |
|---|---|
| sem pacote contratado | Contrate um pacote de anúncios de veículo no Mercado Livre |
| placa duplicada | Esta placa já está anunciada em outra publicação |
| placa não confere com o veículo | Placa não corresponde ao modelo informado |
| token inválido | Conta do Mercado Livre desconectada — reconecte em Tráfego |

### 4.5 Loja suspensa

`allows_processing(db, loja_id, "canal:mercado_livre")` falso → não publica; remover continua
permitido.

---

## 5. Retry — e o ponto que não fechou

A OLX é idempotente de graça (`insert` cria ou edita pelo id que a gente manda). O Mercado Livre
**não é**: `POST /items` cria um item novo toda vez. Se a resposta se perder depois de o item ter
sido criado, tentar de novo publica a mesma moto duas vezes.

É o mesmo risco do Instagram (§6.3 da spec de post), com uma diferença a favor: **o Mercado Livre
recusa placa duplicada**. A segunda tentativa provavelmente bate nessa validação e falha, em vez
de duplicar.

"Provavelmente" não é desenho, então:

> **Aberto — como tornar o create idempotente.** Duas saídas plausíveis: (a) antes de criar,
> procurar nos itens do vendedor um anúncio com a mesma placa e adotá-lo; (b) `retry="manual"`,
> como no Instagram, aceitando que um humano clique. A (a) é melhor e depende de confirmar que a
> busca por atributo do vendedor serve para isso. **Enquanto não confirmar, vale a (b)** — errar
> para o lado de um humano clicando é mais barato que anúncio duplicado.

Atualizações (`PUT /items/{id}`) são idempotentes e não têm esse problema.

---

## 6. Telas

Nada novo além da conexão no Control, ao lado da Meta e da OLX. O canal aparece no cadastro e na
tela da moto como qualquer outro.

O erro de pacote (§4.4) é o mais provável em produção e por isso está escrito como instrução, não
como código: quem lê é o lojista, e a ação é dele.

---

## 7. Testes

```bash
cd estoque-api  && .venv/bin/python -m pytest -q   # Win: .\.venv\Scripts\python.exe -m pytest -q
cd revy-trafego && .venv/bin/python -m pytest -q
```

| Teste | Por quê |
|---|---|
| moto sem placa **ou** sem chassi fica bloqueada neste canal | M2 |
| moto sem placa continua publicando na vitrine e no Instagram | §3.1; o bloqueio é do canal, não do cadastro |
| `channel` vai como `marketplace` | §4.1; sem ele a publicação falha e o motivo não é óbvio |
| descrição é enviada na segunda chamada, com o `item_id` guardado | §4.2 |
| `item_id` vira `id_externo` antes de qualquer retry | §5; sem isso o retry duplica |
| create **não** é reexecutado automaticamente enquanto §5 estiver aberto | §5 |
| `PUT` de atualização é idempotente | §5 |
| `vender()` encerra o anúncio | §4.3 |
| loja suspensa: não publica, encerra sim | §4.5 |
| token nunca aparece em mensagem de erro | invariante do `AGENTS.md` |

---

## 8. Riscos e o que fica aberto

**Aberto — idempotência do create.** §5. É o item que precisa fechar antes de implementar, e a
decisão conservadora (`manual`) já está escrita como default.

**Aberto — o `category_id` da moto.** A categoria de veículos do MLB é conhecida e moto é
subcategoria, mas o identificador exato precisa ser lido da árvore de categorias na
implementação. Tentei confirmar contra a API pública de categorias e ela recusou a leitura
automatizada. **Não inventei o código.**

**Aberto — `listing_type` para classificado de veículo.** Mesma situação: não confirmado em
fonte primária, e depende do pacote que a loja contratou.

**Aberto — vida útil do token e refresh.** Não confirmado em fonte primária. Como a conexão tem
`refresh_token_ciphertext` prevista (§3.3), o desenho suporta refresh; o intervalo se descobre na
primeira conexão.

**Risco — o pacote comercial.** É o gate mais provável de travar um piloto, e ele não é técnico:
loja sem pacote contratado não publica nada, e a Revy não tem como resolver. Confirmar isso
**antes** de escolher a loja piloto deste canal.

**Fora de escopo — perguntas e leads.** O Mercado Livre tem pergunta em anúncio e mensagem de
comprador. É atendimento, dono é o Chatbot, e nada disso entra aqui.

**Não muda:** Chatbot, n8n, Motor, e os demais canais.
