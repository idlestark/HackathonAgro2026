/*
 * ============================================================================
 * Proyecto: Water Drop Method - Control Total Integrado
 *           (Fotodiodo + Bomba Peristáltica + Carrusel de 30 Agregados + Lector Láser)
 * Hardware: ESP32 / Arduino Uno + Módulo Dual MOSFET + Motor 28BYJ-48 (ULN2003)
 *           + Lector Óptico Láser + Fotodiodo
 * ============================================================================
 * 
 * Permite que una única placa microcontroladora (ESP32 o Arduino Uno) realice:
 *   1. Adquisición de datos del fotodiodo para detección de sombras de gotas.
 *   2. Control temporal no bloqueante de la bomba peristáltica (pulso e intervalo).
 *   3. Posicionamiento automático de los 30 agregados en el disco giratorio
 *      mediante motor paso a paso 28BYJ-48 (driver ULN2003) y Lector Láser.
 *   4. Recepción de comandos serie desde Python (START, STOP, DROP, SET,
 *      CAROUSEL:NEXT, CAROUSEL:PREV, CAROUSEL:GOTO, CAROUSEL:HOME, CAROUSEL:STEP).
 * ============================================================================
 */

#if defined(ESP32)
  const int PIN_BOMBA = 18;        // GPIO salida MOSFET bomba peristáltica
  const int PIN_FOTODIODO = 0;     // GPIO entrada ADC fotodiodo
  const int PIN_IN1 = 19;          // ULN2003 IN1 (28BYJ-48)
  const int PIN_IN2 = 21;          // ULN2003 IN2
  const int PIN_IN3 = 22;          // ULN2003 IN3
  const int PIN_IN4 = 23;          // ULN2003 IN4
  const int PIN_LASER_SENSOR = 4;  // Entrada digital del Lector Láser de posición
#else
  const int PIN_BOMBA = 9;         // Pin digital salida MOSFET bomba peristáltica
  const int PIN_FOTODIODO = A0;    // Pin analógico entrada fotodiodo
  const int PIN_IN1 = 4;           // ULN2003 IN1 (28BYJ-48)
  const int PIN_IN2 = 5;           // ULN2003 IN2
  const int PIN_IN3 = 6;           // ULN2003 IN3
  const int PIN_IN4 = 7;           // ULN2003 IN4
  const int PIN_LASER_SENSOR = 2;  // Entrada digital del Lector Láser de posición
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

// Parámetros del carrusel de 30 agregados (28BYJ-48 + Lector Láser)
const int SECUENCIA_MEDIO_PASO[8][4] = {
  {1, 0, 0, 0},
  {1, 1, 0, 0},
  {0, 1, 0, 0},
  {0, 1, 1, 0},
  {0, 0, 1, 0},
  {0, 0, 1, 1},
  {0, 0, 0, 1},
  {1, 0, 0, 1}
};

int totalSlots = 30;
int pasosPorSlot = 137; // 4096 pasos/rev / 30 muestras ≈ 136.53 pasos (12° por muestra)
int slotActual = 1;
int indiceFase = 0;
bool usarLectorLaser = true;

void desenergizarCarrusel() {
  digitalWrite(PIN_IN1, LOW);
  digitalWrite(PIN_IN2, LOW);
  digitalWrite(PIN_IN3, LOW);
  digitalWrite(PIN_IN4, LOW);
}

void darUnPasoCarrusel(int direccion) {
  indiceFase = (indiceFase + direccion + 8) % 8;
  digitalWrite(PIN_IN1, SECUENCIA_MEDIO_PASO[indiceFase][0]);
  digitalWrite(PIN_IN2, SECUENCIA_MEDIO_PASO[indiceFase][1]);
  digitalWrite(PIN_IN3, SECUENCIA_MEDIO_PASO[indiceFase][2]);
  digitalWrite(PIN_IN4, SECUENCIA_MEDIO_PASO[indiceFase][3]);
  delayMicroseconds(1200);
}

bool leerLaserAlineado() {
  return digitalRead(PIN_LASER_SENSOR) == HIGH;
}

void moverCarruselConLaser(int pasosObjetivo, int direccion) {
  // Asegurar que la bomba esté detenida mientras gira el disco
  digitalWrite(PIN_BOMBA, LOW);
  int pasosMinimos = (pasosObjetivo * 75) / 100;
  int pasosMaximos = (pasosObjetivo * 125) / 100;
  int pasosDados = 0;

  while (pasosDados < pasosObjetivo) {
    darUnPasoCarrusel(direccion);
    pasosDados++;
    if (usarLectorLaser && pasosDados >= pasosMinimos && leerLaserAlineado()) {
      break;
    }
  }
  if (usarLectorLaser && !leerLaserAlineado()) {
    while (pasosDados < pasosMaximos && !leerLaserAlineado()) {
      darUnPasoCarrusel(direccion);
      pasosDados++;
    }
  }
  desenergizarCarrusel();
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BOMBA, OUTPUT);
  digitalWrite(PIN_BOMBA, LOW);
  pinMode(PIN_FOTODIODO, INPUT);

  pinMode(PIN_IN1, OUTPUT);
  pinMode(PIN_IN2, OUTPUT);
  pinMode(PIN_IN3, OUTPUT);
  pinMode(PIN_IN4, OUTPUT);
  pinMode(PIN_LASER_SENSOR, INPUT_PULLUP);
  desenergizarCarrusel();

  Serial.println("PUMP_PHOTODIODE_CAROUSEL_READY");
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
  else if (cmd == "NEXT" || cmd == "CAROUSEL:NEXT") {
    moverCarruselConLaser(pasosPorSlot, 1);
    slotActual = (slotActual % totalSlots) + 1;
    Serial.print("ACK:SLOT=");
    Serial.print(slotActual);
    Serial.println(" LASER=1");
  }
  else if (cmd == "PREV" || cmd == "CAROUSEL:PREV") {
    moverCarruselConLaser(pasosPorSlot, -1);
    slotActual = ((slotActual - 2 + totalSlots) % totalSlots) + 1;
    Serial.print("ACK:SLOT=");
    Serial.print(slotActual);
    Serial.println(" LASER=1");
  }
  else if (cmd == "HOME" || cmd == "CAROUSEL:HOME") {
    int dif = 1 - slotActual;
    if (dif != 0) {
      int dir = (dif > 0) ? 1 : -1;
      for (int s = 0; s < abs(dif); s++) {
        moverCarruselConLaser(pasosPorSlot, dir);
      }
    }
    slotActual = 1;
    Serial.println("ACK:SLOT=1 LASER=1 HOME=1");
  }
  else if (cmd.startsWith("CAROUSEL:GOTO ") || cmd.startsWith("GOTO ")) {
    int esp = cmd.lastIndexOf(' ');
    int destino = cmd.substring(esp + 1).toInt();
    if (destino < 1) destino = 1;
    if (destino > totalSlots) destino = totalSlots;
    int dif = destino - slotActual;
    if (dif != 0) {
      int dir = (dif > 0) ? 1 : -1;
      for (int s = 0; s < abs(dif); s++) {
        moverCarruselConLaser(pasosPorSlot, dir);
      }
    }
    slotActual = destino;
    Serial.print("ACK:SLOT=");
    Serial.print(slotActual);
    Serial.println(" LASER=1");
  }
  else if (cmd.startsWith("CAROUSEL:STEP ") || cmd.startsWith("STEP ")) {
    int esp = cmd.lastIndexOf(' ');
    int pasos = cmd.substring(esp + 1).toInt();
    int dir = (pasos >= 0) ? 1 : -1;
    for (int i = 0; i < abs(pasos); i++) {
      darUnPasoCarrusel(dir);
    }
    desenergizarCarrusel();
    Serial.print("ACK:STEPPED ");
    Serial.print(pasos);
    Serial.println(" LASER=1");
  }
  else if (cmd.startsWith("CAROUSEL:CONFIG ")) {
    int p1 = cmd.indexOf(' ');
    int p2 = cmd.indexOf(' ', p1 + 1);
    if (p2 != -1) {
      totalSlots = max(1, (int)cmd.substring(p1 + 1, p2).toInt());
      pasosPorSlot = max(1, (int)cmd.substring(p2 + 1).toInt());
    }
    Serial.print("ACK:CAROUSEL_CONFIG SLOTS=");
    Serial.print(totalSlots);
    Serial.print(" STEPS=");
    Serial.println(pasosPorSlot);
  }
  else if (cmd == "CAROUSEL:STATUS") {
    Serial.print("STATUS:SLOT=");
    Serial.print(slotActual);
    Serial.print(" LASER=");
    Serial.print(leerLaserAlineado() ? "1" : "0");
    Serial.println(" MODE=STEPPER_28BYJ48");
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
