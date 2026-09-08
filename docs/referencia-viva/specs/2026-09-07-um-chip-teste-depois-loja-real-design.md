# Um chip só: testar na loja `teste`, depois virar para a loja real — design

**Data:** 2026-09-07 · **Produtos:** chatbot-api (dono), revy-trafego (Control), Evolution/n8n (ops)

**Decisão do dono (07/09):** um único chip Vivo serve as duas fases. WABA no portfólio
**do amigo**. Loja destino **já existe e já opera Modo 1**. Dados do período de teste são
**apagados** no corte.

Spec-pai: [`2026-08-29-embedded-signup-tech-provider-design.md`](2026-08-29-embedded-signup-tech-provider-design.md).
Estado do dia: [`../handoff-contexto.md`](../handoff-contexto.md) (checkpoint 07/09).

---

## 1. O que este documento decide

O chip novo entra no Revy **uma vez só**, pela loja `teste`, e depois muda de dono sem
passar pelo popup de novo. O que se ganha: os quatro elos do onboarding rodam contra a
Graph de verdade num contexto onde errar não custa nada, e o registro do número na Meta
acontece **uma única vez** — o contador de `registro_tentativas` não é reiniciado pela
mudança de loja, e não precisa ser.

O que este documento **não** decide: se o número velho da loja do amigo continua vivo
depois do corte. Isso é §6, Fase C, e é decisão dele, não de código.

## 2. Por que a virada é barata (o que já está a favor)

Três coisas do desenho atual fazem a troca de `loja_id` bastar para o roteamento:

- **Inbound e outbound leem a mesma linha.** `cloud_canal.loja_id_do_phone_number_id`
  (`chatbot-api/app/cloud_canal.py:96`) resolve loja pelo `phone_number_id` gravado em
  `whatsapp_canais.evolution_instance`; `_loja_por_phone_number_id`
  (`chatbot-api/app/main.py:692`) delega a ele. `canal_cloud_da_loja`
  (`cloud_canal.py:36`) faz o caminho inverso pela mesma linha. Mudar `loja_id` vira os
  dois lados no mesmo instante, sem janela em que um lado enxergue uma loja e o outro
  enxergue outra.
- **O n8n é agnóstico de loja.** O `workflow-cloud.json` só carrega
  `instance = phone_number_id` e deixa o chatbot resolver de quem é (comentário no nó de
  handoff: *"um workflow serve N lojas, e sem ele o chatbot abriria o rodizio na loja do
  token, nao na de quem falou"*). **Nenhuma mudança de workflow no corte.**
- **O template segue a WABA, não a loja.** `aplicar_status_de_template`
  (`main.py:645`) casa a aprovação pelo `waba_id`. Como a WABA é do amigo e não muda, o
  template aprovado durante o teste continua valendo depois do corte.

Bônus: o catálogo que o bot responde vem de `provider.buscar(loja.slug, termo)`
(`main.py:1592`), com a loja resolvida pela instância. Trocou o `loja_id`, o bot passa a
falar do estoque do amigo sozinho.

## 3. As três armadilhas

### 3.1 `loja_id` é declarado imutável, e não existe caminho para mudá-lo

`WhatsAppCanal` (`chatbot-api/app/models_db.py:47`) abre com *"loja_id é imutável após
criação"*, e o repo cumpre: não há rota, não há `db.delete` de canal em lugar nenhum
(`channels.py`, `onboarding_cloud.py`), e `inactivate_channel` (`channels.py:234`) só
mexe em `ativo`, `estado` e `principal_estoque` — a linha e o valor único ficam.

`evolution_instance` é `UNIQUE` global (`models_db.py:51-53`, de propósito: um número
pertence a uma loja só), e o elo 1 recusa número já cadastrado
(`onboarding_cloud.py:63-72`). Então **repetir o popup apontando para a loja real está
fechado**: a única porta é escrever no banco.

Consequência de desenho: a virada é uma **operação administrativa fora do produto**, não
uma feature de tela. §5.1 define a forma dela.

### 3.2 Conversa é chaveada por `(canal_id, telefone)` — sem `loja_id` nenhum

`Conversa.__table_args__` (`models_db.py:192-197`) declara
`UniqueConstraint("canal_id", "telefone")`, e `_get_or_create_conversa`
(`servico.py:665`) busca exatamente por esse par e **devolve a conversa achada sem
conferir nem atualizar `loja_id`**. Quem chama é `registrar_mensagem`
(`servico.py:949-957`), com o canal vindo da instância.

O `canal_id` não muda quando o `loja_id` muda. Então toda conversa criada no teste fica
pendurada no canal com `loja_id` apontando para a loja `teste` — e o seu telefone, o do
amigo e o dos vendedores de teste são exatamente os que vão mandar mensagem depois do
corte. Cada um deles cairia na conversa velha, da loja errada, com o `bot_ativo` e o
`followup_toques` de lá.

É por isso que o corte apaga o histórico do teste (§5.3), e não só reetiqueta.

### 3.3 Modo 2 sequestra **todo** o outbound da loja, inclusive o do número velho

`outbound_para_loja` (`chatbot-api/app/whatsapp_outbound.py:366`):

```python
if loja_opera_modo2(db, loja_id):
    return CloudWhatsAppOutbound()
return get_whatsapp_outbound()
```

`loja_opera_modo2` (`rodizio.py:55`) é por **loja**, não por canal. E
`resolve_canal_for_instance` (`channels.py:441`) **não filtra `ativo`** — inbound da
Evolution continua entrando mesmo com o canal marcado inativo.

Junte os dois na loja do amigo, que hoje é Modo 1: no minuto em que o Control projetar
`whatsapp_modo=2`, um cliente que escrever no **número antigo** dela tem a mensagem
recebida normalmente e a **resposta sai pelo número novo**. Do lado do cliente é o bot
sumindo e um desconhecido aparecendo.

Isto não é bug: a coexistência por vendedor foi recusada em 13/08
(`decisoes/2026-08-13-whatsapp-dois-modos-sem-coexistencia.md`) e o desenho assume a loja
inteira num modo só. Mas é a consequência que precisa estar decidida **antes** do corte,
não descoberta durante.

## 4. Pré-requisitos (nada disto é código novo)

| # | O que | Onde | Verificação |
|---|---|---|---|
| 1 | Loja `teste` ativa e projetada Modo 2 | Control | conferido em prod 07/09: `('teste','loja','ativa')` e `('teste','whatsapp_modo','2')` |
| 2 | As três flags em `1` no `app2037` | secrets | `REVY_CONTROL_WHATSAPP_MODO2_ENABLED`, `CHATBOT_WHATSAPP_MODO2_ENABLED`, `MULTI_WHATSAPP_ENABLED` — todas em `1` desde 23/08 |
| 3 | Popup do embedded signup passando | navegador | o *"Recurso indisponível"* de 07/09 tem de ter sumido. **Gate: não compre o chip antes disto.** |
| 4 | Estoque semeado na loja `teste` | Estoque API | sem veículos no slug `teste` o bot testa metade de si mesmo |
| 5 | `AgenteConfig` publicada na loja `teste` | Loja → Agente | o prompt é metade template, metade dado (`learnings/2026-08-25-o-prompt-e-metade-template-metade-dado`) |
| 6 | Fila de vendedores na loja `teste` | Loja → Agente | `FilaVendedor.usuario_id` aponta para `Usuario.id` do Portal; sem vínculo o sino 1:1 não toca |

## 5. O que precisa ser construído

### 5.1 Um script administrativo, não uma rota

Expor `POST /canais/{id}/mover` daria a qualquer loja um caminho para roubar o número de
outra — a `UNIQUE` global existe justamente para impedir isso. A virada é rara, é sempre
com o dono presente, e o lugar dela é `fly ssh console`.

**Entregável:** `chatbot-api/scripts/mover_canal_de_loja.py`, com teste em
`chatbot-api/tests/`.

Argumentos: `--phone-number-id`, `--para-slug`, `--apagar-dados-da-origem`, `--dry-run`.

Uma transação só, nesta ordem:

1. Carrega o canal por `evolution_instance == phone_number_id`. Ausente → sai com erro.
2. Carrega a loja destino por slug. Confere `allows_processing` (`provisioning.py:30`) —
   destino sem projeção `ativa` aborta, porque o Modo 2 seria fail-closed logo depois.
3. Recusa se houver `OfertaLead.estado == 'aberta'` na loja de origem: mover no meio de um
   rodízio deixa a oferta órfã apontando para `fila_vendedor` de outra loja.
4. Se `--apagar-dados-da-origem`: apaga na ordem de FK (§5.3).
5. `canal.loja_id = <destino>`. Não toca em `evolution_instance`, `waba_id`,
   `token_cifrado`, `pin_cifrado`, `registro_tentativas` nem `template_oferta` — tudo isso
   é da WABA e do número, não da loja.
6. Se `canal.estado == 'cloud_pendente'`, deixa como está: quem libera é o Control (§5.4).
7. Imprime antes/depois. `--dry-run` faz tudo e dá `rollback`.

**Testes obrigatórios.** O banco de teste do chatbot é um só e não se limpa entre testes,
então use `phone_number_id` próprio da faixa `1227059273831581+` — antes de escolher,
`rg 12270592738 tests/` (`learnings/2026-08-29-o-banco-de-teste-do-chatbot-e-um-so`):

- move e o `loja_id_do_phone_number_id` passa a devolver o destino;
- move e `canal_cloud_da_loja(destino)` devolve o canal, `(origem)` devolve `None`;
- destino sem projeção `ativa` → aborta e nada muda;
- oferta aberta na origem → aborta e nada muda;
- `--dry-run` não persiste;
- com `--apagar-dados-da-origem`, a conversa antiga daquele `(canal_id, telefone)` some, e
  a mensagem seguinte cria conversa nova já com o `loja_id` do destino.

O último teste é o que fecha §3.2 — é ele que prova que a armadilha morreu.

### 5.2 O que **não** se constrói

- Rota HTTP de mover canal (§5.1).
- Tela no Control ou na Loja. Isto acontece uma vez.
- Migration. Nenhuma coluna muda.
- Mudança no `workflow-cloud.json` (§2).

### 5.3 A limpeza dos dados de teste

Ordem ditada pelas FKs (`mensagens → conversas` e `→ leads`; `consentimentos → leads`;
`ctwa_auditoria → leads`; `oferta_lead → fila_vendedor`). Tudo filtrado por
`loja_id = <loja teste>`:

```
mensagens → conversas → consentimentos → ctwa_auditoria →
catalog_attributions → oferta_lead → leads → rodizio_ponteiro
```

`fila_vendedor` da loja `teste` **fica**: é cadastro, não tráfego, e serve o próximo
teste. `whatsapp_canais` da origem não tem mais nada — o canal mudou de dono no passo 5.

A fila do destino **não** vem junto: `FilaVendedor.usuario_id` aponta para usuários do
Portal da loja de origem, e vendedor de teste no rodízio do amigo receberia lead real.

### 5.4 A liberação do canal

`_liberar_canal_cloud` (`provisioning.py:72`) sobe `cloud_pendente → cloud_ativo`, e só
roda quando um envelope de projeção é **aplicado** — `_apply_envelope`
(`provisioning.py:91`) descarta versão igual ou menor como `idempotent`/`stale`.

O gatilho existe e é confiável: `set_whatsapp_mode`
(`revy-trafego/app/control/stores.py:255`) faz `loja.versao = loja.versao + 1`
**sempre**, mesmo escolhendo o modo que já estava, e o envelope sai com
`version=store.versao` (`revy-trafego/app/control/provisioning.py:76-89`).

Traduzindo para o corte: **salvar Modo 2 no Control para a loja do amigo, depois de o
canal já estar lá, faz as duas coisas de uma vez** — projeta o modo e acende o canal. Por
isso a ordem da Fase D é mover primeiro, Control depois.

## 6. Runbook

### Fase A — antes de comprar o chip

1. Abrir `/app/loja/whatsapp/conectar` logado na loja `teste` e confirmar que a janela da
   Meta passa. O *"Recurso indisponível"* de 07/09 era propagação; se persistir, **pare** e
   investigue antes de gastar dinheiro.
2. Pré-requisitos 4, 5 e 6 da tabela §4.
3. `mover_canal_de_loja.py` escrito, testado e no `main`. Não se escreve script de corte no
   dia do corte.

### Fase B — o teste (loja `teste`)

4. Chip no aparelho. Popup logado na Loja como `teste` **e** na conta Meta do amigo. Um
   erro no elo 3 gasta uma das 5 tentativas do teto (`onboarding_cloud.py:24`); a Meta
   trava o número por 3 dias em 10. Não repita às cegas.
5. Se o canal ficar `cloud_pendente`: salvar Modo 2 na loja `teste` no Control (§5.4).
6. Esperar a Meta aprovar o template. `template_oferta` preenchido no canal é o sinal.
7. Exercitar: mensagem de cliente → bot responde → handoff abre rodízio → vendedor clica
   "Peguei" → lead trava. Áudio e imagem também
   (`learnings/2026-08-25-corpo-assinado-pela-meta-nao-sobrevive-ao-n8n`).
8. Exercitar os **três caminhos de desistência** do popup, que nunca rodaram.

### Fase C — a decisão que não é técnica

9. Decidir o destino do número antigo da loja do amigo (§3.3). Duas saídas:

   - **Aposentar.** Desconectar a instância na Evolution antes do passo 11. O bot passa a
     atender só no número novo, e quem escrever no antigo não recebe nada — que é o que se
     espera de um número fora de operação.
   - **Manter humano.** O número antigo continua no celular do vendedor, mas a instância
     sai da Evolution do mesmo jeito. O que não pode é ficar conectada: aí o inbound entra
     e a resposta sai pelo número errado.

   Marcar `inativar` no canal Modo 1 **não** resolve — `resolve_canal_for_instance`
   (`channels.py:441`) ignora `ativo`. O corte é na Evolution.

### Fase D — o corte

10. Janela sem tráfego. Backup do banco (`suite-pg`).
11. `--dry-run` primeiro, ler a saída, depois valendo:

    ```
    fly ssh console -a app2037
    cd /app/chatbot-api
    python scripts/mover_canal_de_loja.py \
      --phone-number-id <id> --para-slug <slug-do-amigo> \
      --apagar-dados-da-origem --dry-run
    ```

12. Control: salvar **Modo 2** na loja do amigo. Projeta o modo e libera o canal (§5.4).
13. Loja do amigo: cadastrar a fila de vendedores reais, com vínculo de usuário.
14. Loja do amigo: publicar a config do Agente dela.

### Fase E — verificação

15. `GET /v1/whatsapp/canais` autenticado como a loja do amigo lista o canal Cloud.
16. Mensagem real de um telefone **que não participou do teste** → conversa nasce com o
    `loja_id` do amigo, e o bot responde citando o estoque **do amigo**.
17. Handoff → rodízio → oferta cai num vendedor real.
18. Loja `teste`: tela de Números vazia, Conversas vazia.

### Rollback

Rodar o script ao contrário (`--para-slug teste`) devolve o canal. O que **não** volta é o
histórico apagado no passo 11 — daí o backup do passo 10 ser obrigatório, não recomendado.
Nada do lado da Meta é tocado pelo rollback: WABA, número, registro e template ficam onde
estão.

## 7. Riscos aceitos

| Risco | Por que é aceitável |
|---|---|
| Escrita direta no banco de produção | Uma linha, uma transação, script testado, `--dry-run` antes. A alternativa era uma rota HTTP com risco permanente para todas as lojas. |
| Quebra do invariante "`loja_id` imutável" | O invariante protege contra troca acidental por API. Um script administrativo com o dono presente não é o caso que ele protege. Atualizar o comentário em `models_db.py:48` para *"imutável pela API; muda só por `scripts/mover_canal_de_loja.py`"*. |
| Número novo já registrado na WABA do amigo | É o ponto: registrar uma vez só. O corte não mexe em `registro_tentativas` nem chama a Graph. |
| `config.GRAPH_TOKEN` é um só para todas as WABAs | `CloudWhatsAppOutbound` (`whatsapp_outbound.py:221`) usa o token de System User da Revy, não o do canal. Ele alcança a WABA do amigo porque o elo 2 inscreveu o app nela. Remover a inscrição do lado dele derruba o envio — vale saber, não vale bloquear. |

## 8. Como saber que acabou

```
cd chatbot-api
.\.venv\Scripts\python.exe -m pytest tests -q       # Windows
.venv/bin/python -m pytest tests -q                 # macOS
```

Control não recebe código aqui, só cliques na tela. Se algo em `revy-trafego` mudar, a
suíte dele também.

`git diff --check` e `git status --short`. Não regera mapa: nenhuma rota, modelo, worker,
migration ou flag muda — o script novo não entra nele.
