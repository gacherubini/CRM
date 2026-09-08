"""O canal Cloud muda de loja sem passar pelo popup de novo (spec §5.1).

Um chip só atende as duas fases do rollout do Modo 2: o número entra pela loja
`teste`, é exercitado ali, e depois vira para a loja real. O popup está fechado
para a segunda vez — `evolution_instance` é UNIQUE global e o elo 1 recusa número
já cadastrado —, então a virada é este script.

Engine próprio por teste, como em `test_semear_config_agente.py`: a suíte usa um
banco só que não se limpa entre testes, e `phone_number_id` é UNIQUE global.
Faixa livre a partir de `1227059273831630`.
"""
import uuid

import pytest

from app import db as db_module
from app import models_db
from scripts import mover_canal_de_loja


@pytest.fixture
def sessao_isolada():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    db_module.Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _criar_loja(db, slug, *, ativa=True):
    loja = models_db.Loja(
        id=str(uuid.uuid4()),
        nome=slug,
        slug=slug,
        evolution_instance=f"inst-{slug}",
    )
    db.add(loja)
    if ativa:
        db.add(
            models_db.LojaOperacionalProjecao(
                loja_id=loja.id,
                aggregate="loja",
                version=1,
                state="ativa",
                event_id=f"seed-{slug}",
            )
        )
    return loja


def _criar_canal_cloud(db, loja, phone_number_id):
    canal = models_db.WhatsAppCanal(
        id=str(uuid.uuid4()),
        loja_id=loja.id,
        e164_or_label=phone_number_id,
        evolution_instance=phone_number_id,
        waba_id="waba-do-amigo",
        estado="cloud_ativo",
        onboarding_elo=5,
    )
    db.add(canal)
    return canal


@pytest.fixture
def cenario(sessao_isolada, monkeypatch):
    """Origem com canal Cloud, destino ativo, banco que não é o SQLite de mentira."""
    monkeypatch.setattr(db_module, "DATABASE_URL", "postgresql://u:p@suite-pg/chatbot")
    monkeypatch.delenv("CHATBOT_DATABASE_URL", raising=False)
    monkeypatch.setattr(db_module, "SessionLocal", sessao_isolada)

    db = sessao_isolada()
    origem = _criar_loja(db, "teste")
    destino = _criar_loja(db, "loja-do-amigo")
    canal = _criar_canal_cloud(db, origem, "1227059273831630")
    db.commit()
    dados = {
        "origem_id": origem.id,
        "destino_id": destino.id,
        "canal_id": canal.id,
        "phone_number_id": canal.evolution_instance,
        "sessao": sessao_isolada,
    }
    db.close()
    return dados


def test_move_o_canal_e_os_dois_sentidos_passam_a_ver_o_destino(cenario):
    """Inbound e outbound leem a mesma linha; a virada tem de ser simultânea.

    Uma metade sozinha é o pior estado possível: mensagem entrando por uma loja e
    resposta saindo por outra.
    """
    from app import cloud_canal

    codigo = mover_canal_de_loja.main(
        [
            "mover",
            "--phone-number-id",
            cenario["phone_number_id"],
            "--para-slug",
            "loja-do-amigo",
        ]
    )

    assert codigo == 0
    db = cenario["sessao"]()
    assert (
        cloud_canal.loja_id_do_phone_number_id(db, cenario["phone_number_id"])
        == cenario["destino_id"]
    )
    assert cloud_canal.canal_cloud_da_loja(db, cenario["destino_id"]) is not None
    assert cloud_canal.canal_cloud_da_loja(db, cenario["origem_id"]) is None
    db.close()


def test_destino_sem_projecao_ativa_aborta_sem_mudar_nada(sessao_isolada, monkeypatch, capsys):
    """Modo 2 é fail-closed: mover para loja não-operacional deixa o número mudo."""
    monkeypatch.setattr(db_module, "DATABASE_URL", "postgresql://u:p@suite-pg/chatbot")
    monkeypatch.delenv("CHATBOT_DATABASE_URL", raising=False)
    monkeypatch.setattr(db_module, "SessionLocal", sessao_isolada)

    db = sessao_isolada()
    origem = _criar_loja(db, "teste")
    _criar_loja(db, "loja-suspensa", ativa=False)
    canal = _criar_canal_cloud(db, origem, "1227059273831631")
    db.commit()
    origem_id, canal_id = origem.id, canal.id
    db.close()

    codigo = mover_canal_de_loja.main(
        [
            "mover",
            "--phone-number-id",
            "1227059273831631",
            "--para-slug",
            "loja-suspensa",
        ]
    )

    assert codigo == 1
    assert "loja-suspensa" in capsys.readouterr().err
    db = sessao_isolada()
    assert db.get(models_db.WhatsAppCanal, canal_id).loja_id == origem_id
    db.close()


def test_oferta_aberta_na_origem_aborta_sem_mudar_nada(cenario):
    """Mover no meio de um rodízio deixa a oferta apontando para fila de outra loja."""
    db = cenario["sessao"]()
    vendedor = models_db.FilaVendedor(
        id=str(uuid.uuid4()),
        loja_id=cenario["origem_id"],
        nome="Vendedor de teste",
        telefone="5519999990000",
        ordem=0,
    )
    db.add(vendedor)
    db.add(
        models_db.OfertaLead(
            id=str(uuid.uuid4()),
            loja_id=cenario["origem_id"],
            telefone_cliente="5519888880000",
            vendedor_id=vendedor.id,
            estado="aberta",
            posicao_inicial=0,
        )
    )
    db.commit()
    db.close()

    codigo = mover_canal_de_loja.main(
        [
            "mover",
            "--phone-number-id",
            cenario["phone_number_id"],
            "--para-slug",
            "loja-do-amigo",
        ]
    )

    assert codigo == 1
    db = cenario["sessao"]()
    assert (
        db.get(models_db.WhatsAppCanal, cenario["canal_id"]).loja_id
        == cenario["origem_id"]
    )
    db.close()


def test_dry_run_nao_persiste(cenario, capsys):
    """O ensaio existe para ler a saída antes de escrever em produção."""
    codigo = mover_canal_de_loja.main(
        [
            "mover",
            "--phone-number-id",
            cenario["phone_number_id"],
            "--para-slug",
            "loja-do-amigo",
            "--dry-run",
        ]
    )

    assert codigo == 0
    db = cenario["sessao"]()
    assert (
        db.get(models_db.WhatsAppCanal, cenario["canal_id"]).loja_id
        == cenario["origem_id"]
    )
    db.close()


def test_numero_desconhecido_para_antes_de_tocar_no_banco(cenario, capsys):
    """Digitar o phone_number_id errado não pode virar traceback."""
    codigo = mover_canal_de_loja.main(
        ["mover", "--phone-number-id", "1227059273831639", "--para-slug", "loja-do-amigo"]
    )

    assert codigo == 1
    assert "1227059273831639" in capsys.readouterr().err


def test_slug_inexistente_lista_os_slugs_que_existem(cenario, capsys):
    """Sem isto o operador lê "não existe" e não sabe o que existe."""
    codigo = mover_canal_de_loja.main(
        [
            "mover",
            "--phone-number-id",
            cenario["phone_number_id"],
            "--para-slug",
            "loja-que-nao-existe",
        ]
    )

    assert codigo == 1
    assert "loja-do-amigo" in capsys.readouterr().err


def test_limpeza_solta_o_telefone_do_teste_da_loja_errada(cenario):
    """A armadilha que a troca de `loja_id` sozinha não resolve.

    `Conversa` é única por `(canal_id, telefone)` e `_get_or_create_conversa`
    devolve a conversa achada **sem conferir `loja_id`**. O `canal_id` não muda
    na virada, então o telefone que participou do teste voltaria a cair na
    conversa da loja de origem — e os telefones do teste são justamente os do
    dono, do lojista e dos vendedores.
    """
    from app import servico

    telefone = "5519777770000"
    db = cenario["sessao"]()
    servico.registrar_mensagem(
        db, cenario["phone_number_id"], telefone, "oi, é teste", "wamid-teste-1"
    )
    db.commit()
    db.close()

    codigo = mover_canal_de_loja.main(
        [
            "mover",
            "--phone-number-id",
            cenario["phone_number_id"],
            "--para-slug",
            "loja-do-amigo",
            "--apagar-dados-da-origem",
        ]
    )

    assert codigo == 0
    db = cenario["sessao"]()
    servico.registrar_mensagem(
        db, cenario["phone_number_id"], telefone, "oi, sou cliente", "wamid-real-1"
    )
    db.commit()
    conversas = (
        db.query(models_db.Conversa)
        .filter(models_db.Conversa.telefone == telefone)
        .all()
    )
    assert [c.loja_id for c in conversas] == [cenario["destino_id"]]
    db.close()


def test_limpeza_apaga_o_trafego_e_preserva_a_fila(cenario):
    """Fila é cadastro e serve o próximo teste; conversa e lead são tráfego."""
    from app import servico

    db = cenario["sessao"]()
    db.add(
        models_db.FilaVendedor(
            id=str(uuid.uuid4()),
            loja_id=cenario["origem_id"],
            nome="Vendedor de teste",
            telefone="5519999990001",
            ordem=0,
        )
    )
    servico.registrar_mensagem(
        db, cenario["phone_number_id"], "5519777770001", "oi", "wamid-teste-2"
    )
    db.commit()
    db.close()

    assert (
        mover_canal_de_loja.main(
            [
                "mover",
                "--phone-number-id",
                cenario["phone_number_id"],
                "--para-slug",
                "loja-do-amigo",
                "--apagar-dados-da-origem",
            ]
        )
        == 0
    )

    db = cenario["sessao"]()
    origem = cenario["origem_id"]
    assert (
        db.query(models_db.Conversa)
        .filter(models_db.Conversa.loja_id == origem)
        .count()
        == 0
    )
    assert (
        db.query(models_db.Mensagem)
        .filter(models_db.Mensagem.loja_id == origem)
        .count()
        == 0
    )
    assert (
        db.query(models_db.FilaVendedor)
        .filter(models_db.FilaVendedor.loja_id == origem)
        .count()
        == 1
    )
    db.close()


def test_sem_a_flag_a_limpeza_nao_acontece(cenario):
    """Apagar é destrutivo: só sob pedido explícito."""
    from app import servico

    db = cenario["sessao"]()
    servico.registrar_mensagem(
        db, cenario["phone_number_id"], "5519777770002", "oi", "wamid-teste-3"
    )
    db.commit()
    db.close()

    assert (
        mover_canal_de_loja.main(
            [
                "mover",
                "--phone-number-id",
                cenario["phone_number_id"],
                "--para-slug",
                "loja-do-amigo",
            ]
        )
        == 0
    )

    db = cenario["sessao"]()
    assert (
        db.query(models_db.Conversa)
        .filter(models_db.Conversa.loja_id == cenario["origem_id"])
        .count()
        == 1
    )
    db.close()


def test_sqlite_com_chatbot_database_url_definido_e_recusado(monkeypatch, capsys):
    """A armadilha do `fly ssh console`: `app/db.py` lê DATABASE_URL, não a outra.

    Passar só `CHATBOT_DATABASE_URL` — que é o nome do secret, e por isso o
    palpite natural — faz o engine resolver o SQLite do container. Aqui isso
    seria um "canal não encontrado" mentiroso, com o canal intacto em produção.
    """
    monkeypatch.setattr(db_module, "DATABASE_URL", "sqlite:///./chatbot.db")
    monkeypatch.setenv("CHATBOT_DATABASE_URL", "postgresql://u:p@suite-pg/chatbot")

    codigo = mover_canal_de_loja.main(
        ["mover", "--phone-number-id", "1227059273831630", "--para-slug", "qualquer"]
    )

    assert codigo == 2
    assert "DATABASE_URL" in capsys.readouterr().err
