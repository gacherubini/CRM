"""Driver oficial Banco PAN — OpenAPI de Financiamento de Veículos v2."""
from __future__ import annotations

import base64
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app import config
from app.motor.api_base import ApiBankDriver
from app.motor.base import SolicitacaoSimulacao
from app.motor.drivers import (
    DriverContext,
    IntervencaoNecessaria,
    RejeicaoNegocio,
    ResultadoDriver,
)

PROVEDOR = "pan"
TOKEN_PATH = "/veiculos/v0/tokens"
SIMULACAO_PATH = "/openapi/veiculos/v1/simulacao"

_CAMPOS_CONFIG = {
    "api_key",
    "secret_key",
    "usuario",
    "senha",
    "id_loja",
    "tipo_id_loja",
    "codigo_produto",
    "tipo_calculo",
}


def _decimal(valor: Any) -> Decimal | None:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _primeiro(dados: dict, *caminhos: tuple[str, ...]) -> Any:
    for caminho in caminhos:
        atual: Any = dados
        for chave in caminho:
            if not isinstance(atual, dict) or chave not in atual:
                atual = None
                break
            atual = atual[chave]
        if atual is not None:
            return atual
    return None


def parse_simulacoes_pan(
    corpo: dict[str, Any], sol: SolicitacaoSimulacao
) -> list[ResultadoDriver]:
    """Normaliza a lista de ofertas da resposta PAN sem guardar o JSON bruto."""
    raiz = corpo.get("results") if isinstance(corpo.get("results"), dict) else corpo
    itens = raiz.get("simulacoes") if isinstance(raiz, dict) else None
    if not isinstance(itens, list):
        itens = corpo.get("simulacoes")
    if not isinstance(itens, list):
        raise RejeicaoNegocio("pan_sem_oferta")

    pedidos = set(sol.condicoes.prazos_meses or [])
    resultados: list[ResultadoDriver] = []
    for item in itens:
        if not isinstance(item, dict):
            continue
        prazo_raw = _primeiro(item, ("prazo", "quantidade"), ("prazo",), ("quantidadeParcelas",))
        try:
            prazo = int(prazo_raw)
        except (TypeError, ValueError):
            continue
        if pedidos and prazo not in pedidos:
            continue

        parcela = _decimal(
            _primeiro(item, ("valores", "parcela"), ("valorParcela",), ("parcela",))
        )
        if parcela is None:
            continue
        taxa = _decimal(
            _primeiro(
                item,
                ("informacoesOperacao", "taxasJuros", "baseMes"),
                ("informacoesOperacao", "taxasJuros", "cetMes"),
                ("taxaMes",),
            )
        )
        financiado = _decimal(
            _primeiro(
                item,
                ("informacoesOperacao", "valorTotalFinanciamento"),
                ("valores", "principal"),
                ("valores", "liberado"),
                ("valorFinanciado",),
            )
        )
        if financiado is None and sol.veiculo.valor is not None:
            financiado = Decimal(str(sol.veiculo.valor)) - Decimal(
                str(sol.condicoes.entrada or 0)
            )
        entrada = _decimal(
            _primeiro(item, ("valores", "entrada", "analisada"), ("valorEntrada",))
        )
        if entrada is None:
            entrada = Decimal(str(sol.condicoes.entrada or 0))
        resultados.append(
            ResultadoDriver(
                provedor=PROVEDOR,
                status="concluida",
                valor_parcela=parcela,
                taxa_am=taxa,
                prazo_meses=prazo,
                valor_financiado=financiado,
                entrada=entrada,
            )
        )
    if not resultados:
        raise RejeicaoNegocio("pan_sem_oferta")
    return resultados


class PanDriver(ApiBankDriver):
    provedor = PROVEDOR

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_s: float | None = None,
        transport: httpx.BaseTransport | None = None,
        configuracao: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            base_url=base_url or config.PAN_BASE_URL,
            timeout_s=timeout_s or config.PAN_TIMEOUT_SECONDS,
            transport=transport,
        )
        # Usado apenas por testes/smoke explícito; produção lê do banco cifrado.
        self._configuracao_injetada = configuracao

    def simular(
        self, sol: SolicitacaoSimulacao, ctx: DriverContext | None = None
    ) -> list[ResultadoDriver]:
        cfg = self._obter_configuracao(ctx)
        self._validar_solicitacao(sol)
        try:
            token = self._autenticar(cfg)
            corpo = self._request_json(
                "POST",
                SIMULACAO_PATH,
                headers={
                    "Authorization": f"Bearer {token}",
                    "ApiKey": cfg["api_key"],
                    "Content-Type": "application/json",
                },
                json=self._payload(sol, cfg),
            )
        except IntervencaoNecessaria:
            self._registrar_login(ctx, sucesso=False)
            raise
        self._registrar_login(ctx, sucesso=True)
        return parse_simulacoes_pan(corpo, sol)

    def _obter_configuracao(self, ctx: DriverContext | None) -> dict[str, str]:
        cfg = self._configuracao_injetada
        if cfg is None and ctx is not None and ctx.db is not None and ctx.cliente_id:
            from app.credenciais import obter_configuracao_para_uso

            cfg = obter_configuracao_para_uso(ctx.db, ctx.cliente_id, PROVEDOR)
        cfg = cfg or {}
        faltantes = sorted(c for c in _CAMPOS_CONFIG if not str(cfg.get(c, "")).strip())
        if faltantes:
            raise IntervencaoNecessaria("pan_configuracao_incompleta")
        return cfg

    def _validar_solicitacao(self, sol: SolicitacaoSimulacao) -> None:
        faltantes = []
        if not sol.pessoa.ddd:
            faltantes.append("ddd")
        if not sol.pessoa.celular:
            faltantes.append("celular")
        if not sol.pessoa.codigo_natureza_ocupacao:
            faltantes.append("codigo_natureza_ocupacao")
        if not sol.veiculo.codigo_provedor:
            faltantes.append("codigo_provedor")
        if sol.veiculo.ano_modelo is None:
            faltantes.append("ano_modelo")
        if sol.veiculo.valor is None:
            faltantes.append("valor")
        if faltantes:
            raise RejeicaoNegocio("pan_dados_obrigatorios")

    def _autenticar(self, cfg: dict[str, str]) -> str:
        basic = base64.b64encode(
            f'{cfg["api_key"]}:{cfg["secret_key"]}'.encode("utf-8")
        ).decode("ascii")
        corpo = self._request_json(
            "POST",
            TOKEN_PATH,
            headers={
                "Authorization": f"Basic {basic}",
                "ApiKey": cfg["api_key"],
                "Content-Type": "application/json",
            },
            json={
                "username": cfg["usuario"],
                "password": cfg["senha"],
                "grant_type": "client_credentials+password",
            },
        )
        token = None
        if isinstance(corpo, dict):
            token = corpo.get("access_token") or corpo.get("accessToken") or corpo.get("token")
            if token is None and isinstance(corpo.get("results"), dict):
                token = corpo["results"].get("access_token") or corpo["results"].get("token")
        if not token:
            raise IntervencaoNecessaria("pan_token_ausente")
        return str(token)

    def _payload(self, sol: SolicitacaoSimulacao, cfg: dict[str, str]) -> dict[str, Any]:
        categoria = "MOTOS" if sol.veiculo.categoria == "moto" else "LEVES"
        prazos = sol.condicoes.prazos_meses or (
            [sol.condicoes.prazo_meses] if sol.condicoes.prazo_meses else []
        )
        return {
            "dadosBasicos": {
                "tipoIdLoja": cfg["tipo_id_loja"],
                "idLoja": cfg["id_loja"],
                "codigoProduto": cfg["codigo_produto"],
            },
            "dadosCliente": {
                "cpf": "".join(c for c in sol.pessoa.cpf if c.isdigit()),
                "dataNascimento": sol.pessoa.nascimento,
                "ddd": sol.pessoa.ddd,
                "celular": sol.pessoa.celular,
                "codigoNaturezaOcupacao": sol.pessoa.codigo_natureza_ocupacao,
                "renda": float(sol.pessoa.renda or 0),
                "rendaComplementar": 0.0,
                "taxistaPne": sol.veiculo.finalidade == "pcd",
            },
            "dadosVeiculos": [
                {
                    "categoria": categoria,
                    "codigoVeiculo": sol.veiculo.codigo_provedor,
                    "zeroKm": bool(sol.veiculo.zero_km),
                    "anoModelo": sol.veiculo.ano_modelo,
                    "ufLicenciamento": sol.veiculo.uf_licenciamento or "SP",
                    "valorVenda": float(sol.veiculo.valor or 0),
                }
            ],
            "condicoesPreferenciais": {
                "condicaoRetornoPreferencial": "",
                "plusPreferencial": "",
                "carenciaPreferencial": None,
                "pacoteSegurosPreferencial": None,
                "tabelaPrecoPreferencial": "",
                "prazoSelecionadoPreferencial": None,
            },
            "simulacao": {
                "tipoCalculo": cfg["tipo_calculo"],
                "valorEntrada": float(sol.condicoes.entrada or 0),
                "prazos": [{"quantidade": int(p)} for p in prazos],
            },
        }

    def _registrar_login(self, ctx: DriverContext | None, *, sucesso: bool) -> None:
        if ctx is None or ctx.db is None or not ctx.cliente_id:
            return
        from app import credenciais

        if sucesso:
            credenciais.registrar_sucesso_login(ctx.db, ctx.cliente_id, PROVEDOR)
        else:
            credenciais.registrar_falha_login(
                ctx.db, ctx.cliente_id, PROVEDOR, "credencial_invalida"
            )


def fabrica_pan() -> PanDriver:
    return PanDriver()
