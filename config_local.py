# config_local.py
"""
Configuración central del proveedor de IA.

Permite ejecutar el proyecto 100% en local con Ollama (por defecto) o seguir
usando la API de OpenAI en la nube, cambiando una sola variable de entorno:

    LLM_PROVIDER=ollama   -> todo local (Ollama + faster-whisper)
    LLM_PROVIDER=openai   -> usa la API de OpenAI (comportamiento original)

El resto de los módulos (ia_motor, procesar_datos, vision_chat, video_a_manual,
copiloto_reunion) piden aquí el LLM, los embeddings y la configuración del SDK,
para que exista un único punto de verdad y ambos modos sean consistentes.
"""

import os
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Variables de entorno (con valores por defecto pensados para una RTX 3050 6GB)
# ---------------------------------------------------------------------------
PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
USAR_OLLAMA = PROVIDER == "ollama"

# Servidor local de Ollama
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_OPENAI_BASE = OLLAMA_BASE_URL + "/v1"  # endpoint compatible con OpenAI

# Modelos locales (se descargan con `ollama pull <modelo>`)
#  - Chat/RAG: qwen2.5:7b-instruct -> bueno en español y cabe en 6GB (Q4 ~4.7GB)
#  - Embeddings: nomic-embed-text -> ligero (~274MB) y de buena calidad
#  - Visión: llava:7b -> análisis de imágenes, cabe en 6GB (~4.7GB)
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "llava:7b")

# Transcripción local (faster-whisper). "small" es buen equilibrio para español.
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "auto")  # auto | cuda | cpu

# Clave ficticia para hablar con el endpoint compatible de Ollama (no se valida).
_OLLAMA_FAKE_KEY = "ollama"


def api_key_openai() -> str:
    """Clave real de OpenAI (solo relevante en modo openai)."""
    return os.getenv("OPENAI_API_KEY", "")


def requiere_openai_key() -> bool:
    """True solo si estamos en modo nube y hace falta validar la clave."""
    return not USAR_OLLAMA


# ---------------------------------------------------------------------------
# Factories de LangChain (LLM de chat y embeddings)
# ---------------------------------------------------------------------------
def crear_llm(temperature: float = 0.0, max_tokens: int = 2048,
              request_timeout: int = 120):
    """Devuelve un modelo de chat de LangChain (expone .invoke([...]).content).

    En modo Ollama intenta la clase nativa ChatOllama y, si no estuviera
    disponible en la versión instalada, cae al endpoint compatible con OpenAI.
    """
    if USAR_OLLAMA:
        # 1) Intento con la clase nativa de Ollama
        try:
            try:
                from langchain_community.chat_models import ChatOllama
            except Exception:
                from langchain_community.chat_models.ollama import ChatOllama
            logger.info(f"🧠 LLM local (ChatOllama): {OLLAMA_MODEL}")
            return ChatOllama(
                base_url=OLLAMA_BASE_URL,
                model=OLLAMA_MODEL,
                temperature=temperature,
                num_predict=max_tokens,
            )
        except Exception as e:
            logger.warning(f"ChatOllama no disponible ({e}); uso endpoint /v1 compatible")

        # 2) Respaldo: ChatOpenAI apuntando al endpoint /v1 de Ollama
        from langchain.chat_models import ChatOpenAI
        return ChatOpenAI(
            openai_api_key=_OLLAMA_FAKE_KEY,
            openai_api_base=OLLAMA_OPENAI_BASE,
            model_name=OLLAMA_MODEL,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout=request_timeout,
        )

    # Modo nube original
    from langchain.chat_models import ChatOpenAI
    logger.info("☁️ LLM OpenAI (gpt-3.5-turbo)")
    return ChatOpenAI(
        openai_api_key=api_key_openai(),
        model_name=os.getenv("OPENAI_CHAT_MODEL", "gpt-3.5-turbo"),
        temperature=temperature,
        max_tokens=max_tokens,
        request_timeout=request_timeout,
    )


def crear_embeddings():
    """Devuelve el objeto de embeddings de LangChain.

    IMPORTANTE: la indexación (procesar_datos) y la consulta (ia_motor) deben
    usar SIEMPRE el mismo modelo, por eso ambos llaman a esta función.
    """
    if USAR_OLLAMA:
        # 1) Clase nativa de Ollama (sin tiktoken, sin claves)
        try:
            try:
                from langchain_community.embeddings import OllamaEmbeddings
            except Exception:
                from langchain_community.embeddings.ollama import OllamaEmbeddings
            logger.info(f"🔤 Embeddings locales (Ollama): {OLLAMA_EMBED_MODEL}")
            return OllamaEmbeddings(
                base_url=OLLAMA_BASE_URL,
                model=OLLAMA_EMBED_MODEL,
            )
        except Exception as e:
            logger.warning(f"OllamaEmbeddings no disponible ({e}); uso endpoint /v1 compatible")

        # 2) Respaldo: OpenAIEmbeddings contra el endpoint /v1 de Ollama
        from langchain.embeddings import OpenAIEmbeddings
        return OpenAIEmbeddings(
            openai_api_key=_OLLAMA_FAKE_KEY,
            openai_api_base=OLLAMA_OPENAI_BASE,
            model=OLLAMA_EMBED_MODEL,
        )

    # Modo nube original
    from langchain.embeddings import OpenAIEmbeddings
    logger.info("☁️ Embeddings OpenAI")
    return OpenAIEmbeddings(openai_api_key=api_key_openai())


# ---------------------------------------------------------------------------
# Helper para el SDK openai (0.28.x) usado en visión / video / copiloto
# ---------------------------------------------------------------------------
def configurar_sdk_openai():
    """Configura la librería `openai` según el proveedor y devuelve el nombre
    del modelo de chat a usar. En modo Ollama apunta el SDK al endpoint /v1
    local, de modo que openai.ChatCompletion.create() hable con Ollama."""
    import openai
    if USAR_OLLAMA:
        openai.api_key = _OLLAMA_FAKE_KEY
        openai.api_base = OLLAMA_OPENAI_BASE
        return OLLAMA_MODEL
    openai.api_key = api_key_openai()
    openai.api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    return os.getenv("OPENAI_CHAT_MODEL", "gpt-3.5-turbo")


def modelo_vision() -> str:
    """Nombre del modelo con visión según el proveedor."""
    return OLLAMA_VISION_MODEL if USAR_OLLAMA else "gpt-4o-mini"
