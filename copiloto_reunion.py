"""
Copiloto de Reunión — Proyecto Asistente IA de Procesos
==================================================
App SEPARADA (no es la intranet). Te ayuda a responder al instante preguntas
sobre el proyecto durante una reunión/llamada (ej. Teams).

Cómo funciona:
  1. Presionas un botón y grabas (tu micrófono).
  2. Se transcribe con Whisper (OpenAI).
  3. GPT responde usando el CONTEXTO técnico del proyecto (abajo).

Despliegue: crea una NUEVA app en Streamlit Cloud apuntando a este archivo
(copiloto_reunion.py) como "Main file path". Usa el mismo Secret OPENAI_API_KEY.
"""

import os
import io
import tempfile
import streamlit as st

st.set_page_config(page_title="🎤 Copiloto de Reunión", page_icon="🎤", layout="centered")

# ====== CONTEXTO DEL PROYECTO (la IA responde con esto) ======
PROYECTO_CONTEXT = """
PROYECTO: Asistente IA Corporativo "ProcesosIAEngine v2.0".
QUÉ ES: un chatbot interno que responde dudas sobre procesos de atención de solicitudes y
facturación usando los manuales (PDFs) de la empresa. Técnica: RAG (Recuperación
Aumentada por Generación) — la IA NO inventa, responde solo con la documentación.

ARQUITECTURA (flujo de una pregunta):
- Usuario (navegador) -> App en Streamlit -> Motor IA (RAG) -> OpenAI GPT-3.5.
- Datos: los PDFs de manuales viven en el repositorio; se procesan y se guardan como vectores en ChromaDB.
- El Motor IA busca en ChromaDB el documento correcto y se lo pasa a GPT para redactar.

CÓMO RAZONA LA IA (RAG, 6 pasos):
1) Indexación: cada PDF se parte en fragmentos y se convierte en vectores (embeddings).
2) Pregunta del usuario.
3) Búsqueda de los fragmentos más parecidos en ChromaDB.
4) Selección de UN solo documento (combinando título + semántica) para no mezclar casos.
5) GPT-3.5 redacta usando SOLO ese documento.
6) Continuidad: recuerda el caso para preguntas de seguimiento ("paso a paso").

TECNOLOGÍAS:
- Frontend/App: Streamlit 1.28 (Python 3.11).
- LLM: OpenAI GPT-3.5-turbo. Framework: LangChain.
- Base vectorial: ChromaDB. Embeddings: OpenAI (text-embedding-ada-002).
- PDFs: pypdf. Seguridad: bcrypt. Repo/CI: GitHub. Hosting: Streamlit Community Cloud.

ARCHIVOS CLAVE:
- app.py: interfaz (login, chat, panel admin, seguridad, control de servidor).
- ia_motor.py: Motor IA/RAG (búsqueda, selección de caso, generación).
- procesar_datos.py: lectura de PDFs y creación de la base vectorial.
- chat_procesos.py: conversación y memoria por usuario.
- .streamlit/config.toml: tema oscuro y config del servidor.
- estado_app.json (opcional): interruptor de mantenimiento.

SEGURIDAD:
- Una cuenta por persona (sin mezclar información), sesiones aisladas.
- Contraseñas cifradas con bcrypt (en Streamlit Secrets).
- Bloqueo temporal tras 5 intentos fallidos (anti fuerza bruta).
- Auto-logout por inactividad (15 min).
- Modo mantenimiento (cerrar/activar) desde el panel de administración.
- HTTPS y protección XSRF (a nivel plataforma).

DESPLIEGUE/MANTENIMIENTO:
- Código en GitHub (rama main); cada cambio redespliega solo.
- Auto-indexado al iniciar (Streamlit Cloud borra el disco al redesplegar).
- Carpetas dinámicas: subir una carpeta de PDFs nueva la indexa sola.

RESULTADOS: asistente funcional en la nube, respuestas completas por caso, interfaz
moderna estilo ChatGPT/Gemini, multiusuario seguro, indexado automático.
PRÓXIMOS PASOS: GPT-4 si se requiere, métricas de uso, más manuales/áreas.
"""

# ====== OpenAI (compatible con openai==0.28.1) ======
def _get_key():
    try:
        from secretos import hay_archivo_secrets
        if hay_archivo_secrets() and "OPENAI_API_KEY" in st.secrets:
            return st.secrets["OPENAI_API_KEY"]
    except Exception:
        pass
    return os.getenv("OPENAI_API_KEY", "")

import openai
openai.api_key = _get_key()


def transcribir(audio_bytes: bytes) -> str:
    """Transcribe audio (bytes WAV) usando Whisper."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            ruta = tmp.name
        with open(ruta, "rb") as f:
            tr = openai.Audio.transcribe("whisper-1", f)
        try:
            os.remove(ruta)
        except Exception:
            pass
        # openai 0.28 devuelve dict-like
        return tr["text"] if isinstance(tr, dict) else getattr(tr, "text", "")
    except Exception as e:
        return f"__ERROR__: {e}"


def responder(pregunta: str, modo: str) -> str:
    """Responde la pregunta usando el contexto del proyecto."""
    if modo == "decir":
        instruccion = (
            "Eres el copiloto del expositor. Te van a dar una pregunta que le hicieron "
            "en una reunión sobre el proyecto. Redacta una respuesta BREVE, clara y "
            "profesional que el expositor pueda LEER EN VOZ ALTA (máx. 5 frases). "
            "Tono natural, en primera persona del equipo (\"nosotros\")."
        )
    else:
        instruccion = (
            "Eres un asistente técnico. Responde la pregunta del usuario sobre el "
            "proyecto de forma clara y concisa (máx. 6 frases o lista corta)."
        )
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            temperature=0.3,
            max_tokens=400,
            messages=[
                {"role": "system", "content": instruccion + "\n\nCONTEXTO DEL PROYECTO:\n" + PROYECTO_CONTEXT},
                {"role": "user", "content": pregunta},
            ],
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"❌ Error generando respuesta: {e}"


# ====== ESTILOS ======
st.markdown("""
<style>
    [data-testid="stAppViewContainer"], section.main { background:#212121 !important; }
    h1, h2, h3, p, label, .stMarkdown { color:#ececf1 !important; }
    .tarjeta { background:#2f2f2f; border:1px solid #3c4043; border-radius:12px; padding:16px 18px; margin-top:10px; }
    .etq { color:#8ab4f8; font-weight:700; font-size:.8rem; text-transform:uppercase; letter-spacing:.5px; }
</style>
""", unsafe_allow_html=True)

st.title("🎤 Copiloto de Reunión")
st.caption("Asistente en vivo sobre el proyecto **Asistente IA de Procesos**. Graba tu micrófono y responde al instante.")

if not openai.api_key:
    st.error("⚠️ Falta OPENAI_API_KEY en los Secrets de esta app.")

# ====== Grabador de micrófono ======
try:
    from streamlit_mic_recorder import mic_recorder
    HAY_MIC = True
except Exception:
    HAY_MIC = False

if not HAY_MIC:
    st.warning("Falta el componente de micrófono. Agrega `streamlit-mic-recorder` a requirements.txt.")

if "ultimo_audio_id" not in st.session_state:
    st.session_state.ultimo_audio_id = {"decir": None, "responder": None}

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🎤 Pregunta que me hicieron")
    st.caption("Graba la pregunta del cliente/jefe. Te doy una respuesta lista para decir.")
    if HAY_MIC:
        audio1 = mic_recorder(start_prompt="🔴 Grabar", stop_prompt="⏹️ Detener",
                              key="rec_decir", format="wav")
        if audio1 and audio1.get("id") != st.session_state.ultimo_audio_id["decir"]:
            st.session_state.ultimo_audio_id["decir"] = audio1.get("id")
            with st.spinner("Transcribiendo..."):
                texto = transcribir(audio1["bytes"])
            if texto.startswith("__ERROR__"):
                st.error(texto)
            else:
                st.markdown(f"<div class='tarjeta'><span class='etq'>Pregunta</span><br>{texto}</div>", unsafe_allow_html=True)
                with st.spinner("Pensando respuesta..."):
                    r = responder(texto, "decir")
                st.markdown(f"<div class='tarjeta'><span class='etq'>Respuesta para decir</span><br>{r}</div>", unsafe_allow_html=True)

with col2:
    st.markdown("### 🙋 Mi pregunta")
    st.caption("Pregúntame algo del proyecto y te respondo directo.")
    if HAY_MIC:
        audio2 = mic_recorder(start_prompt="🔵 Grabar", stop_prompt="⏹️ Detener",
                              key="rec_responder", format="wav")
        if audio2 and audio2.get("id") != st.session_state.ultimo_audio_id["responder"]:
            st.session_state.ultimo_audio_id["responder"] = audio2.get("id")
            with st.spinner("Transcribiendo..."):
                texto = transcribir(audio2["bytes"])
            if texto.startswith("__ERROR__"):
                st.error(texto)
            else:
                st.markdown(f"<div class='tarjeta'><span class='etq'>Tu pregunta</span><br>{texto}</div>", unsafe_allow_html=True)
                with st.spinner("Pensando..."):
                    r = responder(texto, "responder")
                st.markdown(f"<div class='tarjeta'><span class='etq'>Respuesta</span><br>{r}</div>", unsafe_allow_html=True)

st.divider()
st.markdown("### ⌨️ ¿Prefieres escribir?")
pregunta_txt = st.text_input("Escribe una pregunta del proyecto", key="txt_q")
modo_txt = st.radio("Tipo", ["Respuesta para decir", "Respuesta directa"], horizontal=True, key="modo_txt")
if st.button("Responder", type="primary") and pregunta_txt.strip():
    modo = "decir" if modo_txt == "Respuesta para decir" else "responder"
    with st.spinner("Pensando..."):
        r = responder(pregunta_txt, modo)
    st.markdown(f"<div class='tarjeta'><span class='etq'>Respuesta</span><br>{r}</div>", unsafe_allow_html=True)
