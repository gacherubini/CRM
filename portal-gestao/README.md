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
- layout responsivo para computador e celular.

Leads e conversas já têm espaço na navegação e serão conectados no próximo incremento.

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
