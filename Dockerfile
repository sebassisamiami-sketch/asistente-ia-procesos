# Dockerfile - Despliegue de Andina Servicios IA SIN marca de Streamlit
# (al alojar fuera de Streamlit Community Cloud, no aparece el badge
#  "Hosted/Built with Streamlit").

FROM python:3.11-slim

# Paquetes del sistema:
# - ffmpeg: para "Video a Manual" (transcripción de audio/video)
# - build-essential / python3-dev: para compilar algunas dependencias
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias primero (aprovecha la caché de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el resto del proyecto (incluye los manuales en PDF para indexar)
COPY . .

# El proveedor (Render/Railway) inyecta el puerto en la variable $PORT.
# Si no existe, usamos 8501 por defecto.
ENV PORT=8501
EXPOSE 8501

# Arranque de la app.
# Nota: enableCORS/enableXsrfProtection en false para máxima compatibilidad
# detrás del proxy del hosting (la seguridad real la da el login de la app).
CMD streamlit run app.py \
    --server.port=${PORT} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --browser.gatherUsageStats=false
