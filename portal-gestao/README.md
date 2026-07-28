# Portal de Gestão

Frontend operacional da loja, servido por FastAPI com páginas Jinja. O token das APIs fica somente no servidor; o navegador recebe uma sessão assinada.

## O que já funciona

- login, logout, sessão e proteção CSRF;
- papéis `dono`, `gerente`, `vendedor` e `admin_plataforma`;
- visão geral do estoque;
- listagem e filtros;
- cadastro e edição de veículos;
- publicar, despublicar, reservar e vender;
- custo oculto para vendedor;
- layout responsivo para computador e celular;
- **Resultados de tráfego** (dono/gerente): gasto/leads/ROAS na visão geral — config técnica (Pixel/CAPI/campanhas) migrou para o app **`revy-trafego`** (equipe Revy);
- Purchase CAPI ao confirmar venda (worker no portal até cutover; ver plano 6.4);
- **Números de cadastro** (autorizados): telefones da equipe que podem cadastrar veículo
  pelo WhatsApp (`cadastro` / fotos / `fim`) — BFF para a Chatbot API
  `/v1/operacao/numeros-autorizados`;
- **Acessos bancos** (credenciais do Motor cifradas; exige `MOTOR_ENCRYPTION_KEY` no Motor).

### Tráfego / Meta (E10 + Revy Tráfego)

Config técnica (Pixel, CAPI, campanhas, spend) é operada no app **`revy-trafego`**.  
Runbook completo: [`docs/plans/2026-07-28-plano-revy-trafego-separacao.md`](../docs/plans/2026-07-28-plano-revy-trafego-separacao.md).

| Variável | Onde | Notas |
|---|---|---|
| `PORTAL_ENCRYPTION_KEY` | Portal (+ Revy Tráfego) | Fernet; **mesma** chave nos dois se shared DB. |
| `PORTAL_TRAFEGO_UI_LEGACY` | Portal | `1` = devolve menus técnicos ao dono (rollback). Default: off. |
| `REVY_TRAFEGO_URL` | Portal | Base do app tráfego (cutover API). |
| `REVY_TRAFEGO_SERVICE_TOKEN` | Portal | Mesmo token do Revy Tráfego. |
| `PORTAL_REVY_TRAFEGO_RESULTADOS` | Portal | `1` = cards ROI via API (default código `0`; **lab Fly = 1**). |
| `PORTAL_REVY_TRAFEGO_VENDA_EVENTS` | Portal | `1` = notifica venda-confirmada (default código `0`; **lab Fly = 1**). |
| `PORTAL_PUBLIC_URL` | Catálogo | Pixel por loja (fallback). |
| `REVY_TRAFEGO_PUBLIC_URL` | Catálogo | Prioridade sobre `PORTAL_PUBLIC_URL` (**lab = loopback :9010**). |
| `META_PIXEL_ID` | Catálogo | Fallback se API offline. |
| `META_PIXEL_ENABLED` | Catálogo | `1`/`0` (default: ligado quando há Pixel). |

O token CAPI **nunca** vai ao front do catálogo nem ao git.

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
