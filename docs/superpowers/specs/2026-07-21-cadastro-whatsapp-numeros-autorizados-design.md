# Design — Fluxo de cadastro por WhatsApp para números autorizados

**Data:** 2026-07-21
**Status:** Aprovado (aguardando plano de implementação)

## Problema

O gate do n8n (`Gate somente nao salvos1`) é fail-closed por número salvo:
descarta toda mensagem em que `isSaved !== false`. O cadastro de veículo pelo
WhatsApp (E5/E6) só dispara para números autorizados — mas números da equipe
quase sempre estão **salvos** na agenda da loja. Resultado: a mensagem do
vendedor é descartada antes do agente rodar, e `cadastrar_veiculo` nunca é
chamado. Na prática, o cadastro por WhatsApp só funcionaria se o número do
vendedor **não** estivesse salvo — frágil e não é como uma loja real opera.

O template versionado, por decisão anterior, não tem bypass por telefone.

## Objetivo

Permitir que um número **salvo e autorizado** (cadastrado no Portal) entre num
fluxo separado de cadastro ao enviar a palavra-gatilho, cadastre veículos e
envie fotos, sem alterar o fluxo de atendimento ao cliente.

## Decisões fechadas (brainstorming)

- **Entrada:** sessão por gatilho. O autorizado manda `cadastro`, abre uma
  sessão; as mensagens seguintes (dados + fotos) vão pro fluxo de cadastro.
- **Gatilho / encerramento:** palavra fixa `cadastro` (no código). Sessão
  encerra com `fim`/`sair` **ou** após ~30 min de inatividade.
- **Escopo do cadastro:** cadastrar veículo (texto) + enviar fotos —
  reaproveita o que já existe e é testado. Sem editar/remover pelo Zap (YAGNI).
- **Tela no Portal:** lista simples — telefone + nome opcional + ativar/desativar/remover.
- **Arquitetura:** decisão de roteamento centralizada no Chatbot (Python
  testável); o n8n só ramifica na resposta.

## Arquitetura

### Roteamento (n8n)

```
Evolution webhook → n8n
  → Consultar contato na Evolution (isSaved)        [já existe]
  → POST chatbot /v1/operacao/roteamento            [NOVO nó HTTP]
       body: { telefone, texto, is_saved }
  → switch(acao):
       "cliente"           → AI Agent cliente        [fluxo atual, intacto]
       "cadastro"          → AI Agent cadastro        [branch novo: cadastrar_veiculo + fotos]
       "cadastro_controle" → envia resposta e para    [confirmações, sem IA]
       "ignorar"           → para                     [salvo não-autorizado ou fora de sessão]
```

O gate `isSaved !== false` deixa de decidir sozinho — quem decide é o Chatbot.

### Chatbot — endpoint de roteamento

`POST /v1/operacao/roteamento` — autenticado pelo token que o n8n já usa; a loja
é resolvida pela instância (nunca vem do body do cliente). Entrada:
`{ telefone, texto, is_saved }`.

Lógica:

- `is_saved === false` → **`cliente`** (não-salvo = cliente; comportamento atual).
- Salvo/desconhecido → busca número autorizado **ativo** (por loja + telefone
  normalizado):
  - não encontrado → **`ignorar`** (bot fica calado, como hoje).
  - encontrado, **sem sessão** aberta:
    - `texto` começa com `cadastro` → abre sessão (agora + 30 min) →
      **`cadastro_controle`** com `resposta` = *"Modo cadastro aberto. Envie os
      dados do veículo e as fotos. Mande 'fim' para encerrar."*
    - senão → **`ignorar`** (autorizado usa o WhatsApp normal sem o bot responder).
  - encontrado, **com sessão** aberta:
    - `texto` é `fim`/`sair` → fecha sessão → **`cadastro_controle`** com
      `resposta` = *"Cadastro encerrado."*
    - senão (dados ou foto) → renova a sessão (agora + 30 min) → **`cadastro`**.

Contrato de resposta:

```json
{ "acao": "cliente" }
{ "acao": "ignorar" }
{ "acao": "cadastro" }
{ "acao": "cadastro_controle", "resposta": "..." }
```

### Estado da sessão

Nova coluna `cadastro_expira_em` (datetime, nullable) na tabela
`numeros_autorizados` — mesma tabela que já guarda `foto_placa_atual` (estado
operacional por número). Aberta = `agora + 30 min`; cada mensagem de cadastro
renova; `fim`/timeout limpa (`NULL`). Sem tabela nova. Sessão considerada aberta
quando `cadastro_expira_em` não é nulo e é maior que agora.

### Migration do Chatbot

`numeros_autorizados`: adiciona `nome` (String, nullable) + `cadastro_expira_em`
(DateTime, nullable). Head **0007 → 0008**. Nada no Portal (Portal não guarda
esses dados).

### Portal — tela de gestão (BFF)

- Página nova em Configurações/Operação: **"Números de cadastro"**.
- Portal como BFF: endpoints que fazem proxy para a API que já existe no Chatbot
  (`GET/POST/DELETE /v1/operacao/numeros-autorizados`), usando o token que o
  Portal já possui. Portal **não** ganha tabela.
- UI: listar (telefone, nome, ativo), adicionar (telefone + nome opcional),
  ativar/desativar/remover.

## Fluxo de uso (dono/vendedor)

1. Dono adiciona o número do vendedor na tela "Números de cadastro" (uma vez).
2. Vendedor manda `cadastro` → sessão abre → bot confirma.
3. Vendedor manda os dados do veículo → veículo publicado no Estoque → aparece
   no Catálogo.
4. Vendedor manda as fotos → galeria do veículo.
5. Vendedor manda `fim` (ou passa 30 min) → sessão encerra.

## Segurança / fail-safe

- Se o `/roteamento` cair, o n8n faz **fallback** para o gate antigo:
  `is_saved === false → cliente`, senão `ignorar`. O fluxo de cliente nunca
  quebra por causa desta feature.
- O branch de **foto** também passa pelo roteamento: só grava foto quando
  `acao === "cadastro"` (autorizado em sessão). Foto de número estranho não
  entra no Estoque.
- Telefone normalizado com o `normalizar_telefone` que já existe.
- Número salvo não-autorizado → `ignorar` (bot calado, como hoje).

## Testes

- **Chatbot:** pytest do `/roteamento` cobrindo todos os ramos — cliente,
  ignorar (não-autorizado e autorizado fora de sessão), abre sessão, renova,
  fecha por `fim`, fecha por timeout, `is_saved` desconhecido.
- **Portal:** pytest dos endpoints BFF de proxy (lista/adiciona/remove).
- **n8n:** assertions novas no `validate_workflow.py` (existência do nó de
  roteamento e dos ramos).
- **Migration:** upgrade/downgrade testados.

## Fora de escopo (YAGNI)

- Editar/remover/despublicar veículo pelo WhatsApp.
- Papéis dono/vendedor expostos na tela do Portal (a coluna existe, a UI não usa agora).
- Histórico de cadastros por vendedor.
- Palavra-gatilho configurável (fixa `cadastro` por ora).

## Componentes tocados

| Componente | Mudança |
|---|---|
| `chatbot-api` | endpoint `/v1/operacao/roteamento`; lógica de sessão em `operacao.py`; migration 0008 (`nome`, `cadastro_expira_em`) |
| `portal-gestao` | endpoints BFF de proxy + página "Números de cadastro" |
| `n8n/workflow-ai-nao-salvos.json` | nó HTTP de roteamento + switch de ramos + branch de cadastro; `validate_workflow.py` |
