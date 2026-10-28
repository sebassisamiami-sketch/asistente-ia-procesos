# backend_web.py
"""
Lógica de negocio compartida por la app web (Flask), SIN depender de Streamlit.

Portado desde app.py: usuarios y roles, verificación de contraseñas (bcrypt),
registro de accesos, estado de mantenimiento del servidor y utilidades de
estadísticas. Reutiliza el resto de módulos del proyecto (ia_motor,
chat_procesos, procesar_datos, etc.) tal cual.
"""

import os
import csv
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger(__name__)

ARCHIVO_USUARIOS = "data/usuarios.json"
ESTADO_APP_PATH = Path(__file__).parent / "estado_app.json"

ROLES_VALIDOS = ["Administrador", "Analista", "Invitado"]


# ---------------------------------------------------------------------------
# Estado del servidor (interruptor de mantenimiento)
# ---------------------------------------------------------------------------
def leer_estado_app() -> bool:
    """True si el servidor está activo; False si está en mantenimiento."""
    try:
        if ESTADO_APP_PATH.exists():
            with open(ESTADO_APP_PATH, "r", encoding="utf-8") as f:
                return bool(json.load(f).get("servidor_activo", True))
    except Exception:
        pass
    return True


def guardar_estado_app(activo: bool) -> bool:
    """Guarda el estado del servidor (activo o mantenimiento)."""
    try:
        with open(ESTADO_APP_PATH, "w", encoding="utf-8") as f:
            json.dump({"servidor_activo": bool(activo)}, f, ensure_ascii=False, indent=2)
        logger.info(f"🖥️ Estado del servidor: activo={activo}")
        return True
    except Exception as e:
        logger.error(f"Error guardando estado del servidor: {e}")
        return False


# ---------------------------------------------------------------------------
# Usuarios y roles
# ---------------------------------------------------------------------------
def cargar_usuarios() -> Dict[str, Dict]:
    """Cargar usuarios combinando variables de entorno + archivo local.

    - ADMIN_USER / ADMIN_PASSWORD: crean el administrador inicial.
    - data/usuarios.json: usuarios creados desde el panel de administración.
    """
    usuarios: Dict[str, Dict] = {}

    admin_pass = os.getenv("ADMIN_PASSWORD")
    if admin_pass:
        usuarios[os.getenv("ADMIN_USER", "admin")] = {
            "contraseña": admin_pass,
            "rol": "Administrador",
        }

    if Path(ARCHIVO_USUARIOS).exists():
        try:
            with open(ARCHIVO_USUARIOS, "r", encoding="utf-8") as f:
                usuarios.update(json.load(f))
        except Exception:
            pass

    return usuarios


def guardar_usuarios(usuarios: Dict):
    """Guardar usuarios creados en la app (data/usuarios.json)."""
    Path("data").mkdir(exist_ok=True)
    with open(ARCHIVO_USUARIOS, "w", encoding="utf-8") as f:
        json.dump(usuarios, f, ensure_ascii=False, indent=2)
    logger.info("✅ Usuarios guardados")


def usuarios_editables() -> Dict[str, Dict]:
    """Solo los usuarios guardados en el archivo (no el admin de entorno)."""
    if Path(ARCHIVO_USUARIOS).exists():
        try:
            with open(ARCHIVO_USUARIOS, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def verificar_password(plano: str, almacenado: str) -> bool:
    """Verifica la contraseña. Soporta hash bcrypt y texto plano."""
    if not isinstance(almacenado, str) or plano is None:
        return False
    if almacenado.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            import bcrypt
            return bcrypt.checkpw(plano.encode("utf-8"), almacenado.encode("utf-8"))
        except Exception:
            return False
    return plano == almacenado


def hash_password(plano: str) -> str:
    """Devuelve un hash bcrypt de la contraseña."""
    import bcrypt
    return bcrypt.hashpw(plano.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def resolver_usuario(usuarios: Dict[str, Dict], escrito: str):
    """Busca el usuario sin distinguir mayúsculas/minúsculas.
    Devuelve (nombre_real, datos) o (None, None)."""
    escrito = (escrito or "").strip()
    if not escrito:
        return None, None
    data = usuarios.get(escrito)
    if data:
        return escrito, data
    for k, v in usuarios.items():
        if k.lower() == escrito.lower():
            return k, v
    return None, None


# ---------------------------------------------------------------------------
# Registro de accesos
# ---------------------------------------------------------------------------
def registrar_acceso(usuario: str, rol: str, accion: str = "LOGIN",
                     ip: str = "local", sesion: str = "N/A"):
    """Registrar acceso en CSV (logs/registro_conexiones.csv)."""
    try:
        Path("logs").mkdir(exist_ok=True)
        archivo_log = "logs/registro_conexiones.csv"
        existe = os.path.exists(archivo_log)
        with open(archivo_log, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not existe:
                writer.writerow(["Timestamp", "Usuario", "Rol", "Acción", "IP", "Sesión"])
            writer.writerow([datetime.now().isoformat(), usuario, rol, accion, ip, sesion])
    except Exception as e:
        logger.error(f"Error registrando acceso: {e}")


def leer_accesos(ultimos: int = 100) -> List[Dict]:
    """Lee los últimos registros de acceso del CSV."""
    archivo_log = "logs/registro_conexiones.csv"
    filas: List[Dict] = []
    try:
        if os.path.exists(archivo_log):
            with open(archivo_log, "r", encoding="utf-8") as f:
                filas = list(csv.DictReader(f))
    except Exception as e:
        logger.warning(f"No se pudieron leer accesos: {e}")
    return filas[-ultimos:][::-1]  # más recientes primero


# ---------------------------------------------------------------------------
# Carpetas de documentos
# ---------------------------------------------------------------------------
def detectar_carpetas_documentos() -> List[str]:
    """Carpetas en la raíz que contienen PDFs (cada una es una 'sección')."""
    carpetas = []
    raiz = Path(".")
    ignorar = {"data", "logs", ".git", "__pycache__", "templates", "static",
               ".devcontainer", ".streamlit", "venv"}
    for d in sorted(raiz.iterdir()):
        if d.is_dir() and d.name not in ignorar and not d.name.startswith("."):
            if list(d.glob("**/*.pdf")):
                carpetas.append(d.name)
    return carpetas
