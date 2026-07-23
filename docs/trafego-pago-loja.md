# Guia da loja — tráfego pago no Revy

Como medir se o anúncio **pagou a conta**: anúncio → UTM → lead → venda → ROI.

## 1. Configurar Pixel (uma vez)

1. No Portal: **Tráfego** → informe **Pixel ID** + **token CAPI**.
2. No serviço do **Catálogo**, env `META_PIXEL_ID` = o mesmo Pixel ID.
3. Confirme eventos: PageView / Lead no site, Purchase ao **confirmar venda**.

## 2. Criar campanha no Ads com UTM

Exemplo de URL do catálogo:

```text
https://SEU-CATALOGO/l/sua-loja/veiculos/ID-VEICULO?utm_source=instagram&utm_medium=paid&utm_campaign=seminovos-julho
```

**Regra de ouro:** o valor de `utm_campaign` deve ser **idêntico** ao cadastrado no Revy (sem espaços; use hífen).

## 3. Cadastrar a campanha no Revy

1. Menu **Campanhas** → **Nova campanha**.
2. Nome interno (ex.: “Seminovos Meta Julho”).
3. Canal: Meta, Google, TikTok, OLX, Marketplace, indicação, orgânico ou outro.
4. `utm_campaign`: `seminovos-julho` (igual ao link).
5. Salve.

## 4. Gasto da mídia (automático Meta ou manual)

### 4.1 Meta — gasto automático (recomendado)

1. No Portal: **Tráfego** → bloco **Gasto automático (Marketing API)**.
2. Informe o **Ad Account ID** (`act_…` ou só números).
3. Cole um token com permissão **`ads_read`** (System User no Business Manager ou token long-lived).  
   **Não** é o mesmo token do CAPI (conversões).
4. Em cada **campanha Revy**, preencha o **ID da campanha no Meta Ads** (Gerenciador → campanha → copiar ID).
5. Clique **Sincronizar gastos agora (7 dias)** para forçar agora, **ou** aguarde o **job automático** do Portal (padrão: a cada 24h, olha os últimos 3 dias).

O Revy grava o spend como origem **Meta**. Re-sincronizar **atualiza** valores da API; **não** sobrescreve gasto **manual** do mesmo dia.

Ops (deploy): `PORTAL_META_SPEND_SYNC_ENABLED=1` (padrão), intervalo
`PORTAL_META_SPEND_SYNC_INTERVAL_SECONDS` (86400), janela
`PORTAL_META_SPEND_SYNC_JANELA_DIAS` (3). Endpoint opcional de cron:
`POST /internal/jobs/meta-spend-sync` com header `X-Job-Token: $PORTAL_META_SPEND_JOB_SECRET`.

### 4.2 Manual (fallback)

Use se a campanha não for Meta, ou para correção:

1. No **detalhe da campanha**, informe um gasto pontual.
2. Em **Campanhas → Lançar gastos**, preencha todas as campanhas ativas de uma vez; valor vazio pula a linha.
3. Na mesma tela, baixe e importe o **modelo CSV Revy** (`utm_campaign;valor;referencia;nota`).

Sem gasto, o ROI ainda mostra leads/vendas, mas CPL/CPA/ROAS ficam em “—”.

## 5. Ler o ROI

Menu **ROI** (ou Tráfego → ROI):

| Métrica | Significado |
|---|---|
| **CPL** | Gasto ÷ leads com match da campanha |
| **CPA** | Gasto ÷ vendas atribuídas |
| **ROAS** | Faturamento ÷ gasto (ex.: 5x = R$5 de venda por R$1 de ads) |

- **Last touch** (padrão): última UTM do lead.
- **First touch**: primeira UTM gravada.

## 6. Ler o bloco Resultados

A **Visão geral** do dono/gerente resume os últimos 7 dias ou o mês atual:

- gasto, leads atribuídos, motos vendidas e ROAS;
- resultado por canal e melhor campanha;
- alertas de CAPI, configuração, vendas sem campanha e campanhas sem gasto;
- checklist “Medindo de verdade?” até o primeiro Purchase entregue.

Se o chatbot estiver offline, leads aparecem como indisponíveis; gastos e vendas locais continuam visíveis. ROAS “—” significa que falta gasto no período, não resultado zero. Clique na melhor campanha para abrir gastos, funil e vendas atribuídas.

## 7. Checklist se os números “não batem”

| Sintoma | Causa comum |
|---|---|
| Ads tem 50 msgs, CRM tem 20 leads | Link do anúncio sem UTM ou WA direto no bio |
| Lead sem campanha | `utm_campaign` diferente do cadastro (typo) |
| Venda sem campanha no ROI | Venda sem `lead_ref` ou confirmada antes do match |
| ROAS “—” | Nenhum gasto lançado no período |

## 8. Click-to-WhatsApp (CTWA)

Anúncio que abre o WhatsApp **direto** (sem catálogo):

1. No Ads, use destino WhatsApp.
2. Na mensagem pré-preenchida, inclua o código da campanha Revy, ex.: `Cód: RV-JUL`.
3. Na campanha Revy, preencha **Código CTWA** = `RV-JUL` e/ou o **ID da campanha Meta**.
4. Quando o cliente mandar a 1ª mensagem, o Chatbot grava origem `meta_ctwa` (e `ctwa_clid` se a Evolution enviar).
5. Ao **confirmar a venda** com esse lead, o Portal envia **Purchase messaging** (CAPI) com o click id, além do CAPI web quando couber.

**Pixel** continua no catálogo (persona/remarketing). CTWA usa o token **CAPI** já configurado em Tráfego (mesmo Pixel ID).

Se o WhatsApp não trouxer click id, o **código na mensagem** ainda amarra o lead à campanha no ROI.

### Auditoria CTWA (dashboard)

Em **Tráfego → Auditoria CTWA** (menu **CTWA**):

- vê se **`ctwa_clid` chegou** (sim/não + sufixo);
- ids de campanha/ad, código da mensagem, se o lead foi atribuído;
- telefone só mascarado (`***1234`).

Logs do Chatbot: linha `ctwa_auditoria … clid=sim|nao` (sem PII completo).  
Para registrar **toda** mensagem inbound (mesmo sem sinal): env `CHATBOT_CTWA_AUDIT_ALL=1`.

### Auditoria Pixel / CAPI (chaves de match)

Em **Tráfego → Auditoria Pixel** (menu **Pixel**):

- **config_salva** — Pixel ID (sufixo), toggles PageView/Lead/Purchase, se há test code;
- **purchase_web** / **purchase_messaging** — quais chaves foram montadas (`ph`, `em`, `fbclid`/`fbc`, `ctwa_clid`, `external_id`);
- **envio_outbox** — se a Meta aceitou (`delivered`) ou falhou (HTTP).

Logs do Portal: linha `pixel_capi_auditoria … ph=sim|nao fbclid=…`.

## 9. O que o Revy **não** faz

- Não cria/pausa anúncio na Meta/Google.
- Não puxa gasto do **Google** Ads (só Meta, se configurado).
- Não gerencia posts de Instagram (fora do core).

O Ads Manager **gasta e veicula**; o Revy **amarra à venda da moto**.
