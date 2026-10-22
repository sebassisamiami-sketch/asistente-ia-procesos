"""Utilidad para leer Streamlit Secrets solo cuando existe el archivo.

Si se accede a st.secrets sin archivo secrets.toml, Streamlit muestra un aviso
en pantalla. Con esta comprobación la app usa variables de entorno sin mostrarlo.
"""
from pathlib import Path


def hay_archivo_secrets() -> bool:
    rutas = [Path.home() / ".streamlit" / "secrets.toml", Path.cwd() / ".streamlit" / "secrets.toml"]
    return any(r.exists() for r in rutas)
