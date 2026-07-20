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
3. Canal: Meta ou Google.
4. `utm_campaign`: `seminovos-julho` (igual ao link).
5. Salve.

## 4. Lançar o custo da mídia

No **detalhe da campanha**, lance o gasto (ex.: R$ 800 da semana, copiado do Ads Manager).

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

## 6. Checklist se os números “não batem”

| Sintoma | Causa comum |
|---|---|
| Ads tem 50 msgs, CRM tem 20 leads | Link do anúncio sem UTM ou WA direto no bio |
| Lead sem campanha | `utm_campaign` diferente do cadastro (typo) |
| Venda sem campanha no ROI | Venda sem `lead_ref` ou confirmada antes do match |
| ROAS “—” | Nenhum gasto lançado no período |

## 7. O que o Revy **não** faz

- Não cria/pausa anúncio na Meta/Google.
- Não importa gasto automaticamente (ainda).
- Não gerencia posts de Instagram (fora do core).

O Ads Manager **gasta e veicula**; o Revy **amarra à venda da moto**.
