#!/usr/bin/env python3
"""Gera 2 PDFs de tráfego pago no Revy:

1. Setup — como arrumar tudo para funcionar
2. Fluxos — uso no dia a dia (diagramas)

Uso: python docs/gerar_pdf_tutorial_trafego_revy.py
"""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "output" / "pdf"
DOCS_DIR = Path(__file__).resolve().parent

OUT_SETUP = OUT_DIR / "tutorial-revy-trafego-setup.pdf"
OUT_SETUP_DOCS = DOCS_DIR / "tutorial-revy-trafego-setup.pdf"
OUT_FLUXOS = OUT_DIR / "tutorial-revy-trafego-fluxos.pdf"
OUT_FLUXOS_DOCS = DOCS_DIR / "tutorial-revy-trafego-fluxos.pdf"

# Compat: nome antigo apontava para um PDF único
OUT_LEGACY = OUT_DIR / "tutorial-revy-trafego-meta.pdf"
OUT_LEGACY_DOCS = DOCS_DIR / "tutorial-revy-trafego-meta.pdf"

FONT_DIR = Path(r"C:\Windows\Fonts")
FONT_REG = FONT_DIR / "arial.ttf"
FONT_BOLD = FONT_DIR / "arialbd.ttf"
FONT_ITAL = FONT_DIR / "ariali.ttf"

PORTAL = "https://app2037.fly.dev"
CATALOGO = "https://app2037.fly.dev/loja/..."


class Doc(FPDF):
    def __init__(self, header_title: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self._header_title = header_title
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
        self.cell(0, 6, self._header_title, align="L")
        self.cell(0, 6, f"p. {self.page_no()}", align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(220, 220, 220)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-12)
        self.set_font("Body", "I", 8)
        self.set_text_color(130, 130, 130)
        self.cell(0, 8, "Revy — dono/gestor · uso interno da loja", align="C")

    def _full_w(self) -> float:
        return self.w - self.l_margin - self.r_margin

    def cover(self, title: str, subtitle: str, blurb: str):
        self.add_page()
        self.set_y(42)
        self.set_font("Body", "B", 28)
        self.set_text_color(10, 10, 10)
        self.cell(0, 12, "Revy", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Body", "", 15)
        self.set_text_color(50, 50, 50)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(4)
        self.set_font("Body", "", 10)
        self.set_text_color(40, 40, 40)
        self.multi_cell(self._full_w(), 5.5, subtitle)
        self.ln(6)
        y = self.get_y()
        self.set_draw_color(10, 10, 10)
        self.line(self.l_margin, y, self.l_margin + 45, y)
        self.ln(8)
        self.set_font("Body", "I", 9)
        self.multi_cell(self._full_w(), 5, blurb)
        self.ln(10)
        self.set_font("Body", "", 9)
        self.set_text_color(30, 30, 30)
        self.multi_cell(self._full_w(), 5, f"Portal: {PORTAL}")
        self.ln(0.5)
        self.multi_cell(self._full_w(), 5, f"Catálogo: {CATALOGO}")

    def h1(self, text: str):
        self.ln(2)
        self.set_x(self.l_margin)
        self.set_font("Body", "B", 13)
        self.set_text_color(10, 10, 10)
        self.multi_cell(self._full_w(), 7, text)
        self.ln(1)

    def h2(self, text: str):
        self.ln(2)
        self.set_x(self.l_margin)
        self.set_font("Body", "B", 11)
        self.set_text_color(25, 25, 25)
        self.multi_cell(self._full_w(), 6, text)
        self.ln(0.4)

    def p(self, text: str):
        self.set_x(self.l_margin)
        self.set_font("Body", "", 9)
        self.set_text_color(30, 30, 30)
        self.multi_cell(self._full_w(), 4.8, text)
        self.ln(0.6)

    def bullet(self, text: str):
        self.set_font("Body", "", 9)
        self.set_text_color(30, 30, 30)
        self.set_x(self.l_margin + 2)
        self.multi_cell(self._full_w() - 2, 4.8, f"• {text}")
        self.ln(0.15)

    def note(self, text: str):
        self.set_x(self.l_margin)
        self.set_font("Body", "I", 8.5)
        self.set_text_color(70, 70, 70)
        self.multi_cell(self._full_w(), 4.6, text)
        self.ln(0.8)

    def code(self, text: str):
        self.set_x(self.l_margin)
        self.set_font("Body", "", 8)
        self.set_text_color(20, 20, 20)
        self.set_fill_color(245, 245, 245)
        self.multi_cell(self._full_w(), 4.3, text, fill=True)
        self.ln(1.2)

    def kv(self, key: str, value: str):
        self.set_x(self.l_margin)
        self.set_font("Body", "B", 9)
        self.set_text_color(20, 20, 20)
        prefix = f"{key}: "
        self.write(4.8, prefix)
        self.set_font("Body", "", 9)
        self.set_text_color(35, 35, 35)
        self.multi_cell(self._full_w() - self.get_string_width(prefix), 4.8, value)
        self.ln(0.2)

    def flow(self, steps: list[str], title: str = ""):
        if title:
            self.set_font("Body", "B", 9)
            self.set_text_color(40, 40, 40)
            self.set_x(self.l_margin)
            self.cell(0, 5, title, new_x="LMARGIN", new_y="NEXT")
            self.ln(1)

        box_h = 7.5
        gap = 3.5
        w = min(120.0, self._full_w() - 10)
        x = self.l_margin + (self._full_w() - w) / 2
        needed = len(steps) * box_h + max(0, len(steps) - 1) * gap + 4
        if self.get_y() + needed > self.h - 20:
            self.add_page()

        for i, label in enumerate(steps):
            y = self.get_y()
            self.set_draw_color(40, 40, 40)
            self.set_fill_color(248, 248, 248)
            self.set_line_width(0.3)
            self.rect(x, y, w, box_h, style="DF")
            self.set_xy(x, y + 1.5)
            self.set_font("Body", "", 8.5)
            self.set_text_color(20, 20, 20)
            self.cell(w, 4.5, label, align="C")
            self.set_y(y + box_h)
            if i < len(steps) - 1:
                mid_x = x + w / 2
                y1 = self.get_y()
                y2 = y1 + gap
                self.set_draw_color(80, 80, 80)
                self.set_line_width(0.4)
                self.line(mid_x, y1 + 0.5, mid_x, y2 - 1.5)
                self.line(mid_x, y2 - 1.5, mid_x - 1.5, y2 - 3.5)
                self.line(mid_x, y2 - 1.5, mid_x + 1.5, y2 - 3.5)
                self.set_y(y2)
        self.ln(3)

    def two_cols_flow(
        self,
        left_title: str,
        left: list[str],
        right_title: str,
        right: list[str],
    ):
        if self.get_y() > self.h - 90:
            self.add_page()
        start_y = self.get_y()
        col_w = (self._full_w() - 8) / 2
        gap_x = 8
        x1 = self.l_margin
        x2 = self.l_margin + col_w + gap_x

        def col(x: float, title: str, steps: list[str]) -> float:
            self.set_xy(x, start_y)
            self.set_font("Body", "B", 9)
            self.set_text_color(30, 30, 30)
            self.cell(col_w, 5, title, align="C", new_x="LMARGIN", new_y="NEXT")
            y = start_y + 7
            box_h = 7
            step_gap = 3
            for i, label in enumerate(steps):
                self.set_draw_color(40, 40, 40)
                self.set_fill_color(248, 248, 248)
                self.set_line_width(0.3)
                self.rect(x, y, col_w, box_h, style="DF")
                self.set_xy(x, y + 1.3)
                self.set_font("Body", "", 7.5)
                self.set_text_color(20, 20, 20)
                self.cell(col_w, 4.5, label, align="C")
                y += box_h
                if i < len(steps) - 1:
                    mid = x + col_w / 2
                    self.set_draw_color(80, 80, 80)
                    self.line(mid, y + 0.3, mid, y + step_gap - 1.2)
                    self.line(mid, y + step_gap - 1.2, mid - 1.2, y + step_gap - 2.8)
                    self.line(mid, y + step_gap - 1.2, mid + 1.2, y + step_gap - 2.8)
                    y += step_gap
            return y

        y1 = col(x1, left_title, left)
        y2 = col(x2, right_title, right)
        self.set_y(max(y1, y2) + 3)

    def save(self, *paths: Path) -> None:
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.output(str(path))


def build_setup() -> Path:
    """PDF 1 — como arrumar tudo para funcionar."""
    pdf = Doc("Revy — Setup de tráfego pago (Meta)")
    pdf.cover(
        title="Setup de tráfego pago (Meta)",
        subtitle=(
            "Como configurar Pixel, CAPI, gasto automático e campanhas "
            "para o Revy medir lead, venda e ROI."
        ),
        blurb=(
            "Faça uma vez por loja (e revise se trocar conta Meta). "
            "O dia a dia está no PDF de Fluxos."
        ),
    )

    pdf.add_page()
    pdf.h1("1. O que você está ligando")
    pdf.p(
        "Ads Manager cria e gasta o anúncio. O Revy amarra origem → lead → "
        "venda → gasto → retorno, e avisa a Meta nas vendas (CAPI)."
    )
    pdf.flow(
        [
            "Conta Meta (Pixel + tokens)",
            "Portal Revy → Tráfego",
            "Campanha no Revy + anúncio no Ads",
            "Lead e venda medidos no Portal",
        ],
        title="Visão do setup",
    )

    pdf.h1("2. Nomes rápidos")
    pdf.kv("Pixel", "Código no catálogo. Meta vê visitas e cliques no site.")
    pdf.kv("CAPI", "Revy avisa a Meta na venda (Purchase). Token secreto.")
    pdf.kv("UTM", "Etiquetas no link. utm_campaign liga lead ↔ campanha Revy.")
    pdf.kv("CTWA", "Anúncio que abre o WhatsApp direto (sem site).")
    pdf.kv("Código CTWA", "Ex.: RV-JUL na msg do anúncio e no cadastro Revy.")
    pdf.kv("ads_read", "Token para puxar gasto da Meta (≠ token CAPI).")
    pdf.note(
        "Regra de ouro: utm_campaign no link = texto igual em Portal → Campanhas."
    )

    pdf.h1("3. O que pegar na Meta e onde colar")
    pdf.h2("Pixel ID")
    pdf.kv("Para quê", "Ativar o Pixel no catálogo e alinhar o CAPI.")
    pdf.kv("Onde pegar", "Events Manager → seu Pixel → ID numérico.")
    pdf.kv("Onde colar", "Portal → Tráfego → Pixel ID.")
    pdf.note("O catálogo puxa o Pixel sozinho. Não precisa de secret no servidor.")

    pdf.h2("Token CAPI")
    pdf.kv("Para quê", "Avisar a Meta nas vendas (Purchase).")
    pdf.kv("Onde pegar", "Events Manager → dataset → gerar access token.")
    pdf.kv("Onde colar", "Portal → Tráfego → Token CAPI.")
    pdf.note("Nunca no catálogo nem no navegador do cliente.")

    pdf.h2("Ad Account ID + token ads_read")
    pdf.kv("Para quê", "Importar gasto das campanhas (ROI).")
    pdf.kv("Onde pegar", "Ads Manager (act_…) + Business Manager (token ads_read).")
    pdf.kv("Onde colar", "Portal → Tráfego → gasto automático.")
    pdf.note("CAPI e ads_read são tokens diferentes.")

    pdf.add_page()
    pdf.h2("Por campanha")
    pdf.kv("utm_campaign", "No link do anúncio (catálogo) e em Campanhas Revy.")
    pdf.kv("ID campanha Meta", "Campanhas Revy — ajuda gasto e CTWA.")
    pdf.kv("Código CTWA", "Msg do anúncio WhatsApp + Campanhas Revy.")

    pdf.h1("4. Passo a passo")
    pdf.flow(
        [
            "1. Tráfego → Pixel ID + CAPI (PageView, Lead, Purchase)",
            "2. Tráfego → Ad Account + ads_read + sync ligada",
            "3. Campanhas → Nova (utm e/ou Cód CTWA e/ou ID Meta)",
            "4. Ads Manager → anúncio com o link ou WhatsApp certo",
            "5. Teste: clique, lead no Portal, UTM/código ok",
        ],
        title="Ordem recomendada",
    )

    pdf.h2("Passo 1 — Pixel e CAPI")
    pdf.bullet("Portal → Tráfego.")
    pdf.bullet("Cole Pixel ID e token CAPI.")
    pdf.bullet("Deixe ligados: PageView, Lead, Purchase → Salvar.")
    pdf.bullet("Menu Pixel: deve aparecer config_salva.")

    pdf.h2("Passo 2 — Gasto automático")
    pdf.bullet("Mesma tela Tráfego → Ad Account ID + token ads_read.")
    pdf.bullet("Sync habilitada → Salvar.")
    pdf.bullet("“Sincronizar agora” ou espere o job diário (~24h).")

    pdf.h2("Passo 3 — Campanha no Revy")
    pdf.bullet("Campanhas → Nova: nome interno, canal Meta.")
    pdf.bullet("utm_campaign (ex.: seminovos-julho) se for link de catálogo.")
    pdf.bullet("ID Meta da campanha no Ads (para gasto).")
    pdf.bullet("Código CTWA se for WhatsApp direto.")

    pdf.h2("Passo 4 — Anúncio na Meta")
    pdf.p("Caminho catálogo (recomendado para medir):")
    pdf.code(
        f"{PORTAL}/loja/SUA-LOJA/veiculos/ID-DA-MOTO\n"
        "?utm_source=instagram&utm_medium=paid&utm_campaign=seminovos-julho"
    )
    pdf.bullet("URL = página da moto no catálogo (não o botão de interesse).")
    pdf.bullet("Ads: objetivo Leads / conversão no site / evento Lead.")
    pdf.bullet("Mesmo Pixel configurado no Portal.")
    pdf.p("Caminho CTWA:")
    pdf.bullet("Destino: WhatsApp da loja.")
    pdf.bullet("Mensagem inicial: Cód: RV-JUL (igual ao cadastro Revy).")

    pdf.add_page()
    pdf.h1("5. Checklist “está amarrado?”")
    pdf.bullet("Pixel ID + CAPI salvos em Tráfego.")
    pdf.bullet("Purchase ligado.")
    pdf.bullet("Ad Account + ads_read salvos.")
    pdf.bullet("Campanha com utm_campaign e/ou Cód CTWA e/ou ID Meta.")
    pdf.bullet("Anúncio com o mesmo utm_campaign (catálogo) ou o mesmo Cód (CTWA).")
    pdf.bullet("Lead de teste com origem/UTM ou meta_ctwa.")
    pdf.bullet("Sync de gasto preencheu valor (ou manual se não for Meta).")
    pdf.bullet("Venda de teste confirmada com lead → Purchase delivered na auditoria Pixel.")

    pdf.h1("6. Se o setup falhar")
    pdf.kv("Lead sem campanha", "Typo no utm_campaign ou no Cód CTWA.")
    pdf.kv("ROAS “—” / gasto zero", "Sync, ID Meta na campanha, ou token ads_read.")
    pdf.kv("CAPI falhou", "Token inválido / Purchase off — retente em Tráfego.")
    pdf.kv("Pixel não dispara", "Pixel ID no Portal? Página do catálogo aberta?")
    pdf.kv("CTWA sem match", "Código na msg ≠ cadastro; veja auditoria CTWA.")

    pdf.h1("7. Telas de configuração")
    pdf.kv("Tráfego", "Pixel, CAPI, conta ads, sync.")
    pdf.kv("Campanhas", "UTM, ID Meta, código CTWA.")
    pdf.kv("Pixel / CTWA", "Auditorias de sinal e envio.")

    pdf.ln(3)
    pdf.note(
        "Depois do setup: use o PDF “Fluxos” para o dia a dia "
        "(atender, vender, ler ROI)."
    )

    pdf.save(OUT_SETUP, OUT_SETUP_DOCS)
    return OUT_SETUP


def build_fluxos() -> Path:
    """PDF 2 — fluxos de uso no dia a dia (com papéis dono × vendedor)."""
    pdf = Doc("Revy — Fluxos de tráfego pago (Meta)")
    pdf.cover(
        title="Fluxos de tráfego pago (Meta)",
        subtitle=(
            "Como o anúncio vira lead e venda no dia a dia — "
            "o que o dono faz, o que o vendedor faz, e por quê."
        ),
        blurb=(
            "Pressupõe setup já feito (PDF “Setup”). "
            "Ads veicula; Revy mede até a moto vendida."
        ),
    )

    # ── Papéis ──
    pdf.add_page()
    pdf.h1("1. Quem faz o quê (e por quê)")
    pdf.p(
        "Se cada um souber o seu papel, o placar fecha sozinho. "
        "Misturar papéis (vendedor “consertando” UTM, dono não confirmando venda) "
        "é o que mais fura o ROI."
    )

    pdf.h2("Dono / gerente")
    pdf.p("Cuida do dinheiro do anúncio e da verdade do placar.")
    pdf.bullet(
        "Configura e revisa Tráfego (Pixel, CAPI, gasto) — por quê: sem isso "
        "a Meta e o Revy não falam a mesma língua."
    )
    pdf.bullet(
        "Cadastra campanhas e monta o link/código do anúncio — por quê: é a "
        "“etiqueta” que liga clique → lead → moto."
    )
    pdf.bullet(
        "Olha ROI toda semana e decide budget — por quê: só ele (ou gerente) "
        "deve pausar o que não paga moto."
    )
    pdf.bullet(
        "Confirma a venda no Portal — por quê: só a confirmação dispara Purchase "
        "na Meta e fecha faturamento no ROI. Registrar não basta."
    )
    pdf.bullet(
        "Não precisa atender todo lead — por quê: o tempo dele vale mais na "
        "decisão de mídia e no fechamento do placar."
    )

    pdf.h2("Vendedor")
    pdf.p("Cuida da conversa e de amarrar a venda à pessoa certa.")
    pdf.bullet(
        "Responde rápido no WhatsApp — por quê: lead de anúncio esfria em minutos; "
        "msg barata sem atendimento vira CPA alto."
    )
    pdf.bullet(
        "Não pede para apagar a mensagem com código CAT-… ou Cód: — por quê: "
        "esse texto é a etiqueta da campanha; sem ele o lead pode ficar “órfão”."
    )
    pdf.bullet(
        "Confere o lead no Portal (origem, UTM, moto) — por quê: sabe se veio "
        "de anúncio e qual campanha; ajuda a priorizar e a falar da moto certa."
    )
    pdf.bullet(
        "Registra a venda escolhendo o lead da conversa — por quê: sem lead_ref "
        "a moto some do ROI da campanha (parece que o anúncio não vendeu)."
    )
    pdf.bullet(
        "Avisa o dono/gerente para confirmar — por quê: o vendedor fecha o "
        "cliente; o dono “bate o carimbo” que manda Purchase e fecha o placar."
    )
    pdf.bullet(
        "Não mexe em Pixel, token nem gasto de ads — por quê: é config de dono; "
        "erro aqui quebra a loja inteira, não só um lead."
    )

    pdf.h2("Resumo em uma linha")
    pdf.kv("Dono", "Paga anúncio, etiqueta campanha, confirma venda, lê ROI.")
    pdf.kv("Vendedor", "Atende, não perde a etiqueta, vende com o lead certo.")

    # ── Fluxo geral ──
    pdf.add_page()
    pdf.h1("2. Fluxo geral")
    pdf.p(
        "Você paga anúncio. O cliente chega no WhatsApp. A loja vende. "
        "O Revy mostra se valeu a pena."
    )
    pdf.flow(
        [
            "Anúncio (Meta Ads)",
            "Catálogo  ou  WhatsApp direto",
            "Conversa no WhatsApp",
            "Lead no Revy",
            "Venda confirmada",
            "ROI no Portal  +  Purchase na Meta",
        ]
    )
    pdf.h2("Em cada etapa, quem age")
    pdf.kv("Anúncio", "Dono: cria no Ads e no Revy. Por quê: define a etiqueta.")
    pdf.kv("Chegada", "Automático (Pixel / CTWA). Por quê: ninguém digita à mão.")
    pdf.kv("Conversa", "Vendedor. Por quê: converte interesse em proposta.")
    pdf.kv("Lead", "Sistema + vendedor confere. Por quê: origem precisa estar certa.")
    pdf.kv("Venda registrada", "Vendedor com lead. Por quê: amarra pessoa ↔ moto.")
    pdf.kv("Venda confirmada", "Dono/gerente. Por quê: Purchase + ROI oficiais.")

    # ── Dois caminhos ──
    pdf.h1("3. Dois caminhos de anúncio")
    pdf.two_cols_flow(
        "A) Catálogo",
        [
            "Anúncio",
            "Página da moto",
            "Clica no WhatsApp",
            "Lead + UTM",
            "Venda → ROI + CAPI",
        ],
        "B) CTWA",
        [
            "Anúncio",
            "WhatsApp na hora",
            "Msg com Cód: RV-…",
            "Lead meta_ctwa",
            "Venda → ROI + CAPI",
        ],
    )
    pdf.bullet("A: melhor para medir e treinar a Meta (Pixel no site).")
    pdf.bullet("B: mais volume de conversa; use código na mensagem.")
    pdf.bullet(
        "Dono compara A vs B pelo custo por venda (CPA), não só por quantidade de msgs."
    )

    # ── Caminho catálogo detalhado ──
    pdf.add_page()
    pdf.h1("4. Caminho catálogo — passo a passo")
    pdf.flow(
        [
            "Cliente vê anúncio → página da moto",
            "Pixel: PageView + ViewContent",
            "Clica “Tenho interesse no WhatsApp”",
            "Pixel Lead + Revy grava UTM e CAT-…",
            "Envia a msg → lead na campanha",
            "Vendedor atende → vende com o lead",
            "Dono confirma → ROI + Purchase",
        ]
    )

    pdf.h2("Antes do anúncio rodar — Dono")
    pdf.bullet(
        "Publica a moto no estoque e copia a URL da página no catálogo — "
        "por quê: o anúncio precisa de um destino real (a vitrine da moto)."
    )
    pdf.bullet(
        "Cadastra a campanha no Revy com o mesmo utm_campaign do link — "
        "por quê: sem isso o lead chega, mas sem campanha no ROI."
    )
    pdf.bullet(
        "Cola no Ads a URL da moto + UTMs (não o link do botão de interesse) — "
        "por quê: a pessoa precisa ver a moto e o Pixel rodar antes do WhatsApp."
    )
    pdf.bullet(
        "Coloca o ID da campanha Meta no cadastro Revy — por quê: o gasto "
        "automático sabe em qual linha somar o dinheiro."
    )

    pdf.h2("Quando o cliente chega — Vendedor")
    pdf.bullet(
        "Atende a conversa no WhatsApp assim que possível — por quê: lead pago "
        "é caro; demora = desperdício de budget do dono."
    )
    pdf.bullet(
        "Deixa a mensagem inicial com o código CAT-… — por quê: o Revy usa isso "
        "para casar o clique do catálogo com o telefone."
    )
    pdf.bullet(
        "Abre o lead no Portal e confere se tem campanha/UTM e qual moto — "
        "por quê: fala da moto certa e sabe se o anúncio está “chegando” no CRM."
    )
    pdf.bullet(
        "Se o lead veio sem campanha, avisa o dono (não inventa UTM no lead) — "
        "por quê: o conserto é no anúncio/cadastro da próxima; o histórico fica honesto."
    )

    pdf.h2("Quando fecha — Vendedor + Dono")
    pdf.bullet(
        "Vendedor: Vendas → nova → escolhe o lead da conversa e a moto — "
        "por quê: amarra faturamento à pessoa que veio do anúncio."
    )
    pdf.bullet(
        "Dono/gerente: Confirmar a venda — por quê: só aí o Revy manda Purchase "
        "à Meta (com valor) e o ROI conta a moto. Sem confirmar, o placar fica aberto."
    )

    # ── CTWA ──
    pdf.add_page()
    pdf.h1("5. Caminho CTWA — passo a passo")
    pdf.flow(
        [
            "Cliente toca no anúncio",
            "WhatsApp abre na hora",
            "Envia msg com Cód: RV-…",
            "Lead meta_ctwa no Revy",
            "Vendedor atende e vende com o lead",
            "Dono confirma → ROI + CAPI",
        ]
    )

    pdf.h2("Dono")
    pdf.bullet(
        "Na campanha Revy: preenche Código CTWA (ex.: RV-JUL) e ID Meta — "
        "por quê: sem código, se o click id não chegar, o lead não casa com a campanha."
    )
    pdf.bullet(
        "No Ads: mensagem inicial com “Cód: RV-JUL” igual ao cadastro — "
        "por quê: o cliente envia esse texto e o Revy lê a etiqueta."
    )
    pdf.bullet(
        "Usa público de quem visitou o catálogo / lookalike quando der — "
        "por quê: CTWA sem persona vira muita msg e pouca moto."
    )
    pdf.bullet(
        "Olha auditoria CTWA de vez em quando — por quê: vê se clid/código estão "
        "chegando; se não, o problema é configuração, não o vendedor."
    )

    pdf.h2("Vendedor")
    pdf.bullet(
        "Mesmo ritmo: atender rápido, não apagar o Cód: da mensagem — "
        "por quê: igual ao catálogo, a etiqueta está no texto."
    )
    pdf.bullet(
        "Trata como lead de anúncio pago (prioridade) — por quê: cada msg tem "
        "custo de mídia atrás."
    )
    pdf.bullet(
        "Venda sempre com o lead da conversa — por quê: o ROI de CTWA só fecha "
        "se a moto estiver ligada a esse lead."
    )

    # ── Turno do vendedor ──
    pdf.h1("6. Turno do vendedor (dia de loja)")
    pdf.flow(
        [
            "Abre Leads / conversas do dia",
            "Prioriza origem anúncio (Meta / UTM / CTWA)",
            "Atende no WhatsApp",
            "Atualiza etapa se a loja usar",
            "Se vendeu: registra com o lead",
            "Pede confirmação ao dono/gerente",
        ]
    )
    pdf.bullet(
        "Por que priorizar anúncio: o dono está pagando por esse contato; "
        "lead orgânico pode esperar um pouco mais."
    )
    pdf.bullet(
        "Por que olhar origem no Portal: se vários leads vêm sem campanha, "
        "o problema é do anúncio — o vendedor deve sinalizar, não “consertar” na mão."
    )
    pdf.bullet(
        "Por que não criar venda “solta” sem lead: o placar de campanha fica "
        "mentiroso (gasto alto, venda zero no ROI)."
    )

    # ── Dono na venda e semanal ──
    pdf.add_page()
    pdf.h1("7. Dono — na hora da venda")
    pdf.flow(
        [
            "Vendedor registrou venda com lead",
            "Dono abre a venda no Portal",
            "Confere lead + moto + preço",
            "Confirmar",
            "Purchase CAPI + ROI atualizados",
        ]
    )
    pdf.bullet(
        "Por que o dono confirma (e não só o vendedor): evita venda “de teste” "
        "ou valor errado mandando Purchase falso para a Meta e sujando o aprendizado."
    )
    pdf.bullet(
        "Por que olhar a auditoria Pixel depois: se deu failed, o token CAPI ou "
        "o Purchase precisa de ajuste — senão a Meta não aprende com a venda real."
    )
    pdf.bullet(
        "Por que não confirmar sem lead: a moto some do ROI da campanha; "
        "parece que o anúncio não funcionou."
    )

    pdf.h1("8. Dono — rotina semanal (~15–20 min)")
    pdf.flow(
        [
            "ROI / Resultados (7 dias ou mês)",
            "Gasto zero? Sync + ID Meta",
            "Pixel delivered? CTWA ok?",
            "Qual campanha tem melhor CPA/ROAS?",
            "Mais budget no que vende · pause o resto",
        ]
    )
    pdf.bullet(
        "Por que toda semana: anúncio ruim queima verba em dias; o placar evita "
        "decidir no feeling do Ads (“muita msg”)."
    )
    pdf.bullet(
        "Por que sync de gasto: sem gasto, ROAS fica “—” e você não sabe se pagou a moto."
    )
    pdf.bullet(
        "Por que comparar CPA e não só volume: CTWA pode ter 100 msgs e 0 moto; "
        "catálogo pode ter 20 msgs e 2 motos — o barato é o que vende."
    )
    pdf.bullet(
        "Por que o vendedor não decide budget: ele não vê custo de mídia completo; "
        "o dono cruza gasto × venda."
    )

    # ── Moto nova ──
    pdf.h1("9. Moto nova no ar")
    pdf.flow(
        [
            "Publicar no estoque",
            "Abrir página no catálogo",
            "Campanha Revy (utm)",
            "Anúncio Ads + UTMs",
            "Teste: lead com UTM",
        ]
    )
    pdf.h2("Dono")
    pdf.bullet("Publica e monta o anúncio — por quê: mídia e etiqueta são dele.")
    pdf.bullet(
        "Faz 1 clique de teste no próprio celular e confere o lead no Portal — "
        "por quê: descobre typo de UTM antes de gastar de verdade."
    )
    pdf.h2("Vendedor")
    pdf.bullet(
        "Só precisa saber que a moto entrou e que leads dessa campanha vão "
        "aparecer — por quê: atende falando do estoque atual, sem configurar ads."
    )

    # ── Ritmo e telas ──
    pdf.add_page()
    pdf.h1("10. Ritmo (calendário)")
    pdf.kv("Uma vez (dono)", "Setup: Pixel, CAPI, ads_read (PDF Setup).")
    pdf.kv("Nova campanha (dono)", "Cadastro Revy + anúncio com UTM ou Cód CTWA.")
    pdf.kv("Todo turno (vendedor)", "Atender leads de ads; não perder código da msg.")
    pdf.kv("Toda venda (ambos)", "Vendedor registra com lead · dono confirma.")
    pdf.kv("Semanal (dono)", "ROI + sync + budget.")
    pdf.kv("Quando algo falhar", "Dono: Tráfego/auditoria. Vendedor: avisa e segue atendendo.")

    pdf.h1("11. Onde cada um olha no Portal")
    pdf.h2("Dono")
    pdf.kv("Tráfego", "Tokens, sync de gasto.")
    pdf.kv("Campanhas / ROI", "Placar e decisão de mídia.")
    pdf.kv("Pixel / CTWA", "Auditoria: sinal e Purchase.")
    pdf.kv("Vendas", "Confirmar.")
    pdf.h2("Vendedor")
    pdf.kv("Leads / conversas", "Quem chegou, origem, moto de interesse.")
    pdf.kv("Vendas", "Registrar com o lead certo (não precisa de Tráfego).")

    pdf.h1("12. Se os números não baterem")
    pdf.kv("Msgs no Ads, poucos leads", "Dono: UTM/código no anúncio. Vendedor: não é culpa do atendimento.")
    pdf.kv("Lead sem campanha", "Dono: typo utm/Cód. Vendedor: avisa, não inventa.")
    pdf.kv("ROAS “—”", "Dono: sync gasto / ID Meta.")
    pdf.kv("Venda fora do ROI", "Vendedor esqueceu o lead ou dono não confirmou.")
    pdf.kv("Muita msg, pouca venda", "Dono: criativo/público. Vendedor: tempo de resposta e qualificação.")

    pdf.ln(3)
    pdf.note(
        "Setup e tokens: PDF “Setup de tráfego pago”. "
        "Criar o anúncio em si: Ads Manager. "
        "Medir se pagou a moto: Revy (ROI + venda confirmada)."
    )

    pdf.save(OUT_FLUXOS, OUT_FLUXOS_DOCS)
    return OUT_FLUXOS


def build_all() -> list[Path]:
    setup = build_setup()
    fluxos = build_fluxos()
    # Remove PDF único antigo se existir (evita confusão)
    for legacy in (OUT_LEGACY, OUT_LEGACY_DOCS):
        if legacy.exists():
            try:
                legacy.unlink()
            except OSError:
                pass
    return [setup, fluxos]


if __name__ == "__main__":
    paths = build_all()
    for p in paths:
        print(p)
        # espelho em docs/
        docs_name = DOCS_DIR / p.name
        if docs_name.exists():
            print(docs_name)
