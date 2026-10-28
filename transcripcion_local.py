# transcripcion_local.py
"""
Transcripción de audio/video en LOCAL con faster-whisper.

Ollama no hace speech-to-text, así que para las funciones "Video a manual" y
"Copiloto de reunión" usamos faster-whisper, que corre offline en GPU o CPU.

El modelo se carga una sola vez y se reutiliza. Intenta GPU (CUDA) y, si no
está disponible, cae a CPU en int8 (más lento pero funciona en cualquier PC).

Variables de entorno (ver config_local.py):
    WHISPER_MODEL   tiny | base | small | medium | large-v3   (def: small)
    WHISPER_DEVICE  auto | cuda | cpu                         (def: auto)
"""

import logging

from config_local import WHISPER_MODEL, WHISPER_DEVICE

logger = logging.getLogger(__name__)

_modelo = None


def _cargar_modelo():
    """Carga (y cachea) el modelo de faster-whisper."""
    global _modelo
    if _modelo is not None:
        return _modelo

    try:
        from faster_whisper import WhisperModel
    except Exception as e:
        raise RuntimeError(
            "faster-whisper no está instalado. Ejecuta: "
            "pip install faster-whisper"
        ) from e

    # Orden de intentos según el dispositivo pedido
    intentos = []
    if WHISPER_DEVICE in ("auto", "cuda"):
        intentos.append(("cuda", "float16"))
    intentos.append(("cpu", "int8"))

    ultimo_error = None
    for device, compute_type in intentos:
        try:
            logger.info(f"🎙️ Cargando faster-whisper '{WHISPER_MODEL}' en {device} ({compute_type})...")
            _modelo = WhisperModel(WHISPER_MODEL, device=device, compute_type=compute_type)
            logger.info(f"✅ Whisper local listo en {device}")
            return _modelo
        except Exception as e:
            ultimo_error = e
            logger.warning(f"No se pudo usar {device}: {e}")

    raise RuntimeError(f"No se pudo cargar faster-whisper: {ultimo_error}")


def transcribir_archivo(ruta: str, idioma: str = "es") -> str:
    """Transcribe un archivo de audio o video y devuelve el texto plano."""
    modelo = _cargar_modelo()
    segmentos, _info = modelo.transcribe(ruta, language=idioma, vad_filter=True)
    return " ".join(s.text.strip() for s in segmentos).strip()
