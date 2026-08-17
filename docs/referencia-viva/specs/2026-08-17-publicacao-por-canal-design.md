# Publicação por canal — do booleano ao leque de destinos (design)

Data: 2026-08-17 · Produtos: **Estoque API** (`estoque-api`), **Revy Loja** (`portal-gestao`)
e **Revy Control** (`revy-trafego`)
Estado: **desenhado, não implementado**
Calibrado contra o main em **`67e62e7`**, com o Estoque em `0010_loja_catalogo_url`
(10 migrations). Migration nova no Estoque depois disso obriga a reconferir §3.5.

Hoje `Veiculo.publicado` é um booleano: ligado significa "está na vitrine pública". Um
destino cabia num booleano; oito não cabem. Esta spec troca a flag por estado por canal,
põe a escolha dos canais no cadastro do veículo, e cria o esqueleto onde cada canal externo
entra depois como um arquivo.

Esta spec entrega o esqueleto **com a vitrine como único canal real**. Catálogo Meta,
Instagram, Facebook, Webmotors e iCarros são specs próprias (§6), cada uma carregando o
prazo externo dela.

---

## 1. O estado de hoje, medido

Levantado em 17/08 do código, não de plano antigo.

### A flag

```python
# estoque-api/app/models_db.py:87
publicado: Mapped[bool] = mapped_column(Boolean, default=False)
```

Quem escreve nela hoje:

| Local | O que faz |
|---|---|
| `servico.py:510` `definir_publicado()` | liga/desliga; 409 se o veículo não está `disponivel` |
| `servico.py:544` `reservar()` | força `publicado=False` |
| `servico.py:567` `vender()` | força `publicado=False` |

Quem lê:

| Consumidor | Uso |
|---|---|
| `GET /public/v1/...` | devolve só `disponivel` + `publicado` — Catálogo e Chatbot |
| `GET /v1/veiculos?publicado=` | `main.py:228` — filtro da lista do Portal |
| `admin.py:86` | métrica "publicados" do admin HTMX |
| `estoque/lista.html:45` | coluna `Publicado` / `Interno` |
| `loja/estoque_visao.html:59` | métrica do dono |

### O cadastro

`POST /app/estoque/novo` (`portal-gestao/app/main.py:983`):

```python
criado = estoque.criar(dados_veiculo(form, pode_ver_custo(usuario)))
await _anexar_foto_se_enviada(estoque, (criado or {}).get("id"), form)
```

É formulário, aceita **uma foto opcional**, e publicar é ação separada depois. O caminho
"estoque nasce por foto no grupo do WhatsApp" do `PRODUCT.md` **não existe em código** —
o n8n não chama `/v1/veiculos`. Esta spec não o cria.

### Publicar hoje é um botão

```jinja
{# portal-gestao/app/templates/estoque/form.html:44 #}
{% if veiculo.publicado %}
  …/despublicar… Despublicar
{% elif veiculo.status == 'disponivel' %}
  …/publicar… Publicar no catálogo
{% endif %}
```

### O que já existe e vai ser reusado

| Peça | Onde | Serve para |
|---|---|---|
| Outbox + worker HMAC, backoff, descarte após 5 | `app/outbox.py`, `app/worker.py` | referência de padrão; **não** é a fila desta spec (§4.1) |
| `LojaOperacionalProjecao` + `allows_processing()` fail-closed | `app/provisioning.py` | entitlement de canal, sem tabela nova (§3.4) |
| `PortfolioControl` — estado, versão, auditoria, snapshot | `revy-trafego/app/control/portfolio.py` | molde do `CanaisControl` (§5.4) |
| `ESTOQUE_MEDIA_PUBLIC_BASE_URL` | `app/config.py:18` | URL pública estável de mídia, que Instagram e catálogo Meta exigem |
| `erro_api_sanitizado` | `revy-trafego/app/meta_ads_spend.py` | precedente de traduzir código de erro da Meta (§4.4) |
| `<script>` inline em formulário | 9 templates do Portal, incl. `metas/form.html` | precedente para §5.1 |

---

## 2. Decisões tomadas

Decididas com o dono em 17/08. Registradas aqui para não voltarem como proposta.

| # | Decisão | Por quê |
|---|---|---|
| D1 | Moto vendida **não** sai do Instagram nem do Facebook | o objetivo do post é acumular alcance no perfil da loja; o Chatbot já trata o lead que pergunta por moto indisponível |
| D2 | O Publicador mora **dentro do Estoque API** | o `AGENTS.md` já atribui "publicação" ao Estoque; produto novo custaria um processo no bundle 3-VM com piloto em produção |
| D3 | Uma memória de padrão **por loja**; todos os papéis leem e gravam | um registro, fácil de explicar ao lojista |
| D4 | O padrão começa **vazio** e aprende a última escolha | sem tela de Ajustes: configura-se pelo uso |
| D5 | Moto incompleta: **checkbox desabilitado** com o motivo; o cadastro salva normal | erro na hora, nada pendente; e o cadastro nunca trava |
| D6 | **Admin Revy** libera o canal para a loja | canal é item comercial, igual aos módulos de hoje |
| D7 | Canal não liberado **não aparece** na tela | ausência, não checkbox cinza |
| D8 | Canal recém-liberado entra **desmarcado** | senão a loja publica em lugar que nunca pediu |
| D9 | **TikTok fora**; o bot **não muda** | escopo |

---

## 3. Modelo de dados

### 3.1 `publicado` não muda de significado

Continua sendo "está na vitrine pública", e passa a ser a projeção derivada do canal
`vitrine`. `/public/v1` intocado e `?publicado=` intocado. Os templates do Portal ganham
conteúdo (§5.3), mas **o significado da coluna `Publicado` / `Interno` não muda**: ela
continua sendo a vitrine, e ninguém que lê essa coluna precisa aprender nada novo.

> **Invariante — escritor único.** `veiculo.publicado` só muda pela transição do canal
> `vitrine`. `definir_publicado()` passa a operar o canal e sincronizar a coluna, nunca o
> contrário. Divergência entre os dois não é estado válido: é bug, e tem teste (§7).

### 3.2 O catálogo de canais é código

`app/canais/` — registry em código, **não tabela**. Canal sem adaptador não existe; tabela
permitiria cadastrar `tiktok` sem código atrás e criar drift silencioso.

```python
# app/canais/base.py
class Canal(Protocol):
    codigo: str                      # "vitrine" | "catalogo_meta" | "instagram" | ...
    nome: str
    modo: Literal["api", "feed"]
    retry: Literal["idempotente", "manual"] | None
    remove_ao_vender: bool
    suporta_remocao: bool

    def requisitos(self, veiculo) -> tuple[str, ...]: ...

    # só quando modo == "api"
    def publicar(self, ctx, veiculo) -> str: ...          # devolve id_externo
    def despublicar(self, ctx, veiculo, id_externo: str) -> None: ...
```

`requisitos()` devolve o que **falta** (`("chassi", "1 foto")`); vazio significa que pode
publicar. É a mesma função que alimenta o checkbox desabilitado de §5.1 — regra num lugar só.

> **Adendo 17/08 — `modo`.** Nem todo canal é uma chamada. Canal `api` (vitrine, Instagram,
> Facebook e **Webmotors** — ver §6.1) publica por requisição, guarda `id_externo` e passa pelo
> worker. Canal `feed` (catálogo Meta) é o contrário: **o outro lado busca**
> um arquivo que a gente hospeda, de hora em hora. Ele não tem `publicar()`, nem `id_externo`,
> nem `tentativas`, nem retry — a próxima busca corrige tudo — e **o worker não o enxerga**
> (§4.1). Ver [`2026-08-17-catalogo-meta-feed-design.md`](2026-08-17-catalogo-meta-feed-design.md).

> **Adendo 17/08 — `suporta_remocao`.** A Graph API **não tem DELETE de mídia do Instagram**:
> post publicado por lá não sai por código, nunca. Então `despublicar()` não pode ser
> obrigatório no Protocol, e o botão `[ Despublicar ]` da §5.2 não pode ser renderizado para
> quem não sabe remover — botão que não funciona é mentira na tela. Instagram fica `False`;
> Facebook, que **aceita** DELETE de post de Página, fica `True`. É o primeiro ponto onde os
> dois deixam de ser gêmeos.

> **Regra de tamanho.** `servico.py` já tem 1210 linhas e **não cresce** nesta spec. Ele
> grava intenção e estado. Cada canal é um arquivo isolado em `app/canais/`, testável sem
> rede. Se um adaptador precisar tocar `servico.py`, a interface acima está errada.

### 3.3 `veiculo_canal`

Uma linha por (veículo, canal). É o coração da spec e também a lista de trabalho do worker.

| Coluna | Tipo | Nota |
|---|---|---|
| `veiculo_id` | FK → `veiculo`, cascade | |
| `canal` | str | código do registry |
| `desejado` | bool | o que o vendedor marcou |
| `estado` | str | `pendente` \| `publicado` \| `erro` \| `removido` |
| `id_externo` | str \| null | `ig_media_id`, id do anúncio no portal |
| `erro` | str \| null | motivo sanitizado; **nunca** stack nem payload |
| `tentativas` | int | |
| `publicado_em` | datetime \| null | |
| `atualizado_em` | datetime | |

`unique (veiculo_id, canal)`.

`id_externo` é o campo que hoje não existe e sem o qual nada é reversível: sem guardar o
que o canal devolveu, não há como atualizar nem remover depois.

**Quatro estados persistidos, seis exibidos.** A tela de §5.2 mostra `publicando` e
`bloqueado`, que **não** existem na coluna `estado` — são derivados na renderização e não
podem virar coluna, senão passam a ter que ser mantidos em sincronia:

| Exibido | Derivado de |
|---|---|
| `◐ publicando` | `desejado=true` e `estado='pendente'` |
| `⊘ bloqueado` | `requisitos(veiculo)` devolveu lista não vazia |
| `◆ no feed` | canal `modo="feed"`, `desejado=true` e requisitos vazios |

> **Adendo 17/08 — por que `no feed` e não `publicado`.** Canal `feed` não devolve resposta:
> se o outro lado rejeitar a linha, o erro aparece no painel dele, não no nosso. Escrever
> `publicado` ali seria afirmar uma coisa que o sistema não tem como verificar. Pela mesma
> razão canal `feed` **nunca** exibe `✕ erro` — não há chamada que possa falhar.

### 3.4 `loja_canal` — a memória do padrão

| Coluna | Tipo | Nota |
|---|---|---|
| `loja_id` | str | |
| `canal` | str | |
| `padrao` | bool | vem marcado no próximo cadastro |
| `atualizado_em` | datetime | |

`primary key (loja_id, canal)`.

Canal recém-liberado não tem linha, então `padrao` é falso por ausência — que é D8 sem
código extra.

**Entitlement não ganha tabela.** Reusa a projeção existente com `aggregate="canal:<codigo>"`
e `state="ativo"|"suspenso"`; o gate é `allows_processing(db, loja_id, "canal:instagram")`,
que já é fail-closed quando a projeção não existe.

### 3.5 Migration `0011_publicacao_por_canal`

1. cria `veiculo_canal` e `loja_canal`;
2. para cada veículo existente, insere a linha `vitrine` com
   `desejado = publicado` e `estado = 'publicado' if publicado else 'removido'`.

Nenhum consumidor muda. `downgrade` derruba as duas tabelas; `publicado` nunca foi tocado,
então a volta é limpa.

---

## 4. Fluxo de publicação

### 4.1 Não existe tabela de fila

`veiculo_canal` **é** a lista de trabalho. O worker reconcilia:

```
desejado = true   e estado ∈ (pendente, erro)   →  publicar
desejado = false  e estado = publicado          →  despublicar
```

Auto-cura: worker parado por horas volta e converge. Uma tabela de fila separada teria que
ser mantida em sincronia com o estado — dois lugares para divergir.

O outbox de `app/outbox.py` **não** é reusado como fila: ele descarta após 5 tentativas, o
que é aceitável para notificação e inaceitável para publicação (o vendedor marcou, o sistema
desistiu em silêncio).

### 4.2 Duas políticas de retry

**`idempotente`** — vitrine e, depois, catálogo Meta, Webmotors, iCarros.
Reenviar converge. O worker tenta com backoff e não desiste; o estado é a verdade.

> **Adendo 17/08.** O catálogo Meta saiu desta lista: canal `feed` não tem retry porque não tem
> chamada (§3.2). Webmotors continua aqui, mas como canal `api` — ver §6.1.

**`manual`** — Instagram e Facebook.
**Uma tentativa.** Falhou → `estado='erro'` com o motivo, visível na moto, e um humano
clica "tentar de novo".

> O caso que justifica: `media_publish` deu certo e a resposta se perdeu. Retry automático
> publica a mesma moto duas vezes no perfil da loja. Post duplicado é pior que post
> faltando — o primeiro o dono vê e cobra; o segundo alguém percebe e resolve.

### 4.3 O que é síncrono

**O cadastro nunca chama canal externo.** Grava `desejado` e devolve; chamar a Meta dentro
da request deixaria o cadastro refém do uptime dela.

Exceção: **vitrine é local** — flag no mesmo banco, aplicada na mesma transação. Por isso o
vendedor vê `Vitrine ● publicado` instantâneo e os demais em `◐ publicando`.

> Isto **não** é a "fila de espera" recusada em D5. Aquela guardava intenção em moto
> incompleta e publicava sozinha quando o dado chegasse. Aqui a moto já passou no gate de
> requisitos: o que se espera é rede, não dado faltando.

### 4.4 Falha fala a língua do lojista

Seguindo `erro_api_sanitizado` do Control:

> `OAuthException 190` → **"Token expirado — reconecte a conta do Instagram"**

### 4.5 Loja suspensa

Invariante do `AGENTS.md` (suspensão é gate de backend) e o ADR já registrado em
`main.py:316` (*"Despublicar permanece permitido sob suspensão"*).

**Loja suspensa não publica, mas despublica.** O worker chama `allows_processing()` antes de
publicar e ignora esse gate ao remover.

### 4.6 Venda

`vender()` zera `desejado` **só** nos canais com `remove_ao_vender = True`:

| Canal | `remove_ao_vender` | `suporta_remocao` |
|---|---|---|
| vitrine, catálogo Meta, Webmotors, iCarros | `True` | `True` |
| Facebook | `False` | `True` |
| Instagram | `False` | **`False`** |

É D1 escrita como atributo do canal, não como `if` espalhado.

Os dois eixos são diferentes e não se confundem: `remove_ao_vender` é **se a gente quer**
remover ao vender (D1: não queremos, o post acumula alcance); `suporta_remocao` é **se dá para
remover**. Instagram é o único que é `False` nos dois, e pelo segundo motivo — não existe DELETE
de mídia na Graph API. Ou seja, mesmo que o dono mudasse de ideia sobre D1, o Instagram
continuaria sem sair.

### 4.7 Worker

Um processo, flag default **OFF** (`ESTOQUE_CANAIS_WORKER=0`), ligada por secret no piloto.
O `README` do Control tem o aviso de nunca rodar worker duplicado sobre a mesma outbox; vale
igual aqui.

---

## 5. Telas

> Os mocks abaixo mostram o **estado final**, com vários canais, porque é ele que justifica
> o layout. Nesta spec só a vitrine existe de fato (§6) — as telas nascem com uma linha só,
> e cada canal novo aparece sem precisar mexer no template.

### 5.1 Cadastro — bloco novo em `estoque/form.html`

```
Publicar em
────────────────────────────────────────────────
[x] Vitrine pública
[x] Catálogo Meta
[ ] Instagram        anexe ao menos 1 foto
[ ] Facebook         anexe ao menos 1 foto
```

Canal não liberado não aparece (D7).

O servidor emite o requisito como dado:

```html
<input type="checkbox" name="canal" value="instagram" data-requer="foto" disabled>
<span class="motivo">anexe ao menos 1 foto</span>
```

~15 linhas de JS inline leem `data-requer` e habilitam o checkbox quando o campo é
preenchido. **O JS não conhece regra nenhuma** — compara nomes de campo; as regras vivem em
`Canal.requisitos()`.

> **O JS nunca é o portão.** O `POST` revalida no servidor sempre. Sem JS, o checkbox fica
> desabilitado e o vendedor marca depois na moto — fail-closed.

### 5.2 Moto existente — substitui `form.html:44`

```
Publicação
────────────────────────────────────────────────
Vitrine pública    ● publicado         [ Despublicar ]
Catálogo Meta      ● publicado         [ Despublicar ]
Instagram          ✕ erro              [ Tentar de novo ]
                   Token expirado — reconecte a conta
Facebook           ○ não publicado     [ Publicar ]
Webmotors          ⊘ bloqueado
                   falta o ano de fabricação
```

> **Adendo 17/08.** O mock original dizia *"falta o chassi"* no Webmotors. O levantamento de §6.1
> mostrou que **a Webmotors não usa chassi** — quem exige são o catálogo Meta e o Mercado Livre.
> O requisito real dela é o ano de fabricação, que a Revy também não tem. Trocado para não induzir
> quem implementar.

Cinco estados, cada um com **forma + palavra** — cor nunca comunica sozinha (compromisso do
`PRODUCT.md`). O verde de marca não é usado como status.

Esta tela é obrigatória por causa de D5: é onde o vendedor volta depois de subir as fotos.

**Rotas novas:** `POST /v1/veiculos/{id}/canais/{canal}/publicar` e `.../despublicar`.
As rotas `/publicar` e `/despublicar` **continuam existindo** e significam vitrine, então
`clients/estoque.py:131` e os links atuais não quebram.

### 5.3 Lista — `estoque/lista.html`

A coluna `Publicado` / `Interno` **não muda de significado**: continua vitrine.

Ganha a coluna `Canais` (`3/4`) e o filtro ganha **"com erro de publicação"**. Sem esse
filtro, canal quebrado só aparece se alguém abrir a moto — e ninguém abre.

### 5.4 Revy Control — liberar canal

`CanaisControl`, irmão de `PortfolioControl`: mesma forma (estado ativo/suspenso, versão,
auditoria, `safe_enqueue_store_snapshot`), com enum e tabela próprios **no Control**.

> Não confundir com §3.4: o Control **tem** tabela (é ele o dono do fato); o Estoque **não
> ganha** tabela de entitlement, porque recebe o mesmo fato pela projeção
> `aggregate="canal:<codigo>"`. Dono de um lado, projeção do outro — o padrão que os módulos
> já seguem hoje.

**`ModuleCode` não é estendido.** Ele alimenta `check_module_access` e `Module.ESTOQUE`;
misturar canal de publicação ali quebraria o significado de "módulo contratado". Eixos
diferentes, tabelas diferentes.

Na tela da loja, seção "Canais de publicação" ao lado de "Módulos", só Admin.

### 5.5 Quem escreve o padrão

**Só o cadastro.** No `POST /app/estoque/novo` bem-sucedido, o Estoque grava
`loja_canal.padrao` com o que foi marcado, na mesma transação.

Marcar canal numa **moto antiga não mexe no padrão** — senão consertar o Instagram de uma
moto de três semanas atrás mudaria o padrão de todas as próximas.

---

## 6. Recorte

**Nesta spec:** modelo (§3), worker e políticas de retry (§4), telas (§5), `CanaisControl`,
padrão aprendido, e **`vitrine` como único canal real**.

**Specs próprias, uma por canal:** catálogo Meta, Instagram, Facebook, Webmotors, iCarros.

O catálogo Meta ficou de fora do esqueleto porque exige `catalog_management` com App Review
e verificação de empresa — mesmo prazo externo dos demais. Vitrine é o único canal sem
dependência externa, e sozinha já percorre o caminho inteiro (intenção → estado → worker →
publicado). Depois dela, **cada canal novo é um arquivo** — e esta spec pode ir a produção
enquanto App Review e homologação correm em paralelo.

> **Adendo 17/08 — a ordem mudou, e o catálogo Meta subiu.** O parágrafo acima supõe que o
> catálogo Meta só entra por API. Não é o caso: catálogo também aceita **feed agendado** — a
> gente hospeda um arquivo por loja numa URL e o Commerce Manager do lojista busca sozinho, de
> hora em hora. Sem app, sem token, sem `catalog_management`, **sem App Review**, porque nunca
> chamamos a Meta.
>
> Isso tira o catálogo Meta da fila de prazo externo e o põe como **segundo canal**, logo depois
> da vitrine — e ele é o único que liga publicação a Ads e ROI, porque post não vira linha de
> ROI e item de catálogo vira. Ver [`2026-08-17-catalogo-meta-feed-design.md`](2026-08-17-catalogo-meta-feed-design.md).
>
> A ordem passa a ser: **catálogo Meta (feed) → Facebook e Instagram**, com o App Review aberto
> em paralelo desde já, já que ele não bloqueia o catálogo.
>
> **E os dois de post viraram uma spec só**, contra a promessa de "uma por canal" logo acima. O
> motivo daquela promessa era o prazo externo — cada canal esperando o dele. Facebook e Instagram
> esperam **o mesmo**: uma submissão de App Review cobre os dois, e eles dividem conexão, token,
> tratamento de foto e geração de texto. Separá-los daria duas specs em que a maior parte é a
> mesma coisa escrita duas vezes. Ver
> [`2026-08-17-instagram-facebook-post-design.md`](2026-08-17-instagram-facebook-post-design.md).
>
> O item aberto do §8 desta spec ("mais de uma foto no cadastro") **foi decidido lá**: o cadastro
> passa a aceitar várias fotos.

### 6.1 Webmotors e iCarros — levantado em 17/08

Esta seção existe porque a versão original supunha que os dois eram feed. **Um é API e o outro
não é público.** Nenhum dos dois tem spec ainda; isto é o material para escrevê-las.

#### Webmotors — é **API**, e a Revy entra como *Gestor de Estoque Terceiro*

Confirmado no portal do desenvolvedor (gateway Sensedia) e na central de ajuda da Webmotors.
Não existe opção de feed XML ou CSV: a integração é REST com OAuth 2.0.

> **Correção 17/08 — não é REST.** A frase acima está errada e ficou registrada porque foi
> afirmada com confiança. O gateway Sensedia é REST com OAuth 2.0 e serve **leads, catálogo, site
> e classificados**. O caminho de **publicar estoque** é o serviço **SOAP** legado em
> `integracao.webmotors.com.br` (ASP.NET `.asmx`), com autenticação própria por hash de sessão —
> sem OAuth. O API Browser da Sensedia enumera todas as REST do gateway e não há nenhuma de gestor
> de estoque. Ver [`2026-08-17-webmotors-design.md`](2026-08-17-webmotors-design.md).
>
> **E moto tem serviço próprio:** `wsEstoqueRevendedorMotos.asmx`, com objeto e catálogo
> separados dos de carro. A pergunta eliminatória está respondida — Webmotors aceita moto, com
> folga. O nome contratual do plano é **"Assinatura de Motos"**.

A Webmotors publica a lista de gestores de estoque homologados — Byus, ALM, RevendaPro, Boom,
BNDV, Revenda Mais, Altimus, Disal, Click Garage, AutoGestor, EasyCar, Localiza, BRDealer,
Batcar, Simples Veículo, DuSeller. **A Revy entraria nessa lista**, no mesmo papel.

O que cada lado precisa fazer:

| Lado | Passo |
|---|---|
| Lojista | contratar um Plano Webmotors — existe **Plano Motos** |
| Lojista | aceitar o Termo de Adesão no Cockpit |
| Lojista | pedir ao atendimento a criação de usuário com perfil **"Integração Revendedor"** |
| Revy | registrar-se no portal do desenvolvedor e pedir acesso ao ambiente de homologação |
| Revy | desenvolver, homologar, e pedir promoção para produção |

> **O prazo é duro e não é o de sempre.** O acesso ao ambiente de homologação é **revogado após
> 90 dias corridos**, ou quando a integração for aprovada e promovida. Isso inverte a ordem
> natural: não se abre o acesso "para ir olhando". Abre-se quando houver quem termine dentro da
> janela, senão o relógio corre sozinho e o acesso morre.

Veículo publicado por integração aparece no Cockpit com a TAG `WS` — é assim que se confere de
fora se a publicação chegou.

Fora do escopo de publicação, mas registrado porque muda o Chatbot mais tarde: o mesmo portal
expõe **Consultar Leads** e **Incluir Lead**. A Webmotors devolve lead, e hoje esse lead não
entra na Revy por lugar nenhum.

#### iCarros — **não é público**

Não existe portal de desenvolvedor nem documentação de API aberta. Procurei e não achei; e a
ausência aqui é informação, não falta de esforço.

O que dá para observar de fora, pelos integradores que anunciam a integração (RevendaMais,
Cockpit, Loja Conectada, BNDV, Auto Adm): o lojista informa **usuário e senha do classificado**
e "libera a conta iCarros"; o portal pode pedir CNPJ e e-mail e devolver credencial por e-mail.
Isso é a cara de acordo privado entre o iCarros e integradores homologados — não de API aberta.

**Conclusão: para saber, tem que falar com o iCarros.** É contato comercial, não pesquisa, e
nenhuma spec de iCarros deve ser escrita antes dessa conversa. Escrever agora seria inventar.

> **Correção 17/08 — a documentação existe.** O parágrafo acima está errado. O iCarros serve um
> **OpenAPI 2.0 vivo e sem autenticação** em `www.icarros.com.br/rest/swagger.json`, com Swagger
> UI em `/apidocs/` e manual de OAuth em `/apidocs/apiOauth.html`: *"API para gerenciamento de
> anúncios no iCarros"*, 54 rotas, CRUD de estoque por revenda, Keycloak com Authorization Code.
> Não aparece em busca porque **não está linkada em navegação nenhuma do site** — é
> pública-mas-não-divulgada. Ver [`2026-08-17-icarros-design.md`](2026-08-17-icarros-design.md).
>
> **A lição vale além deste canal:** "não achei em busca" não é "não existe". A primeira pesquisa
> parou cedo demais e a conclusão foi escrita com confiança que ela não tinha.
>
> E o padrão de login-e-senha descrito abaixo (§6.2) é, segundo o próprio iCarros, o método
> **desaconselhado e possivelmente bloqueado** para integrador de terceiros. O caminho pretendido
> é consentimento do lojista por Authorization Code, sem a Revy jamais guardar senha.

#### O que isso muda no plano

Webmotors não é "mais um arquivo em `app/canais/`". É canal `api` com homologação externa, uma
contratação do lado do lojista e uma janela de 90 dias. Cabe na interface `Canal` sem forçar
nada — o que não cabe é no cronograma junto com o resto.

A ordem completa fica: **catálogo Meta → Facebook → Instagram → Webmotors → iCarros**, com
Webmotors podendo correr em paralelo aos dois de post (não compartilham nada), e iCarros
esperando uma conversa comercial que ainda não aconteceu.

### 6.2 Agregador: procurado, não existe — e o que apareceu no lugar

Levantado em 17/08. A pergunta era: existe um intermediário com API REST que a Revy chame **uma
vez** e que publique em todos os portais, evitando homologar com cada um?

**Praticamente não.** Um único candidato vende API para outro software — a Loja Conectada, com
"API White Label", cobrindo Webmotors e iCarros, com moto de primeira classe. Mas **não publica
uma linha de documentação técnica**: o Swagger que existe no domínio deles é de outro produto, o
GitHub da empresa só tem forks, e o acesso ao sandbox se pede por WhatsApp. A empresa opera há
anos; o que não dá para verificar é se a API existe como produto. Tudo o mais que aparece nessa
busca (RevendaMais, BNDV, Auto Adm, Altimus, StockCarWeb…) é **ERP vendido ao lojista** — nesses
a Revy é concorrente, não cliente.

**Como os integradores alcançam o iCarros.** A documentação pública do Smart Dealer (ERP, produto
errado, doc excelente) mostra o modelo canônico do mercado: `POST /connect/contract/` recebe
`{ site_id, filial, cnpj, login, senha }` — **login e senha da conta da loja no portal**. Os
integradores em geral não têm credencial de parceiro própria: eles agem *como se fossem a loja*.

> É isso que torna o iCarros alcançável sem documentação, e é um passivo que a Revy herdaria:
> guardar senha de portal de cliente. Isso bate de frente com os invariantes de segredo do
> `AGENTS.md` e, se um dia for o caminho, precisa ser **decisão explícita**, nunca consequência.

**O que a pesquisa achou de bom.** Três portais autoatendidos, com documentação pública, sem
homologação formal, e **com moto**:

| Portal | Documentação | Homologação | Spec |
|---|---|---|---|
| **OLX** | pública e completa | não | [`2026-08-17-olx-design.md`](2026-08-17-olx-design.md) |
| **Mercado Livre** | pública | não | [`2026-08-17-mercado-livre-design.md`](2026-08-17-mercado-livre-design.md) |
| Mobiauto | Swagger 2.0 aberto, OAuth de parceiro, moto na spec | não | **fora do escopo por decisão do dono em 17/08** |

Os dois primeiros entraram no escopo em 17/08. São mais baratos que Webmotors e iCarros: o custo
de entrada da OLX é um e-mail pedindo credencial, e o do Mercado Livre é o lojista contratar um
pacote.

**A ordem final, com sete canais** — todos com spec escrita em 17/08:

| # | Canal | Portão externo | Spec |
|---|---|---|---|
| 1 | vitrine | nenhum | esta |
| 2 | catálogo Meta | nenhum (feed) | [catálogo Meta](2026-08-17-catalogo-meta-feed-design.md) |
| 3 | OLX | um e-mail pedindo credencial | [OLX](2026-08-17-olx-design.md) |
| 4 | Facebook + Instagram | App Review (uma submissão) | [post](2026-08-17-instagram-facebook-post-design.md) |
| 5 | Mercado Livre | lojista contratar pacote | [Mercado Livre](2026-08-17-mercado-livre-design.md) |
| 6 | Webmotors | homologação, janela de 90 dias | [Webmotors](2026-08-17-webmotors-design.md) |
| 7 | iCarros | **bloqueado**: moto no marketplace | [iCarros](2026-08-17-icarros-design.md) |

Dois canais precisam de algo que **não é código** e que atrasa mais que qualquer implementação:
a submissão do App Review (canal 4) e um e-mail para `api@icarros.com.br` perguntando se o
segmento MOTO está ativo (canal 7). Os dois deveriam sair antes de a primeira linha ser escrita.

---

## 7. Testes

Três produtos mudam, então três suítes mais os consumidores do contrato:

```bash
cd estoque-api   && .venv/bin/python -m pytest -q   # Win: .\.venv\Scripts\python.exe -m pytest -q
cd portal-gestao && .venv/bin/python -m pytest -q
cd revy-trafego  && .venv/bin/python -m pytest -q
cd estoque-api   && .venv/bin/python -m alembic upgrade head
```

**`CanalFalso` é a peça central**: adaptador com falha programável que testa worker, retry e
reconciliação sem tocar em rede. Nenhum teste precisa de credencial.

| Teste | Por quê |
|---|---|
| `publicado` nunca diverge de `veiculo_canal['vitrine']` | invariante de escritor único (§3.1); se quebrar, o catálogo público mente |
| `/public/v1` devolve o mesmo conjunto antes e depois da migration | contrato de Chatbot e Catálogo |
| canal `manual` é chamado **exatamente uma vez** ao falhar | proteção contra post duplicado; regressão fica visível no perfil da loja |
| canal `idempotente` refaz com backoff e converge | |
| loja suspensa: publica não, despublica sim | §4.5 |
| `vender()` zera `desejado` só onde `remove_ao_vender` | D1 virando teste |
| cadastro grava padrão; moto antiga não grava | §5.5; efeito colateral invisível se inverter |
| `POST` rejeita canal sem requisito, sem JS envolvido | §5.1, o servidor é o portão |
| migration cria `vitrine` com o estado certo para todo veículo | §3.5 |

---

## 8. Riscos e o que fica aberto

**Risco — `servico.py` engordar.** É o motivo da regra de §3.2. Vale conferir no review: se
o diff de `servico.py` passar de ~80 linhas, a interface `Canal` está errada.

**Risco — o JS virar portão.** Se algum canal depender do JS para ser bloqueado, a validação
do servidor está incompleta. O teste de §7 cobre.

**Aberto — onde mora o segredo de canal.** Vitrine não usa credencial, então esta spec não
decide. A decisão sai na spec do primeiro canal que precisar dela.

> **Correção 17/08.** A versão original desta seção dizia que o Control guarda credencial Meta
> em `meta_graph_config.py`. Está errado: esse arquivo tem 20 linhas e só guarda a versão da
> Graph API. Os segredos reais são três, em `revy-trafego/app/models.py`, todos por loja e
> cifrados por `app/cripto.py` do Control:
>
> | Onde | O quê |
> |---|---|
> | `meta_ads_config.token_ciphertext` + `ad_account_id` (`:580`) | token `ads_read`, **colado à mão** pelo lojista na aba Tráfego |
> | `meta_pixel_config.token_ciphertext` + `pixel_id` (`:561`) | token do CAPI de conversões |
> | `google_ads_connections.refresh_token_ciphertext` + `scopes` + `status` (`:817`) | OAuth de verdade, com `conectado`/`atencao`/`expirado`/`revogado` |
>
> O que interessa para a decisão futura: os dois tokens da Meta são colados à mão; o do Google
> é OAuth. **O padrão de conexão OAuth que os canais Meta vão precisar já existe no Control —
> na integração do Google, não na da Meta.** É dele que se copia.
>
> E o caminho recomendado para os canais `api`: uma conexão só, por Business Login, em que o
> lojista compartilha com o BM da Revy a Página, a conta do Instagram, o catálogo, a conta de
> anúncios e a WABA do Cloud API (`whatsapp_modo=2`) de uma vez. Token de System User, que não
> expira — token de usuário longo dura 60 dias e cai de madrugada sem ninguém perceber. E uma
> submissão de App Review cobre o app inteiro: pede-se tudo junto, não um pedido por canal.

**Aberto — mais de uma foto no cadastro.** O formulário aceita uma foto opcional
(`_anexar_foto_se_enviada`). Instagram publica carrossel. Quando a spec do Instagram chegar,
ou o cadastro passa a aceitar várias fotos, ou o canal só fica marcável na tela da moto.
Não é problema desta spec porque vitrine não depende de foto.

> **Fechado em 17/08:** o cadastro passa a aceitar várias fotos. Decisão P1 de
> [`2026-08-17-instagram-facebook-post-design.md`](2026-08-17-instagram-facebook-post-design.md),
> tomada assim porque a mesma mudança serve o carrossel do Instagram e melhora o catálogo Meta.
> É a mudança de maior superfície daquela spec: toca o cadastro de toda moto, inclusive de loja
> que não usa canal externo nenhum.

**Não muda:** o Chatbot (D9), o n8n, e o caminho de cadastro por foto no grupo do WhatsApp,
que continua não existindo em código.
