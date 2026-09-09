r"""Descartável: três hierarquias para Atendimento, na rota existente, ?variant=A/B/C.

Windows: .\.venv\Scripts\python.exe prototype_atendimento.py
macOS: .venv/bin/python prototype_atendimento.py
Não importa app/config/main, não lê .env, não conecta integrações. SQLite em memória.
"""
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
    return RedirectResponse('/app/loja/atendimento/demo-marina?variant=A')


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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    print(f'Demonstração local: http://127.0.0.1:{args.port}/app/loja/atendimento/demo-marina?variant=A')
    uvicorn.run(app, host='127.0.0.1', port=args.port, access_log=False)
