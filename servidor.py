# servidor.py
"""
Asistente IA de Procesos — versión WEB con Flask (sin Streamlit).

Se abre en local como una web normal:

    python servidor.py
    -> http://localhost:8501

Reutiliza todo el backend del proyecto (motor RAG, embeddings, visión, Ollama)
y la lógica portada en backend_web.py. El proveedor de IA se controla con la
variable LLM_PROVIDER (ollama por defecto); ver config_local.py y README.
"""

import os
import io
import logging
import secrets as _secrets
import tempfile
from datetime import datetime
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, send_file, flash, abort,
)

import config_local
import backend_web as bw
import invite_links as il

# ---------------------------------------------------------------------------
# Inicialización
# ---------------------------------------------------------------------------
for d in ["data/pdfs", "data/db", "data/sessions", "logs",
          "Manual Solicitudes", "Manual Facturacion"]:
    Path(d).mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("logs/app.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", _secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB (videos)

# Cache de procesadores de chat por (usuario, rol) — dev server de proceso único.
_chat_cache = {}


def get_chat(usuario: str, rol: str):
    """Devuelve (y cachea) el ChatProcessor del usuario."""
    clave = f"{usuario}::{rol}"
    proc = _chat_cache.get(clave)
    if proc is None:
        from chat_procesos import ChatProcessor
        proc = ChatProcessor(usuario, rol)
        proc._cargar_memoria_usuario()
        _chat_cache[clave] = proc
    return proc


# ---------------------------------------------------------------------------
# Decoradores de autenticación
# ---------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if not session.get("autenticado"):
            return redirect(url_for("login"))
        # Mantenimiento: solo el Administrador entra
        if not bw.leer_estado_app() and session.get("rol") != "Administrador":
            return render_template("mantenimiento.html"), 503
        return f(*args, **kwargs)
    return wrap


def admin_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if not session.get("autenticado"):
            return redirect(url_for("login"))
        if session.get("rol") != "Administrador":
            abort(403)
        return f(*args, **kwargs)
    return wrap


@app.context_processor
def inyectar_globales():
    return {
        "usuario": session.get("usuario"),
        "rol": session.get("rol"),
        "servidor_activo": bw.leer_estado_app(),
        "proveedor": "Ollama (local)" if config_local.USAR_OLLAMA else "OpenAI",
        "modelo": config_local.OLLAMA_MODEL if config_local.USAR_OLLAMA else "gpt-3.5-turbo",
    }


# ---------------------------------------------------------------------------
# Login / Logout / Invitados
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    # Acceso de invitado por enlace de invitación: ?invite=<token>
    token = request.args.get("invite")
    if token and not session.get("autenticado"):
        valido, _exp = il.validar_token(token)
        if valido:
            session.clear()
            session["autenticado"] = True
            session["usuario"] = "Invitado-" + _secrets.token_hex(3)
            session["rol"] = "Invitado"
            session["sid"] = _secrets.token_hex(6)
            bw.registrar_acceso(session["usuario"], "Invitado", "LOGIN_INVITADO",
                                request.remote_addr or "local", session["sid"])
            return redirect(url_for("chat"))
        flash("El enlace de invitación no es válido o ya caducó.", "error")
    if session.get("autenticado"):
        return redirect(url_for("chat"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("autenticado"):
        return redirect(url_for("chat"))

    if request.method == "POST":
        usuarios = bw.cargar_usuarios()
        escrito = request.form.get("usuario", "").strip()
        contra = request.form.get("password", "")

        nombre, datos = bw.resolver_usuario(usuarios, escrito)
        if not datos or not bw.verificar_password(contra, datos.get("contraseña", "")):
            logger.warning(f"Intento fallido: {escrito}")
            flash("Usuario o contraseña incorrectos.", "error")
            return render_template("login.html"), 401

        session.clear()
        session["autenticado"] = True
        session["usuario"] = nombre
        session["rol"] = datos["rol"]
        session["sid"] = _secrets.token_hex(6)
        session["inicio"] = datetime.now().isoformat()
        bw.registrar_acceso(nombre, datos["rol"], "LOGIN",
                            request.remote_addr or "local", session["sid"])
        logger.info(f"✅ Login: {nombre} ({datos['rol']})")
        return redirect(url_for("chat"))

    if not os.getenv("ADMIN_PASSWORD"):
        flash("No hay usuarios configurados. Define ADMIN_USER y ADMIN_PASSWORD en el archivo .env", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    if session.get("usuario"):
        bw.registrar_acceso(session.get("usuario"), session.get("rol", "?"),
                            "LOGOUT", request.remote_addr or "local",
                            session.get("sid", "N/A"))
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------
@app.route("/chat")
@login_required
def chat():
    proc = get_chat(session["usuario"], session["rol"])
    return render_template("chat.html", historial=proc.obtener_historial(100))


@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    datos = request.get_json(force=True, silent=True) or {}
    mensaje = (datos.get("mensaje") or "").strip()
    modo_experto = bool(datos.get("modo_experto"))
    if not mensaje:
        return jsonify({"exitoso": False, "respuesta": "Mensaje vacío"}), 400

    proc = get_chat(session["usuario"], session["rol"])
    r = proc.procesar_mensaje(mensaje, contexto={"modo_experto": modo_experto})
    return jsonify({
        "exitoso": r.get("exitoso", False),
        "respuesta": r.get("respuesta", ""),
        "modo": r.get("modo", ""),
        "sources": r.get("sources", []),
    })


@app.route("/api/imagen", methods=["POST"])
@login_required
def api_imagen():
    archivo = request.files.get("imagen")
    pregunta = (request.form.get("pregunta") or "").strip()
    if not archivo:
        return jsonify({"exitoso": False, "respuesta": "No se recibió la imagen"}), 400
    try:
        from vision_chat import analizar_imagen
        datos = archivo.read()
        respuesta = analizar_imagen(pregunta, datos,
                                    mime=archivo.mimetype or "image/png")
        return jsonify({"exitoso": True, "respuesta": respuesta, "modo": "VISION"})
    except Exception as e:
        logger.error(f"Error en visión: {e}")
        return jsonify({"exitoso": False,
                        "respuesta": f"No se pudo analizar la imagen: {e}"}), 500


@app.route("/chat/limpiar", methods=["POST"])
@login_required
def chat_limpiar():
    proc = get_chat(session["usuario"], session["rol"])
    proc.limpiar_historial()
    return redirect(url_for("chat"))


# ---------------------------------------------------------------------------
# Administración
# ---------------------------------------------------------------------------
@app.route("/admin")
@admin_required
def admin():
    return redirect(url_for("admin_pdfs"))


@app.route("/admin/usuarios", methods=["GET", "POST"])
@admin_required
def admin_usuarios():
    if request.method == "POST":
        accion = request.form.get("accion")
        editables = bw.usuarios_editables()
        if accion == "crear":
            nuevo = request.form.get("usuario", "").strip()
            clave = request.form.get("password", "")
            rol = request.form.get("rol", "Analista")
            if not nuevo or not clave:
                flash("Usuario y contraseña son obligatorios.", "error")
            elif nuevo in bw.cargar_usuarios():
                flash("Ese usuario ya existe.", "error")
            else:
                editables[nuevo] = {"contraseña": bw.hash_password(clave), "rol": rol}
                bw.guardar_usuarios(editables)
                flash(f"Usuario '{nuevo}' creado.", "ok")
        elif accion == "eliminar":
            quitar = request.form.get("usuario")
            if quitar in editables:
                editables.pop(quitar)
                bw.guardar_usuarios(editables)
                flash(f"Usuario '{quitar}' eliminado.", "ok")
        return redirect(url_for("admin_usuarios"))

    admin_env = os.getenv("ADMIN_USER", "admin")
    return render_template("admin_usuarios.html",
                           editables=bw.usuarios_editables(),
                           admin_env=admin_env,
                           roles=["Analista", "Administrador"])


def _carpetas_con_conteo():
    """Lista de carpetas con PDFs y cuántos PDFs tiene cada una."""
    datos = []
    for c in bw.detectar_carpetas_documentos():
        n = len(list(Path(c).glob("**/*.pdf")))
        datos.append({"nombre": c, "pdfs": n})
    return datos


def _recargar_motor():
    """Hace que el chat vea los documentos recién indexados sin reiniciar."""
    try:
        from ia_motor import obtener_motor
        obtener_motor().recargar_vectorstore()
    except Exception as e:
        logger.warning(f"No se pudo recargar el motor: {e}")


@app.route("/admin/pdfs", methods=["GET", "POST"])
@admin_required
def admin_pdfs():
    resultado = None
    if request.method == "POST":
        from procesar_datos import DataProcessor
        processor = DataProcessor()
        objetivo = request.form.get("carpeta")  # None/"__todas__" o una carpeta
        resultado = []
        carpetas = bw.detectar_carpetas_documentos()
        destino = carpetas if objetivo in (None, "__todas__") else [objetivo]
        for c in destino:
            res = processor.procesar_carpeta(c, c)
            resultado.append({"carpeta": c, **res})
        _recargar_motor()
        flash("Indexación completada.", "ok")
    return render_template("admin_pdfs.html", carpetas=_carpetas_con_conteo(), resultado=resultado)


@app.route("/admin/pdfs/subir", methods=["POST"])
@admin_required
def admin_pdfs_subir():
    from werkzeug.utils import secure_filename
    archivos = request.files.getlist("pdfs")

    # Destino: una carpeta existente elegida en el desplegable, o una nueva.
    elegida = (request.form.get("destino") or "").strip()
    nueva = (request.form.get("seccion_nueva") or "").strip()
    existentes = bw.detectar_carpetas_documentos()
    if elegida and elegida != "__nueva__" and elegida in existentes:
        seccion = elegida                 # carpeta existente -> se usa tal cual
        carpeta = elegida
    else:
        seccion = nueva or "Manuales subidos"
        carpeta = secure_filename(seccion) or "Manuales_subidos"
    destino = Path(carpeta)
    destino.mkdir(parents=True, exist_ok=True)

    guardados = 0
    for f in archivos:
        if not f or not f.filename:
            continue
        if not f.filename.lower().endswith(".pdf"):
            continue
        nombre = secure_filename(f.filename) or f"doc_{guardados}.pdf"
        f.save(str(destino / nombre))
        guardados += 1

    if guardados == 0:
        flash("No se subió ningún PDF válido.", "error")
        return redirect(url_for("admin_pdfs"))

    # Indexar de una vez la sección subida
    from procesar_datos import DataProcessor
    res = DataProcessor().procesar_carpeta(str(destino), carpeta)
    _recargar_motor()
    if res.get("exito"):
        flash(f"Se subieron {guardados} PDF(s) a «{seccion}» y se indexaron "
              f"({res.get('chunks_creados', 0)} fragmentos). Ya puedes preguntarles en el chat.", "ok")
    else:
        flash(f"Se subieron {guardados} PDF(s), pero falló la indexación: {res.get('error')}", "error")
    return redirect(url_for("admin_pdfs"))


@app.route("/admin/bd", methods=["GET", "POST"])
@admin_required
def admin_bd():
    from procesar_datos import DataProcessor
    processor = DataProcessor()
    if request.method == "POST":
        processor.limpiar_vectorstore()
        flash("Base de datos vectorial reiniciada.", "ok")
        return redirect(url_for("admin_bd"))
    estado = processor.obtener_estado_bd()
    return render_template("admin_bd.html", estado=estado)


@app.route("/admin/accesos")
@admin_required
def admin_accesos():
    return render_template("admin_accesos.html", filas=bw.leer_accesos(150))


@app.route("/admin/estadisticas-ia")
@admin_required
def admin_estadisticas_ia():
    from ia_motor import obtener_motor
    try:
        estado = obtener_motor().obtener_estado()
    except Exception as e:
        estado = {"estado": "error", "error": str(e), "estadisticas": {}}
    return render_template("admin_estadisticas.html", estado=estado)


@app.route("/admin/servidor", methods=["GET", "POST"])
@admin_required
def admin_servidor():
    if request.method == "POST":
        activar = request.form.get("activar") == "1"
        bw.guardar_estado_app(activar)
        flash("Servidor " + ("activado." if activar else "en mantenimiento."), "ok")
        return redirect(url_for("admin_servidor"))
    return render_template("admin_servidor.html", activo=bw.leer_estado_app())


@app.route("/admin/enlaces", methods=["GET", "POST"])
@admin_required
def admin_enlaces():
    enlace = None
    if request.method == "POST":
        dias = int(request.form.get("dias", 7) or 7)
        token = il.generar_token(dias=dias)
        base = request.host_url.rstrip("/")
        enlace = il.construir_enlace(base, token)
        _ok, exp = il.validar_token(token)
        enlace_exp = il.expira_legible(exp) if exp else "—"
        return render_template("admin_enlaces.html", enlace=enlace, expira=enlace_exp)
    return render_template("admin_enlaces.html", enlace=None)


@app.route("/admin/video", methods=["GET", "POST"])
@admin_required
def admin_video():
    if request.method == "POST":
        archivo = request.files.get("video")
        titulo = (request.form.get("titulo") or "Manual").strip()
        if not archivo:
            flash("Sube un archivo de video o audio.", "error")
            return redirect(url_for("admin_video"))
        try:
            suf = Path(archivo.filename or "video.mp4").suffix or ".mp4"
            with tempfile.NamedTemporaryFile(suffix=suf, delete=False) as tmp:
                archivo.save(tmp.name)
                ruta = tmp.name
            from video_a_manual import procesar_video
            res = procesar_video(ruta, titulo)
            try:
                os.remove(ruta)
            except Exception:
                pass
            return send_file(
                io.BytesIO(res["pdf"]),
                mimetype="application/pdf",
                as_attachment=True,
                download_name=f"{titulo}.pdf",
            )
        except Exception as e:
            logger.error(f"Error video a manual: {e}")
            flash(f"No se pudo generar el manual: {e}", "error")
            return redirect(url_for("admin_video"))
    return render_template("admin_video.html")


# ---------------------------------------------------------------------------
# Copiloto de reunión (reemplaza la app Streamlit aparte)
# ---------------------------------------------------------------------------
PROYECTO_CONTEXT = (
    "PROYECTO: Asistente IA de Procesos. Chatbot interno que responde dudas sobre "
    "procesos de atención de solicitudes y facturación usando los manuales (PDFs) de "
    "la empresa con RAG. Arquitectura: Streamlit/Flask + LangChain + ChromaDB; en local "
    "usa Ollama (LLM, embeddings y visión) y faster-whisper para transcribir."
)


@app.route("/copiloto")
@login_required
def copiloto():
    return render_template("copiloto.html")


@app.route("/api/copiloto", methods=["POST"])
@login_required
def api_copiloto():
    archivo = request.files.get("audio")
    modo = request.form.get("modo", "decir")
    if not archivo:
        return jsonify({"error": "No se recibió audio"}), 400
    try:
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            archivo.save(tmp.name)
            ruta = tmp.name

        from transcripcion_local import transcribir_archivo
        import openai
        pregunta = transcribir_archivo(ruta, idioma="es")
        try:
            os.remove(ruta)
        except Exception:
            pass

        if modo == "decir":
            instruccion = (
                "Eres el copiloto del expositor. Te dan una pregunta de una reunión "
                "sobre el proyecto. Redacta una respuesta BREVE y profesional para leer "
                "en voz alta (máx. 5 frases), en primera persona del equipo."
            )
        else:
            instruccion = (
                "Eres un asistente técnico. Responde la pregunta sobre el proyecto de "
                "forma clara y concisa (máx. 6 frases o lista corta)."
            )

        modelo = config_local.configurar_sdk_openai()
        if not config_local.USAR_OLLAMA:
            openai.api_key = config_local.api_key_openai()
        resp = openai.ChatCompletion.create(
            model=modelo, temperature=0.3, max_tokens=400,
            messages=[
                {"role": "system", "content": instruccion + "\n\nCONTEXTO:\n" + PROYECTO_CONTEXT},
                {"role": "user", "content": pregunta},
            ],
        )
        respuesta = resp["choices"][0]["message"]["content"].strip()
        return jsonify({"pregunta": pregunta, "respuesta": respuesta})
    except Exception as e:
        logger.error(f"Error copiloto: {e}")
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    puerto = int(os.getenv("PORT", "8501"))
    print(f"\n  Asistente IA de Procesos (web)  ->  http://localhost:{puerto}\n")
    app.run(host="127.0.0.1", port=puerto, debug=False)
