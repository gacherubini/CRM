# Catálogo conectado

Sobe somente o Catálogo e o conecta por HTTP a uma Estoque API existente. Portal, Chatbot e
Motor não são necessários.

1. Copie `.env.example` para `.env` e ajuste `ESTOQUE_PUBLIC_API_URL`.
2. Garanta que a loja exista e tenha veículos disponíveis publicados na Estoque API.
3. Suba o serviço:

```powershell
docker compose up -d --build
docker compose ps
```

A vitrine fica em `http://localhost:8200/l/<slug-da-loja>`. Eventos de clique ficam no volume
`catalogo_data`; preserve esse volume em backup. Para parar sem apagar eventos:

```powershell
docker compose down
```

Não use `docker compose down -v` se quiser preservar o histórico de interesses.
