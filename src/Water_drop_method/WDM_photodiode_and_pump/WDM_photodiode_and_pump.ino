/*
 * ============================================================================
 * Proyecto: Water Drop Method - Control Integrado (Fotodiodo + Bomba Peristáltica)
 * Hardware: Arduino Uno / ESP32-C3 + Módulo Dual MOSFET + Fotodiodo (A0)
 * ============================================================================
 * 
 * Permite que una única placa microcontroladora realice simultáneamente:
 *   1. La adquisición de datos del fotodiodo para detección de sombras de gotas.
 *   2. El control temporal no bloqueante de la bomba peristáltica (pulso e intervalo).
 *   3. La recepción de comandos por puerto serie desde Python (START, STOP, DROP, SET).
 * ============================================================================
 */

#if defined(ESP32)
  const int PIN_BOMBA = 18;      // GPIO salida MOSFET
  const int PIN_FOTODIODO = 0;   // GPIO entrada ADC fotodiodo
#else
  const int PIN_BOMBA = 9;       // Pin digital salida MOSFET
  const int PIN_FOTODIODO = A0;  // Pin analógico entrada fotodiodo
#endif

// Parámetros de la bomba por defecto (entregarGota(14) + delay(200) -> 6 mL/min)
unsigned long duracionPulsoMs = 14;     // Pulso activo para 1 gota
unsigned long intervaloGotaMs = 200;    // Pausa entre gotas (200 ms)

bool bombaActiva = false;
bool enFaseDePulso = false;
unsigned long tiempoUltimaBomba = 0;

// Parámetros de adquisición de fotodiodo
bool transmisionFotodiodo = true;
unsigned long intervaloLecturaUs = 1000; // Muestreo a ~1 kHz (1000 microsegundos)
unsigned long tiempoUltimaLecturaUs = 0;

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BOMBA, OUTPUT);
  digitalWrite(PIN_BOMBA, LOW);
  pinMode(PIN_FOTODIODO, INPUT);

  Serial.println("PUMP_AND_PHOTODIODE_READY");
}

void procesarComando(String cmd) {
  cmd.trim();
  cmd.toUpperCase();

  if (cmd == "START") {
    bombaActiva = true;
    enFaseDePulso = true;
    digitalWrite(PIN_BOMBA, HIGH);
    tiempoUltimaBomba = millis();
    Serial.println("ACK:STARTED");
  } 
  else if (cmd == "STOP") {
    bombaActiva = false;
    enFaseDePulso = false;
    digitalWrite(PIN_BOMBA, LOW);
    Serial.println("ACK:STOPPED");
  } 
  else if (cmd == "DROP") {
    digitalWrite(PIN_BOMBA, HIGH);
    delay(duracionPulsoMs);
    digitalWrite(PIN_BOMBA, LOW);
    Serial.println("ACK:DROP_DELIVERED");
  } 
  else if (cmd.startsWith("SET ")) {
    int primerEspacio = cmd.indexOf(' ');
    int segundoEspacio = cmd.indexOf(' ', primerEspacio + 1);

    if (segundoEspacio != -1) {
      duracionPulsoMs = cmd.substring(primerEspacio + 1, segundoEspacio).toInt();
      intervaloGotaMs = cmd.substring(segundoEspacio + 1).toInt();
      Serial.print("ACK:CONFIG_UPDATED ");
      Serial.print(duracionPulsoMs);
      Serial.print(" ");
      Serial.println(intervaloGotaMs);
    }
  }
  else if (cmd == "PHOTO:ON") {
    transmisionFotodiodo = true;
  }
  else if (cmd == "PHOTO:OFF") {
    transmisionFotodiodo = false;
  }
}

void loop() {
  // 1. Escuchar comandos serie sin bloquear
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    procesarComando(cmd);
  }

  // 2. Control no bloqueante de la bomba
  if (bombaActiva) {
    unsigned long ahoraMs = millis();

    if (enFaseDePulso) {
      if (ahoraMs - tiempoUltimaBomba >= duracionPulsoMs) {
        digitalWrite(PIN_BOMBA, LOW);
        enFaseDePulso = false;
        tiempoUltimaBomba = ahoraMs;
      }
    } else {
      if (ahoraMs - tiempoUltimaBomba >= intervaloGotaMs) {
        digitalWrite(PIN_BOMBA, HIGH);
        enFaseDePulso = true;
        tiempoUltimaBomba = ahoraMs;
      }
    }
  }

  // 3. Muestreo periódico del fotodiodo
  if (transmisionFotodiodo) {
    unsigned long ahoraUs = micros();
    if (ahoraUs - tiempoUltimaLecturaUs >= intervaloLecturaUs) {
      tiempoUltimaLecturaUs = ahoraUs;
      int valorSensor = analogRead(PIN_FOTODIODO);
      Serial.println(valorSensor);
    }
  }
}
