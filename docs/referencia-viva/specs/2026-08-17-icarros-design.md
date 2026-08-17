# iCarros — canal de publicação (design)

Data: 2026-08-17 · Produtos: **Estoque API** (`estoque-api`) e **Revy Control** (`revy-trafego`)
Estado: **desenhado, bloqueado por uma pergunta** — ver §1.2
Depende de [`2026-08-17-publicacao-por-canal-design.md`](2026-08-17-publicacao-por-canal-design.md).

Calibrado contra o main em `ce36207`. Levantado em 17/08 contra o OpenAPI oficial do iCarros.

---

## 1. Duas descobertas, uma boa e uma que pode matar o canal

### 1.1 A documentação existe

Um levantamento anterior concluiu que o iCarros não tinha documentação pública e que o caminho
seria contato comercial. **Errado.** Existe um OpenAPI 2.0 vivo, servido pelo próprio iCarros e
sem autenticação:

| | |
|---|---|
| Spec | `https://www.icarros.com.br/rest/swagger.json` |
| Swagger UI | `https://www.icarros.com.br/apidocs/index.html` |
| Manual de OAuth | `https://www.icarros.com.br/apidocs/apiOauth.html` |

Título `iCarros API`, versão `2.0.0`, descrição *"API para gerenciamento de anúncios no iCarros"*,
`host: paginasegura.icarros.com.br`, `basePath: /rest`. **54 rotas, 35 definições.**

Ela não aparece em busca porque **não está linkada em nenhuma navegação do site**. É
pública-mas-não-divulgada, não inexistente. A lição vale além deste canal: "não achei em busca"
não é "não existe".

### 1.2 A pergunta que bloqueia

**O modelo de dados aceita moto. A vitrine, aparentemente, não.**

A favor, tudo confirmado na spec oficial:
- o parâmetro `segmento` está descrito literalmente como *"Carro, Moto ou Caminhao."*
- `Categoria.segmento` é o enum `["CARRO", "CAMINHAO", "MOTO"]`
- `Dealer.segments` é *"lista de segmentos que o anunciante atua (CARRO, MOTO, CAMINHAO)"*
- **todo** o catálogo é parametrizado por segmento: `/makes/{segmento}`, `/models/{segmento}`,
  `/trims/{segmento}`, `/equipments/{segmento}`

Contra, tudo observado de fora:
- `icarros.com.br/comprar/motos` devolve 200 mas renderiza a busca genérica de carro — título
  *"comprar carros em todo o Brasil"*, meta *"0 ofertas de carros"*. É 200 falso, não vertical
- a central de ajuda ao consumidor não tem **um** artigo sobre anunciar moto; o de "informações
  necessárias para criar um anúncio" fala só de carro
- o objeto `Deal` tem `doors` (número de portas) e **nenhum campo de cilindrada** — o esquema do
  anúncio tem forma de carro

> **Esta spec não deve virar código antes da resposta.** A pergunta é uma só, para
> `api@icarros.com.br`: *o segmento MOTO está ativo para anunciante PJ no marketplace, ou existe
> apenas no modelo de dados?* Se a resposta for "só no modelo", o canal morre aqui e a spec vira
> registro de por quê. É uma pergunta de e-mail, não um projeto — e ela vem **antes** de tudo.

---

## 2. Decisões tomadas

| # | Decisão | Por quê |
|---|---|---|
| I1 | `modo="api"`, REST | §3 |
| I2 | **Authorization Code**, nunca password grant | §3.1 — o próprio iCarros desaconselha o outro |
| I3 | `suporta_remocao=True`, `remove_ao_vender=True` | `DELETE` de anúncio existe |
| I4 | Conexão OAuth **por loja**, guardada no Control | §3.1 |
| I5 | Implementação só depois da resposta de §1.2 | não construir sobre enum possivelmente legado |

---

## 3. O protocolo

```
GET    /rest/dealerservice/dealer                              # lojas que o login alcança
GET    /rest/dealerservice/dealer/{dealerId}/inventory         # estoque atual
POST   /rest/dealerservice/dealer/{dealerId}/inventory/new     # cria
PUT    /rest/dealerservice/dealer/{dealerId}/inventory/{id}    # atualiza
DELETE /rest/dealerservice/dealer/{dealerId}/inventory/{id}    # remove
POST   /rest/imageservice/upload/deal/{dealId}                 # foto: base64 ou URL, máx. 3 MB
DELETE /rest/dealerservice/dealer/{dealerId}/inventory/{id}/image/{imageId}
GET    /rest/dealerservice/dealer/{dealerId}/inventory/{id}/orderimages/{ids}
GET    /rest/databaseservice/{makes|models|trims|equipments|category}/{segmento}
GET    /rest/databaseservice/{colors|fueltypes|transmissions}
```

Criar devolve `{"httpStatus": 200, "mensagem": "Anuncio salvo com sucesso", "anuncioId": 12345678}`
— e o `anuncioId` vira `id_externo`.

`GET /dealerservice/dealer` é a primitiva de multi-loja: devolve as revendas que aquele token
alcança. É por ela que a conexão descobre o `dealerId`, em vez de a Revy pedir ao lojista.

### 3.1 Autenticação — e o aviso que o iCarros dá

Keycloak em `accounts.icarros.com`, `Bearer`, `expires_in: 3600` (1 hora), com `refresh_token` e
escopo `offline_access` para renovação indefinida. O fluxo declarado na spec é `accessCode`
(Authorization Code), com os escopos `anunciantepj` (*"acesso à gestão do(s) anunciante(s) PJ
relacionados ao usuário"*) e `gruporegional`.

O iCarros nomeia o nosso caso de uso e desaconselha o atalho, textualmente:

> *"Esse método [Resource Owner Password Credentials] deve ser utilizado apenas por aplicações
> que possuem senhas do iCarros, e **não por aplicações que tratam de dados de terceiros (ex:
> integrador que atualiza o estoque de uma loja, e para isso armazena a senha desta loja)**. Por
> esse motivo, este método pode estar bloqueado para a maioria dos clientes e não funcionar."*

Isto resolve, para este canal, a tensão levantada em §6.2 do esqueleto: o padrão de mercado de
guardar login e senha da loja é **o caminho desaconselhado pelo próprio portal**, e possivelmente
bloqueado. I2 escolhe o consentimento: a Revy redireciona o lojista para `accounts.icarros.com`,
ele aprova, e a Revy guarda um refresh token — nunca uma senha.

`client_id` e `client_secret` são emitidos **à mão**, pela central de atendimento. Não há cadastro
autoatendido, não há console de app, não há sandbox documentado.

### 3.2 O anúncio

O campo obrigatório do `Deal` é **um só: `trimId`** — a versão, resolvida do catálogo. O resto é
opcional na spec: `makeId`, `modelId`, `productionYear`, `modelYear`, `doors`, `colorId`, `km`,
`price`, `priceResale`, `fuelId`, `plate`, `photosIds[]`, `equipmentsIds[]`, `text`, `publishes[]`.

**`chassi` e `renavam` não aparecem uma vez na spec inteira.** Como na Webmotors, e ao contrário
do Mercado Livre.

A `placa` é opcional. O trabalho real é o mesmo da Webmotors: resolver marca, modelo e versão do
texto livre da Revy para os ids do catálogo do iCarros — só que aqui o catálogo é REST e
parametrizado por segmento, o que é mais fácil de consultar e cachear.

`priceResale` tem o mesmo cheiro do `PrecoRevenda` da Webmotors: **não recebe `custo`** enquanto
o significado não for confirmado.

### 3.3 Fotos

`POST /imageservice/upload/deal/{dealId}` aceita **base64 ou URL**, máximo **3 MB** por imagem. A
opção por URL é a boa: a Revy já expõe mídia pública por `ESTOQUE_MEDIA_PUBLIC_BASE_URL`, então
não precisa carregar bytes.

A ordem é definida à parte, por `orderimages`. O limite de quantidade existe em
`/databaseservice/deal/numberImages`, mas o valor está atrás de autenticação.

---

## 4. Criar provavelmente não é idempotente

A spec não declara chave externa do integrador para o `Deal` — o `idExternal` que existe pertence
ao fluxo de montadora, não ao de revenda. O `anuncioId` é atribuído pelo servidor.

Presunção conservadora, igual à Webmotors: **criar duplica**. O adaptador ramifica por
`id_externo` (vazio → `POST /new`, preenchido → `PUT`), e
`GET /dealerservice/dealer/{id}/inventory` é a primitiva de reconciliação.

Confirmar no primeiro contato, junto com limite de requisições — a spec não traz `429` nem
documentação de rate limit.

---

## 5. Testes

```bash
cd estoque-api  && .venv/bin/python -m pytest -q   # Win: .\.venv\Scripts\python.exe -m pytest -q
cd revy-trafego && .venv/bin/python -m pytest -q
```

| Teste | Por quê |
|---|---|
| `id_externo` vazio faz `POST /new`; preenchido faz `PUT` | §4; se inverter, duplica anúncio |
| `anuncioId` é persistido antes de qualquer retry | §4 |
| `custo` não vai em `priceResale` nem em campo nenhum | §3.2 |
| foto é enviada por URL, e maior que 3 MB é recusada antes de sair | §3.3 |
| segmento enviado é `MOTO` | §1.2; se um dia virar `CARRO` por engano, o anúncio sai errado e ninguém vê |
| `refresh_token` renova sem intervenção; senha nunca é guardada | I2 |
| token nunca aparece em log nem em erro | invariante do `AGENTS.md` |

---

## 6. Riscos e o que fica aberto

**Bloqueador — moto no marketplace.** §1.2. Uma pergunta de e-mail. **Nada começa antes dela.**

**Aberto — tudo que está atrás de credencial.** As listas de catálogo, o
`/deal/numberImages`, os códigos de erro reais e o comportamento de idempotência retornam 302 sem
`client_id`. Só se conhece depois que o iCarros emitir credencial.

**Aberto — rate limit e política de homologação.** A spec não traz nem um nem outro. Não há
sandbox documentado, o que é diferente da Webmotors (que tem ambiente de homologação com prazo) e
da OLX (que não precisa).

**Risco — a de-para de catálogo.** Mesmo problema da Webmotors (§4.3 de lá): texto livre da Revy
para `trimId` do iCarros. Aqui é mais fácil de consultar, mas o esforço de casamento é o mesmo.

**Risco — credencial à mão.** Sem autoatendimento, cada etapa depende de alguém responder e-mail.
Isso não é bloqueio técnico, é prazo de calendário sem previsão — e é por isso que este canal é o
último da fila.

**Contato:** `api@icarros.com.br`, declarado como `contact.email` na própria spec oficial. É a
porta certa; `faleconosco@` é atendimento ao consumidor.
