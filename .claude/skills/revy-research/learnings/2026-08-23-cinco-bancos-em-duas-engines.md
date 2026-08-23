---
gatilho: procurar o banco de um produto ou cruzar dados entre produtos
produto: todos
custo: um card de plano escrito com premissa errada
---
# Sao 5 bancos em 2 engines, e Portal e Control sao SQLite

Levantado em 16/08/2026 direto da infra, nao do repo:

- `suite-pg` (postgres-flex, uma primary) tem **quatro** bancos: `chatbot`, `estoque`,
  `motor` e **`evolution`** — o WhatsApp mora la tambem.
- **Portal e Revy Control rodam SQLite**, em arquivo no volume do `app2037`:
  `/data/portal/portal.db` e `/data/revy-trafego/revy_trafego.db`. `PORTAL_DATABASE_URL`
  **nao existe** entre os secrets do app: vale o `[env]` do `fly.app.toml`. Nao adianta
  procurar em Settings.
- Os seis servicos rodam **no mesmo container** e conversam por HTTP em `127.0.0.1`.
- Ha **10 nomes de tabela duplicados** entre produtos (`lojas` em tres,
  `loja_operacional_projecao` em tres, e o bloco Meta/Ads e fork literal de schema entre
  Portal e Control). Achar a tabela nao diz de qual produto ela e.

Duas ideias que morrem nisso: "o Copiloto consulta o banco" (o Portal nao alcanca veiculo
nem lead, nem por join nem por FDW — so HTTP versionado) e qualquer plano que pressuponha
**RLS**, que nao existe em SQLite. Um card ja foi escrito com essa premissa errada sobre a
propria infra.

Snapshot diario com retencao de 5 dias nos dois volumes.
