# Plano #6 — Evoluções (roadmap)

> **Regra de produto:** toda evolução declara em qual produto vive e integra os demais somente por
> contrato. Nenhum item futuro pode transformar Portal, Catálogo ou Motor em dependência obrigatória
> do Chatbot Standalone.

> **Natureza deste documento:** diferente dos Planos #1–#5, este é um **roadmap** de evoluções
> futuras — cada item é um esboço de abordagem, não uma sequência de tarefas TDD. Quando um item
> for priorizado, ele vira um plano completo próprio (via a skill de escrita de planos).

**Origem:** recursos observados em uma plataforma de referência madura (prints do usuário) que
fazem sentido depois dos produtos-base relevantes estarem de pé.

**Princípio:** todos encaixam sem quebrar os contratos versionados de cada produto
(`/v1/simulacoes`, Chatbot API, Estoque API pública/privada e Portal). São extensões por adapter ou
evento, não acesso direto a bancos de dados vizinhos.

| Evolução | Produto proprietário | Integração opcional |
|---|---|---|
| Áudio/multimodal, auto-pausa, multi-agente | Chatbot | provedor de IA/transcrição |
| Score; drivers API/Playwright/agregador (híbrido) | Motor + UI credenciais no Portal | banco/parceiro/agregador |
| Cadastro de veículo por WhatsApp | Chatbot | Estoque API |
| Fotos e galeria | Estoque + Catálogo | storage de objetos |
| Funil, vendas, metas, campanhas | Portal | eventos do Chatbot/Estoque/Motor |

---

## E1 — Áudio / multimodal (transcrição)

**O que é:** cliente manda **áudio** (ou imagem) no WhatsApp e o bot entende.

**Por quê:** grande parte dos clientes de loja manda áudio; hoje o bot só lê texto.

**Abordagem:**
- No workflow `Bot`, após o Webhook, classificar o tipo da mensagem (`conversation` vs `audioMessage`).
- Se áudio: baixar o arquivo (a Evolution entrega base64/URL), enviar para uma API de transcrição
  (OpenAI Whisper ou equivalente) e usar o texto transcrito como `texto` no fluxo normal.
- Imagem/documento: enviar para um modelo multimodal (Claude com visão) e extrair o conteúdo.

**Onde pluga:** somente no Chatbot (Plano #2A), antes do gate de handoff.

**Esforço/risco:** médio. Custo por transcrição; latência maior.

**Gatilho:** quando clientes reais começarem a mandar áudio com frequência.

---

## E2 — Busca de score de crédito (enriquecimento)

**O que é:** antes de simular de verdade, consultar um **score/bureau** (ex.: DirectD, Serasa,
Boa Vista) a partir do CPF, como a plataforma de referência faz ("busca score" via `api v3.directd`).

**Por quê:** confirma na prática o que já sabíamos — **CPF + nascimento não bastam**. O score
define elegibilidade e afina a simulação real. É o passo que falta entre coletar dados e ter uma
oferta de banco confiável.

**Abordagem:**
- Novo endpoint no serviço: `POST /score` `{cpf}` → `{score, faixa, ...}`, chamando o provedor
  contratado. Mockável primeiro (igual ao motor).
- O motor real (híbrido API + Playwright + agregador opcional — ver Plano #1A) pode usar o score
  como entrada do driver.

**Onde pluga:** Motor + opcionalmente Chatbot. O contrato de simulação pode ganhar `score`
opcional sem quebrar quem não usa. Credenciais de portal: UI no Portal (#3A Task 9A).

**Esforço/risco:** médio-alto. Exige **contrato com o bureau** (custo por consulta, LGPD reforçada).

**Gatilho:** depois do Plano #1A, junto do primeiro driver real e somente com contrato/base legal.

---

## E3 — Auto-pausa ao detectar o atendente

**O que é:** completar o handoff (Plano #2A Task 7) para **pausar sozinho** quando o atendente
responde manualmente pelo WhatsApp — sem precisar clicar no portal.

**Por quê:** é o "Parar Resposta Agent" da referência; mais natural que o botão.

**Abordagem:**
- Detectar mensagens `fromMe = true` no payload da Evolution.
- Deduplicar: distinguir a resposta **do próprio bot** (enviada via API) da resposta **do atendente**
  (digitada no app). Estratégia: registrar toda mensagem que o bot envia (hash/ID) e, ao receber um
  `fromMe`, se **não** casar com uma enviada pelo bot → é o atendente → `PATCH bot_ativo=false`.
- Opcional: reativar o bot automaticamente após X horas de silêncio do atendente.

**Onde pluga:** Chatbot (Plano #2A) e seus dados de conversa/handoff.

**Esforço/risco:** médio. A deduplicação `fromMe` é a parte chata (exige rastrear os envios do bot).

**Gatilho:** quando o handoff manual do portal já estiver em uso e incomodar clicar.

---

## E4 — Roteador de intenção / multi-agente

**O que é:** um "Direcionamento" (como na referência) que classifica a intenção e manda para
agentes especializados: `financiamento`, `vendas`, `test_drive`, `grupos`, etc.

**Por quê:** conforme o bot cresce, um único prompt fica sobrecarregado; separar melhora qualidade.

**Abordagem:**
- Nó de classificação (LLM) logo após o buffer → `Switch` por intenção → sub-workflows por agente
  (n8n "Execute Workflow").
- Cada agente é um workflow com seu próprio prompt e ferramentas.

**Onde pluga:** Chatbot (Plano #2A) vira um roteador + N sub-workflows. Outros produtos intactos.

**Esforço/risco:** médio-alto (mais workflows para manter).

**Gatilho:** quando houver ≥3 fluxos distintos bem definidos (hoje o financiamento sozinho justifica 1 agente).

---

## E5 — Cadastro de veículo via WhatsApp

**O que é:** o dono/vendedor **adiciona um veículo ao estoque mandando mensagem** para o bot
(equivalente ao "Adiciona Veículo BD - Whatsapp" da referência).

**Por quê:** cadastrar estoque sem abrir o portal, direto do celular na loja.

**Abordagem:**
- Lista de números autorizados (donos/vendedores).
- Se a mensagem vier de um número autorizado e for um comando de cadastro (ex.: foto + "CG 160 2023
  16000"), um agente/tool chama `POST /veiculos` com `loja_id` do remetente.
- Foto do WhatsApp → upload (ver E6) → `foto_url`.

**Onde pluga:** `Bot` (nova ferramenta `adicionar_veiculo`, restrita por número) + `/veiculos` (já existe).

**Esforço/risco:** médio (parsing do comando + autorização).

**Gatilho:** quando o cadastro pelo portal for gargalo para a operação.

---

## E6 — Upload real de fotos + página de detalhe do veículo

**O que é:** hoje `foto_url` é um link manual. Evoluir para **upload** de fotos (portal e/ou
WhatsApp) e uma página de detalhe na vitrine (`/l/{loja_id}/v/{id}`) com galeria.

**Abordagem:**
- Armazenamento de objetos (S3/MinIO/Cloudflare R2) ou volume; guardar a URL em `foto_url`
  (ou uma tabela `veiculo_fotos` para múltiplas).
- Página de detalhe no catálogo público (Plano #5A).

**Onde pluga:** Estoque API é dona de `veiculo_fotos`; Catálogo apenas consome URLs/metadados;
Portal pode oferecer uma interface cliente da API.

**Esforço/risco:** médio.

**Gatilho:** quando a vitrine (Produto C) for pra produção de verdade.

---

## E7 — Analytics avançado e projeção de simulações

**O que é:** após os Planos #3A/#3B, projetar no Portal o estado resumido das simulações e criar
análises avançadas de coorte, tempo por etapa e reconciliação. O Motor continua dono da simulação;
o Portal guarda referência/projeção, não copia payload pessoal bancário.

**Onde pluga:** eventos/API do Motor → projeção idempotente do Portal.

**Esforço/risco:** baixo-médio.

**Gatilho:** quando o volume tornar relatórios operacionais dos Planos #3A/#3B insuficientes.

---

## E8 — Atribuição e retorno de campanhas

**O que é:** evoluir campanhas do Plano #3B para importar custos e comparar origem, lead, venda e
lucro bruto por canal, mantendo `first_touch` e `last_touch` explícitos.

**Onde pluga:** Portal. Catálogo e Chatbot apenas emitem UTMs/eventos padronizados.

**Gatilho:** quando houver campanhas reais com custos e volume suficiente para decisão.

---

## E9 — Gestão de redes sociais e tráfego

**O que é:** conectores para cadastro/agendamento de publicações e plataformas de anúncio, além de
alertas e recomendações. São módulos/add-ons separados, não parte obrigatória do Dashboard.

**Pré-requisito:** E8 funcionando; sem atribuição confiável, automação de tráfego gera atividade sem
provar impacto em venda.

**Onde pluga:** produto/add-on de Marketing → API de campanhas do Portal.

---

## Ordem sugerida de ataque (depois do MVP)

1. **E3** (auto-pausa) — completa o handoff standalone.
2. **E1** (áudio) — grande ganho de UX real.
3. **E6** (upload real de fotos) — quando o Catálogo entrar em produção.
4. **E8** (atribuição de campanhas) — antes de automatizar marketing.
5. **E2** (score) — junto do primeiro fluxo bancário real e contrato com bureau.
6. **E7** (analytics avançado) — quando relatórios básicos não bastarem.
7. **E5 / E4** (cadastro via WhatsApp / multi-agente) — quando a operação pedir.
8. **E9** (redes sociais e tráfego) — somente após medir origem → lead → venda.
