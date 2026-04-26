"""
CobrApp OCR API
================
Servicio FastAPI para procesamiento OCR de capturas de pago Yape/Plin.

NOTA: el campo 'beneficiario' es el nombre que aparece EN la captura
(destinatario del pago según Yape/Plin). El nombre del PAGADOR se
obtiene aparte desde los metadatos del mensaje de Telegram en n8n.

Endpoints:
  GET  /                  - Info de la API
  GET  /health            - Healthcheck (Docker)
  GET  /docs              - Swagger UI
  POST /procesar-imagen   - Procesa imagen y extrae datos del pago
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
import pytesseract
import cv2
import numpy as np
import re
import hashlib
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("cobrapp")

app = FastAPI(
    title="CobrApp OCR API",
    description="API para extraer datos de capturas Yape/Plin con OCR",
    version="1.5.0"
)


# Lista negra de palabras que NO pueden ser parte de un nombre
PALABRAS_NO_NOMBRE = {
    "DATOS", "TRANSACCIÓN", "TRANSACCION", "OPERACIÓN", "OPERACION",
    "CÓDIGO", "CODIGO", "SEGURIDAD", "DESTINO", "YAPE", "PLIN",
    "YAPEASTE", "ENVIASTE", "PAGO", "PAGADO", "MONTO", "FECHA",
    "HORA", "BANCO", "CUENTA", "NÚMERO", "NUMERO", "CELULAR",
    "TELÉFONO", "TELEFONO", "DNI", "RUC", "USUARIO", "BENEFICIARIO",
    "ENVIADO", "RECIBIDO", "NRO", "COMISIÓN", "COMISION", "DESDE",
    "GRATIS", "DESCARGAR", "COMPARTIR", "DESCUBRE", "DESCUENTOS",
    "EXITOSA", "EXITOSO", "MICUENTITA", "QORE",
    "SÁBADO", "DOMINGO", "LUNES", "MARTES", "MIÉRCOLES", "JUEVES",
    "VIERNES", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO",
    "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE", "ENERO",
    "FEBRERO", "MARZO", "PM", "AM"
}

MESES = {
    'ene': '01', 'feb': '02', 'mar': '03', 'abr': '04',
    'may': '05', 'jun': '06', 'jul': '07', 'ago': '08',
    'sep': '09', 'set': '09', 'oct': '10', 'nov': '11', 'dic': '12'
}

PREFIJOS_MONTO_CONFUSOS = [
    r'[Ss58$\$]\s*/\.?',
    r'\bal\b', r'\bel\b', r'\bs[\'`´]',
    r'\boz\b', r'\bq1\b',
    r'\bg/', r'\b5/', r'\b8/',
]


# ====================================================
#                ENDPOINTS BÁSICOS
# ====================================================

@app.get("/")
def root():
    return {
        "service": "CobrApp OCR API",
        "version": "1.5.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "procesar": "POST /procesar-imagen",
            "swagger": "/docs"
        }
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "service": "cobrapp-ocr-api"
    }


# ====================================================
#              PREPROCESAMIENTO
# ====================================================

def preprocesar_imagen(image_bytes: bytes) -> np.ndarray:
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("No se pudo decodificar la imagen")
    img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    thresh = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11, 2
    )
    return thresh


def calcular_hash_imagen(image_bytes: bytes) -> str:
    return hashlib.md5(image_bytes).hexdigest()


# ====================================================
#                  EXTRACTOR DE MONTO
# ====================================================

def validar_monto(valor_str: str) -> str | None:
    valor_str = valor_str.replace(',', '.')
    if '.' not in valor_str:
        valor_str += ".00"
    try:
        valor = float(valor_str)
        if 0.10 <= valor <= 50000:
            return f"{valor:.2f}"
    except ValueError:
        pass
    return None


def extraer_monto(texto: str, tipo: str) -> str | None:
    """4 niveles de detección con heurística Yape como fallback."""
    patrones_explicitos = [
        r'[Ss58$\$]\s*/\.?\s*(\d{1,5}[.,]\d{2})',
        r'(\d{1,4}[.,]\d{2})\s*(?:soles|nuevos\s+soles)',
        r'(?:Monto|Total|Pagado)[:\s]+[Ss58$]?\s*/?\.?\s*(\d{1,5}(?:[.,]\d{2})?)',
        r'PEN\s*(\d{1,5}(?:[.,]\d{2})?)',
    ]
    for patron in patrones_explicitos:
        m = re.search(patron, texto, re.IGNORECASE)
        if m:
            monto = validar_monto(m.group(1))
            if monto:
                logger.debug(f"Monto [N1-explícito]: {monto}")
                return monto

    m = re.search(r'[Ss58$\$]\s*/\.?\s*(\d{1,5})(?!\d)(?!\s*[.,]\d)', texto, re.IGNORECASE)
    if m:
        monto = validar_monto(m.group(1))
        if monto:
            logger.debug(f"Monto [N2-entero]: {monto}")
            return monto

    for prefijo in PREFIJOS_MONTO_CONFUSOS:
        patron = prefijo + r'\s*(\d{1,5}(?:[.,]\d{2})?)'
        m = re.search(patron, texto, re.IGNORECASE)
        if m:
            monto = validar_monto(m.group(1))
            if monto:
                logger.debug(f"Monto [N3-confuso]: {monto}")
                return monto

    if tipo == "Yape":
        lineas = [l.strip() for l in texto.split('\n') if l.strip()]
        triggers = ['yapeaste', 'operación exitosa', 'operacion exitosa']
        for i, linea in enumerate(lineas):
            if any(t in linea.lower() for t in triggers):
                for j in range(i + 1, min(i + 4, len(lineas))):
                    m = re.search(r'(?:^|\s)(\d{1,4}(?:[.,]\d{2})?)(?:\s|$)', lineas[j])
                    if m:
                        monto = validar_monto(m.group(1))
                        if monto:
                            logger.debug(f"Monto [N4-heurística Yape]: {monto}")
                            return monto
                break
    return None


# ====================================================
#              EXTRACTOR DE BENEFICIARIO (v2 — robusto)
# ====================================================

def es_token_de_nombre(token: str) -> bool:
    """
    Determina si un token (palabra) puede ser parte de un nombre.
    Acepta: 'Julio', 'Med*', 'García', 'Pérez', 'José'
    Rechaza: 'DATOS', '425', '8', 'Yape', '|', '()'
    """
    # Quitar asteriscos al final (censura Yape)
    token_clean = re.sub(r'\*+$', '', token)
    # Quitar puntuación al final (puntos, comas, dos puntos)
    token_clean = re.sub(r'[.,;:!?]+$', '', token_clean)
    
    if len(token_clean) < 2:
        return False
    
    # Debe empezar con letra mayúscula
    if not token_clean[0].isalpha() or not token_clean[0].isupper():
        return False
    
    # Verificar contra lista negra (mayúsculas, sin asteriscos)
    token_upper = re.sub(r'[^A-ZÁÉÍÓÚÑ]', '', token_clean.upper())
    if token_upper in PALABRAS_NO_NOMBRE:
        return False
    
    # No debe ser solo dígitos
    if token_clean.replace('.', '').isdigit():
        return False
    
    # Debe tener al menos 2 caracteres alfabéticos
    letras_count = sum(1 for c in token_clean if c.isalpha())
    if letras_count < 2:
        return False
    
    return True


def buscar_nombre_en_lineas(lineas: list[str], idx_inicio: int, max_lineas: int = 5) -> str | None:
    """
    Busca una línea con formato de nombre (1-4 palabras válidas)
    a partir de un índice dado.
    """
    for j in range(idx_inicio, min(idx_inicio + max_lineas, len(lineas))):
        linea = lineas[j].strip()
        if not linea:
            continue
        
        tokens = linea.split()
        if not (1 <= len(tokens) <= 5):
            continue
        
        tokens_validos = [t for t in tokens if es_token_de_nombre(t)]
        
        # Si AL MENOS la mitad de los tokens (y mínimo 1) son válidos → es nombre
        if len(tokens_validos) >= 1 and len(tokens_validos) >= len(tokens) / 2:
            # Reconstruir el nombre con los tokens válidos
            resultado = ' '.join(t for t in tokens if es_token_de_nombre(t))
            # Limpiar puntuación final
            resultado = re.sub(r'[.,;:!?]+$', '', resultado).strip()
            
            if len(resultado) >= 3:
                logger.debug(f"Beneficiario detectado en línea {j}: '{resultado}'")
                return resultado
    
    return None


def extraer_beneficiario(texto: str, tipo: str) -> str | None:
    """
    Estrategia robusta para detectar al beneficiario:
    
    1. Patrones explícitos ('Yapeaste a XXX', 'Enviado a XXX')
    2. Heurística Yape: buscar líneas válidas DESPUÉS del 'yapeaste'/'operación exitosa'
    3. Fallback: cualquier línea con tokens capitalizados válidos
    """
    
    # ------ Estrategia 1: patrones explícitos ------
    patrones_explicitos = [
        r'Yapeaste\s+(?:a|al)\s+([A-ZÁÉÍÓÚÑa-záéíóúñ][^\n]{2,40})',
        r'Enviad[oa]\s+a[:\s]+([A-ZÁÉÍÓÚÑa-záéíóúñ][^\n]{2,40})',
        r'(?:Para|De)[:\s]+([A-ZÁÉÍÓÚÑa-záéíóúñ][^\n]{2,40})',
        r'Beneficiario[:\s]+([A-ZÁÉÍÓÚÑa-záéíóúñ][^\n]{2,40})',
    ]
    for patron in patrones_explicitos:
        m = re.search(patron, texto, re.MULTILINE | re.IGNORECASE)
        if m:
            candidato = m.group(1).strip().split('\n')[0]
            tokens = candidato.split()
            tokens_validos = [t for t in tokens if es_token_de_nombre(t)]
            if tokens_validos:
                resultado = ' '.join(tokens_validos[:4]).strip()
                logger.debug(f"Beneficiario [E1-explícito]: {resultado}")
                return resultado
    
    # ------ Estrategia 2: heurística contextual Yape/Plin ------
    lineas = [l.strip() for l in texto.split('\n') if l.strip()]
    triggers = ['yapeaste', 'operación exitosa', 'operacion exitosa', 'enviaste']
    
    for i, linea in enumerate(lineas):
        if any(t in linea.lower() for t in triggers):
            # Buscar nombre en las siguientes 5 líneas (puede haber monto en medio)
            nombre = buscar_nombre_en_lineas(lineas, i + 1, max_lineas=5)
            if nombre:
                logger.debug(f"Beneficiario [E2-heurística Yape]: {nombre}")
                return nombre
            break
    
    # ------ Estrategia 3: fallback general ------
    nombre = buscar_nombre_en_lineas(lineas, 0, max_lineas=len(lineas))
    if nombre:
        logger.debug(f"Beneficiario [E3-fallback]: {nombre}")
        return nombre
    
    return None


# ====================================================
#               OTROS EXTRACTORES
# ====================================================

def extraer_operacion(texto: str) -> str | None:
    patrones = [
        r'(?:N[°º]?\s*de\s*operaci[oó]n|Nro\.?\s*de\s*operaci[oó]n|N[uú]mero\s*de\s*operaci[oó]n)[:\s]*(\d{6,12})',
        r'(?:Operaci[oó]n|C[oó]digo\s*de\s*operaci[oó]n)[:\s]*(\d{6,12})',
        r'(?<!\d)(\d{8,12})(?!\d)',
    ]
    for patron in patrones:
        m = re.search(patron, texto, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def extraer_fecha(texto: str) -> str:
    m = re.search(
        r'(\d{1,2})\s+(ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic)\.?\s+(\d{4})',
        texto, re.IGNORECASE
    )
    if m:
        return f"{m.group(1).zfill(2)}/{MESES.get(m.group(2).lower(), '01')}/{m.group(3)}"

    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', texto)
    if m:
        return f"{m.group(1).zfill(2)}/{m.group(2).zfill(2)}/{m.group(3)}"

    m = re.search(r'(\d{1,2})-(\d{1,2})-(\d{2,4})', texto)
    if m:
        return f"{m.group(1).zfill(2)}/{m.group(2).zfill(2)}/{m.group(3)}"

    m = re.search(r'(\d{1,2})\s+de\s+(\w+)\s+(?:de\s+)?(\d{4})', texto, re.IGNORECASE)
    if m:
        mes_palabra = m.group(2).lower()[:3]
        return f"{m.group(1).zfill(2)}/{MESES.get(mes_palabra, '01')}/{m.group(3)}"

    return datetime.now().strftime('%d/%m/%Y')


def detectar_tipo_pago(texto: str) -> str:
    t = texto.lower()
    if any(k in t for k in ["yape", "yapeo", "yapeaste"]):
        return "Yape"
    if any(k in t for k in ["plin", "pliniaste"]):
        return "Plin"
    return "Desconocido"


# ====================================================
#                ENDPOINT PRINCIPAL
# ====================================================

@app.post("/procesar-imagen")
async def procesar_imagen(file: UploadFile = File(...)):
    try:
        contenido = await file.read()
        if not contenido:
            raise HTTPException(status_code=400, detail="Imagen vacía")

        logger.info(f"Procesando: {file.filename} ({len(contenido)} bytes)")

        hash_img = calcular_hash_imagen(contenido)

        try:
            img_proc = preprocesar_imagen(contenido)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        texto = pytesseract.image_to_string(img_proc, lang='spa')
        logger.info(f"OCR raw text:\n---START---\n{texto}\n---END---")

        tipo = detectar_tipo_pago(texto)
        monto = extraer_monto(texto, tipo)
        beneficiario = extraer_beneficiario(texto, tipo)
        operacion = extraer_operacion(texto)
        fecha = extraer_fecha(texto)

        valido = monto is not None

        respuesta = {
            "valido": valido,
            "tipo": tipo,
            "monto": monto,
            "beneficiario": beneficiario or "No detectado",
            "operacion": operacion or "No detectado",
            "fecha": fecha,
            "hora": datetime.now().strftime('%H:%M:%S'),
            "hash_imagen": hash_img,
            "texto_ocr": texto.strip(),
            "procesado_en": datetime.now().isoformat()
        }

        if valido:
            logger.info(f"✓ {tipo}: S/ {monto} → {beneficiario} [op: {operacion}]")
        else:
            logger.warning(f"✗ Sin monto. tipo={tipo}, op={operacion}")

        return respuesta

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))