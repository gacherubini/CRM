# Plano — anúncio rastreável → Revy → WhatsApp

> **Status 2026-07-21: PRONTO PARA IMPLEMENTAÇÃO.**
> Escopo: fechar as lacunas do fluxo anúncio de veículo → captura de atribuição → redirecionamento
> ao WhatsApp → lead atribuído no Revy. Não reimplementa campanhas, ROI, Pixel/CAPI nem o funil
> `CAT-*` que já existem.

**Eixo:** A · Demo/WhatsApp + C · medição de tráfego, em uma entrega transversal e isolada.
**Depende de:** Catálogo Público, Chatbot API, Estoque publicado e webhook WhatsApp operacional.
**Não inclui:** criar ou pausar anúncios, importar gasto da Meta, prometer atribuição causal ou ocultar
coleta de dados exigida por lei/política.

## Objetivo

Oferecer dois destinos oficiais para cada anúncio de moto:

1. **Direto:** uma URL do domínio do Catálogo registra o clique e responde `302` para `wa.me`.
2. **Com página:** a URL abre o detalhe da moto; o CTA registra o clique e abre o WhatsApp.

Nos dois casos, o Revy deve guardar veículo, UTMs e click IDs antes de abrir o WhatsApp. Quando o
cliente enviar a mensagem predefinida com a referência `CAT-*`, o Chatbot deve associar o telefone
ao clique pendente e criar/enriquecer o lead com first/last touch.

```text
Anúncio da moto
  → catalogo.../interesse/{veiculo}?utm_*     (direto)
  ou catalogo.../veiculos/{veiculo}?utm_*    (com página)
  → interest_events + outbox
  → 302 wa.me com veículo + CAT-*
  → mensagem recebida pela Evolution/n8n
  → Chatbot correlaciona CAT-* + telefone
  → lead no Revy com veículo, campanha e click IDs
```

## Diagnóstico do estado atual

| Parte | Estado | Evidência |
|---|---|---|
| Detalhe copia `utm_*`, `fbclid` e `gclid` para o CTA | Feito | `catalogo-publico/app/main.py::vehicle_detail` |
| Rota de interesse grava evento e redireciona ao `wa.me` | Feito | `catalogo-publico/app/main.py::register_interest` |
| Outbox entrega `catalog.interest_clicked` | Feito | `catalogo-publico/app/events.py` + `outbox.py` |
| Chatbot ingere evento de catálogo com idempotência | Feito | `POST /v1/integracoes/catalogo/interesses` |
| Mensagem com `CAT-*` vincula telefone, veículo e touch | Feito | `chatbot-api/app/servico.py::_correlacionar_catalogo` |
| Corrida “mensagem antes da outbox” é fechada depois | Feito | `_correlacionar_atribuicao_tardia` |
| Vitrine preserva tracking ao abrir um card | **Lacuna** | `storefront.html` monta o `href` sem query string |
| Filtros e paginação preservam tracking | **Lacuna** | `page_url` e o form só carregam filtros de estoque |
| Deploy 3-VM liga Catálogo → Chatbot por padrão | **Lacuna** | `fly.app.toml`/`env.example` não declaram `CATALOGO_EVENTS_URL`; token não está documentado no bundle |
| Saúde/observabilidade acusa atribuição desligada | **Lacuna** | `/health/ready` verifica estoque e SQLite, não o transporte de eventos |
| Webhook usa metadados nativos de Click-to-WhatsApp | **Não suportado** | n8n extrai texto/telefone, mas descarta `referral`/`externalAdReply` se o provedor os enviar |

## Decisões de produto e arquitetura

### 1. Link canônico por moto

Para abrir o WhatsApp imediatamente:

```text
https://catalogo.exemplo/l/{loja}/interesse/{veiculo}
  ?utm_source=meta
  &utm_medium=paid_social
  &utm_campaign=fan-160-julho
  &utm_content=video-a
```

Para usar a página de detalhe antes do WhatsApp, trocar `/interesse/` por `/veiculos/`.

- Cada anúncio de moto aponta para o ID real do Estoque.
- `utm_campaign` deve bater com a campanha cadastrada no Portal após a normalização já existente.
- A URL final do `wa.me` não carrega UTMs; elas ficam no servidor do Catálogo.
- A mensagem mantém `CAT-*`. O código pode ser apresentado como “Referência do atendimento”, mas
  não pode ser removido enquanto não existir correlação equivalente e testada pelo provedor.
- Link direto para `wa.me` continua permitido operacionalmente, mas deve ser rotulado como **não
  atribuível** no guia: o Revy não observa esse clique.

### 2. O que é capturado em cada momento

No clique, o sistema conhece campanha, criativo, veículo, horário e click IDs. Não conhece o telefone.
O telefone só entra quando a pessoa envia a mensagem e o webhook do WhatsApp chega. Clique pendente
não deve ser contado como lead; essa separação atual permanece.

### 3. Privacidade e segurança

- Não adicionar telefone, cookie anônimo ou token de serviço ao payload público/browser.
- Continuar limitando e sanitizando parâmetros de tracking no servidor.
- Token Catálogo → Chatbot permanece somente em secret do runtime.
- “Sem o usuário perceber a UTM” significa remover parâmetros técnicos da URL final do WhatsApp;
  não significa esconder avisos de privacidade ou contornar consentimento/políticas aplicáveis.
- Manter isolamento por loja e rejeição `403` quando o slug não pertence ao token.

### 4. Click-to-WhatsApp nativo

Não bloquear o MVP por metadados nativos da Meta. Primeiro fazer um **spike com payload real** da
Evolution para saber se chegam `referral`, `ctwa_clid` ou `externalAdReply`. Só então definir contrato.
Não inferir campanha por texto do anúncio nem por heurística.

Se o payload real trouxer identificadores estáveis:

1. preservar os campos na extração do n8n;
2. acrescentá-los de forma opcional ao webhook do Chatbot;
3. persistir o snapshot bruto mínimo permitido, sem tokens nem conteúdo desnecessário;
4. definir uma chave explícita de match com campanha/anúncio;
5. cobrir fallback sem metadados e deduplicação.

Essa fase é opcional e separada: o fluxo `CAT-*` continua sendo o caminho canônico.

## Entregas

### Fase A — preservar tracking em toda a vitrine (P0)

1. Criar helper único para extrair, limpar e serializar a allowlist:
   `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term`, `fbclid`, `gclid`.
2. Fazer `storefront` receber tracking separado dos filtros de estoque.
3. Propagar tracking nos links dos cards, paginação e submit dos filtros.
4. Não propagar parâmetros desconhecidos, vazios ou acima dos limites.
5. Manter codificação por `urlencode`; nunca concatenar query manualmente.

Arquivos previstos:

- `catalogo-publico/app/main.py`
- `catalogo-publico/app/templates/storefront.html`
- `catalogo-publico/tests/test_pages.py`

### Fase B — ligar Catálogo → Chatbot no deploy 3-VM (P0)

1. Declarar em `fly.app.toml`:

   ```toml
   CATALOGO_EVENTS_URL = "http://127.0.0.1:8001/v1/integracoes/catalogo/interesses"
   ```

2. Documentar `CATALOGO_EVENTS_TOKEN` em `deploy/fly/3vm/env.example` como secret obrigatório para
   atribuição e explicitar que deve pertencer à mesma loja.
3. Atualizar o runbook 3-VM com configuração, rotação e diagnóstico, sem imprimir o token.
4. Adicionar sinal operacional não sensível (`events_configured`) a `/version` ou a um endpoint de
   diagnóstico. Não derrubar a vitrine inteira quando o Chatbot estiver indisponível: outbox e retry
   continuam sendo o mecanismo de resiliência.
5. Emitir log claro uma vez no boot quando URL/token estiverem incompletos; nunca logar o token.

Arquivos previstos:

- `deploy/fly/3vm/fly.app.toml`
- `deploy/fly/3vm/env.example`
- `deploy/fly/3vm/README.md`
- `catalogo-publico/app/config.py`
- `catalogo-publico/app/main.py`
- testes de configuração/health do Catálogo

### Fase C — URL operacional e documentação da loja (P1)

1. Documentar os dois formatos de URL e quando usar cada um.
2. Mostrar que `utm_campaign` precisa coincidir com a campanha do Portal.
3. Incluir checklist de anúncio por moto: veículo publicado, URL testada, campanha cadastrada,
   outbox entregue e mensagem correlacionada.
4. Explicar que link `wa.me` direto não cria atribuição e que o telefone só chega após o envio.
5. Opcional: adicionar no detalhe da campanha um gerador/copiar-link que receba `veiculo_id`, usando
   `CATALOGO_PUBLIC_BASE_URL`; não hardcodear hostname de laboratório.

Arquivos previstos:

- `docs/trafego-pago-loja.md`
- `catalogo-publico/README.md`
- opcionalmente `portal-gestao/app/templates/campanhas/detalhe.html` e rota associada

### Fase D — robustez e observabilidade (P1)

1. Expor contagens sem PII: outbox pendente, entregue, morta e idade do item mais antigo.
2. Criar alerta operacional para outbox acumulada ou token ausente.
3. Garantir que clique/crawler sem mensagem nunca crie lead.
4. Manter `event_id` estável em retry e deduplicação Meta Pixel/CAPI já existente.
5. Definir retenção/limpeza de interesses pendentes sem apagar leads atribuídos ou trilha necessária.

### Fase E — spike CTWA nativo (P2, opcional)

1. Capturar um payload real e anonimizado de anúncio Click-to-WhatsApp em ambiente de teste.
2. Verificar o que a versão implantada da Evolution entrega ao n8n.
3. Registrar decisão: suportado com contrato e testes, ou não suportado pelo provedor atual.
4. Implementar somente em PR separada se houver identificador estável e benefício sobre `CAT-*`.

## Testes obrigatórios

### Catálogo

- Detalhe da moto copia todos os parâmetros permitidos para `/interesse/`.
- Card da vitrine preserva UTMs e click IDs.
- Filtrar e paginar não perde tracking.
- Parâmetro desconhecido não é propagado.
- Valores vazios, caracteres de controle e excesso de tamanho seguem a sanitização atual.
- `/interesse/` registra evento/outbox e responde `302` para o número correto.
- URL do `wa.me` contém moto e `CAT-*`, mas não contém UTM/token/cookie.

### Chatbot

- Outbox entregue antes da mensagem: correlação imediata.
- Mensagem recebida antes da outbox: correlação tardia.
- Reentrega do evento e da mensagem é idempotente.
- Código alterado/removido não atribui campanha por heurística.
- Código de outra loja não correlaciona.
- Segundo clique atualiza last touch sem apagar first touch.

### Deploy/contrato

- Validação automatizada garante que a URL interna de eventos está presente no manifesto 3-VM.
- Runtime com URL sem token informa `events_configured=false` sem expor segredo.
- Falha temporária do Chatbot deixa outbox pendente e a entrega posterior não duplica.

### E2E de homologação

1. Criar campanha de teste no Portal.
2. Abrir link de uma moto com UTMs conhecidas.
3. Confirmar `302` e mensagem com `CAT-*`.
4. Enviar a mensagem por um número de teste não salvo.
5. Confirmar no lead: telefone, `veiculo_ref`, `catalog_interest_ref`, first/last UTM e click ID.
6. Confirmar que ROI inclui o lead apenas depois do match e que nenhuma UTM aparece na conversa.

## Critérios de aceite

- [ ] Nenhuma navegação normal da vitrine perde os sete parâmetros de tracking permitidos.
- [ ] O deploy 3-VM configura a URL de eventos e documenta o token obrigatório por loja.
- [ ] O Catálogo informa de modo seguro quando a integração está desligada.
- [ ] Link direto do domínio Revy registra o clique e abre o WhatsApp em um redirecionamento.
- [ ] O usuário não recebe UTM na URL/mensagem final; recebe apenas a referência operacional.
- [ ] Um lead só nasce/enriquece após mensagem real com referência válida.
- [ ] First/last touch, veículo e isolamento multi-loja passam nos testes.
- [ ] O guia diferencia link Revy rastreável, página da moto, `wa.me` direto e CTWA nativo.
- [ ] Teste E2E real é registrado sem expor telefone, token ou payload pessoal em commits/logs.

## Ordem de implementação sugerida

1. **PR 1:** Fases A + B + testes — fecha perda de dados e ativa transporte no deploy.
2. **PR 2:** Fase C + gerador de link opcional — reduz erro operacional no Ads Manager.
3. **PR 3:** Fase D — métricas/alertas e retenção.
4. **PR 4 opcional:** Fase E — somente após evidência de payload CTWA real.

## Rollout e rollback

1. Publicar Catálogo + config 3-VM com token da loja.
2. Fazer smoke com campanha e moto de teste antes de trocar anúncios ativos.
3. Migrar um anúncio canário para o link Revy e acompanhar outbox/lead por 24 horas.
4. Migrar os demais anúncios por moto.
5. Rollback de URL: voltar o anúncio ao destino anterior. Os eventos já gravados permanecem para
   auditoria; não apagar volume/banco. Se o Chatbot falhar, manter Catálogo ativo e deixar retry da
   outbox trabalhar.

## Fora do escopo

- Capturar nome/telefone antes de o cliente enviar mensagem.
- Associar com segurança um `wa.me` direto que nunca passa pelo Revy.
- Sincronizar automaticamente gasto, campanha ou criativo pela Marketing API.
- Remover `CAT-*` antes de existir outra chave de correlação comprovada.
- Usar fingerprint, redirecionamento enganoso ou técnica para contornar privacidade/políticas.
