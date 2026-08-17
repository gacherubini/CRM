# OLX — canal de publicação (design)

Data: 2026-08-17 · Produtos: **Estoque API** (`estoque-api`) e **Revy Control** (`revy-trafego`)
Estado: **desenhado, não implementado**
Depende de [`2026-08-17-publicacao-por-canal-design.md`](2026-08-17-publicacao-por-canal-design.md).

Calibrado contra o main em `ce36207`.

A OLX entrou no escopo depois da pesquisa de 17/08 (§6.1 do esqueleto), que procurava agregador
e encontrou três portais autoatendidos. **É o canal externo mais barato de todos**: documentação
pública e completa, sem homologação formal, sem prazo externo, e moto é categoria de primeira
classe.

---

## 1. Por que a OLX é diferente de tudo que veio antes

| | Webmotors | Catálogo Meta | **OLX** |
|---|---|---|---|
| Documentação | pública | pública | **pública e completa** |
| Homologação | sim, 90 dias | não | **não** |
| Prazo externo | semanas | nenhum | **nenhum** |
| Custo para a Revy | homologar | zero | **um e-mail** |

O único portão é obter `client_id` e `client_secret`, que se pede por e-mail a
`suporteintegrador@olxbr.com` com os dados da empresa. Não há App Review, não há ambiente de
homologação com relógio correndo, não há contrato de parceiro.

O gate comercial existe, mas é **do lojista**: a OLX vende slots de anúncio, e estourar o que a
conta tem contratado devolve erro (§4.4).

---

## 2. Decisões tomadas

| # | Decisão | Por quê |
|---|---|---|
| O1 | `modo="api"`, mas em **duas fases** | a importação é assíncrona: manda e depois confere (§4.2) |
| O2 | `retry="idempotente"` | `operation: "insert"` **cria e edita**, distinguido pelo `id` que a gente manda. Reenviar converge por construção |
| O3 | `suporta_remocao=True`, `remove_ao_vender=True` | `operation: "delete"` existe e é uma linha |
| O4 | Referência curta própria, **não** `veiculo.id` | o `id` da OLX aceita 19 caracteres e o nosso é UUID de 36 (§3.1) |
| O5 | Conexão OAuth **por loja**, guardada no Control | o token representa a conta do lojista na OLX |
| O6 | Lead da OLX fica **fora** desta spec | a OLX devolve lead e webhook; é outro eixo, e o Chatbot é dono dele |

---

## 3. Modelo de dados

### 3.1 A referência curta — o detalhe que quebraria tudo

A OLX exige `id` **alfanumérico de 1 a 19 caracteres**, único na conta do lojista. O
`Veiculo.id` é `String(36)` — UUID. **Não cabe.**

Truncar UUID é tentador e errado: 19 dos 36 caracteres não são garantia de unicidade, e colisão
aqui significa uma moto sobrescrevendo o anúncio da outra silenciosamente.

`veiculo_canal` ganha `ref_curta`, inteiro sequencial **por loja**, atribuído na primeira
publicação e imutável depois. Cabe folgado, é único por conta, e é estável — que é o que a
semântica de "insert edita se o id já existe" exige. Mudar a `ref_curta` de uma moto criaria um
anúncio novo e deixaria o antigo órfão.

### 3.2 Conexão OLX

No Control, mesmo molde de `google_ads_connections` (`revy-trafego/app/models.py:817`) e da
conexão Meta:

| Coluna | Nota |
|---|---|
| `loja_id` | unique |
| `status` | `conectado` \| `expirado` \| `revogado` \| `erro` |
| `token_ciphertext` | cifrado por `app/cripto.py` |
| `refresh_token_ciphertext` | se houver — ver §7 |
| `conectada_em` / `atualizada_em` | |

### 3.3 O que já existe e serve

| Campo da OLX | Vem de |
|---|---|
| `zipcode` | `lojas.endereco_cep` — **coluna criada pela spec do catálogo Meta** |
| `phone` | `lojas.whatsapp` (10–11 dígitos, DDD + número, sem máscara) |
| `images` | `fotos` por `VeiculoFoto.ordem`, via `ESTOQUE_MEDIA_PUBLIC_BASE_URL` |

O CEP é reuso direto: a coluna nasce na spec do catálogo Meta por exigência da Meta, e a OLX
cobra o mesmo dado. Uma migration serve dois canais.

---

## 4. Publicação

### 4.1 O envelope

```
PUT https://apps.olx.com.br/autoupload/import
Content-Type: application/json; charset=utf-8      (máx. 1 MB)

{ "access_token": "...", "ad_list": [ { "id": "...", "operation": "insert", ... } ] }
```

Campos por anúncio, todos confirmados na documentação:

| Campo | Regra |
|---|---|
| `id` | 1–19 alfanumérico → `ref_curta` (§3.1) |
| `operation` | `insert` (cria **e** edita) \| `delete` |
| `subject` | 2–90 — título gerado: marca, modelo, versão, ano |
| `body` | 2–6.000 — descrição gerada |
| `phone` | 10–11 dígitos, só DDD + número |
| `type` | `s` (venda) |
| `price` | **inteiro, sem decimais** — `preco` arredondado |
| `zipcode` | numérico |
| `images` | array de URLs, **máx. 20**, a primeira vira a capa. Obrigatórias desde jan/2025 |
| `category` | inteiro; moto é subcategoria de Autos |

> **`price` é inteiro.** `Veiculo.preco` é `Numeric(12,2)`. O arredondamento acontece no
> adaptador e tem teste, porque mandar centavos aqui é erro silencioso: a OLX não devolve
> "formato inválido", ela interpreta errado.

### 4.2 Duas fases

O `PUT` **não** confirma publicação — devolve um token de importação. O estado real vem depois:

```
PUT  /autoupload/import            → token da importação
GET  /autoupload/import/{token}    → status daquele lote
GET  /autoupload/ads/{list_id}     → status de um anúncio publicado
```

Isso é uma terceira forma, diferente do `api` síncrono (Instagram devolve o id na hora) e do
`feed` (a Meta busca). O worker precisa de um passo de confirmação:

```
desejado=true, estado=pendente   → PUT import, guarda o token, fica em 'pendente'
próxima passada                  → GET import/{token}; ok vira 'publicado' com list_id
```

O `list_id` devolvido é o `id_externo`.

> Isso **não** cria estado novo em `veiculo_canal` (§3.3 do esqueleto): "mandou e ainda não
> confirmou" continua sendo `pendente`, que é exatamente o que ele significa. O token da
> importação cabe em `id_externo` até o `list_id` chegar e tomar o lugar.

### 4.3 Por que o retry é idempotente

`operation: "insert"` cria se o `id` não existe e edita se existe. Reenviar o mesmo anúncio
converge para o mesmo estado — não há risco de anúncio duplicado, que é o que obriga o
Instagram ao retry manual.

É por isso que a OLX é o canal `api` mais fácil: o worker do esqueleto (§4.1) funciona nela sem
nenhuma exceção.

### 4.4 Slots — o gate comercial

Estourar o número de slots contratados devolve **status `-7`**. Não é falha nossa e não adianta
tentar de novo.

Tratamento: `estado='erro'` com *"Limite de anúncios da conta OLX atingido — contrate mais
slots"*, e **sem** reagendar. É o oposto do rate limit do Instagram (§6.4 da spec de post): lá
esperar resolve, aqui só o lojista resolve.

### 4.5 Loja suspensa

`allows_processing(db, loja_id, "canal:olx")` falso → não publica. Remover continua permitido
(§4.5 do esqueleto).

---

## 5. Remoção

```json
{ "id": "1042", "operation": "delete" }
```

Só isso. `suporta_remocao=True` e `remove_ao_vender=True`: moto vendida sai da OLX, ao contrário
do post do Instagram — porque anúncio de classificado com moto vendida é reclamação de
comprador, não alcance acumulado.

---

## 6. Telas

Nenhuma tela nova além da conexão. O canal aparece no bloco "Publicar em" do cadastro e na tela
da moto, como qualquer outro — que era a promessa do esqueleto.

No Control, aba Tráfego, ao lado da conexão Meta:

```
Conexão OLX
────────────────────────────────────────────────
Status      ● conectado
            [ Reconectar ]
```

---

## 7. Testes

```bash
cd estoque-api  && .venv/bin/python -m pytest -q   # Win: .\.venv\Scripts\python.exe -m pytest -q
cd revy-trafego && .venv/bin/python -m pytest -q
```

| Teste | Por quê |
|---|---|
| `ref_curta` cabe em 19 caracteres e é estável entre publicações | §3.1; se mudar, cria anúncio novo e órfã o antigo |
| `ref_curta` é única por loja | colisão sobrescreve anúncio de outra moto em silêncio |
| `price` vai inteiro, sem centavos | §4.1; a OLX não reclama, ela interpreta errado |
| reenviar o mesmo anúncio não duplica | §4.3, a base do retry idempotente |
| lote respeita 1 MB | payload maior é rejeitado inteiro, não parcialmente |
| no máximo 20 imagens, capa é a de menor `ordem` | §4.1 |
| status `-7` vira erro **sem** reagendar | §4.4; reagendar aqui é laço infinito contra um limite comercial |
| `delete` ao vender | §5 |
| loja suspensa: não publica, remove sim | §4.5 |
| token/`client_secret` nunca aparecem em mensagem de erro | invariante do `AGENTS.md` |

---

## 8. Riscos e o que fica aberto

**Aberto — o inteiro da categoria de moto.** A documentação confirma que moto é subcategoria de
Autos, mas o valor exato precisa ser lido da tabela de categorias da OLX na implementação. Não
inventei o número.

**Aberto — vida útil e refresh do token.** A documentação de OAuth descreve o *authorization
code* (expira em 10 minutos, uso único) mas **não** documenta o tempo de vida do `access_token`
nem o refresh. Descobre-se na primeira conexão real. Se não houver refresh, a conexão vira
reconexão manual periódica e isso muda a tela de §6.

**Aberto — planos.** Há indicação de que plano de vendedor autônomo não permite integração por
API, só plano Empresa. Confiança média, e é pergunta comercial: as lojas piloto precisam estar
no plano certo antes de qualquer teste.

**Fora de escopo — lead.** A OLX devolve lead e tem webhooks. Isso não é publicação e o dono
desse eixo é o Chatbot. Registrado aqui só para não se perder: **a OLX gera lead e hoje ele não
entra na Revy por lugar nenhum** — igual à Webmotors (§6.1 do esqueleto).

**Não muda:** Chatbot, n8n, Motor, e os demais canais.
