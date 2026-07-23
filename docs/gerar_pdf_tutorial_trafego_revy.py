#!/usr/bin/env python3
"""Gera PDF: Tutorial de tráfego pago no Revy (Meta, Pixel, CTWA, ROI)."""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output" / "pdf" / "tutorial-revy-trafego-meta.pdf"
OUT_DOCS = Path(__file__).resolve().parent / "tutorial-revy-trafego-meta.pdf"
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
        self.cell(0, 6, "Revy — Tutorial de tráfego pago (Meta)", align="L")
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

    def h1(self, text: str):
        self.ln(3)
        self.set_x(self.l_margin)
        self.set_font("Body", "B", 14)
        self.set_text_color(10, 10, 10)
        self.multi_cell(self._full_w(), 7.5, text)
        self.ln(1)

    def h2(self, text: str):
        self.ln(2.5)
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
        self.ln(0.8)

    def bullet(self, text: str):
        self.set_font("Body", "", 9)
        self.set_text_color(30, 30, 30)
        self.set_x(self.l_margin + 3)
        self.multi_cell(self._full_w() - 3, 5, f"• {text}")
        self.ln(0.2)

    def note(self, text: str):
        self.set_x(self.l_margin)
        self.set_font("Body", "I", 9)
        self.set_text_color(60, 60, 60)
        self.multi_cell(self._full_w(), 5, text)
        self.ln(1)

    def code(self, text: str):
        self.set_x(self.l_margin)
        self.set_font("Body", "", 8)
        self.set_text_color(20, 20, 20)
        self.set_fill_color(245, 245, 245)
        self.multi_cell(self._full_w(), 4.5, text, fill=True)
        self.ln(1.5)

    def kv(self, key: str, value: str):
        self.set_x(self.l_margin)
        self.set_font("Body", "B", 9)
        self.set_text_color(20, 20, 20)
        self.write(5, f"{key}: ")
        self.set_font("Body", "", 9)
        self.set_text_color(35, 35, 35)
        self.multi_cell(self._full_w() - self.get_string_width(f"{key}: "), 5, value)
        self.ln(0.3)


def build() -> Path:
    pdf = Doc()
    pdf.add_page()

    # Capa
    pdf.set_y(40)
    pdf.set_font("Body", "B", 28)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 12, "Revy", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Body", "", 16)
    pdf.set_text_color(50, 50, 50)
    pdf.cell(0, 9, "Tutorial de tráfego pago (Meta)", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Body", "", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(
        pdf._full_w(),
        5.5,
        "O que é cada coisa, o que você precisa preencher e como usar o Portal "
        "para saber se o anúncio pagou a moto.",
    )
    pdf.ln(6)
    y = pdf.get_y()
    pdf.set_draw_color(10, 10, 10)
    pdf.line(pdf.l_margin, y, pdf.l_margin + 50, y)
    pdf.ln(8)
    pdf.set_font("Body", "I", 9)
    pdf.multi_cell(
        pdf._full_w(),
        5,
        "Para dono e gerente. Ads Manager cria o anúncio; o Revy amarra lead, "
        "venda, gasto e retorno. Atualizado para o lab Fly (app2037) com CTWA, "
        "CAPI, gasto automático Meta e auditorias.",
    )
    pdf.ln(10)
    pdf.set_font("Body", "", 9)
    pdf.p("Portal: https://app2037.fly.dev")
    pdf.p("Catálogo (exemplo): https://app2037.fly.dev/loja/...")

    # 1. Ideia geral
    pdf.add_page()
    pdf.h1("1. Em uma frase")
    pdf.p(
        "Você paga anúncio no Instagram/Facebook. O cliente chega no WhatsApp, "
        "a loja vende a moto, e o Revy mostra: quanto gastou, quantos leads, "
        "quantas motos e se valeu a pena."
    )
    pdf.h2("Fluxo completo")
    pdf.code(
        "Anúncio Meta\n"
        "   → Catálogo (vitrine + Pixel)  OU  WhatsApp direto (CTWA)\n"
        "   → Conversa no WhatsApp (bot / vendedor)\n"
        "   → Lead no Revy\n"
        "   → Venda confirmada\n"
        "   → ROI (gasto + faturamento) + aviso à Meta (CAPI)"
    )
    pdf.p(
        "O Ads Manager veicula e gasta. O Revy não cria anúncio: ele amarra "
        "origem → pessoa → venda → real."
    )

    # 2. Glossário
    pdf.h1("2. O que é cada coisa (glossário)")
    pdf.h3("Pixel (Meta Pixel)")
    pdf.p(
        "Código da Meta que roda no site (Catálogo). Serve para a Meta ver quem "
        "visitou a vitrine, viu moto e clicou em WhatsApp. Com isso a Meta monta "
        "públicos e lookalikes (pessoas parecidas)."
    )
    pdf.bullet("Onde vive: páginas do Catálogo no navegador.")
    pdf.bullet("O que você cola no Revy: o Pixel ID (número público).")
    pdf.bullet("Não roda se o anúncio for só WhatsApp direto (sem abrir o site).")

    pdf.h3("CAPI (Conversions API)")
    pdf.p(
        "Envio do servidor do Revy para a Meta: “essa venda (ou lead) aconteceu”. "
        "Mais confiável que o Pixel sozinho (não depende de cookie/bloqueio)."
    )
    pdf.bullet("Purchase web: venda com dados do funil site/CRM.")
    pdf.bullet("Purchase messaging (CTWA): venda com click id do WhatsApp Ads.")
    pdf.bullet("Usa um token secreto (não é o mesmo do gasto de ads).")

    pdf.h3("UTM")
    pdf.p(
        "Etiquetas no link do anúncio (utm_source, utm_medium, utm_campaign…). "
        "A mais importante no Revy é utm_campaign: ela casa o lead com a campanha "
        "cadastrada no Portal."
    )
    pdf.note("Regra de ouro: o texto do utm_campaign no link = o cadastro no Revy (igualzinho).")

    pdf.h3("Campanha (no Revy)")
    pdf.p(
        "Registro interno: nome, canal, UTM, opcionalmente ID da campanha no Meta "
        "e código CTWA. Não cria o anúncio no Ads — só organiza a medição e o gasto."
    )

    pdf.h3("ID da campanha no Meta Ads")
    pdf.p(
        "Número longo da campanha no Gerenciador de Anúncios. Serve para: "
        "(1) puxar o gasto automático e (2) ajudar a casar leads de CTWA."
    )

    pdf.h3("Código CTWA")
    pdf.p(
        "Código curto (ex.: RV-JUL) que você coloca na mensagem pré-preenchida do "
        "anúncio de WhatsApp e no cadastro da campanha no Revy. É o plano B se o "
        "WhatsApp não mandar o click id (ctwa_clid)."
    )

    pdf.h3("CTWA (Click-to-WhatsApp)")
    pdf.p(
        "Anúncio que abre o WhatsApp na hora, sem passar pelo site. Gera mais "
        "conversa; o Pixel de página não roda. O Revy amarra com ctwa_clid (se a "
        "Evolution entregar) e/ou com o código da mensagem."
    )

    pdf.h3("ctwa_clid")
    pdf.p(
        "Identificador do clique do anúncio de WhatsApp. Com ele, na venda, o Revy "
        "pode avisar a Meta (CAPI messaging) com mais precisão. Se não chegar, use "
        "o código na mensagem e veja a auditoria CTWA."
    )

    pdf.h3("Gasto automático (Marketing API / ads_read)")
    pdf.p(
        "O Revy consulta a Meta e grava quanto cada campanha gastou, sem você digitar "
        "toda semana. Precisa de Ad Account ID + token com permissão ads_read "
        "(diferente do token CAPI)."
    )

    pdf.h3("ROI / ROAS / CPL / CPA")
    pdf.bullet("CPL: gasto ÷ leads da campanha.")
    pdf.bullet("CPA (custo por moto): gasto ÷ vendas atribuídas.")
    pdf.bullet("ROAS: faturamento das vendas ÷ gasto (ex.: 5x = R$5 de venda por R$1 de ads).")
    pdf.bullet("Se gasto = 0, ROAS aparece “—” (falta sync ou ID Meta na campanha).")

    pdf.h3("Auditoria CTWA e Auditoria Pixel")
    pdf.p(
        "Telas do Portal para ver se os sinais estão chegando. CTWA: se o click id "
        "ou código entrou no webhook. Pixel: se o CAPI montou as chaves certas "
        "(telefone hash, fbc, ctwa_clid…) e se a Meta aceitou o envio."
    )

    # 3. Dois caminhos de anúncio
    pdf.add_page()
    pdf.h1("3. Dois caminhos de anúncio")
    pdf.h2("A) Anúncio → Catálogo → WhatsApp (recomendado para medir bem)")
    pdf.p(
        "O cliente vê a moto no site, o Pixel registra, o CTA abre o WhatsApp com "
        "código de interesse e UTMs. Melhor para persona, remarketing e ROI por UTM."
    )
    pdf.h2("B) Anúncio → WhatsApp direto (CTWA)")
    pdf.p(
        "Mais volume de conversa. Use código na mensagem e ID Meta na campanha. "
        "Use a persona do Pixel em públicos/lookalike no Ads Manager para CTWA "
        "mais qualificado."
    )
    pdf.h2("Híbrido (o que a loja madura faz)")
    pdf.bullet("Parte do budget em catálogo (aprender + medir).")
    pdf.bullet("Parte em CTWA mirando quem já visitou ou lookalike de compradores.")
    pdf.bullet("Gasto Meta entra sozinho no Revy; venda confirmada fecha o placar.")

    # 4. O que preencher (tabela conceitual)
    pdf.h1("4. O que você precisa da Meta (e para quê)")
    pdf.h3("1. Pixel ID")
    pdf.kv("Para quê", "Ativar o Pixel no Catálogo (browser) e alinhar o CAPI.")
    pdf.kv("Onde pegar", "Meta Events Manager → seu Pixel → ID numérico.")
    pdf.kv(
        "Onde colar",
        "Só no Portal → Tráfego → Pixel ID. O Catálogo puxa sozinho (por loja).",
    )
    pdf.note(
        "Você não precisa configurar secret no servidor do Catálogo. "
        "Salvou no Portal = já vale na vitrine."
    )

    pdf.h3("2. Token CAPI")
    pdf.kv("Para quê", "Servidor avisar a Meta nas vendas (Purchase).")
    pdf.kv("Onde pegar", "Events Manager → Configurações do dataset → Gerar token de acesso.")
    pdf.kv("Onde colar", "Portal → Tráfego → Token CAPI (campo senha).")
    pdf.note("Nunca coloque o token CAPI no Catálogo ou no navegador.")

    pdf.h3("3. Ad Account ID")
    pdf.kv("Para quê", "Saber de qual conta de anúncios puxar o gasto.")
    pdf.kv("Onde pegar", "Ads Manager → configurações da conta (act_123… ou só números).")
    pdf.kv("Onde colar", "Portal → Tráfego → Gasto automático → Ad Account ID.")

    pdf.h3("4. Token ads_read (Marketing API)")
    pdf.kv("Para quê", "Ler spend (gasto) das campanhas automaticamente.")
    pdf.kv("Onde pegar", "Business Manager → Usuários do sistema → token com ads_read.")
    pdf.kv("Onde colar", "Portal → Tráfego → Token Marketing API.")
    pdf.note("É OUTRO token. CAPI ≠ ads_read.")

    pdf.h3("5. ID da campanha no Meta")
    pdf.kv("Para quê", "Ligar gasto da Meta à campanha do Revy (e ajudar CTWA).")
    pdf.kv("Onde pegar", "Ads Manager → campanha → copiar ID.")
    pdf.kv("Onde colar", "Portal → Campanhas → editar → ID da campanha no Meta Ads.")

    pdf.h3("6. utm_campaign")
    pdf.kv("Para quê", "Casar o clique do site com a campanha do CRM.")
    pdf.kv("Onde usar", "URL do anúncio que aponta para o catálogo.")
    pdf.kv("Onde colar", "Portal → Campanhas → campo utm_campaign (mesmo texto).")

    pdf.h3("7. Código CTWA (ex.: RV-JUL)")
    pdf.kv("Para quê", "Casar anúncio de WhatsApp direto sem depender só do clid.")
    pdf.kv("Onde usar", "Mensagem pré-preenchida do anúncio: “Cód: RV-JUL”.")
    pdf.kv("Onde colar", "Portal → Campanhas → Código CTWA.")

    # 5. Passo a passo
    pdf.add_page()
    pdf.h1("5. Passo a passo — configurar uma vez")
    pdf.h2("Passo 1 — Tráfego: Pixel e CAPI")
    pdf.bullet("Menu Tráfego.")
    pdf.bullet("Preencha Pixel ID + Token CAPI.")
    pdf.bullet("Deixe ligados: PageView, Lead, Purchase.")
    pdf.bullet("Salvar Pixel / CAPI.")
    pdf.bullet("Confira no menu Pixel: deve aparecer “config_salva”.")
    pdf.p(
        "Pronto: o Catálogo busca esse Pixel ID sozinho na vitrine da sua loja. "
        "Não precisa pedir secret no servidor nem copiar o ID em outro lugar."
    )

    pdf.h2("Passo 2 — Tráfego: gasto automático")
    pdf.bullet("Ad Account ID + token ads_read.")
    pdf.bullet("Sync habilitada → Salvar conta de anúncios.")
    pdf.bullet("Depois: “Sincronizar gastos agora” ou espere o job diário (~24h).")

    pdf.h2("Passo 3 — Cadastrar campanha no Revy")
    pdf.bullet("Campanhas → Nova.")
    pdf.bullet("Nome interno (só para você).")
    pdf.bullet("Canal: Meta.")
    pdf.bullet("utm_campaign: texto do link (ex. seminovos-julho).")
    pdf.bullet("ID Meta: da campanha no Ads.")
    pdf.bullet("Código CTWA: se for anúncio de WhatsApp direto.")
    pdf.bullet("Salvar.")

    pdf.h2("Passo 4 — Montar o anúncio")
    pdf.h3("Se for para o catálogo")
    pdf.code(
        "https://app2037.fly.dev/loja/SUA-LOJA/veiculos/ID"
        "?utm_source=instagram&utm_medium=paid&utm_campaign=seminovos-julho"
    )
    pdf.h3("Se for CTWA (WhatsApp direto)")
    pdf.bullet("Destino: WhatsApp da loja.")
    pdf.bullet("Mensagem inicial com: Cód: RV-JUL (igual ao cadastro).")

    pdf.h1("6. Uso no dia a dia")
    pdf.bullet("Segunda: olhe ROI e Resultados (gasto, leads, motos, ROAS).")
    pdf.bullet("Se gasto zerado: sincronizar ou conferir ID Meta na campanha.")
    pdf.bullet("Menu CTWA: clid chegou? código chegou?")
    pdf.bullet("Menu Pixel: venda gerou purchase + envio delivered?")
    pdf.bullet("Venda só conta no ROI da campanha se estiver com lead amarrado.")
    pdf.bullet("Gasto manual só se for canal sem Meta (OLX etc.) ou correção.")

    pdf.h1("7. Telas do Portal (mapa)")
    pdf.kv("Tráfego", "Pixel, CAPI, conta de ads, sync de gasto.")
    pdf.kv("Campanhas", "Cadastro e detalhe; gastos Meta ou manuais.")
    pdf.kv("ROI", "CPL, CPA, ROAS por campanha e período.")
    pdf.kv("CTWA", "Auditoria: sinais do anúncio de WhatsApp.")
    pdf.kv("Pixel", "Auditoria: chaves CAPI e status de envio.")
    pdf.kv("Leads", "Origem, UTM, bloco WhatsApp Ads.")
    pdf.kv("Vendas", "Confirmar venda dispara CAPI e fecha ROI.")

    pdf.add_page()
    pdf.h1("8. Checklist “está amarrado?”")
    pdf.bullet("1. Pixel ID + CAPI salvos em Tráfego (Catálogo puxa sozinho).")
    pdf.bullet("2. Token CAPI com Purchase ligado.")
    pdf.bullet("3. Ad Account + ads_read salvos.")
    pdf.bullet("4. Campanha com utm_campaign e/ou ID Meta e/ou código CTWA.")
    pdf.bullet("5. Link do anúncio com o mesmo utm_campaign (caminho catálogo).")
    pdf.bullet("6. CTWA com Cód: na mensagem (caminho zap).")
    pdf.bullet("7. Lead aparece com origem/UTM ou meta_ctwa.")
    pdf.bullet("8. Sync de gasto preencheu valores Meta.")
    pdf.bullet("9. Venda confirmada com lead → ROI e auditoria Pixel.")

    pdf.h1("9. Problemas comuns")
    pdf.h3("Ads tem muitas msgs, Revy tem poucos leads")
    pdf.p("Link sem UTM, WA direto no bio, ou bot ignorando contato já salvo.")
    pdf.h3("Lead sem campanha")
    pdf.p("Typo no utm_campaign ou código CTWA diferente do cadastro.")
    pdf.h3("ROAS “—”")
    pdf.p("Sem gasto no período: sync, ID Meta, ou campanha sem ads_read.")
    pdf.h3("clid? = não na auditoria CTWA")
    pdf.p(
        "Evolution/n8n não entregou ctwa_clid. Use código na mensagem; "
        "confirme workflow n8n atualizado."
    )
    pdf.h3("CAPI falhou na auditoria Pixel")
    pdf.p("Token inválido, Purchase desligado, ou erro HTTP — retente em Tráfego.")
    pdf.h3("Venda sem campanha no ROI")
    pdf.p("Venda sem lead_ref ou confirmada antes do match de UTM/CTWA.")

    pdf.h1("10. O que o Revy não faz")
    pdf.bullet("Não cria, pausa ou edita anúncio no Meta/Google.")
    pdf.bullet("Não puxa gasto do Google Ads (só Meta, se configurado).")
    pdf.bullet("Não gerencia posts do Instagram.")
    pdf.bullet("Não promete multi-touch perfeito: first/last touch honestos.")

    pdf.h1("11. Resumo para o dono")
    pdf.p(
        "Configure Pixel + CAPI uma vez no Portal (a vitrine já herda o Pixel). "
        "Conecte a conta de anúncios uma vez. "
        "Cadastre cada campanha com o mesmo nome de UTM (e ID Meta / código CTWA). "
        "Venda com lead no Portal. O Revy mostra se o anúncio pagou a moto."
    )
    pdf.ln(4)
    pdf.note(
        "Dúvida de setup: Tráfego + Campanhas + telas CTWA e Pixel. "
        "Dúvida de anúncio: Ads Manager. Os dois se complementam."
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT))
    pdf.output(str(OUT_DOCS))
    return OUT


if __name__ == "__main__":
    path = build()
    print(path)
    print(OUT_DOCS)
