# Catálogo Meta por feed (design)

Data: 2026-08-17 · Produtos: **Estoque API** (`estoque-api`), **Revy Control** (`revy-trafego`),
**Revy Loja** (`portal-gestao`) e **Catálogo Público** (`catalogo-publico`)
Estado: **desenhado, não implementado**
Depende de [`2026-08-17-publicacao-por-canal-design.md`](2026-08-17-publicacao-por-canal-design.md),
que entrega o registry de canais, `veiculo_canal` e o worker. Esta spec é o **primeiro canal
externo** e o primeiro do tipo `feed`.

Calibrado contra o main em `ce36207`. Estoque em `0010_loja_catalogo_url`, Control em
`0020_loja_whatsapp_modo`.

---

## 1. O que é o catálogo, medido

### Não é post

Catálogo não tem URL, não tem visitante e não é publicação. É uma tabela dentro do Commerce
Manager do Business Manager **da loja**, com uma linha por moto. Ninguém navega um catálogo.

Quem consome é o **anúncio de estoque automotivo**: uma campanha cujo criativo é um molde
(imagem, título, preço, destino) preenchido pela Meta uma vez por linha do catálogo. O gestor
de tráfego monta a campanha uma vez; moto nova entra no feed e já é anunciável, preço mudou e
o anúncio muda junto, vendeu e o anúncio para.

### O circuito que isso fecha

```
pessoa abre /l/{slug}/veiculos/{id} no catálogo público
      ↓  vehicle.html:47 dispara ViewContent com content_ids: [veiculo.id]
a Meta registra que essa pessoa olhou o item <veiculo.id>
      ↓  a campanha procura <veiculo.id> no catálogo
anúncio daquela moto, com foto e preço vindos do feed
      ↓  clique volta para /l/{slug}/veiculos/{id}
o CTA dispara Lead (vehicle.html:56), que já existe
```

Hoje a ponta de cima está aberta: o pixel manda um id que a Meta não reconhece, porque não há
catálogo onde procurá-lo. Esta spec fecha o circuito.

### O que já existe e vai ser reusado

| Peça | Onde | Serve para |
|---|---|---|
| `content_ids: ['{{ veiculo.id }}']` | `catalogo-publico/app/templates/vehicle.html:39` | **a chave de junção já bate** com o `vehicle_id` do feed |
| `GET /l/{slug}/veiculos/{vehicle_id}` | `catalogo-publico/app/main.py:460` | o campo `url` de cada linha |
| `ESTOQUE_MEDIA_PUBLIC_BASE_URL` | `estoque-api/app/config.py:18` | URLs públicas das fotos, que a Meta baixa |
| `lojas.catalogo_url` chegando por provisionamento | `0010_loja_catalogo_url`, `revy-trafego/app/control/provisioning_outbox.py` | **precedente exato** do trilho do endereço (§3.2) |
| `MetaAdsConfig` / `MetaPixelConfig` na aba Tráfego | `revy-trafego/app/models.py:580` e `:561` | onde a tela de instalação encosta (§6.1) |
| `allows_processing()` fail-closed | `estoque-api/app/provisioning.py` | gate de loja suspensa (§4.5) |

---

## 2. Decisões tomadas

Decididas com o dono em 17/08.

| # | Decisão | Por quê |
|---|---|---|
| C1 | **Feed agendado, não API** | a Meta busca um arquivo nosso; sem app, sem token, sem `catalog_management`, sem App Review |
| C2 | Estado exibido é **`no feed`**, nunca `publicado` | o feed não devolve resposta; dizer "publicado" seria afirmar o que não se sabe |
| C3 | **Loja suspensa gera feed vazio** | arquivo vazio remove tudo: é "não publica, mas despublica" da §4.5 do esqueleto, de graça |
| C4 | **CSV**, cabeçalhos em inglês | formato mais simples que a Meta aceita; ela exige cabeçalho em inglês |
| C5 | **Basic auth por loja**, segredo gerado pelo Estoque | sem isso o estoque da loja fica numa URL adivinhável |
| C6 | Instalação **manual** no Commerce Manager | 5 minutos por loja contra semanas de App Review; automatizar exige exatamente o que C1 evita |
| C7 | Endereço é **coluna da loja**, dono no Control | é fato da loja, não do canal; Webmotors e iCarros vão querer o mesmo |
| C8 | Chassi é **campo do `Veiculo`**, nullable | não é "campo da Meta"; se o Webmotors pedir, já está lá |
| C9 | `title`, `description` e `state_of_vehicle` são **gerados** | nenhum exige digitação nem migration |
| C10 | `content_type` do pixel passa de `product` para `vehicle` | sem isso o pixel e o catálogo não se juntam e o remarketing não faz nada |

---

## 3. Modelo de dados

### 3.1 `veiculos.chassi`

Coluna nova, `String(17)`, **nullable**. Não é obrigatória no cadastro: é requisito do canal
`catalogo_meta`, cobrado por `Canal.requisitos()` como qualquer outro. Moto sem chassi cadastra
normal, aparece na vitrine, e fica `⊘ bloqueado` só neste canal.

Ganha o mesmo tratamento de `placa`: normalizada em maiúsculas, sem espaço nem hífen.

> **Não vira unique.** A tentação é `unique (loja_id, chassi)` por analogia com `placa`. Placa
> é do país e chassi é do fabricante — mas o dado é digitado, e um erro de digitação que colida
> com outra moto travaria o cadastro por um motivo que ninguém entenderia na tela. Duplicata de
> chassi não quebra o feed.

### 3.2 Endereço da loja

Hoje **não existe em produto nenhum**: nem `lojas` do Control (`id`, `slug`, `nome`, `status`,
`versao`, `whatsapp_modo`), nem `lojas` do Estoque (`id`, `nome`, `slug`, `whatsapp`,
`catalogo_url`); o Portal não tem tabela de lojas, só projeção por `loja_slug`.

Quatro colunas, **nas duas tabelas**. País é sempre `BR` e não vira coluna.

| Coluna | Tipo | Exemplo |
|---|---|---|
| `endereco_logradouro` | `String(200)` | Av. Brasil, 1200 |
| `endereco_cidade` | `String(120)` | Vitória |
| `endereco_uf` | `String(2)` | ES |
| `endereco_cep` | `String(9)` | 29050-000 |

**Dono é o Control** (`AGENTS.md`: Control é dono de lojas). A cópia no Estoque existe porque
é ele que gera o arquivo, e não vai perguntar o endereço ao Control a cada linha.

O trilho já existe e não se inventa nada: é o mesmo do `catalogo_url` — coluna em `lojas` do
Estoque, carregada pelo provisionamento do Control (`provisioning_outbox.py`). Endereço entra
no mesmo carregamento.

### 3.3 Credencial do feed

Uma linha por loja, no Estoque:

| Coluna | Nota |
|---|---|
| `loja_id` | PK |
| `usuario` | derivado do slug |
| `senha_hash` | **hash**, não cifra — o Estoque só precisa conferir, nunca reexibir |
| `ultima_busca_em` | datetime \| null — o sinal de §6.1 |
| `criada_em` | |

A senha em claro aparece **uma vez**, na geração, na tela do Control. Perdeu, gera outra: é
mais barato que guardar segredo reversível para uma comodidade.

### 3.4 Migrations

| Produto | Migration | O quê |
|---|---|---|
| Estoque | após `0011_publicacao_por_canal` | `veiculos.chassi`, endereço em `lojas`, tabela da credencial |
| Control | após a que o `CanaisControl` criar (hoje em `0020`) | endereço em `lojas` |

Nenhuma migration no Portal e nenhuma no Catálogo Público.

---

## 4. O feed

### 4.1 A rota

```
GET /feeds/{loja_slug}/catalogo-meta.csv     (Basic auth)
```

Gerado na hora, a partir do estado atual. **Não há arquivo em disco, não há cache, não há
job.** Um `SELECT` e um CSV. É o que dá à §4.1 do esqueleto ("auto-cura") o caso trivial:
não existe estado intermediário para divergir.

A Meta busca **de hora em hora** — é o piso dela; mais rápido não existe.

### 4.2 O mapa de campos

Obrigatórios da Meta, todos resolvidos:

| Campo Meta | Vem de | Como |
|---|---|---|
| `vehicle_id` | `veiculo.id` | direto — **já bate com o pixel** |
| `vin` | `veiculo.chassi` | §3.1 |
| `make` / `model` | `marca` / `modelo` | direto |
| `year` | `ano_modelo` | direto |
| `mileage` | `km` | com unidade `KM` |
| `price` / `currency` | `preco` / `BRL` | direto |
| `exterior_color` | `cor` | requisito bloqueante (hoje nullable) |
| `images` | `fotos`, ordenadas por `VeiculoFoto.ordem` | URL pública via `ESTOQUE_MEDIA_PUBLIC_BASE_URL` |
| `url` | `/l/{slug}/veiculos/{id}` | `main.py:460` |
| `address` | `lojas.endereco_*` | §3.2 |
| `title` | gerado | `marca modelo versão ano` |
| `description` | gerado | `marca modelo versão ano · N km · cor` |
| `state_of_vehicle` | derivado | `km == 0` → `NEW`, senão `USED` |
| `body_style` | fixo | `OTHER` — ver §4.3 |

`vehicle_type = MOTORCYCLE` é opcional na Meta e vai junto por §4.3.

### 4.3 A dobra da moto

O `body_style` da Meta é enum de carro: `SEDAN`, `SUV`, `HATCHBACK`, `PICKUP`, `TRUCK`,
`COUPE`… e `OTHER`. **Não tem motocicleta.** Motocicleta existe em outro campo, `vehicle_type`,
que aceita `MOTORCYCLE` — e esse é opcional.

Então, para moto: `body_style=OTHER` **e** `vehicle_type=MOTORCYCLE`.

> Isto está escrito aqui porque parece erro. Quem abrir o gerador daqui a seis meses e vir uma
> constante `OTHER` num campo obrigatório vai querer "consertar". Não é bug: é o enum da Meta
> que não previu duas rodas.

Carro (`veiculo.tipo == "carro"`) fica **fora desta spec**: exigiria mapear `body_style` de
verdade a partir de um dado que o `Veiculo` não tem. Carro simplesmente não entra no feed, e a
tela mostra o motivo.

### 4.4 Quem entra no arquivo

```
canal='catalogo_meta'  e  desejado=true  e  requisitos(veiculo) vazio  e  status='disponivel'
```

`requisitos()` deste canal devolve o que falta entre: **chassi**, **cor**, **1 foto**,
**endereço da loja** e **ser moto**.

Vendeu, sai do arquivo na busca seguinte — o `remove_ao_vender = True` do esqueleto (§4.6 de lá)
não precisa fazer nada além de zerar `desejado`.

### 4.5 Loja suspensa

`allows_processing(db, loja_id, "canal:catalogo_meta")` falso → **o arquivo sai vazio**, com
cabeçalho e zero linhas. A Meta esvazia o catálogo e os anúncios param.

A rota continua respondendo 200. Devolver 401 ou 500 faria a Meta manter o último estado
conhecido — exatamente o contrário do que suspensão significa.

### 4.6 O canal no registry

```python
# estoque-api/app/canais/catalogo_meta.py
codigo = "catalogo_meta"
nome = "Catálogo Meta"
modo = "feed"
retry = None                  # não existe chamada para repetir
remove_ao_vender = True
suporta_remocao = True        # sumir do arquivo é remover
```

`modo="feed"` significa: **o worker não vê este canal.** Não há `publicar()`, não há
`despublicar()`, não há `id_externo`, não há `tentativas`. O adaptador tem uma
responsabilidade só — transformar um `Veiculo` numa linha de CSV — e é testável sem rede,
sem credencial e sem worker.

---

## 5. O pixel do catálogo público

Uma palavra, e sem ela nada disto funciona:

```diff
  # catalogo-publico/app/templates/vehicle.html:40
- content_type: 'product',
+ content_type: 'vehicle',
```

`ViewContent` (`:47`) e `Lead` (`:56`) ficam como estão; `content_ids` (`:39`) já manda o
`veiculo.id` certo.

> Confiança média na fonte. É a única afirmação desta spec que não veio da documentação de
> referência da Graph API, e sim do comportamento documentado de anúncios automotivos. A
> primeira instalação real confirma em minutos: se o `content_type` estiver errado, o público
> de remarketing fica em zero enquanto o catálogo mostra os itens aprovados. Se a primeira loja
> mostrar isso, é aqui que se olha.

---

## 6. Telas

### 6.1 Control — instalação, na aba Tráfego

Ao lado de `MetaAdsConfig` e `MetaPixelConfig`, onde essa pessoa já está quando faz este
trabalho:

```
Catálogo Meta
────────────────────────────────────────────────
URL do feed   https://estoque.revy.app/feeds/vitor-motos/catalogo-meta.csv  [copiar]
Usuário       feed-vitor-motos
Senha         ••••••••••••          [ Gerar nova senha ]

Última busca da Meta:  nunca
⚠ A instalação no Commerce Manager ainda não foi feita.
```

**"Última busca" é o ponto desta tela.** Como o feed não devolve erro (C2), uma loja pode ter o
canal liberado, o vendedor marcando motos há duas semanas, e ninguém ter colado a URL no
Commerce Manager — tudo verde de cá e nada do lado de lá. O único sinal disponível é o acesso
ao arquivo. `ultima_busca_em` nulo é a única evidência possível de instalação faltando, e por
isso é aviso na tela, não linha de log.

### 6.2 Cadastro — dois campos

`portal-gestao/app/templates/estoque/form.html` ganha **chassi** e passa a tratar **cor** como
requisito do canal. Ambos usam o mecanismo de §5.1 do esqueleto (`data-requer`, checkbox
desabilitado com o motivo) — nenhuma regra nova de UI, nenhum JS novo.

### 6.3 A moto

Na tela de §5.2 do esqueleto, este canal aparece assim:

```
Catálogo Meta      ◆ no feed
Catálogo Meta      ⊘ bloqueado
                   falta o chassi
```

Sem `[ Publicar ]` e sem `[ Despublicar ]`: o botão é o próprio checkbox `desejado`. Sem
`✕ erro`, porque não há resposta que possa falhar.

---

## 7. Instalação, uma vez por loja

O runbook do gestor de tráfego, que é o que a §6.1 apoia:

1. Admin Revy libera o canal `catalogo_meta` para a loja (`CanaisControl`).
2. Preencher o endereço da loja no Control — sem ele o feed sai vazio.
3. Copiar URL, usuário e senha da tela da §6.1.
4. No Commerce Manager do BM **da loja**: criar catálogo do tipo **Veículos** → fonte de dados
   → **feed agendado** → colar URL e credencial → frequência **de hora em hora**.
5. Vincular o catálogo à conta de anúncios da loja.
6. Criar a campanha de estoque automotivo apontando para o catálogo.
7. Conferir na §6.1 que "última busca" deixou de ser "nunca".

Depois disto ninguém volta ao Commerce Manager por causa de moto. O vendedor marca o checkbox
no cadastro e acabou.

---

## 8. Testes

```bash
cd estoque-api      && .venv/bin/python -m pytest -q   # Win: .\.venv\Scripts\python.exe -m pytest -q
cd portal-gestao    && .venv/bin/python -m pytest -q
cd revy-trafego     && .venv/bin/python -m pytest -q
cd catalogo-publico && .venv/bin/python -m pytest -q
cd estoque-api      && .venv/bin/python -m alembic upgrade head
cd revy-trafego     && .venv/bin/python -m alembic upgrade head
```

Nenhum teste precisa de credencial da Meta nem de rede: o feed é uma função de estado para
texto.

| Teste | Por quê |
|---|---|
| `vehicle_id` do feed == `content_ids` do pixel | é a junção inteira; se divergir, o remarketing fica mudo e nada na tela avisa |
| moto sem chassi / sem cor / sem foto não entra no arquivo | §4.4; a rejeição da Meta é invisível para nós, então o bloqueio local é o **único** lugar onde esse erro aparece |
| loja sem endereço → feed vazio, não linha sem `address` | §3.2 |
| loja suspensa → 200 com zero linhas | §4.5; devolver erro faria a Meta congelar o estado anterior |
| moto vendida some do arquivo | §4.4 |
| linha de moto tem `body_style=OTHER` e `vehicle_type=MOTORCYCLE` | §4.3; regressão silenciosa se alguém "consertar" o `OTHER` |
| carro não entra no arquivo | §4.3 |
| feed sem Basic auth → 401 | C5 |
| `title`/`description`/`state_of_vehicle` gerados batem o formato | §4.2 |
| cabeçalho do CSV está em inglês e completo | C4; um cabeçalho errado invalida o arquivo inteiro, não uma linha |
| canal `feed` não é visitado pelo worker | §4.6 |

---

## 9. Riscos e o que fica aberto

**Risco — o erro é invisível.** É a característica central do modo feed e vale repetir: linha
rejeitada aparece no painel da Meta, não no nosso. A defesa é o gate local de §4.4 mais o
"última busca" de §6.1. Se aparecer um terceiro modo de falhar em campo, ele **não** vira
`estado='erro'` — vira requisito novo em `requisitos()`.

**Risco — o `content_type`.** §5 explica; é a única afirmação de confiança média aqui.

**Risco — endereço desatualizado.** O endereço viaja pelo provisionamento. Loja que muda de
ponto e não avisa passa a anunciar distância errada, e nada quebra. Não vale mecanismo agora;
vale saber que existe.

**Aberto — habilitação da conta de anúncios.** Rodar a campanha de estoque automotivo pode
exigir habilitação junto à Meta. Não achei fonte primária. É passo do gestor de tráfego, não da
integração, e o catálogo é pré-requisito de qualquer forma.

**Aberto — Marketplace.** Catálogo de veículos também pode alimentar listagem de Marketplace
para revenda, mas no Brasil isso passa por parceiro aprovado. Fora desta spec.

**Não muda:** o Chatbot, o n8n, o Motor, e o `publicado` da vitrine.
