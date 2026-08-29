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

### Task 0: Declarar o app como Independent Tech Provider

**Sem isto a Task 1 não existe.** Conferido em 29/08: num app de WhatsApp "direto" (WABA
própria, o arranjo do piloto) a criação de configuração só oferece a variação *General* —
a de **WhatsApp Embedded Signup não aparece na lista**.

- [ ] **Passo 1:** App Dashboard → **WhatsApp → Início rápido**, seção *Scale your
      Business*, escolher **Independent Tech Provider**.
- [ ] **Passo 2:** Conferir que o piloto não caiu junto: `GET /{waba_id}/subscribed_apps`
      ainda lista o app da Revy, e uma mensagem ao número de teste ainda gera resposta.
      É o mesmo app que está em produção.
- [ ] **Passo 3:** Se o piloto quebrar, **parar aqui** e avisar. Reverter logo depois é
      barato; três dias depois, não.

---

### Task 1: Configuração v4 do Facebook Login for Business

**Entregável:** o `config_id` existe e o popup abre.

**Já decidido em 29/08, ao percorrer a tela** (as duas escolhas são irreversíveis):
tipo **token de acesso do usuário do sistema**, expiração **Nunca**. O "60 days
(recomendado)" da Meta pressupõe rotação automática, que não existe aqui — e token que
morre sozinho deixa a loja muda em silêncio. Mesma razão pela qual o token de System User
da Revy já está em Nunca.

- [ ] **Passo 1:** No App Dashboard, criar a configuração em **Login do Facebook para
      empresas → Configurações** (a **segunda** do menu, entre *Início rápido* e *Modelos* —
      a primeira é a de OAuth e não é essa).
- [ ] **Passo 2:** Selecionar **só** os ativos e permissões que o §10.2 do spec lista.
      Catálogos, contas de anúncio, Pages, datasets e contas de Instagram ficam **fora** —
      pedir ativo desnecessário é a causa de reprovação nº 1 e ela vale aqui também.
- [ ] **Passo 3:** Guardar o `config_id`. Ele **não** é segredo (vai no JS do navegador),
      então pode ficar em `[env]` do Fly, não em secret.
- [ ] **Passo 4:** Registrar no spec, em §7, qual template foi usado e quais ativos foram
      marcados.

---

### Task 2: Elo 1 — trocar o `code` por token de negócio

**A chamada já está confirmada pela doc** e escrita no §7 do spec:
`GET /{v}/oauth/access_token` com `client_id`, `client_secret` e `code`. O que sobrou aqui
são as três coisas que só a execução responde.

- [ ] **Passo 1:** Rodar o popup contra o business de teste e capturar o
      `response.authResponse.code`.
- [ ] **Passo 2:** Trocar o `code` por token no servidor **medindo o tempo** de ponta a
      ponta. O TTL é de 30 s e o desenho síncrono do §4 depende dessa folga: se a troca
      sozinha já come uma fatia grande, o desenho precisa de margem, não de fila.
- [ ] **Passo 3:** **A pergunta aberta que mais importa:** a resposta traz `expires_in`?
      O §8 assume token de vida longa. O template de configuração do Login se chama
      *"With 60 Expiration Token"*, o que levanta a suspeita de 60 dias — se o token
      expirar, o §8 muda e nasce uma dívida com prazo (renovação por loja), que hoje não
      existe em lugar nenhum do desenho. Anotar o campo, **nunca o valor**.
- [ ] **Passo 4:** Caminho triste: `code` reusado e `code` expirado. Anotar o erro exato de
      cada — é o que a tela do §6 precisa distinguir de erro nosso.

---

### Task 3: Elo 3 — registrar o número com PIN

**A chamada já está confirmada pela doc:** `POST /{phone_number_id}/register` com
`messaging_product=whatsapp` e `pin` de 6 dígitos, e duas etapas **não se desliga** pela API.

> **CUIDADO — este é o único passo do card com custo irreversível.** O registro tem teto de
> **10 chamadas por número em 72 h móveis**; estourar devolve `133016` e trava o número por
> três dias. Faça os passos abaixo **contando as tentativas**, e pare em 5. Se travar o
> número de teste, o spike inteiro para por 72 h.

- [ ] **Passo 1:** Registrar o número de teste e confirmar que a chamada da doc é a que
      funciona. (tentativa 1)
- [ ] **Passo 2:** **Repetir a chamada** com o número já registrado. O §7 assume que "já
      registrado" é sucesso, não erro — confirmar e anotar o código exato. Se for erro, o
      Card 3 precisa tratá-lo como sucesso explicitamente. (tentativa 2)
- [ ] **Passo 3:** Anotar o que acontece com número que ainda está ativo no aplicativo do
      WhatsApp. Isso falha **dentro** do popup — confirmar se chega evento até nós ou se a
      tela precisa mesmo da saída manual de "não deu certo". **Não gaste tentativa de
      registro nisto**: o teste é no popup, não no elo 3.
- [ ] **Passo 4:** Escrever no §7 quantas tentativas foram gastas e quando a janela de 72 h
      zera, para o Card 3 não começar já perto do teto.

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
