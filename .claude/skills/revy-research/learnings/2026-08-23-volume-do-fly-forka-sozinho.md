---
gatilho: investigar custo, volume ou RAM dos apps do Fly
produto: deploy
---
# Cada migracao de host forka um volume, e keepalive piora

O Fly migra maquina de host sozinho (`migrated=true` nos eventos) e **cada migracao de
maquina-com-volume forka um volume novo**, deixando o antigo em `pending_destroy`. Em
14/07/2026 chegaram a acumular 8 volumes por app (8 GB cobrados), agravado por um
incidente de capacidade em GRU.

Duas leituras erradas para nao repetir:
- o numero de "memoria" no dashboard de apps e **armazenamento** (soma dos volumes),
  nao RAM;
- **nao usar keepalive** (`up-all.sh 60`): ficar acordando maquina suspensa **acelera
  ~10x** os forks de volume. So piora.

Para limpar: `deploy/fly/clean-orphan-volumes.sh` roda dry-run por padrao e o `--apply`
so apaga volume sem maquina anexada — nunca toca no que esta em uso.
