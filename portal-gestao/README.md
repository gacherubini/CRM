# Revy Loja (diretório `portal-gestao`)

Frontend operacional da loja, servido por FastAPI com páginas Jinja. O diretório
mantém o nome histórico `portal-gestao`; a UI nova usa a marca **Revy Loja**. Tokens
das APIs ficam somente no servidor e o navegador recebe uma sessão assinada.

## O que já funciona

- login, logout, sessão e proteção CSRF;
- papéis `dono`, `gerente`, `vendedor` e `admin_plataforma`;
- **Shell Revy Loja** (flag): nav Vendas / Estoque / Ajustes / Conta;
- **Atendimento** (flag): lista unificada de leads+conversas; workspace de chat com
  bolhas; envio de texto humano (Chatbot → Evolution); handoff assumir/devolver;
  polling de mensagens novas (`after_id`); multi-canal (resposta pelo canal da conversa);
- **Perfil** (`/app/loja/perfil`): dados da conta + troca de senha (avatar no topbar;
  `/conta/senha` redireciona para o Perfil);
- visão geral de Vendas e de Estoque;
- listagem e filtros de veículos; cadastro e edição; publicar, despublicar, reservar e vender;
- custo oculto para vendedor;
- layout responsivo para computador e celular;
- **Resultados de tráfego** (dono/gerente): gasto/leads/ROAS na visão geral — config técnica (Pixel/CAPI/campanhas) migrou para o app **`revy-trafego`** (equipe Revy);
- confirmação/cancelamento de venda publicados no Revy por outbox transacional criptografado;
  o Portal não chama a Meta nem o Revy dentro da requisição;
- **Grupo do estoque** (Ajustes no shell): `/app/operacao/numeros` — escolher grupo WA
  de fotos/cadastro + números autorizados (aviso de simulação/handoff). BFF
  `/v1/operacao/numeros-autorizados`. Fluxo WA: `cadastro` / fotos / `fim` no grupo;
- **Números de WhatsApp da loja** (flag): Ajustes → `/app/loja/whatsapp` — QR efêmero,
  reconectar/desconectar sem expor a API key da Evolution;
- **Integrações** (status read-only Meta/Google/WA): `/app/loja/integracoes`;
- **Acessos bancos** (credenciais do Motor cifradas; exige `MOTOR_ENCRYPTION_KEY` no Motor).

### Aquisição 2026-08-08 — "Por onde as pessoas chegam"

A seção **"De onde veio o resultado"** (`/app/loja/vendas`) passou a ter dois blocos. A
tabela de campanhas responde *quanto cada campanha custou e rendeu*; o bloco novo responde
*por onde as pessoas entraram* — Anúncio, Link direto, Procurou no WhatsApp.

- **Guard próprio, e é o ponto da mudança.** A tabela de campanhas depende da API do Revy
  responder. O bloco novo tem como fonte o lead do Chatbot, então **continua renderizando
  com a fonte de mídia offline** — que é justamente quando o lojista mais quer saber por
  onde entrou gente. A `<section>` abre se **qualquer um** dos dois tiver conteúdo.
- **Agrupa por `ctwa_source_type`, não por `origem`.** `origem` está errada em 10 leads
  antigos e não será corrigida retroativamente; `source_type` é o dado cru da Meta e está
  certo. O painel nasce correto sem tocar em uma linha do banco.
- Comparação em `casefold`: o valor real em produção é `FB_Ads`, com maiúsculas.
- Dentro de "Anúncio", uma nota conta quantos leads estão **sem identificação de
  campanha**. É o que explica, na própria tela, por que a soma das campanhas não bate com
  o total de "Anúncio" — sem esse número o lojista vê a diferença e não descobre a causa.
- Lead sem `criada_em` fica **fora** do total: virar "Não identificado" incharia o balde
  com lead antigo e faria o percentual mentir.
- Permanece atrás de `pode_ver_aquisicao` (dono/gerente). Custo de integração zero: nenhum
  campo, endpoint ou contrato novo.

O mapa de rótulos em `app/loja/sales_overview.py` é **duplicação consciente** com
`FAMILIA_ANUNCIO` em `chatbot-api/app/servico.py` — produtos diferentes, sem import entre
eles. Mudou lá, muda aqui.

Sobre a venda que aparece na linha da campanha: quem decide isso é o Revy
(`revy-trafego/README.md` → "Atribuição de venda no ROI"). Vale lembrar que essa linha é o
**seu relatório**, e não a atribuição da Meta — a compra só chega ao Gerenciador de
Anúncios pelo Purchase CAPI, que depende de `ctwa_clid` no lead. Os dois números podem
divergir legitimamente.

### Triagem de UX 2026-08-07 (o que mudou na interface)

Decisões e itens **recusados** em
[`../docs/2026-08-07-triagem-revisao-ux-loja-control.md`](../docs/2026-08-07-triagem-revisao-ux-loja-control.md).
Consulte antes de propor mudanças nessas telas — parte do que "parece faltando" foi
recusado de propósito.

| Tela | Mudança |
|---|---|
| Vendas › **Resultado** (era "Visão geral") | Rodapé "Atalhos" para telas legadas removido; bloco "Pendências" só aparece quando há pendência; números do funil abrem `/app/loja/atendimento` filtrado. |
| Vendas › **Atendimento** | Coluna **"Aguardando há"** (helper `tempo_relativo()` em `app/main.py`, sobre `atualizada_em`); badge de canal migrou do `<style>` inline para `app.css` com tokens — no tema claro ele era branco sobre branco. |
| Vendas › **Agente** | Redesenhada: barra dividida "só com o agente" × "transferidos", série diária preenchida do dia 1 até hoje (`montar_visao_agente` em `app/loja/routes.py` — o Chatbot só devolve dias com conversa). Ícone próprio no menu. |
| Estoque › **Situação do estoque** (era "Visão geral") | Painéis "Cadastro › Pendências" e "Reservas e vendas recentes" removidos; texto sem jargão de API/shell. |
| Estoque › **Vitrine** (era "Ordem na vitrine") | Passou a reunir a ordenação **e** a configuração do catálogo (WhatsApp do CTA + link), que morava em Ajustes › Números de WhatsApp. O POST `/app/loja/whatsapp/catalogo` redireciona para `/app/loja/estoque/vitrine#catalogo-wa`. |
| Topbar | Páginas do shell declaram `page_title`; sem isso o `if/elif` de `base.html` não cobre `/app/loja/*` e a topbar escreve "Ajustes". **Item novo no menu precisa de `page_title` no template e de ícone no dicionário `loja_icons` de `base.html`** — `tests/test_loja_navigation.py::test_shell_nav_todos_os_itens_tem_icone` falha se o ícone faltar. |

### Revy Loja (shell / entitlements — defaults de código OFF)

Evolução do portal para o shell operacional **Revy Loja** (Vendas + Estoque). Com flags
desligadas a UI legada permanece idêntica. Em **prod `app2037`** o piloto liga shell,
entitlements, atendimento e WhatsApp por secrets; redirect legado permanece off.
Detalhe: [`../docs/2026-08-02-provisionamento-loja-entitlements.md`](../docs/2026-08-02-provisionamento-loja-entitlements.md).
Mapa de rotas: [`docs/revy-loja-route-map.md`](docs/revy-loja-route-map.md).

| Variável | Default código | Efeito |
|---|---|---|
| `REVY_LOJA_SHELL_ENABLED` | `0` | `1` = brand/nav Vendas·Estoque; `0` = menu legado |
| `REVY_LOJA_ENTITLEMENTS_ENABLED` | `0` | `1` = 403 se módulo não contratado/ativo; `0` = fail-open |
| `REVY_LOJA_ATENDIMENTO_ENABLED` | `0` | Workspace `/app/loja/atendimento` (+ chat/envio/poll) |
| `REVY_LOJA_WHATSAPP_ENABLED` | `0` | `1` = tela de números de WhatsApp em Ajustes (`/app/loja/whatsapp`) |
| `REVY_LOJA_REDIRECT_LEGACY` | `0` | `1` = 303 de paths legados → shell (exige shell on); ver cutover |
| `SELLER_AI_ENABLED` | `0` | Seller AI (F7+); ainda não altera rotas |

Backend: `app/loja/*` (domínio) + `app/web/loja_shell.py` + `app/web/loja_perfil.py` +
`app/web/loja_whatsapp.py` + `app/loja/routes.py` (Atendimento) + `app/loja/redirects.py`.
Projeção: `app.provisioning.allows_processing` / `LojaOperacionalProjecao`.  
Cutover / rollback: [`docs/revy-loja-cutover.md`](docs/revy-loja-cutover.md).

#### Usar o chat no Atendimento

1. Login com shell + atendimento ligados.
2. **Vendas → Atendimento** (`/app/loja/atendimento`).
3. Clique no **nome do contato** ou em **Abrir conversa**.
4. Opcional: **Assumir atendimento** (pausa o bot). Enviar texto também pausa o bot no Chatbot.
5. Digite e **Enter** (Shift+Enter quebra linha). Mensagens novas do cliente entram por poll (~4s).
6. Canal **off** / desconectado: histórico visível, envio bloqueado — reconecte em Ajustes → Números de WhatsApp.

### Tráfego / Meta (E10 + Revy Tráfego)

Config técnica (Pixel, CAPI, campanhas, spend) é operada no app **`revy-trafego`**.  
Runbook completo: [`docs/plans/2026-07-28-plano-revy-trafego-separacao.md`](../docs/plans/2026-07-28-plano-revy-trafego-separacao.md).

| Variável | Onde | Notas |
|---|---|---|
| `PORTAL_ENCRYPTION_KEY` | Portal | Fernet do outbox Portal → Revy e demais segredos locais. |
| `PORTAL_TRAFEGO_UI_LEGACY` | Portal | `1` = devolve menus técnicos ao dono (rollback). Default: off. |
| `REVY_TRAFEGO_URL` | Portal | Base do app tráfego (cutover API). |
| `REVY_TRAFEGO_SERVICE_TOKEN` | Portal | Mesmo token do Revy Tráfego. |
| `PORTAL_REVY_TRAFEGO_RESULTADOS` | Portal | `1` = cards ROI via API (default código `0`; **lab Fly = 1**). |
| `PORTAL_REVY_TRAFEGO_VENDA_EVENTS` | Portal | `1` = notifica venda-confirmada (default código `0`; **lab Fly = 1**). |
| `PORTAL_REVY_TRAFEGO_RETRY_INTERVAL_SECONDS` | Portal | Intervalo do worker do outbox; default `60`. |
| `PORTAL_PUBLIC_URL` | Catálogo | Pixel por loja (fallback). |
| `REVY_TRAFEGO_PUBLIC_URL` | Catálogo | Prioridade sobre `PORTAL_PUBLIC_URL` (**lab = loopback :9010**). |
| `META_PIXEL_ID` | Catálogo | Fallback se API offline. |
| `META_PIXEL_ENABLED` | Catálogo | `1`/`0` (default: ligado quando há Pixel). |

O token CAPI **nunca** vai ao front do catálogo nem ao git.

### Banco e migrações

O Portal continua fonte da verdade de CRM/vendas. O Revy mantém uma projeção própria alimentada
por eventos; não há leitura SQL cruzada entre os produtos.

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

Head esperado pelo código: `0018_redefinicoes_senha` (cadeia … → 0015 auditoria
canal → 0016 convites → 0017 vínculo loja/pessoa → 0018 redefinições de senha).
O app não executa `create_all` no boot: falha de migração deve impedir readiness/deploy.

## Executar com Docker

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose exec portal python -m app.cli criar-dono --email dono@loja.com --nome "Dono da loja" --senha "troque-esta-senha" --loja-slug minha-loja
```

Abra `http://localhost:9000`. Para o estoque real aparecer, preencha `ESTOQUE_API_TOKEN` no `.env`.

## Testes locais

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest
```
