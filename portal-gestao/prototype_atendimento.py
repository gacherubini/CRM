r"""Runner local dos previews da Loja, com templates reais e dados fictícios.

Windows: .\.venv\Scripts\python.exe prototype_atendimento.py
macOS: .venv/bin/python prototype_atendimento.py
Não importa app/config/main, não lê .env, não conecta integrações. SQLite em memória.
"""
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace as NS
import argparse
import re
import sqlite3

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
import uvicorn

ROOT = Path(__file__).resolve().parent
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.state.prototype_atendimento = True  # Único local que habilita o gancho.
db = sqlite3.connect(':memory:', check_same_thread=False)
db.execute('CREATE TABLE mensagens (direcao TEXT, texto TEXT, hora TEXT)')
db.executemany('INSERT INTO mensagens VALUES (?, ?, ?)', [
    ('entrada', 'Oi! Vi a Fazer azul no anúncio. Ainda está disponível?', '10:12'),
    ('saida', 'Olá, Marina! A Fazer FZ25 2024 está disponível, sim. Você pensa em financiar?', '10:12'),
    ('entrada', 'Sim! Tenho R$ 6 mil para dar de entrada. Uso a moto para trabalhar.', '10:14'),
    ('saida', 'Entendi. Vou chamar alguém da equipe para seguir com a simulação e tirar suas dúvidas.', '10:14'),
    ('entrada', 'Perfeito. Se der certo, consigo passar aí amanhã de manhã.', '10:15'),
    ('entrada', 'Pode ver as opções para mim?', '10:16'),
])
env = Environment(loader=FileSystemLoader(ROOT / 'app/templates'), autoescape=select_autoescape())
app.mount('/static', StaticFiles(directory=ROOT / 'app/static'), name='static')


@app.middleware('http')
async def local_only(request: Request, call_next):
    if request.method not in ('GET', 'HEAD'):
        return PlainTextResponse('Demonstração: nenhuma alteração é persistida.', status_code=405)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
        "font-src 'self'; img-src 'self' data:; connect-src 'none'; form-action 'none'; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    )
    return response


@app.get('/')
@app.get('/app/loja/atendimento')
async def index():
    return RedirectResponse('/app/loja/agente?periodo=mes')


def _shell_demo(request: Request):
    nav = [NS(title=title, items=[NS(label=label, href=href) for label, href in items]) for title, items in [
        ('Vendas', [('Resultado', '/app/loja/vendas'), ('Atendimento', '/app/loja/atendimento'),
                    ('Vendas da loja', '/app/loja/vendas/lista'), ('Agente do WhatsApp', '/app/loja/agente'),
                    ('Simulações', '/app/simulacoes')]),
        ('Estoque', [('Situação do estoque', '/app/loja/estoque'), ('Veículos', '/app/loja/estoque/veiculos'),
                     ('Vitrine', '/app/loja/estoque/vitrine')]),
        ('Ajustes', [('Equipe', '/app/equipe'), ('Acessos dos bancos', '/app/financeiras')]),
    ]]
    return dict(
        request=request, loja_shell=True, loja_brand='Revy Loja', loja_nav=nav,
        nav_item_is_active=lambda item, path: False,
        usuario=NS(nome='Rafael Demo', email='rafael@example.invalid', papel='gerente', loja_slug='Horizonte Motos'),
        store_context=NS(loja_slug='Horizonte Motos'), lojas_disponiveis=[],
        entitlements=NS(vendas_enabled=True, estoque_enabled=True), csrf='',
    )


@app.get('/app/loja/agente', response_class=HTMLResponse)
async def agente_demo(request: Request):
    # Task 5 definitiva: template real com dados fictícios e sem persistência.
    chave = request.query_params.get('periodo', 'mes')
    hoje = date.today()
    if chave == 'hoje':
        inicio, rotulo, vazio = hoje, 'Hoje', 'hoje'
    elif chave == 'semana':
        inicio, rotulo, vazio = hoje - timedelta(days=6), 'Últimos 7 dias', 'nos últimos 7 dias'
    else:
        chave, inicio, rotulo, vazio = 'mes', hoje.replace(day=1), 'Este mês', 'neste mês'
    valores = (4, 7, 1, 9, 12, 5, 8, 3, 10)
    serie = []
    for i in range((hoje - inicio).days + 1):
        valor = valores[i % len(valores)]
        serie.append(NS(dia=f'{(inicio + timedelta(days=i)).day:02d}', atendimentos=valor,
                        altura=round(valor / 12 * 100), pico=valor == 12))
    context = _shell_demo(request)
    context.update(
        nav_item_is_active=lambda item, path: item.href == '/app/loja/agente',
        agente_config_habilitado=True, erro_resumo=None,
        periodo=NS(chave=chave, inicio=inicio, fim=hoje, rotulo=rotulo, vazio=vazio),
        visao=NS(atendimentos=65, so_agente=27, transferidos=38,
                 so_agente_pct=.42, transferidos_pct=.58, serie=serie,
                 maximo=12, pico=NS(atendimentos=12, dia='05')),
        card_rodizio=NS(oferecidos=18, atendidos=11, aguardando=4, perdidos=3),
    )
    html = env.get_template('loja/agente.html').render(**context)
    html = re.sub(r'<link\b[^>]*https://fonts\.(?:googleapis|gstatic)\.com[^>]*>', '', html)
    return HTMLResponse(html)


@app.get('/app/loja/estoque/demo', response_class=HTMLResponse)
async def estoque_demo(request: Request):
    # Direcao "patio" definitiva desde 09/09: o demo rende o template real
    # com dados ficticios. Sem ?variant= — os prototipos A/B foram aposentados.
    context = _shell_demo(request)
    context.update(
        caminho_veiculos='/app/loja/estoque/veiculos', caminho_novo='/app/loja/estoque/veiculos/novo',
        pode_gerir=True,
        overview=NS(status='ok',
                     contagens=NS(disponivel=14, reservado=3, vendido=5, publicados=11, total=22),
                     idade=NS(com_data=15, sem_data=2, ate_30=6, de_31_a_60=4, de_61_a_90=3, acima_90=2)),
    )
    html = env.get_template('loja/estoque_visao.html').render(**context)
    html = re.sub(r'<link\b[^>]*https://fonts\.(?:googleapis|gstatic)\.com[^>]*>', '', html)
    return HTMLResponse(html)


@app.get('/app/loja/vitrine/demo', response_class=HTMLResponse)
async def vitrine_demo(request: Request):
    # Task 3: rende o template real com dados ficticios (sem persistencia).
    context = _shell_demo(request)
    veiculos = [
        NS(id='v1', foto_url=None, midia_principal=None, marca='Honda',
           modelo='CG 160 Fan', tipo='moto', ano_modelo=2024, km=12500, preco=18900),
        NS(id='v2', foto_url=None, midia_principal=None, marca='Yamaha',
           modelo='Fazer FZ25', tipo='moto', ano_modelo=2023, km=20800, preco=21500),
        NS(id='v3', foto_url=None, midia_principal=None, marca='Honda',
           modelo='NXR 160 Bros', tipo='moto', ano_modelo=2024, km=8300, preco=22400),
        NS(id='v4', foto_url=None, midia_principal=None, marca='Yamaha',
           modelo='Factor 150', tipo='moto', ano_modelo=2022, km=31400, preco=15900),
        NS(id='v5', foto_url=None, midia_principal=None, marca='Honda',
           modelo='CB 300F Twister', tipo='moto', ano_modelo=2023, km=15600, preco=24900),
    ]
    context.update(
        pode_gerir=True, csrf='',
        veiculos=veiculos, all_ids=[v.id for v in veiculos],
        total_items=len(veiculos), limit=12, offset=0,
        previous_url=None, next_url=None,
        page_links=[{'kind': 'page', 'number': 1, 'url': '#', 'current': True}],
        showing_from=1, showing_to=len(veiculos),
        erro=None, mensagem=None,
        catalogo_whatsapp='(11) 98888-7777',
        catalogo_url='https://revyapp.com.br/catalogo/l/horizonte-motos',
        catalogo_erro=None, catalogo_mensagem=None,
    )
    html = env.get_template('loja/vitrine_ordem.html').render(**context)
    html = re.sub(r'<link\b[^>]*https://fonts\.(?:googleapis|gstatic)\.com[^>]*>', '', html)
    return HTMLResponse(html)


@app.get('/app/loja/atendimento/{workspace_id}', response_class=HTMLResponse)
async def workspace(request: Request, workspace_id: str):
    variant = request.query_params.get('variant', 'A').upper()
    if variant not in ('A', 'B', 'C'):
        variant = 'A'
    nav = [NS(title=title, items=[NS(label=label, href=href) for label, href in items]) for title, items in [
        ('Vendas', [('Resultado', '/app/loja/vendas'), ('Atendimento', '/app/loja/atendimento'),
                    ('Vendas da loja', '/app/loja/vendas/lista'), ('Agente do WhatsApp', '/app/loja/agente'),
                    ('Simulações', '/app/simulacoes')]),
        ('Estoque', [('Situação do estoque', '/app/loja/estoque'), ('Veículos', '/app/loja/estoque/veiculos'),
                     ('Vitrine', '/app/loja/estoque/vitrine')]),
        ('Ajustes', [('Equipe', '/app/equipe'), ('Acessos dos bancos', '/app/financeiras')]),
    ]]
    context = dict(
        request=request, variant=variant, loja_shell=True, loja_brand='Revy Loja', loja_nav=nav,
        nav_item_is_active=lambda item, path: item.href == '/app/loja/atendimento',
        usuario=NS(nome='Rafael Demo', email='rafael@example.invalid', papel='gerente', loja_slug='Horizonte Motos'),
        store_context=NS(loja_slug='Horizonte Motos'), lojas_disponiveis=[],
        entitlements=NS(vendas_enabled=True, estoque_enabled=True), csrf='',
        # Helpers que o template real espera (versões fictícias, sem backend).
        mascarar_telefone=lambda t: t, formatar_horario=lambda v: v or '',
        pode_enviar=True, pode_handoff=True, pode_atualizar_etapa=False,
        origem_lead=None, etapas={},
        workspace=NS(id=workspace_id, nome='Marina Demo', telefone='(00) 00000-0142',
                     canal_label='WhatsApp da loja', veiculo_interesse='Yamaha Fazer FZ25',
                     estado='aguardando_simulacao', estado_label='Aguardando simulação',
                     canal_estado='conectado', canal_ativo=True, canal_id=None, lead=None,
                     assignment=NS(vendedor_email='rafael@example.invalid'),
                     venda_status=None, erros_bloco=None, envio_bloqueado_canal=False,
                     conversa_resumo=NS(bot_ativo=False),
                     mensagens=[NS(direcao=d, texto=t, hora=h, criada_em=h, id=None)
                                for d, t, h in db.execute('SELECT * FROM mensagens')]),
    )
    html = env.get_template('loja/atendimento_workspace.html').render(**context)
    # O shell mantém sua fonte/fallback; estes links externos não fazem parte da demo offline.
    html = re.sub(r'<link\b[^>]*https://fonts\.(?:googleapis|gstatic)\.com[^>]*>', '', html)
    return HTMLResponse(html)


QR_FICTICIO = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 29 29'%3E"
    "%3Crect width='29' height='29' fill='white'/%3E"
    "%3Cg fill='black'%3E%3Crect x='2' y='2' width='7' height='7'/%3E"
    "%3Crect x='20' y='2' width='7' height='7'/%3E%3Crect x='2' y='20' width='7' height='7'/%3E"
    "%3C/g%3E%3Cg fill='white'%3E%3Crect x='3' y='3' width='5' height='5'/%3E"
    "%3Crect x='21' y='3' width='5' height='5'/%3E%3Crect x='3' y='21' width='5' height='5'/%3E"
    "%3C/g%3E%3Cg fill='black'%3E%3Crect x='4' y='4' width='3' height='3'/%3E"
    "%3Crect x='22' y='4' width='3' height='3'/%3E%3Crect x='4' y='22' width='3' height='3'/%3E"
    "%3Cpath d='M11 3h2v1h-2zM14 5h1v2h-1zM11 8h1v1h-1zM16 10h2v2h-2zM12 13h1v1h-1z"
    "M24 12h1v2h-1zM11 16h2v1h-2zM18 18h1v1h-1zM25 20h1v1h-1zM13 22h1v2h-1z"
    "M17 24h2v1h-2zM24 25h1v1h-1zM11 26h1v1h-1z'/%3E%3C/g%3E%3C/svg%3E"
)


@app.get('/app/loja/whatsapp/demo', response_class=HTMLResponse)
async def whatsapp_demo(request: Request):
    # Task 6 definitiva (direcao B): rende o template real com dados ficticios
    # e sem persistencia. ?modo=1|2|2novo troca o cenario; ?variant= legado e
    # ignorado. Sem ?variant= — os prototipos A/B/C foram aposentados.
    modo_param = request.query_params.get('modo', '1')
    if modo_param not in ('1', '2', '2novo'):
        modo_param = '1'
    cloud = modo_param == '2'
    if modo_param == '2novo':
        canais = []
        qr, view = None, NS(baileys=False, erro=None, canais=canais,
                            mostrar_link_conectar=True, pode_adicionar=False)
    elif cloud:
        canais = [NS(id='n1', label='Central Revy na nuvem', estado='cloud_pendente',
                      rotulo='Conectado — aguardando liberação da Revy',
                      principal_estoque=False,
                      pode_conectar=False, pode_desconectar=False,
                      pode_marcar_principal_estoque=False,
                      onboarding_texto='Tudo feito do seu lado — falta a liberação da Revy.',
                      onboarding_falhou=False,
                      onboarding_acao='Enquanto isso, monte a fila de vendedores que atende as conversas.',
                      onboarding_acao_url='/app/loja/whatsapp/fila', pode_tentar_de_novo=False)]
        qr, view = None, NS(baileys=False, erro=None, canais=canais,
                            mostrar_link_conectar=False, pode_adicionar=False)
    else:
        canais = [
            NS(id='c1', label='Linha 1 \u2014 vendas', estado='conectado',
               rotulo='Conectado', principal_estoque=True,
               pode_conectar=False, pode_desconectar=True,
               pode_marcar_principal_estoque=False,
               onboarding_texto='', onboarding_falhou=False, onboarding_acao='',
               onboarding_acao_url='', pode_tentar_de_novo=False),
            NS(id='c2', label='Linha 2 \u2014 suporte', estado='pendente',
               rotulo='Aguardando leitura do QR', principal_estoque=False,
               pode_conectar=True, pode_desconectar=False,
               pode_marcar_principal_estoque=True,
               onboarding_texto='', onboarding_falhou=False, onboarding_acao='',
               onboarding_acao_url='', pode_tentar_de_novo=False),
            NS(id='c3', label='Linha 3 \u2014 pe\u00e7as', estado='desconectado',
               rotulo='Caiu \u2014 reconectar', principal_estoque=False,
               pode_conectar=True, pode_desconectar=False,
               pode_marcar_principal_estoque=True,
               onboarding_texto='', onboarding_falhou=False, onboarding_acao='',
               onboarding_acao_url='', pode_tentar_de_novo=False),
        ]
        qr = NS(canal_id='c2', payload=QR_FICTICIO)
        view = NS(baileys=True, erro=None, canais=canais,
                  mostrar_link_conectar=False, pode_adicionar=True)
    context = _shell_demo(request)
    context.update(
        nav_item_is_active=lambda item, path: False,
        view=view, qr=qr, csrf='demonstracao',
        acao_erro=None, acao_mensagem=None,
    )
    html = env.get_template('loja/whatsapp_canais.html').render(**context)
    html = re.sub(r'<link\b[^>]*https://fonts\.(?:googleapis|gstatic)\.com[^>]*>', '', html)
    return HTMLResponse(html)


@app.get('/app/loja/vendas/demo', response_class=HTMLResponse)
async def vendas_demo(request: Request):
    # Task 7 (direcao "balanco"): rende o template real com dados ficticios
    # e sem persistencia. Cenario rico: margem incompleta + aquisicao ok.
    hoje = date.today()
    inicio = hoje.replace(day=1)

    def formatar_brl(valor):
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            return '—'
        texto = f'{numero:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')
        return f'R$ {texto}'

    def formatar_data(iso):
        if not iso:
            return ''
        try:
            return date.fromisoformat(str(iso)[:10]).strftime('%d/%m/%Y')
        except ValueError:
            return str(iso)

    overview = NS(
        escopo='loja', vendas_status='ok', qtd_vendas=12, receita=243500.0,
        margem_completa=False, vendas_lucro_incompleto=2, margem=31200.0,
        funil_status='ok', leads_count=48,
        funil=NS(taxa_resposta_pct=62, taxa_conversao_pct=25,
                 auditavel=NS(disponivel=True, atendidos=31, vendas_vinculadas=9)),
        aquisicao_status='ok',
        aquisicao=NS(investimento_disponivel=True, investimento=5200.0,
                     cac_disponivel=True, cac=433.33,
                     roas_disponivel=True, roas=46.83, mensagem=None),
        aquisicao_campanhas=[
            NS(nome='Civic — julho', canal='Meta', gasto=2100.0, leads=19,
               vendas=4, faturamento=86200.0, roas=41.05),
            NS(nome='Fazer — agosto', canal='Meta', gasto=1750.0, leads=14,
               vendas=3, faturamento=64800.0, roas=37.03),
            NS(nome='Bros — vitrine', canal='Catálogo', gasto=None, leads=6,
               vendas=2, faturamento=44900.0, roas=None),
        ],
        aquisicao_canais=[NS(canal='Meta', gasto=3850.0, roas=39.17)],
        aquisicao_origens=[
            NS(rotulo='Anúncio', nota='9 sem identificação de campanha', leads=27, share='56.3'),
            NS(rotulo='Link direto', nota=None, leads=12, share='25.0'),
            NS(rotulo='Catálogo', nota=None, leads=6, share='12.5'),
            NS(rotulo='Procurou no WhatsApp', nota=None, leads=3, share='6.2'),
        ],
    )
    context = _shell_demo(request)
    context.update(
        nav_item_is_active=lambda item, path: item.href == '/app/loja/vendas',
        overview=overview, periodo={'inicio': inicio.isoformat(), 'fim': hoje.isoformat()},
        pode_ver_margem=True, pode_ver_aquisicao=True,
        formatar_brl=formatar_brl, formatar_data=formatar_data,
    )
    html = env.get_template('loja/vendas_visao.html').render(**context)
    html = re.sub(r'<link\b[^>]*https://fonts\.(?:googleapis|gstatic)\.com[^>]*>', '', html)
    return HTMLResponse(html)


@app.get('/app/loja/financeiro/demo', response_class=HTMLResponse)
async def financeiro_demo(request: Request):
    # Task 8 (direcao "fechamento"): rende o template real com dados ficticios
    # e sem persistencia. Cenario: margem parcial + equilibrio alcancado.
    hoje = date.today()
    competencia = hoje.strftime('%Y-%m')

    def formatar_brl(valor):
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            return '—'
        texto = f'{numero:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')
        return f'R$ {texto}'

    def formatar_data(iso):
        if not iso:
            return ''
        try:
            return date.fromisoformat(str(iso)[:10]).strftime('%d/%m/%Y')
        except ValueError:
            return str(iso)

    resultado = NS(
        qtd_vendas=5, receita=79500.0, custo_veiculo_total=61200.0,
        custo_vendas=61200.0, custos_diretos=2300.0, lucro_bruto=16000.0,
        margem_completa=False, vendas_sem_custo=1,
        despesa_fixa=6000.0, tem_despesa_cadastrada=True,
        lucro_operacional=10000.0,
        ponto_equilibrio_disponivel=True, margem_media=3200.0,
        ponto_equilibrio=2, vendas_ate_equilibrio=2,
        dia_do_equilibrio=hoje.replace(day=9).isoformat(),
        ponto_equilibrio_motivo=None,
        linhas=[
            NS(descricao='Honda CG 160 Fan', data=hoje.replace(day=3).isoformat(),
               preco=18900.0, custo=14500.0, custos_diretos=600.0, lucro=3800.0, venda_id=11),
            NS(descricao='Yamaha Fazer FZ25', data=hoje.replace(day=9).isoformat(),
               preco=21500.0, custo=17200.0, custos_diretos=800.0, lucro=3500.0, venda_id=12),
            NS(descricao='Honda NXR 160 Bros', data=hoje.replace(day=14).isoformat(),
               preco=22400.0, custo=None, custos_diretos=900.0, lucro=None, venda_id=13),
        ],
    )
    context = _shell_demo(request)
    context.update(
        nav_item_is_active=lambda item, path: False,
        resultado=resultado, competencia=competencia, competencia_hoje=competencia,
        formatar_brl=formatar_brl, formatar_data=formatar_data,
    )
    html = env.get_template('loja/financeiro_resultado.html').render(**context)
    html = re.sub(r'<link\b[^>]*https://fonts\.(?:googleapis|gstatic)\.com[^>]*>', '', html)
    return HTMLResponse(html)


@app.get('/app/loja/financeiro/despesas/demo', response_class=HTMLResponse)
async def despesas_demo(request: Request):
    # Task 9 (direcao "arquivo"): rende o template real com dados ficticios
    # e sem persistencia. Uma linha com ajuste no mes + arquivo com 2 itens.
    hoje = date.today()
    # Mês passado de propósito: mostra o "Próximo ›" vivo no trocador.
    competencia = (hoje.replace(day=1) - timedelta(days=1)).strftime('%Y-%m')
    competencia_hoje = hoje.strftime('%Y-%m')

    def formatar_brl(valor):
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            return '—'
        texto = f'{numero:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')
        return f'R$ {texto}'

    itens = [
        (NS(id='d1', descricao='Aluguel da loja', categoria='aluguel',
            valor_mensal=2500.0), 2500.0),
        (NS(id='d2', descricao='Salários', categoria='pessoal',
            valor_mensal=2800.0), 2800.0),
        (NS(id='d3', descricao='Energia', categoria='contas',
            valor_mensal=400.0), 320.0),
    ]
    encerradas = [
        NS(id='d9', descricao='Anúncio antigo', categoria='marketing',
           valor_mensal=900.0, inicio_competencia='2026-01', fim_competencia='2026-06'),
        NS(id='d8', descricao='Contador avulso', categoria='servicos',
           valor_mensal=600.0, inicio_competencia='2026-02', fim_competencia=None),
    ]
    context = _shell_demo(request)
    context.update(
        nav_item_is_active=lambda item, path: False,
        competencia=competencia, competencia_hoje=competencia_hoje,
        itens=itens, encerradas=encerradas,
        categorias=['aluguel', 'pessoal', 'contas', 'marketing', 'servicos'],
        aviso_ok=None, aviso_erro=None, csrf='demonstracao',
        formatar_brl=formatar_brl,
    )
    html = env.get_template('loja/financeiro_despesas.html').render(**context)
    html = re.sub(r'<link\b[^>]*https://fonts\.(?:googleapis|gstatic)\.com[^>]*>', '', html)
    return HTMLResponse(html)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    print(f'Demonstração local: http://127.0.0.1:{args.port}/app/loja/agente?periodo=mes')
    uvicorn.run(app, host='127.0.0.1', port=args.port, access_log=False)
