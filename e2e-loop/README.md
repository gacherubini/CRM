# e2e-loop — harness do loop WhatsApp loja teste (18/09/2026)

Cópia de `/tmp/revy_e2e/` na branch `handoff/e2e-18-09`, **sem** `.token*`,
`import.env`, `logs/` e `n8nq*.log`. Handoff completo em
`docs/referencia-viva/handoff-2026-09-18-e2e-whatsapp.md`.

## Arquivos

| Arquivo | Papel |
|---|---|
| `run.sh` | loop: roda cenários em ordem, para no 1º vermelho |
| `cenarios.sh` | T1–T11 (T8 Modo 2: oferta + log; T3/T4 pausados) |
| `lib.sh` / `api.sh` | envio via ponte, espera, asserts, chamadas API |
| `config.sh` | chip, dígitos sem-9, pnid, timeouts |
| `reset.sh` / `reset.sql` | zera loja teste **preservando inbound do vendedor** |
| `dbq.sh` | SELECT readonly no banco via console app2037 |
| `provisionar.sh` | cria credencial de loja → `.token` (rodar 1 vez) |
| `fila-dono.sh` | poe o numero do dono na fila de rodizio, ordem 0 (stdin do `fly ssh console`) |
| `esperar-webhook.sh` | espera n8n voltar após restart |
| `audios/` | fixtures (foto + ogg; áudio pausado por ora) |

## Retomar

```bash
cp -r e2e-loop /tmp/revy_e2e && cd /tmp/revy_e2e
./provisionar.sh   # 1 vez (precisa fly auth login da conta Revy)
fly apps restart n8n2037 && ./esperar-webhook.sh
CHIP=+5519996631046 SEED_OK=1 ./run.sh
```
