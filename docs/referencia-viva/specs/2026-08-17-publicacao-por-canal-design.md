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
    retry: Literal["idempotente", "manual"]
    remove_ao_vender: bool

    def requisitos(self, veiculo) -> tuple[str, ...]: ...
    def publicar(self, ctx, veiculo) -> str: ...          # devolve id_externo
    def despublicar(self, ctx, veiculo, id_externo: str) -> None: ...
```

`requisitos()` devolve o que **falta** (`("chassi", "1 foto")`); vazio significa que pode
publicar. É a mesma função que alimenta o checkbox desabilitado de §5.1 — regra num lugar só.

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

| Canal | `remove_ao_vender` |
|---|---|
| vitrine, catálogo Meta, Webmotors, iCarros | `True` |
| Instagram, Facebook | `False` |

É D1 escrita como atributo do canal, não como `if` espalhado.

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
                   falta o chassi
```

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
decide. O Control é dono das credenciais hoje (Fernet, `meta_graph_config.py`), e o Estoque
tem `app/cripto.py` próprio. A decisão sai na spec do primeiro canal que precisar dela.

**Aberto — mais de uma foto no cadastro.** O formulário aceita uma foto opcional
(`_anexar_foto_se_enviada`). Instagram publica carrossel. Quando a spec do Instagram chegar,
ou o cadastro passa a aceitar várias fotos, ou o canal só fica marcável na tela da moto.
Não é problema desta spec porque vitrine não depende de foto.

**Não muda:** o Chatbot (D9), o n8n, e o caminho de cadastro por foto no grupo do WhatsApp,
que continua não existindo em código.
