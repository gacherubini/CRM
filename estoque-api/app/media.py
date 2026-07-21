"""Armazenamento local persistente e entrega pública de fotos do Estoque."""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import unquote

from fastapi import HTTPException

from app import config


_SEGMENTO_RE = re.compile(r"^[A-Za-z0-9-]{1,120}$")
_ARQUIVO_RE = re.compile(r"^[a-f0-9]{32}\.(?:jpg|png|webp)$")
_EXTENSAO_POR_MIME = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
_MIME_POR_EXTENSAO = {extensao: mime for mime, extensao in _EXTENSAO_POR_MIME.items()}


def normalizar_mime_imagem(valor: object) -> str:
    mime = str(valor or "").split(";", 1)[0].strip().lower()
    if mime not in _EXTENSAO_POR_MIME:
        raise HTTPException(status_code=415, detail="tipo de imagem não permitido")
    return mime


def validar_assinatura(conteudo: bytes, mime: str) -> None:
    valido = False
    if mime == "image/jpeg":
        valido = len(conteudo) >= 3 and conteudo.startswith(b"\xff\xd8\xff")
    elif mime == "image/png":
        valido = conteudo.startswith(b"\x89PNG\r\n\x1a\n")
    elif mime == "image/webp":
        valido = (
            len(conteudo) >= 12
            and conteudo.startswith(b"RIFF")
            and conteudo[8:12] == b"WEBP"
        )
    if not valido:
        raise HTTPException(status_code=415, detail="conteúdo não corresponde ao tipo da imagem")


def _segmento(valor: str, nome: str) -> str:
    texto = str(valor or "").strip()
    if not _SEGMENTO_RE.fullmatch(texto):
        raise HTTPException(status_code=422, detail=f"{nome} inválido para mídia")
    return texto


def gerar_storage_key(
    loja_id: str,
    veiculo_id: str,
    mime: str,
    idempotency_key: str | None,
) -> str:
    loja = _segmento(loja_id, "loja_id")
    veiculo = _segmento(veiculo_id, "veiculo_id")
    semente = str(idempotency_key or uuid.uuid4())[:512].encode()
    nome = hashlib.sha256(semente).hexdigest()[:32]
    return f"{loja}/{veiculo}/{nome}.{_EXTENSAO_POR_MIME[mime]}"


def caminho_seguro(storage_key: str) -> Path:
    partes = storage_key.split("/")
    if (
        len(partes) != 3
        or not _SEGMENTO_RE.fullmatch(partes[0])
        or not _SEGMENTO_RE.fullmatch(partes[1])
        or not _ARQUIVO_RE.fullmatch(partes[2])
    ):
        raise HTTPException(status_code=404, detail="mídia não encontrada")
    raiz = config.MEDIA_STORAGE_DIR.resolve()
    destino = (raiz / partes[0] / partes[1] / partes[2]).resolve()
    if raiz not in destino.parents:
        raise HTTPException(status_code=404, detail="mídia não encontrada")
    return destino


def salvar(storage_key: str, conteudo: bytes) -> tuple[Path, bool]:
    destino = caminho_seguro(storage_key)
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        if destino.read_bytes() != conteudo:
            raise HTTPException(status_code=409, detail="chave de mídia já utilizada")
        return destino, False

    temporario: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destino.parent, prefix=".upload-", delete=False
        ) as arquivo:
            temporario = arquivo.name
            arquivo.write(conteudo)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.chmod(temporario, 0o640)
        try:
            # Publica o arquivo completo sem sobrescrever uma entrega concorrente
            # que tenha usado a mesma chave idempotente.
            os.link(temporario, destino)
        except FileExistsError:
            if destino.read_bytes() != conteudo:
                raise HTTPException(status_code=409, detail="chave de mídia já utilizada")
            return destino, False
    finally:
        if temporario and os.path.exists(temporario):
            os.unlink(temporario)
    return destino, True


def remover_se_novo(caminho: Path, criado: bool) -> None:
    if criado:
        try:
            caminho.unlink(missing_ok=True)
        except OSError:
            pass


def storage_key_da_url(url: str | None) -> str | None:
    """Reconhece somente URLs geradas pela base pública configurada."""
    base = config.MEDIA_PUBLIC_BASE_URL.rstrip("/")
    valor = str(url or "").strip()
    prefixo = f"{base}/" if base else ""
    if not prefixo or not valor.startswith(prefixo):
        return None
    chave = unquote(valor[len(prefixo) :])
    try:
        caminho_seguro(chave)
    except HTTPException:
        return None
    return chave


def remover_por_url(
    url: str | None, *, idade_minima_segundos: int | None = None
) -> bool:
    chave = storage_key_da_url(url)
    if chave is None:
        return False
    caminho = caminho_seguro(chave)
    idade_minima = (
        config.MEDIA_ORPHAN_GRACE_SECONDS
        if idade_minima_segundos is None
        else max(0, idade_minima_segundos)
    )
    try:
        if caminho.exists() and time.time() - caminho.stat().st_mtime < idade_minima:
            return False
        caminho.unlink(missing_ok=True)
    except OSError:
        return False
    return True


def listar_storage_keys() -> set[str]:
    raiz = config.MEDIA_STORAGE_DIR.resolve()
    if not raiz.is_dir():
        return set()
    encontradas: set[str] = set()
    for caminho in raiz.glob("*/*/*"):
        if caminho.is_symlink() or not caminho.is_file():
            continue
        try:
            chave = caminho.relative_to(raiz).as_posix()
            if caminho_seguro(chave) == caminho.resolve():
                encontradas.add(chave)
        except (HTTPException, ValueError, OSError):
            continue
    return encontradas


def limpar_orfas(referenciadas: set[str], *, aplicar: bool = False) -> dict:
    encontradas = listar_storage_keys()
    orfas = encontradas - referenciadas
    elegiveis: set[str] = set()
    agora = time.time()
    for chave in orfas:
        try:
            caminho = caminho_seguro(chave)
            if agora - caminho.stat().st_mtime >= config.MEDIA_ORPHAN_GRACE_SECONDS:
                elegiveis.add(chave)
        except OSError:
            continue
    removidas = 0
    if aplicar:
        for chave in elegiveis:
            try:
                caminho_seguro(chave).unlink(missing_ok=True)
                removidas += 1
            except OSError:
                continue
    return {
        "arquivos": len(encontradas),
        "referenciados": len(encontradas & referenciadas),
        "orfaos": len(orfas),
        "aguardando_carencia": len(orfas - elegiveis),
        "removidos": removidas,
        "modo": "aplicar" if aplicar else "previa",
    }


def resolver_publica(loja_id: str, veiculo_id: str, arquivo: str) -> tuple[Path, str]:
    storage_key = f"{loja_id}/{veiculo_id}/{arquivo}"
    caminho = caminho_seguro(storage_key)
    if not caminho.is_file():
        raise HTTPException(status_code=404, detail="mídia não encontrada")
    extensao = arquivo.rsplit(".", 1)[-1]
    return caminho, _MIME_POR_EXTENSAO[extensao]
