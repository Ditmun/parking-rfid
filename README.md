# 🅿️ Sistema de Estacionamiento RFID

Sistema de control de estacionamiento con tarjetas RFID usando ESP32.  
Proyecto universitario — Node.js + Express + PostgreSQL.

## Estructura del proyecto

```
parking-rfid/
├── server.js           # Servidor Express con todos los endpoints
├── public/
│   └── index.html      # Interfaz web (panel de control)
├── package.json
├── .env.example        # Variables de entorno de ejemplo
└── README.md           # Este archivo
```

## Base de datos

Una sola tabla `tarjetas`:

| Campo          | Tipo          | Descripción                           |
|----------------|---------------|---------------------------------------|
| `id_tarjeta`   | TEXT (PK)     | ID único de la tarjeta RFID           |
| `saldo`        | INTEGER       | Saldo en pesos chilenos               |
| `estado`       | TEXT          | `'adentro'` o `'afuera'`             |
| `hora_entrada` | TIMESTAMPTZ   | Hora de entrada (null si está afuera) |

## API Endpoints

### `GET /tarjeta/:id`
Obtiene info de una tarjeta. Si no existe, la crea automáticamente.

### `POST /tarjeta/:id/saldo`
Modifica el saldo. Body: `{ "monto": 5000 }` (positivo o negativo).

### `POST /tarjeta/:id/validar`
Endpoint principal que llama el ESP32 al pasar una tarjeta por el lector.

### `GET /tarjetas`
Lista todas las tarjetas registradas.

---

## Desarrollo local

### 1. Instalar PostgreSQL
Descarga e instala [PostgreSQL](https://www.postgresql.org/download/).  
Crea una base de datos llamada `parking`.

### 2. Configurar variables de entorno
```bash
cp .env.example .env
# Edita .env con tus credenciales de PostgreSQL
```

### 3. Instalar dependencias y ejecutar
```bash
npm install
npm start
```

Abre `http://localhost:3000` en tu navegador.

---

## Despliegue en Render (GRATIS)

### Paso 1: Subir el código a GitHub
```bash
git init
git add .
git commit -m "Sistema de estacionamiento RFID"
git remote add origin https://github.com/TU_USUARIO/parking-rfid.git
git push -u origin main
```

### Paso 2: Crear base de datos PostgreSQL en Render
1. Ve a [render.com](https://render.com) y crea una cuenta
2. Dashboard → **New** → **PostgreSQL**
3. Nombre: `parking-db`
4. Plan: **Free**
5. Click **Create Database**
6. Copia la **Internal Database URL** (la necesitarás en el paso 3)

### Paso 3: Crear el Web Service en Render
1. Dashboard → **New** → **Web Service**
2. Conecta tu repositorio de GitHub
3. Configuración:
   - **Name**: `parking-rfid`
   - **Runtime**: `Node`
   - **Build Command**: `npm install`
   - **Start Command**: `node server.js`
   - **Plan**: **Free**
4. En **Environment Variables**, agrega:
   - `DATABASE_URL` = (la Internal Database URL del paso 2)
5. Click **Create Web Service**

Tu app quedará disponible en: `https://parking-rfid.onrender.com`

> ⚠️ **Nota**: En el plan gratuito de Render, el servicio se "duerme" después de 15 minutos de inactividad. La primera petición tras eso tarda ~30 segundos en responder.

---

## Código ESP32 (Arduino)

### Dependencias
Necesitas estas librerías en Arduino IDE:
- `WiFi.h` (incluida con ESP32)
- `HTTPClient.h` (incluida con ESP32)
- `MFRC522` (instalar desde Library Manager)
- `ArduinoJson` (instalar desde Library Manager, versión 7.x)

### Código completo

```cpp
// ============================================================
// ESP32 + MFRC522 — Cliente del sistema de estacionamiento
// ============================================================

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <MFRC522.h>

// --- Configuración WiFi ---
const char* WIFI_SSID = "NOMBRE_DE_TU_RED";
const char* WIFI_PASS = "CONTRASEÑA_DE_TU_RED";

// --- URL del servidor ---
// Cambia esto por la URL de tu servidor en Render
const char* SERVER_URL = "https://parking-rfid.onrender.com";

// --- Pines del lector RFID (MFRC522) ---
// Ajusta según tu conexión
#define RST_PIN  22
#define SS_PIN    5

MFRC522 rfid(SS_PIN, RST_PIN);

void setup() {
  Serial.begin(115200);
  Serial.println("=== Sistema de Estacionamiento RFID ===");

  // Inicializar SPI y MFRC522
  SPI.begin();
  rfid.PCD_Init();
  Serial.println("Lector RFID inicializado");

  // Conectar a WiFi
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Conectando a WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("Conectado! IP: ");
  Serial.println(WiFi.localIP());
  Serial.println("Acerca una tarjeta al lector...");
}

void loop() {
  // Verificar si hay una tarjeta nueva
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) {
    delay(100);
    return;
  }

  // Leer el UID de la tarjeta como string hexadecimal
  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(rfid.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();

  Serial.println("-------------------------------");
  Serial.print("Tarjeta detectada: ");
  Serial.println(uid);

  // Llamar al endpoint /validar
  validarTarjeta(uid);

  // Detener la comunicación con la tarjeta
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();

  // Esperar un poco para evitar lecturas repetidas
  delay(2000);
}

// ============================================================
// Función: Validar entrada/salida
// Llama a POST /tarjeta/:id/validar
// ============================================================
void validarTarjeta(String idTarjeta) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("ERROR: Sin conexión WiFi");
    return;
  }

  HTTPClient http;
  String url = String(SERVER_URL) + "/tarjeta/" + idTarjeta + "/validar";

  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  // POST sin body (la lógica está en el servidor)
  int httpCode = http.POST("{}");

  if (httpCode > 0) {
    String response = http.getString();
    Serial.print("Respuesta (HTTP ");
    Serial.print(httpCode);
    Serial.println("):");
    Serial.println(response);

    // Parsear la respuesta JSON
    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, response);

    if (!error) {
      const char* accion = doc["accion"];
      const char* resultado = doc["resultado"];

      if (strcmp(accion, "entrada") == 0) {
        int saldo = doc["saldo"];
        Serial.println(">>> ENTRADA APROBADA");
        Serial.print("    Saldo actual: $");
        Serial.println(saldo);
        // Aquí puedes activar un LED verde, un buzzer, abrir barrera, etc.

      } else if (strcmp(accion, "salida") == 0) {
        int costo = doc["costo"];
        int saldoNuevo = doc["saldo_nuevo"];
        Serial.println(">>> SALIDA APROBADA");
        Serial.print("    Costo: $");
        Serial.println(costo);
        Serial.print("    Saldo restante: $");
        Serial.println(saldoNuevo);
        // Aquí puedes activar un LED verde, un buzzer, abrir barrera, etc.
      }
    }
  } else {
    Serial.print("ERROR HTTP: ");
    Serial.println(httpCode);
  }

  http.end();
}

// ============================================================
// Función extra: Consultar saldo (opcional, útil para debug)
// Llama a GET /tarjeta/:id
// ============================================================
void consultarSaldo(String idTarjeta) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("ERROR: Sin conexión WiFi");
    return;
  }

  HTTPClient http;
  String url = String(SERVER_URL) + "/tarjeta/" + idTarjeta;

  http.begin(url);
  int httpCode = http.GET();

  if (httpCode > 0) {
    String response = http.getString();
    Serial.println(response);
  } else {
    Serial.print("ERROR HTTP: ");
    Serial.println(httpCode);
  }

  http.end();
}
```

### Diagrama de conexión ESP32 ↔ MFRC522

```
ESP32         MFRC522
─────         ───────
3.3V    →     VCC
GND     →     GND
GPIO 5  →     SDA (SS)
GPIO 18 →     SCK
GPIO 23 →     MOSI
GPIO 19 →     MISO
GPIO 22 →     RST
```

---

## Probando con cURL

Si quieres probar los endpoints sin el ESP32:

```bash
# Consultar tarjeta (se crea si no existe)
curl https://parking-rfid.onrender.com/tarjeta/A1B2C3D4

# Agregar saldo
curl -X POST https://parking-rfid.onrender.com/tarjeta/A1B2C3D4/saldo \
  -H "Content-Type: application/json" \
  -d '{"monto": 10000}'

# Simular entrada
curl -X POST https://parking-rfid.onrender.com/tarjeta/A1B2C3D4/validar \
  -H "Content-Type: application/json" \
  -d '{}'

# Esperar unos segundos...

# Simular salida
curl -X POST https://parking-rfid.onrender.com/tarjeta/A1B2C3D4/validar \
  -H "Content-Type: application/json" \
  -d '{}'

# Listar todas las tarjetas
curl https://parking-rfid.onrender.com/tarjetas
```
