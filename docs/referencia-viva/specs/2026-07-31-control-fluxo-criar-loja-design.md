# Revy Control — fluxo de criar/gerenciar loja mais intuitivo

Data: 2026-07-31 · Escopo: `revy-trafego` (Revy Control, superfície `/app/control/lojas`).

## Problema

1. **Criar loja** pede um `slug` cru, com `pattern` regex e zero explicação. O admin
   não sabe o que é slug nem o formato esperado.
2. Depois de criar, o app volta pra **lista** — o admin não é levado a configurar a
   loja (adicionar equipe, módulos, contrato).
3. O **detalhe da loja** é uma parede única de ~8 painéis empilhados; achar "adicionar
   pessoas" exige rolar por Google Ads, módulos e contrato.

## Decisões (aprovadas)

- Slug **automático + preview**: digita só o Nome; o endereço é gerado ao vivo, com
  botão "editar" pra ajuste manual opcional.
- Pós-criação: redireciona pro **detalhe reorganizado em abas**, já aberto em
  **Pessoas**, com banner de próximos passos.
- Escopo: só o fluxo de loja (Criar + Detalhe). Outras telas ficam pra depois.

## Design

Estende o design system atual (monocromático, Inter, tokens em `app.css`,
tema claro/escuro). Nenhuma identidade nova; só componentes novos coerentes.

### 1. Criar loja (`control/lojas.html` + `create_store_page`)

- Campo **Nome da loja**. Abaixo, bloco "Endereço da loja" com o slug gerado ao vivo
  (`revy.../auto-center-bh`) e botão **editar** que revela o input manual
  (pré-preenchido). Preview via JS de slugify no template.
- Mantém `id="form-criar-loja"`, `name="nome"`, `name="slug"` (contratos de teste).
- Backend: slug vira **opcional**. Helper `_slugify(nome)` no web layer (remove
  acentos, minúsculas, não-alfanumérico → hífen, colapsa). Vazio ⇒ deriva do nome;
  se o nome não gera slug válido ⇒ erro pedindo pra editar o endereço. O domínio
  (`StoreControl.create`) continua exigindo slug canônico — a derivação é na rota.
- Conflito de slug ⇒ mensagem amigável referindo "endereço".
- Sucesso ⇒ `303` para `…/lojas/{id}?created=1&tab=pessoas`.

### 2. Detalhe em abas (`control/loja_detail.html`)

- **Banner de próximos passos** (quando `created=1`), acima das abas, contendo o texto
  "Loja criada com sucesso" (mantém contrato de teste) + atalho pra Pessoas.
- Alertas de sucesso (`ok=…`) e erro ficam acima das abas (sempre visíveis).
- **Tablist ARIA** + JS vanilla (padrão do `base.html`, sem lib): abas
  **Visão geral · Pessoas · Módulos & contrato · Integrações · Estado · Auditoria**.
  - `Pessoas` e `Estado` só para admin. `Integrações` quando Google Ads habilitado.
  - Aba inicial: `?tab=` → senão derivada de `ok=` → senão `visao`.
  - JS troca `.is-active` nos painéis e atualiza o hash; deep-link por hash/param.
- **Visão geral**: cartão-resumo (nome, endereço/slug, estado, versão) + checklist de
  próximos passos derivada do estado.
- **Preserva todos os IDs/actions** existentes (`form-atribuir-cargo`,
  `tabela-cargos-loja`, `form-configurar-modulos`, `selecao-modulo-*`, `modulo-*`,
  `contrato-*`, `form-configurar-contrato`, `form-alterar-estado`,
  `form-conceder-gestor`, `form-revogar-gestor`, `google-*`, `loja-versao`). As abas
  só embrulham as seções — nada é removido; testes checam presença de string no HTML.

### 3. CSS (`app.css`)

Componentes novos, escopados: `.control-tabs`/`.control-tab`, `.control-tabpanel`,
`.slug-preview`, `.next-steps` (banner), `.overview-*`. Reaproveita tokens e evita
colisão de especificidade com `.section`/`.panel`.

## Fora de escopo

Polimento das demais telas do Control (Dashboard, lista de Lojas, Acessos).
Anotar sugestões ao final, decidir depois.

## Validação

`cd revy-trafego && .\.venv\Scripts\python.exe -m pytest -q` verde, com foco em
`test_control_admin_ui.py` e `test_control_people_roles_ui.py`.

## Passos de implementação

1. `_slugify` + slug opcional + redirect pro detalhe em `create_store_page`.
2. `active_tab`/`created` no contexto de `_render_store_detail`.
3. Redesenhar `lojas.html` (form + preview JS).
4. Reorganizar `loja_detail.html` em abas + banner + Visão geral (IDs preservados).
5. CSS dos componentes novos.
6. Rodar testes do `revy-trafego`; ajustar até verde.
