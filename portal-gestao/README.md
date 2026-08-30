# Revy Loja (diretório `portal-gestao`)

Frontend operacional da loja: FastAPI + páginas Jinja. Papéis `dono`, `gerente`,
`vendedor`, `admin_plataforma`. O diretório mantém o nome histórico `portal-gestao`; a UI
se chama **Revy Loja**.

Tokens das APIs ficam **somente no servidor**; o navegador recebe uma sessão assinada.

## Armadilhas — leia antes de mexer

- **O Portal fala com o chatbot pela credencial da loja da SESSÃO.** O chatbot resolve a
  loja **pelo token**, então um token só num deploy multi-loja faz toda tela mostrar a
  mesma loja — em 24/08 a tela do Agente com a loja `teste` selecionada exibiu os 1104
  atendimentos da `moto-center`, número a número. `get_chatbot_client` (`app/main.py`)
  recebe o `Request` por isso; **não** volte a montá-lo sem ele, e não chame o
  `ChatbotClient` direto passando `settings.chatbot_token`. O mapa é
  `CHATBOT_API_TOKENS_JSON` (`{"slug": "token"}`), no formato do Control. Loja fora do
  mapa fica **sem token** de propósito: a tela diz "indisponível" em vez de mostrar,
  com confiança, o número de outra loja. Sem mapa e sem `CHATBOT_API_LOJA_SLUG`, o token
  global vale — é o contrato de "deploy de uma loja só", e é o que mantém instalação
  antiga de pé. Emitir o token de cada loja:
  `python -m app.cli criar-credencial-loja --slug <loja>` no `chatbot-api`.

- **Todo erro HTTP do `ChatbotClient` vira "não foi possível acessar o chatbot agora"
  se não ganhar escape.** O `_request` (`app/clients/chatbot.py`) termina em
  `raise_for_status()` dentro de um `except (httpx.HTTPError, ValueError)` que levanta
  `ChatbotIndisponivel` — e `HTTPStatusError` **é** `HTTPError`. Status que a tela
  precisa distinguir pede escape explícito: hoje existem `erro_404`, `erro_409`,
  `erro_422` e `erro_502` (este levanta `OnboardingFalhou(mensagem, elo=...)`, para o
  lojista ler qual passo parou em vez de "erro de conexão"). Falha de rede **continua**
  `ChatbotIndisponivel`: são situações diferentes e pedem frases diferentes. Já custou
  uma tela errada duas vezes. O construtor aceita `transport=` (keyword-only) porque é
  o único jeito de um teste exercitar o `_request` de verdade — o padrão de sobrescrever
  `_request` numa subclasse não serve quando o que está sob teste é o próprio `_request`.
- **Custo do veículo, lucro, tokens e credenciais do Motor nunca aparecem para vendedor.**
  Aplique RBAC no backend, não escondendo item de menu. Vale para toda superfície
  do módulo Financeiro (telas e JSON).
- **Despesa fixa não é rateada por venda.** Decisão do dono (16/08): ratear faria o
  lucro de uma moto depender de quantas outras foram vendidas no mês. Quem responde
  "essa moto pagou a estrutura?" é o **ponto de equilíbrio** em `app/loja/financeiro.py`.
  Margem parcial não vira estimativa: sem custo em alguma venda, lucro operacional e
  ponto de equilíbrio ficam **indisponíveis**.
- **Apagar venda ≠ cancelar.** `cancelada` é negócio desfeito e fica no histórico;
  `excluida` é registro errado — some de listas e totais, mas a linha permanece com
  autoria. Consulta nova sobre `Venda` precisa excluir `status == "excluida"`.
- **Item novo no menu do shell precisa de duas coisas:** `page_title` no template e ícone
  no dicionário `loja_icons` de `base.html`. Sem `page_title` a topbar escreve "Ajustes";
  sem ícone, `tests/test_loja_navigation.py::test_shell_nav_todos_os_itens_tem_icone` falha.
- **O Portal não chama a Meta nem o Revy dentro da requisição.** Confirmação e
  cancelamento de venda saem por outbox transacional criptografado.
- **Não leia tabela do Revy nem do Chatbot por SQL.** O Portal é fonte da verdade de
  CRM/vendas; o resto vem por HTTP.
- **`FAMILIA_ANUNCIO` / mapa de rótulos em `app/loja/sales_overview.py` é duplicação
  consciente** com `chatbot-api/app/servico.py` — produtos diferentes, sem import entre
  eles. Mudou lá, muda aqui.
- **Sem `create_all` no boot.** Falha de migração tem de impedir readiness/deploy.
- Antes de mudar as telas da Loja, leia
  [`../docs/referencia-viva/2026-08-07-triagem-revisao-ux-loja-control.md`](../docs/referencia-viva/2026-08-07-triagem-revisao-ux-loja-control.md):
  parte do que "parece faltando" foi **recusado pelo dono**.
- O `app.css` **não** pode reabrir `:root` para declarar token de marca: ele carrega depois
  do `revy-tokens.css` e a redeclaração anula a fonte única.
  `shared/brand/tests/test_app_css.py` falha se acontecer.
- **Copiloto: sem PII no prompt e o LLM não inventa cifra.** Número vem da ferramenta
  tipada; fonte fora → `indisponivel`, nunca zero. Identidade (`loja_slug`, papel) não
  entra no schema das tools — vem de `CopilotoContexto`. Simulação de financiamento
  no chat foi **retirada** (CPF no provedor).
- **Copiloto some com qualquer um dos três gates off:** `REVY_LOJA_SHELL_ENABLED`,
  `REVY_LOJA_COPILOTO_ENABLED` e entitlement `Module.COPILOTO`. Só dono/gerente.
  A chave `REVY_LOJA_COPILOTO_LLM_KEY` nunca vai ao `[env]` do Fly nem ao git.

## Onde editar

| Arquivo | Responsabilidade |
|---|---|
| `app/main.py` | Bootstrap, middleware, auth, rotas legadas restantes, helpers de template |
| `app/loja/` + `app/web/loja_*.py` | Shell Revy Loja (domínio + rotas) |
| `app/web/loja_whatsapp.py` + `app/loja/whatsapp_canais.py` | Números de WhatsApp: canais Evolution, conexão pela nuvem e fila do Modo 2 |
| `app/loja/copiloto/` + `app/web/loja_copiloto.py` | Copiloto: tools, sinais, FIPE, ações, chat, sino |
| `app/copiloto_sinais_job.py` · `app/copiloto_purge_job.py` | Worker de regras e retenção |
| `app/loja/routes.py` | Atendimento (chat, envio, polling, visão do agente) e **configuração do agente** |
| `app/loja/sales_overview.py` | Visão geral de Vendas e painel de aquisição |
| `app/web/simulacoes.py` | Simulação manual, jobs, histórico, prints |
| `app/web/trafego.py` | Campanhas, ROI, Pixel/CAPI, Ads e jobs de tráfego |
| `app/web/metas.py` · `app/web/equipe.py` | Metas · equipe e acesso |
| `app/financeiro_calc.py` | Cálculos financeiros compartilhados |
| `app/loja/financeiro.py` + `app/web/loja_financeiro.py` | Módulo Financeiro: DRE do mês, ponto de equilíbrio, despesas fixas |
| `app/clients/` | Clientes HTTP (Chatbot, Motor, Estoque, Revy) |

Mapa de rotas (F0, incompleto para o Copiloto): [`docs/revy-loja-route-map.md`](docs/revy-loja-route-map.md).
Cutover/rollback do shell: [`docs/revy-loja-cutover.md`](docs/revy-loja-cutover.md).
Env do Copiloto: [`docs/copiloto-env.md`](docs/copiloto-env.md).
Validação manual do LLM: [`docs/copiloto-validacao.md`](docs/copiloto-validacao.md).

## O que já funciona

Login/logout/sessão com CSRF · shell Vendas·Estoque·Ajustes·Conta · **Atendimento** (lista
unificada de leads+conversas, chat, envio de texto humano via Chatbot→Evolution, handoff,
polling `after_id`, multi-canal) · **Perfil** com troca de senha · veículos (listar,
filtrar, cadastrar, editar, publicar, despublicar, reservar, vender) · custo oculto para
vendedor · vendas, metas e resultados de mídia · **Grupo do estoque** e **números de
WhatsApp** (QR efêmero, sem expor a API key da Evolution) · **Integrações** (status
read-only Meta/Google/WA) · **Conectar o WhatsApp pela nuvem** (embedded signup da
Meta, Modo 2 — a tela abre para dono e gerente, o botão é só do dono) · **Acessos bancos** (credenciais do Motor cifradas; exige
`MOTOR_ENCRYPTION_KEY` no Motor) · **Copiloto de Vendas** (F1–F4: chat, 7 sinais, FIPE,
ações com confirmação/desfazer, sino — flag + módulo OFF por default) · **editar e
apagar venda** com o efeito propagado ao Control · **Financeiro** (lucro por moto,
lucro operacional do mês, ponto de equilíbrio e despesas fixas recorrentes — flag +
módulo OFF por default) · **Configuração do agente por loja** (formulário, rascunho com
autosave, conversa de teste com o rascunho, publicar e histórico — no ar desde 29/08;
falta só o workflow do n8n). Foto de veículo ainda é URL. Sino geral fora do Copiloto ainda não
existe. A página Hoje do Copiloto foi removida em 16/08: o sino cobre os sinais.

## Flags (defaults de código OFF)

Com tudo desligado a UI legada permanece idêntica. Em prod `app2037` o piloto liga shell,
entitlements, atendimento e WhatsApp por secrets; redirect legado segue off.

| Variável | Efeito com `1` |
|---|---|
| `REVY_LOJA_SHELL_ENABLED` | Brand/nav Vendas·Estoque (`0` = menu legado) |
| `REVY_LOJA_ENTITLEMENTS_ENABLED` | 403 se módulo não contratado/ativo (`0` = fail-open) |
| `REVY_LOJA_ATENDIMENTO_ENABLED` | Workspace `/app/loja/atendimento` (+ chat/envio/poll) |
| `REVY_LOJA_WHATSAPP_ENABLED` | Tela de números de WhatsApp em Ajustes |
| `REVY_LOJA_REDIRECT_LEGACY` | 303 de paths legados → shell (exige shell on) |
| `REVY_LOJA_COPILOTO_ENABLED` | Seção e rotas `/app/loja/copiloto` (exige shell + módulo) |
| `REVY_LOJA_FINANCEIRO_ENABLED` | Seção e rotas `/app/loja/financeiro` (exige shell + módulo) |
| `REVY_LOJA_AGENTE_CONFIG_ENABLED` | Tela `/app/loja/agente/configuracao` (sem gate de módulo) |
| `SELLER_AI_ENABLED` | Seller AI (F7+); ainda não altera rotas |

Integração com o Revy Control: `REVY_TRAFEGO_URL`, `REVY_TRAFEGO_SERVICE_TOKEN`,
`PORTAL_REVY_TRAFEGO_RESULTADOS` (cards de ROI via API),
`PORTAL_REVY_TRAFEGO_VENDA_EVENTS` (notifica venda-confirmada),
`PORTAL_REVY_TRAFEGO_RETRY_INTERVAL_SECONDS` (60), `PORTAL_TRAFEGO_UI_LEGACY` (rollback),
`PORTAL_ENCRYPTION_KEY` (Fernet do outbox e demais segredos locais).

Embedded signup: `PORTAL_META_APP_ID` e `PORTAL_META_CONFIG_ID`. **Nenhum dos dois é
segredo** — os dois vão para o HTML da tela, então moram no `[env]` do `fly.app.toml` e
nunca em `fly secrets`. O segredo do embedded signup é o App Secret, e ele fica só no
`chatbot-api`, que é quem troca o `code` por token.

Config técnica de Pixel/CAPI/campanhas **não fica aqui** — é operada no `revy-trafego`.

## Configuração do agente (`/app/loja/agente/configuracao`)

O lojista escreve **campos**, não prompt. A Loja aqui é **só tela**: os campos, o texto
gerado, o núcleo Revy, as versões e o histórico moram no `chatbot-api` e chegam pelo
`ChatbotClient`. Nenhuma tabela nova, nenhuma montagem de texto neste produto.

**Conferido em produção em 29/08:** `REVY_LOJA_AGENTE_CONFIG_ENABLED` e
`CHATBOT_AGENTE_PREVIEW_URL` aparecem como `Deployed` no `fly secrets list` do `app2037`,
e o banco tem a `agente_config` da loja piloto. **Falta publicar o workflow do n8n** — que
é o passo que muda o que o cliente ouve, e o único ainda pendente. Sequência completa e
ordem no `chatbot-api/README.md`, seção "O que falta".

**Feito:** rota da tela + três rotas de escrita (`configuracao.json` para o autosave,
`publicar`, `restaurar`), a conversa de teste (`testar.json`), o formulário inteiro
(identidade, personalidade, FAQ, regras da conversa, instruções livres, liga/desliga),
o resumo "o que o Revy garante", o prompt montado à vista, e o histórico de versões.
Arquivos: `app/loja/routes.py`, `app/templates/loja/agente_configuracao.html`,
`app/static/js/agente_configuracao.js`, estilos `.agente-config-*`/`.agente-teste-*` no
`app.css`.

- **Gate: sessão + flag + papel dono/gerente. São três, não quatro** — a tela vizinha
  (`/app/loja/agente`) não tem gate de módulo, e a configuração segue o gate da tela onde
  ela mora. Módulo próprio exigiria recriar o CHECK de `modulos_revy` numa migration.
- **Rota irmã, não aba.** Não existe componente de abas no `app.css`; inventar um é
  decisão de design. O padrão da casa é rota própria + link recíproco no
  `.heading-actions`.
- **O formulário é consciente do modo da loja.** No Modo 2 não existe tool de foto (campo
  desabilitado, com a razão à vista) e existe follow-up (interruptor aparece). No Modo 1 é
  o contrário. O modo vem do `chatbot-api`, em `GET /v1/agente/rascunho` — a Loja não
  reimplementa o gate.
- **O aviso de conflito avisa, não bloqueia.** `422` é campo inválido; conflito com o
  núcleo é texto amarelo e o lojista salva assim mesmo.
- **`422` precisa chegar como `422`.** O `raise_for_status` do `ChatbotClient`
  transformava o `422` em `ChatbotIndisponivel`, e a tela dizia "não foi possível salvar
  agora" para um erro de digitação — culpando a conexão, sem dizer qual campo. Hoje há
  `CamposAgenteInvalidos`, e a mensagem nomeia o campo.
- **Restaurar sobrescreve o rascunho aberto.** A confirmação é da tela: o chatbot faz em
  silêncio.
- **A tela não se verifica com pytest.** Formulário e autosave são JS. Verificação é no
  navegador, com portal local semeado — foi assim que o `422`→`502` apareceu, com um
  horário sem zero à esquerda.
- **A conversa de teste vive só no navegador.** O histórico é uma lista em JS; nada
  entra em Conversas, vira lead ou avisa a equipe — as ferramentas rodam em modo seco
  no workflow de preview. O botão só aparece quando o chatbot diz
  `preview_disponivel: true`; sem workflow importado, oferecer um teste que sempre
  falha ensinaria o lojista a desconfiar do produto inteiro.
- **A tela nunca manda telefone para o teste.** Quem o escolhe é o chatbot, e é
  sintético: `consultar_estoque` guarda a moto escolhida chaveada por telefone, e o
  lojista testaria com o próprio número.
- **Clicar em Testar publica o rascunho pendente antes.** Sem isso ele digita uma
  regra, clica e conversa com a versão anterior do próprio agente.
- **Expressões e "nunca diga" são chips** (spec §4.2), e a fonte da verdade é o **DOM da
  lista** — não um input escondido em paralelo. Input escondido seria um segundo estado
  para manter em sincronia, e é assim que uma remoção deixa de chegar ao backend sem
  ninguém ver. Os chips são renderizados no servidor para não piscarem vazios antes do JS.
  Enter e vírgula adicionam, colar `a, b, c` vira três, duplicata (ignorando maiúsculas)
  não entra, Backspace no campo vazio apaga o último, e sair do campo com texto digitado
  não perde o termo.
- **O JS tem um teste de sintaxe** (`tests/test_js_sintaxe.py` roda `node --check` em
  `app/static/js/*.js`, e pula sem node). Ele não substitui olhar no navegador: existe
  porque um `\n` que virou quebra de linha de verdade derrubou o arquivo inteiro, e o
  sintoma na tela foi "nada acontece ao digitar" — que não parece erro de sintaxe.
- **Mexeu no `app.css`? são cinco arquivos de `?v=`, não um.** O `base.html` e as quatro
  telas de auth (`login`, `senha_esqueci`, `senha_redefinir`, `convite_aceitar`), que não
  estendem o base. `python .claude/skills/revy-deploy/preflight.py` reprova a divergência
  — e reprovou esta feature quando só o `base.html` foi bumpado.

## Conectar o WhatsApp pela nuvem (`/app/loja/whatsapp/conectar`)

Embedded signup da Meta: o lojista abre a janela da Meta sem sair da Loja e o número
passa a ser Cloud API (Modo 2). A Loja aqui é **tela e repasse**: o `GET` monta a
decisão, o `POST` da mesma rota recebe o que o popup devolveu e entrega ao `chatbot-api`.
Quem troca o `code` por token é o chatbot, porque a troca exige o App Secret — e ele não
ganha segunda cópia neste produto. Card:
[`../docs/referencia-viva/planos/2026-08-29-embedded-signup-4-tela-na-loja.md`](../docs/referencia-viva/planos/2026-08-29-embedded-signup-4-tela-na-loja.md).

- **Gerente vê a tela, só o dono conecta.** Decisão do dono (29/08): quem clica precisa
  ser admin do portfólio empresarial na Meta, e gerente normalmente não é. O gerente
  precisa responder por que o WhatsApp não está no ar, então a tela abre para ele. O gate
  do POST é `_e_dono` explícito — o `_guarda`, que todas as escritas usam, aceita
  `ROLES_GESTAO` e deixaria o gerente passar.
- **A escolha da tela é o aceite, e é a única coisa irreversível do fluxo.** Migrar o
  número que a loja já anuncia deixa o histórico daquele celular para trás e tira o
  número do aparelho. Não existe um "li e concordo" depois; continuar já é a escolha. A
  tela também lista o que precisa estar em mãos antes (ser admin do portfólio, cartão, o
  chip do número): descobrir isso dentro da janela da Meta obriga a recomeçar do zero.
- **O botão acende sozinho.** `portal_meta_app_id()` e `portal_meta_config_id()`
  (`app/config.py`) são lidos em **runtime**, não do `Settings`, que é snapshot de boot —
  assim o botão liga no dia em que as variáveis existirem, sem redeploy. Com qualquer um
  vazio ele fica `disabled` e a tela diz que a janela está em liberação com a Meta; com
  um só, o popup abriria e a Meta recusaria sem dizer por quê.
- **O JS do popup nunca foi verificado em navegador.** Pytest não abre a janela da Meta e
  `node --check` só olha sintaxe. Quem mexer no `<script>` do `whatsapp_decidir.html`
  confere no navegador antes de dizer que funciona.
- **Canal Cloud não oferece botão de QR.** `pode_conectar` e `pode_desconectar` são
  `False` em canal Cloud (reconhecido pelo `waba_id`) porque o botão do Modo 1 chama a
  Evolution pedindo QR para um número que é da Cloud API. `ROTULOS` traduz os quatro
  estados `cloud_*` para frase de dono de loja, e a view diz qual passo do onboarding
  parou e de quem é a vez — sem oferecer "tentar de novo" quando o erro é o teto de 72 h
  da Meta, que é um clique já se sabendo recusado.
- **`montar_canais_view` reconstrói `CanalView` com `dataclasses.replace`, de propósito.**
  É no bloco do `principal_estoque`. Com reconstrução campo a campo, esquecer um campo
  novo passa por todos os testes e o defeito só aparece em loja com mais de um canal —
  foi assim que o `cloud` sumiu uma vez. Não volte a construir à mão.
- **Campo novo no chatbot não chega sozinho ao read-model.** O que `whatsapp_canais.py`
  lê é um dicionário montado campo a campo em `chatbot-api/app/channels.py`. Ler um campo
  que não está listado lá dá feature verde no CI e inerte em produção — já custou isso.
  Abra o serializer e confirme antes.

## Usar o chat no Atendimento

1. Login com shell + atendimento ligados → **Vendas → Atendimento**.
2. Clique no nome do contato ou em **Abrir conversa**.
3. Opcional: **Assumir atendimento** (pausa o bot). Enviar texto também pausa.
4. **Enter** envia, Shift+Enter quebra linha. Mensagens novas entram por poll (~4s).
5. Canal desconectado: histórico visível, envio bloqueado — reconecte em Ajustes →
   Números de WhatsApp.

## Rodar e testar

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m alembic upgrade head   # head: confira com `alembic heads`
```

Docker:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose exec portal python -m app.cli criar-dono --email dono@loja.com --nome "Dono da loja" --senha "troque-esta-senha" --loja-slug minha-loja
```

Abre em `http://localhost:9000`. Para o estoque real aparecer, preencha `ESTOQUE_API_TOKEN`
no `.env`.

---

Histórico (painel de aquisição 08/08, triagem de UX 08/07, piloto de flags):
[`../docs/nao-plano/historico/revy-loja.md`](../docs/nao-plano/historico/revy-loja.md).
