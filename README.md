# CobrApp — Sistema Automatizado de Gestión de Pagos Yape/Plin

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![n8n](https://img.shields.io/badge/n8n-Workflow-EA4B71?logo=n8n&logoColor=white)](https://n8n.io/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Tesseract](https://img.shields.io/badge/Tesseract-OCR-4285F4)](https://github.com/tesseract-ocr/tesseract)
[![Status](https://img.shields.io/badge/Status-Academic-blue.svg)]()

> Sistema que automatiza la recepción, verificación y registro de pagos vía Yape y Plin recibidos por Telegram, utilizando OCR para extraer los datos de las capturas y Google Sheets como base de datos.

---

## Tabla de contenido

- [Descripción](#descripción)
- [Arquitectura](#arquitectura)
- [Stack tecnológico](#stack-tecnológico)
- [Funcionalidades](#funcionalidades)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Setup y configuración](#setup-y-configuración)
- [Cómo levantar el sistema](#cómo-levantar-el-sistema)
- [Endpoints disponibles](#endpoints-disponibles)
- [Workflows de n8n](#workflows-de-n8n)
- [Troubleshooting](#troubleshooting)
- [Limitaciones conocidas](#limitaciones-conocidas)
- [Autores](#autores)

---

## Descripción

CobrApp resuelve un problema real de los pequeños y medianos negocios peruanos que cobran mediante Yape y Plin: **el registro manual de pagos consume horas diarias y genera errores frecuentes** (pagos duplicados, omitidos o mezclados con conversaciones del grupo).

El sistema automatiza el flujo completo:

1. Un cliente envía la captura de su pago al grupo de Telegram.
2. El bot procesa la imagen con OCR y extrae los datos relevantes.
3. Verifica si es un pago duplicado mediante hash MD5 de la imagen.
4. Registra el pago en Google Sheets si es un pago nuevo.
5. Confirma al cliente con un mensaje anonimizado en el grupo.
6. Genera reportes diarios automáticos al cierre del día (23:59 hrs).

**Caso de estudio:** Academia Fitness Lima, gimnasio con más de 200 socios activos.

---

## Arquitectura

El sistema sigue una arquitectura por capas que separa claramente las responsabilidades:

```
┌─────────────────────────────────────────────────┐
│  PRESENTATION LAYER                             │
│  Telegram Bot · Web Dashboard · REST Endpoints  │
└──────────────────────┬──────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────┐
│  ORCHESTRATION LAYER                            │
│  n8n (Workflow: Registro · Workflow: Reporte)   │
└──────────────────────┬──────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────┐
│  BUSINESS LOGIC LAYER                           │
│  Python API — FastAPI                           │
│  OpenCV · Tesseract OCR · Jinja2 · Parsers      │
└──────────────────────┬──────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────┐
│  PERSISTENCE LAYER                              │
│  Google Sheets (vía Service Account)            │
└─────────────────────────────────────────────────┘
```

> Para el diagrama detallado completo, revisar el **Informe Técnico** entregado.

---

## Stack tecnológico

| Componente | Tecnología | Propósito |
|---|---|---|
| Messaging Bot | Telegram Bot API | Recepción de capturas |
| Workflow Orchestrator | n8n (self-hosted) | Coordinación de flujos low-code |
| Backend API | Python 3.13 + FastAPI | Procesamiento OCR y servicio HTTP |
| Template Engine | Jinja2 | Renderizado del dashboard web |
| Image Processing | OpenCV (cv2) | Preprocesamiento previo al OCR |
| OCR Engine | Tesseract | Extracción de texto de capturas |
| Database | Google Sheets API | Base de datos accesible |
| HTTPS Tunnel | ngrok | Webhook público para Telegram |
| Containerization | Docker Compose | Despliegue del stack completo |

---

## Funcionalidades

### Procesamiento automático de pagos

- Detección automática del tipo de pago (Yape o Plin).
- Extracción de monto, beneficiario, número de operación, fecha y hora.
- Validación con múltiples niveles de detección y heurísticas contextuales.
- Hash MD5 de cada imagen para detección de duplicados.

### Notificaciones inteligentes

- Confirmación al grupo cuando un pago se registra correctamente.
- Aviso al detectar un comprobante duplicado.
- Mensajes anonimizados para preservar la privacidad financiera del negocio.

### Reportes automáticos

- Reporte diario consolidado generado a las 23:59 hrs (zona horaria `America/Lima`).
- Envío al chat privado del propietario, no al grupo, para proteger datos sensibles.
- Desglose por tipo de pago (Yape vs Plin).

### Dashboard administrativo web

- Vista de bienvenida con navegación entre las distintas secciones.
- Tabla detallada de pagos del día con estadísticas en tiempo real.
- Vista consolidada del reporte del día.
- Diseño profesional con paleta sobria de tonos azules y grises.

### REST API para integraciones

- Endpoint `/pagos` con datos del día en formato JSON.
- Endpoint `/reporte` con reporte agregado en formato JSON.
- Documentación interactiva auto-generada en `/docs` (Swagger UI).

---

## Estructura del proyecto

```
CobrApp_Pagos/
│
├── docker-compose.yml          # Orquestación de los 3 contenedores
├── .env                        # Variables de entorno (NO incluido en el repo)
├── .env.example                # Plantilla de variables de entorno
├── .gitignore
├── .dockerignore
├── README.md                   # Este archivo
│
├── python-api/                 # Python API con FastAPI
│   ├── main.py                 # Lógica principal (OCR + endpoints)
│   ├── credenciales-google.json # Service Account de Google (NO incluido en el repo)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── templates/              # Plantillas HTML (Jinja2)
│   │   ├── home.html
│   │   ├── pagos.html
│   │   └── reporte.html
│   └── static/
│       └── dashboard.css       # Estilos del dashboard
│
├── pagos/                      # Datos persistentes (NO incluido en el repo)
└── database/                   # Datos compartidos entre contenedores (NO incluido en el repo)
```

---

## Setup y configuración

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop) instalado y corriendo.
- Cuenta gratuita de [ngrok](https://ngrok.com/) con un dominio reservado.
- Cuenta de Google Cloud con una Service Account configurada para Google Sheets.
- Bot de Telegram creado mediante [@BotFather](https://t.me/BotFather).

### 1. Clone the repository

```bash
git clone https://github.com/Jmedrano-Git/CobrApp_Pagos.git
cd CobrApp_Pagos
```

### 2. Configure environment variables

Crea un archivo `.env` en la raíz del proyecto basándote en la plantilla:

```bash
cp .env.example .env
```

Las credenciales reales para evaluación se encuentran en el **Anexo G del Informe Técnico**. Las variables requeridas son:

| Variable | Descripción |
|---|---|
| `NGROK_AUTHTOKEN` | Token de autenticación de la cuenta ngrok. |
| `N8N_PASSWORD` | Contraseña del admin de n8n (usuario por defecto: `admin`). |

### 3. Place Google credentials

Coloca el archivo `credenciales-google.json` (Service Account de Google) dentro de la carpeta `python-api/`:

```
python-api/credenciales-google.json
```

> Este archivo se entrega al docente por canal directo dada su naturaleza de credencial privada.

### 4. Configure Telegram bot in n8n

Una vez levantado el sistema, accede a `http://localhost:5678` y configura las credenciales del bot de Telegram en los workflows. 

---

## Cómo levantar el sistema

### Start all containers

Desde la raíz del proyecto:

```bash
docker-compose up -d
```

El primer arranque toma entre **1 y 2 minutos** mientras Docker descarga las imágenes y construye el contenedor de Python.

### Verify containers are running

```bash
docker ps
```

Debes ver **tres contenedores activos**:

| Container | Port | Función |
|---|---|---|
| `n8n-cobrapp` | 5678 | Workflow orchestrator |
| `python-api-cobrapp` | 8000 | Python API + OCR engine |
| `ngrok-cobrapp` | 4040 | HTTPS public tunnel |

### Quick verification

| URL | Propósito |
|---|---|
| http://localhost:8000/health | API healthcheck |
| http://localhost:8000/docs | Swagger UI documentation |
| http://localhost:8000/dashboard | Admin dashboard |
| http://localhost:5678 | n8n panel |
| http://localhost:4040 | ngrok inspector |

### End-to-end test

1. Abre el grupo de Telegram donde está agregado el bot.
2. Envía una captura de un pago Yape o Plin.
3. Espera entre 5 y 10 segundos.
4. El bot debe responder con un mensaje de confirmación anonimizado.
5. Verifica que el pago aparezca en el Google Sheet de pagos y en el dashboard web.

### Stop the system

```bash
docker-compose down
```

> **Warning:** este comando detiene los contenedores pero **conserva los datos** del volumen de n8n (workflows, credenciales). Para eliminar también los datos persistentes, se debería usar `docker-compose down -v`. **No usar este flag** salvo que se quiera empezar desde cero, ya que **borra todos los workflows configurados**.

### Rebuild after code changes

Si modificas el código de la API Python, necesitas reconstruir el contenedor:

```bash
docker-compose up -d --build python-api
```

---

## Endpoints disponibles

### OCR & Data endpoints

| Method | Endpoint | Descripción |
|---|---|---|
| `GET` | `/` | Información general de la API. |
| `GET` | `/health` | Healthcheck para Docker. |
| `POST` | `/procesar-imagen` | Recibe una imagen multipart y devuelve los datos OCR en JSON. |
| `GET` | `/pagos` | Lista los pagos del día actual en formato JSON. |
| `GET` | `/reporte` | Reporte agregado del día en formato JSON. |
| `GET` | `/docs` | Documentación interactiva Swagger UI. |

### Web dashboard endpoints

| Method | Endpoint | Descripción |
|---|---|---|
| `GET` | `/dashboard` | Página de bienvenida con navegación. |
| `GET` | `/dashboard/pagos` | Tabla de pagos del día con estadísticas. |
| `GET` | `/dashboard/reporte` | Resumen consolidado del día. |

---

## Workflows de n8n

El sistema implementa **dos workflows separados** siguiendo el principio de Single Responsibility.

### CobrApp - Registro de Pagos

Se activa cada vez que llega un mensaje al bot de Telegram:

```
Telegram Trigger
    ↓
¿Es foto? (IF filter)
    ↓
Get a file (descarga imagen)
    ↓
HTTP Request → POST /procesar-imagen
    ↓
¿Pago válido? (IF filter)
    ↓
Datos completos del pago (consolidación)
    ↓
Buscar duplicado (consulta hash en Sheets)
    ↓
If: ¿existe? ─── sí ───→ Aviso Duplicado al grupo
    │
    └── no ───→ Append row in sheet ───→ Mensaje confirmación
```

### CobrApp - Reporte Diario

Se ejecuta automáticamente todos los días a las **23:59 hrs** (zona horaria `America/Lima`):

```
Schedule Trigger (Day, 23:59, America/Lima)
    ↓
Filas de hoy (lectura del Sheet filtrada)
    ↓
Calcular Totales (Code node, JavaScript)
    ↓
Enviar reporte → Chat privado del propietario
```

> Los archivos JSON de ambos workflows se encuentran en la carpeta `workflows/` del repositorio para importación directa en n8n.

---

## Estructura del Google Sheet

El Sheet "CobrApp - Pagos Academia Fitness Lima" contiene 10 columnas:

| Columna | Descripción | Ejemplo |
|---|---|---|
| Fecha | Fecha del registro | `28/04/2026` |
| Hora | Hora de procesamiento | `17:34:22` |
| Pagador | Nombre del usuario de Telegram | `Arnold Alva` |
| Username | @username de Telegram | `@arnold_at` |
| Beneficiario | Nombre del destinatario extraído por OCR | `ANDERSON FLERLANS PUCUHUAYLA` |
| Monto | Monto del pago en soles | `3.00` |
| Tipo | Tipo de pago detectado | `Yape` o `Plin` |
| N° Operación | Número de operación extraído | `04522043` |
| Hash | MD5 de la imagen (anti-duplicados) | `a3f5e2b9...` |
| Estado | Estado del registro | `Registrado` |

---

## Troubleshooting

<details>
<summary><b>Los contenedores no inician correctamente</b></summary>

Verifica los logs de cada contenedor:

```bash
docker logs n8n-cobrapp --tail 50
docker logs python-api-cobrapp --tail 50
docker logs ngrok-cobrapp --tail 50
```

Si Docker Desktop muestra "WSL is unresponsive", reinicia el sistema operativo.
</details>

<details>
<summary><b>El bot no responde a las capturas</b></summary>

1. Verifica que ngrok esté funcionando: http://localhost:4040
2. Verifica que el webhook de Telegram apunte al dominio correcto de ngrok.
3. Verifica que el workflow `CobrApp - Registro de Pagos` esté **publicado** (toggle "Active" en n8n), no solo guardado.
</details>

<details>
<summary><b>El dashboard no carga los estilos</b></summary>

Refresca el navegador con **Ctrl+F5** (hard refresh). Si persiste, verifica que la carpeta `python-api/static/` exista y contenga `dashboard.css`.
</details>

<details>
<summary><b>El OCR devuelve "valido: false"</b></summary>

Significa que Tesseract no pudo detectar el monto. Verifica:

- Que la imagen sea clara y no esté rotada.
- Que el texto del monto sea legible.
- Revisa los logs: `docker logs python-api-cobrapp --tail 30`
</details>

<details>
<summary><b>Después de modificar main.py los cambios no se reflejan</b></summary>

El contenedor necesita reconstruirse cuando cambia el código Python:

```bash
docker-compose up -d --build python-api
```

Las modificaciones a archivos HTML/CSS dentro de `templates/` y `static/` sí se reflejan sin reconstruir, gracias al motor de plantillas Jinja2.
</details>

---

## Limitaciones conocidas

- **OCR accuracy**: Tesseract presenta una tasa de éxito aproximada del 70-80% con capturas de Yape modernas. En algunos casos puede confundir el símbolo `S/` con el dígito `1` o capturar fragmentos del banner publicitario.
- **Histórico de reportes**: el sistema entrega reportes solo del día actual. Para conocer el recaudo de un día pasado se debe filtrar manualmente el Sheet.
- **Authentication**: el sistema asume que todos los miembros del grupo de Telegram son confiables. No hay verificación cruzada de identidad.
- **Escalabilidad de Google Sheets**: para volúmenes muy altos (más de 10 millones de celdas), Sheets podría ser un cuello de botella. Es suficiente para el caso de uso actual.

> La sección **7. Limitaciones conocidas y mejoras futuras** del Informe Técnico detalla las propuestas de mejora.

---

## Autores

- **Arnold Alva Torres** — Workflows n8n, integraciones, dashboard, documentación.
- **Julio Cesar Medrano** — Python API, OCR, image processing.

---

## Documentación adicional

- **Informe Técnico** (`Informe_Tecnico_CobrApp.docx`) — Documento completo con arquitectura, decisiones técnicas, dificultades encontradas y mejoras futuras.
- **Video demostrativo** — (Por adjuntar en la entrega final.)
- **Workflows JSON** — Archivos de exportación de los workflows de n8n para reimportación directa.

