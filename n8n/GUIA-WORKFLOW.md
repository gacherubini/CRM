# Guia do workflow da Vitor Motos

Este guia descreve o arquivo `workflow-ai-nao-salvos.json`, que é a fonte principal.
O fluxo de teste é gerado a partir dele e atende somente o número configurado em
`build_test_workflow.js`.

## Regra mais importante

Edite o arquivo principal. Não edite os arquivos `workflow-fly*.ready.json`: eles
são gerados com endereços e credenciais locais apenas na hora da publicação.

## Multi-WhatsApp (um workflow)

- A Evolution envia `body.instance` em todo webhook.
- `Extrair1` propaga `instance`; eventos sem instance são descartados.
- Chamadas Evolution usam a instance do evento (não há `__INSTANCE__` fixo).
- O Chatbot resolve loja/canal por instance; conversa e handoff são por canal.
- Placeholders de deploy: só `__EVOLUTION_KEY__`, `__CHATBOT_TOKEN__`,
  `__CHATBOT_WEBHOOK_TOKEN__` (e URLs). **Um workflow serve N números.**

No **Modo 2** (`workflow-cloud.json`) vale o mesmo princípio, com duas diferenças
que já custaram um bug silencioso:

- a `instance` é o **`phone_number_id` da Meta**, não um nome de instância Evolution;
- **um workflow serve N lojas, não só N números** — então a `instance` tem de ir em
  **toda** chamada ao chatbot, não só no inbound. O `__CHATBOT_TOKEN__` do Modo 2 é
  uma **credencial de integração** (sem loja): se a chamada não disser de qual loja
  fala, o chatbot procura a conversa na loja errada e o agente para — sem erro, só
  `200` e silêncio.

Quem garante isso é `validate_workflow_cloud.py`, que reprova chamada sem `instance`.
A injeção mora em `fork_cloud_workflow.py` (`INJECOES_INSTANCE`) e **para o gerador**
se a forma da chamada mudar no Modo 1, em vez de gerar um fork que serve uma loja só.
Exceção deliberada: `GET /v1/config/catalogo-bot`, que é cega para loja pelo contrato
com o Estoque — `instance` ali não consertaria nada.

## O prompt não mora mais aqui inteiro

Desde 25/08 o `systemMessage` do `AI Agent1` é **expressão**, e a última coisa que ele
manda ao modelo é o prompt **daquela loja**, buscado em `GET /v1/agente/config` pelos nós
`Buscar config do agente1` → `Gate config do agente1`. O que ficou no JSON é a operação do
atendimento (jornada, ferramentas, anti-alucinação); identidade, tom, FAQ e regras da loja
são dado no `chatbot-api`.

Três consequências práticas:

- **Não escreva nome, cidade nem tom de loja neste arquivo.** `validate_workflow.py`
  reprova `vitor motos` e `limeira` no template — era exatamente assim que a segunda loja
  se apresentaria como a primeira.
- **Nada pode ser colado depois do slot.** O prompt da loja termina no núcleo Revy, e o
  núcleo só prevalece porque é o último bloco. O validador reprova rodapé, marca d'água ou
  debug depois dele.
- **423 para o fluxo, e só falha técnica cai no padrão.** Loja suspensa responde 423; se o
  gate tratasse isso como falha, o bot atenderia loja suspensa.

Para mudar como **uma loja** fala, mexa na config dela (hoje por rota; a tela é o card 3).
Para mudar como **toda loja** opera, mexa aqui — e no núcleo Revy, que vive em
`chatbot-api/app/agente_prompt.py`.

O fluxo atual tem 34 nós e trabalha com:

- mensagens de texto de clientes;
- contexto de anúncios;
- consulta e fotos do estoque;
- cadastro de estoque pela equipe;
- simulação e criação de lead qualificado;
- encaminhamento para atendimento humano.

Áudios estão desativados. O nó `Extrair1` identifica `audioMessage` e encerra a
execução sem registrar, chamar a IA ou responder.

## Visão geral

```mermaid
flowchart LR
    A[Webhook1] --> B[Extrair1]
    B --> C{E imagem de estoque1}
    C -- foto do grupo --> D[Salvar foto no estoque1]
    D --> E[Foto deve responder1]
    E --> F[Responder cadastro de foto1]
    C -- texto --> G{E grupo de estoque1}
    G -- grupo --> H[Rotear grupo de estoque1]
    G -- cliente --> I[Registrar mensagem e ler handoff1]
    I --> J[Gate handoff e duplicidade1]
    J --> K[Consultar contato na Evolution1]
    K --> L[Rotear operacao1]
    H --> M[Gate somente nao salvos1]
    L --> M
    M --> N{Se resposta controle1}
    N -- menu da equipe --> O[Responder WhatsApp1]
    N -- cliente --> P[AI Agent1]
    P --> W[Aguardar 40s cliente1]
    W --> O
    O --> Q{E resposta de grupo1}
    Q -- cliente --> R[Registrar saida do bot1]
```

## O caminho de uma mensagem de cliente

1. `Webhook1` recebe o evento da Evolution.
2. `Extrair1` aceita apenas mensagem privada ou o grupo autorizado, ignora
   eventos técnicos, reações, saídas do próprio bot e áudios.
3. `E imagem de estoque1` separa fotos do grupo de estoque.
4. `E grupo de estoque1` separa operação da equipe de conversa de cliente.
5. `Registrar mensagem e ler handoff1` grava a entrada no CRM e devolve
   `bot_ativo`, `primeira_mensagem`, **`tem_saida`** (já houve resposta na conversa)
   e **`historico_recente`** (últimas msgs compactas para o prompt).
6. `Gate handoff e duplicidade1` encerra duplicatas e `fromMe` que não devem
   continuar.
7. `Consultar contato na Evolution1` + `Normalizar isSaved Evolution1` → `isSaved`
   (agenda) e `chatFound` (chat no WA). Lista vazia ⇒ `isSaved: null` (desconhecido).
8. `Rotear operacao1` → `/v1/operacao/roteamento` com `is_saved` e `chat_found`.
   Backend (defesa em profundidade), **ordem**: (1) conversa com saída → `cliente`;
   (2) `is_saved === true` no 1º contato → agenda, `ignorar`; (3) `chat_found` no
   1º contato → `ignorar`; (4) `is_saved` null/false sem prova → **fail-open**
   (atende lead novo/CTWA). `tem_saida` vem **antes** de agenda: após a 1ª resposta
   a Evolution costuma marcar `isSaved=true` e isso não pode calar a 2ª msg.
9. `Gate somente nao salvos1` — função **`atendeLeadVirgem()`** (juiz fino n8n):
   mesma ordem (`tem_saida` → agenda → `chatFound`); cala handoff; atende
   virgem/Evolution cega e multi-msg rápida. Aplica a tranca também quando o
   backend manda `acao=cliente` (não só no fallback).
10. `Se resposta controle1` manda menus da equipe direto ao WhatsApp; clientes
    seguem para a IA.
11. `AI Agent1` usa system message com **prioridade da `mensagem_atual`**, jornada
    **fotos ou simulação** no mesmo convite (moto clara), **sem insistir** em
    recusa, e user prompt com **`historico_recente`** (CRM) + flags de anúncio.
12. `Aguardar 40s cliente1` — espera **40 segundos** antes de mandar a resposta
    (tom mais humano). Só no caminho da IA; menus da equipe e fotos de estoque
    não passam por este Wait.
13. `Responder WhatsApp1` envia a resposta.
14. `Registrar saida do bot1` grava no CRM a mensagem enviada ao cliente.

## O caminho da equipe e das fotos

- Mensagem no grupo autorizado: `Rotear grupo de estoque1`.
- Foto no grupo: `Salvar foto no estoque1`.
- `Foto deve responder1` evita confirmação quando a foto foi ignorada.
- `Responder cadastro de foto1` confirma somente uma foto aceita.
- Menus e respostas de controle não passam pela IA.

Essa separação é intencional: impede que uma mensagem comum altere o estoque.

## O Agent e suas ferramentas

O texto de comportamento fica em:

`AI Agent1` → `Options` → `System Message`

Ferramentas conectadas:

| Ferramenta | Responsabilidade |
|---|---|
| `consultar_estoque1` | Consulta estoque real e guarda uma moto quando a busca específica retorna uma única opção. |
| `enviar_foto_veiculo1` | Envia até quatro fotos usando somente o ID retornado pelo estoque. |
| `simular1` | Recupera a moto escolhida, valida CPF/nascimento/entrada, cria o lead qualificado e avisa o vendedor. |
| `solicitar_handoff1` | Pausa o bot, avisa o vendedor ativo e envia o link do CRM quando o cliente pede uma pessoa ou ocorre uma falha real. |
| `cadastrar_veiculo1` | Cadastra veículo quando a mensagem veio da equipe autorizada. |

O modelo usado fica em `Google Gemini Chat Model1`. A memória fica em
`Memoria da conversa1` e guarda as últimas 20 mensagens da sessão.

## Regras da simulação

- Antes de uma moto específica ser escolhida, o bot pergunta somente qual moto o
  cliente quer simular.
- CPF, nascimento e entrada só são pedidos depois da escolha.
- Uma busca específica com resultado único guarda os dados internos da moto.
- Uma mensagem com CPF, data e entrada é normalizada pela ferramenta.
- A placa é interna e nunca deve ser pedida ao cliente.
- O lead nasce somente dentro de `simular1`, já como `qualificado`.
- O bot continua ativo e o vendedor recebe um aviso sem CPF ou nascimento.
- No handoff explícito, o bot é pausado e o vendedor recebe o link da conversa.

## Onde mexer

| Mudança desejada | Local |
|---|---|
| Tom de voz, identidade e regras **de uma loja** | config da loja no `chatbot-api` (`app/agente_prompt.py` gera o texto) |
| Operação do atendimento (vale para toda loja) | `AI Agent1` → `System Message` |
| Núcleo Revy (o que nenhuma loja edita) | `chatbot-api/app/agente_prompt.py`, `NUCLEO_REVY` |
| Primeira mensagem / prioridade do pedido | seções `prioridade absoluta` e `primeiro contato` |
| Histórico no prompt | registrar (`historico_recente`) + template `text` do Agent |
| Tranca virgem / handoff / fail-open | `Gate somente nao salvos1` (`atendeLeadVirgem`) + backend `decidir_roteamento` |
| Comportamento de anúncio | seção `mensagem de anúncio` |
| Busca e seleção da moto | `consultar_estoque1` |
| Criação do lead e aviso ao vendedor | `simular1` |
| Resposta final no WhatsApp | `Responder WhatsApp1` |
| Filtro do número de teste | constantes no início de `build_test_workflow.js` |
| Reativar áudio no futuro | criar um ramo depois de `Extrair1`; não misturar com o caminho de texto |
| Teste da tranca sem rede | `node n8n/test_gate_somente_nao_salvos.js` |

## Arquivos do workflow

- `workflow-ai-nao-salvos.json`: **oficial de produção** — nome `WhatsApp IA - Somente Nao Salvos`,
  webhook `whatsapp-ai`, contatos não salvos + grupo de estoque, **jornada de catálogo**
  (fotos antes de simular). Placeholders de secret no prepare-workflow.
- `build_test_workflow.js`: gera a cópia restrita a partir do oficial (só freios de lab:
  1 telefone, sem grupos, webhook `whatsapp-ai-teste`).
- `workflow-teste-numero-autorizado.json`: cópia de teste gerada (não usar no número da loja).
- `validate_workflow.py`: protege as regras do fluxo oficial.
- `validate_test_workflow.py`: garante que o teste continue restrito.
- `fork_cloud_workflow.py`: **gera** o workflow do Modo 2 a partir do oficial. É aqui
  que se mexe no lado n8n do Modo 2 — nunca no JSON.
- `workflow-cloud.json`: saída do gerador (Modo 2, central Cloud API). **Não editar a
  mão**: o validador compara o arquivo com o que o gerador produz e sai `1` se divergir.
- `validate_workflow_cloud.py`: protege as regras do Modo 2 — sem segredo da Meta, sem
  resíduo de Evolution, assinatura no corpo cru e `instance` em toda chamada.

## Validar e publicar

Na raiz do projeto:

```powershell
python n8n\validate_workflow.py
node n8n\build_test_workflow.js
python n8n\validate_test_workflow.py
python n8n\fork_cloud_workflow.py        # Modo 2: regera o fork
python n8n\validate_workflow_cloud.py    # e confere que o JSON e o que o gerador produz
```

Para preparar e publicar o teste:

```powershell
& 'deploy\fly\3vm\prepare-workflow.ps1' -Mode test
& 'deploy\fly\3vm\upload-and-import-workflow.ps1' -Mode test
fly apps restart n8n2037
```

Sempre valide antes de publicar. O workflow de teste deve continuar limitado ao
número definido no gerador.

## Roteiro de teste

1. Envie uma saudação: deve apresentar a Vitor Motos.
2. Peça para ver motos: não deve criar lead.
3. Escolha uma moto específica.
4. Confirme que quer simular.
5. Envie CPF, nascimento e entrada juntos.
6. O bot não deve repetir a pergunta.
7. O CRM deve criar um lead `qualificado`.
8. O vendedor deve receber o aviso interno.
