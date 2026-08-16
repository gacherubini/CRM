"""Worker do prazo do rodízio (spec §5.3): o timer é nosso, não Wait do n8n."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models_db import OfertaLead
from app.rodizio import abrir_oferta


class RodizioWorker:
    def run_once(self, db: Session) -> dict[str, int]:
        agora = datetime.now(timezone.utc)
        vencidas = (
            db.query(OfertaLead)
            .filter(
                OfertaLead.estado == "aberta",
                OfertaLead.prazo_em.isnot(None),
                OfertaLead.prazo_em <= agora,
            )
            .all()
        )

        contagem = {"expiradas": 0, "reofertadas": 0, "esgotadas": 0}
        for oferta in vencidas:
            oferta.estado = "expirada"
            contagem["expiradas"] += 1
            db.commit()

            nova = abrir_oferta(db, oferta.loja_id, oferta.telefone_cliente)
            if nova is None:
                contagem["esgotadas"] += 1
            else:
                contagem["reofertadas"] += 1
        return contagem
