# Plano — Revy Tráfego separado do Portal da loja

> **Status 2026-07-28: FASE 1 CÓDIGO FEITO** — app `revy-trafego/` + slim portal (sem UI técnica no dono por default).  
> Fase 2 (API resultados + cutover CAPI/pixel) ainda **não** implementada.  
> Spec: [`docs/superpowers/specs/2026-07-28-revy-trafego-separacao-portal-design.md`](../superpowers/specs/2026-07-28-revy-trafego-separacao-portal-design.md)

**Eixo:** C · CRM / marketing  
**Depende de:** campanhas+ROI DONE, Meta spend MVP, CTWA MVP, resultados dono no dashboard  
**Não reimplementar:** fórmula ROI, match UTM, CAPI Purchase, spend Meta — só **extrair e reorganizar**

**Goal:** Equipe Revy opera tráfego multi-loja num app próprio (config + resultados + diagnóstico). Portal da loja mostra só resultados de negócio (mesmas métricas, UI limpa), sem Pixel/tokens/CRUD técnico.

**Architecture:** Strangler. Fase 1 = app `revy-trafego` + auth interna + port da superfície técnica + slim do portal (DB/schema ainda compartilhado ok). Fase 2 = API de resultados como fonte única + cutover pixel/CAPI/venda. Integração só HTTP entre produtos no alvo.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy, Alembic, Jinja2, pytest, httpx — mesmo padrão do `portal-gestao`.

---

## Decisões (não reabrir sem motivo)

1. Gestor = **equipe Revy** (todas as lojas no seletor).
2. Cliente = **só resultados** (gasto, leads, vendas, CPL, CPA, ROAS).
3. App **separado** (`revy-trafego`), não só papel no portal.
4. Fonte da verdade de mídia → Revy Tráfego (médio prazo).
5. Resultados **nos dois** apps; **uma** fórmula/fonte no alvo.
6. Diagnóstico com lead/conversa (proxy chatbot) permitido.
7. Migração **strangler**, não big bang.

---

## Fases e planos detalhados

| Fase | Plano detalhado | Entrega | Status |
|---:|---|---|---|
| **1** | [Fase 1 — app multi-loja + slim portal](../superpowers/plans/2026-07-28-revy-trafego-fase1-app-multi-loja.md) | Cockpit Revy + cliente sem menus técnicos | **CÓDIGO FEITO** — falta deploy lab |
| **2** | [Fase 2 — API + cutover](../superpowers/plans/2026-07-28-revy-trafego-fase2-api-cutover.md) | Resultados via API; pixel/CAPI/venda no Revy Tráfego | **NÃO IMPLEMENTADO** |
| **3** | (opcional, sem plano detalhado ainda) | Split DB, atribuição por gestor, audit PII completo | Backlog |

### Critério de pronto Fase 1

- [ ] App `revy-trafego` sobe local (+ path de deploy lab documentado).
- [ ] Login interno Revy; seletor de loja com todas as lojas.
- [ ] Gestor configura Pixel/CAPI/Ads, campanhas, vê ROI e auditorias por loja.
- [ ] Gestor abre lead/conversa de diagnóstico (proxy chatbot).
- [ ] Dono/gerente **não** vê Tráfego/CTWA/Pixel/Campanhas no portal.
- [ ] Dono ainda vê resultados de mídia na visão geral.
- [ ] CAPI na venda e pixel no catálogo **não regredem** (mesmo processo worker se necessário).

### Critério de pronto Fase 2

- [ ] `GET /v1/lojas/{slug}/resultados` estável; portal consome para cards.
- [ ] Catálogo lê pixel no Revy Tráfego.
- [ ] Venda confirmada notifica Revy Tráfego; worker CAPI só lá.
- [ ] Portal sem models de mídia na UI de resultados.

---

## Ordem de trabalho recomendada

```text
Fase 1 Task 1–3  scaffold + auth + lojas
        Task 4–7  port domínio + telas + jobs
        Task 8–9  diagnóstico + slim portal
        Task 10   deploy/docs/regressão
Fase 2 Task 1–n  API → portal client → pixel → venda → limpeza
```

Não misturar Fase 2 antes da Fase 1 estar utilizável pela equipe Revy.

---

## Impacto em docs existentes

| Doc | Ação na implementação |
|---|---|
| `docs/trafego-pago-loja.md` | Virar guia do **cliente** (só resultados); setup técnico → guia Revy |
| `docs/fluxo-utm-pixel-ctwa-meta.md` | Atualizar dono do endpoint Pixel / CAPI |
| `docs/contexto-compacto.md` | Entrada eixo C: Revy Tráfego |
| Tutoriais PDF tráfego | Regenerar quando Fase 1 fechar UI |

---

## Relação com planos DONE

| Plano | Relação |
|---|---|
| `2026-07-20-plano-trafego-pago-crm-campanhas-roi.md` | DONE — domínio a **mover**, não reescrever |
| `2026-07-21-plano-conversao-atribuicao-insights.md` | Resultados dono / CAPI — slim + cutover |
| `2026-07-22-plano-ctwa-...` / `meta-spend-api` | Telas/jobs migram com o app |

---

## Pacote comercial (visão)

- **Portal da loja:** CRM + resultados de mídia (leitura).
- **Revy Tráfego:** operação interna (não vendido como self-serve de token ao lojista no MVP).
