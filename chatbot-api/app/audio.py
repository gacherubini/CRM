"""Download e transcrição efêmeros de áudio recebido pelo WhatsApp."""
from __future__ import annotations

import base64
import binascii
import json
import logging
import math
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx

from app import config
from app.vehicle_photo import parse_tamanho_declarado


logger = logging.getLogger("chatbot.audio")

MIMES_AUDIO_PERMITIDOS = frozenset(
    {
        "audio/aac",
        "audio/amr",
        "audio/m4a",
        "audio/mp4",
        "audio/mpeg",
        "audio/ogg",
        "audio/opus",
        "audio/wav",
        "audio/webm",
        "audio/x-wav",
    }
)


class AudioIndisponivel(RuntimeError):
    pass


# Frases que o Whisper inventa em trecho mudo — legenda de vídeo que vazou do
# treino, não fala de cliente. A comparação é feita já normalizada (ver
# ``_normalizar_frase``), então aqui elas também vão sem pontuação e minúsculas.
FRASES_ALUCINACAO_CONHECIDAS = frozenset(
    {
        "legendas pela comunidade amara org",
        "tradução e legendas pela comunidade amara org",
        "legendado pela comunidade amara org",
        "amara org",
        "obrigado por assistir",
        "obrigado por assistir ao vídeo",
        "inscreva se no canal",
        "se inscreva no canal",
        "não se esqueça de se inscrever no canal",
        "até o próximo vídeo",
    }
)


def _normalizar_frase(texto: str) -> str:
    """Minúscula, sem pontuação e com um espaço só entre palavras."""
    sem_pontuacao = "".join(
        caractere if caractere.isalnum() or caractere.isspace() else " "
        for caractere in texto
    )
    return " ".join(sem_pontuacao.casefold().split())


def frase_de_alucinacao_conhecida(texto: str) -> bool:
    """A transcrição inteira é uma frase da lista (repetida ou não)?

    Só reprova quando **nada** sobra depois de tirar a frase conhecida: um
    "obrigado por assistir" isolado é legenda, mas "obrigado, quero ver a moto"
    é cliente falando e tem de passar.
    """
    normalizado = _normalizar_frase(texto)
    if not normalizado:
        return False
    for frase in FRASES_ALUCINACAO_CONHECIDAS:
        if normalizado == frase or not normalizado.replace(frase, " ").strip():
            return True
    return False


def _numero(valor: object) -> float | None:
    """Float finito, ou ``None`` quando o provider mandou outra coisa."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        convertido = float(valor)
    elif isinstance(valor, str):
        try:
            convertido = float(valor.strip())
        except ValueError:
            return None
    else:
        return None
    return convertido if math.isfinite(convertido) else None


@dataclass(frozen=True)
class SinaisTranscricao:
    """O que o ``verbose_json`` diz sobre a própria transcrição.

    ``None`` em um campo = o provider não mandou aquele sinal. Nunca guarda o
    texto: isto é medida, não conteúdo — fala de cliente não entra em log.
    """

    no_speech_prob: float | None = None
    avg_logprob: float | None = None
    compression_ratio: float | None = None
    duration_seconds: float | None = None

    @property
    def tem_confianca(self) -> bool:
        """Veio pelo menos um dos três sinais de confiança?"""
        return any(
            valor is not None
            for valor in (
                self.no_speech_prob,
                self.avg_logprob,
                self.compression_ratio,
            )
        )


def _media_ponderada(pares: list[tuple[float, float]]) -> float | None:
    if not pares:
        return None
    total_peso = sum(peso for _, peso in pares)
    if total_peso <= 0:
        return sum(valor for valor, _ in pares) / len(pares)
    return sum(valor * peso for valor, peso in pares) / total_peso


def extrair_sinais(payload: object) -> SinaisTranscricao:
    """Agrega os sinais dos segmentos do ``verbose_json`` em um número por eixo.

    Como agrega, e por quê:

    * ``no_speech_prob`` e ``avg_logprob``: **média ponderada pela duração** do
      segmento. São medidas do áudio inteiro — um respiro mudo de 0,3 s no meio
      de 20 s de fala não pode reprovar o áudio todo, e trecho longo pesa mais
      que trecho curto porque é mais do que o cliente falou. Segmento sem
      duração utilizável entra com peso 1.
    * ``compression_ratio``: **o pior segmento** (máximo). Aqui a média mentiria:
      esse número é assinatura de *loop* — "obrigado obrigado obrigado" — e loop
      é local por natureza. Um único segmento em repetição já é evidência de
      alucinação; diluí-lo em segmentos limpos é exatamente como ela passaria.
    * ``duration``: o topo do payload, ou o maior ``end`` dos segmentos.

    Segmento que não traz um campo não entra na conta daquele campo — o eixo
    fica ``None`` (sem sinal) em vez de virar zero.
    """
    if not isinstance(payload, dict):
        return SinaisTranscricao()

    bruto = payload.get("segments")
    segmentos = (
        [s for s in bruto if isinstance(s, dict)] if isinstance(bruto, list) else []
    )

    no_speech: list[tuple[float, float]] = []
    logprob: list[tuple[float, float]] = []
    compressoes: list[float] = []
    fim_maximo: float | None = None

    for segmento in segmentos:
        inicio = _numero(segmento.get("start"))
        fim = _numero(segmento.get("end"))
        peso = 1.0
        if inicio is not None and fim is not None and fim > inicio:
            peso = fim - inicio
        if fim is not None:
            fim_maximo = fim if fim_maximo is None else max(fim_maximo, fim)

        valor = _numero(segmento.get("no_speech_prob"))
        if valor is not None:
            no_speech.append((valor, peso))
        valor = _numero(segmento.get("avg_logprob"))
        if valor is not None:
            logprob.append((valor, peso))
        valor = _numero(segmento.get("compression_ratio"))
        if valor is not None:
            compressoes.append(valor)

    # Provider que devolve os sinais no topo (segmento único, ou outro formato).
    if not no_speech:
        valor = _numero(payload.get("no_speech_prob"))
        if valor is not None:
            no_speech.append((valor, 1.0))
    if not logprob:
        valor = _numero(payload.get("avg_logprob"))
        if valor is not None:
            logprob.append((valor, 1.0))
    if not compressoes:
        valor = _numero(payload.get("compression_ratio"))
        if valor is not None:
            compressoes.append(valor)

    duracao = _numero(payload.get("duration"))
    if duracao is None:
        duracao = fim_maximo

    return SinaisTranscricao(
        no_speech_prob=_media_ponderada(no_speech),
        avg_logprob=_media_ponderada(logprob),
        compression_ratio=max(compressoes) if compressoes else None,
        duration_seconds=duracao,
    )


def motivo_de_reprovacao(sinais: SinaisTranscricao) -> str | None:
    """Nome do sinal que reprova a transcrição, ou ``None`` se ela passa.

    Os tetos são os do próprio Whisper (``config.AUDIO_*``), não valores
    inventados aqui.

    Falha-abre: campo ausente (``None``) nunca reprova. Se o provider trocar e
    parar de mandar os sinais, o bot volta a ser o de hoje — surdo em silêncio
    seria pior que o problema que este gate resolve.

    ``duration`` só reprova acima do teto (é o guard de duração da §5.10 valendo
    no Modo 2, onde a Meta não manda duração no inbound): duração zerada é
    placeholder de provider, não evidência de áudio longo demais.
    """
    if (
        sinais.no_speech_prob is not None
        and sinais.no_speech_prob > config.AUDIO_NO_SPEECH_PROB_MAX
    ):
        return "no_speech_prob"
    if (
        sinais.avg_logprob is not None
        and sinais.avg_logprob < config.AUDIO_AVG_LOGPROB_MIN
    ):
        return "avg_logprob"
    if (
        sinais.compression_ratio is not None
        and sinais.compression_ratio > config.AUDIO_COMPRESSION_RATIO_MAX
    ):
        return "compression_ratio"
    if (
        sinais.duration_seconds is not None
        and sinais.duration_seconds > config.AUDIO_MAX_DURATION_SECONDS
    ):
        return "duracao"
    return None


class MediaDownloader(Protocol):
    def baixar(
        self,
        instancia: str,
        message_id: str,
        mime_declarado: str | None = None,
    ) -> tuple[bytes, str]: ...


class TranscriptionProvider(Protocol):
    def transcrever(self, arquivo: Path, mime_type: str) -> str: ...


def normalizar_mime(valor: object) -> str:
    mime = str(valor or "").split(";", 1)[0].strip().lower()
    if mime not in MIMES_AUDIO_PERMITIDOS:
        raise AudioIndisponivel("tipo de áudio não permitido")
    return mime


class EvolutionMediaDownloader:
    """Obtém base64 na Evolution; a apikey nunca passa pelo n8n nem por logs."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = (base_url or config.AUDIO_EVOLUTION_URL).rstrip("/")
        self.api_key = api_key or config.AUDIO_EVOLUTION_API_KEY
        self.timeout = timeout or config.AUDIO_DOWNLOAD_TIMEOUT
        self.transport = transport

    def baixar(
        self,
        instancia: str,
        message_id: str,
        mime_declarado: str | None = None,
    ) -> tuple[bytes, str]:
        if not self.base_url or not self.api_key:
            raise AudioIndisponivel("download de áudio não configurado")
        if mime_declarado:
            normalizar_mime(mime_declarado)

        limite_json = ((config.AUDIO_MAX_BYTES + 2) // 3 * 4) + 64 * 1024
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers={"apikey": self.api_key},
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                with client.stream(
                    "POST",
                    f"/chat/getBase64FromMediaMessage/{quote(instancia, safe='')}",
                    json={
                        "message": {"key": {"id": message_id}},
                        "convertToMp4": False,
                    },
                ) as resposta:
                    resposta.raise_for_status()
                    bruto = bytearray()
                    for parte in resposta.iter_bytes():
                        bruto.extend(parte)
                        if len(bruto) > limite_json:
                            raise AudioIndisponivel("resposta de mídia acima do limite")
        except AudioIndisponivel:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise AudioIndisponivel("não foi possível obter o áudio") from exc

        try:
            payload = json.loads(bruto)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AudioIndisponivel("resposta de mídia inválida") from exc
        return self._decodificar(payload, mime_declarado)

    @staticmethod
    def _decodificar(
        payload: object, mime_declarado: str | None
    ) -> tuple[bytes, str]:
        if not isinstance(payload, dict):
            raise AudioIndisponivel("resposta de mídia inválida")
        dados = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        base64_texto = dados.get("base64")
        if not isinstance(base64_texto, str) or not base64_texto:
            raise AudioIndisponivel("mídia ausente na resposta")

        mime_data_uri = None
        if base64_texto.startswith("data:") and ";base64," in base64_texto[:160]:
            cabecalho, base64_texto = base64_texto.split(",", 1)
            mime_data_uri = cabecalho[5:].split(";", 1)[0]

        mime = normalizar_mime(
            dados.get("mimetype")
            or dados.get("mimeType")
            or mime_data_uri
            or mime_declarado
        )
        tamanho = parse_tamanho_declarado(dados.get("size"))
        if tamanho is not None and tamanho > config.AUDIO_MAX_BYTES:
            raise AudioIndisponivel("áudio acima do limite")

        limite_base64 = ((config.AUDIO_MAX_BYTES + 2) // 3 * 4) + 4
        if len(base64_texto) > limite_base64:
            raise AudioIndisponivel("áudio acima do limite")
        try:
            conteudo = base64.b64decode(base64_texto, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise AudioIndisponivel("base64 de áudio inválido") from exc
        if not conteudo or len(conteudo) > config.AUDIO_MAX_BYTES:
            raise AudioIndisponivel("tamanho de áudio inválido")
        return conteudo, mime


class GraphMediaDownloader:
    """Baixa mídia da Cloud API (spec §5.10). Implementa ``MediaDownloader``.

    Dois passos, e o segundo também precisa do Bearer: ``GET /{media_id}``
    devolve uma URL assinada de vida curta (~5 min) que ainda exige o header.
    Sem ele o CDN responde 401 — é o erro clássico dessa integração.

    Por isso o download é síncrono, no inbound: enfileirar para depois faz a
    URL expirar antes do worker acordar.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or config.GRAPH_BASE_URL).rstrip("/")
        self.token = token or config.GRAPH_TOKEN
        self.timeout = timeout or config.AUDIO_DOWNLOAD_TIMEOUT
        self._transport = transport

    def baixar(
        self,
        instancia: str,
        message_id: str,
        mime_declarado: str | None = None,
    ) -> tuple[bytes, str]:
        if not self.token:
            raise AudioIndisponivel("download Cloud não configurado")
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            with httpx.Client(
                timeout=self.timeout, transport=self._transport, headers=headers
            ) as cliente:
                meta = cliente.get(f"{self.base_url}/{message_id}")
                meta.raise_for_status()
                dados = meta.json()
                url = dados.get("url")
                if not url:
                    raise AudioIndisponivel("mídia sem url na resposta do Graph")
                binario = cliente.get(url)
                binario.raise_for_status()
                conteudo = binario.content
        except AudioIndisponivel:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise AudioIndisponivel("não foi possível baixar a mídia") from exc

        if len(conteudo) > config.AUDIO_MAX_BYTES:
            raise AudioIndisponivel("mídia acima do limite")
        mime = (
            dados.get("mime_type")
            or binario.headers.get("content-type")
            or mime_declarado
            or ""
        )
        return conteudo, str(mime).split(";", 1)[0].strip().lower()


class NoopTranscriptionProvider:
    def transcrever(self, arquivo: Path, mime_type: str) -> str:
        raise AudioIndisponivel("transcrição de áudio não configurada")


class HttpTranscriptionProvider:
    """Contrato genérico: multipart `file`; resposta JSON com `text` ou `texto`.

    Pede `response_format=verbose_json` porque o texto sozinho não diz se havia
    fala: o Whisper devolve frase plausível para dois segundos de rua. Com o
    formato verboso vêm `no_speech_prob`, `avg_logprob`, `compression_ratio` e
    `duration`, e é sobre eles que o gate decide (`motivo_de_reprovacao`).
    Provider que ignora o campo continua funcionando — sem sinal, o texto passa.
    """

    def __init__(
        self,
        url: str,
        token: str = "",
        timeout: float = 15,
        transport: httpx.BaseTransport | None = None,
        model: str | None = None,
    ):
        self.url = url
        self.token = token
        self.timeout = timeout
        self._transport = transport
        # `model` é obrigatório no Groq e em qualquer API compatível com a da
        # OpenAI — sem ele a resposta é 400 e **todo** áudio cairia no fallback,
        # em silêncio, parecendo um bot que simplesmente não ouve. Por isso o
        # default vem preenchido em vez de vazio: esquecer de configurar não
        # pode ser um modo de falha calado. Provider que não quer o campo se
        # declara com string vazia e ele não é enviado.
        self.model = config.AUDIO_TRANSCRIPTION_MODEL if model is None else model

    def _campos(self) -> dict[str, str]:
        """Campos do multipart, fora o arquivo.

        `temperature=0` porque o assunto aqui é alucinação: temperatura acima de
        zero deixa o Whisper mais criativo exatamente onde não se quer nenhuma
        criatividade. É o valor que a própria Groq recomenda.
        """
        campos = {
            # ISO-639-1, duas letras. "pt-BR" não é código válido: alguns
            # providers ignoram em silêncio (perde acurácia), outros 400.
            "language": "pt",
            "response_format": "verbose_json",
            "temperature": "0",
        }
        if self.model:
            campos["model"] = self.model
        return campos

    def transcrever(self, arquivo: Path, mime_type: str) -> str:
        if not self.url:
            raise AudioIndisponivel("provider de transcrição não configurado")
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            with arquivo.open("rb") as stream:
                with httpx.Client(
                    timeout=self.timeout, transport=self._transport, headers=headers
                ) as cliente:
                    resposta = cliente.post(
                        self.url,
                        files={"file": (arquivo.name, stream, mime_type)},
                        data=self._campos(),
                    )
            resposta.raise_for_status()
            payload = resposta.json()
        except (OSError, httpx.HTTPError, ValueError) as exc:
            raise AudioIndisponivel("provider de transcrição indisponível") from exc
        texto = None
        if isinstance(payload, dict):
            texto = payload.get("text") or payload.get("texto")
        if not isinstance(texto, str) or not texto.strip():
            raise AudioIndisponivel("transcrição vazia")
        texto = texto.strip()

        sinais = extrair_sinais(payload)
        if not sinais.tem_confianca:
            # Falha-abre: sem sinal o texto passa, como antes deste gate.
            logger.info("gate de confiança sem sinal do provider")
        motivo = motivo_de_reprovacao(sinais)
        if motivo is None and frase_de_alucinacao_conhecida(texto):
            motivo = "frase_conhecida"
        if motivo is not None:
            # Só o motivo: o texto é fala de cliente e não entra em log.
            logger.warning("transcrição reprovada motivo=%s", motivo)
            raise AudioIndisponivel("transcrição reprovada pelo gate de confiança")
        return texto


class AudioProcessor:
    def __init__(self, downloader: MediaDownloader, provider: TranscriptionProvider):
        self.downloader = downloader
        self.provider = provider

    def processar(
        self,
        instancia: str,
        message_id: str,
        mime_type: str | None,
        duration_seconds: float | None,
    ) -> dict:
        try:
            if duration_seconds is not None and (
                duration_seconds <= 0
                or duration_seconds > config.AUDIO_MAX_DURATION_SECONDS
            ):
                raise AudioIndisponivel("duração de áudio inválida")
            conteudo, mime = self.downloader.baixar(
                instancia, message_id, mime_type
            )
            # A extensão não é cosmética: APIs no padrão da OpenAI (Groq
            # inclusive) decidem o decoder pelo NOME do arquivo, e `.audio`
            # é recusado. Mime aceito aqui sem entrada nesta tabela vira um
            # 400 no provider e um fallback que ninguém entende.
            sufixo = {
                "audio/ogg": ".ogg",
                "audio/opus": ".ogg",
                "audio/mpeg": ".mp3",
                "audio/mp4": ".m4a",
                "audio/m4a": ".m4a",
                "audio/webm": ".webm",
                "audio/wav": ".wav",
                "audio/x-wav": ".wav",
                "audio/aac": ".aac",
                "audio/amr": ".amr",
            }.get(mime, ".audio")
            with tempfile.TemporaryDirectory(prefix="revy-audio-") as diretorio:
                arquivo = Path(diretorio) / f"entrada{sufixo}"
                arquivo.write_bytes(conteudo)
                texto = self.provider.transcrever(arquivo, mime).strip()
            if not texto or len(texto) > config.WEBHOOK_MAX_TEXT_CHARS or "\x00" in texto:
                raise AudioIndisponivel("transcrição inválida")
            return {"transcrito": True, "texto": texto, "fallback": None}
        except Exception:
            logger.warning("áudio não transcrito")
            return {
                "transcrito": False,
                "texto": None,
                "fallback": config.AUDIO_FALLBACK_TEXT,
            }


def get_audio_processor() -> AudioProcessor:
    provider_nome = config.AUDIO_TRANSCRIPTION_PROVIDER.strip().lower()
    if provider_nome == "http":
        provider: TranscriptionProvider = HttpTranscriptionProvider(
            config.AUDIO_TRANSCRIPTION_URL,
            config.AUDIO_TRANSCRIPTION_TOKEN,
            config.AUDIO_TRANSCRIPTION_TIMEOUT,
        )
    else:
        provider = NoopTranscriptionProvider()
    return AudioProcessor(EvolutionMediaDownloader(), provider)


def processador_de_audio(modo: int) -> "AudioProcessor | None":
    """Processador do canal, ou ``None`` quando o canal não transcreve.

    Transcrição é **só do Modo 2** (spec §5.10): a central precisa ouvir para
    responder, porque não há humano do outro lado. No Modo 1 quem recebe o
    áudio é o vendedor, no celular dele — transcrever ali só geraria custo.

    Por isso a decisão é por canal, não por variável global do processo:
    ligar `AUDIO_TRANSCRIPTION_PROVIDER` globalmente mudaria o Modo 1 junto.
    """
    if modo != 2:
        return None
    if not config.AUDIO_TRANSCRIPTION_URL:
        return None
    return AudioProcessor(
        downloader=GraphMediaDownloader(),
        provider=HttpTranscriptionProvider(
            url=config.AUDIO_TRANSCRIPTION_URL,
            token=config.AUDIO_TRANSCRIPTION_TOKEN,
        ),
    )
