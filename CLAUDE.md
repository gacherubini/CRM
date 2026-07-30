# Guia rapido do repositorio

Use este arquivo como mapa antes de abrir codigo grande. O estado atual do produto fica em
`docs/contexto-compacto.md`; o checkpoint operacional, em `docs/handoff-contexto.md`; e os
planos validos, em `docs/plans/README.md`. Ignore `docs/plans/_archive/` e nao implemente a
partir de `docs/design.md`.

## Como explorar com poucos tokens

1. Identifique primeiro o produto afetado na tabela abaixo.
2. Use `rg -n` para localizar rota, classe, mensagem de erro ou variavel de ambiente.
3. Leia somente o modulo do dominio. No Portal, nao abra `app/main.py` inteiro: ele faz o
   bootstrap e ainda contem rotas legadas, enquanto os dominios maiores ficam em `app/web/`.
4. Para falhas entre produtos, siga o contrato HTTP e as configs de deploy; o grafo Python nao
   representa n8n, Fly, migrations nem chamadas HTTP entre servicos.
5. Para RPA bancario, comece pelos logs e pelos documentos `docs/plans/*playwright*` do banco.

## Mapa dos produtos

| Produto | Pasta / entrada | Responsabilidade e integracoes |
|---|---|---|
| Chatbot API | `chatbot-api/app/main.py`; dominio em `app/servico.py` | Leads, conversas, handoff, roteamento WhatsApp e tools do n8n. Chama Motor e Estoque por HTTP. |
| Motor | `motor-simulacao/app/main.py` | Contrato `/v1/simulacoes`, mock, fan-out e Playwright de Santander, Fontecred, Bradesco e Pan. Credenciais bancarias ficam aqui. |
| Estoque API | `estoque-api/app/main.py` | Fonte unica de verdade de veiculos, fotos, publicacao e idempotencia. Alimenta bot, Portal e Catalogo. |
| Portal de Gestao | `portal-gestao/app/main.py`; routers em `app/web/` | CRM, vendas, metas, equipe, simulacoes e resultados. Consome Chatbot, Motor e Estoque; publica vendas ao Revy Trafego por outbox HTTP. |
| Revy Trafego | `revy-trafego/app/main.py` | Banco proprio de midia, projecao de vendas, Pixel/CAPI, campanhas, gastos e ROI. |
| Catalogo publico | `catalogo-publico/app/main.py` | Vitrine read-only dos veiculos publicados; CTA/UTM/Pixel. Consulta Estoque e configuracao publica do Portal. |
| Site | `site/` | Landing estatica e assets de marketing. |

`n8n/` nao e biblioteca Python: contem os workflows que orquestram Evolution, Gemini e as APIs.
O workflow canonico e `n8n/workflow-ai-nao-salvos.json`. Nunca versionar
`workflow-fly.ready.json`, `.secrets.local`, `.env*` reais, tokens ou credenciais.

## Fluxos que atravessam servicos

- WhatsApp: Evolution -> n8n -> Chatbot -> Motor/Estoque; respostas financeiras ficam no Portal.
- Veiculos: Estoque -> Chatbot, Portal e Catalogo. Nao duplique veiculos em outro produto.
- Vendas/midia: Portal -> outbox transacional HTTP -> Revy Trafego -> Meta CAPI/Ads.
- Configuracao bancaria: Portal e BFF; segredo cifrado e execucao pertencem ao Motor.
- Cada produto tem banco/migrations proprios. Nao crie import Python entre produtos; integre por
  contrato HTTP/evento versionado.

## Portal: onde editar

- Bootstrap, middleware, auth e rotas legadas restantes: `portal-gestao/app/main.py`.
- Simulacao manual, jobs, historico e prints: `portal-gestao/app/web/simulacoes.py`.
- Metas: `portal-gestao/app/web/metas.py`.
- Equipe e acesso: `portal-gestao/app/web/equipe.py`.
- Campanhas, ROI, Pixel/CAPI, Ads e jobs de trafego: `portal-gestao/app/web/trafego.py`.
- Shell Revy Loja: `portal-gestao/app/loja/` e `portal-gestao/app/web/loja_*.py`.
- Calculos financeiros compartilhados: `portal-gestao/app/financeiro_calc.py`.
- Clientes HTTP: `portal-gestao/app/clients/`.

## Comandos usuais

Execute testes a partir da pasta do produto para nao importar o pacote `app` errado:

```powershell
cd portal-gestao
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Nos outros produtos, use o mesmo padrao (`python -m pytest -q`; venv local quando existir).
Smokes minimos por eixo estao em `docs/contexto-compacto.md`, secao "Verificacao minima".

Portal local completo:

```powershell
cd portal-gestao
docker compose up --build -d
```

Lab Fly consolidado, sempre a partir da raiz do repositorio:

```bash
bash deploy/fly/up-all.sh --3vm
bash deploy/fly/down-all.sh --3vm --yes
fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false
fly deploy . -a motor2037 -c deploy/fly/3vm/fly.worker.toml --ha=false
```

Inventario atual: `suite-pg`, `evolution2037`, `app2037` e `n8n2037` ficam always-on quando o
lab esta ativo; `motor2037` e worker Playwright sob demanda. Nao recrie apps monoliticos antigos,
nao destrua volumes e nao rode deploy sem conferir `deploy/fly/3vm/README.md`.

## Validacao antes de concluir

- Rode os testes do produto alterado e os consumidores diretos do contrato.
- Em migrations, confira `upgrade head` e a migration head do produto correto.
- Em n8n, rode `python n8n/validate_workflow.py` a partir da raiz.
- Em mudancas Fly/RPA, registre evidencia de health, job/eventos e logs sem imprimir segredos.
- Finalize com `git diff --check` e `git status --short`; preserve mudancas alheias no worktree.
