# invite_links.py - Enlaces de invitación con token firmado
"""
Genera y valida ENLACES DE INVITACIÓN para que personas externas puedan
entrar a la IA SIN usuario/contraseña, usando únicamente un enlace que:

- Va cambiando: cada vez que se genera, el token es distinto (incluye un nonce).
- Caduca: por defecto dura 7 días (1 semana) desde que se genera.
- Es exclusivo: solo funcionan los enlaces firmados con la semilla del servidor;
  no se puede entrar "de otra manera" (sin enlace válido no hay acceso de invitado).

Diseño SIN estado (no necesita base de datos ni archivos):
el token lleva su propia fecha de caducidad y una firma HMAC. La validez se
comprueba recalculando la firma con la semilla secreta. Por eso los enlaces
siguen funcionando aunque Streamlit Cloud reinicie/redespliegue la app.

Seguridad de la semilla:
- Producción: define la semilla en Streamlit Secrets como  invite_seed = "algo-largo-y-secreto"
  (o en la variable de entorno INVITE_SEED). Así puedes invalidar TODOS los
  enlaces existentes con solo cambiar la semilla.
- Si no hay semilla configurada, se usa una por defecto (menos segura) para
  que la función no deje de operar.
"""

import base64
import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime

# Semilla por defecto (se recomienda sobreescribir con Secrets/env en producción)
# Si no se configura INVITE_SEED, se usa una semilla aleatoria por proceso:
# los enlaces siguen siendo seguros, pero dejan de valer al reiniciar la app.
_SEMILLA_DEFECTO = secrets.token_bytes(32)


def _semilla() -> bytes:
    """Obtiene la semilla secreta para firmar/validar tokens."""
    # 1) Streamlit Secrets
    try:
        import streamlit as st  # import local para no exigir streamlit en tests
        from secretos import hay_archivo_secrets
        valor = st.secrets.get("invite_seed", None) if hay_archivo_secrets() else None
        if valor:
            return str(valor).encode("utf-8")
    except Exception:
        pass
    # 2) Variable de entorno
    valor = os.getenv("INVITE_SEED")
    if valor:
        return valor.encode("utf-8")
    # 3) Por defecto
    return _SEMILLA_DEFECTO


def _firmar(payload: str) -> str:
    """Firma el payload con HMAC-SHA256 y devuelve una firma url-safe corta."""
    firma = hmac.new(_semilla(), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(firma).decode("utf-8").rstrip("=")[:32]


def generar_token(dias: int = 7) -> str:
    """Genera un token de invitación nuevo, válido durante `dias` (por defecto 7).

    Formato: "<nonce>.<exp>.<firma>"  (sin puntos dentro de cada parte).
    """
    nonce = secrets.token_urlsafe(8)
    exp = int(time.time()) + int(dias) * 86400
    payload = f"{nonce}.{exp}"
    return f"{payload}.{_firmar(payload)}"


def validar_token(token: str):
    """Valida un token de invitación.

    Devuelve una tupla (valido: bool, expira_en: int|None) donde `expira_en`
    es el timestamp UNIX de caducidad (si se pudo leer).
    """
    try:
        partes = str(token).split(".")
        if len(partes) != 3:
            return (False, None)
        nonce, exp_str, firma = partes
        payload = f"{nonce}.{exp_str}"
        # Comparación segura contra ataques de tiempo
        if not hmac.compare_digest(firma, _firmar(payload)):
            return (False, None)
        exp = int(exp_str)
        if time.time() > exp:
            return (False, exp)  # firma válida pero caducado
        return (True, exp)
    except Exception:
        return (False, None)


def expira_legible(exp: int) -> str:
    """Convierte el timestamp de caducidad a texto legible (local)."""
    try:
        return datetime.fromtimestamp(int(exp)).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return "—"


def construir_enlace(base_url: str, token: str) -> str:
    """Construye el enlace completo a partir de la URL base y el token."""
    base = (base_url or "").strip().rstrip("/")
    sep = "&" if ("?" in base) else "?"
    return f"{base}{sep}invite={token}"



# ===== Tokens de SESIÓN (para mantener la sesión al refrescar la página) =====
# Se firman con la misma semilla. Llevan usuario, rol y caducidad, así al
# recargar la página el usuario sigue dentro sin tener que volver a iniciar sesión.

def generar_token_sesion(usuario: str, rol: str, horas: int = 8) -> str:
    """Genera un token de sesión firmado para el usuario (válido `horas`)."""
    exp = int(time.time()) + int(horas) * 3600
    payload_raw = f"{usuario}|{rol}|{exp}"
    payload_b64 = base64.urlsafe_b64encode(
        payload_raw.encode("utf-8")
    ).decode("utf-8").rstrip("=")
    return f"{payload_b64}.{_firmar(payload_b64)}"


def validar_token_sesion(token: str):
    """Valida un token de sesión. Devuelve dict {usuario, rol, exp} o None."""
    try:
        partes = str(token).split(".")
        if len(partes) != 2:
            return None
        payload_b64, firma = partes
        if not hmac.compare_digest(firma, _firmar(payload_b64)):
            return None
        pad = "=" * (-len(payload_b64) % 4)
        raw = base64.urlsafe_b64decode(payload_b64 + pad).decode("utf-8")
        usuario, rol, exp = raw.rsplit("|", 2)
        if time.time() > int(exp):
            return None
        return {"usuario": usuario, "rol": rol, "exp": int(exp)}
    except Exception:
        return None
