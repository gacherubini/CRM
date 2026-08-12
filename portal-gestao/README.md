# Revy Loja (diretório `portal-gestao`)

Frontend operacional da loja: FastAPI + páginas Jinja. Papéis `dono`, `gerente`,
`vendedor`, `admin_plataforma`. O diretório mantém o nome histórico `portal-gestao`; a UI
se chama **Revy Loja**.

Tokens das APIs ficam **somente no servidor**; o navegador recebe uma sessão assinada.

## Armadilhas — leia antes de mexer

- **Custo do veículo, lucro, tokens e credenciais do Motor nunca aparecem para vendedor.**
  Aplique RBAC no backend, não escondendo item de menu.
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
  [`../docs/2026-08-07-triagem-revisao-ux-loja-control.md`](../docs/2026-08-07-triagem-revisao-ux-loja-control.md):
  parte do que "parece faltando" foi **recusado pelo dono**.
- O `app.css` **não** pode reabrir `:root` para declarar token de marca: ele carrega depois
  do `revy-tokens.css` e a redeclaração anula a fonte única.
  `shared/brand/tests/test_app_css.py` falha se acontecer.

## Onde editar

| Arquivo | Responsabilidade |
|---|---|
| `app/main.py` | Bootstrap, middleware, auth, rotas legadas restantes, helpers de template |
| `app/loja/` + `app/web/loja_*.py` | Shell Revy Loja (domínio + rotas) |
| `app/loja/routes.py` | Atendimento (chat, envio, polling, visão do agente) |
| `app/loja/sales_overview.py` | Visão geral de Vendas e painel de aquisição |
| `app/web/simulacoes.py` | Simulação manual, jobs, histórico, prints |
| `app/web/trafego.py` | Campanhas, ROI, Pixel/CAPI, Ads e jobs de tráfego |
| `app/web/metas.py` · `app/web/equipe.py` | Metas · equipe e acesso |
| `app/financeiro_calc.py` | Cálculos financeiros compartilhados |
| `app/clients/` | Clientes HTTP (Chatbot, Motor, Estoque, Revy) |

Mapa completo de rotas: [`docs/revy-loja-route-map.md`](docs/revy-loja-route-map.md).
Cutover/rollback do shell: [`docs/revy-loja-cutover.md`](docs/revy-loja-cutover.md).
Variáveis de ambiente do Copiloto de Vendas: [`docs/copiloto-env.md`](docs/copiloto-env.md).

## O que já funciona

Login/logout/sessão com CSRF · shell Vendas·Estoque·Ajustes·Conta · **Atendimento** (lista
unificada de leads+conversas, chat, envio de texto humano via Chatbot→Evolution, handoff,
polling `after_id`, multi-canal) · **Perfil** com troca de senha · veículos (listar,
filtrar, cadastrar, editar, publicar, despublicar, reservar, vender) · custo oculto para
vendedor · vendas, metas e resultados de mídia · **Grupo do estoque** e **números de
WhatsApp** (QR efêmero, sem expor a API key da Evolution) · **Integrações** (status
read-only Meta/Google/WA) · **Acessos bancos** (credenciais do Motor cifradas; exige
`MOTOR_ENCRYPTION_KEY` no Motor).

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
| `SELLER_AI_ENABLED` | Seller AI (F7+); ainda não altera rotas |

Integração com o Revy Control: `REVY_TRAFEGO_URL`, `REVY_TRAFEGO_SERVICE_TOKEN`,
`PORTAL_REVY_TRAFEGO_RESULTADOS` (cards de ROI via API),
`PORTAL_REVY_TRAFEGO_VENDA_EVENTS` (notifica venda-confirmada),
`PORTAL_REVY_TRAFEGO_RETRY_INTERVAL_SECONDS` (60), `PORTAL_TRAFEGO_UI_LEGACY` (rollback),
`PORTAL_ENCRYPTION_KEY` (Fernet do outbox e demais segredos locais).

Config técnica de Pixel/CAPI/campanhas **não fica aqui** — é operada no `revy-trafego`.

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
[`../docs/historico/revy-loja.md`](../docs/historico/revy-loja.md).
