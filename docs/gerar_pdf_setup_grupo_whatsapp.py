#!/usr/bin/env python3
"""Gera o guia visual de configuração do grupo de estoque no WhatsApp."""

from pathlib import Path

from fpdf import FPDF


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output" / "pdf" / "setup-grupo-whatsapp-estoque.pdf"
FONT_DIR = Path(r"C:\Windows\Fonts")


class Guia(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.add_font("Body", "", str(FONT_DIR / "arial.ttf"))
        self.add_font("Body", "B", str(FONT_DIR / "arialbd.ttf"))
        self.add_font("Body", "I", str(FONT_DIR / "ariali.ttf"))
        self.set_margins(16, 16, 16)
        self.set_auto_page_break(auto=True, margin=17)

    @property
    def usable_width(self):
        return self.w - self.l_margin - self.r_margin

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Body", "", 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, "Revy | Setup do grupo de estoque", align="L")
        self.cell(0, 5, f"p. {self.page_no()}", align="R", ln=1)
        self.set_draw_color(220, 220, 220)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(5)

    def footer(self):
        self.set_y(-12)
        self.set_font("Body", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 6, "Uso interno da loja | atualizado em 24/07/2026", align="C")

    def heading(self, text):
        self.set_font("Body", "B", 18)
        self.set_text_color(18, 18, 18)
        self.multi_cell(self.usable_width, 9, text)
        self.ln(2)

    def h2(self, text):
        self.ln(2)
        self.set_font("Body", "B", 12)
        self.set_text_color(20, 20, 20)
        self.multi_cell(self.usable_width, 7, text)
        self.ln(1)

    def p(self, text, *, bold=False):
        self.set_font("Body", "B" if bold else "", 9.5)
        self.set_text_color(38, 38, 38)
        self.multi_cell(self.usable_width, 5.2, text)
        self.ln(1)

    def step(self, number, title, detail):
        y = self.get_y()
        self.set_fill_color(20, 20, 20)
        self.set_text_color(255, 255, 255)
        self.set_font("Body", "B", 10)
        self.ellipse(self.l_margin, y, 9, 9, style="F")
        self.set_xy(self.l_margin, y + 1.2)
        self.cell(9, 6.5, str(number), align="C")
        self.set_xy(self.l_margin + 13, y)
        self.set_text_color(20, 20, 20)
        self.set_font("Body", "B", 10)
        self.cell(self.usable_width - 13, 5, title, ln=1)
        self.set_x(self.l_margin + 13)
        self.set_font("Body", "", 9)
        self.set_text_color(55, 55, 55)
        self.multi_cell(self.usable_width - 13, 4.8, detail)
        self.ln(3)

    def status_box(self, title, lines, *, ok=True):
        x = self.get_x()
        y = self.get_y()
        width = self.usable_width
        height = 13 + (len(lines) * 5)
        if ok:
            self.set_fill_color(236, 247, 239)
            self.set_draw_color(87, 155, 104)
        else:
            self.set_fill_color(248, 241, 235)
            self.set_draw_color(177, 123, 78)
        self.rect(x, y, width, height, style="DF")
        self.set_xy(x + 4, y + 3)
        self.set_font("Body", "B", 10)
        self.set_text_color(25, 25, 25)
        self.cell(width - 8, 5, title, ln=1)
        self.set_font("Body", "", 9)
        for line in lines:
            self.set_x(x + 4)
            self.cell(width - 8, 5, f"- {line}", ln=1)
        self.set_y(y + height + 4)

    def flow(self, steps):
        box_width = 122
        box_height = 9
        x = self.l_margin + (self.usable_width - box_width) / 2
        for index, label in enumerate(steps):
            y = self.get_y()
            self.set_fill_color(247, 247, 247)
            self.set_draw_color(80, 80, 80)
            self.rect(x, y, box_width, box_height, style="DF")
            self.set_xy(x + 3, y + 2)
            self.set_font("Body", "", 9)
            self.set_text_color(25, 25, 25)
            self.cell(box_width - 6, 5, label, align="C")
            self.set_y(y + box_height)
            if index < len(steps) - 1:
                middle = x + box_width / 2
                self.line(middle, self.get_y(), middle, self.get_y() + 5)
                self.set_y(self.get_y() + 5)


def build():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf = Guia()

    pdf.add_page()
    pdf.set_y(43)
    pdf.set_font("Body", "B", 27)
    pdf.set_text_color(12, 12, 12)
    pdf.cell(0, 12, "Revy", ln=1)
    pdf.set_font("Body", "", 17)
    pdf.cell(0, 10, "Setup do grupo de estoque no WhatsApp", ln=1)
    pdf.ln(7)
    pdf.set_draw_color(25, 25, 25)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + 55, pdf.get_y())
    pdf.ln(9)
    pdf.p(
        "Configure um único grupo para cadastrar veículos, consultar o estoque e enviar fotos. "
        "Imagens privadas e mensagens de outros grupos ficam fora do catálogo."
    )
    pdf.ln(10)
    pdf.status_box(
        "Resultado esperado",
        [
            "somente o grupo escolhido abre o menu de estoque",
            "foto privada não recebe resposta do bot",
            "foto de outro grupo não recebe resposta do bot",
            "o backend valida o grupo antes de baixar a mídia",
        ],
    )

    pdf.add_page()
    pdf.heading("1. Escolher o grupo no Portal")
    pdf.step(1, "Entre como dono ou gerente", "Abra o Portal Revy com uma conta que possa administrar a operação.")
    pdf.step(2, "Abra Grupo do estoque", "No menu lateral, em Configurações, escolha Grupo do estoque.")
    pdf.step(3, "Escolha Grupo autorizado", "A lista mostra os grupos encontrados na instância de WhatsApp conectada à loja.")
    pdf.step(4, "Clique em Salvar grupo", "O status da tela deve mostrar o nome e o identificador do grupo selecionado.")
    pdf.step(5, "Teste no WhatsApp", "No grupo escolhido, envie menu. O bot deve responder com as opções 1 a 5 e 0 para sair.")
    pdf.h2("Atenção ao trocar o grupo")
    pdf.p(
        "Ao selecionar outro grupo, o Revy encerra a sessão anterior de menu e de fotos. "
        "O grupo antigo passa a ser ignorado imediatamente."
    )
    pdf.status_box(
        "Se o grupo não aparecer na lista",
        [
            "confirme que a instância do WhatsApp está conectada",
            "confirme que a conta participa do grupo",
            "recarregue a tela Grupo do estoque",
        ],
        ok=False,
    )

    pdf.add_page()
    pdf.heading("2. Usar o menu e enviar fotos")
    pdf.flow(
        [
            "Equipe envia menu no grupo selecionado",
            "Bot mostra as opções do estoque",
            "Equipe envia os dados do veículo",
            "Revy cadastra e abre a sessão de fotos",
            "Fotos do grupo entram no Estoque e no Catálogo",
        ]
    )
    pdf.ln(7)
    pdf.h2("Opções do menu")
    pdf.p("1 - Cadastrar veículo   2 - Ver veículos   3 - Editar veículo")
    pdf.p("4 - Despublicar   5 - Marcar como vendido   0 - Sair")
    pdf.h2("Regra das fotos")
    pdf.p(
        "Para um veículo já existente, envie a primeira foto com a placa na legenda, por exemplo ABC1D23. "
        "Durante os 10 minutos seguintes, as outras fotos do mesmo veículo podem ser enviadas sem repetir a placa."
    )
    pdf.status_box(
        "Aceito",
        [
            "texto e menu dentro do grupo selecionado",
            "foto dentro do grupo selecionado",
            "qualquer participante do grupo pode continuar a sessão",
        ],
    )
    pdf.status_box(
        "Ignorado sem resposta",
        [
            "foto enviada em conversa privada",
            "foto enviada em outro grupo",
            "mensagem enviada pelo próprio bot no grupo",
        ],
        ok=False,
    )

    pdf.output(str(OUT))
    print(OUT)


if __name__ == "__main__":
    build()
