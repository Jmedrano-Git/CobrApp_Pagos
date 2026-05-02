"""
CobrApp OCR API
================
Servicio FastAPI para procesamiento OCR de capturas de pago Yape/Plin.

Endpoints:
  GET  /                  - Info de la API
  GET  /health            - Healthcheck (Docker)
  GET  /docs              - Swagger UI
  POST /procesar-imagen   - Procesa imagen y extrae datos del pago
  GET  /pagos             - Lista de pagos del día (JSON)
  GET  /reporte           - Reporte resumido del día (JSON)
  GET  /dashboard         - Dashboard admin (HTML)
  GET  /dashboard/pagos   - Tabla de pagos del día (HTML)
  GET  /dashboard/reporte - Reporte del día (HTML)
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import pytesseract
import cv2
import numpy as np
import re
import hashlib
import logging
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

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

# Montar archivos estáticos (CSS, JS, imágenes) y motor de templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


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
    r'\b51', r'\b81', r'\bS1', r'\bs1',
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
            "swagger": "/docs",
            "dashboard": "/dashboard"
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
#       LECTOR DE GOOGLE SHEETS PARA DASHBOARD
# ====================================================

SHEET_ID_DASHBOARD = "1MrKuC-eebDtugHMYMH-fPtrVY8U1BMuItK0rjgFEsf0"
CREDENTIALS_FILE_DASHBOARD = "credenciales-google.json"


def leer_pagos_del_sheet():
    """Lee todas las filas del Google Sheet y devuelve una lista de pagos."""
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly"
        ]
        creds = Credentials.from_service_account_file(
            CREDENTIALS_FILE_DASHBOARD, scopes=scopes
        )
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_ID_DASHBOARD).sheet1
        return sheet.get_all_records()
    except Exception as e:
        logger.exception(f"Error leyendo Google Sheets: {e}")
        return []


def calcular_estadisticas_del_dia():
    """
    Función helper que centraliza el cálculo de estadísticas del día.
    Retorna un dict con todos los datos pre-calculados.
    """
    pagos = leer_pagos_del_sheet()
    fecha_hoy = datetime.now().strftime('%d/%m/%Y')
    
    pagos_hoy = [p for p in pagos if p.get("Fecha", "") == fecha_hoy]
    
    total_pagos = len(pagos_hoy)
    monto_total = sum(float(p.get("Monto", 0) or 0) for p in pagos_hoy)
    yape_count = sum(1 for p in pagos_hoy if p.get("Tipo") == "Yape")
    plin_count = sum(1 for p in pagos_hoy if p.get("Tipo") == "Plin")
    monto_yape = sum(
        float(p.get("Monto", 0) or 0)
        for p in pagos_hoy if p.get("Tipo") == "Yape"
    )
    monto_plin = sum(
        float(p.get("Monto", 0) or 0)
        for p in pagos_hoy if p.get("Tipo") == "Plin"
    )
    
    return {
        "fecha_hoy": fecha_hoy,
        "hora_actualizacion": datetime.now().strftime('%H:%M:%S'),
        "pagos_hoy": pagos_hoy,
        "total_pagos": total_pagos,
        "monto_total": monto_total,
        "yape_count": yape_count,
        "plin_count": plin_count,
        "monto_yape": monto_yape,
        "monto_plin": monto_plin,
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
#              EXTRACTOR DE BENEFICIARIO
# ====================================================

def es_token_de_nombre(token: str) -> bool:
    """Valida si un token cumple las reglas de un nombre propio."""
    token_clean = re.sub(r'\*+$', '', token)
    token_clean = re.sub(r'[.,;:!?]+$', '', token_clean)
    
    if len(token_clean) < 2:
        return False
    
    if not token_clean[0].isalpha() or not token_clean[0].isupper():
        return False
    
    token_upper = re.sub(r'[^A-ZÁÉÍÓÚÑ]', '', token_clean.upper())
    if token_upper in PALABRAS_NO_NOMBRE:
        return False
    
    if token_clean.replace('.', '').isdigit():
        return False
    
    letras_count = sum(1 for c in token_clean if c.isalpha())
    if letras_count < 2:
        return False
    
    # Rechazar tokens 100% mayúscula con 4+ letras
    letras_solo = ''.join(c for c in token_clean if c.isalpha())
    if len(letras_solo) >= 4 and letras_solo.isupper():
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
        
        if len(tokens_validos) >= 1 and len(tokens_validos) >= len(tokens) / 2:
            resultado = ' '.join(t for t in tokens if es_token_de_nombre(t))
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
    
    # Estrategia 1: patrones explícitos
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
    
    # Estrategia 2: heurística contextual Yape/Plin
    lineas = [l.strip() for l in texto.split('\n') if l.strip()]
    triggers = ['yapeaste', 'operación exitosa', 'operacion exitosa', 'enviaste']
    
    for i, linea in enumerate(lineas):
        if any(t in linea.lower() for t in triggers):
            nombre = buscar_nombre_en_lineas(lineas, i + 1, max_lineas=5)
            if nombre:
                logger.debug(f"Beneficiario [E2-heurística Yape]: {nombre}")
                return nombre
            break
    
    # Estrategia 3: fallback general
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
#                ENDPOINT OCR PRINCIPAL
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


# ====================================================
#         DASHBOARD HTML — PORTAL ADMIN
#         (usa templates de Jinja2 + CSS estático)
# ====================================================

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_inicio(request: Request):
    """Página de bienvenida del Dashboard Admin con navegación."""
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/dashboard/pagos", response_class=HTMLResponse)
def dashboard_pagos(request: Request):
    """Vista HTML con la tabla de pagos del día."""
    stats = calcular_estadisticas_del_dia()
    
    # Preparar las filas para el template (en orden inverso, más reciente primero)
    pagos_para_template = []
    for p in reversed(stats["pagos_hoy"]):
        pagos_para_template.append({
            "fecha": p.get("Fecha", ""),
            "hora": p.get("Hora", ""),
            "pagador": p.get("Pagador", ""),
            "beneficiario": p.get("Beneficiario", ""),
            "monto": float(p.get("Monto", 0) or 0),
            "tipo": p.get("Tipo", ""),
            "operacion": p.get("N° Operación", "")
        })
    
    return templates.TemplateResponse("pagos.html", {
        "request": request,
        "fecha_hoy": stats["fecha_hoy"],
        "hora_actualizacion": stats["hora_actualizacion"],
        "total_pagos": stats["total_pagos"],
        "monto_total": stats["monto_total"],
        "yape_count": stats["yape_count"],
        "plin_count": stats["plin_count"],
        "pagos_hoy_reversed": pagos_para_template,
    })


@app.get("/dashboard/reporte", response_class=HTMLResponse)
def dashboard_reporte(request: Request):
    """Vista HTML con el resumen del reporte del día."""
    stats = calcular_estadisticas_del_dia()
    
    return templates.TemplateResponse("reporte.html", {
        "request": request,
        "fecha_hoy": stats["fecha_hoy"],
        "hora_actualizacion": stats["hora_actualizacion"],
        "total_pagos": stats["total_pagos"],
        "monto_total": stats["monto_total"],
        "yape_count": stats["yape_count"],
        "plin_count": stats["plin_count"],
        "monto_yape": stats["monto_yape"],
        "monto_plin": stats["monto_plin"],
    })


# ====================================================
#         ENDPOINTS REST PARA INTEGRACIONES (JSON)
# ====================================================

@app.get("/pagos")
def get_pagos():
    """
    Lista todos los pagos registrados del día actual.
    Devuelve JSON con la lista de pagos y un resumen.
    """
    stats = calcular_estadisticas_del_dia()
    
    return {
        "fecha": stats["fecha_hoy"],
        "total_pagos": stats["total_pagos"],
        "monto_total": round(stats["monto_total"], 2),
        "pagos_yape": stats["yape_count"],
        "pagos_plin": stats["plin_count"],
        "pagos": stats["pagos_hoy"]
    }


@app.get("/reporte")
def get_reporte():
    """
    Retorna el reporte resumido del día actual con el total recaudado.
    Pensado para integraciones externas (dashboards, contabilidad, etc.).
    """
    stats = calcular_estadisticas_del_dia()
    
    return {
        "fecha": stats["fecha_hoy"],
        "resumen": {
            "total_pagos": stats["total_pagos"],
            "monto_total_recaudado": round(stats["monto_total"], 2),
            "moneda": "PEN"
        },
        "desglose_por_tipo": {
            "yape": {
                "cantidad": stats["yape_count"],
                "monto": round(stats["monto_yape"], 2)
            },
            "plin": {
                "cantidad": stats["plin_count"],
                "monto": round(stats["monto_plin"], 2)
            }
        },
        "generado_en": datetime.now().isoformat()
    }