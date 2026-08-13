# Autogestão de senha do lojista — reset por e-mail + troca logado

- Data: 2026-08-01
- Produto: Portal de Gestão (`portal-gestao`)
- Status: aprovado (design), pronto para plano de implementação

## Objetivo

Permitir que o lojista gerencie a própria senha, sem depender do admin:

1. **Esqueci minha senha** (deslogado): recupera acesso via link enviado por e-mail.
2. **Trocar senha** (logado): troca a própria senha informando a senha atual.

## Escopo

- **Vale para:** qualquer usuário **ativo** do Portal com e-mail (dono, gerente, vendedor).
- **Fora do escopo (v1):**
  - Login do **Revy Control** (gestor de tráfego, `revy-trafego`) — fluxo separado, fica para depois.
  - Invalidar outras sessões ativas ao trocar/redefinir senha (a sessão é cookie assinado, sem store server-side).
  - Política de complexidade além de tamanho (sem exigência de símbolos/números).

## Contexto do código existente (reuso)

- `app/auth.py`: `hash_senha`, `verifica_senha`, `autenticar`, `usuario_atual`, `csrf_token`, `csrf_valido`.
- `app/owner_invitations.py`: padrão de token single-use já implementado (hash sha256, `expira_em`, `usado_em`, `revogado_em`, `_token_hash`, `_as_utc`). O reset **espelha** esse padrão em módulo próprio.
- `app/models.py::ConviteAcessoLoja`: referência do modelo de token. **Não** será reusada (ver decisão abaixo).
- `app/web/equipe.py::_validar_nova_senha`: validação de senha (tamanho + confirmação). Mínimo hoje = `SENHA_EQUIPE_MINIMA = 10` (em `app/main.py`); o convite do dono usa 12.
- `app/loja/navigation.py`: seção **"Ajustes"** no shell da Loja — onde a tela de trocar senha logado será pendurada.
- `app/email/__init__.py` + `sender.py`: `send_email(EmailMessage(...))` — infra de e-mail (SMTP/console) já usada pelo convite.

## Decisões de design

### D1. Tabela dedicada de reset (não reusar `ConviteAcessoLoja`)

Nova tabela `RedefinicaoSenha`, espelhando o padrão de token. O convite cria usuário+vínculo e ativa acesso; o reset apenas troca a senha de quem já existe. Reusar `ConviteAcessoLoja` acoplaria o reset ao fluxo de ativação (recém-corrigido) e embolaria as duas responsabilidades. Módulos separados = fronteiras limpas e testáveis.

Alternativas descartadas:
- Reusar `ConviteAcessoLoja` — acopla reset à ativação.
- Reset sem token, mandando senha nova por e-mail — inseguro (senha em texto claro).

### D2. Política de senha unificada em 12 caracteres

O reset e a troca logado usam um **validador compartilhado** com mínimo **12** (alinha com o fluxo do dono, que é o lojista principal) e máximo 256, mais confirmação. A divergência do `equipe.py` (mínimo 10) fica registrada mas **não** é alterada nesta entrega.

### D3. Anti-enumeração + rate limit

- `POST /senha/esqueci` responde **sempre** de forma neutra ("Se houver uma conta com esse e-mail, enviamos um link"), sem revelar se o e-mail existe.
- Rate limit simples: se já existe token de reset **não usado** emitido há menos de ~2 min para aquele usuário, não reemite (evita flood). A resposta neutra é a mesma.
- Token nunca aparece em log/banco em texto claro (só o hash sha256). E-mail/link nunca vão para log.

## Componentes

### 1. Modelo + migration

`app/models.py::RedefinicaoSenha`:

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | str (uuid) | PK, padrão dos demais modelos |
| `usuario_id` | str FK `usuarios.id` | indexado |
| `token_hash` | String(64) unique | sha256 do token |
| `expira_em` | DateTime(tz) | criado_em + 24h |
| `usado_em` | DateTime(tz) nullable | marca uso único |
| `revogado_em` | DateTime(tz) nullable | reemissão revoga pendentes |
| `criado_em` | DateTime(tz) | para o rate limit |

Migration Alembic nova (head do Portal). `upgrade head` verificado.

### 2. Domínio `app/password_reset.py` (espelha `owner_invitations.py`)

- `issue_reset(db, *, email) -> IssuedReset | None`
  - normaliza e-mail; busca usuário **ativo**; se não existe/ inativo → retorna `None` (chamador responde neutro).
  - rate limit (D3); revoga tokens pendentes; gera token (`secrets.token_urlsafe(32)`), grava hash + `expira_em = agora()+24h`; retorna token + e-mail + nome.
- `consume_reset(db, *, token, password) -> Usuario`
  - valida token (formato); acha token válido (não usado, não revogado, não expirado) via helper compartilhado do padrão; valida senha (validador compartilhado); grava `senha_hash`; marca `usado_em`; commit.
  - erros → `PasswordResetInvalid("link inválido ou expirado")`.
- `_token_hash` / `_as_utc` são extraídos de `owner_invitations.py` para um util compartilhado `app/tokens.py`, consumido pelos dois módulos (convite e reset).

### 3. Validador de senha compartilhado

A validação (tamanho 12–256 + confirmação) vive em `app/password_rules.py`, consumida pelos dois fluxos novos (reset e troca logado).

### 4. Web — fluxo reset (deslogado)

Router novo `app/web/password_reset.py`:

- `GET /senha/esqueci` → form (e-mail) + csrf.
- `POST /senha/esqueci` → csrf; chama `issue_reset`; se retornou token, envia e-mail (`send_email`) com link `/senha/redefinir?token=…`; **resposta neutra** sempre.
- `GET /senha/redefinir?token=…` → form (nova senha + confirmação) ou página de erro se token claramente inválido.
- `POST /senha/redefinir` → csrf; `consume_reset`; sucesso → `RedirectResponse('/login?senha_redefinida=1')`; erro → re-render com mensagem.

E-mail (assunto/corpo): "Redefinir sua senha da Revy" + link + "expira em 24 horas". Sem token em log.

### 5. Web — troca logado (Ajustes)

- `GET /conta/senha` (autenticado) → form: senha atual, nova, confirmação.
- `POST /conta/senha` → csrf; `verifica_senha(user.senha_hash, atual)`; se falhar → erro "senha atual incorreta"; valida nova (validador compartilhado); grava hash; flash de sucesso.
- Item novo na seção **Ajustes** do shell da Loja apontando para `/conta/senha`.

### 6. UI

- Link **"Esqueci minha senha"** na página `/login`.
- Templates novos: `senha_esqueci.html`, `senha_redefinir.html`, `conta_senha.html` (seguindo os templates existentes, ex.: `convite_aceitar.html`).
- Mensagens de sucesso no `/login` (`senha_redefinida=1`) e na tela de Ajustes.

## Fluxo de dados

```
Esqueci:
  /login → "Esqueci minha senha"
  GET /senha/esqueci → form
  POST /senha/esqueci → issue_reset → (se ativo) send_email(link) → resposta neutra
  e-mail → GET /senha/redefinir?token → form
  POST /senha/redefinir → consume_reset → /login?senha_redefinida=1

Trocar (logado):
  Ajustes → GET /conta/senha → form (atual/nova/confirmação)
  POST /conta/senha → verifica_senha(atual) → grava nova → sucesso
```

## Tratamento de erros

- Token inválido/expirado/usado → "link inválido ou expirado" (mesma msg para os três, sem vazar qual).
- Senha fora das regras → mensagem do validador (tamanho/confirmação).
- Senha atual errada (troca logado) → "senha atual incorreta".
- CSRF inválido → "sessão expirada, recarregue".
- E-mail inexistente no reset → resposta neutra (não é erro visível).

## Testes

**Domínio (`password_reset`):**
- emitir para usuário ativo gera token; usuário inexistente/inativo → `None`.
- consumir token válido troca a senha e marca `usado_em`.
- token expirado / já usado / revogado / formato inválido → `PasswordResetInvalid`.
- reemitir revoga o token pendente anterior.
- rate limit: reemissão < 2 min não gera novo token.

**Endpoints:**
- `POST /senha/esqueci` responde neutro tanto para e-mail existente quanto inexistente (sem diferença observável).
- reset feliz: e-mail ativo → link → redefinir → login com aviso; senha nova autentica.
- `POST /conta/senha` feliz troca a senha; senha atual errada → erro e senha inalterada.

## Verificação antes de concluir

- `python -m pytest -q` no `portal-gestao` verde (fora as falhas pré-existentes de `test_funil.py`).
- `alembic upgrade head` aplica a migration nova; head correto do Portal.
- `git diff --check` limpo.
