# Guía de instalación — CobrApp

Esta guía explica cómo levantar el sistema CobrApp en una máquina nueva, desde cero. 

Por canal privado (no por este repositorio) se entrega los siguientes archivos y datos, necesarios para completar la instalación:

| Recurso | Para qué se usa |
|---|---|
| `credenciales-google.json` | Service Account de Google con permisos sobre el Sheet del proyecto |
| Token del bot de Telegram | Para que n8n se conecte al bot CobrApp |
| `CobrApp - Registro de Pagos.json` | Workflow de n8n (ya configurado con Chat IDs y Sheet ID) |
| `CobrApp - Reporte Diario.json` | Workflow de n8n (ya configurado con Chat IDs y Sheet ID) |
| Link del Google Sheet | Solo para visualizar el registro de pagos |
| Invitación al grupo de Telegram | El equipo agrega al usuario una vez que el sistema está corriendo |

> Los tokens y credenciales **no se incluyen en el repositorio** por seguridad. Se envía aparte.

---

## Paso 1. Requisitos previos

Antes de empezar, confirma que tienes instalado y funcionando:

- **Docker Desktop** (Windows/macOS) o **Docker Engine** (Linux). Verifica con:
  ```bash
  docker --version
  docker compose version
  ```
- **Git**. Verifica con:
  ```bash
  git --version
  ```
- Una **cuenta de Telegram** activa (para que el equipo agregue al usuario al grupo).

> En Windows, si Docker Desktop muestra "WSL is unresponsive", reinicia el sistema operativo antes de continuar.

---

## Paso 2. Clonar el repositorio

```bash
git clone https://github.com/Jmedrano-Git/CobrApp_Pagos.git
cd CobrApp_Pagos
```

Todos los comandos que siguen se ejecutan desde la raíz del proyecto (`CobrApp_Pagos/`).

---

## Paso 3. Crear cuenta de ngrok y reservar dominio

ngrok funciona como puente HTTPS entre Telegram (que solo habla con URLs públicas) y el n8n local. Necesitas tu propia cuenta y un dominio reservado.

### 3.1 Crear cuenta

1. Entra a [https://dashboard.ngrok.com/signup](https://dashboard.ngrok.com/signup).
2. Regístrate con un correo (puedes usar Google login).

### 3.2 Obtener el token de autenticación

1. Entra a [https://dashboard.ngrok.com/get-started/your-authtoken](https://dashboard.ngrok.com/get-started/your-authtoken).
2. Copia de preferencia en un BLOCK DE NOTAS el token completo. Tiene este formato:
   ```
   2abcdef123456...XYZ
   ```

### 3.3 Reservar dominio estático

n8n necesita una URL fija porque Telegram registra el webhook una sola vez. Sin dominio reservado, la URL cambia en cada reinicio y el bot deja de funcionar.

1. Entra a [https://dashboard.ngrok.com/domains](https://dashboard.ngrok.com/domains).
2. ngrok asigna un dominio gratuito del tipo `algo-algo-algo.ngrok-free.dev` en domains.
3. Haga click en el dominio gratuito y copie EN SU BLOCK DE NOTAS el dominio completo, **sin** `https://`. Ejemplo:
   ```
   funny-cobra-fast.ngrok-free.dev
   ```

---

## Paso 4. Crear y configurar el archivo `.env`

### 4.1 Copiar la plantilla

Desde la raíz del proyecto:

```bash
cp .env.example .env
```

En Windows con PowerShell, usar:

```powershell
Copy-Item .env.example .env
```

### 4.2 Editar el `.env`

Abre el archivo `.env` con un editor de texto (VS Code, Notepad, nano, etc.) y completa los tres valores con tu token y nombre de dominio de ngrok, el password es cualquiera que desee:

```env
NGROK_AUTHTOKEN=2abcdef123456...XYZ
NGROK_DOMAIN=funny-cobra-fast.ngrok-free.dev
N8N_PASSWORD=la_contraseña_que_quieras
```

**Reglas críticas:**

- No usar comillas alrededor de los valores.
- No dejar espacios alrededor del `=`.
- `NGROK_DOMAIN` se escribe **sin** `https://`, solo el dominio.
- `N8N_PASSWORD` es la contraseña de tu instancia local de n8n (usuario `admin`). Elige cualquier contraseña.

---

## Paso 5. Colocar `credenciales-google.json`

El equipo te entregó por canal privado un archivo llamado `credenciales-google.json`. Guárdalo dentro del proyecto en esta ruta exacta:

```
CobrApp_Pagos/python-api/credenciales-google.json
```

> El archivo debe quedar al mismo nivel que `main.py` y `Dockerfile`. La API espera encontrarlo exactamente ahí.

---

## Paso 6. Levantar el sistema con Docker

Desde la raíz del proyecto:

```bash
docker compose up -d
```

El primer arranque toma 1–2 minutos porque descarga las imágenes y compila la API Python.

### 6.1 Verificar que los 3 contenedores estén corriendo

```bash
docker ps
```

Salida esperada:

| Contenedor | Puerto | Estado |
|---|---|---|
| `n8n-cobrapp` | 5678 | `Up` |
| `python-api-cobrapp` | 8000 | `Up (healthy)` |
| `ngrok-cobrapp` | 4040 | `Up` |

Si alguno aparece como `Restarting` o `Exited`, revisa los logs:

```bash
docker logs n8n-cobrapp --tail 50
docker logs python-api-cobrapp --tail 50
docker logs ngrok-cobrapp --tail 50
```

### 6.2 Verificar que las URLs locales responden

Abre cada una en el navegador y confirma:

| URL | Qué debes ver |
|---|---|
| http://localhost:8000/health | `{"status":"ok"}` o similar |
| http://localhost:8000/dashboard | Página de bienvenida del dashboard |
| http://localhost:8000/docs | Swagger UI con la lista de endpoints |
| http://localhost:5678 | Login de n8n (entrar con `admin` + tu `N8N_PASSWORD`) |
| http://localhost:4040 | Inspector de ngrok mostrando el túnel activo |
| `https://<TU_NGROK_DOMAIN>` | Login de n8n por HTTPS (esta es la URL pública) |

> Si la última URL no carga pero `localhost:5678` sí, el problema está en ngrok. Revisa `docker logs ngrok-cobrapp`.

**Si todos los puntos verifican ✅, el stack está corriendo correctamente.** Continúa al paso 7.

---

## Paso 7. Configurar n8n

Esta es la parte más detallada de la instalación. Tómate tu tiempo.

### 7.1 Entrar a n8n

1. Abre [http://localhost:5678](http://localhost:5678).
2. Registrate:
3. Si es la primera vez que entras a n8n, te pedirá crear una cuenta dueña del workspace. Llena los campos (nombre, correo, contraseña — pueden ser ficticios, son locales). **Skippea** la pantalla de marketing/encuestas si aparece.

### 7.2 Importar el primer workflow (Registro de Pagos Telegram)

1. En el menú lateral izquierdo, click en **"Workflows"**.
2. Click en el botón superior derecho **"Create workflow"** .
3. Click en los 3 puntos superior derecho, selecciona "import from file" e importa el archivo `CobrApp - Registro de Pagos.json` .
4. n8n abrirá el workflow con todos los nodos visibles. **Probablemente los nodos aparecen con un ícono de advertencia rojo o amarillo** — eso significa que faltan credenciales. Lo resolveremos en el paso 7.6.
5. Verifica que el workflow se llame `CobrApp - Registro de Pagos` arriba a la izquierda. Si no, renómbralo.

### 7.3 Importar el segundo workflow (Reporte Diario)

Repite el procedimiento del paso 7.2 con el archivo `CobrApp - Reporte Diario.json`.

Ahora deberías ver dos workflows en tu lista, ambos con nodos marcados en rojo. Es normal.

### 7.4 Crear la credencial de Telegram

1. En el menú principapl de n8n, click en **"Credentials"**.
2. Click en **"Add credential"** (botón arriba a la derecha).
3. En el buscador, escribe `Telegram` y selecciona **"Telegram API"**.
4. En el campo **Access Token**, pega el token del bot CobrApp que te entregó el equipo (formato `123456789:ABC-DEF...`).
5. Arriba a la izquierda, donde dice "Telegram account", **renombra la credencial** a exactamente:
   ```
   Telegram CobrApp
   ```
6. Click en **"Save"**.
7. Si todo está bien, verás un check verde con el mensaje "Connection tested successfully".

### 7.5 Crear la credencial de Google Sheets

1. Ingresa al WorkFlow Registro de Pagos.
2. Doble click a cualquier nodo de google sheet
3. Click en "Set Up Credential"
4. Seleccionar de Auth2 a Service Account
4. Abre el archivo `credenciales-google.json` con un editor de texto. Verás un JSON con varios campos. Necesitas dos:
   - `client_email`: copia el valor completo (formato `nombre@proyecto.iam.gserviceaccount.com`).
   - `private_key`: copia el valor completo, incluyendo las líneas `-----BEGIN PRIVATE KEY-----` y `-----END PRIVATE KEY-----`, **con los saltos de línea `\n` tal como aparecen**.
5. En n8n, pega `client_email` en el campo **Service Account Email**.
6. Pega `private_key` en el campo **Private Key**.
7. Renombra la credencial a exactamente:
   ```
   Google Sheets CobrApp
   ```
8. Click en **"Save"**.

9. Para abrir el google sheets logeate , coloca el Identificador deñ sheet en la url en medio de /d/ y /edit?.

> ⚠️ Si al guardar te aparece un error de "invalid key" o similar, abre el JSON otra vez y vuelve a copiar la `private_key` asegurándote de incluir TODOS los caracteres entre comillas, incluso los `\n`.

### 7.6 Conectar las credenciales a los nodos

Ahora vuelve a cada workflow y asigna las credenciales recién creadas a cada nodo en rojo.

**Procedimiento general para cada nodo:**

1. Abre el workflow.
2. Doble click sobre un nodo en rojo.
3. En el campo **Credential to connect with**, abre el dropdown y selecciona la credencial correspondiente(Tambien puede que se autoconecte).
4. Click en **"Execute step"** para probar (opcional, pero recomendado).
5. Cierra el nodo (botón "Back" o `Esc`).

**Workflow `CobrApp - Registro de Pagos`** — nodos que necesitan credencial:

| Nodo | Credencial a asignar |
|---|---|
| `Telegram Trigger` | Telegram CobrApp |
| `Get a file` | Telegram CobrApp |
| `Buscar duplicado` | Google Sheets CobrApp |
| `Append row in sheet` | Google Sheets CobrApp |
| `Mensaje confirmación` | Telegram CobrApp |
| `Aviso Duplicado` | Telegram CobrApp |

**Workflow `CobrApp - Reporte Diario`** — nodos que necesitan credencial:

| Nodo | Credencial a asignar |
|---|---|
| `Filas de hoy` | Google Sheets CobrApp |
| `Enviar reporte` | Telegram CobrApp |


### 7.7 Activar los workflows 

Una vez que **ningún nodo está en rojo**, activa cada workflow:

1. Abre el workflow `CobrApp - Registro de Pagos`.
2. En la esquina superior derecha hay un toggle **"Publish"**. Click para activarlo. Ponle un nombre Debe quedarse en **azul/verde** con el texto **"Published"**.
3. Repite con `CobrApp - Reporte Diario`.

> Si el toggle no cambia de estado y aparece un error tipo "Workflow cannot be activated", revisa que todos los nodos tengan credencial asignada y que el `HTTP Request` apunte a `python-api`, no a `localhost`.

---

## Paso 8. Verificar el webhook de Telegram

Al activar el workflow Registro de Pagos, n8n le dice automáticamente a Telegram *"mándame los updates a esta URL"*. Para confirmar que se registró bien:

1. Abre en el navegador esta URL, reemplazando `<TOKEN>` por el token del bot:
   ```
   https://api.telegram.org/bot<TOKEN>/getWebhookInfo
   ```
2. Deberías ver un JSON tipo:
   ```json
   {
     "ok": true,
     "result": {
       "url": "https://funny-cobra-fast.ngrok-free.dev/webhook/...",
       "pending_update_count": 0
     }
   }
   ```
3. Confirma que el campo `url` contiene **tu** dominio de ngrok (el que pusiste en `.env`).

Si el campo `url` está vacío o apunta a otro dominio, desactiva y reactiva el workflow `CobrApp - Registro de Pagos` en n8n para forzar el re-registro.

---

## Paso 9. Pedir invitación al grupo de Telegram

Entra al enlace de telegram para verificar la foto plin o yape y procesada por bot.

---

## Paso 10. Prueba end-to-end
