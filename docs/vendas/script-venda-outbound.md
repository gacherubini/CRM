# Script de venda — outbound frio (Revy/HEVY)

_Atualizado em 2026-08-09._ Roteiro consultivo (estilo SPIN: pergunta antes de pitchar)
para abordar **revendas de moto/seminovos a frio**. Deriva da
[análise de mercado e fit](../mercado/README.md).

**Princípio que rege o script:** a **atribuição** (anúncio → WhatsApp → venda → ROI) é a
única coisa que nenhum concorrente faz — então é ela que abre a porta. Financiamento e
estoque entram como reforço ("e ainda faz isso"), **nunca** como manchete: financiamento é
paridade (Credere/AutoConf/Boom já fazem) e estoque é commodity.

**ICP (filtro da etapa 0):** revenda de **moto/seminovos, porte médio (30–200 unidades)**,
que **já roda tráfego pago** e **financia venda**. Fora disso → nutrir, não abordar agora.

## Fluxo da conversa

```mermaid
flowchart TD
    Start(["📞 Abordagem outbound frio"]) --> Q0

    Q0{"0 · PRÉ-QUALIFICAÇÃO<br/>É ICP? moto/seminovos +<br/>anuncia pago + WhatsApp no anúncio"}
    Q0 -->|não| NUT["🌱 Nutrição / lista fria<br/>(não abordar agora)"]
    Q0 -->|sim| A1

    A1["1 · ABERTURA (gancho, não pitch)<br/>'Vi que vocês anunciam. Rapidinho —<br/>vocês conseguem dizer qual anúncio<br/>trouxe a última moto vendida?'"]
    A1 --> QA1{"Reação?"}
    QA1 -->|"curiosidade / interesse"| D
    QA1 -->|"'sem tempo' / seco"| PERM["Micro-permissão:<br/>'me dá 30 segundos'"]
    PERM -->|ok| D
    PERM -->|não| FUP

    D["2 · DESCOBERTA (amplifica a dor)<br/>3 sondas:<br/>• Atribuição: mede CPL/CPA por campanha?<br/>• Resposta: quanto demora às 22h/domingo?<br/>• Financiamento: quantos bancos, quanto tempo?"]
    D --> DOR{"Dor mais aguda?"}
    DOR -->|"não sabe a origem da venda"| P
    DOR -->|"perde lead por demora"| P
    DOR -->|"financiar é lento/manual"| P

    P["3 · DEMO / PITCH — o 'aha' da atribuição<br/>Anúncio → WhatsApp 24/7 white-label →<br/>financiamento fan-out → venda → ROI<br/>'Essa venda veio dessa campanha,<br/>custou X, ROAS Y'"]
    P --> OBJ{"Levantou objeção?"}
    OBJ -->|não| CLOSE
    OBJ -->|sim| OT{"Qual objeção?"}

    OT -->|"'já tenho sistema/CRM'"| R1["Não substituo, COMPLETO<br/>'Seu sistema te diz o ROAS por<br/>campanha? Não? Então não competimos.'"]
    OT -->|"'já uso Credere / já simulo'"| R2["A cunha é atribuição + WhatsApp<br/>Financiamento é bônus, sem<br/>comissão de agregador"]
    OT -->|"'tá caro'"| R3["Ancora em ROI<br/>1 venda a mais paga o mês;<br/>vs. pagar Credere (~R$690) sozinho"]
    OT -->|"'não dou login do banco'"| R4["Transparência<br/>Credencial cifrada, você controla;<br/>dá pra começar só com<br/>atribuição + WhatsApp"]
    OT -->|"'sem tempo agora'"| R5["Micro-compromisso<br/>15 min de demo com<br/>dados da própria loja"]

    R1 --> CLOSE
    R2 --> CLOSE
    R3 --> CLOSE
    R4 --> CLOSE
    R5 --> CLOSE

    CLOSE{"5 · FECHAMENTO (passo pequeno)<br/>'Me passa 1 campanha e eu te mostro<br/>a venda amarrada.' Demo/piloto<br/>com dados reais, sem compromisso"}
    CLOSE -->|aceita| WIN(["✅ Demo agendada / piloto"])
    CLOSE -->|hesita| FUP

    FUP["6 · FOLLOW-UP estruturado<br/>Cadência 7–10 toques em 30 dias<br/>(a própria dor que vendemos:<br/>não abandonar em 2–3)"]
    FUP -.->|"reconecta"| D

    classDef fase fill:#e8f5e9,stroke:#2e7d32,color:#14210f;
    classDef obj fill:#fff3e0,stroke:#ef6c00,color:#231402;
    classDef win fill:#2e7d32,stroke:#1b5e20,color:#ffffff;
    classDef cold fill:#eceff1,stroke:#607d8b,color:#1b2327;

    class Q0,A1,D,P,CLOSE fase;
    class OT,R1,R2,R3,R4,R5 obj;
    class WIN win;
    class NUT,FUP,PERM cold;
```

## Talk track (as falas, por bloco)

**0 · Pré-qualificação** — antes de gastar energia, confirme: anuncia pago? é moto/seminovos?
tem volume? Fora do ICP, entra na nutrição.

**1 · Abertura** — não pitcheie. Uma pergunta que expõe a dor nº 1:
> "Vi que vocês anunciam no [Meta/portal]. Rapidinho: vocês conseguem dizer hoje qual anúncio
> trouxe a última moto que venderam?"

Quase sempre a resposta é "não". Esse "não" é a abertura.

**2 · Descoberta** — três sondas para achar a dor mais aguda (ancore o pitch nela):
- Atribuição: *"Quando entra lead no WhatsApp, você sabe de qual campanha veio? Mede CPL/CPA?"*
- Resposta: *"Um lead que chega 22h ou domingo — quanto tempo até alguém responder?"*
- Financiamento: *"Pra fechar financiado, quantos bancos você simula e quanto tempo leva?"*

**3 · Demo/Pitch** — mostre o "aha" na tela: uma venda com a campanha amarrada, CPL/CPA/ROAS
sem planilha. Reforce **white-label** (nome da loja) e **moto-first**. Financiamento entra como
*"e ainda simula seus bancos sozinho, sem redigitar cadastro"*.

**4 · Objeções** — rebata e volte ao fechamento (ver diagrama). A mais comum, "já tenho
sistema", nunca é confronto: *"não substituo seu sistema, completo — ele te diz o ROAS por
campanha?"*.

**5 · Fechamento** — peça um passo pequeno e concreto, não assinatura:
> "Me passa uma campanha sua e eu te mostro a venda amarrada. 15 minutos, sem compromisso."

**6 · Follow-up** — se não fechou, cadência de 7–10 toques em 30 dias. Não abandone em 2–3
(é literalmente a dor que você vende).

---
_Fonte da estratégia: [`docs/mercado/README.md`](../mercado/README.md) e as duas pesquisas
citadas lá._
