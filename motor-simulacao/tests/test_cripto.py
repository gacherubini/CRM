import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import cripto, models_db, servico
from app.db import Base
from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo


def _db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _sol():
    return SolicitacaoSimulacao(
        pessoa=Pessoa(cpf="529.982.247-25", nascimento="1990-05-20", renda=3000),
        veiculo=Veiculo(categoria="moto", valor=20000),
        condicoes=Condicoes(entrada=5000, prazo_meses=48),
    )


def test_cifrar_decifrar_roundtrip():
    token = cripto.cifrar("segredo-123")
    assert token != "segredo-123"
    assert cripto.decifrar(token) == "segredo-123"


def test_indice_cego_normaliza_e_discrimina():
    a = cripto.indice_cego("529.982.247-25")
    assert a == cripto.indice_cego("52998224725")  # ignora pontuação
    assert a != cripto.indice_cego("111.444.777-35")
    assert "529" not in a  # não vaza o CPF


def test_cpf_nao_persiste_em_claro():
    db = _db()
    sim, _ = servico.criar_simulacao(db, _sol())
    row = db.get(models_db.SimulacaoORM, sim.id)
    blob = row.payload_cifrado or ""
    assert "52998224725" not in blob
    assert "529.982.247-25" not in blob
    # mas é recuperável com a chave
    dados = json.loads(cripto.decifrar(blob))
    assert dados["cpf"] == "529.982.247-25"
    assert row.cpf_indice_cego == cripto.indice_cego("529.982.247-25")
