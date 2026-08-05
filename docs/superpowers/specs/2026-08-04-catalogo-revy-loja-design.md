# Catálogo público alinhado à Revy Loja

Data: 2026-08-04  
Status: aprovado para implementação

## Objetivo

1. Visual da vitrine com tokens/componentes do Revy Loja (sem sidebar).
2. WhatsApp do CTA configurável na Loja (campo livre de telefone).
3. Paginação numerada (Anterior / 1 2 3 … / Próxima + total).
4. Veículos **com foto** antes dos sem foto na listagem pública.

## Decisões

| Tema | Decisão |
|---|---|
| Número do CTA | Continua em `estoque.lojas.whatsapp`; Loja edita via API privada do Estoque |
| UI Loja | Ajustes → **Catálogo** (`/app/loja/catalogo`), dono/gerente, shell ligado |
| Ordenação | `ordem_vitrine ASC`, depois `tem_foto DESC`, depois `criado_em DESC` (manual na Loja: `/app/loja/estoque/vitrine`) |
| Total | `paginacao.total` no contrato público (além de limit/offset/quantidade) |
| Dark mode | Fora de escopo |

## Superfícies

### estoque-api

- `listar_veiculos_publicos`: contagem total + ordenação por foto.
- `GET/PATCH /v1/loja`: ler/atualizar `whatsapp` (gestão: dono/gerente).

### catalogo-publico

- CSS com tokens `--ink`/`--paper`/etc. espelhando Loja.
- Paginação com páginas e “Mostrando X–Y de Z”.
- Contrato `Pagination.total` (default 0 se ausente em mocks).

### portal-gestao

- `EstoqueClient.obter_loja` / `atualizar_loja`.
- Rota + template de configuração do WhatsApp do catálogo.
- Item de nav em Ajustes quando estoque habilitado.

## Testes

- Estoque: total, ordem com/sem foto, PATCH whatsapp.
- Catálogo: HTML de páginas e contagem.
- Portal: smoke da tela (quando shell/estoque configurados nos testes existentes, ou unit do client).
