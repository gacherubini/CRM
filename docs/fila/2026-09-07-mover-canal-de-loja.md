# Mover canal Cloud de uma loja para outra (script administrativo)

**Produto:** chatbot-api · **Spec:** [`../referencia-viva/specs/2026-09-07-um-chip-teste-depois-loja-real-design.md`](../referencia-viva/specs/2026-09-07-um-chip-teste-depois-loja-real-design.md) §5.1

Um chip só atende as duas fases: o número entra pelo embedded signup na loja `teste`,
é exercitado ali, e depois muda de dono sem passar pelo popup de novo. O popup está
fechado para a segunda vez — `evolution_instance` é `UNIQUE` global
(`app/models_db.py:51-53`) e o elo 1 recusa número já cadastrado
(`app/onboarding_cloud.py:63-72`). Este card constrói a única porta que sobra.

## Global constraints

- **Produto:** só `chatbot-api`. Nada de Control, Loja, n8n ou migration.
- **Arquivos que pode tocar:** `chatbot-api/scripts/mover_canal_de_loja.py` (novo),
  `chatbot-api/tests/test_mover_canal_de_loja.py` (novo), e o comentário de
  `chatbot-api/app/models_db.py:48` (uma linha).
- **Sem rota HTTP.** Expor isso na API daria a qualquer loja um caminho para roubar o
  número de outra, que é o que a `UNIQUE` global existe para impedir.
- **Sem migration.** Nenhuma coluna muda.
- **Teste com engine próprio**, como `tests/test_semear_config_agente.py:59` faz. O banco
  de teste da suíte é um só e não se limpa entre testes
  (`learnings/2026-08-29-o-banco-de-teste-do-chatbot-e-um-so`). `phone_number_id` livre a
  partir de `1227059273831630`.
- **Não faça:** apagar `fila_vendedor`, tocar em `registro_tentativas`, `waba_id`,
  `token_cifrado`, `pin_cifrado` ou `template_oferta`, nem chamar a Graph. O corte é só
  de banco.

## Task 1 — o script

`scripts/mover_canal_de_loja.py`, no molde de `scripts/semear_config_agente.py`:
`main(argv) -> int`, `SessionLocal` de `app.db`, guarda de banco errado
(`DATABASE_URL` × `CHATBOT_DATABASE_URL`, ver `_banco_errado` do vizinho —
`learnings/2026-08-23-alembic-mente-sem-database-url`).

Argumentos: `--phone-number-id`, `--para-slug`, `--apagar-dados-da-origem`, `--dry-run`.

Uma transação, nesta ordem:

1. Canal por `evolution_instance == phone_number_id`. Ausente → erro, código 1.
2. Loja destino por slug. Ausente → erro listando os slugs que existem (o vizinho já faz
   assim, e foi defeito real). Presente mas sem `allows_processing`
   (`app/provisioning.py:30`) → erro: o Modo 2 seria fail-closed logo depois.
3. Origem com `OfertaLead.estado == 'aberta'` → erro. Mover no meio de um rodízio deixa a
   oferta apontando para `fila_vendedor` de outra loja.
4. `--apagar-dados-da-origem` → Task 2.
5. `canal.loja_id = destino.id`.
6. `estado` não se toca: `cloud_pendente` é liberado pelo Control depois
   (`app/provisioning.py:72`).
7. Imprime antes/depois. `--dry-run` faz tudo e dá `rollback`.

## Task 2 — a limpeza da origem

Ordem ditada pelas FKs (`mensagens → conversas` e `→ leads`; `consentimentos → leads`;
`ctwa_auditoria → leads`; `oferta_lead → fila_vendedor`), tudo por `loja_id` da origem:

```
mensagens → conversas → consentimentos → ctwa_auditoria →
catalog_attributions → oferta_lead → leads → rodizio_ponteiro
```

`fila_vendedor` **fica**: é cadastro, não tráfego, e serve o próximo teste.

Sem esta limpeza a mudança de `loja_id` não basta: `Conversa` é única por
`(canal_id, telefone)` (`app/models_db.py:192-197`) e `_get_or_create_conversa`
(`app/servico.py:665`) devolve a conversa achada **sem conferir `loja_id`**. Os telefones
do teste voltariam a escrever depois do corte e cairiam na conversa da loja errada.

## Task 3 — testes

Cada um nasce vermelho antes do código correspondente:

1. move e `cloud_canal.loja_id_do_phone_number_id` passa a devolver o destino;
2. move e `cloud_canal.canal_cloud_da_loja(destino)` acha o canal, `(origem)` devolve `None`;
3. destino sem projeção `ativa` → código de erro e **nada** mudou no banco;
4. `OfertaLead` aberta na origem → código de erro e nada mudou;
5. `--dry-run` não persiste;
6. com `--apagar-dados-da-origem`, a conversa antiga daquele `(canal_id, telefone)` some e a
   próxima `registrar_mensagem` cria conversa nova já com o `loja_id` do destino.

O 6 é o que fecha a armadilha da Task 2 — sem ele o card não está pronto.

## Como saber que acabou

```
cd chatbot-api
.\.venv\Scripts\python.exe -m pytest tests -q       # Windows
.venv/bin/python -m pytest tests -q                 # macOS
```

Suíte inteira verde, não só o arquivo novo. `git diff --check`, `git status --short`.
Mapa não regera: script novo não é rota, modelo, worker, migration nem flag.
