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
- aba **Tráfego** (dono/gerente): Pixel ID + token CAPI cifrado, Purchase ao confirmar venda;
- **Números de cadastro** (autorizados): telefones da equipe que podem cadastrar veículo
  pelo WhatsApp (`cadastro` / fotos / `fim`) — BFF para a Chatbot API
  `/v1/operacao/numeros-autorizados`;
- **Acessos bancos** (credenciais do Motor cifradas; exige `MOTOR_ENCRYPTION_KEY` no Motor).

### Tráfego / Meta (E10)

| Variável | Onde | Notas |
|---|---|---|
| `PORTAL_ENCRYPTION_KEY` | Portal | Fernet urlsafe; gera com `python -m app.cli gerar-chave-cifragem`. **Obrigatória** se `PORTAL_ENV=production`. |
| `PORTAL_PUBLIC_URL` | Catálogo público | URL do Portal; catálogo puxa Pixel ID por loja (`/public/v1/lojas/{slug}/pixel`). |
| `META_PIXEL_ID` | Catálogo | Fallback se o Portal estiver offline. |
| `META_PIXEL_ENABLED` | Catálogo | `1`/`0` (default: ligado quando há Pixel). |

O token CAPI **nunca** vai ao front do catálogo nem ao git. No Portal ele é gravado cifrado; na leitura aparece só como “Configurado” / mascarado.

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
