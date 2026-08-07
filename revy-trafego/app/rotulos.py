"""Rótulos humanos dos enums do Control.

O Control mostrava o valor cru do enum na interface — "em configuracao" sem
acento, "gestor_responsavel", "encerrada" — e cada template resolvia (ou não)
do seu jeito. Este é o mapa único; os dois ambientes Jinja (``app.main`` e
``app.web.control_ui``) registram tudo daqui em ``registrar_globals``.
"""
from __future__ import annotations

ROTULO_STATUS_LOJA: dict[str, str] = {
    "rascunho": "Rascunho",
    "em_configuracao": "Em configuração",
    "pronta": "Pronta",
    "ativa": "Ativa",
    "suspensa": "Suspensa",
    "encerrada": "Encerrada",
}

ROTULO_PAPEL: dict[str, str] = {
    "admin": "Admin Revy",
    "gestor": "Gestor",
    "responsavel": "Responsável",
    "colaborador": "Colaborador",
    "dono": "Dono",
    "gerente": "Gerente",
    "vendedor": "Vendedor",
}

ROTULO_ACESSO: dict[str, str] = {
    "ativo": "Ativo",
    "convidado": "Convidado",
    "pendente": "Pendente",
    "revogado": "Revogado",
    "inativo": "Inativo",
    "expirado": "Expirado",
    "aceito": "Aceito",
    "recusado": "Recusado",
}


def rotular(mapa: dict[str, str], valor) -> str:
    """Rótulo humano de um enum; desconhecido cai no valor sem underline."""
    if valor is None:
        return "—"
    bruto = getattr(valor, "value", valor)
    return mapa.get(str(bruto), str(bruto).replace("_", " "))


def registrar_globals(env) -> None:
    """Publica os mapas e o helper no ambiente Jinja informado."""
    env.globals["rotulo_status"] = ROTULO_STATUS_LOJA
    env.globals["rotulo_papel"] = ROTULO_PAPEL
    env.globals["rotulo_acesso"] = ROTULO_ACESSO
    env.globals["rotular"] = rotular
