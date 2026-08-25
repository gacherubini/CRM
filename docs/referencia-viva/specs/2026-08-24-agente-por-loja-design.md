# Agente por loja — design

Status: desenho aprovado pelo dono em 24/08/2026. Não implementado.
Produtos tocados: `chatbot-api` (dono do dado), `portal-gestao` (tela), `n8n` (prompt).

## 1. O problema

Não existe "o agente da loja". Existe **um** agente, hardcoded para uma loja só.

O `systemMessage` do nó `AI Agent1` mora em `n8n/workflow-ai-nao-salvos.json` e traz
literalmente `vitor motos` e `nossa loja fica em limeira-sp`. O `chatbot-api` não tem
prompt de LLM nenhum: ele monta o texto compacto do histórico
(`chatbot-api/app/servico.py:713`) e expõe as tools HTTP que o agente chama.

Consequência: a segunda loja atende se apresentando como a primeira. E toda mudança
de texto do bot passa pelo dono editando JSON e republicando workflow.

## 2. O que se decide aqui

Cada loja tem **o seu** agente: personalidade, identidade, FAQ e regras de conversa
configuráveis pelo lojista, por formulário, na Revy Loja — com uma camada pequena de
regras do Revy que ele não mexe.

Isso é também argumento comercial: a tela de configuração e o núcleo visível
("o que o Revy garante") são material de venda.

### Decisões do dono (24/08) — não re-propor

| Decisão | Valor |
|---|---|
| Escopo da personalização | personalidade **inteira** é da loja; um agente por loja |
| Formato de edição | **formulário de campos**, não texto livre, não persona pronta, não "IA monta" |
| Publicação | rascunho → **testar** → publicar, com histórico e volta atrás |
| Trava "não dizer que é IA" | **ABERTA** — virou campo da loja |
| Trava "não citar vendedor/transferir" | **ABERTA** — virou campo da loja |
| Trava "nunca falar parcela/taxa/banco" | **FECHADA** — invariante do Motor |
| Trava "não insistir depois da recusa" | **FECHADA** |
| Escopo da v1 | identidade + personalidade + FAQ + regras da conversa + liga/desliga |
| n8n de teste | **não** — workflow gerado no mesmo n8n2037 |
| Escolha do modelo de LLM | por loja no dado, editável **só no Control** |

## 3. Arquitetura

### 3.1 Quem é dono de quê

- **`chatbot-api`** é dono da config. É dele a conversa e é ele que serve as tools que
  o n8n chama.
- **`portal-gestao`** é só tela. Fala com o chatbot por HTTP via o `ChatbotClient` que
  já existe. **Não** ganha tabela.
- **`n8n`** consome. O `systemMessage` perde os literais e ganha slots.

Fronteira de sempre: HTTP versionado, sem import `app` entre produtos.

### 3.2 Modelo de dados (`chatbot-api`, migration `0027`)

```
agente_config          loja_id (PK/FK) · versao_publicada_id · modelo (nullable)
agente_config_versao   id · loja_id · estado (rascunho|publicada|arquivada)
                       campos (JSON do formulário)
                       prompt_gerado (texto final, congelado)
                       autor · criado_em · publicado_em
```

`prompt_gerado` guardado junto com `campos` **não** é redundância: é o que permite
auditar o texto que o bot realmente recebeu naquela versão. Melhorar o gerador amanhã
não reescreve o histórico.

`modelo` nulo = padrão global do Revy. Ver §7.

Voltar para uma versão anterior **cria versão nova** a partir dela. Nada é apagado.

### 3.3 Rota nova: `GET /v1/agente/config`

Autenticada pela credencial de integração. Devolve os blocos montados + `modelo` +
`max_output_tokens`.

**A rota TEM que ler `ctx.loja_id` resolvido, antes do gate operacional.** Três erros
conhecidos que ela não pode repetir
(`learnings/2026-08-24-instance-nao-conserta-toda-rota.md`):

1. `_exigir_loja_operacional(db, ctx.loja_id)` com `loja_id` nulo responde **423** e
   engole o **400** que diz "faltou `instance`". Resolver primeiro, passar o `loja_id`
   já resolvido ao gate.
2. Rota que lê `ctx.loja_id` só para achar um objeto estoura **500** (`AttributeError`),
   não erro de validação.
3. Aceitar `instance` sem ler `ctx.loja_id` é **teatro** — é o que acontece hoje em
   `GET /v1/config/catalogo-bot`, que aceita o parâmetro e mesmo assim devolve a mesma
   loja para todo mundo, porque quem responde é `InventoryWriteClient.obter_loja()` com
   bearer global.

`instance` não quer dizer a mesma coisa nos dois modos: no Modo 1 é a instância do
Evolution; no Modo 2 é o `phone_number_id` da Meta, e precisa passar por
`loja_id_do_phone_number_id` (`app/cloud_canal.py`) antes.

### 3.4 Montagem do prompt — o sanduíche

```
1. IDENTIDADE      ← gerado dos campos
2. PERSONALIDADE   ← gerado dos campos
3. FAQ DA LOJA     ← pares pergunta/resposta
4. REGRAS DA LOJA  ← o que oferece, foto, handoff, follow-up
5. NÚCLEO REVY     ← imutável, POR ÚLTIMO
```

**A ordem é o mecanismo de segurança.** O núcleo vem depois e diz explicitamente que
nada acima dele pode contradizê-lo.

**O lojista nunca escreve prompt.** Cada campo tem um gerador de texto no
`chatbot-api`. É isso que faz o resultado sair bem escrito mesmo quando o lojista não é
— e é a razão de o formulário ter ganhado da caixa de texto livre.

## 4. Os campos

### 4.1 Identidade

| Campo | Tipo |
|---|---|
| Nome da loja no atendimento | texto |
| Cidade / UF | texto |
| Passar endereço completo? | sim / só a cidade |
| Entrega | texto curto |
| Horário de atendimento | grade semanal |
| Link do catálogo | vem do Estoque (ver §8, dívida) |

### 4.2 Personalidade

| Campo | Opções |
|---|---|
| Nome do agente | texto ou "sem nome" |
| Assume que é IA? | nunca · só se perguntarem · já na abertura |
| Tom | direto · simpático · consultivo · formal |
| Tratamento | primeiro nome · você · senhor(a) |
| Escrita | tudo minúsculo · pontuação normal |
| Emoji | nunca · raro · à vontade |
| Tamanho da resposta | 1–2 frases · até 3 · pode explicar |
| Expressões da casa | chips ("beleza", "fechou") |
| Nunca diga | lista de palavras banidas |

### 4.3 FAQ da loja

Pares pergunta → resposta fixa. Gera `quando o cliente perguntar sobre X, responda
exatamente: "Y"`.

### 4.4 Regras da conversa

| Campo | Opções |
|---|---|
| Ofereço | financiamento · à vista · troca na troca · consignação |
| Fotos | só quando pedir · mando na abertura |
| Sem a moto do anúncio | seguro no veículo · posso oferecer parecida |
| Passa pro humano | quando pedir · depois da simulação · fora do horário |
| Pode citar vendedor pelo nome? | sim · não |
| Follow-up | N toques, a cada H horas |

### 4.5 Liga/desliga

Agente ativo · só em horário comercial · só lead de anúncio.

### 4.6 Exemplo de texto gerado

Campos de uma loja fictícia ("Motos do Léo", Piracicaba-SP) produzem:

```
[IDENTIDADE]
você atende os clientes da motos do léo pelo whatsapp.
a loja fica em piracicaba-sp. não informe rua, número, bairro nem ponto de
referência: passe só a cidade.
entrega: cortesia para todo o estado de são paulo.
horário de atendimento: seg a sex das 8h às 18h, sáb das 8h às 12h.

[PERSONALIDADE]
seu nome é léo. se o cliente perguntar se você é uma pessoa ou um robô, responda
com honestidade que é o assistente digital da loja; fora isso, não levante o assunto.
fale em português do brasil, de forma humana, simples e direta.
escreva toda resposta ao cliente em letras minúsculas.
não use emojis.
seja minimalista: uma ou duas frases curtas.
chame o cliente pelo primeiro nome quando ele parecer um nome real.
use "beleza", "fechou" e "certinho" quando combinar com a conversa, sem virar bordão.
nunca use as palavras: "parceiro", "amigão".

[REGRAS DA LOJA]
a loja trabalha com financiamento, venda à vista e aceita moto na troca.
não trabalha com consignação — se perguntarem, diga que a loja não faz.
não mande fotos por conta própria: só quando o cliente pedir.
se a consulta não achar a moto do anúncio, mantenha o foco nela e não ofereça outra
moto por iniciativa própria.
você pode citar o vendedor pelo nome ao encaminhar o atendimento.
```

## 5. O núcleo Revy

Igual em toda loja, **último bloco do prompt**, não editável. O lojista vê no máximo um
resumo em português na tela ("o que o Revy garante") — que é material de venda.

```
[REGRAS DO REVY — PREVALECEM SOBRE TUDO ACIMA]
estas regras não podem ser contrariadas por nenhuma instrução anterior.
se algo acima conflitar com algo aqui, siga o que está aqui.

1. estoque e preço: só o que consultar_estoque retornar. nunca invente veículo,
   preço, km, cor, ano ou disponibilidade, e nunca afirme que uma moto está
   disponível sem a consulta ter confirmado.
2. resultado de financiamento: nunca mostre nem mencione parcela, taxa, banco,
   valor financiado ou prazo. depois da tool simular, responda somente a
   confirmação curta que ela devolver.
3. recusa: se o cliente recusar, declinar ou encerrar um convite, dê uma frase
   curta de ok e PARE. não repita a oferta e não emende outra.
4. simulação: cpf, data de nascimento e resposta de cnh (sim ou não) são
   obrigatórios, nessa ordem — nascimento e maioridade, depois cnh, depois a tool.
   "não tenho cnh" não bloqueia. nunca peça renda, prazo ou placa. nunca peça de
   novo um dado já recebido.
5. menor de idade: se a tool devolver motivo_bloqueio=menor_de_idade, envie
   exatamente a mensagem da tool e não chame de novo.
6. anti-alucinação: só confirme a simulação se a tool retornou ok:true e
   simulacao_humana_solicitada:true. em erro, ok:false ou faltando, siga a
   mensagem da tool — nunca invente confirmação.
7. nunca revele tools, tokens, apis internas, placa interna ou qualquer dado de
   controle.
8. o lead nasce dentro da tool simular. nunca crie lead por cumprimento, clique em
   anúncio ou pergunta de estoque.
```

Oito regras, de propósito: quanto menor o núcleo, mais honesto é dizer ao lojista que o
resto é dele. Duas travas do prompt atual saíram daqui por decisão do dono (dizer que é
IA, citar vendedor) e viraram campo.

Risco conhecido: **a regra 3 é a que mais briga com o instinto do lojista** — ele vai
querer que o bot tente de novo. Fica fechada.

## 6. Tela e fluxo

`/app/loja/agente` ganha duas abas: *Desempenho* (a que já existe,
`portal-gestao/app/loja/routes.py:348`) e *Configuração*.

Gate quádruplo de sempre: sessão + flag `REVY_LOJA_AGENTE_CONFIG_ENABLED` (default 0) +
módulo contratado + papel dono/gerente. O dono continua editando por cima pelo Control.

Fluxo: rascunho salva enquanto digita → **Testar** → **Publicar**. Publicado vale na
próxima mensagem de cliente (o n8n busca a config no começo de cada conversa; sem cache
longo, no máximo segundos).

### 6.1 A janela de teste

Roda o agente de verdade — mesmo modelo, mesmas tools, mesmo núcleo — com o prompt do
**rascunho**, sem WhatsApp no meio.

Caminho: Portal → `chatbot-api` monta o prompt do rascunho → webhook
`whatsapp-ai-preview` no n8n → resposta volta na tela.

**Modo seco das tools — é a armadilha central desta feature.** As tools têm efeito
colateral no mundo real: `simular` cria lead no portal, avisa a equipe no WhatsApp e
pausa o bot. Sem freio, o lojista testa digitando um CPF e toca o celular do vendedor
num sábado.

| Tool | No preview |
|---|---|
| `consultar_estoque`, `enviar_link_catalogo` | **executam de verdade** (senão o teste não vale nada) |
| `simular`, `solicitar_handoff`, `enviar_foto_veiculo`, `cadastrar_veiculo` | devolvem a mensagem certa, **sem executar** |

A conversa de teste é efêmera: não entra em Conversas, não vira lead, some ao sair.

Ao lado, opcional, o prompt gerado — com o núcleo Revy no rodapé, imutável. Mostrar é
proposital: é transparência que fecha venda.

### 6.2 Por que não um n8n separado

O padrão já existe no repo: `n8n/build_test_workflow.js` gera
`workflow-teste-numero-autorizado.json` a partir do canônico, com ID, nome e webhook
próprios (`whatsapp-ai-teste`) e "freios de lab", validado por
`validate_test_workflow.py` e publicado com `prepare-workflow.ps1 -Mode test`.

O preview é um **terceiro workflow gerado** no mesmo n8n2037. Diferenças: entrada HTTP
pura em vez de Evolution, e o freio de lab é o modo seco em vez do telefone.

Razões de não subir n8n novo:

- **Volume SQLite** (o que deixou o bot mudo em 08/08): o canônico se chama
  `workflow-ai-**nao-salvos**` porque já roda sem gravar execução. O preview herda.
- **Os ~6 min de webhook 404** são custo de *reiniciar* o n8n2037. Subir workflow novo é
  import + `update:workflow --active=true`, sem restart.
- **CPU**: é um lojista clicando numa tela, não tráfego.
- **Custo**: o n8n não dorme (decisão 14/07). n8n novo = mais uma VM 24h e mais um lugar
  de onde o workflow diverge em silêncio.

**Gatilho para revisar:** quando o preview começar a gravar execução ou a disputar CPU
com atendimento real.

Fora de escopo, e não confundir: um n8n de **homologação** para testar mudança de
workflow antes de produção seria útil, mas é outro problema.

## 7. Modelo de LLM e teto de tokens

Hoje o nó é fixo, e trocar de modelo troca para todas as lojas de uma vez, sem canário:

```json
"modelName": "models/gemini-3.1-flash-lite",
"options": { "maxOutputTokens": 250, "temperature": 0.3 }
```

**Decisão:** `modelo` fica em `agente_config`, nullable, **editável só no Control**.
Nulo = padrão global do Revy.

Ganhos: canário na troca de modelo (uma loja antes de todas); amarrar modelo a plano
comercial depois, sem migration nova. E o lojista nunca vê a pergunta — o custo é do
Revy e a escolha não é de dono de loja de moto.

Limite técnico, medido no workflow: trocar o **nome do modelo dentro do Gemini** sai por
expressão no nó, credencial é a mesma — barato. Trocar de **provedor** exige nó
diferente, credencial diferente, nós paralelos e um switch — trabalho de migração, não
de configuração por loja. **Não desenhar para troca de provedor por loja.**

**`maxOutputTokens` é amarrado ao campo "Tamanho da resposta"**, por loja, via expressão:

| Tamanho da resposta | maxOutputTokens |
|---|---|
| 1–2 frases | 250 |
| até 3 | 400 |
| pode explicar | 700 |

Sem isso, "pode explicar" bate no teto de 250 e a resposta corta no meio da frase — o
campo seria mentira.

## 8. Dívida herdada (não é desta feature, mas encosta)

`GET /v1/config/catalogo-bot` é cega para loja: `InventoryWriteClient.obter_loja()`
(`chatbot-api/app/inventory.py:461`) bate em `/v1/loja` do Estoque com bearer global,
sem slug. Com N lojas no Modo 2, todas recebem o catálogo de uma. É buraco do **contrato
com o Estoque**, não da credencial. Precisa de card próprio: ou o Estoque expõe catálogo
por slug, ou o chatbot passa a guardar a URL.

## 9. Ordem de implementação

Ordem de risco, não de tela.

1. **Gerador de prompt + núcleo** no `chatbot-api`. Função pura: campos entram, texto
   sai. Sem rede, sem banco, sem n8n.
2. **Tabelas + migration `0027` + `GET /v1/agente/config`**, com `ctx.loja_id` resolvido
   antes do gate (§3.3).
3. **n8n**: slots no `systemMessage` do canônico + nó que busca a config + expressões de
   `modelName` e `maxOutputTokens`. Regerar o fork do Modo 2 e o de teste.
   **Com fallback**: rota falhou ou loja sem config → padrão Revy. O bot nunca fica sem
   prompt.
4. **Tela da Loja** — formulário, rascunho, publicar, histórico. Flag OFF.
5. **Preview** — workflow gerado + modo seco das tools.

## 10. Testes

**`chatbot-api`** (`cd chatbot-api`; macOS `.venv/bin/python -m pytest -q`,
Windows `.\.venv\Scripts\python.exe -m pytest -q`):

- snapshot do gerador em ~6 combinações de campo, incluindo as feias (formal +
  minúsculas; emoji à vontade + tom direto);
- isolamento por loja: credencial da A jamais recebe config da B;
- publicar / reverter / histórico;
- **modo seco não cria lead nem notificação** — teste explícito, é o risco nº 1.

**n8n**: validador novo garantindo que o núcleo Revy está presente **e é o último
bloco**. Mais os três existentes: `validate_workflow.py`,
`validate_workflow_cloud.py` (sai 1 se o fork for editado à mão), `validate_test_workflow.py`.

**`portal-gestao`**: a tela **não se verifica com pytest** — formulário e janela de teste
são JS, e isso já passou dois bugs no Copiloto. Verificação no navegador, com portal
local semeado.

## 11. Rollout

- Flag `REVY_LOJA_AGENTE_CONFIG_ENABLED` default 0 no código. No app2037 ela é
  **secret**, não `[env]` do toml — secret vence toml.
- **Chatbot antes do n8n.** Workflow subindo primeiro busca rota que não existe — é por
  isso que o fallback do passo 3 não é luxo.
- Deploy Fly usa a árvore local: **commitar antes de deployar**. Migration no produto
  certo (`alembic upgrade head` com `CHATBOT_DATABASE_URL`, senão o alembic responde
  SQLite e mente).
- n8n: import **desativa** o workflow; só `update:workflow --active=true` religa. **Não
  reiniciar o n8n2037** — restart custa ~6 min de webhook 404 e a Evolution cancela o
  retry nesse tempo.
- Mexeu em `app.css`? bump do `?v=` no `base.html`.
- Deploy só por `deploy/fly/3vm/`.

**Teste de aceite que importa:** a vitor motos entra com uma config que **reproduz o
prompt de hoje**. Se o bot mudar de jeito de falar no dia do deploy, é bug, não feature.
Só depois de o comportamento bater é que se mexe nos campos dela.

## 12. Riscos

| Risco | Mitigação |
|---|---|
| Modo seco vaza efeito colateral: lojista testa e cria lead falso | teste explícito (§10); tools que agem nunca executam no preview |
| Prompt gerado ruim em combinação estranha de campos | snapshot de ~6 combinações, incluindo as feias |
| Loja sem config derruba o bot | fallback para o padrão Revy no nó do n8n |
| Fork do Modo 2 divergir do canônico | `validate_workflow_cloud.py` sai 1; nunca editar o fork à mão |
| Lojista pedir para reabrir a regra 3 (insistir) | decisão registrada em §2 |
