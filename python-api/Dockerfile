FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Lima \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=5

# Dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-spa \
    libgl1 \
    libglib2.0-0 \
    python3-opencv \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar deps Python
COPY requirements.txt .
RUN pip install --no-cache-dir \
    --timeout 300 \
    --retries 5 \
    -r requirements.txt

# Hacer cv2 visible para Python 3.13
# cv2 viene como archivo .so en Debian (no como carpeta), por eso symlinkamos el .so
RUN ln -sf /usr/lib/python3/dist-packages/cv2.cpython-313-x86_64-linux-gnu.so \
           /usr/local/lib/python3.13/site-packages/cv2.cpython-313-x86_64-linux-gnu.so

# Copiar código
COPY . .

# Crear carpetas runtime
RUN mkdir -p /app/pagos /app/database

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]