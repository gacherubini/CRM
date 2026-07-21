#!/usr/bin/env python3
"""Gera docs/Revy-Sistema-Completo.pdf — mapa completo do produto Revy."""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

OUT = Path(__file__).resolve().parent / "Revy-Sistema-Completo.pdf"
FONT_DIR = Path(r"C:\Windows\Fonts")
FONT_REG = FONT_DIR / "arial.ttf"
FONT_BOLD = FONT_DIR / "arialbd.ttf"
FONT_ITAL = FONT_DIR / "ariali.ttf"


class Doc(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.add_font("Body", "", str(FONT_REG))
        self.add_font("Body", "B", str(FONT_BOLD))
        self.add_font("Body", "I", str(FONT_ITAL))
        self.set_auto_page_break(auto=True, margin=16)
        self.set_margins(16, 16, 16)

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Body", "I", 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 6, "Revy — Prompt completo do sistema", align="L")
        self.cell(0, 6, f"p. {self.page_no()}", align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(220, 220, 220)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-12)
        self.set_font("Body", "I", 8)
        self.set_text_color(130, 130, 130)
        self.cell(0, 8, "Confidencial — uso interno / onboarding / agentes", align="C")

    def _full_w(self) -> float:
        return self.w - self.l_margin - self.r_margin

    def h1(self, text: str):
        self.ln(3)
        self.set_x(self.l_margin)
        self.set_font("Body", "B", 15)
        self.set_text_color(10, 10, 10)
        self.multi_cell(self._full_w(), 8, text)
        self.ln(1)

    def h2(self, text: str):
        self.ln(2)
        self.set_x(self.l_margin)
        self.set_font("Body", "B", 11)
        self.set_text_color(25, 25, 25)
        self.multi_cell(self._full_w(), 6, text)
        self.ln(0.5)

    def h3(self, text: str):
        self.ln(1.5)
        self.set_x(self.l_margin)
        self.set_font("Body", "B", 10)
        self.set_text_color(40, 40, 40)
        self.multi_cell(self._full_w(), 5.5, text)

    def p(self, text: str):
        self.set_x(self.l_margin)
        self.set_font("Body", "", 9)
        self.set_text_color(30, 30, 30)
        self.multi_cell(self._full_w(), 5, text)
        self.ln(1)

    def bullet(self, text: str):
        self.set_font("Body", "", 9)
        self.set_text_color(30, 30, 30)
        self.set_x(self.l_margin + 3)
        self.multi_cell(self._full_w() - 3, 5, f"- {text}")
        self.ln(0.2)

    def code_block(self, text: str):
        self.set_fill_color(245, 245, 245)
        self.set_font("Courier", "", 7)
        self.set_text_color(20, 20, 20)
        self.set_x(self.l_margin)
        self.multi_cell(self._full_w(), 3.8, text, fill=True)
        self.ln(2)
        self.set_x(self.l_margin)

    def table(self, headers: list[str], rows: list[list[str]], col_w: list[float]):
        self.set_x(self.l_margin)
        self.set_font("Body", "B", 8)
        self.set_fill_color(15, 15, 15)
        self.set_text_color(255, 255, 255)
        for i, h in enumerate(headers):
            self.cell(col_w[i], 6, h, border=0, fill=True)
        self.ln()
        self.set_text_color(25, 25, 25)
        self.set_font("Body", "", 7.5)
        fill = False
        for row in rows:
            if self.get_y() > self.h - 28:
                self.add_page()
                self.set_x(self.l_margin)
                self.set_font("Body", "B", 8)
                self.set_fill_color(15, 15, 15)
                self.set_text_color(255, 255, 255)
                for i, h in enumerate(headers):
                    self.cell(col_w[i], 6, h, border=0, fill=True)
                self.ln()
                self.set_text_color(25, 25, 25)
                self.set_font("Body", "", 7.5)
            self.set_x(self.l_margin)
            if fill:
                self.set_fill_color(248, 248, 248)
            else:
                self.set_fill_color(255, 255, 255)
            line_h = 4.2
            parts = []
            max_lines = 1
            for i, cell in enumerate(row):
                t = (cell or "").replace("\n", " ")
                max_c = max(12, int(col_w[i] * 0.55))
                lines = []
                words = t.split(" ")
                cur = ""
                for w in words:
                    trial = (cur + " " + w).strip()
                    if len(trial) <= max_c:
                        cur = trial
                    else:
                        if cur:
                            lines.append(cur)
                        cur = w
                if cur:
                    lines.append(cur)
                if not lines:
                    lines = [""]
                parts.append(lines)
                max_lines = max(max_lines, len(lines))
            row_h = line_h * max_lines + 1.5
            y0 = self.get_y()
            x0 = self.l_margin
            if fill:
                self.rect(x0, y0, sum(col_w), row_h, style="F")
            else:
                self.rect(x0, y0, sum(col_w), row_h, style="F")
            for i, lines in enumerate(parts):
                self.set_xy(x0 + sum(col_w[:i]), y0 + 0.8)
                self.multi_cell(col_w[i], line_h, "\n".join(lines), border=0)
            self.set_y(y0 + row_h)
            fill = not fill
        self.ln(2)
        self.set_x(self.l_margin)


def build() -> Path:
    pdf = Doc()
    pdf.add_page()

    # Cover
    pdf.set_y(48)
    pdf.set_font("Body", "B", 32)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 14, "Revy", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Body", "", 15)
    pdf.set_text_color(70, 70, 70)
    pdf.cell(0, 9, "Prompt completo do sistema", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_font("Body", "", 10)
    pdf.set_text_color(35, 35, 35)
    pdf.multi_cell(
        0,
        5.5,
        "Mapa do produto: o que é, como funciona, features por módulo, "
        "fluxos ponta a ponta, tráfego pago, RBAC, stack e limites. "
        "Fonte de verdade para onboarding, pitch e agentes de código. "
        "Estado lab Fly (~2026-07).",
    )
    pdf.ln(8)
    y = pdf.get_y()
    pdf.set_draw_color(10, 10, 10)
    pdf.line(pdf.l_margin, y, pdf.l_margin + 55, y)
    pdf.ln(8)
    pdf.set_font("Body", "I", 10)
    pdf.multi_cell(
        0,
        5.5,
        "Elevator pitch: Revy é o sistema da revenda — atende no WhatsApp, "
        "simula financiamento nos bancos da loja, organiza estoque e vitrine, "
        "e entrega o vendedor na hora certa, com o dono enxergando venda, meta e origem.",
    )

    # 1
    pdf.add_page()
    pdf.h1("1. O que é o Revy (30 segundos)")
    pdf.p(
        "Revy é o sistema operacional da revenda de veículos (foco moto) no Brasil. "
        "Ele (1) atende o cliente no WhatsApp com bot + handoff humano; "
        "(2) simula financiamento de verdade nos portais dos bancos da loja (RPA); "
        "(3) organiza estoque e vitrine pública; "
        "(4) dá ao vendedor e ao dono CRM, vendas, metas e ROI de tráfego pago."
    )
    pdf.h3("Não é")
    pdf.bullet("CRM genérico / HighLevel / HubSpot")
    pdf.bullet("Agregador de crédito tipo marketplace")
    pdf.bullet("Ad Manager (criar anúncio Meta/Google)")
    pdf.bullet("App de posts em redes sociais")
    pdf.h3("É")
    pdf.bullet("Operação da loja: do lead no Zap à parcela e à venda registrada")
    pdf.bullet("Suite multi-produto plugável (HTTP entre serviços)")

    pdf.h1("2. Princípios de produto")
    pdf.bullet("Produtos independentes (Motor, Chatbot, Estoque, Portal, Catálogo) se falam só por HTTP.")
    pdf.bullet("Estoque é a fonte de verdade de veículos.")
    pdf.bullet("Simulação real = portais dos bancos (Playwright), não taxa inventada.")
    pdf.bullet("Nunca prometer aprovação de crédito.")
    pdf.bullet("LGPD: consentimento antes de dados sensíveis; CPF mascarado em logs.")
    pdf.bullet("Handoff: o humano manda; o bot para (auto-pausa).")
    pdf.bullet("Multi-loja (tenancy) no desenho; lab opera loja de teste.")
    pdf.bullet("Tráfego pago mensurável (Pixel + campanhas + ROI) sem virar social suite.")

    pdf.h1("3. Arquitetura")
    pdf.p("Peças principais e como se conectam:")
    pdf.code_block(
        """
                    [ Site B2B landing - site2037 ]

  Anuncio Meta --> Catalogo publico --> WhatsApp (CTA)
                         |                    |
                         | outbox CAT-xxx      | Evolution API
                         v                    v
                    Chatbot API <--------- n8n + Gemini
                         |
         +---------------+---------------+
         v               v               v
      Estoque          Motor          Portal CRM
   (veiculos)     (sim RPA multi)   (vendas/metas/ROI)
         |               |               |
         +------ HTTP only (sem DB compartilhado) ------+
""".strip(
            "\n"
        )
    )

    pdf.h2("3.1 Produtos e pastas")
    pdf.table(
        ["Produto", "Pasta", "Papel", "Fly lab"],
        [
            ["Motor", "motor-simulacao/", "Simulações multi-banco RPA", "motor2037"],
            ["Chatbot API", "chatbot-api/", "Leads, msgs, handoff, tools", "chatbot2037"],
            ["Estoque API", "estoque-api/", "CRUD veículos, placa, admin", "estoque2037"],
            ["Portal", "portal-gestao/", "CRM loja, sim UI, tráfego", "portal2037"],
            ["Catálogo", "catalogo-publico/", "Vitrine + Pixel + CTA WA", "catalogo2037"],
            ["Site", "site/", "Landing marketing Revy", "site2037"],
            ["Evolution", "(imagem)", "Canal WhatsApp", "evolution2037"],
            ["n8n", "(imagem)", "Orquestra bot 1:1", "n8n2037"],
            ["Postgres", "suite-pg", "DBs motor/estoque/chatbot", "suite-pg"],
        ],
        [32, 40, 68, 32],
    )
    pdf.p("Portal e Catálogo usam SQLite em volume Fly. Integrações internas via rede privada (.flycast).")

    pdf.h1("4. Fluxos de ponta a ponta")

    pdf.h2("4.1 Cliente no WhatsApp (atendimento + simulação)")
    pdf.code_block(
        """
Cliente msg
  -> Evolution (webhook)
  -> n8n (estado + Gemini + tools HTTP no Chatbot)
  -> Chatbot API (mensagem, lead, handoff)
  -> Se simular: Chatbot/Portal -> Motor
  -> Motor: fan-out bancos, workers Playwright sob demanda
  -> Resultado (parcela/taxa/status) formatado no Zap
  -> Se vendedor responde no app: auto-pausa do bot (E3)
""".strip(
            "\n"
        )
    )
    pdf.p(
        "Coleta típica: consentimento LGPD → moto/interesse → entrada/prazo "
        "→ CPF/nascimento → confirmação → simulação → handoff opcional."
    )

    pdf.h2("4.2 Vitrine → lead")
    pdf.code_block(
        """
Anuncio/catalogo
  -> PageView / ViewContent (Pixel browser)
  -> CTA WhatsApp -> Lead (Pixel) + evento CAT-xxx
  -> Outbox Catalogo -> Chatbot (interesse)
  -> Cliente manda msg com codigo CAT-...
  -> Chatbot correlaciona -> lead com UTM first/last + fbclid
""".strip(
            "\n"
        )
    )

    pdf.h2("4.3 Venda + Pixel Purchase + ROI")
    pdf.code_block(
        """
Vendedor registra venda no Portal (ideal: lead_ref = ID do lead)
  -> Dono/gerente CONFIRMA venda
  -> Snapshot campanha first/last na venda
  -> CAPI Purchase (servidor Meta) best-effort
  -> ROI: gasto campanha x leads x vendas (CPL/CPA/ROAS)
""".strip(
            "\n"
        )
    )
    pdf.p(
        "Venda no WhatsApp NÃO dispara Pixel no celular. "
        "Dispara CAPI no momento de confirmar a venda no Portal."
    )

    pdf.h2("4.4 Tráfego pago (dono)")
    pdf.bullet("1. Configura Pixel + token CAPI em Portal → Tráfego")
    pdf.bullet("2. Cadastra Campanha com o mesmo utm_campaign do anúncio")
    pdf.bullet("3. Lança gasto (R$) no detalhe da campanha")
    pdf.bullet("4. Links do anúncio apontam pro catálogo com UTMs")
    pdf.bullet("5. Lê ROI (first/last touch)")

    pdf.add_page()
    pdf.h1("5. Features por módulo")

    pdf.h2("A) WhatsApp / Chatbot — Revy Atende")
    pdf.table(
        ["Feature", "Status"],
        [
            ["Receber/enviar via Evolution", "Lab (transporte ok; go-live IA manual)"],
            ["LLM Gemini via n8n", "Previsto / config manual"],
            ["Lead + etapas", "Feito"],
            ["Consentimento LGPD", "Feito"],
            ["Handoff bot ↔ humano", "Feito"],
            ["Auto-pausa atendente no app (E3)", "Feito"],
            ["Cadastro veículo por WA (E5)", "Feito (texto)"],
            ["Simulação / tools por placa", "Feito (integração)"],
            ["Atribuição catálogo UTM/first-last/fbclid", "Feito"],
            ["Áudio/multimodal (E1)", "Roadmap"],
            ["Broadcast em massa (E11)", "Roadmap"],
            ["Exclusão LGPD completa", "Aberto"],
        ],
        [100, 72],
    )

    pdf.h2("B) Motor de simulação")
    pdf.table(
        ["Feature", "Status"],
        [
            ["API async de simulações", "Feito"],
            ["Multi-banco fan-out", "Feito"],
            ["Drivers LIVE: Santander, Fontecred, Bradesco, Pan", "Feito (RPA)"],
            ["Workers Playwright sob demanda (2GB)", "Feito"],
            ["Teto browsers lab (2)", "Feito"],
            ["Warm session / storage_state", "Feito / evolução"],
            ["Histórico + timeline + prints blob", "Feito"],
            ["Credenciais cifradas (Portal 9A → Motor)", "Feito"],
            ["testar-login real", "Placeholder"],
            ["Score bureau (E2)", "Adiado"],
        ],
        [100, 72],
    )

    pdf.h2("C) Estoque — Revy Estoque")
    pdf.table(
        ["Feature", "Status"],
        [
            ["CRUD veículos multi-loja", "Feito"],
            ["Placa / por-placa", "Feito"],
            ["Publicado vs rascunho", "Feito"],
            ["Admin HTMX", "Feito"],
            ["Outbox para catálogo", "Feito (E2E residual)"],
            ["Upload real de fotos (E6)", "Roadmap"],
        ],
        [100, 72],
    )

    pdf.h2("D) Catálogo público — Revy Vitrine")
    pdf.table(
        ["Feature", "Status"],
        [
            ["Vitrine /l/{loja}", "Feito"],
            ["Detalhe + galeria (URLs)", "Feito"],
            ["CTA WhatsApp + UTM/fbclid", "Feito"],
            ["Pixel: PageView, Lead, ViewContent", "Feito"],
            ["Domínio próprio (E18)", "Roadmap"],
        ],
        [100, 72],
    )

    pdf.h2("E) Portal CRM — Revy Painel")
    pdf.table(
        ["Feature", "Status"],
        [
            ["Login por papel (dono/gerente/vendedor)", "Feito"],
            ["Leads / conversas / handoff", "Feito"],
            ["Estoque via API", "Feito"],
            ["Simulações multi-banco + histórico/prints", "Feito"],
            ["Vendas registrar/confirmar/cancelar", "Feito"],
            ["Custos e lucro bruto", "Feito"],
            ["Metas loja e vendedor", "Feito"],
            ["Financeiro dashboard dono", "Feito"],
            ["Funil auditável", "Feito (parcial)"],
            ["Relatórios CSV", "Feito"],
            ["Acessos dos bancos (credenciais)", "Feito"],
            ["Tráfego Pixel + CAPI", "Feito"],
            ["Campanhas + gastos", "Feito"],
            ["ROI CPL/CPA/ROAS first-last", "Feito"],
            ["Dashboard vendedor", "Feito"],
            ["Seleção amigável de lead na venda", "Fraco (cola UUID)"],
            ["Eventos finos funil (#3B Task 4)", "Aberto"],
        ],
        [100, 72],
    )

    pdf.h2("F) Site marketing")
    pdf.p("Landing Revy (site2037) — pitch B2B da plataforma.")

    pdf.h1("6. Papéis (RBAC)")
    pdf.table(
        ["Papel", "Pode"],
        [
            ["Vendedor", "Leads, conversas, estoque, vendas próprias, sims, metas; SEM token CAPI/ROI admin"],
            ["Gerente", "Operação + financeiro/metas + tráfego/campanhas/ROI"],
            ["Dono", "Tudo da loja + equipe/config quando existir"],
            ["Admin plataforma", "Escopo multi-loja quando ativo"],
        ],
        [38, 134],
    )

    pdf.h1("7. Tráfego pago — modelo mental")
    pdf.p("Dois sistemas de verdade:")
    pdf.h3("1) Revy ROI (loja)")
    pdf.p(
        "Pergunta: esta campanha (UTM) gerou quantos leads/vendas e quanto gastei? "
        "Match declarado por utm_campaign (+ first/last touch). CPL = gasto/leads; "
        "CPA = gasto/vendas; ROAS = faturamento/gasto."
    )
    pdf.h3("2) Meta Ads (Pixel/CAPI)")
    pdf.p(
        "Browser no catálogo: PageView / Lead / ViewContent. "
        "Servidor no Portal: Purchase ao CONFIRMAR venda. "
        "Match com usuário é probabilístico (clique, cookies, telefone hash)."
    )
    pdf.h3("Quem faz o que")
    pdf.bullet("Dono: configura Pixel/CAPI e cadastra campanhas + gasto")
    pdf.bullet("Vendedor: NÃO copia token; registra venda no lead certo")
    pdf.bullet(
        "lead_ref hoje: copiar UUID da URL /app/leads/{id} e colar em "
        "Vendas → Referência do lead"
    )
    pdf.p(
        "Caminho fraco: cliente entra no Zap sem catálogo (sem UTM) ou venda "
        "sem lead_ref → ROI em “Sem campanha” e match Meta pior."
    )

    pdf.h1("8. Stack técnica")
    pdf.bullet("Backend: Python 3.12, FastAPI, SQLAlchemy, Alembic")
    pdf.bullet("Portal/Catálogo UI: Jinja2 + CSS próprio")
    pdf.bullet("Simulação real: Playwright + Xvfb (headed)")
    pdf.bullet("Orquestração bot: n8n + Gemini")
    pdf.bullet("Canal WA: Evolution API")
    pdf.bullet("Deploy: Fly.io região gru, org crm-419")
    pdf.bullet("Testes: pytest por produto")

    pdf.h1("9. Fora do core (não inventar)")
    pdf.bullet("Criar/pausar anúncios Meta/Google")
    pdf.bullet("Agendar posts / social planner (E9 FORA)")
    pdf.bullet("Fidelidade, gift card, curso/membership")
    pdf.bullet("Multi-agente complexo (E4 adiado)")
    pdf.bullet("Score Serasa automático (E2 adiado)")
    pdf.bullet("Contabilidade completa / lucro líquido contábil")

    pdf.h1("10. Maturidade (honesto)")
    pdf.table(
        ["Área", "Nível"],
        [
            ["Simulação multi-banco demonstrável", "Alta (~96% demo)"],
            ["CRM vendas/metas/financeiro", "Alta"],
            ["Catálogo + Pixel + campanhas/ROI", "Alta"],
            ["WhatsApp E2E produção com IA estável", "Média (go-live manual/ops)"],
            ["UX vendedor sem colar UUID", "Baixa"],
            ["Match Meta Purchase phone/fbclid no CAPI", "Parcial"],
            ["Fotos nativas / áudio no bot", "Roadmap"],
        ],
        [105, 67],
    )

    pdf.h1("11. URLs lab")
    pdf.bullet("Portal: https://portal2037.fly.dev")
    pdf.bullet("Catálogo: https://catalogo2037.fly.dev")
    pdf.bullet("Site: https://site2037.fly.dev")
    pdf.bullet("n8n: https://n8n2037.fly.dev")
    pdf.bullet("Evolution Manager: https://evolution2037.fly.dev/manager")

    pdf.h1("12. Tom de voz")
    pdf.bullet("Português BR claro, frases curtas")
    pdf.bullet("Rápido, preciso, honesto")
    pdf.bullet("Confirma antes de gravar/simular")
    pdf.bullet("Nunca: “você já está aprovado”, hype de IA, pressão agressiva")
    pdf.bullet("Painel dono: sistema e operação | Zap cliente: assistente da loja")

    pdf.h1("13. Instruções para agentes de código")
    pdf.bullet("Ler docs/contexto-compacto.md primeiro")
    pdf.bullet("Planos válidos em docs/plans/ (não _archive/)")
    pdf.bullet("Não misturar eixos na mesma PR")
    pdf.bullet("Não imprimir secrets / .env")
    pdf.bullet("Integração só HTTP entre produtos")
    pdf.bullet("Estoque = verdade de veículos")
    pdf.bullet(
        "Não reimplementar FEITO (ex.: histórico sims Task 16, E3, E5, E10 base, campanhas/ROI)"
    )

    pdf.h1("14. Diagrama mental: dia a dia da loja")
    pdf.code_block(
        """
DONO                          VENDEDOR                      CLIENTE
 |                              |                              |
 Configura Pixel/CAPI           Atende no WhatsApp             Clica anuncio
 Cadastra campanha+gasto        Simula no Portal/Zap           Ve catalogo
 Le ROI e metas                 Registra venda + lead_ref      Manda msg no Zap
 Confirma venda                 Devolve/assume bot             Recebe parcelas
""".strip(
            "\n"
        )
    )

    pdf.h1("15. Checklist go-live rápido")
    pdf.bullet("Backends: portal, chatbot, estoque, motor, postgres up")
    pdf.bullet("WA: evolution + n8n up; instância conectada; workflow Gemini")
    pdf.bullet("Catálogo: veículos publicados no estoque")
    pdf.bullet("Tráfego: Pixel ID igual no Portal e META_PIXEL_ID do catálogo")
    pdf.bullet("Campanha: utm_campaign idêntico no anúncio e no Revy")
    pdf.bullet("Teste: lead com UTM → venda com lead_ref → confirmar → ROI + Events Manager")

    pdf.h1("16. Pitch de 15s")
    pdf.p(
        "Revy é o sistema da revenda: atende no WhatsApp, simula financiamento "
        "nos bancos da loja, organiza estoque e vitrine, e entrega o vendedor "
        "na hora certa — com o dono enxergando venda, meta e origem do tráfego."
    )

    pdf.ln(6)
    pdf.set_font("Body", "I", 8)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(
        0,
        4,
        "Documento gerado a partir do estado do produto no repositório bot-whatsapp-financiamento. "
        "Atualize quando features mudarem. Arquivo: docs/Revy-Sistema-Completo.pdf",
    )

    pdf.output(str(OUT))
    return OUT


if __name__ == "__main__":
    path = build()
    print(path)
    print(f"size={path.stat().st_size} bytes")
