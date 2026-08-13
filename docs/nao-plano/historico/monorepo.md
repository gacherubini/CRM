# Histórico — monorepo

Contexto que saiu do `README.md` da raiz.

## Roadmap por fases (entregas concluídas)

- [x] **Fundação** — domínio, contratos v1, multi-loja, papéis e segurança (Plano #0).
- [x] **Chatbot + n8n** — API, handoff, E3/E5, tools, sim mock e real.
- [x] **Estoque + Catálogo + Portal** — CRUD, vitrine, CRM vendedor, 9A financeiras.
- [x] **Vendas / metas / CSV / E10 Pixel** — + campanhas + ROI (E8), 2026-07-20.
- [x] **Motor multi-banco** — Santander, Fontecred, Bradesco, Pan portal LIVE; fan-out;
  warm session teto 2.
- [x] **Deploy Fly 3-VM** — `suite-pg` + `evolution2037` + `app2037`; `motor2037`
  Playwright on-demand.
- [x] **Roteamento WA 3 casos** — só contato novo recebe IA; equipe em modo cadastro.
- [x] **#3B Task 4 + event bus** — eventos/tempos, UI do funil e adapter Meta.
- [x] **Revy Tráfego Fase 3** — banco/Alembic próprios, projeção de vendas e outbox
  criptografado Portal → Revy; CAPI assíncrona e isolada por loja.
- [x] **Revy Control/Loja lean** — shells, RBAC, prontidão, operação Google Ads e números
  multi-WhatsApp com QR efêmero.
- [x] **Atendimento humano na Loja** — lista unificada, workspace de chat, envio de texto,
  handoff, polling com cursor `after_id`; Perfil/troca de senha.
- [x] **Mídia WhatsApp backend** — áudio efêmero; foto automática WhatsApp → Estoque →
  Catálogo; lote por sessão; envio da capa ao cliente.
- [x] **Piloto flags Loja em prod** — shell + entitlements + atendimento + WhatsApp Loja.

Fila pendente vive em `docs/referencia-viva/contexto-compacto.md` → "Prioridades independentes".

## Fluxo conversacional detalhado (contato novo)

1. **Saudação + identificação do interesse**; consentimento explícito pode ser registrado
   quando informado, sem bloquear o atendimento.
2. **Qual moto** → modelo, ano, valor aproximado.
3. **Condições** → valor de entrada, prazo desejado (meses).
4. **Dados pessoais** → nome completo, CPF, data de nascimento *(renda opcional)*.
5. **Validação** → CPF (dígito verificador), data real, idade ≥ 18.
6. **Confirmação** → resume tudo e pede "confirma?".
7. **Dispara o motor internamente** → a resposta financeira não volta ao cliente pelo bot.
8. **Handoff automático** → pausa o bot e chama um vendedor.
9. **Fechamento** → o bot avisa que o vendedor trará o resultado; parcelas/taxas ficam no
   Portal.

**Validações:** CPF com cálculo de dígito verificador (rejeita sequências inválidas); data
existente com idade mínima 18; valores como "20 mil"/"R$ 20.000"/"20000" → 20000.

## Proteções de resposta do WhatsApp

- Eventos sem horário válido, com mais de **5 minutos** ou mais de **2 minutos no futuro**
  são descartados antes de qualquer chamada à IA.
- O caminho do cliente espera **40 segundos**, agrupando mensagens consecutivas. Antes de
  responder, o n8n pergunta ao Chatbot se aquela ainda é a entrada mais recente.
- Só a última mensagem recebida pode gerar resposta. Se o cliente escreveu novamente ou a
  última mensagem já é uma saída da loja, a execução antiga termina sem responder.

## Fallback temporário — estoque digital incompleto

Enquanto nem todas as motos estiverem cadastradas, uma busca específica sem resultado não
encerra a conversa. O nó isolado `TEMP continuar sem estoque1`:

1. preserva o modelo/ano procurado;
2. **não oferece nem envia fotos** e não inventa preço ou disponibilidade;
3. oferece apenas verificar uma simulação;
4. após o aceite, coleta somente CPF, nascimento e entrada que ainda faltarem;
5. cria o lead qualificado, avisa a equipe para fazer a simulação humana e pausa o bot.

Esse caminho não chama o motor automático, porque não existe veículo/preço confiável no
estoque. A implementação removível está concentrada no nó acima e nos blocos marcados
`[TEMP_ESTOQUE_INCOMPLETO_INICIO]` / `[TEMP_ESTOQUE_INCOMPLETO_FIM]` do prompt e da
descrição de `consultar_estoque1`.

**Para retirar quando o estoque estiver completo:** exclua o nó e sua conexão `ai_tool`,
remova os dois blocos marcados, regenere o workflow de teste com
`node n8n/build_test_workflow.js` e ajuste os validadores para 29 nós. O fluxo permanente
`simular1` não precisa ser alterado.

Antes de publicar/reativar:

```bash
node n8n/test_fallback_estoque_temporario.js
python3 n8n/validate_workflow.py
python3 n8n/validate_test_workflow.py
```

## Estratégia por banco

A loja **já tem acesso ao portal do lojista dos 5 bancos**, então o caminho do motor real
é **RPA** (automatizar os portais com Playwright). Agregador pago fica como plano B.

| Banco | Estado no Motor | Estratégia |
|---|---|---|
| **Santander** (Aymoré) | LIVE Playwright | Portal lojista |
| **Fontecred** | LIVE Playwright | Portal + warm session |
| **Bradesco** (Turbo) | LIVE Playwright | Portal lojista |
| **Pan** | LIVE dual-path | Portal go!PAN (default) + API se config completa |
| **BV** | backlog | API parceiro como upgrade futuro |

Mapa de campos e decisões:
`docs/referencia-viva/planos/2026-07-13-plano1a-task12-bancos-reconhecimento.md`.

## Critérios de aceite do lab (3-VM)

1. Evolution `loja1` (ou instância ativa) state `open`.
2. WhatsApp **contato novo** (`isSaved=false`) → resposta IA via n8n/chatbot.
3. Contato **já salvo** e não autorizado → **sem** resposta de bot.
4. Grupo selecionado: `menu` abre as opções; cadastro e fotos alimentam Estoque → Catálogo.
5. Imagem privada ou enviada em outro grupo → nenhuma resposta e nenhum cadastro.
6. Portal login + listagem básica + Acessos bancos (com `MOTOR_ENCRYPTION_KEY`).
7. Simulação **mock** 2xx sem subir worker Playwright.
8. Always-on machines started; workers Playwright stopped fora de job.
9. Health agregado: `https://app2037.fly.dev/healthz`; Revy:
   `https://app2037.fly.dev/trafego/health/ready`.
