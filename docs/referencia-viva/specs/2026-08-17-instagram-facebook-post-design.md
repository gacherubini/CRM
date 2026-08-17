# Instagram e Facebook — os canais de post (design)

Data: 2026-08-17 · Produtos: **Estoque API** (`estoque-api`), **Revy Control** (`revy-trafego`)
e **Revy Loja** (`portal-gestao`)
Estado: **desenhado, não implementado**
Depende de [`2026-08-17-publicacao-por-canal-design.md`](2026-08-17-publicacao-por-canal-design.md).
Irmã de [`2026-08-17-catalogo-meta-feed-design.md`](2026-08-17-catalogo-meta-feed-design.md),
com a qual **não** compartilha nada além do Business Manager da loja.

Calibrado contra o main em `ce36207`.

---

## 1. Por que os dois numa spec só

O esqueleto (§6) prometeu "uma spec por canal", e o motivo era o prazo externo: cada canal
carrega a espera dele. **Instagram e Facebook carregam a mesma.** Uma submissão de App Review
cobre os dois, e eles dividem conexão, token, tratamento de foto e geração de texto. Separá-los
daria duas specs em que 70% é a mesma coisa escrita duas vezes, e uma delas mentindo sobre ser
independente.

O que **não** é comum entre eles é o mais interessante, e está em §7: um remove, o outro não
consegue.

### O que estes canais são, e o que não são

Post é **alcance orgânico** — aparece uma vez no feed de quem segue a loja e afunda. Não é
munição de anúncio: post não vira linha de ROI, e por isso o catálogo Meta (spec irmã) resolve
um problema que estes dois não resolvem, e vice-versa. Publicar moto no Instagram serve para
acumular presença no perfil da loja; é por isso que D1 do esqueleto manda **não** despublicar ao
vender.

---

## 2. Decisões tomadas

D1–D9 do esqueleto continuam valendo. Estas são as desta spec, decididas com o dono em 17/08.

| # | Decisão | Por quê |
|---|---|---|
| P1 | **O cadastro passa a aceitar várias fotos** | o Instagram publica carrossel; e o catálogo Meta também fica melhor. Uma mudança serve os dois |
| P2 | Texto **gerado, com ajuste opcional** | publica sozinho por padrão; quem quiser a voz da loja sobrescreve |
| P3 | **Publica na hora**, sem espaçamento | simples de implementar e de explicar; a consequência está em §6.4 |
| P4 | Instagram **nunca remove** (`suporta_remocao=False`) | a Graph API não tem DELETE de mídia. Não é escolha |
| P5 | Facebook **remove** (`suporta_remocao=True`) | DELETE de post de Página existe |
| P6 | Retry `manual`, **exceto rate limit** | §6.4 — a Meta rejeitou antes de publicar, então não há duplicata a temer |
| P7 | Conexão por **Business Login**, token de System User, guardada no Control | §3 |
| P8 | **Uma** submissão de App Review para os dois | §9 |
| P9 | Foto nunca é **recortada**: é preenchida | §4.2 — cortar moto é pior que barra lateral |

---

## 3. A conexão Meta

### 3.1 Uma consentida, cinco ativos

O lojista compartilha os ativos **dele** com o Business Manager da Revy, num fluxo de Business
Login só. Numa consentida vêm a Página, a conta do Instagram, o catálogo, a conta de anúncios e
a WABA do Cloud API (`whatsapp_modo=2`).

Esta spec **usa** só os dois primeiros. Os outros três entram no escopo de quem precisar deles
depois; o que importa aqui é não construir um fluxo de conexão que sirva a um canal só.

> **Escopo declarado.** Migrar o token de `meta_ads_config` — hoje **colado à mão** pelo lojista
> na aba Tráfego — para esta conexão é tentador e está **fora** desta spec. É mudança em
> funcionalidade que já roda em produção, e merece a decisão dela. Aqui a conexão nasce ao lado,
> servindo publicação.

### 3.2 System User, não token de usuário

Token de usuário longo dura 60 dias e cai de madrugada sem ninguém perceber — e o sintoma é a
loja parar de publicar em silêncio. **Token de System User não expira.**

O custo é onboarding: o lojista precisa concluir o fluxo uma vez. É um custo de instalação, não
um custo recorrente, e o troco é não ter job de refresh cujo fracasso é invisível.

### 3.3 Onde mora

No **Control**, cifrado por `app/cripto.py`, com o molde de `google_ads_connections`
(`revy-trafego/app/models.py:817`) — que é a conexão OAuth de verdade que já existe na casa:

| Coluna | Nota |
|---|---|
| `loja_id` | unique |
| `status` | `conectado` \| `atencao` \| `expirado` \| `revogado` \| `erro` |
| `token_ciphertext` | System User token |
| `ig_user_id` | conta do Instagram |
| `page_id` | Página do Facebook |
| `scopes` | o que foi concedido |
| `conectada_em` / `atualizada_em` | |

> **Não copiar de `meta_ads_config`.** Aquela tabela é de token colado à mão e não tem estado de
> conexão. `google_ads_connections` tem `status` com os quatro estados de uma conexão que pode
> ser revogada pelo outro lado — que é exatamente o que acontece aqui.

O Estoque pede o token ao Control por HTTP interno, com cache curto, e **não guarda cópia**.
Dono de um lado, uso do outro — o mesmo padrão do entitlement (§3.4 do esqueleto).

### 3.4 Quando a conexão cai

`status != 'conectado'` → o worker **não tenta**, e marca `erro` com
*"Conta da Meta desconectada — reconecte em Tráfego"*. Tentar com token morto só gasta tentativa
e enche log.

---

## 4. Fotos

### 4.1 O cadastro passa a aceitar várias (P1)

Hoje `POST /app/estoque/novo` chama `_anexar_foto_se_enviada`, no singular. O modelo **já está
pronto**: `Veiculo.fotos` é `relationship` para `VeiculoFoto` com `order_by=VeiculoFoto.ordem`.
Falta só o formulário e o handler pararem de assumir uma.

Isto é a mudança de maior superfície da spec e a única que toca o caminho de cadastro de toda
moto, inclusive de quem não usa canal nenhum. Merece atenção no review.

### 4.2 O que o Instagram exige, e o que fazemos com foto que não cabe

O Instagram aceita proporção entre **4:5 e 1.91:1** e JPEG. Foto de moto em retrato de celular
(9:16) está fora da faixa e é recusada.

Três saídas: recusar a foto, recortar, ou preencher. **P9 escolhe preencher**:

> Recortar para caber corta a moto — e a moto é o assunto inteiro do post. Uma foto recusada
> viraria `⊘ bloqueado` num canal em que o vendedor não entende por que a foto "boa" não serve.
> Preencher para **1:1 com fundo neutro** mantém a moto inteira, cabe na faixa, e é o que
> revenda faz no Brasil. Barra lateral é feia; moto sem roda é pior.

O redimensionamento acontece **na publicação**, não no upload: a foto original fica intacta para
a vitrine, o catálogo e o Webmotors, que não têm essa restrição.

### 4.3 Carrossel

Até **10** fotos, na ordem de `VeiculoFoto.ordem`. Moto com uma foto vira post simples, não
carrossel de um item.

### 4.4 Facebook

Mais permissivo: sem restrição de proporção equivalente. Álbum na mesma ordem, sem
redimensionamento.

---

## 5. O texto

Gerado por padrão (P2):

```
Honda CB 500F 2021 · 18.400 km · R$ 32.900
Fale com a gente pelo WhatsApp.
```

Campo opcional no cadastro sobrescreve. Vazio significa gerado — **não** significa post sem
texto.

**Link:** o Facebook leva a URL da ficha (`/l/{slug}/veiculos/{id}`), que é clicável. O
Instagram **não** leva: link em legenda do Instagram não é clicável, e colar URL ali só suja o
texto. Quem quiser o link do Instagram usa a bio, que é assunto da loja e não do sistema.

**Sem enxurrada de hashtag.** Se um dia entrarem, entram como decisão de marca, não como
default do sistema.

---

## 6. Publicação

### 6.1 Instagram — dois passos

```
POST /{ig-user-id}/media          → creation_id     (a Meta baixa a imagem da URL pública)
POST /{ig-user-id}/media_publish  → ig_media_id     (vira id_externo)
```

Carrossel: cada foto vira um filho com `is_carousel_item=true`, depois um contêiner de carrossel,
depois o publish.

A imagem é **baixada pela Meta** de uma URL pública nossa — daí `ESTOQUE_MEDIA_PUBLIC_BASE_URL`
(`estoque-api/app/config.py:18`) ser peça obrigatória e não detalhe.

> **Guardar o `creation_id` antes do publish.** É o que estreita a janela de duplicata: se a
> resposta do `media_publish` se perder, a gente ao menos sabe qual contêiner estava em voo e
> pode conferir antes de qualquer humano clicar "tentar de novo".

### 6.2 Facebook

`POST /{page-id}/photos` (ou `/feed`), com token de Página. Devolve o id do post, que vira
`id_externo`.

### 6.3 Retry `manual` (§4.2 do esqueleto)

Uma tentativa. Falhou, `estado='erro'` com o motivo na moto, e um humano clica. O caso que
justifica continua sendo: `media_publish` deu certo e a resposta se perdeu — retry automático
publicaria a mesma moto duas vezes no perfil da loja.

### 6.4 A exceção: rate limit

P3 diz publicar na hora, sem espaçar. O Instagram limita ~**25 publicações por 24h** por conta,
e isso é limite de API, não conselho: estourou, a chamada é **rejeitada**.

Então esse erro tem tratamento próprio:

> **Rate limit reagenda sozinho.** É o único erro em que o retry automático é seguro, porque a
> Meta rejeitou **antes** de publicar — não existe post duplicado a temer, que era o motivo
> inteiro do retry manual. A moto fica `pendente` e o worker tenta depois da janela.

Todo outro erro continua `manual`. A distinção não é "erro recuperável ou não": é **"a Meta
chegou a publicar ou não"**. Rate limit é o único caso em que a resposta é um "não" garantido.

Uma loja que cadastre mais de 25 motos num dia vê o excedente sair no dia seguinte, sozinho.

### 6.5 Erro fala a língua do lojista

Seguindo `erro_api_sanitizado` do Control:

| Da Meta | Na tela |
|---|---|
| `OAuthException 190` | Token expirado — reconecte a conta em Tráfego |
| limite de publicação | Limite diário do Instagram atingido — sai amanhã |
| proporção inválida | Foto fora do formato aceito pelo Instagram |

Nunca stack, nunca payload, nunca o token — que `meta_ads_spend.py:106` já sabe remover de
mensagem de erro.

---

## 7. Remoção — onde os dois deixam de ser gêmeos

| | `suporta_remocao` | `remove_ao_vender` |
|---|---|---|
| Instagram | **`False`** | `False` |
| Facebook | `True` | `False` |

**Instagram não sai nunca.** Não existe DELETE de mídia na Graph API. A tela da moto não mostra
`[ Despublicar ]` para ele — botão que não funciona é mentira na tela.

**Facebook pode sair**, por `DELETE /{post-id}`, mas **não sai ao vender**: D1 vale para os dois,
porque o post existe para acumular alcance e o Chatbot já trata quem pergunta por moto
indisponível. O botão existe para o caso de erro humano — foto errada, preço errado.

---

## 8. Telas

### 8.1 Cadastro

Duas mudanças em `portal-gestao/app/templates/estoque/form.html`:

```
Fotos          [ escolher arquivos ]  (arraste para ordenar)
Texto do post  [                                    ]  opcional
```

O bloco "Publicar em" do §5.1 do esqueleto não muda de forma — ganha duas linhas.

### 8.2 A moto

```
Instagram    ● publicado
Facebook     ● publicado          [ Despublicar ]
Instagram    ✕ erro               [ Tentar de novo ]
             Limite diário do Instagram atingido — sai amanhã
```

Instagram publicado **não tem botão**. É a diferença visível de P4, e está certa.

### 8.3 Control — conectar

Na aba Tráfego, ao lado do que já existe:

```
Conexão Meta
────────────────────────────────────────────────
Status      ● conectado
Página      Vitor Motos
Instagram   @vitormotos
            [ Reconectar ]
```

`atencao`, `expirado` e `revogado` aparecem com o motivo e o mesmo botão.

---

## 9. App Review

O portão externo, e o mais longo. **Não bloqueia o catálogo Meta** (spec irmã), então deve ser
aberto em paralelo desde já.

Permissões a pedir, **numa submissão só** (P8):

| Permissão | Para |
|---|---|
| `instagram_basic` | ler a conta |
| `instagram_content_publish` | publicar |
| `pages_show_list` | listar Páginas na conexão |
| `pages_read_engagement` | ler a Página |
| `pages_manage_posts` | publicar e remover no Facebook |

A Meta pede caso de uso e um vídeo do fluxo funcionando. Isso implica ter o fluxo rodando em
ambiente de teste **antes** de submeter — o App Review é o fim do desenvolvimento, não o começo.

Verificação de empresa é pré-requisito e é de calendário, não de código.

---

## 10. Testes

```bash
cd estoque-api   && .venv/bin/python -m pytest -q   # Win: .\.venv\Scripts\python.exe -m pytest -q
cd portal-gestao && .venv/bin/python -m pytest -q
cd revy-trafego  && .venv/bin/python -m pytest -q
```

`CanalFalso` do esqueleto (§7 de lá) é a base: falha programável, sem rede, sem credencial.

| Teste | Por quê |
|---|---|
| canal `manual` é chamado **exatamente uma vez** ao falhar | o post duplicado aparece no perfil da loja e não tem desfazer |
| **erro de rate limit reagenda; qualquer outro não** | §6.4 — se inverter, ou duplica post ou trava moto para sempre |
| Instagram não expõe `despublicar()` nem o botão | P4 |
| Facebook expõe os dois | P5 |
| `vender()` não zera `desejado` em nenhum dos dois | D1 |
| conexão `!= conectado` → não tenta, marca erro | §3.4 |
| foto 9:16 é preenchida para 1:1, não recortada | P9; regressão vira moto sem roda no perfil da loja |
| foto original fica intacta depois da publicação | §4.2; a vitrine e o catálogo usam a mesma foto |
| carrossel respeita `VeiculoFoto.ordem` e para em 10 | §4.3 |
| moto com 1 foto vira post simples | §4.3 |
| texto vazio no cadastro → texto gerado | §5; se sair post sem texto, o erro é invisível até alguém abrir o perfil |
| mensagem de erro não contém token nem payload | §6.5 |

---

## 11. Riscos e o que fica aberto

**Risco — a mudança de fotos é a maior da spec.** §4.1 toca o cadastro de **toda** moto,
inclusive de loja que não usa canal externo nenhum. É o ponto onde uma regressão afeta quem não
pediu nada disto.

**Risco — App Review negado.** Acontece, e o motivo costuma ser caso de uso mal explicado, não
código. Mitigação é de processo: submeter com o fluxo real gravado e a descrição do uso pela
revenda.

**Risco — post duplicado.** Está mitigado em três camadas (retry manual, `creation_id` guardado
antes do publish, teste de chamada única) porque é o erro que **não tem desfazer no Instagram**.

**Aberto — o token de Ads.** §3.1: migrar `meta_ads_config` para a conexão nova é decisão
separada, e vale tomar depois que esta conexão estiver rodando.

**Aberto — se o dono mudar de ideia sobre espaçar.** P3 escolheu publicar na hora. Se o perfil de
alguma loja piloto sofrer com cadastro em lote, espaçar é uma regra de intervalo no worker, sem
mudar modelo nem tela. Fica barato de reverter, e é por isso que a decisão simples foi aceitável.

**Não muda:** o Chatbot (D9), o n8n, o Motor, o catálogo Meta e a vitrine.
