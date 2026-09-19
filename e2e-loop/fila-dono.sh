# Poe o numero do dono na fila de rodizio da loja teste, ordem 0.
# Uso (uma vez, com `fly auth login` da conta Revy):
#   fly ssh console -a app2037 < e2e-loop/fila-dono.sh
# Nao e executavel local: o conteudo e o stdin do shell remoto do app2037.
# Idempotente — rodar de novo so reafirma ordem 0 e ativo.
cd /srv/chatbot
cat > /tmp/fila_dono.py <<'PYFILA'
import uuid
from app.db import SessionLocal
from app.models_db import FilaVendedor, Loja
from app.operacao import normalizar_telefone

TEL = normalizar_telefone("+5551980336365")
NOME = "Gabriel"

db = SessionLocal()
loja = db.query(Loja).filter(Loja.slug == "teste").first()
if loja is None:
    raise SystemExit("loja teste inexistente")

v = (
    db.query(FilaVendedor)
    .filter(FilaVendedor.loja_id == loja.id, FilaVendedor.telefone == TEL)
    .first()
)
if v is None:
    v = FilaVendedor(
        id=str(uuid.uuid4()), loja_id=loja.id, nome=NOME, telefone=TEL,
        ordem=0, ativo=True, usuario_id=None,
    )
    db.add(v)
# Ordem 0 e de proposito: o reset zera o ponteiro, entao a oferta de cada run
# sai para o primeiro da fila. Sem isto o 1020 (ordem 1) pega tudo.
v.ordem, v.ativo = 0, True
db.commit()

for f in (
    db.query(FilaVendedor)
    .filter(FilaVendedor.loja_id == loja.id)
    .order_by(FilaVendedor.ordem)
    .all()
):
    print("FILA", f.ordem, f.nome, f.telefone, "ativo" if f.ativo else "inativo")
db.close()
PYFILA
# PYTHONPATH explicito: o script mora em /tmp, entao sys.path[0] e /tmp e o
# `import app` falha mesmo depois do cd. (`python -m` do provisionar.sh nao
# sofre disso porque o -m poe o cwd no caminho.)
DATABASE_URL="$CHATBOT_DATABASE_URL" PYTHONPATH=/srv/chatbot python /tmp/fila_dono.py
rm -f /tmp/fila_dono.py
exit
