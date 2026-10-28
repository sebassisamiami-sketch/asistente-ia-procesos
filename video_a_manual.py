"""
video_a_manual.py
=================
Convierte un video (o audio) en el contenido de un MANUAL y lo entrega como PDF.

Flujo:
  1) Extrae el audio del video con ffmpeg (si está disponible).
  2) Transcribe con Whisper (OpenAI). Si el audio es muy grande, lo divide.
  3) Resume la transcripción en formato de manual con GPT (map-reduce si es largo).
  4) Genera un PDF descargable.

Usa la librería estándar + openai (0.28.x) + fpdf2.
"""

import os
import glob
import shutil
import tempfile
import subprocess
import logging

import openai

import config_local

logger = logging.getLogger(__name__)

MAX_BYTES = 24 * 1024 * 1024  # límite práctico de Whisper (25MB)

# Contexto del negocio para interpretar mejor los videos (NO afecta el chat ni los manuales existentes)
DOMAIN_CONTEXT = (
    "CONTEXTO DEL NEGOCIO (úsalo para interpretar el video, no para inventar):\n"
    "- El equipo trabaja con la plataforma BPM y procesos de BPM (Business Process Management).\n"
    "- Los 'tickets' o 'casos' se RESUELVEN en el gestor de tickets.\n"
    "- Los casos se gestionan dentro de los flujos de BPM: se BUSCAN, se VALIDAN "
    "(la etapa/flujo correcto) y se CIERRAN/RESUELVEN en el gestor de tickets.\n"
    "- Un caso típico implica: identificar el ticket, buscarlo/abrirlo, validar la etapa del flujo "
    "de BPM, ejecutar acciones (consultas, cambios, validaciones) y resolver/cerrar el caso en el gestor de tickets.\n"
    "- Presta especial atención a: el NOMBRE del caso/ticket, la ETAPA o FLUJO de BPM, cómo se "
    "BUSCA/abre el ticket, QUÉ se valida, qué DATOS o CONSULTAS se usan, y cómo se RESUELVE/CIERRA "
    "el caso en el gestor de tickets."
)


def _extraer_relevante(texto: str) -> str:
    """Paso 1: extrae de forma exhaustiva todo lo operativamente relevante del video."""
    return _gpt([
        {"role": "system", "content": DOMAIN_CONTEXT + "\n\nEres analista de procesos. Lee la "
         "transcripción y EXTRAE en una lista exhaustiva y ORDENADA todo lo relevante: nombre del "
         "caso/ticket, cómo se busca y se abre, la etapa/flujo de BPM involucrado, validaciones, "
         "acciones concretas, pantallas/botones/campos, datos y consultas exactas, y cómo se cierra "
         "el caso. No omitas detalles. No inventes nada que no esté en la transcripción."},
        {"role": "user", "content": texto},
    ], max_tokens=2500, temp=0.2)


def _api_key():
    try:
        import streamlit as st
        from secretos import hay_archivo_secrets
        if hay_archivo_secrets() and "OPENAI_API_KEY" in st.secrets:
            return st.secrets["OPENAI_API_KEY"]
    except Exception:
        pass
    return os.getenv("OPENAI_API_KEY", "")


def extraer_audio(video_path: str):
    """Extrae audio comprimido (mp3 mono) con ffmpeg. Devuelve (ruta, ok)."""
    if not shutil.which("ffmpeg"):
        return video_path, False
    salida = video_path + ".mp3"
    cmd = ["ffmpeg", "-y", "-i", video_path, "-vn", "-ac", "1",
           "-ar", "16000", "-b:a", "64k", salida]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return salida, True
    except Exception as e:
        logger.warning(f"ffmpeg falló: {e}")
        return video_path, False


def _segmentar(audio_path: str):
    """Divide el audio en trozos de ~10 minutos (para audios largos)."""
    carpeta = tempfile.mkdtemp()
    patron = os.path.join(carpeta, "part%03d.mp3")
    cmd = ["ffmpeg", "-y", "-i", audio_path, "-f", "segment",
           "-segment_time", "600", "-c", "copy", patron]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        partes = sorted(glob.glob(os.path.join(carpeta, "part*.mp3")))
        return partes or [audio_path]
    except Exception as e:
        logger.warning(f"No se pudo segmentar: {e}")
        return [audio_path]


def transcribir(path: str) -> str:
    """Transcribe un archivo de audio/video.

    - En modo local (Ollama): usa faster-whisper offline. No necesita trocear
      el archivo porque no hay límite de 25MB.
    - En modo nube: usa Whisper de OpenAI (whisper-1), troceando si supera 25MB.
    """
    # --- Modo local: faster-whisper ---
    if config_local.USAR_OLLAMA:
        try:
            from transcripcion_local import transcribir_archivo
            return transcribir_archivo(path, idioma="es")
        except Exception as e:
            logger.error(f"Error en transcripción local: {e}")
            return f"[Error transcribiendo en local: {e}]"

    # --- Modo nube: Whisper de OpenAI ---
    config_local.configurar_sdk_openai()
    openai.api_key = _api_key()
    partes = [path]
    try:
        if os.path.getsize(path) > MAX_BYTES and shutil.which("ffmpeg"):
            partes = _segmentar(path)
    except Exception:
        pass

    textos = []
    for p in partes:
        try:
            with open(p, "rb") as f:
                tr = openai.Audio.transcribe("whisper-1", f, language="es")
            textos.append(tr["text"] if isinstance(tr, dict) else getattr(tr, "text", ""))
        except Exception as e:
            logger.error(f"Error transcribiendo {p}: {e}")
            textos.append(f"[Error transcribiendo un segmento: {e}]")
    return "\n".join(textos).strip()


def _gpt(mensajes, max_tokens=1500, temp=0.2, model=None):
    """Llama al modelo de chat (Ollama en local u OpenAI en la nube)."""
    modelo_cfg = config_local.configurar_sdk_openai()
    if not config_local.USAR_OLLAMA:
        openai.api_key = _api_key()
    model = model or modelo_cfg
    try:
        resp = openai.ChatCompletion.create(
            model=model, temperature=temp, max_tokens=max_tokens, messages=mensajes,
        )
    except Exception as e:
        logger.warning(f"Modelo {model} no disponible ({e}); reintentando con {modelo_cfg}")
        resp = openai.ChatCompletion.create(
            model=modelo_cfg, temperature=temp,
            max_tokens=min(max_tokens, 4000), messages=mensajes,
        )
    return resp["choices"][0]["message"]["content"].strip()


def _resumen_parcial(texto: str) -> str:
    return _gpt([
        {"role": "system", "content": "Extrae de esta parte de la transcripción TODOS los "
         "pasos, acciones, nombres de pantallas/botones/campos, datos y consultas que se "
         "mencionen. Mantén el ORDEN. No resumas en exceso: conserva el detalle operativo. "
         "Devuelve viñetas concretas."},
        {"role": "user", "content": texto},
    ], max_tokens=1000)


def _manual_final(texto: str, titulo: str, puntos: str = "") -> str:
    instruccion = (
        DOMAIN_CONTEXT + "\n\n"
        "Eres un redactor técnico experto en documentación de procesos BPM. A partir de la "
        "TRANSCRIPCIÓN y los PUNTOS CLAVE EXTRAÍDOS de un video, redacta un MANUAL COMPLETO, "
        "EXTENSO y DETALLADO en español.\n\n"
        f"El NOMBRE DEL CASO es: \"{titulo}\". Úsalo como referencia del proceso.\n\n"
        "Estructura obligatoria (desarrolla CADA sección al máximo, sin dejar nada vacío):\n\n"
        f"# {titulo}\n"
        "## Caso / Proceso\n"
        "Explica de qué caso o ticket trata y en qué flujo/etapa de BPM aplica.\n"
        "## Objetivo\n"
        "Qué se logra al completar el proceso.\n"
        "## Requisitos previos\n"
        "Accesos, sistemas (la plataforma BPM/BPM), datos o herramientas necesarios.\n"
        "## Pasos detallados\n"
        "Enumera TODOS los pasos en orden (1, 2, 3, ...). Para cada paso explica QUÉ se hace, "
        "DÓNDE (pantalla, menú, botón, campo, etapa de BPM) y CON QUÉ DATOS. Incluye cómo se "
        "busca/abre el ticket, cómo se valida la etapa y cómo se cierra el caso. Incluye consultas, "
        "rutas o valores exactos. Sé minucioso: mejor sobrar que faltar.\n"
        "## Validaciones y cierre del caso\n"
        "Cómo se valida el flujo de BPM y cómo se cierra el ticket.\n"
        "## Notas y advertencias\n"
        "Errores comunes, validaciones, recomendaciones.\n"
        "## Resumen\n"
        "Resumen breve del proceso.\n\n"
        "REGLAS:\n"
        "- Usa TODA la información disponible; reordénala y redáctala con claridad.\n"
        "- NO dejes secciones vacías. Si algo no se menciona, escribe 'No se especifica en el video'.\n"
        "- Desarrolla los pasos con frases completas, no en telegrama.\n"
        "- Es un documento oficial: profesional, claro y EXTENSO."
    )
    contenido_usuario = f"TRANSCRIPCIÓN DEL VIDEO:\n{texto}"
    if puntos:
        contenido_usuario += f"\n\nPUNTOS CLAVE EXTRAÍDOS:\n{puntos}"
    return _gpt([
        {"role": "system", "content": instruccion},
        {"role": "user", "content": contenido_usuario},
    ], max_tokens=3800, temp=0.4)


def resumir_a_manual(transcripcion: str, titulo: str) -> str:
    """Convierte la transcripción en un manual completo (2 pasos: extraer + redactar)."""
    transcripcion = (transcripcion or "").strip()
    if not transcripcion:
        return "No se obtuvo transcripción del video."

    base = transcripcion
    # Si es larguísimo, condensar por partes primero (conservando detalle)
    if len(transcripcion) > 40000:
        trozos = [transcripcion[i:i + 12000] for i in range(0, len(transcripcion), 12000)]
        partes = []
        for t in trozos:
            try:
                partes.append(_resumen_parcial(t))
            except Exception as e:
                logger.error(f"Error en resumen parcial: {e}")
        base = "\n".join(partes)

    # Paso 1: extraer TODO lo relevante (enfoque BPM / tickets)
    try:
        puntos = _extraer_relevante(base)
    except Exception as e:
        logger.error(f"Error extrayendo puntos: {e}")
        puntos = ""

    # Paso 2: redactar el manual final con el contexto + los puntos
    return _manual_final(base, titulo, puntos)


def resumir_a_manual(transcripcion: str, titulo: str) -> str:
    """Convierte la transcripción en el contenido de un manual (map-reduce si es largo)."""
    transcripcion = (transcripcion or "").strip()
    if not transcripcion:
        return "No se obtuvo transcripción del video."

    max_chars = 40000  # gpt-4o-mini admite contexto grande -> usamos toda la transcripción
    if len(transcripcion) <= max_chars:
        return _manual_final(transcripcion, titulo)

    # Dividir y resumir por partes, luego combinar
    trozos = [transcripcion[i:i + max_chars] for i in range(0, len(transcripcion), max_chars)]
    resumenes = []
    for t in trozos:
        try:
            resumenes.append(_resumen_parcial(t))
        except Exception as e:
            logger.error(f"Error en resumen parcial: {e}")
    combinado = "\n".join(resumenes)
    if len(combinado) > max_chars:
        combinado = combinado[:max_chars]
    return _manual_final(combinado, titulo)


def _latin(texto: str) -> str:
    """Compatibiliza con fuentes core (latin-1) y corta palabras larguísimas
    para evitar el error 'Not enough horizontal space' de FPDF."""
    t = (texto or "").encode("latin-1", "replace").decode("latin-1")
    fijas = []
    for w in t.split(" "):
        while len(w) > 70:
            fijas.append(w[:70])
            w = w[70:]
        fijas.append(w)
    return " ".join(fijas)


def generar_pdf(titulo: str, contenido: str) -> bytes:
    """Genera un PDF con el contenido del manual. Devuelve bytes."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Encabezado
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 9, _latin(titulo or "Manual"))
    pdf.ln(2)
    pdf.set_draw_color(138, 180, 248)
    pdf.set_line_width(0.8)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)

    for linea in (contenido or "").split("\n"):
        bruto = linea.rstrip()
        texto = _latin(bruto.replace("**", "").replace("#", "").strip())
        if not texto:
            pdf.ln(3)
            continue
        try:
            # Encabezado de sección (línea corta en mayúsculas o que empieza con #)
            es_titulo = bruto.startswith("#") or (bruto.isupper() and len(bruto) < 60)
            if es_titulo:
                pdf.ln(2)
                pdf.set_font("Helvetica", "B", 13)
                pdf.set_text_color(30, 30, 30)
                pdf.multi_cell(0, 7, texto)
                pdf.ln(1)
            elif bruto.lstrip().startswith(("-", "*", "•")):
                pdf.set_font("Helvetica", "", 11)
                pdf.set_text_color(50, 50, 50)
                pdf.multi_cell(0, 6, "  -  " + texto.lstrip("-*• ").strip())
            else:
                pdf.set_font("Helvetica", "", 11)
                pdf.set_text_color(50, 50, 50)
                pdf.multi_cell(0, 6, texto)
        except Exception:
            # Si una línea no se puede renderizar, la omitimos para no romper el PDF
            continue

    salida = pdf.output(dest="S")
    if isinstance(salida, str):
        return salida.encode("latin-1")
    return bytes(salida)


def procesar_video(ruta_video: str, titulo: str):
    """Pipeline completo. Devuelve dict con transcripcion, manual y pdf (bytes)."""
    audio, _ = extraer_audio(ruta_video)
    transcripcion = transcribir(audio)
    manual = resumir_a_manual(transcripcion, titulo)
    pdf = generar_pdf(titulo, manual)
    return {"transcripcion": transcripcion, "manual": manual, "pdf": pdf}
