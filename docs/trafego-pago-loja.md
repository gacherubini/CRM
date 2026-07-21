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

## 4. Lançar o custo da mídia

Você pode lançar de três formas:

1. No **detalhe da campanha**, informe um gasto pontual.
2. Em **Campanhas → Lançar gastos**, preencha todas as campanhas ativas de uma vez; valor vazio pula a linha.
3. Na mesma tela, baixe e importe o **modelo CSV Revy** (`utm_campaign;valor;referencia;nota`). Linhas válidas entram e erros aparecem no resumo. O arquivo não cria campanhas automaticamente.

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

## 8. O que o Revy **não** faz

- Não cria/pausa anúncio na Meta/Google.
- Não importa gasto automaticamente (ainda).
- Não gerencia posts de Instagram (fora do core).

O Ads Manager **gasta e veicula**; o Revy **amarra à venda da moto**.
