"""Read-model dos canais WhatsApp para a tela de Ajustes da Loja.

Traduz o estado técnico do Chatbot para linguagem de dono de loja. Nunca
carrega QR: o QR vive só no ciclo de request/response da ação de conectar.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

ROTULOS = {
    "conectado": "Conectado",
    "pendente": "Aguardando leitura do QR",
    "desconectado": "Caiu — reconectar",
    "inativo": "Desativado",
    # Modo 2 (Cloud API). O vocabulário técnico mora em
    # ``whatsapp_provider.ESTADOS_VALIDOS``, no chatbot; aqui ele vira frase de
    # dono de loja. Restrito e banido vêm da Meta e NÃO se consertam clicando —
    # o rótulo precisa dizer isso, senão o lojista fica tentando.
    "cloud_pendente": "Conectado — aguardando liberação da Revy",
    "cloud_ativo": "No ar",
    "cloud_restrito": "Limitado pela Meta — falar com a Revy",
    "cloud_banido": "Bloqueado pela Meta — falar com a Revy",
}

# As duas telas para onde esta tela empurra. Constantes locais e não import de
# ``app.web.loja_whatsapp``: o read-model não depende da camada web.
TELA_CONECTAR = "/app/loja/whatsapp/conectar"
TELA_FILA = "/app/loja/whatsapp/fila"

# Os cinco elos do onboarding Cloud (``onboarding_elo``, 1 a 5), com o nome que
# o dono de loja reconhece. "Parou ao registrar o número" é útil; "erro" não é.
PASSOS_ONBOARDING = {
    1: "autorizar a Revy na Meta",
    2: "ligar a Revy à conta de WhatsApp",
    3: "registrar o número",
    4: "criar o modelo de mensagem",
    5: "liberar o número aqui na Revy",
}

# O mesmo passo, quando ainda está andando: a frase precisa dizer de quem é a
# vez. Só o passo 1 é do lojista (a janela da Meta); do 2 ao 4 é a Revy que
# chama a Meta sozinha; no 5 não falta nada do lado da loja.
ANDAMENTO_ONBOARDING = {
    1: "Falta autorizar a Revy na Meta — é a sua vez.",
    2: "A Revy está ligando o seu número à conta de WhatsApp.",
    3: "A Revy está registrando o número.",
    4: "A Revy está criando o modelo de mensagem.",
    5: "Tudo feito do seu lado — falta a liberação da Revy.",
}

# A Meta bloqueia o número por 72 horas quando o registro estoura o limite dela,
# e o chatbot para de tentar em 5 tentativas. A partir daí, oferecer "tentar de
# novo" é oferecer um clique que já se sabe que vai recusar.
_MARCAS_DE_TETO = ("72 horas", "72h", "72 hours")

_ACAO_TETO = (
    "A Meta bloqueou novas tentativas neste número por 72 horas. "
    "Fale com a Revy."
)
_ACAO_TENTAR = "Tentar de novo"
_ACAO_FILA = "Enquanto isso, monte a fila de vendedores que atende as conversas."
_ACAO_JANELA = "Abrir a janela da Meta e concluir."


@dataclass(frozen=True)
class CanalView:
    id: str
    label: str
    instancia: str
    estado: str
    rotulo: str
    ativo: bool
    cloud: bool
    principal_estoque: bool
    pode_conectar: bool
    pode_desconectar: bool
    pode_marcar_principal_estoque: bool
    # Onboarding Cloud: só existe em canal Cloud ainda pendente. ``falhou`` é
    # estado de TELA — no banco o canal continua ``cloud_pendente``, e quem diz
    # que parou é ``onboarding_erro`` vindo do chatbot.
    onboarding_elo: int | None = None
    onboarding_passo: str = ""
    onboarding_texto: str = ""
    onboarding_acao: str = ""
    onboarding_acao_url: str = ""
    onboarding_falhou: bool = False
    pode_tentar_de_novo: bool = False


@dataclass(frozen=True)
class CanaisView:
    canais: tuple[CanalView, ...]
    erro: str | None
    pode_adicionar: bool
    # A tela de decisão (``TELA_CONECTAR``) não tem porta: quem só tem Modo 1
    # nunca a alcança clicando. Com canal Cloud, o lugar do estado é esta tela
    # mesmo — um segundo convite seria uma segunda porta para a mesma coisa.
    mostrar_link_conectar: bool = False


def _onboarding(bruto: dict, *, cloud: bool, estado: str) -> dict:
    """Traduz ``onboarding_elo``/``onboarding_erro`` em frase de dono de loja.

    Nunca devolve o texto cru do erro: ele vem do chatbot em vocabulário de
    dentro (e a tela do lojista não é lugar de código da Meta).
    """
    vazio = {
        "onboarding_elo": None,
        "onboarding_passo": "",
        "onboarding_texto": "",
        "onboarding_acao": "",
        "onboarding_acao_url": "",
        "onboarding_falhou": False,
        "pode_tentar_de_novo": False,
    }
    # Canal no ar (ou limitado/banido pela Meta) não fala de passo: o rótulo já
    # diz o que é. Onboarding só enquanto o canal está pendente.
    if not cloud or estado != "cloud_pendente":
        return vazio

    try:
        elo = int(bruto.get("onboarding_elo"))
    except (TypeError, ValueError):
        return vazio
    passo = PASSOS_ONBOARDING.get(elo)
    if not passo:
        return vazio

    erro = str(bruto.get("onboarding_erro") or "").strip()
    if erro:
        no_teto = any(marca in erro.casefold() for marca in _MARCAS_DE_TETO)
        return {
            "onboarding_elo": elo,
            "onboarding_passo": passo,
            "onboarding_texto": f"Parou ao {passo}.",
            "onboarding_acao": _ACAO_TENTAR if not no_teto else _ACAO_TETO,
            "onboarding_acao_url": "" if no_teto else TELA_CONECTAR,
            "onboarding_falhou": True,
            "pode_tentar_de_novo": not no_teto,
        }

    if elo == 1:
        acao, url = _ACAO_JANELA, TELA_CONECTAR
    elif elo == 5:
        # A fila de vendedores é a única coisa acionável enquanto a liberação
        # não sai: template e meio de pagamento não dependem do lojista aqui.
        acao, url = _ACAO_FILA, TELA_FILA
    else:
        acao, url = "", ""
    return {
        "onboarding_elo": elo,
        "onboarding_passo": passo,
        "onboarding_texto": ANDAMENTO_ONBOARDING[elo],
        "onboarding_acao": acao,
        "onboarding_acao_url": url,
        "onboarding_falhou": False,
        "pode_tentar_de_novo": False,
    }


def montar_canais_view(
    canais: list[dict] | None,
    *,
    erro: str | None = None,
    multi_habilitado: bool = True,
) -> CanaisView:
    """Monta a view. ``canais=None`` significa falha de leitura, não lista vazia."""
    if canais is None:
        # Sem a lista não dá para saber se a loja já tem canal Cloud — e
        # convidar a conectar de novo quem já conectou é pior do que não
        # convidar.
        return CanaisView(
            canais=(), erro=erro, pode_adicionar=False, mostrar_link_conectar=False
        )

    itens: list[CanalView] = []
    for bruto in canais:
        estado = str(bruto.get("estado") or "pendente")
        ativo = bool(bruto.get("ativo", True))
        # "Apagar" é inativação lógica: o Chatbot é dono de whatsapp_canais e não
        # deleta (histórico de conversas fica preservado). Os inativos ficam de
        # fora da lista para que apagar signifique "sumiu" para o dono.
        if not ativo or estado == "inativo":
            continue
        principal = bool(bruto.get("principal_estoque"))
        # Canal Cloud se reconhece pelo waba_id, que é o que o Modo 2 grava e o
        # Modo 1 deixa nulo — mesma regra do ``cloud_canal.py`` no chatbot.
        cloud = bool(bruto.get("waba_id"))
        itens.append(
            CanalView(
                id=str(bruto.get("id") or ""),
                label=str(bruto.get("e164_or_label") or "—"),
                instancia=str(bruto.get("evolution_instance") or ""),
                estado=estado,
                rotulo=ROTULOS.get(estado, estado),
                ativo=ativo,
                cloud=cloud,
                principal_estoque=principal,
                # Conectar/desconectar são ações da Evolution (QR). Num canal
                # Cloud o botão chamaria ``conectar_canal_whatsapp``, que pede
                # QR para um número que é da Cloud API.
                pode_conectar=not cloud and estado != "conectado",
                pode_desconectar=not cloud and estado == "conectado",
                pode_marcar_principal_estoque=not principal,
                **_onboarding(bruto, cloud=cloud, estado=estado),
            )
        )
    # Se a API ainda não marcou ninguém, o primeiro da lista é o implícito
    # (mesmo fallback do Chatbot: ativo mais antigo). ``replace`` copia todo o
    # resto: reconstruir campo a campo já apagou ``cloud`` uma vez, sem nenhum
    # teste ficar vermelho.
    if itens and not any(c.principal_estoque for c in itens):
        itens[0] = replace(
            itens[0],
            principal_estoque=True,
            pode_marcar_principal_estoque=False,
        )
        for i in range(1, len(itens)):
            itens[i] = replace(
                itens[i],
                principal_estoque=False,
                pode_marcar_principal_estoque=True,
            )
    return CanaisView(
        canais=tuple(itens),
        erro=erro,
        pode_adicionar=bool(multi_habilitado),
        mostrar_link_conectar=not any(c.cloud for c in itens),
    )
