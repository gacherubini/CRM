# Handoff — loop e2e WhatsApp loja teste (18/09/2026, noite)

Branch `handoff/e2e-18-09`. Objetivo do dono: bot da loja teste em loop real
até 100% — estoque, catálogo, simulação repassada ao vendedor, fotos,
follow-up e prompt injection. Áudio pausado por ordem do dono (texto primeiro).

## Números e dados (tudo teste, autorizado pelo dono)

- Cliente (Gabriel Brain): `+5551980336365`; a Meta entrega `from` SEM o 9:
  `555180336365` — tudo que lê conversa usa este.
- Chip loja teste: `+5519996631046`, `phone_number_id=1356659367525459`,
  WABA `1628109642104591`.
- Vendedor único ("1020"): `5551995941020`; inbound chega como `555195941020`.
- Dados do cliente: CPF `85486094000`, nasc `13/12/2002`, tem CNH.
- Harness: `/tmp/revy_e2e/` (+ cópia nesta branch em `e2e-loop/`, sem tokens).

## Placar (último run verde-parcial, `run-20260918-184132`)

| Caso | Estado |
|---|---|
| T1 abertura, T2 barra, T5 catálogo, T6 estoque+fotos | verdes |
| T8 simulação (CPF→nasc→CNH→oferta) | verde até `T8-oferta` |
| T8-vendedor (WhatsApp ao vendedor) | **vermelho** — template inexistente, janela fechava |
| T7 handoff, T9 imagem, T10 follow-up, T11 injection | não rodados (loop para no 1º vermelho) |
| T3/T3b/T4 áudio | pausados (dono) |

## O que foi achado e corrigido hoje

### 1. Vendedor nunca era notificado (bloqueante) — causa exata isolada

`enviar_oferta` falhava no template e o erro vinha como "404" genérico.
Depois do fix de log (§3), o corpo da Meta apareceu:

`(#132001) template name (chama_vendedor) does not exist in pt_BR`

Mais a janela de 24h do vendedor sempre fechada → 100% das ofertas caíam no
caminho pago inexistente. Duas saídas (dono já orientado):
- **atalho**: "oi" do 1020 para o chip abre a janela → interativa grátis;
- **definitivo**: criar `chama_vendedor` pt_BR na WABA `1628109642104591`
  (Utility, body com 1 variável `{{1}}`, 1 botão quick-reply "Peguei").

### 2. Aviso ao cliente não era persistido — corrigido (`9c72440`)

`disparar_handoff` mandava "já estou chamando um vendedor" pelo outbound
direto, sem `registrar_mensagem`: chegou no aparelho, mas não existe no banco
→ Portal com histórico pela metade + T8 "mudo". Agora persiste nos ramos
ofertado/aguardando e loga `oferta enviada ... envelope=`.
Prova em prod: `T8-4.txt` do run 184132 tem as duas mensagens.
Arquivos: `chatbot-api/app/handoff_gatilhos.py`,
`chatbot-api/tests/test_handoff_gatilhos.py`,
`test_fluxo_modo2_ponta_a_ponta.py`, `test_oferta_envio.py` (canal na fixture).

### 3. Erro Cloud sem corpo — corrigido (`9c72440`)

`CloudWhatsAppOutbound._post` engolia o corpo da Meta. Agora loga status +
corpo sanitizado e o corte de redação subiu de 5 para 7 dígitos para os
códigos de 6 dígitos da Meta (132001) sobreviverem.
Arquivo: `chatbot-api/app/whatsapp_outbound.py`, teste em
`chatbot-api/tests/test_cloud_outbound.py`.

### 4. Template PENDING derrubava o handoff com 500 — corrigido (`95da977`)

Envio da oferta virou best-effort com log (oferta aberta no CRM + retry na
reoferta), senão o cliente ouvia "não consegui registrar" para simulação
registrada. Arquivo: `chatbot-api/app/handoff_gatilhos.py`.

### 5. Foto no Modo 2 calava o agente — desviado no fork (`c2deb99`)

`enviar_foto_veiculo1` não existe no Modo 2 e o prompt mandava chamar:
agente girava até maxIterations e calava. Fork reescreve para link do
catálogo. Workflow ativo `wCloudMeta0001` (upd 19:45Z) conferido com a
reescrita. **Mas é probabilístico**: T6-fotos deu verde/vermelho/verde em
runs seguidos (18:15 ok, 18:35 mudo, 18:46 ok). Se repetir, o fix é um gate
determinístico antes do agente, não mais prompt.

### 6. Reset apagava a janela do vendedor — corrigido (harness)

`reset.sql` deletava TODAS as mensagens, então o "oi" do vendedor morria no
reset seguinte e a janela nunca estava aberta no T8. Agora preserva
inbound do vendedor (normalizado com/sem 9, conferido no banco).
Arquivo: `e2e-loop/reset.sql`.

### 7. T8 reescrito para o Modo 2 (harness)

O assert antigo (`notificacoes_operacionais='sent'`) é impossível no Modo 2
(sem grupo). Agora: oferta aberta via API + rastro `oferta enviada` no log
(`fly logs -n` grep pelo oferta id; falha explícita se "falha ao enviar").
Arquivo: `e2e-loop/cenarios.sh`.

### 8. Commits e deploy de hoje (main)

`172a18e` PATCH estado resolve loja pela instance ·
`c2deb99` fork desvia foto · `95da977` best-effort no envio ·
`9c72440` persiste aviso + erro Cloud (mapa regerado junto).
Suite chatbot-api: **686 passed**. `app2037` no ar conferido em `9c72440`
(pós-flight `verificar.py`; o 1º deploy foi sem `--build-arg GIT_SHA` e o
pós-flight reprovou — redeployado com carimbo).

## Pendências

1. **Dono**: mais um "oi" do 1020 para o chip (o anterior foi apagado pelos
   resets antigos; o reset novo preserva). Depois disso, loop deve passar T8.
2. **Dono**: criar template `chama_vendedor` (passo a passo já passado no chat).
3. Rodar loop até T7/T9/T10/T11 verdes; T6-fotos observado (flaky).
4. Áudio (T3/T3b/T4 + fallback) quando o dono liberar.
5. Reverter temporários do loop: allowlist + `dmPolicy disabled` na ponte.
6. Higiene (não bloqueia): banco do n8n com 365MB de executions; prune.

## Adendo 19/09 — o número do dono vira o vendedor da vez

Decisão do dono: `+5551980336365` (o mesmo aparelho que é o **cliente** do
loop) entra na `fila_vendedor` da loja teste. Consequências, todas queridas:

- **Ordem 0**, à frente do 1020, que fica intacto. O reset zera o
  `rodizio_ponteiro`, então a oferta de cada run sai para a ordem 0 — sem isso
  o dono nunca receberia.
- **A janela de 24h deixa de ser problema.** `janela_aberta`
  (`chatbot-api/app/oferta_envio.py:16`) procura inbound daquele número nas
  últimas 24h; como ele é o cliente, o próprio loop abre a janela. A oferta sai
  como **interativa**, e o template `chama_vendedor` deixa de bloquear o T8.
  Criar o template continua valendo para loja real — não para este loop.
- **Mesmo fio no WhatsApp.** Oferta e conversa de cliente chegam do mesmo
  número central, então os dois papéis dividem a mesma conversa no aparelho.
  Só o **clique** no botão vira comando de vendedor
  (`chatbot-api/app/main.py:786`); texto continua indo para o bot como lead.

### O que mudou no harness

- `cenarios.sh`: T8 ganhou `t8_esperar_peguei` + `t_reset T8-fim`. O reset do
  fim do cenário é o pedido do dono: **esperar a resposta do vendedor e só
  então limpar**. Resetar antes apagava a `oferta_lead` no meio do caminho.
  Timeout em `T8_PEGUEI_SECS` (`config.sh`, 300s), porque o "Peguei" é o único
  passo que só o aparelho faz.
- `reset.sql`: a guarda que preservava inbound de vendedor agora **exclui o
  cliente do loop**. Sem isso, pôr o número dele na fila transformava o reset
  em no-op justo na conversa que todo cenário zera.

### Falta aplicar em produção

O cadastro na fila não foi aplicado: escrita remota bloqueada na sessão que
escreveu isto. Roda uma vez, com `fly auth login` da conta Revy:

```bash
# macOS / Git Bash
fly ssh console -a app2037 < e2e-loop/fila-dono.sh
```

```powershell
# PowerShell: nao tem redirecionamento de entrada (`<` e reservado)
Get-Content e2e-loopila-dono.sh -Raw | fly ssh console -a app2037
```

Pela tela dá no mesmo: Loja → WhatsApp → Fila
(`portal-gestao/app/web/loja_whatsapp.py:640`), só que a tela exige que a
projeção de modo vinda do Control diga Modo 2 para o slug `teste`
(`loja_operacional_projecao`) — essa linha não foi conferida.

Vinculando o vendedor a uma pessoa da equipe da loja (`usuario_id`), o sino 1:1
do Portal também toca. Sem vínculo, só o WhatsApp — é o caso do 1020 hoje.

### Pendência que morre com isto

A pendência 1 ("mais um `oi` do 1020") só existia para abrir a janela do 1020.
Com a ordem 0 no dono, o T8 não passa mais pelo 1020.

## Retomar

```bash
# 1. n8n limpo + webhook de pé
fly apps restart n8n2037 && /tmp/revy_e2e/esperar-webhook.sh
# 2. loop inteiro de uma vez (memória n8n é instance:telefone; não fatiar)
cd /tmp/revy_e2e && CHIP=+5519996631046 SEED_OK=1 ./run.sh [T1..T11]
# 3. placar
L=$(ls -td /tmp/revy_e2e/logs/run-* | head -n 1); grep -h "PASSOU\|FALHOU\|PARADA" "$L"/loop.log
```

Pré-requisitos: `fly auth login` (conta Revy), `./provisionar.sh` uma vez
(token em `.token`, fora do git), ponte WhatsApp com allowlist do teste.

**Onde o loop roda.** Ele precisa do `openclaw` no PATH — é a ponte que envia
pelo WhatsApp do dono. Na máquina Windows dele o `openclaw` não está instalado,
então o loop inteiro é trabalho de Mac por enquanto; `run.sh` agora falha na
hora, com mensagem, em vez de pintar todo cenário de vermelho por timeout.
O oráculo deixou de chamar `python3` direto: o `python3` do PATH no Windows é o
stub da Microsoft Store, que existe, **sai 49 e imprime nada**. `config.sh`
escolhe o interpretador testando execução (`$PY`), não presença.
Sem áudio até o dono liberar: TODOS em `run.sh` já exclui T3/T3b/T4.

### Run 19/09 01:02 — T8-vendedor era vermelho falso, não produto

Placar: T1, T2, T5, T6 (+fotos), T8 até `T8-oferta` verdes; `T8-vendedor`
vermelho com `T8-envio.log` vazio — e a oferta chegou no aparelho do dono.
Causa: o assert procurava `oferta enviada ... envelope=` (`logger.info`) no
`fly logs`, mas o root em produção é WARNING (uvicorn sem `--log-level`, sem
`basicConfig` no código), então a linha do sucesso nunca é emitida. A de falha
(`logger.exception`, ERROR) aparece — foi assim que o mesmo pipeline pegou o
template inexistente em 18/09. Defeito no oráculo do teste, não no produto.
Fix no harness: T8-vendedor agora só reprova no rastro explícito de falha; a
entrega é provada pelo `T8-peguei` (oferta `travada` via API).

Run `run-20260919-012044` repetiu o padrão com outra cara: `T8-oferta` vermelho
com `[]` — a oferta nasceu 04:29:43 e foi travada 04:29:51, 1s antes da
consulta `aberta` (04:29:52). O dedo do dono venceu o oráculo por 1s. Fix:
T8-oferta sonda `travada` antes de qualquer veredito; travada prova entrega +
aceite e pula direto ao reset de fim.
