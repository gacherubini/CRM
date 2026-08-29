# Embedded Signup — Card 1: spike dos endpoints

> **For agentic workers:** este card é **pesquisa, não código**. Ele não tem TDD e não
> produz software. O entregável é uma seção escrita no spec, e ele **desbloqueia o Card 3**
> (a cadeia dos elos), que hoje não pode ser planejado sem placeholder.

**Goal:** confirmar, contra a API real, a sequência exata de chamadas dos elos 1 e 3 do
§7 do spec — troca do `code` por token e registro do número com PIN.

**Spec:** [`../referencia-viva/specs/2026-08-29-embedded-signup-tech-provider-design.md`](../referencia-viva/specs/2026-08-29-embedded-signup-tech-provider-design.md)

**Por que existe:** o §16.5 do spec dos dois modos marcou confiança **média** na sequência
do passo 6, e a conferência de 29/08 confirmou a *forma* (o SDK devolve `code`, `waba_id`,
`phone_number_id`, `business_id`; o `code` vale 30 s) mas **não** os endpoints dos elos 1
e 3. Planejar a cadeia sem isso produz tasks com "confirmar o endpoint" dentro do passo,
que é exatamente o que um plano não pode ter.

## Global Constraints

- Nada de token, `code`, App Secret ou PIN em log, em commit ou no corpo deste card.
  Registrar **forma** — endpoint, parâmetros, formato da resposta —, nunca valor.
- Business de **teste**, nunca a WABA de produção da Revy nem número de cliente.
- Não abrir código de produção neste card. O entregável é texto.

---

### Task 1: Configuração v4 do Facebook Login for Business

**Entregável:** o `config_id` existe e o popup abre.

- [ ] **Passo 1:** No App Dashboard, criar a configuração em **Facebook Login for Business
      → Configurations**, usando o template *"WhatsApp Embedded Signup Configuration With
      60 Expiration Token"* ou uma custom equivalente.
- [ ] **Passo 2:** Selecionar **só** os ativos e permissões que o §10.2 do spec lista.
      Catálogos, contas de anúncio, Pages, datasets e contas de Instagram ficam **fora** —
      pedir ativo desnecessário é a causa de reprovação nº 1 e ela vale aqui também.
- [ ] **Passo 3:** Guardar o `config_id`. Ele **não** é segredo (vai no JS do navegador),
      então pode ficar em `[env]` do Fly, não em secret.
- [ ] **Passo 4:** Registrar no spec, em §7, qual template foi usado e quais ativos foram
      marcados.

---

### Task 2: Elo 1 — trocar o `code` por token de negócio

**Entregável:** endpoint, parâmetros e forma da resposta escritos no §7 do spec.

- [ ] **Passo 1:** Rodar o popup contra o business de teste e capturar o
      `response.authResponse.code`.
- [ ] **Passo 2:** Trocar o `code` por token **no servidor**, medindo quanto tempo a troca
      leva de ponta a ponta. O TTL é de 30 s e a decisão de arquitetura do §4 depende
      dessa medida — se a troca sozinha já consome uma fatia grande, o desenho síncrono
      precisa de folga, não de fila.
- [ ] **Passo 3:** Registrar, **sem valores**: método, caminho, parâmetros exigidos, e se a
      resposta traz `expires_in` ou é permanente. O spec assume token por loja de vida
      longa (§8) — se ele expirar, o §8 muda e vira dívida com prazo.
- [ ] **Passo 4:** Testar o caminho triste: `code` reusado e `code` expirado. Anotar o erro
      exato de cada, porque é o que a tela `falhou` do §6 precisa distinguir de erro nosso.

---

### Task 3: Elo 3 — registrar o número com PIN

**Entregável:** endpoint, parâmetros e comportamento de repetição escritos no §7 do spec.

- [ ] **Passo 1:** Registrar o número de teste e anotar método, caminho e parâmetros,
      incluindo como o PIN de duas etapas entra.
- [ ] **Passo 2:** **Repetir a chamada** com o número já registrado. O §7 do spec assume
      que "já registrado" é sucesso, não erro — confirmar, e anotar o código exato de
      retorno. Se for erro, o Card 3 precisa tratá-lo como sucesso explicitamente, e é uma
      linha de código que só existe se este passo for feito.
- [ ] **Passo 3:** Anotar o que acontece com número que ainda está ativo no aplicativo do
      WhatsApp. É o erro mais comum previsto no §6 e ele acontece **dentro** do popup —
      confirmar se chega evento até nós ou se a tela precisa mesmo da saída manual de
      "não deu certo".

---

### Task 4: Elo 2 — confirmar que a inscrição continua igual

**Entregável:** uma linha no §7, confirmando ou corrigindo.

- [ ] **Passo 1:** `POST /{waba_id}/subscribed_apps` na WABA de teste. Este elo **já foi
      verificado em produção em 23/08**; o objetivo aqui é só confirmar que ele se comporta
      igual numa WABA que não é da Revy.
- [ ] **Passo 2:** Repetir a chamada e confirmar que é idempotente.
- [ ] **Passo 3:** Assinar o campo `message_template_status_update` no webhook e confirmar
      que o evento chega. O §7 do spec depende disso para o status do template, e é a única
      parte do card que toca configuração que já existe — conferir que não derruba o campo
      `messages`, que está em produção.

---

### Task 5: Fechar o spike

- [ ] **Passo 1:** Editar o §7 do spec, trocando as duas linhas "endpoint a confirmar" pelo
      que foi medido.
- [ ] **Passo 2:** Se algo contrariou o desenho — token com validade curta, "já registrado"
      sendo erro, evento que não chega —, escrever um learning na `revy-research` com o
      gatilho certo, procurando duplicata antes.
- [ ] **Passo 3:** Commitar spec e learning juntos.
- [ ] **Passo 4:** Avisar que o Card 3 pode ser escrito.

## Como saber que acabou

O §7 do spec não tem mais nenhuma célula "endpoint a confirmar", e cada elo tem método,
caminho, parâmetros e o comportamento da segunda chamada.
