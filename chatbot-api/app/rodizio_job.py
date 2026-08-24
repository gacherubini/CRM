"""Worker do prazo do rodízio (spec §5.3): o timer é nosso, não Wait do n8n."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.cloud_canal import phone_number_id_da_loja
from app.models_db import OfertaLead
from app.oferta_envio import enviar_oferta
from app.rodizio import abrir_oferta

logger = logging.getLogger("chatbot.rodizio_job")

# Quando o handoff disparou, o cliente ouviu "Já estou chamando um vendedor para
# falar com você" (`handoff_gatilhos.py`). Se a volta fecha sem ninguém pegar —
# 10 min por vendedor depois — ele não pode ficar só com o silêncio.
TEXTO_VOLTA_ESGOTADA = (
    "Ainda não consegui um vendedor livre agora. Já deixei seu atendimento com a "
    "equipe e alguém te chama por aqui."
)


class RodizioWorker:
    def run_once(self, db: Session, *, outbound) -> dict[str, int]:
        """Expira o prazo, passa o lead adiante e **manda** a reoferta.

        ``outbound`` é obrigatório de propósito. A versão anterior rodava sem
        ele: criava a linha da oferta nova e parava aí, então passados os 10 min
        o banco entregava o lead ao vendedor 2 e o celular dele nunca tocava.
        Teste verde, lead morto num registro.
        """
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

        contagem = {
            "expiradas": 0,
            "reofertadas": 0,
            "esgotadas": 0,
            "enviadas": 0,
            "falhas_envio": 0,
        }
        for oferta in vencidas:
            # Ler antes de expirar: o commit expira o objeto da sessão e ler
            # depois traria outra ida ao banco a cada atributo.
            oferta_id, loja_id = oferta.id, oferta.loja_id
            telefone_cliente = oferta.telefone_cliente

            if not self._reivindicar(db, oferta_id):
                continue
            contagem["expiradas"] += 1

            nova = abrir_oferta(db, loja_id, telefone_cliente)
            if nova is None:
                contagem["esgotadas"] += 1
                self._avisar_volta_esgotada(
                    db, loja_id, telefone_cliente, outbound=outbound
                )
                continue

            contagem["reofertadas"] += 1
            if self._enviar(db, nova, outbound=outbound):
                contagem["enviadas"] += 1
            else:
                contagem["falhas_envio"] += 1
        return contagem

    def _reivindicar(self, db: Session, oferta_id: str) -> bool:
        """Expira a oferta com o estado no ``WHERE``. ``False`` = já era.

        O ciclo roda a cada 300 s sobre um banco compartilhado; com mais de uma
        máquina, dois ciclos veem a mesma oferta vencida. Sem o estado na
        condição os dois reofertariam e o vendedor da vez receberia a mesma
        oferta duas vezes — e o ponteiro do rodízio pularia um vendedor.
        """
        expirou = (
            db.query(OfertaLead)
            .filter(OfertaLead.id == oferta_id, OfertaLead.estado == "aberta")
            .update({"estado": "expirada"}, synchronize_session=False)
        )
        # Commit por oferta: uma falha adiante não desfaz o que já foi decidido
        # nas anteriores.
        db.commit()
        return bool(expirou)

    def _enviar(self, db: Session, oferta: OfertaLead, *, outbound) -> bool:
        """Envia a reoferta. Falhar aqui não pode derrubar o ciclo inteiro.

        Quem escolhe interativa × template é ``enviar_oferta`` — a regra de
        cobrança é um template por vendedor por dia, não por lead (spec §5.7).
        """
        try:
            envelope = enviar_oferta(db, oferta, outbound=outbound)
        except Exception:  # noqa: BLE001
            # Nem telefone nem nome no log: os ids bastam para achar a linha.
            logger.exception(
                "falha ao enviar reoferta oferta=%s loja=%s", oferta.id, oferta.loja_id
            )
            # A sessão pode ter ficado suja; sem isto a próxima oferta vencida
            # morre em PendingRollbackError e o ciclo inteiro se perde.
            db.rollback()
            return False
        logger.info(
            "reoferta enviada oferta=%s loja=%s envelope=%s",
            oferta.id,
            oferta.loja_id,
            envelope,
        )
        return True

    def _avisar_volta_esgotada(
        self, db: Session, loja_id: str, telefone_cliente: str, *, outbound
    ) -> bool:
        """A volta fechou sem ninguém pegar: o cliente merece saber.

        Sai uma vez só porque a oferta já foi para ``expirada`` antes daqui —
        o ciclo seguinte não a encontra mais entre as vencidas.
        """
        try:
            outbound.send_text(
                instance=phone_number_id_da_loja(db, loja_id),
                number=telefone_cliente,
                text=TEXTO_VOLTA_ESGOTADA,
            )
        except Exception:  # noqa: BLE001
            logger.exception("falha ao avisar volta esgotada loja=%s", loja_id)
            db.rollback()
            return False
        return True
