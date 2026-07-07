// ============================================================
// ESP32 + MFRC522 — Cliente del sistema de estacionamiento
// 
// CONEXIONES ESP32 -> MFRC522:
//   3.3V -> VCC
//   GND  -> GND
//   D5   -> SDA (SS)
//   D18  -> SCK
//   D23  -> MOSI
//   D19  -> MISO
//   D22  -> RST
//
// LIBRERIAS NECESARIAS (instalar desde Library Manager):
//   - MFRC522 (by GithubCommunity)
//   - ArduinoJson (by Benoit Blanchon, version 7.x)
// ============================================================

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <MFRC522.h>

// ===================== CONFIGURAR ESTO =====================
const char* WIFI_SSID = "NOMBRE_DE_TU_RED";     // <-- Cambia esto
const char* WIFI_PASS = "CONTRASEÑA_DE_TU_RED";  // <-- Cambia esto
const char* SERVER    = "https://parking-rfid.onrender.com";
// ===========================================================

// Pines del MFRC522
#define RST_PIN  22
#define SS_PIN    5

MFRC522 rfid(SS_PIN, RST_PIN);

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println();
  Serial.println("========================================");
  Serial.println("  SISTEMA DE ESTACIONAMIENTO RFID");
  Serial.println("========================================");

  // Iniciar lector RFID
  SPI.begin();
  rfid.PCD_Init();
  delay(100);
  Serial.print("Lector RFID: ");
  rfid.PCD_DumpVersionToSerial();

  // Conectar WiFi
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Conectando a WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("Conectado! IP: ");
  Serial.println(WiFi.localIP());
  Serial.println("----------------------------------------");
  Serial.println("Acerca una tarjeta al lector...");
  Serial.println("----------------------------------------");
}

void loop() {
  // Esperar tarjeta
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) {
    delay(100);
    return;
  }

  // Leer UID como texto hexadecimal (ej: "A1B2C3D4")
  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(rfid.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();

  Serial.println();
  Serial.println(">>> Tarjeta detectada: " + uid);

  // Llamar al servidor
  validarTarjeta(uid);

  // Soltar la tarjeta
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();

  // Pausa para no leer la misma tarjeta dos veces seguidas
  delay(3000);
}

// ============================================================
// Llama a POST /tarjeta/:id/validar
// El servidor decide si es entrada o salida
// ============================================================
void validarTarjeta(String uid) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("ERROR: Sin WiFi!");
    return;
  }

  HTTPClient http;
  String url = String(SERVER) + "/tarjeta/" + uid + "/validar";

  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  int code = http.POST("{}");

  if (code == 200) {
    String body = http.getString();

    JsonDocument doc;
    deserializeJson(doc, body);

    const char* accion = doc["accion"];

    if (strcmp(accion, "entrada") == 0) {
      // --- ENTRADA ---
      const char* resultado = doc["resultado"];
      int saldo = doc["saldo"];
      
      if (strcmp(resultado, "aprobado") == 0) {
        Serial.println("✅ ENTRADA APROBADA");
        Serial.println("   Saldo: $" + String(saldo));
        // TODO: Activar LED verde, abrir barrera, etc.
      } else {
        const char* err = doc["error"];
        Serial.println("❌ ENTRADA DENEGADA");
        Serial.println("   Motivo: " + String(err));
        Serial.println("   Saldo actual: $" + String(saldo));
        // TODO: Activar LED rojo, buzzer de error, etc.
      }

    } else {
      // --- SALIDA ---
      int costo      = doc["costo"];
      int saldoNuevo = doc["saldo_nuevo"];
      int segundos   = doc["segundos_estacionado"];
      Serial.println("✅ SALIDA APROBADA");
      Serial.println("   Tiempo: " + String(segundos) + " seg");
      Serial.println("   Costo:  $" + String(costo));
      Serial.println("   Saldo:  $" + String(saldoNuevo));
      // TODO: Activar LED verde, buzzer, servo de barrera, etc.
    }

  } else {
    Serial.println("ERROR HTTP: " + String(code));
    Serial.println(http.getString());
  }

  http.end();
}
