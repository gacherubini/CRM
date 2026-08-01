# PR-4 — Identidade Loja fase B: memberships multi-loja na sessão

**Status:** PLANO (não implementado). Referência: as-built
`docs/design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md` §7 PR-4 (linha 436).

**Gate:** sem mudar auth password; flag `REVY_LOJA_ENTITLEMENTS_ENABLED` continua default off.

**Motivação:** hoje o Portal é single-loja por usuário (`Usuario.email unique` + um só
`loja_slug`). Quando o Control vincula um dono cujo e-mail já existe em outra loja, o
`issue_owner_invitation` levanta `OwnerInvitationConflict`
(`portal-gestao/app/owner_invitations.py:68`, condição `user.loja_slug != normalized_slug`)
e o operador vê "Dono vinculado, mas não foi possível enviar o convite". O Control já tem
`CargoLoja` (multi-loja) e entrega snapshots com `people[]`/`roles[]`, mas o Portal **não
persiste** essas projeções — `HttpControlProjectionPort.get_memberships` retorna `[]` e a
auth continua usando `Usuario.loja_slug` legado.

---

## Diagnóstico — a mensagem tem 3 causas (confirmado empiricamente 2026-07-31)

A frase "Dono vinculado, mas não foi possível enviar o convite"
(`revy-trafego/app/web/control_ui.py:786`) dispara sempre que `convidar_dono` levanta
`PortalIndisponivel` — e `convidar_dono` (`revy-trafego/app/clients/portal.py:85-93`)
colapsa **qualquer** resposta não-2xx do Portal em `PortalIndisponivel`. Reproduzido
batendo no endpoint real `POST /internal/v1/lojistas/convite`:

| Cenário | Status do Portal | Origem | Este PR resolve? |
|---|---|---|---|
| Dono já vinculado a OUTRA loja | **409** | `owner_invitations.py:68` | **Sim** (Passos 7-8) |
| Envio de e-mail estoura (SMTP) | **502** | `web/owner_invitations.py:86-90` | Parcial: troca 502→200 `email_pendente`, mas o e-mail continua sem sair |
| Caminho feliz (backend `console`) | **200** | — | — (`console` só loga; ninguém recebe) |

**Consequência para o escopo:** este PR ataca o **409** (dono multi-loja). Ele **não**
entrega o e-mail: com o backend default `console`
(`portal-gestao/app/email/sender.py:40-42`, que não levanta) o convite retorna 200 mas
**nada é enviado**; só SMTP real entrega. Configurar SMTP é pré-requisito independente
(ver `docs/superpowers/plans/2026-07-31-acesso-convite-email-cascata.md`, Fatia 4).

**Antes de começar:** confirmar qual status o Portal está devolvendo no caso do dono
(409 vs 502). Se for 502, o problema é SMTP e este PR **não** é o plano certo. O caminho
de convite do dono (endpoint + camada de e-mail no Portal) **já foi construído** (Fatia 2
do plano cascata; `web/owner_invitations.py`, commits `4b100a9`/`c94bcfe`) — este PR
**estende** esse caminho para multi-loja, não o cria do zero.

---

## Escopo do PR-4

Completar o caminho B do cutover de identidade: persistir `people[]`/`roles[]` do
snapshot do Control numa tabela de vínculos do Portal e alimentar `memberships` dela,
para que um dono (ou gerente/vendedor) possa operar várias lojas com seletor real.

**Não entra:** mudar auth/senha; migrar `Usuario` para `Pessoa`; apagar `loja_slug`
legado; ligar entitlements por default; multi-loja no Catálogo/Chatbot (só Portal).

---

## Passos

### Passo 1 — Modelo: tabela de vínculos `vinculo_loja_pessoa`

**Criar** migration `portal-gestao/alembic/versions/0017_vinculo_loja_pessoa.py`.

Tabela:
```
vinculo_loja_pessoa
  id           String(36) PK
  pessoa_id    String(36) NOT NULL  -- referencia pessoas do Control projetada
  loja_slug    String(120) NOT NULL
  cargo        String(32) NOT NULL   -- dono | gerente | vendedor
  state        String(32) NOT NULL   -- ativo | revogado | pendente
  versao       Integer NOT NULL      -- versao do envelope que produziu
  atualizado_em DateTime
  UNIQUE (pessoa_id, loja_slug, cargo)
  INDEX (pessoa_id)
  INDEX (loja_slug)
```

**Criar** também `pessoa_revy_projetada` (se ainda não existe) para evitar FK órfã:
```
pessoa_revy_projetada
  id    String(36) PK
  email String(320) UNIQUE NOT NULL
  nome  String(160)
```
Alternativa: reusar `Usuario` como projeção de `pessoa_id` (ver Passo 3 — decisão de
design a confirmar).

**Modificar** `portal-gestao/app/models.py`: adicionar `VinculoLojaPessoa` ORM.

### Passo 2 — Persistir projeção no endpoint de provisioning

**Modificar** `portal-gestao/app/provisioning.py` → `apply_payload`.

Hoje só processa `operational[]` (envelopes de estado). Acrescentar processamento de
`people[]` e `roles[]` do payload:

1. Para cada `person` em `payload["people"]`:
   - Upsert em `pessoa_revy_projetada` (ou mapear para `Usuario.id` se decisão do
     Passo 3 for reusar `Usuario`).
2. Para cada `role` em `payload["roles"]` ou derivado de `people[].roles`:
   - Upsert em `vinculo_loja_pessoa` com `state`, `versao` do envelope.
   - **Monotônico:** se `versao` menor que a local → `stale` (não revoga).
   - Se `state` mudou → `applied`.
   - Idempotente se mesma versão+state.

**Gate:** nenhuma mutação se `REVY_CONTROL_PROVISIONING_DELIVERY_ENABLED=0` (já é o
caso hoje — o endpoint existe mas o worker do Control não entrega sem flag).

### Passo 3 — Resolver `pessoa_id` ↔ `Usuario`

**Decisão de design** (confirmar antes de codar):

- **Opção A (recomendada):** criar `pessoa_revy_projetada` separada. `Usuario` continua
  para auth. O `pessoa_id` da sessão passa a ser `pessoa_revy_projetada.id` (ou
  `Usuario.id` como aliases durante cutover). Mantém `Usuario` intacto.
- **Opção B:** reusar `Usuario.id` como `pessoa_id`. Simples, mas acopla auth a
  projeção. Se o Control criar uma Pessoa antes do usuário existir (convite pendente),
  FK quebra.

Recomendo **Opção A** com tabela separada — separa identidade (Control) de autenticação
(Portal) e permite convite pendente sem `Usuario`.

### Passo 4 — `HttpControlProjectionPort.get_memberships` real

**Modificar** `portal-gestao/app/loja/control_projection.py` → `HttpControlProjectionPort`.

Hoje `get_memberships` retorna `[]`. Mudar para ler `vinculo_loja_pessoa` do DB:

```python
def get_memberships(self, pessoa_id: str) -> list[StoreMembership]:
    with SessionLocal() as db:
        rows = db.query(VinculoLojaPessoa).filter(
            VinculoLojaPessoa.pessoa_id == pessoa_id,
            VinculoLojaPessoa.state == "ativo",
        ).all()
        # agrupar por loja_slug, unir cargos
        ...
```

**Resolver `pessoa_id` do `Usuario` logado**: adicionar coluna
`Usuario.pessoa_revy_id` (nullable; migration) ou mapear por e-mail em
`pessoa_revy_projetada`. Usar e-mail como chave de resolução no cutover.

### Passo 5 — `loja_shell.py`: alimentar memberships do port real

**Modificar** `portal-gestao/app/web/loja_shell.py`.

Hoje `resolve_store_and_entitlements` recebe `control_memberships=None` (linha 46).
`_actor_for` chama `actor_from_usuario(usuario, memberships=None)` → fallback em
`membership_from_usuario` (single-loja legado).

Mudança: quando `control_memberships is None`, **consultar o port** ao invés de cair
no fallback legado:

```python
port = get_control_projection_port()  # factory; Http ou InMemory
pessoa_id = _resolve_pessoa_id(usuario)
control_memberships = port.get_memberships(pessoa_id)
actor = _actor_for(usuario, memberships=control_memberships or None)
```

Se `control_memberships` vier vazio (Control não projetou ainda), **continuar
fallback legado** — cutover seguro.

### Passo 6 — Seletor de loja no header (multi-membership)

**Modificar** templates `portal-gestao/templates/base.html` ou
`templates/loja/base.html` (onde `lojas_disponiveis` é renderizado).

Hoje `template_extras` já devolve `lojas_disponiveis = available_store_slugs(actor)`
(loja_shell.py:104). Quando houver >1 loja, renderizar dropdown `<select>` que faz
POST `/app/loja/selecionar` (rota já existe, loja_shell.py:152).

A rota `loja_selecionar` já valida com `select_store_slug(actor, slug)` — **não exige
mudança**, só precisa de `actor` com memberships multi-loja preenchidas (Passo 5).

### Passo 7 — `owner_invitations.py`: convite multi-loja

**Modificar** `portal-gestao/app/owner_invitations.py` → `issue_owner_invitation`.

Hoje (linha 55-76): se `Usuario` existe e `loja_slug != normalized_slug` →
`OwnerInvitationConflict`. Mudar:

1. Se usuário **não existe**: criar `Usuario` (como hoje) + criar
   `vinculo_loja_pessoa` com `cargo=dono, state=pendente`.
2. Se usuário **existe e ativo**: não criar outro `Usuario`; **criar
   `vinculo_loja_pessoa`** para a nova loja. Se já existe vínculo ativo para a mesma
   loja, reemitir token (idempotente). Se existe para **outra** loja, criar o novo
   vínculo e emitir token — não conflitar.
3. `Usuario.loja_slug` permanece a **primeira** loja (legado); o seletor da sessão
   (Passo 6) decide qual loja opera. Não mudar `loja_slug` preserva o rollback do
   cutover. **Atenção:** criar o `vinculo_loja_pessoa` da 2ª loja **não basta** para o
   dono operá-la — sem os Passos 4-6 e `REVY_LOJA_ENTITLEMENTS_ENABLED=1`, a sessão
   continua no fallback legado (`get_memberships` vazio → só a loja de `loja_slug`).
   Ver "Ordem segura".

**Modificar** `portal-gestao/app/web/owner_invitations.py` (endpoint HTTP):
- Tratar `OwnerInvitationConflict` como **sucesso** (409 → 200 com
  `{"usuario_id", "email", "loja_slug", "expira_em", "reenvio": true}`) quando o
  vínculo já existe e é idempotente.
- Envio de e-mail: não retornar 502 quando falha — retornar 200 com
  `{"email_pendente": true}` e logar o erro. O vínculo já está salvo. **Isso remove o
  502 da tela, mas não conserta a entrega** — o e-mail só chega com SMTP configurado
  (ver Diagnóstico); com `console` o `email_pendente` nem aparece (retorna 200 "normal").

### Passo 8 — Control: tratar respostas do Portal

**Modificar** `revy-trafego/app/clients/portal.py` → `convidar_dono`.

Hoje qualquer erro HTTP vira `PortalIndisponivel`. Mudar:
- HTTP 409 → **não é erro**: o Portal disse que o vínculo já existe; tratar como
  sucesso idempotente (retornar o corpo do 409 como dict, sem raise).
- HTTP 200 com `email_pendente: true` → **sucesso** (o convite foi criado; e-mail
  enviado depois).
- HTTP 502 (legado) → manter `PortalIndisponivel` mas com retry (mudar `retries=0`
  para `retries=self.retries` que é o default configurável).

**Modificar** `revy-trafego/app/web/control_ui.py:777-791`: quando
`convidar_dono` retornar sucesso com `email_pendente`, mostrar aviso não-bloqueante
em vez de erro 502. Redirecionar para o detalhe com `?aviso=email_pendente`.

### Passo 9 — Cutover por flag

**Não introduzir flag nova.** O PR-4 é ativado pela combinação existente:
- `REVY_CONTROL_PROVISIONING_DELIVERY_ENABLED=1` (Control entrega snapshots)
- `REVY_LOJA_ENTITLEMENTS_ENABLED=1` (Portal consome memberships no shell)

Sem essas flags, o código novo é **dormant**: `get_memberships` retorna `[]` (sem
projeção persistida), `owner_invitations` cria `vinculo_loja_pessoa` mas o shell
ainda usa fallback legado. **Rollback = desligar flags.**

---

## Arquivos a criar/modificar

| Arquivo | Ação | Linhas-chave |
|---|---|---|
| `portal-gestao/alembic/versions/0017_vinculo_loja_pessoa.py` | criar | migration |
| `portal-gestao/app/models.py` | modificar | adicionar `VinculoLojaPessoa`, `PessoaRevyProjetada` |
| `portal-gestao/app/provisioning.py` | modificar | `apply_payload`: persistir `people[]`/`roles[]` (linha 11) |
| `portal-gestao/app/loja/control_projection.py` | modificar | `HttpControlProjectionPort.get_memberships` real (linha 215) |
| `portal-gestao/app/web/loja_shell.py` | modificar | `resolve_store_and_entitlements`: alimentar do port (linha 41-67) |
| `portal-gestao/app/owner_invitations.py` | modificar | `issue_owner_invitation`: multi-loja (linha 41-103) |
| `portal-gestao/app/web/owner_invitations.py` | modificar | 409→200, e-mail não-bloqueante (linha 63-90) |
| `portal-gestao/templates/loja/base.html` (ou `base.html`) | modificar | seletor dropdown multi-loja |
| `revy-trafego/app/clients/portal.py` | modificar | 409→sucesso, retry, `email_pendente` (linha 46-93) |
| `revy-trafego/app/web/control_ui.py` | modificar | aviso não-bloqueante (linha 777-791) |

---

## Testes a escrever

### Portal (`portal-gestao/tests/`)
- `test_projection_persists_people_roles.py`: `apply_payload` com `people[]`/`roles[]`
  cria `VinculoLojaPessoa`; segunda chamada idempotente; versão stale não revoga.
- `test_memberships_multi_loja.py`: `HttpControlProjectionPort.get_memberships`
  devolve N memberships ativas; filtra `state != ativo`.
- `test_loja_shell_multi_membership.py`: usuário com 2 memberships; seletor troca;
  `resolve_store_context` isola cargos por loja (cargo de A não vaza para B).
- `test_owner_invitation_multi_loja.py`: mesmo e-mail dono em 2 lojas → 2 vínculos
  criados, 2 tokens emitidos, sem `OwnerInvitationConflict`.
- `test_owner_invitation_email_pending.py`: SMTP falha → 200 com `email_pendente`,
  vínculo salvo.
- `test_owner_invitation_idempotent.py`: reenvio para mesma loja → 200 com
  `reenvio: true`, não 409.

### Control (`revy-trafego/tests/`)
- `test_portal_client_409_is_success.py`: Portal 409 → `convidar_dono` retorna dict,
  sem `PortalIndisponivel`.
- `test_portal_client_email_pending.py`: Portal 200 com `email_pendente` → sucesso.
- `test_control_ui_invite_success_path.py`: fluxo completo cria loja + vincula dono
  → redirect 303, não 502.

---

## Riscos e mitigações

| Risco | Impacto | Mitigação |
|---|---|---|
| `Usuario.loja_slug` legado ainda usado em 100+ pontos | Regressão em relatórios/equipe/CAPI que assumem 1 loja | `loja_slug` continua válido (primeira loja); seletor de sessão troca o contexto; queries legadas continuam funcionando para a loja padrão |
| Projeção não chega (flag off) | `get_memberships` retorna `[]`, fallback legado | **Dormant** sem flag; rollback = desligar |
| `pessoa_id` ≠ `Usuario.id` (convite pendente sem `Usuario`) | `get_memberships` não resolve | Opção A: tabela `pessoa_revy_projetada`; resolver por e-mail no cutover |
| E-mail não enviado mas vínculo criado | Dono não recebe link de ativação | 200 com `email_pendente`; churn de reenvio via UI do Control |
| Conflito de versão tardio (snapshot antigo chega depois) | Reativa vínculo revogado | Monotônico: `versao < local` → `stale`, não aplica |
| Isolamento multi-loja quebrado (cargo de A vaza p/ B) | Vendedor de loja A vê dados de B | `roles_in_store` já filtra por slug; testes de isolamento obrigatórios |

---

## Dependências críticas

1. **`REVY_CONTROL_PROVISIONING_DELIVERY_ENABLED=1`** no Control — sem isso o snapshot
   nunca chega ao Portal. Hoje está OFF (lab).
2. **`REVY_LOJA_ENTITLEMENTS_ENABLED=1`** no Portal — sem isso o shell não consulta
   memberships do port. Hoje está OFF.
3. **Endpoint `/internal/v1/provisioning/state`** do Portal já existe
   (`web/trafego.py:896`) e já chama `provisioning.apply_payload` — só precisa
   estender para `people[]`/`roles[]`.
4. **Deployspiloto** (PR-10 do as-built): ligar flags em 1 loja e observar antes
   de generalizar.

---

## Ordem de implementação sugerida

1. Migration + models (Passo 1) — sem behavior change.
2. `provisioning.apply_payload` persiste people/roles (Passo 2) — dormant sem flag.
3. `HttpControlProjectionPort.get_memberships` (Passo 4) — dormant sem projeção.
4. `owner_invitations` multi-loja + endpoint 200 (Passo 7) — corrige o erro atual.
5. Control `portal.py` + `control_ui.py` (Passo 8) — deixa de quebrar.
6. `loja_shell.py` alimenta memberships do port (Passo 5) — ativa multi-loja na UI.
7. Seletor dropdown (Passo 6) — UX multi-loja.
8. Testes em paralelo a cada passo.

**Ordem segura (corrigida):** os **Passos 7 e 8** (owner_invitations + Control client)
podem ir **antes** do resto e fazem o operador do Control **parar de ver o erro** já no
primeiro merge. **Mas 7-8 sozinhos NÃO entregam multi-loja de verdade:** com as flags
OFF, o dono convidado para a 2ª loja ativa a senha e, ao logar, **só enxerga a loja de
`Usuario.loja_slug`** (fallback legado — Passos 5 e 9). O erro visível vira um **sucesso
enganoso** (Control diz "ok", dono não alcança a loja nova). Para o dono realmente operar
as duas lojas é **obrigatório** entregar também os Passos 4-6 e ligar
`REVY_LOJA_ENTITLEMENTS_ENABLED=1` (piloto de 1 loja — dependência #4). E, em qualquer
caso, o e-mail só chega com SMTP configurado (Diagnóstico).

**Corte enxuto recomendado** (multi-loja funcionando, sem o resto do sync de snapshot):
Passos **1, 4, 5, 6, 7, 8** + flag no piloto. O **Passo 2** (persistir projeção
`people[]`/`roles[]` do Control) **pode ser adiado** — é outro driver (sync
Control→Portal), não o convite do dono, que grava `vinculo_loja_pessoa` direto no Passo 7.
O **Passo 3** pode, no 1º corte, resolver `pessoa_id` por e-mail contra `Usuario` (que o
convite já cria), evitando a tabela `pessoa_revy_projetada`.
