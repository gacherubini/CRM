# Revy — plataforma comercial para revendas de veículos

Monorepo de sete produtos independentes, ligados **só por HTTP**. O bot de WhatsApp
conversa com o cliente, coleta os dados, solicita a simulação internamente e transfere o
atendimento para um vendedor. **Parcelas, taxas e bancos nunca são enviados ao cliente
pelo bot** — ficam na Revy Loja, com o vendedor.

**Agentes: comece por [`CLAUDE.md`](CLAUDE.md)** (mapa dos produtos, onde editar, comandos)
e [`docs/contexto-compacto.md`](docs/contexto-compacto.md) (estado atual e prioridades).

## Fluxo entre produtos

```
Cliente (WhatsApp) ──▶ Evolution ──▶ n8n (Gemini) ──▶ Chatbot API ──▶ Motor / Estoque
                                                          │
Catálogo público ──▶ Estoque API ◀────────────────────────┘
                          │
                     Revy Loja (portal-gestao) ──outbox HTTP──▶ Revy Control (revy-trafego)
                     CRM, vendas, atendimento              Pixel/CAPI, Ads, campanhas, ROI
```

| Produto | Pasta | Papel |
|---|---|---|
| Chatbot API | `chatbot-api/` | Leads, conversas, handoff, roteamento WA, tools do n8n |
| Motor | `motor-simulacao/` | `/v1/simulacoes`: mock + Playwright (Santander, Fontecred, Bradesco, Pan) |
| Estoque API | `estoque-api/` | Fonte única de veículos, fotos, publicação, idempotência |
| Revy Loja | `portal-gestao/` | CRM, vendas, metas, Atendimento/chat, resultados de mídia |
| Revy Control | `revy-trafego/` | Multi-loja: Pixel/CAPI, Ads, campanhas, gastos, ROI, prontidão |
| Catálogo público | `catalogo-publico/` | Vitrine read-only dos publicados; CTA/UTM/Pixel |
| Site | `site/` | Landing de marketing |

`n8n/` guarda os workflows (não é biblioteca Python). Canônico:
`n8n/workflow-ai-nao-salvos.json`.

## Regras que valem para o repositório inteiro

- **Sem import Python entre produtos.** Integre por contrato HTTP/evento versionado.
- **Estoque API é a única fonte de veículos**; Chatbot é a única fonte de
  conversas/mensagens (a Loja autoriza e exibe).
- **Cada produto tem banco e migrations próprios.** Nunca leia a tabela de outro produto.
- **Nunca versionar** `workflow-fly.ready.json`, `.secrets.local`, `.env*` reais, tokens
  ou credenciais. O token CAPI nunca vai ao front nem ao git.
- O contrato `/v1/simulacoes` não muda entre motor mock e motor real.
- Antes de propor mudança de interface no Control ou na Loja, leia
  [a triagem de UX](docs/2026-08-07-triagem-revisao-ux-loja-control.md): **13 itens foram
  recusados pelo dono** e não devem voltar como proposta nova.

## Rodar

**Tudo local, um comando** (Docker; cria segredos só nesta máquina):

```bash
./local.sh up
```

Operação e componentes: [`deploy/local/README.md`](deploy/local/README.md).

**Testes** — sempre a partir da pasta do produto, senão importa o pacote `app` errado:

```powershell
cd portal-gestao
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m alembic upgrade head
```

**Lab Fly** (3-VM consolidado, da raiz do repositório):

```bash
bash deploy/fly/up-all.sh --3vm
bash deploy/fly/down-all.sh --3vm --yes
```

Inventário, secrets e deploy: [`deploy/fly/3vm/README.md`](deploy/fly/3vm/README.md).

## Quem o bot atende (roteamento)

A decisão fica no Chatbot (`POST /v1/operacao/roteamento`), não só no n8n. Sinal de
"contato novo" = `isSaved === false` na Evolution.

| Caso | Quem | Ação |
|---|---|---|
| Contato que já fala | salvo na agenda, não é equipe | **ignora** — sem bot de vendas |
| Contato **novo** | não salvo, não é equipe | **IA** (único caso de bot de vendas) |
| Grupo do estoque | mensagem no grupo escolhido no Portal | menu de estoque: cadastrar, consultar, editar, fotos |
| Privado ou outro grupo | imagem fora do grupo escolhido | **ignora** silenciosamente |

Sem sinal claro de contato novo → **fail-closed (ignora)**. Qualquer participante do grupo
escolhido pode operar o estoque.

## LGPD

Consentimento é registrado quando informado, sem virar barreira antes do lead. Coleta
mínima. CPF criptografado; logins de portal bancário fora do código (env/cofre). Exclusão
só por processo administrativo autorizado — o cliente não tem autosserviço.

## Documentação

| Onde | O quê |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Mapa para agentes: produtos, onde editar, comandos |
| [`docs/contexto-compacto.md`](docs/contexto-compacto.md) | **Estado atual** + prioridades (leia primeiro) |
| [`docs/handoff-contexto.md`](docs/handoff-contexto.md) | Checkpoint operacional |
| [`docs/plans/README.md`](docs/plans/README.md) | Índice dos planos válidos (ignore `_archive/`) |
| [`docs/design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md`](docs/design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md) | As-built Control/Loja |
| [`docs/2026-08-07-triagem-revisao-ux-loja-control.md`](docs/2026-08-07-triagem-revisao-ux-loja-control.md) | UX aceita **e recusada** |
| [`docs/README-COMERCIAL.md`](docs/README-COMERCIAL.md) | Visão comercial e vocabulário |
| [`docs/tutorial-dono.md`](docs/tutorial-dono.md) · [`docs/tutorial-vendedor.md`](docs/tutorial-vendedor.md) | Manuais de operação |
| [`docs/historico/`](docs/historico/) | Incidentes, decisões antigas, roadmap concluído |
