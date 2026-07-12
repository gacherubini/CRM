# Catálogo Público

Vitrine FastAPI/Jinja independente. Consome somente o contrato HTTP público da Estoque API e
mantém apenas seus eventos de interesse em SQLite próprio.

## Desenvolvimento

```powershell
cd catalogo-publico
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
$env:ESTOQUE_PUBLIC_API_URL="http://localhost:8100"
.\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8200
```

Abra `http://localhost:8200/l/<slug-da-loja>`. O veículo precisa estar disponível e publicado
na Estoque API.

Configurações:

- `ESTOQUE_PUBLIC_API_URL`: URL-base da Estoque API;
- `ESTOQUE_PUBLIC_API_TOKEN`: Bearer opcional, mantido apenas no servidor;
- `CATALOGO_DATABASE_PATH`: arquivo SQLite de eventos;
- `CATALOGO_PAGE_SIZE`: tamanho padrão da página;
- `CATALOGO_PUBLIC_BASE_URL`: URL pública da instalação;
- `CATALOGO_SECURE_COOKIE=1`: cookie anônimo somente por HTTPS.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
