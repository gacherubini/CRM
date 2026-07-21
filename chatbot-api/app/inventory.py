"""InventoryProvider — consulta o Estoque Lite (Plano #2A Task 2A + por-placa + E5 escrita).

- buscar: API pública (ESTOQUE_PUBLIC_URL)
- obter_por_placa: API privada (ESTOQUE_API_URL + ESTOQUE_API_TOKEN)
- HttpInventoryWriteClient: POST /v1/veiculos (cadastro WhatsApp E5)

O chatbot só responde com veículos reais. Se o estoque estiver indisponível/vazio,
o provider devolve lista vazia / None e o chamador oferece fallback/handoff (nunca inventa).
O Chatbot NÃO é fonte de verdade de veículos.
"""
import ipaddress
from typing import Protocol
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

from app import config


class InventoryProvider(Protocol):
    def buscar(self, slug: str, termo: str | None = None) -> list[dict]: ...

    def obter_por_placa(self, placa: str) -> dict | None: ...

    def obter_midia_principal(self, slug: str, veiculo_id: str) -> dict | None: ...


_CAMPOS_VEICULO_CHATBOT = {
    "id", "tipo", "marca", "modelo", "versao", "ano_modelo", "cor", "km",
    "preco", "status", "publicado", "placa",
}
_CONTENT_TYPES_IMAGEM = {"image/jpeg", "image/png", "image/webp"}


def _content_type_url_legada(url: str) -> str | None:
    path = urlparse(url).path.lower()
    if path.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if path.endswith(".png"):
        return "image/png"
    if path.endswith(".webp"):
        return "image/webp"
    return None


def _url_midia_publica(url: object) -> str | None:
    valor = str(url or "").strip()
    if not valor or len(valor) > 2048:
        return None
    parsed = urlparse(valor)
    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or host == "localhost"
        or host.endswith((".localhost", ".local", ".internal"))
    ):
        return None
    try:
        endereco = ipaddress.ip_address(host)
    except ValueError:
        endereco = None
    if endereco is not None and not endereco.is_global:
        return None
    if config.ESTOQUE_MEDIA_ALLOWED_HOSTS and host not in config.ESTOQUE_MEDIA_ALLOWED_HOSTS:
        return None
    return valor


def _projetar_midia(midia: object) -> dict | None:
    if not isinstance(midia, dict):
        return None
    url = _url_midia_publica(midia.get("url"))
    content_type = midia.get("content_type")
    if not url or content_type not in _CONTENT_TYPES_IMAGEM:
        return None
    tamanho = midia.get("tamanho_bytes")
    if tamanho is not None:
        try:
            tamanho = int(tamanho)
        except (TypeError, ValueError):
            return None
        if tamanho <= 0 or tamanho > 10 * 1024 * 1024:
            return None
    return {
        "url": url,
        "content_type": content_type,
        "tamanho_bytes": tamanho,
        "ordem": int(midia.get("ordem") or 0),
        "capa": bool(midia.get("capa")),
    }


def projetar_veiculo_chatbot(veiculo: object) -> dict | None:
    """Allowlist para o modelo: remove custo, códigos e quaisquer paths internos."""
    if not isinstance(veiculo, dict):
        return None
    saida = {campo: veiculo.get(campo) for campo in _CAMPOS_VEICULO_CHATBOT if campo in veiculo}
    midias = []
    for item in veiculo.get("midias") or []:
        projetada = _projetar_midia(item)
        if projetada:
            midias.append(projetada)
    if not midias:
        url_legada = _url_midia_publica(veiculo.get("foto_url"))
        content_type_legado = _content_type_url_legada(url_legada) if url_legada else None
        if url_legada and content_type_legado:
            midias.append(
                {
                    "url": url_legada,
                    "content_type": content_type_legado,
                    "tamanho_bytes": None,
                    "ordem": 0,
                    "capa": True,
                }
            )
    midias.sort(key=lambda item: item["ordem"])
    saida["midias"] = midias
    saida["midia_principal"] = next(
        (item for item in midias if item["capa"]), midias[0] if midias else None
    )
    # Compatibilidade dos consumidores atuais; sempre com URLs já sanitizadas.
    saida["fotos"] = [item["url"] for item in midias]
    saida["foto_url"] = (
        saida["midia_principal"]["url"] if saida["midia_principal"] else None
    )
    saida["tem_foto"] = bool(midias)
    return saida


class HttpInventoryProvider:
    def __init__(
        self,
        base_url: str | None = None,
        api_url: str | None = None,
        api_token: str | None = None,
        timeout: float = 5.0,
    ):
        self.base_url = (base_url if base_url is not None else config.ESTOQUE_PUBLIC_URL).rstrip("/")
        self.api_url = (api_url if api_url is not None else config.ESTOQUE_API_URL).rstrip("/")
        self.api_token = config.ESTOQUE_API_TOKEN if api_token is None else api_token
        self.timeout = timeout

    def buscar(self, slug: str, termo: str | None = None) -> list[dict]:
        if not self.base_url:
            return []
        url = f"{self.base_url}/public/v1/lojas/{slug}/veiculos"
        try:
            r = httpx.get(url, timeout=self.timeout)
            r.raise_for_status()
            veiculos = r.json().get("veiculos", [])
        except Exception:
            return []
        if termo:
            t = termo.lower()
            veiculos = [
                v
                for v in veiculos
                if t in f"{v.get('marca', '')} {v.get('modelo', '')}".lower()
            ]
        return [
            projetado
            for veiculo in veiculos
            if (projetado := projetar_veiculo_chatbot(veiculo)) is not None
        ]

    def obter_por_placa(self, placa: str) -> dict | None:
        """GET privado /v1/veiculos/por-placa/{placa}. 404/erros → None."""
        if not self.api_url or not self.api_token or not placa:
            return None
        placa_limpa = placa.strip()
        if not placa_limpa:
            return None
        url = f"{self.api_url}/v1/veiculos/por-placa/{placa_limpa}"
        try:
            r = httpx.get(
                url,
                headers={"Authorization": f"Bearer {self.api_token}"},
                timeout=self.timeout,
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return projetar_veiculo_chatbot(r.json())
        except Exception:
            return None

    def obter_midia_principal(self, slug: str, veiculo_id: str) -> dict | None:
        """Resolve a capa pela vitrine tenant-scoped; mídia não publicada não é exposta."""
        if not self.base_url or not slug or not veiculo_id:
            return None
        url = f"{self.base_url}/public/v1/lojas/{slug}/veiculos/{veiculo_id}"
        try:
            r = httpx.get(url, timeout=self.timeout)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            veiculo = projetar_veiculo_chatbot(r.json())
        except Exception:
            return None
        return veiculo.get("midia_principal") if veiculo else None


def get_inventory_provider() -> InventoryProvider:
    return HttpInventoryProvider()


class InventoryWriteClient(Protocol):
    def disponivel(self) -> bool: ...

    def criar_veiculo(
        self, dados: dict, idempotency_key: str | None = None
    ) -> dict: ...


class HttpInventoryWriteClient:
    """Cliente HTTP de escrita no Estoque privado (POST /v1/veiculos)."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
    ):
        self.base_url = (base_url if base_url is not None else config.ESTOQUE_API_URL).rstrip("/")
        self.token = token if token is not None else config.ESTOQUE_API_TOKEN
        self.timeout = config.ESTOQUE_REQUEST_TIMEOUT if timeout is None else timeout

    def disponivel(self) -> bool:
        return bool(self.base_url and self.token)

    def criar_veiculo(
        self, dados: dict, idempotency_key: str | None = None
    ) -> dict:
        if not self.disponivel():
            raise HTTPException(
                status_code=503,
                detail="integração de estoque (escrita) não configurada",
            )
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            r = httpx.post(
                f"{self.base_url}/v1/veiculos",
                json=dados,
                headers=headers,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502, detail="estoque indisponível no momento"
            ) from exc

        if r.status_code in (200, 201):
            return r.json()

        detail = _extrair_detail(r)
        if r.status_code == 422:
            raise HTTPException(status_code=422, detail=detail or "dados inválidos no estoque")
        if r.status_code == 409:
            raise HTTPException(status_code=409, detail=detail or "conflito no estoque")
        if r.status_code in (401, 403):
            raise HTTPException(
                status_code=502,
                detail="credencial de estoque recusada (verifique ESTOQUE_API_TOKEN)",
            )
        raise HTTPException(
            status_code=502,
            detail=detail or f"estoque retornou {r.status_code}",
        )


def _extrair_detail(r: httpx.Response) -> str | None:
    try:
        body = r.json()
    except Exception:
        return None
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        partes = []
        for item in detail:
            if isinstance(item, dict):
                loc = ".".join(str(x) for x in item.get("loc", []) if x != "body")
                msg = item.get("msg", "")
                partes.append(f"{loc}: {msg}" if loc else msg)
        return "; ".join(partes) if partes else None
    return None


def get_inventory_write_client() -> InventoryWriteClient:
    return HttpInventoryWriteClient()
