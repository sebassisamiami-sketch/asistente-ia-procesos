# app.py - ProcesosIAEngine v2.0 OPTIMIZADO
"""
ProcesosIAEngine v2.0 - Sistema IA Corporativo
Optimizado para Streamlit Cloud
"""

import streamlit as st
from pathlib import Path

# ===== LOGO DE LA PÁGINA =====
# Cargamos logo.png como ícono de la página (pestaña del navegador).
# Si por alguna razón no se puede cargar, usamos el emoji como respaldo.
LOGO_PATH = Path(__file__).parent / "logo.png"
try:
    from PIL import Image
    _page_icon = Image.open(LOGO_PATH) if LOGO_PATH.exists() else "🤖"
except Exception:
    _page_icon = "🤖"

import base64

def _logo_data_uri():
    """Devuelve el logo como data URI para incrustarlo en HTML (bienvenida)."""
    try:
        if LOGO_PATH.exists():
            data = base64.b64encode(LOGO_PATH.read_bytes()).decode()
            return f"data:image/png;base64,{data}"
    except Exception:
        pass
    return ""

# ===== CONFIGURACIÓN INICIAL (DEBE SER LO PRIMERO) =====
st.set_page_config(
    page_title="Asistente IA de Procesos",
    page_icon=_page_icon,
    layout="wide",
    initial_sidebar_state="expanded"
)

import logging
import os
from secretos import hay_archivo_secrets
import json
import csv
import html
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

# ===== FUNCIONES DE INICIALIZACIÓN =====
@st.cache_resource(show_spinner=False)
def inicializar_sistema():
    """Inicializar sistema una sola vez"""
    from dotenv import load_dotenv
    
    # Cargar variables de entorno
    load_dotenv()
    
    # Verificar API Key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.error("❌ OPENAI_API_KEY no configurada")
        st.info("Por favor, configura tu API key en Streamlit Cloud → Settings → Secrets")
        st.stop()
    
    # Crear directorios necesarios
    directorios = [
        "data/pdfs", "data/db", "data/sessions", 
        "logs", "Manual Solicitudes", "Manual Facturacion"
    ]
    
    for directorio in directorios:
        Path(directorio).mkdir(parents=True, exist_ok=True)
    
    # Configurar logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/app.log'),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info("✅ Sistema inicializado")
    
    return logger

# Inicializar sistema
logger = inicializar_sistema()

# ===== IMPORTS LAZY (solo cuando sea necesario) =====
@st.cache_resource(show_spinner=False)
def cargar_motor_ia():
    """Cargar motor IA una sola vez (rápido: NO indexa aquí para no bloquear el login)."""
    try:
        from ia_motor import obtener_motor
        logger.info("✅ Cargando motor IA...")
        motor = obtener_motor()
        logger.info("✅ Motor IA listo (indexado diferido)")
        return motor
    except Exception as e:
        logger.error(f"❌ Error cargando motor: {e}")
        return None


@st.cache_resource(show_spinner=False)
def asegurar_indice():
    """Indexa los PDFs UNA sola vez, de forma perezosa (al primer uso del chat).
    Cacheado con cache_resource: solo corre la primera vez por despliegue, así el
    login NO espera por la indexación."""
    try:
        motor = cargar_motor_ia()
        _autoindexar_documentos(motor)
        return True
    except Exception as e:
        logger.error(f"⚠️ Error asegurando índice: {e}")
        return False

def detectar_carpetas_documentos():
    """Detecta las carpetas (a nivel raíz del repo) que contienen PDFs.
    Cada una se trata como una sección. Devuelve una lista de nombres."""
    base = Path(__file__).parent
    excluir = {".git", ".streamlit", ".devcontainer", ".agents", "data",
               "logs", "__pycache__", ".github"}
    carpetas = []
    try:
        for d in sorted(base.iterdir(), key=lambda x: x.name.lower()):
            if d.is_dir() and d.name not in excluir and not d.name.startswith("."):
                if any(True for _ in d.rglob("*.pdf")):
                    carpetas.append(d.name)
    except Exception as e:
        logger.error(f"Error detectando carpetas: {e}")
    return carpetas

def subcarpetas_con_pdfs(nombre_carpeta):
    """Lista las subcarpetas (y PDFs sueltos) que contienen PDFs dentro de una carpeta."""
    base = Path(__file__).parent / nombre_carpeta
    subs = []
    try:
        for sub in sorted(base.iterdir(), key=lambda x: x.name.lower()):
            if sub.is_dir():
                n = len(list(sub.rglob("*.pdf")))
                if n > 0:
                    subs.append((sub.name, n))
        pdfs_raiz = list(base.glob("*.pdf"))
        if pdfs_raiz:
            subs.append(("(archivos sueltos)", len(pdfs_raiz)))
    except Exception:
        pass
    return subs

def _autoindexar_documentos(motor):
    """Indexa los PDFs del repo automaticamente si el indice esta vacio.

    Streamlit Cloud borra el disco en cada redespliegue, por eso reconstruimos
    el indice al arrancar para que la IA siempre tenga los documentos.
    """
    try:
        if not motor or not getattr(motor, "vectorstore", None):
            return
        try:
            count = motor.vectorstore._collection.count()
        except Exception:
            count = 0
        if count and count > 0:
            logger.info(f"📚 Indice ya tiene {count} documentos")
            return
        logger.info("📚 Indice vacio: indexando PDFs automaticamente...")
        from procesar_datos import DataProcessor
        processor = DataProcessor()
        total = 0
        for carpeta in detectar_carpetas_documentos():
            res = processor.procesar_carpeta(carpeta, carpeta)
            if res.get('exito'):
                total += res.get('chunks_creados', 0)
        logger.info(f"✅ Auto-indexado completado: {total} chunks")
    except Exception as e:
        logger.error(f"⚠️ Error auto-indexando: {e}", exc_info=True)

def cargar_chat_processor(usuario, rol):
    """Cargar chat processor"""
    try:
        from chat_procesos import ChatProcessor
        logger.info(f"✅ Chat processor para {usuario}")
        return ChatProcessor(usuario, rol)
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return None

def cargar_data_processor():
    """Cargar data processor"""
    try:
        from procesar_datos import DataProcessor
        return DataProcessor()
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return None


# ===== USUARIOS Y ROLES ADMINISTRABLES =====
ARCHIVO_USUARIOS = "data/usuarios.json"

# ===== ESTADO DEL SERVIDOR (interruptor de mantenimiento) =====
# Se guarda en la raíz del proyecto; si no existe, el servidor se considera activo.
ESTADO_APP_PATH = Path(__file__).parent / "estado_app.json"

def leer_estado_app() -> bool:
    """True si el servidor está activo; False si está en mantenimiento."""
    try:
        if ESTADO_APP_PATH.exists():
            with open(ESTADO_APP_PATH, 'r', encoding='utf-8') as f:
                return bool(json.load(f).get("servidor_activo", True))
    except Exception:
        pass
    return True

def guardar_estado_app(activo: bool) -> bool:
    """Guarda el estado del servidor (activo o mantenimiento)."""
    try:
        with open(ESTADO_APP_PATH, 'w', encoding='utf-8') as f:
            json.dump({"servidor_activo": bool(activo)}, f, ensure_ascii=False, indent=2)
        logger.info(f"🖥️ Estado del servidor: activo={activo}")
        return True
    except Exception as e:
        logger.error(f"Error guardando estado del servidor: {e}")
        return False

def cargar_usuarios() -> Dict[str, Dict]:
    """Cargar usuarios combinando: variables de entorno + Secrets (permanentes) + archivo local.

    No hay contraseñas escritas en el código:
    - Variables de entorno ADMIN_USER / ADMIN_PASSWORD: crean el administrador inicial.
    - Secrets: persisten siempre (recomendado para los demás usuarios).
    - Archivo local (data/usuarios.json): creados en la app, se pierden al redesplegar.
    """
    # 1) Administrador inicial desde variables de entorno
    usuarios = {}
    admin_pass = os.getenv("ADMIN_PASSWORD")
    if admin_pass:
        usuarios[os.getenv("ADMIN_USER", "admin")] = {"contraseña": admin_pass, "rol": "Administrador"}

    # 2) Usuarios PERMANENTES definidos en Streamlit Secrets ([usuarios.<nombre>])
    try:
        secret_users = st.secrets.get("usuarios", None) if hay_archivo_secrets() else None
        if secret_users:
            for nombre, datos in dict(secret_users).items():
                datos = dict(datos)
                usuarios[nombre] = {
                    "contraseña": datos.get("contraseña", datos.get("password", "")),
                    "rol": datos.get("rol", "Analista")
                }
    except Exception:
        pass

    # 3) Usuarios creados en la app (temporales hasta el próximo redespliegue)
    if Path(ARCHIVO_USUARIOS).exists():
        try:
            with open(ARCHIVO_USUARIOS, 'r', encoding='utf-8') as f:
                usuarios.update(json.load(f))
        except Exception:
            pass

    return usuarios

def guardar_usuarios(usuarios: Dict):
    """Guardar usuarios en archivo"""
    Path("data").mkdir(exist_ok=True)
    with open(ARCHIVO_USUARIOS, 'w', encoding='utf-8') as f:
        json.dump(usuarios, f, ensure_ascii=False, indent=2)
    logger.info("✅ Usuarios guardados")

def _verificar_password(plano: str, almacenado: str) -> bool:
    """Verifica la contraseña. Soporta hash bcrypt y texto plano (compatibilidad)."""
    if not isinstance(almacenado, str) or plano is None:
        return False
    # ¿Es un hash bcrypt?
    if almacenado.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            import bcrypt
            return bcrypt.checkpw(plano.encode("utf-8"), almacenado.encode("utf-8"))
        except Exception:
            return False
    # Texto plano (sigue funcionando para no romper nada)
    return plano == almacenado

def registrar_acceso(usuario: str, rol: str, accion: str = "LOGIN"):
    """Registrar acceso en CSV"""
    try:
        archivo_log = "logs/registro_conexiones.csv"
        archivo_existe = os.path.exists(archivo_log)
        
        with open(archivo_log, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not archivo_existe:
                writer.writerow(['Timestamp', 'Usuario', 'Rol', 'Acción', 'IP', 'Sesión'])
            
            writer.writerow([
                datetime.now().isoformat(),
                usuario,
                rol,
                accion,
                st.session_state.get('ip', 'local'),
                st.session_state.get('session_id', 'N/A')
            ])
    except Exception as e:
        logger.error(f"Error registrando acceso: {e}")

# ===== CSS PERSONALIZADO =====
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* Tipografía profesional en toda la app */
    html, body, [class*="css"], .stApp,
    section.main, section[data-testid="stSidebar"],
    input, textarea, button, select {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif !important;
    }

    /* Ocultar barra/herramientas de Streamlit (Deploy, menu, footer) y franja blanca superior */
    header[data-testid="stHeader"] {
        background: transparent !important;
        height: 0 !important;
    }
    [data-testid="stToolbar"] { display: none !important; }
    [data-testid="stDecoration"] { display: none !important; }
    [data-testid="stStatusWidget"] { display: none !important; }
    #MainMenu { display: none !important; }
    footer { display: none !important; }

    /* ===== Ocultar badge/insignia de Streamlit Community Cloud =====
       (el "Hosted with Streamlit" y el perfil "hosted by <tu cuenta>" que
       aparece para que se vea más profesional y sin marca personal). */
    [data-testid="stToolbarActions"] { display: none !important; }
    [data-testid="manage-app-button"] { display: none !important; }
    [data-testid="stAppDeployButton"] { display: none !important; }
    [class*="viewerBadge"] { display: none !important; }
    [class*="profileContainer"] { display: none !important; }
    a[href*="streamlit.io/cloud"] { display: none !important; }
    a[href*="share.streamlit.io"] { display: none !important; }
    a[href*="streamlit.app"][target="_blank"] { display: none !important; }
    .viewerBadge_container__r5tak,
    .viewerBadge_link__qRIco,
    ._profileContainer_gzau3_53,
    ._container_gzau3_1,
    ._link_gzau3_10,
    ._profilePreview_gzau3_63 { display: none !important; }

    /* ===== Intento final: footer del modo embed "Built with Streamlit" + "Fullscreen" =====
       Se oculta cualquier enlace a streamlit.io y su contenedor directo, además del
       botón de pantalla completa del modo embed. (Algunos elementos los pone el
       hosting fuera del alcance del CSS; si persiste, es atribución del plan gratis.) */
    a[href*="streamlit.io"] { display: none !important; }
    div:has(> a[href*="streamlit.io"]) { display: none !important; }
    span:has(> a[href*="streamlit.io"]) { display: none !important; }
    button[title="Fullscreen"],
    button[title="Enter fullscreen"],
    button[title="Exit fullscreen"] { display: none !important; }
    [class*="viewerBadge"],
    [class*="ViewerBadge"],
    [class*="_viewerBadge"],
    [class*="stAppViewBadge"] { display: none !important; }


    /* Colores corporativos */
    :root {
        --primary: #667eea;
        --secondary: #764ba2;
        --success: #21a366;
        --danger: #e74c3c;
    }
    
    /* Contenedor de login */
    .login-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 50px;
        border-radius: 20px;
        max-width: 500px;
        margin: 50px auto;
        color: white;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    }
    
    .login-container h1 {
        text-align: center;
        margin-bottom: 10px;
    }
    
    .login-container p {
        text-align: center;
        margin-bottom: 30px;
        opacity: 0.9;
    }
    
    /* Botones */
    .stButton button {
        border-radius: 10px;
        font-weight: bold;
        padding: 10px 20px;
        transition: all 0.3s ease;
    }
    
    .stButton button:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 20px rgba(0, 0, 0, 0.2);
    }
    
    /* Sidebar estilo ChatGPT (oscuro) */
    section[data-testid="stSidebar"] {
        background: #171717 !important;
        border-right: 1px solid #2a2a2a;
    }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] h4,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] * {
        color: #ececf1 !important;
    }
    section[data-testid="stSidebar"] hr { border-color: #2a2a2a !important; }
    /* Selectbox del sidebar en oscuro */
    section[data-testid="stSidebar"] div[data-baseweb="select"] > div {
        background: #2a2a2a !important;
        color: #ececf1 !important;
        border-color: #3a3a3a !important;
    }
    /* Botones del sidebar: degradado gris elegante con borde sutil */
    section[data-testid="stSidebar"] .stButton button {
        background: linear-gradient(135deg, #3a3a40, #29292e) !important;
        color: #ececf1 !important;
        border: 1px solid #3f3f46 !important;
        border-radius: 10px !important;
        font-weight: 500 !important;
        transition: all .2s ease;
    }
    section[data-testid="stSidebar"] .stButton button:hover {
        background: linear-gradient(135deg, #45454c, #313137) !important;
        border-color: #8ab4f8 !important;
        transform: translateY(-1px);
    }

    /* Ocultar el botón "Ver pantalla completa" de las imágenes/logos */
    button[title="View fullscreen"],
    [data-testid="StyledFullScreenButton"],
    [data-testid="StyledFullScreenButton"] button {
        display: none !important;
    }
    
    /* Cards */
    .stats-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 20px;
        border-radius: 15px;
        margin: 10px 0;
        box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
    }
    
    .stats-card h3 {
        margin-top: 0;
    }
    
    .stats-card .value {
        font-size: 28px;
        font-weight: bold;
    }
    
    /* Mensajes */
    .chat-message {
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
        border-left: 4px solid #667eea;
    }
    
    .user-message {
        background: #f0f4ff;
        border-left-color: #667eea;
    }
    
    .ai-message {
        background: #f5f5f5;
        border-left-color: #764ba2;
    }
    
    /* Inputs */
    .stTextInput input, .stTextArea textarea {
        border-radius: 10px !important;
    }
    
    /* Dividers */
    hr {
        margin: 20px 0;
    }

    /* ===== CHAT MODERNO Y MINIMALISTA ===== */
    .chat-bubble {
        border-radius: 14px;
        padding: 14px 18px;
        margin: 8px 0;
        line-height: 1.5;
        animation: fadeIn .25s ease;
    }
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(6px); }
        to   { opacity: 1; transform: translateY(0); }
    }
    .user-bubble {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: #ffffff;
        margin-left: 18%;
        box-shadow: 0 4px 14px rgba(102, 126, 234, 0.25);
    }
    .ai-bubble {
        background: #f4f6fb;
        color: #1f2937;
        margin-right: 12%;
        border: 1px solid #e6e9f2;
    }
    .bubble-label {
        font-size: .72rem;
        font-weight: 700;
        letter-spacing: .6px;
        text-transform: uppercase;
        opacity: .75;
        margin-bottom: 4px;
    }
    .bubble-text { font-size: .95rem; }
    .chat-time {
        font-size: .7rem;
        color: #9ca3af;
        margin: 2px 0 14px 0;
    }

    /* ===== FUENTES ESTILO VENTANA DE COMANDOS / TERMINAL ===== */
    div[data-testid="stCodeBlock"] {
        background: #0d1117 !important;
        border-radius: 10px;
        border: 1px solid #30363d;
        box-shadow: 0 6px 18px rgba(0, 0, 0, 0.35);
        overflow: hidden;
    }
    div[data-testid="stCodeBlock"] pre {
        background: #0d1117 !important;
        color: #c9d1d9 !important;
        padding: 16px !important;
        font-size: .82rem !important;
    }
    div[data-testid="stCodeBlock"] code { color: #c9d1d9 !important; }
    /* Barra superior tipo ventana con tres "botones" */
    .terminal-bar {
        background: #161b22;
        border: 1px solid #30363d;
        border-bottom: none;
        border-radius: 10px 10px 0 0;
        padding: 8px 12px;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        font-size: .75rem;
        color: #8b949e;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .terminal-bar .dot {
        width: 11px; height: 11px; border-radius: 50%;
        display: inline-block;
    }
    .terminal-bar .red    { background: #ff5f56; }
    .terminal-bar .yellow { background: #ffbd2e; }
    .terminal-bar .green  { background: #27c93f; }
    .terminal-bar .title  { margin-left: 10px; }
    /* Pega el code block a la barra del terminal */
    .terminal-bar + div[data-testid="stCodeBlock"] {
        border-radius: 0 0 10px 10px;
        margin-top: 0;
    }
</style>
""", unsafe_allow_html=True)

# ===== INICIALIZAR SESIÓN =====
def inicializar_sesion():
    """Inicializar variables de sesión"""
    variables_default = {
        "autenticado": False,
        "usuario": None,
        "rol": None,
        "motor_ia": None,
        "chat_processor": None,
        "historial": [],
        "inicio_sesion": None,
        "sidebar_expandido": True,
        "session_id": str(datetime.now().timestamp()),
        "ip": "local",
        "intentos_fallidos": 0,
        "bloqueo_hasta": None,
        "ultima_actividad": None
    }
    
    for var, valor_default in variables_default.items():
        if var not in st.session_state:
            st.session_state[var] = valor_default

# ===== PANTALLA LOGIN =====
def pantalla_login():
    """Pantalla de login"""
    
    usuarios = cargar_usuarios()
    
    col1, col2, col3 = st.columns([1, 12, 1])
    
    with col2:
        # Estilos estilo Microsoft (tarjeta blanca centrada) SOLO para login
        st.markdown("""
        <style>
            /* Fondo con degradado suave y elegante */
            [data-testid="stAppViewContainer"] {
                background: linear-gradient(135deg, #f5f7fb 0%, #eef1f7 45%, #e7ecf4 100%) !important;
            }
            [data-testid="stHeader"] { background: transparent; }

            /* Tarjeta central blanca, limpia y con sombra suave */
            section.main .block-container {
                max-width: 470px;
                background: #ffffff;
                padding: 46px 44px 38px 44px;
                margin-top: 7vh;
                box-shadow: 0 12px 40px rgba(31, 41, 70, 0.12),
                            0 2px 8px rgba(31, 41, 70, 0.08);
                border: 1px solid #eceff4;
                border-radius: 14px;
            }

            /* Encabezado */
            .ms-title {
                font-size: 1.55rem; font-weight: 600;
                color: #1b1b1b; margin: 16px 0 6px 0;
            }
            .ms-sub { color: #605e5c; font-size: .9rem; margin-bottom: 20px; }

            /* Etiquetas */
            section.main .stTextInput label,
            section.main .stSelectbox label {
                color: #1b1b1b !important; font-weight: 600; font-size: .85rem;
                letter-spacing: .2px; margin-bottom: 6px;
            }
            /* Inputs limpios y profesionales */
            /* La CASILLA completa (contenedor) lleva el borde redondeado.
               Así el input y el botón del ojo quedan dentro del mismo recuadro. */
            section.main .stTextInput div[data-baseweb="input"] {
                background: #ffffff !important;
                border: 1px solid #c8c6c4 !important;
                border-radius: 12px !important;
                box-shadow: none !important;
                overflow: hidden !important;
                transition: border-color .15s ease, box-shadow .15s ease;
            }
            /* Forzar BLANCO en las capas internas de Streamlit (tema oscuro) */
            section.main .stTextInput div[data-baseweb="input"] > div,
            section.main .stTextInput [data-baseweb="base-input"] {
                background: #ffffff !important;
            }
            /* Select del login (si aplica) */
            section.main div[data-baseweb="select"] > div {
                background: #ffffff !important;
                color: #1b1b1b !important;
                border: 1px solid #c8c6c4 !important;
                border-radius: 12px !important;
            }
            /* El input interno SIN borde propio (evita el doble borde) */
            section.main .stTextInput div[data-baseweb="input"] > input,
            section.main .stTextInput input {
                background: transparent !important;
                color: #1b1b1b !important;
                -webkit-text-fill-color: #1b1b1b !important;
                border: none !important;
                box-shadow: none !important;
                padding: 12px 14px !important;
                font-size: .95rem !important;
                font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif !important;
            }
            /* Texto guía (placeholder) más oscuro y con mejor tipografía */
            section.main .stTextInput input::placeholder {
                color: #5b5b5b !important;
                -webkit-text-fill-color: #5b5b5b !important;
                opacity: 1 !important;
                font-weight: 400 !important;
                font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif !important;
                letter-spacing: .1px;
            }
            /* Hover sutil */
            section.main .stTextInput div[data-baseweb="input"]:hover {
                border-color: #8a8886 !important;
            }
            /* GLOW AZUL BRILLANTE solo cuando la casilla está seleccionada (foco) */
            section.main .stTextInput div[data-baseweb="input"]:focus-within {
                border-color: #2b88ff !important;
                box-shadow: 0 0 0 3px rgba(43, 136, 255, 0.35),
                            0 0 10px rgba(43, 136, 255, 0.25) !important;
            }
            /* El input interno no dibuja su propio halo (lo hace el contenedor) */
            section.main .stTextInput input:focus {
                box-shadow: none !important;
                border: none !important;
            }
            /* Botón mostrar/ocultar contraseña: gris matizado y semitransparente */
            section.main .stTextInput div[data-baseweb="input"] button {
                background: transparent !important;
                border: none !important;
                color: rgba(96, 94, 92, 0.55) !important;
            }
            section.main .stTextInput div[data-baseweb="input"] button svg {
                fill: rgba(96, 94, 92, 0.55) !important;
            }
            section.main .stTextInput div[data-baseweb="input"] button:hover,
            section.main .stTextInput div[data-baseweb="input"] button:hover svg {
                color: rgba(43, 136, 255, 0.85) !important;
                fill: rgba(43, 136, 255, 0.85) !important;
            }
            /* Botón azul Microsoft (incluye el botón del formulario de login) */
            section.main .stButton button[kind="primary"],
            section.main [data-testid="stFormSubmitButton"] button {
                background: #0067b8 !important;
                color: #ffffff !important;
                border: none !important;
                border-radius: 6px !important;
                font-weight: 600;
                padding: 11px 16px !important;
            }
            section.main .stButton button[kind="primary"]:hover,
            section.main [data-testid="stFormSubmitButton"] button:hover {
                background: #005da6 !important;
                transform: none;
                box-shadow: none;
            }
        </style>
        """, unsafe_allow_html=True)

        # Logo (estilo Microsoft, arriba a la izquierda)
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=108)

        st.markdown('<div class="ms-title">Iniciar sesión</div>', unsafe_allow_html=True)
        st.markdown('<div class="ms-sub">Usa tu cuenta de la demo</div>', unsafe_allow_html=True)

        # Aviso si llegaron con un enlace de invitación inválido o caducado
        if st.session_state.get("_invite_error"):
            st.error("🔗 El enlace de invitación no es válido o ya caducó. "
                     "Solicita un enlace nuevo al administrador.")
        
        # Escribir el usuario y la contraseña DENTRO de un formulario,
        # así se puede enviar con Enter (no solo con el botón).
        with st.form("login_form"):
            usuario_input = st.text_input(
                "Usuario",
                key="input_usuario_login",
                placeholder="Escribe tu usuario"
            )
            contraseña = st.text_input(
                "Contraseña",
                type="password",
                key="input_password_login"
            )
            _enviar = st.form_submit_button(
                "Iniciar sesión", use_container_width=True, type="primary"
            )

        col_login = st.container()

        with col_login:
            if _enviar:
                
                # 🔒 Bloqueo temporal por intentos fallidos
                bloqueo_hasta = st.session_state.get("bloqueo_hasta")
                if bloqueo_hasta and datetime.now() < bloqueo_hasta:
                    restante = int((bloqueo_hasta - datetime.now()).total_seconds())
                    st.error(f"🔒 Demasiados intentos. Intenta de nuevo en {restante} segundos.")
                    return

                if not usuario_input or not usuario_input.strip():
                    st.error("❌ Ingresa tu usuario")
                    return

                if not contraseña:
                    st.error("❌ Ingresa la contraseña")
                    return

                # Resolver el usuario escrito (sin distinguir mayúsculas/minúsculas)
                usuario_seleccionado = usuario_input.strip()
                usuario_data = usuarios.get(usuario_seleccionado)
                if not usuario_data:
                    for _k, _v in usuarios.items():
                        if _k.lower() == usuario_seleccionado.lower():
                            usuario_seleccionado = _k
                            usuario_data = _v
                            break
                
                if not usuario_data or not _verificar_password(contraseña, usuario_data.get('contraseña', '')):
                    st.session_state.intentos_fallidos = st.session_state.get("intentos_fallidos", 0) + 1
                    intentos = st.session_state.intentos_fallidos
                    logger.warning(f"Intento fallido ({intentos}/5): {usuario_seleccionado}")
                    if intentos >= 5:
                        st.session_state.bloqueo_hasta = datetime.now() + timedelta(minutes=2)
                        st.session_state.intentos_fallidos = 0
                        st.error("🔒 Demasiados intentos fallidos. Cuenta bloqueada por 2 minutos.")
                    else:
                        st.error(f"❌ Credenciales inválidas ({intentos}/5 intentos)")
                    return
                
                with st.spinner("Iniciando sesión..."):
                    try:
                        logger.info(f"Iniciando sesión para {usuario_seleccionado}")
                        
                        # Obtener motor IA (cached)
                        motor_ia = cargar_motor_ia()
                        
                        if not motor_ia:
                            st.error("❌ Motor IA no disponible")
                            st.info("Verifica que OPENAI_API_KEY esté configurada")
                            return
                        
                        estado_motor = motor_ia.obtener_estado()
                        logger.info(f"Estado motor: {estado_motor['estado']}")
                        
                        if estado_motor['estado'] != 'listo':
                            st.error(f"❌ Motor IA no disponible: {estado_motor['estado']}")
                            return
                        
                        # Inicializar chat processor
                        chat_processor = cargar_chat_processor(
                            usuario_seleccionado,
                            usuario_data['rol']
                        )
                        
                        if not chat_processor:
                            st.error("❌ Error inicializando chat")
                            return
                        
                        chat_processor._cargar_memoria_usuario()
                        
                        # Actualizar sesión
                        st.session_state.autenticado = True
                        st.session_state.usuario = usuario_seleccionado
                        st.session_state.rol = usuario_data['rol']
                        st.session_state.motor_ia = motor_ia
                        st.session_state.chat_processor = chat_processor
                        st.session_state.historial = chat_processor.historial_local
                        st.session_state.inicio_sesion = datetime.now()
                        st.session_state.ultima_actividad = datetime.now()
                        st.session_state.intentos_fallidos = 0
                        st.session_state.bloqueo_hasta = None
                        
                        # Registrar
                        registrar_acceso(usuario_seleccionado, usuario_data['rol'], "LOGIN")
                        
                        logger.info(f"✅ Login exitoso: {usuario_seleccionado}")
                        # Guardar token de sesión; la URL se actualiza en el
                        # render ya autenticado (en main), para no perderlo por
                        # la carrera con st.rerun().
                        try:
                            from invite_links import generar_token_sesion
                            st.session_state.session_token = generar_token_sesion(
                                usuario_seleccionado, usuario_data['rol'], horas=8
                            )
                        except Exception:
                            pass
                        st.success(f"✅ ¡Bienvenido {usuario_seleccionado}!")
                        st.rerun()
                    
                    except Exception as e:
                        logger.error(f"❌ Error: {e}", exc_info=True)
                        st.error(f"❌ Error iniciando sistema:\n{str(e)}")
        
        # Nota discreta de acceso (la gestión de usuarios es solo para admin)
        st.markdown(
            "<p style='text-align:center; color:#64748b; font-size:.78rem; "
            "margin-top:22px;'>Acceso restringido &middot; La gestión de usuarios "
            "está disponible para administradores</p>",
            unsafe_allow_html=True
        )

        # 🚧 Aviso de mantenimiento si el servidor está cerrado
        if not leer_estado_app():
            st.markdown(
                "<div style='text-align:center; margin-top:16px; padding:14px; "
                "background:#3a1d1d; border:1px solid #b91c1c; border-radius:10px; "
                "color:#fca5a5; font-weight:600;'>🚧 En mantenimiento</div>",
                unsafe_allow_html=True
            )

# ===== PANTALLA PRINCIPAL =====
def pantalla_principal():
    """Pantalla principal después de login"""

    # 🚧 Si el servidor está en mantenimiento, solo el Administrador puede entrar
    if not leer_estado_app() and st.session_state.rol != "Administrador":
        st.markdown(
            "<div style='text-align:center; margin-top:22vh;'>"
            "<h1 style='color:#ececf1;'>🚧 En mantenimiento</h1>"
            "<p style='color:#9a9a9a;'>El servidor está temporalmente cerrado. "
            "Por favor vuelve a intentarlo más tarde.</p></div>",
            unsafe_allow_html=True
        )
        st.stop()

    # Sidebar expandible con tema profesional
    with st.sidebar:
        # Estilos del menú lateral (profesional y minimalista)
        st.markdown("""
        <style>
            section[data-testid="stSidebar"] .side-user {
                display:flex; align-items:center; gap:12px;
                background:#1f1f22; border:1px solid #2f2f35; border-radius:14px;
                padding:12px 14px; margin:6px 0 10px 0;
            }
            section[data-testid="stSidebar"] .side-avatar {
                width:42px; height:42px; border-radius:50%; flex:0 0 42px;
                background:linear-gradient(135deg,#8ab4f8,#764ba2);
                color:#fff; display:flex; align-items:center; justify-content:center;
                font-weight:700; font-size:18px;
            }
            section[data-testid="stSidebar"] .side-user-name {
                color:#ececf1; font-weight:600; font-size:.95rem; line-height:1.15;
            }
            section[data-testid="stSidebar"] .side-user-role {
                color:#8ab4f8; font-size:.78rem; margin-top:2px;
            }
            section[data-testid="stSidebar"] .side-label {
                color:#8e8ea0; font-size:.72rem; font-weight:700; letter-spacing:1.2px;
                text-transform:uppercase; margin:14px 0 6px 2px;
            }
        </style>
        """, unsafe_allow_html=True)

        # Logo de la empresa (centrado, compacto)
        if LOGO_PATH.exists():
            lc1, lc2, lc3 = st.columns([1, 2, 1])
            with lc2:
                st.image(str(LOGO_PATH), use_column_width=True)

        # Tarjeta de usuario
        _inicial = (st.session_state.usuario or "U")[0].upper()
        st.markdown(f"""
        <div class="side-user">
            <div class="side-avatar">{_inicial}</div>
            <div>
                <div class="side-user-name">{st.session_state.usuario}</div>
                <div class="side-user-role">{st.session_state.rol}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Navegación principal
        st.markdown('<div class="side-label">Navegación</div>', unsafe_allow_html=True)
        # Los invitados (acceso por enlace) solo ven el Chat
        opciones_nav = ["Chat"] if st.session_state.rol == "Invitado" else ["Chat", "Estadísticas"]
        opcion = st.radio(
            "Navegación",
            opciones_nav,
            label_visibility="collapsed",
            key="menu_principal"
        )
        
        # Panel Admin (solo para administradores)
        if st.session_state.rol == "Administrador":
            st.markdown('<div class="side-label">Administración</div>', unsafe_allow_html=True)
            
            admin_opcion = st.selectbox(
                "Herramientas Admin",
                [
                    "— Inicio —",
                    "Gestionar Usuarios",
                    "Enlaces de acceso",
                    "Procesar PDFs",
                    "Estado de BD",
                    "Registros de Acceso",
                    "Estadísticas IA",
                    "Control del Servidor",
                    "Video a Manual"
                ],
                label_visibility="collapsed",
                key="admin_menu"
            )
            
            st.divider()
        else:
            admin_opcion = None
        
        # Sesión
        st.markdown('<div class="side-label">Sesión</div>', unsafe_allow_html=True)
        
        col_sesion1, col_sesion2 = st.columns(2)
        
        with col_sesion1:
            if st.button("Limpiar chat", use_container_width=True):
                st.session_state.chat_processor.limpiar_historial()
                st.session_state.historial = []
                st.success("✅ Chat limpiado")
                st.rerun()
        
        with col_sesion2:
            if st.button("Cerrar sesión", use_container_width=True, type="secondary"):
                registrar_acceso(st.session_state.usuario, st.session_state.rol, "LOGOUT")
                
                st.session_state.autenticado = False
                st.session_state.usuario = None
                st.session_state.rol = None
                st.session_state.motor_ia = None
                st.session_state.chat_processor = None
                st.session_state.historial = []
                st.session_state.session_token = None
                # Marcamos cierre de sesión: la URL se limpia en el siguiente
                # render (en main), porque limpiarla aquí no persiste por la
                # carrera con st.rerun().
                st.session_state._post_logout = True
                
                logger.info("✅ Sesión cerrada")
                st.rerun()
        
        # Información
        st.markdown("---")
        st.caption(f"Sesión iniciada: {st.session_state.inicio_sesion.strftime('%H:%M:%S')}")
    
    # CONTENIDO PRINCIPAL
    mostrar_admin = (
        st.session_state.rol == "Administrador"
        and admin_opcion
        and admin_opcion != "— Inicio —"
    )

    if mostrar_admin:
        if admin_opcion == "Gestionar Usuarios":
            mostrar_admin_usuarios()
        elif admin_opcion == "Enlaces de acceso":
            mostrar_admin_enlaces()
        elif admin_opcion == "Procesar PDFs":
            mostrar_admin_pdfs()
        elif admin_opcion == "Estado de BD":
            mostrar_admin_bd()
        elif admin_opcion == "Registros de Acceso":
            mostrar_admin_accesos()
        elif admin_opcion == "Estadísticas IA":
            mostrar_admin_estadisticas_ia()
        elif admin_opcion == "Control del Servidor":
            mostrar_admin_servidor()
        elif admin_opcion == "Video a Manual":
            mostrar_admin_video()
    elif opcion == "Chat":
        mostrar_chat()
    elif opcion == "Estadísticas":
        mostrar_estadisticas()

def mostrar_chat():
    """Interfaz de chat estilo ChatGPT (oscuro, minimalista y fiel)"""

    # ===== TEMA OSCURO ESTILO CHATGPT =====
    st.markdown("""
    <style>
        [data-testid="stAppViewContainer"], section.main {
            background-color: #212121 !important;
        }
        /* Columna de conversacion centrada y estrecha */
        section.main .block-container {
            max-width: 900px;
            padding-top: 1.5rem;
            padding-bottom: 9rem;
        }
        section.main h1, section.main h2, section.main h3, section.main h4 {
            color: #ececf1 !important;
        }
        section.main .stMarkdown p, section.main .stMarkdown li,
        section.main .stMarkdown strong {
            color: #ececf1 !important;
            font-size: 1rem;
            line-height: 1.75;
        }
        section.main [data-testid="stCaptionContainer"] * { color: #9a9a9a !important; }

        /* Pantalla de bienvenida centrada */
        .welcome-screen { text-align: center; margin-top: 16vh; }
        .welcome-logo { width: 64px; height: auto; margin-bottom: 18px; }
        .welcome-title {
            color: #ececf1; font-weight: 600; font-size: 2rem;
            margin: 0; letter-spacing: -0.5px;
        }
        .welcome-sub { color: #9a9a9a; font-size: .95rem; margin-top: 8px; }

        /* Mensajes estilo ChatGPT */
        [data-testid="stChatMessage"] {
            background: transparent !important;
            padding: 10px 0 !important;
        }
        [data-testid="stChatMessage"] * { color: #ececf1 !important; }
        /* Avatar (logo) sin recortar: se ve completo y encuadrado */
        [data-testid="stChatMessage"] img {
            object-fit: contain !important;
            background: transparent !important;
            padding: 2px !important;
        }

        /* Barra inferior y caja de entrada estilo ChatGPT */
        [data-testid="stChatFloatingInputContainer"],
        div[class*="stChatFloatingInputContainer"],
        [data-testid="stBottom"],
        [data-testid="stBottom"] > div,
        [data-testid="stBottomBlockContainer"] {
            background-color: #212121 !important;
            border-top: none !important;
            box-shadow: none !important;
        }
        /* ===== Barra de busqueda estilo Gemini ===== */
        [data-testid="stChatInput"] {
            background: #1e1f20 !important;
            border: 1px solid #3c4043 !important;
            border-radius: 28px !important;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.45);
            padding: 8px 14px !important;
            transition: border-color .2s ease, box-shadow .2s ease;
        }
        [data-testid="stChatInput"]:focus-within {
            border-color: #8ab4f8 !important;
            box-shadow: 0 0 0 2px rgba(138, 180, 248, 0.30),
                        0 6px 26px rgba(0, 0, 0, 0.55) !important;
        }
        /* Quitar TODOS los bordes internos (elimina el segundo borde) */
        [data-testid="stChatInput"] *:not(button) {
            background: transparent !important;
            border: none !important;
            outline: none !important;
            box-shadow: none !important;
        }
        /* Boton de enviar circular con degradado */
        [data-testid="stChatInput"] button {
            background: linear-gradient(135deg, #8ab4f8, #4a7fe0) !important;
            border-radius: 50% !important;
            border: none !important;
            color: #ffffff !important;
            box-shadow: 0 2px 10px rgba(138, 180, 248, 0.5);
            transition: filter .2s ease, transform .1s ease;
        }
        [data-testid="stChatInput"] button:hover { filter: brightness(1.15); }
        [data-testid="stChatInput"] button:active { transform: scale(0.92); }
        [data-testid="stChatInput"] button svg {
            fill: #ffffff !important;
            color: #ffffff !important;
        }
        [data-testid="stChatInput"] textarea,
        textarea[data-testid="stChatInputTextArea"],
        [data-testid="stChatInput"] [data-baseweb="textarea"] textarea,
        section.main [data-testid="stChatInput"] textarea {
            background: transparent !important;
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
            caret-color: #8ab4f8 !important;
            opacity: 1 !important;
            font-size: 1.02rem !important;
            line-height: 1.5 !important;
            padding: 6px 8px !important;
        }
        [data-testid="stChatInput"] textarea::placeholder,
        textarea[data-testid="stChatInputTextArea"]::placeholder {
            color: #9a9aa8 !important;
            -webkit-text-fill-color: #9a9aa8 !important;
        }

        /* Expander de fuentes */
        section.main [data-testid="stExpander"] {
            border: 1px solid #3a3a3a !important;
            border-radius: 10px !important;
            background: #1a1a1a !important;
        }
        section.main [data-testid="stExpander"] summary,
        section.main [data-testid="stExpander"] summary * { color: #ececf1 !important; }

        /* Caja de entrada un poco más gruesa */
        [data-testid="stChatInput"] { padding: 10px 16px !important; }
        [data-testid="stChatInput"] textarea {
            min-height: 54px !important;
            padding-top: 10px !important;
        }

        /* Botón de adjuntar compacto (estilo clip), no una caja grande */
        [data-testid="stFileUploader"] { margin-bottom: 8px; }
        [data-testid="stFileUploader"] label { color: #9a9aa8 !important; font-size: .8rem; }
        [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzoneInstructions"] {
            display: none !important;
        }
        [data-testid="stFileUploader"] section {
            padding: 6px 10px !important;
            min-height: 0 !important;
            background: #2f2f2f !important;
            border: 1px solid #4d4f5c !important;
            border-radius: 12px !important;
        }
        [data-testid="stFileUploader"] section button {
            background: linear-gradient(135deg, #8ab4f8, #4a7fe0) !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 8px !important;
        }
    </style>
    """, unsafe_allow_html=True)

    def _render_fuentes(sources):
        """Renderiza las fuentes como ventana de comandos / terminal."""
        if not sources:
            return
        with st.expander(f"📚 Fuentes ({len(sources)})"):
            for i, source in enumerate(sources, 1):
                archivo = html.escape(str(source.get('archivo', 'documento')))
                pagina = source.get('metadata', {}).get('page', 'N/A')
                st.markdown(f"""
<div class="terminal-bar">
<span class="dot red"></span>
<span class="dot yellow"></span>
<span class="dot green"></span>
<span class="title">fuente {i} &mdash; {archivo} &middot; pag. {pagina}</span>
</div>
""", unsafe_allow_html=True)
                st.code(source['contenido'], language="text")

    # Leer el historial vivo desde el chat_processor
    historial_actual = []
    if st.session_state.chat_processor:
        historial_actual = st.session_state.chat_processor.historial_local

    # Avatar del asistente: usa el logo de Andina Servicios (con respaldo a emoji)
    avatar_ia = str(LOGO_PATH) if LOGO_PATH.exists() else "🤖"

    if not historial_actual:
        # Pantalla de bienvenida centrada estilo ChatGPT
        logo_uri = _logo_data_uri()
        logo_html = f'<img src="{logo_uri}" class="welcome-logo"/>' if logo_uri else ''
        if st.session_state.get("rol") == "Invitado":
            # Bienvenida dedicada para accesos por enlace de invitación
            st.markdown(f"""
<div class="welcome-screen">
{logo_html}
<div style="display:inline-block; margin-bottom:14px; padding:5px 14px;
            border:1px solid #3c4043; border-radius:999px; color:#8ab4f8;
            font-size:.74rem; font-weight:600; letter-spacing:.6px;
            background:#1e1f20;">ACCESO DE INVITADO</div>
<h1 class="welcome-title">Bienvenido al Asistente IA de Procesos</h1>
<p class="welcome-sub">Estás en una sesión temporal de invitado. Pregúntame sobre los
procesos de la empresa demo (radicar solicitudes, reasignar casos bloqueados,
cerrar casos, corregir facturas y validar pagos no aplicados).</p>
</div>
""", unsafe_allow_html=True)
        else:
            st.markdown(f"""
<div class="welcome-screen">
{logo_html}
<h1 class="welcome-title">¿En qué puedo ayudarte?</h1>
<p class="welcome-sub">Consulta los manuales de procesos con IA</p>
</div>
""", unsafe_allow_html=True)
    else:
        # Conversacion en orden cronologico (estilo ChatGPT)
        for msg in historial_actual[-30:]:
            with st.chat_message("user", avatar="🧑"):
                st.markdown(str(msg.get('mensaje_original', '')))
            with st.chat_message("assistant", avatar=avatar_ia):
                if msg.get('exitoso'):
                    st.markdown(msg.get('respuesta', ''))
                    _render_fuentes(msg.get('sources'))
                else:
                    st.error(msg.get('respuesta', 'Error'))

    # Botón compacto: Modo experto (activar/desactivar)
    col_exp, _col_exp2 = st.columns([0.4, 0.6])
    with col_exp:
        modo_experto = st.checkbox(
            "🎓 Modo experto",
            key="modo_experto_chk",
            help=("Activado: responde con conocimiento general del tema "
                  "(BPM, la plataforma BPM, el gestor de tickets...). Desactivado: responde "
                  "solo con la documentación de los manuales.")
        )

    # Adjuntar imagen (opcional) para analizar casos de BPM / el gestor de tickets / la plataforma BPM
    if "img_uploader_n" not in st.session_state:
        st.session_state.img_uploader_n = 0
    imagen = st.file_uploader(
        "📎 Adjuntar imagen del caso (opcional)",
        type=["png", "jpg", "jpeg", "webp"],
        key=f"img_chat_{st.session_state.img_uploader_n}"
    )

    # Si hay imagen adjunta, mostramos un campo + botón para enviarla (con o sin texto)
    pregunta_imagen = ""
    enviar_imagen = False
    if imagen is not None:
        col_pi, col_bi = st.columns([0.74, 0.26])
        with col_pi:
            pregunta_imagen = st.text_input(
                "Pregunta sobre la imagen",
                key="preg_img",
                label_visibility="collapsed",
                placeholder="Pregunta sobre la imagen (opcional)"
            )
        with col_bi:
            enviar_imagen = st.button("Analizar imagen", use_container_width=True, type="primary")

    # Entrada fija abajo (estilo ChatGPT)
    user_input = st.chat_input("Escribe tu pregunta...")

    # ---- Decidir qué se envía ----
    pregunta_final = None
    usar_imagen = False
    if enviar_imagen and imagen is not None:
        pregunta_final = pregunta_imagen.strip() or "Ayúdame con el caso que se ve en la imagen."
        usar_imagen = True
    elif user_input and user_input.strip():
        pregunta_final = user_input
        usar_imagen = imagen is not None

    if pregunta_final:
        logger.info(f"📨 Mensaje de {st.session_state.usuario}: {pregunta_final[:50]} (imagen={usar_imagen})")

        # Preparar la base de conocimiento (indexado) SOLO la primera vez,
        # con un mensaje claro para que se entienda la pequeña espera inicial.
        if not st.session_state.get("_indice_ok"):
            with st.spinner("📚 Preparando la base de conocimiento (solo la primera vez)..."):
                asegurar_indice()
            st.session_state._indice_ok = True

        # Mostrar la pregunta del usuario (con la imagen si aplica)
        with st.chat_message("user", avatar="🧑"):
            if usar_imagen and imagen is not None:
                st.image(imagen, width=300)
            st.markdown(pregunta_final)

        # Respuesta del asistente
        with st.chat_message("assistant", avatar=avatar_ia):
            if usar_imagen and imagen is not None:
                # ----- Caso con IMAGEN (análisis de visión) -----
                r = None
                with st.spinner("Analizando la imagen..."):
                    try:
                        from vision_chat import analizar_imagen
                        ctx_doc = ""
                        try:
                            asegurar_indice()
                            motor = st.session_state.motor_ia
                            if motor and getattr(motor, "vectorstore", None) and pregunta_final.strip():
                                ds = motor.vectorstore.similarity_search(pregunta_final, k=2)
                                ctx_doc = "\n\n".join(d.page_content for d in ds)
                        except Exception:
                            ctx_doc = ""
                        r = analizar_imagen(
                            pregunta_final, imagen.getvalue(),
                            getattr(imagen, "type", "image/png"), ctx_doc
                        )
                    except Exception as e:
                        logger.error(f"❌ Error visión: {e}", exc_info=True)
                        st.error(f"❌ Error analizando la imagen: {e}")

                if r:
                    st.markdown(r)
                    # Guardar el turno en el historial (como texto)
                    try:
                        st.session_state.chat_processor.historial_local.append({
                            "exitoso": True,
                            "mensaje_original": pregunta_final + "  [imagen adjunta]",
                            "respuesta": r, "sources": [],
                            "timestamp": datetime.now().isoformat(),
                            "usuario": st.session_state.usuario,
                            "rol": st.session_state.rol, "modo": "VISION",
                        })
                    except Exception:
                        pass
                    # 🧹 Limpiar la imagen adjunta para que no quede "seleccionada"
                    st.session_state.img_uploader_n += 1
                    st.rerun()
            else:
                # ----- Caso solo TEXTO (RAG normal) -----
                with st.spinner("Pensando..."):
                    try:
                        respuesta = st.session_state.chat_processor.procesar_mensaje(
                            mensaje=pregunta_final,
                            contexto={'rol': st.session_state.rol, 'modo_experto': modo_experto}
                        )
                    except Exception as e:
                        logger.error(f"❌ Error: {e}", exc_info=True)
                        st.error(f"❌ Error procesando: {str(e)}")
                        return

                if respuesta.get('exitoso'):
                    st.markdown(respuesta.get('respuesta', ''))
                    _render_fuentes(respuesta.get('sources'))
                else:
                    st.error(respuesta.get('respuesta', 'Error'))


def mostrar_estadisticas():
    """Mostrar estadísticas"""
    
    st.markdown("# 📊 Estadísticas")
    
    motor = st.session_state.motor_ia
    stats = motor.obtener_estado()['estadisticas']
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="stats-card">
        <h3>📊 Queries Totales</h3>
        <div class="value">{stats['queries_totales']}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="stats-card">
        <h3>✅ Exitosas</h3>
        <div class="value">{stats['queries_exitosas']}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="stats-card">
        <h3>❌ Fallidas</h3>
        <div class="value">{stats['queries_fallidas']}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        tasa_exito = (
            (stats['queries_exitosas'] / stats['queries_totales'] * 100)
            if stats['queries_totales'] > 0 else 0
        )
        st.markdown(f"""
        <div class="stats-card">
        <h3>📈 Tasa Éxito</h3>
        <div class="value">{tasa_exito:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)

def mostrar_admin_usuarios():
    """Panel de gestión de usuarios"""
    
    st.markdown("## 👥 Gestión de Usuarios")

    # 🔐 Generador de contraseñas cifradas (para usar en Secrets, más seguro)
    with st.expander("🔐 Generar contraseña cifrada (hash) para Secrets"):
        st.caption("Escribe una contraseña y copia el hash resultante en tus Secrets. "
                   "Así no la guardas en texto plano.")
        pwd_plana = st.text_input("Contraseña a cifrar", type="password", key="gen_hash_pwd")
        if st.button("🔒 Generar hash", key="btn_gen_hash"):
            if not pwd_plana:
                st.warning("Escribe una contraseña primero.")
            else:
                try:
                    import bcrypt
                    h = bcrypt.hashpw(pwd_plana.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
                    st.success("✅ Hash generado. Cópialo en tus Secrets como 'password':")
                    st.code(h, language="text")
                    st.caption("Ejemplo en Secrets:")
                    st.code(
                        f'[usuarios.nombre]\npassword = "{h}"\nrol = "Analista"',
                        language="toml"
                    )
                except Exception as e:
                    st.error(f"No se pudo generar el hash: {e}")

    usuarios = cargar_usuarios()
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### Usuarios Actuales")
        
        for usuario, datos in usuarios.items():
            col_user, col_rol, col_delete = st.columns([3, 2, 1])
            
            with col_user:
                st.text(f"👤 {usuario}")
            
            with col_rol:
                st.text(f"🏷️ {datos['rol']}")
            
            with col_delete:
                if st.button("🗑️", key=f"delete_{usuario}"):
                    del usuarios[usuario]
                    guardar_usuarios(usuarios)
                    st.success(f"✅ {usuario} eliminado")
                    st.rerun()
    
    with col2:
        st.markdown("### ➕ Nuevo Usuario")
        
        nuevo_user = st.text_input("Usuario", key="admin_new_user")
        nueva_pass = st.text_input("Contraseña", type="password", key="admin_new_pass")
        nuevo_rol = st.selectbox("Rol", ["Analista", "Administrador"], key="admin_new_rol")
        
        if st.button("➕ Crear", use_container_width=True):
            if not nuevo_user or not nueva_pass:
                st.error("❌ Completa todos los campos")
            elif nuevo_user in usuarios:
                st.error("❌ Usuario ya existe")
            else:
                usuarios[nuevo_user] = {
                    "contraseña": nueva_pass,
                    "rol": nuevo_rol
                }
                guardar_usuarios(usuarios)
                st.success(f"✅ Usuario '{nuevo_user}' creado")
                st.rerun()

def mostrar_admin_pdfs():
    """Panel de procesamiento de PDFs (dinámico: una sección por carpeta del repo)."""
    st.markdown("## 📄 Procesar Documentos")

    carpetas = detectar_carpetas_documentos()
    if not carpetas:
        st.info("ℹ️ No se detectaron carpetas con PDFs en el repositorio. "
                "Sube una carpeta con PDFs a GitHub y aparecerá aquí automáticamente.")
        return

    st.caption(
        f"Se detectaron **{len(carpetas)}** carpeta(s) con documentos. "
        "Cada carpeta nueva que subas a GitHub aparecerá aquí automáticamente "
        "(y se indexa sola al iniciar la app)."
    )

    # Botón para procesar TODAS las carpetas
    if st.button("🔄 Procesar TODAS las carpetas", type="primary", use_container_width=True):
        processor = cargar_data_processor()
        if not processor:
            st.error("❌ Error cargando procesador")
        else:
            total = 0
            with st.spinner("⏳ Procesando todas las carpetas..."):
                for c in carpetas:
                    res = processor.procesar_carpeta(c, c)
                    if res.get('exito'):
                        total += res.get('chunks_creados', 0)
            st.success(f"✅ Listo. {total} fragmentos indexados en total.")

    st.divider()

    # Una sección independiente por cada carpeta
    for carpeta in carpetas:
        st.markdown(f"### 📁 {carpeta}")

        subs = subcarpetas_con_pdfs(carpeta)
        if subs:
            for nombre_sub, n in subs:
                st.markdown(f"&nbsp;&nbsp;&nbsp;📂 **{nombre_sub}** — {n} PDF(s)", unsafe_allow_html=True)
        else:
            st.caption("Sin subcarpetas con PDFs.")

        if st.button(f"🔄 Procesar '{carpeta}'", key=f"btn_proc_{carpeta}"):
            processor = cargar_data_processor()
            if not processor:
                st.error("❌ Error cargando procesador")
            else:
                with st.spinner(f"⏳ Procesando {carpeta}..."):
                    try:
                        resultado = processor.procesar_carpeta(carpeta, carpeta)
                        if resultado['exito']:
                            st.success(f"✅ {resultado['archivos_procesados']} archivos procesados")
                            st.info(f"📊 {resultado['chunks_creados']} chunks creados")
                        else:
                            st.error(f"❌ {resultado.get('error', 'Error desconocido')}")
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")

        st.divider()

def mostrar_admin_bd():
    """Panel estado de base de datos"""
    
    st.markdown("## 💾 Estado de Base de Datos")
    
    try:
        processor = cargar_data_processor()
        if not processor:
            st.error("❌ Error cargando procesador")
            return
        
        estado = processor.obtener_estado_bd()
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("📄 Documentos", estado['documentos'])
        
        with col2:
            st.metric("💾 Tamaño (MB)", estado['tamaño_mb'])
        
        with col3:
            st.metric("🔧 Estado", estado['estado'].upper())
        
        st.divider()
        
        if st.button("🗑️ Limpiar base de datos", type="secondary"):
            if st.confirm("⚠️ ¿Estás seguro? Esto eliminará todos los documentos."):
                with st.spinner("🔄 Limpiando..."):
                    if processor.limpiar_vectorstore():
                        st.success("✅ Base de datos limpiada")
                        st.rerun()
                    else:
                        st.error("❌ Error limpiando BD")
    
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")

def mostrar_admin_accesos():
    """Panel de registros de acceso"""
    
    st.markdown("## 📋 Registro de Accesos")
    
    try:
        if Path("logs/registro_conexiones.csv").exists():
            import pandas as pd
            df = pd.read_csv("logs/registro_conexiones.csv")
            
            st.dataframe(df, use_container_width=True)
            
            col1, col2 = st.columns(2)
            
            with col1:
                logins = len(df[df['Acción'] == 'LOGIN'])
                st.metric("🔓 Logins Totales", logins)
            
            with col2:
                logouts = len(df[df['Acción'] == 'LOGOUT'])
                st.metric("🚪 Logouts Totales", logouts)
        else:
            st.info("ℹ️ No hay registros aún")
    
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")

def mostrar_admin_estadisticas_ia():
    """Panel de estadísticas IA"""
    
    st.markdown("## 🤖 Estadísticas IA")
    
    motor = st.session_state.motor_ia
    estado = motor.obtener_estado()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### Estado del Motor")
        for key, value in estado.items():
            if key != 'estadisticas':
                st.text(f"**{key}:** {value}")
    
    with col2:
        st.markdown("### Estadísticas")
        stats = estado['estadisticas']
        for key, value in stats.items():
            st.text(f"**{key}:** {value}")

# ===== MAIN =====
def mostrar_admin_video():
    """Panel: convertir un video en el contenido de un manual (PDF)."""
    st.markdown("## 🎬 Video a Manual (PDF)")
    st.caption("Sube un video o audio, la IA lo transcribe, lo resume en formato de manual "
               "y genera un PDF descargable.")

    archivo = st.file_uploader(
        "Sube el video o audio",
        type=["mp4", "mov", "mkv", "webm", "m4a", "mp3", "wav", "mpeg", "mpga"],
        key="uploader_video"
    )
    # El título del caso se toma del NOMBRE DEL ARCHIVO (editable)
    titulo_def = os.path.splitext(archivo.name)[0] if archivo else "Manual"
    titulo = st.text_input(
        "Título del caso (se toma del nombre del archivo, puedes editarlo)",
        value=titulo_def,
        key=f"titulo_manual_{archivo.name if archivo else 'none'}"
    )

    st.caption("💡 Recomendado: videos de pocos minutos. Para videos largos puede tardar más.")

    if st.button("⚙️ Generar manual", type="primary", use_container_width=True):
        if not archivo:
            st.warning("Primero sube un archivo de video o audio.")
            return
        try:
            import tempfile
            from video_a_manual import procesar_video

            sufijo = "." + archivo.name.split(".")[-1].lower()
            with tempfile.NamedTemporaryFile(suffix=sufijo, delete=False) as tmp:
                tmp.write(archivo.getbuffer())
                ruta = tmp.name

            with st.spinner("⏳ Procesando: extrayendo audio, transcribiendo y resumiendo..."):
                resultado = procesar_video(ruta, titulo)

            try:
                os.remove(ruta)
            except Exception:
                pass

            st.success("✅ Manual generado")

            # Descargar PDF
            st.download_button(
                "⬇️ Descargar manual (PDF)",
                data=resultado["pdf"],
                file_name=f"{titulo.replace(' ', '_')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

            # Vista previa del manual
            with st.expander("👀 Vista previa del manual", expanded=True):
                st.markdown(resultado["manual"])

            # Transcripción completa
            with st.expander("📝 Transcripción completa"):
                st.text_area(
                    "Texto transcrito",
                    value=resultado["transcripcion"],
                    height=350,
                    label_visibility="collapsed"
                )

        except Exception as e:
            st.error(f"❌ Error procesando el video: {e}")

def mostrar_admin_servidor():
    """Panel para cerrar/activar el servidor (modo mantenimiento)."""
    st.markdown("## 🖥️ Control del Servidor")

    activo = leer_estado_app()

    if activo:
        st.success("🟢 El servidor está **ACTIVO**. Los usuarios pueden usar la aplicación.")
        st.caption("Al cerrar el servidor, los usuarios verán '🚧 En mantenimiento' en el login y no podrán ingresar (solo el administrador).")
        if st.button("🔴 Cerrar servidor", type="primary", use_container_width=True):
            if guardar_estado_app(False):
                st.warning("🚧 Servidor **CERRADO**. Los usuarios verán el mensaje de mantenimiento.")
                st.rerun()
            else:
                st.error("❌ No se pudo actualizar el estado.")
    else:
        st.error("🔴 El servidor está **CERRADO** (en mantenimiento). Los usuarios no pueden ingresar.")
        if st.button("🟢 Activar servidor", type="primary", use_container_width=True):
            if guardar_estado_app(True):
                st.success("✅ Servidor **ACTIVADO**. Los usuarios ya pueden ingresar.")
                st.rerun()
            else:
                st.error("❌ No se pudo actualizar el estado.")

    st.divider()
    st.caption(
        "ℹ️ Este interruptor afecta la instancia en ejecución de inmediato. "
        "Tras un redespliegue, el servidor vuelve a su estado guardado en estado_app.json "
        "(si no existe, queda activo)."
    )

def mostrar_admin_enlaces():
    """Generador de enlaces de invitación (acceso temporal solo por enlace)."""
    from invite_links import (
        generar_token, validar_token, expira_legible, construir_enlace
    )

    st.markdown("## 🔗 Enlaces de acceso")
    st.caption(
        "Genera un enlace temporal para que otras personas entren a la IA sin "
        "usuario ni contraseña. El enlace cambia cada vez que lo generas, caduca "
        "en 7 días y es la única forma de acceso para invitados."
    )

    # URL pública de la app (para armar el enlace)
    url_secreto = ""
    try:
        url_secreto = st.secrets.get("app_url", "") if hay_archivo_secrets() else ""
    except Exception:
        url_secreto = ""
    base_url = st.text_input(
        "URL de la aplicación",
        value=st.session_state.get("_app_url", url_secreto),
        placeholder="https://tu-app.streamlit.app",
        help="La dirección pública de la app. Se usa para construir el enlace que compartes."
    )
    st.session_state["_app_url"] = base_url

    dias = st.slider("Duración del enlace (días)", 1, 7, 7)

    if st.button("🔗 Generar enlace de invitación", type="primary", use_container_width=True):
        if not base_url.strip():
            st.warning("Primero escribe la URL de la aplicación.")
        else:
            token = generar_token(dias)
            st.session_state["_invite_link"] = construir_enlace(base_url, token)
            st.session_state["_invite_token"] = token

    link = st.session_state.get("_invite_link")
    if link:
        token = st.session_state.get("_invite_token", "")
        _, exp = validar_token(token)
        st.success("✅ Enlace generado. Cópialo y compártelo:")
        st.code(link, language="text")
        if exp:
            st.caption(
                f"⏳ Caduca el {expira_legible(exp)}. "
                "Después de esa fecha el enlace dejará de funcionar."
            )

    st.divider()
    st.markdown("**¿Cómo funciona la seguridad?**")
    st.markdown(
        "- Solo funcionan los enlaces generados aquí (van firmados). Sin un enlace "
        "válido, nadie puede entrar como invitado.\n"
        "- El enlace **caduca** automáticamente (1 semana por defecto).\n"
        "- Los invitados entran **solo al chat**; no ven las herramientas de administración.\n"
        "- Para invalidar **todos** los enlaces de golpe (o reforzar la seguridad), "
        "define `invite_seed` en *Settings → Secrets* y cámbiala cuando quieras."
    )


def _restaurar_sesion_desde_token() -> bool:
    """Si la URL trae ?s=<token de sesión> válido, restaura la sesión del usuario
    sin pedir login otra vez (mantiene la sesión al refrescar la página)."""
    if st.session_state.get("autenticado"):
        return False
    try:
        qp = st.experimental_get_query_params()
    except Exception:
        qp = {}
    valores = qp.get("s") if qp else None
    if isinstance(valores, list):
        token = valores[0] if valores else None
    else:
        token = valores
    if not token:
        return False

    try:
        from invite_links import validar_token_sesion
    except Exception:
        return False
    data = validar_token_sesion(token)
    if not data:
        return False

    usuarios = cargar_usuarios()
    usuario = data.get("usuario")
    if not usuario or usuario not in usuarios:
        return False
    rol = usuarios[usuario].get("rol", data.get("rol", "Analista"))

    motor_ia = cargar_motor_ia()
    if not motor_ia:
        return False
    try:
        if motor_ia.obtener_estado().get('estado') != 'listo':
            return False
    except Exception:
        return False

    chat_processor = cargar_chat_processor(usuario, rol)
    if not chat_processor:
        return False
    try:
        chat_processor._cargar_memoria_usuario()
    except Exception:
        pass

    st.session_state.autenticado = True
    st.session_state.usuario = usuario
    st.session_state.rol = rol
    st.session_state.session_token = token
    st.session_state.motor_ia = motor_ia
    st.session_state.chat_processor = chat_processor
    st.session_state.historial = chat_processor.historial_local
    st.session_state.inicio_sesion = datetime.now()
    st.session_state.ultima_actividad = datetime.now()
    logger.info(f"🔄 Sesión restaurada desde token: {usuario}")
    return True


def _intentar_acceso_invitado() -> bool:
    """Si la URL trae ?invite=<token> válido, autentica como Invitado (sin login).

    Devuelve True si quedó autenticado como invitado. Esta es la ÚNICA forma de
    acceso para personas externas: sin un enlace válido no pueden entrar.
    """
    if st.session_state.get("autenticado"):
        return False
    try:
        qp = st.experimental_get_query_params()
    except Exception:
        qp = {}
    valores = qp.get("invite") if qp else None
    if isinstance(valores, list):
        token = valores[0] if valores else None
    else:
        token = valores
    if not token:
        return False

    try:
        from invite_links import validar_token
    except Exception:
        return False

    valido, _exp = validar_token(token)
    if not valido:
        st.session_state["_invite_error"] = True
        return False

    # Enlace válido -> crear sesión de invitado (solo chat)
    motor_ia = cargar_motor_ia()
    if not motor_ia:
        return False
    try:
        if motor_ia.obtener_estado().get('estado') != 'listo':
            return False
    except Exception:
        return False

    uid = "invitado-" + str(st.session_state.get("session_id", "")).replace(".", "")[-8:]
    chat_processor = cargar_chat_processor(uid, "Invitado")
    if not chat_processor:
        return False
    try:
        chat_processor._cargar_memoria_usuario()
    except Exception:
        pass

    st.session_state.autenticado = True
    st.session_state.usuario = uid
    st.session_state.rol = "Invitado"
    st.session_state.motor_ia = motor_ia
    st.session_state.chat_processor = chat_processor
    st.session_state.historial = chat_processor.historial_local
    st.session_state.inicio_sesion = datetime.now()
    st.session_state.ultima_actividad = datetime.now()
    st.session_state["_invite_error"] = False
    try:
        registrar_acceso(uid, "Invitado", "LOGIN_INVITADO")
    except Exception:
        pass
    logger.info(f"✅ Acceso de invitado por enlace: {uid}")
    return True


def main():
    """Función principal"""
    inicializar_sesion()

    # Acceso de invitado por enlace, o restauración de sesión al refrescar
    if not st.session_state.autenticado:
        if st.session_state.get("_post_logout"):
            # Acabamos de cerrar sesión: limpiar el token de la URL en ESTE
            # render (que muestra el login y no va seguido de rerun, así sí
            # persiste) y NO restaurar la sesión anterior.
            st.session_state._post_logout = False
            try:
                st.experimental_set_query_params()
            except Exception:
                pass
        else:
            if not _intentar_acceso_invitado():
                _restaurar_sesion_desde_token()
    
    if st.session_state.autenticado:
        # 🔒 Auto-logout por inactividad (15 minutos)
        ahora = datetime.now()
        ultima = st.session_state.get("ultima_actividad")
        if ultima and (ahora - ultima) > timedelta(minutes=15):
            try:
                registrar_acceso(st.session_state.usuario, st.session_state.rol, "TIMEOUT")
            except Exception:
                pass
            st.session_state.autenticado = False
            st.session_state.usuario = None
            st.session_state.rol = None
            st.session_state.motor_ia = None
            st.session_state.chat_processor = None
            st.session_state.historial = []
            st.session_state.ultima_actividad = None
            st.session_state.session_token = None
            # Quitar el token de sesión de la URL (para que el refresco pida login)
            try:
                st.experimental_set_query_params()
            except Exception:
                pass
            st.warning("⏱️ Tu sesión se cerró por inactividad (15 minutos). Inicia sesión nuevamente.")
            pantalla_login()
            return
        # Renovar el tiempo de actividad en cada interacción
        st.session_state.ultima_actividad = ahora
        # Asegurar el token de sesión en la URL (persiste al refrescar).
        # Se hace aquí, en el render normal, NO justo antes de un rerun.
        if st.session_state.rol != "Invitado" and st.session_state.get("session_token"):
            try:
                st.experimental_set_query_params(s=st.session_state.session_token)
            except Exception:
                pass
        pantalla_principal()
    else:
        pantalla_login()

if __name__ == "__main__":
    main()
