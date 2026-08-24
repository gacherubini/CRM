# Modo 2 — humanização da entrega — Implementation Plan

> **For agentic workers:** a Task 1 é a única grande e cruza dois produtos —
> `chatbot-api` **e** `n8n`. Não faça os dois na mesma leva (`AGENTS.md` §4).
> A Task 3 é **decisão do dono**, não código: um agente não a executa sozinho.

**Goal:** o bot do Modo 2 entregar as mensagens como o do Modo 1 entrega — com
"digitando…", espaçadas — sem mexer no que ele diz.

**Architecture:** nada novo. O cálculo já existe e já roda; falta caminho para a
saída dele chegar na central Cloud.

**Diagnóstico completo** (não re-descubra):
[`../referencia-viva/design/2026-08-16-whatsapp-modo2-asbuilt.md`](../referencia-viva/design/2026-08-16-whatsapp-modo2-asbuilt.md),
seção "O bot do Modo 2 fala igual ao do Baileys, mas não soa igual".

## O que já está estabelecido

O `systemMessage` é **byte a byte idêntico** nos dois workflows. A personalidade
não divergiu — o que divergiu foi a entrega. Não gaste tempo comparando prompt.

`Atraso anti-ban1` é idêntico nos dois e **continua rodando** no Modo 2,
calculando `__delayAntiBan` (~45 ms/char até 4 s, mais jitter de 0,8–2,5 s, mais
espaçamento de 3–6 s entre mensagens da mesma instância). No Modo 1 o
`Responder WhatsApp1` manda `{ number, text, delay }` e a Evolution segura a
mensagem mostrando "digitando…". No Modo 2 ele manda `{ telefone, texto }`: **o
delay é calculado e jogado fora.**

## Global Constraints

- O `workflow-cloud.json` é **gerado**. Mudança no lado n8n vai em
  `n8n/fork_cloud_workflow.py`; editar o JSON à mão faz o
  `validate_workflow_cloud.py` sair 1.
- O `systemMessage` mora no n8n e é **compartilhado**: mexer nele muda o Baileys
  junto. Isso é a Task 3, e é decisão do dono.
- Deploy: mexeu em `n8n/` → sobe `n8n2037` com a sequência do
  `import → publish → update:workflow --active=true` (só o terceiro liga), e cada
  restart custa ~6 min de 404 com a Evolution cancelando retry. Mexeu em
  `chatbot-api/app/` → sobe `app2037`. Ver a skill `revy-deploy`.
- Nada de secret em git ou log.
- Testes a partir da pasta do produto: `.\.venv\Scripts\python.exe -m pytest tests -q`
  (Windows) e `.venv/bin/python -m pytest tests -q` (macOS). Rodar `pytest -q` da
  raiz do `chatbot-api` não coleta: há dois diretórios órfãos `test-tmp-run4/` e
  `test-tmp-run5/` que estouram `PermissionError` no scandir. Vale limpar.

---

## Task 1 — o "digitando…" chegar na central

Esta é a que muda a sensação. Duas metades; faça a do `chatbot-api` primeiro,
porque ela define o contrato que o n8n vai usar.

### 1a — `chatbot-api`

- [ ] `/v1/operacao/responder` (`app/main.py:1817`) passa a aceitar o atraso no
      corpo. Hoje recebe só `{telefone, texto}`.
- [ ] Ligar o indicador de digitação da Cloud API antes de enviar. **Atenção:** na
      Cloud ele não é parâmetro de envio — é chamada à parte que precisa do
      `wamid` da mensagem **do cliente**, que a rota não recebe hoje. O `wamid`
      está no banco (última mensagem de entrada da conversa); buscá-lo ali evita
      mudar o contrato com o n8n duas vezes.
- [ ] Decidir onde a espera acontece. `responder_cliente` é `def`, não
      `async def`: esperar dentro dela segura uma thread do pool por até 16 s por
      resposta. Ou a rota vira assíncrona, ou a espera muda de lugar.
- [ ] `WhatsAppOutboundPort.send_text` (`app/whatsapp_outbound.py:65`) é o port
      compartilhado pelos dois adapters. Se ganhar delay, muda Evolution, Cloud e
      o `FakeWhatsAppOutbound` juntos — avalie se o delay não deve ficar **fora**
      do port, já que só a Cloud precisa dele explicitamente.

**Como saber que acabou:** teste que prova que o indicador foi ligado e que o
envio veio **depois** da espera — não um teste que só confere que o campo existe
no corpo. Suíte do `chatbot-api` verde (473 na data deste card).

### 1b — `n8n`, leva separada

- [ ] Em `fork_cloud_workflow.py`, o `Responder WhatsApp1` do fork passa a
      repassar o `__delayAntiBan` no campo que a Task 1a definiu.
- [ ] Regerar e validar: `python n8n/validate_workflow_cloud.py` (sai 1 se o JSON
      divergir do gerador) e `python n8n/validate_workflow.py` na raiz.

---

## Task 2 — o filtro de minúsculas pular URL e código

Menor, e evita um link quebrado mais adiante.

- [ ] O `Responder WhatsApp1` do Modo 2 aplica
      `toLocaleLowerCase('pt-BR')` no texto **inteiro**. Um slug com maiúscula
      quebra o link, e o `Cód:` da task 4 do CTWA viraria `cód:`.
- [ ] Preservar URLs e códigos; o resto do filtro (minúsculas, sem emoji, `!`
      vira `.`) é **intencional** e fica.
- [ ] Nota de coerência: no Modo 1 o filtro só se aplica quando
      `fluxo.acao === 'cliente'`; no Modo 2 é incondicional. Como no Modo 2 não
      existe grupo, hoje dá no mesmo — decidir se vale igualar mesmo assim.

Tudo em `fork_cloud_workflow.py`. Sobe `n8n2037`.

---

## Task 3 — o tom, se o dono quiser (decisão, não código)

O que a conversa do piloto mostrou e o prompt permite: pede confirmação
redundante ("quer que eu simule?" logo depois do cliente dizer que gostou), pede
CPF, nascimento e CNH num bloco só, manda o link cru e nunca usa o nome do
cliente.

**Isso não é divergência entre os modos.** O `systemMessage` é o mesmo, então
mexer aqui muda o **Baileys junto**. Precisa de decisão explícita antes de
qualquer edição.

- [ ] Dono decide se o tom muda nos dois modos ou em nenhum.
- [ ] Se mudar: alvo é o `systemMessage` em `n8n/workflow-ai-nao-salvos.json`, e o
      fork propaga ao regerar. Subir `app2037` depois de mexer no prompt **não
      muda nada** — o prompt não está no `chatbot-api`.
