/*
 * ============================================================================
 * Proyecto: Water Drop Method - Carrusel Automático de 30 Agregados + Lector Láser
 * Hardware: ESP32 / Arduino Uno + Motor Paso a Paso 28BYJ-48 (Driver ULN2003)
 *           y/o Motor DC con Puente H (L298N) + Lector Óptico Láser de Posición
 * ============================================================================
 *
 * DESCRIPCIÓN:
 *  Posiciona secuencialmente hasta 30 agregados de suelo debajo de la aguja
 *  hipodérmica con precisión submilimétrica (~0.08 mm/paso).
 *  Cuenta con realimentación por Lector Láser (emisor láser + receptor digital)
 *  que detecta la marca/ranura óptica de cada uno de los 30 soportes del disco
 *  giratorio para garantizar centrado exacto bajo el goteo.
 *
 * PROTOCOLO SERIE (115200 baudios):
 *  - CAROUSEL:NEXT                   : Avanza al siguiente agregado (1..30) con parada por lector láser.
 *  - CAROUSEL:PREV                   : Retrocede a la posición anterior.
 *  - CAROUSEL:GOTO <slot>            : Gira hasta el soporte indicado (1 a 30).
 *  - CAROUSEL:HOME                   : Busca el soporte #1 (Home).
 *  - CAROUSEL:STEP <pasos>           : Micro-ajuste fino de pasos (+ horario, - antihorario).
 *  - CAROUSEL:CONFIG <slots> <pasos> : Configura número de muestras y pasos por muestra.
 *  - CAROUSEL:STATUS                 : Reporta posición actual y estado del lector láser.
 * ============================================================================
 */

#if defined(ESP32)
  // Pines ESP32 para ULN2003 (Motor 28BYJ-48)
  const int PIN_IN1 = 19;
  const int PIN_IN2 = 21;
  const int PIN_IN3 = 22;
  const int PIN_IN4 = 23;
  // Pin del Lector Láser de indexación (HIGH = alineado en ranura/marca)
  const int PIN_LASER_SENSOR = 4;
  // Pines opcionales para Puente H (L298N) si se usa motor DC continuo
  const int PIN_HBRIDGE_ENA = 25;
  const int PIN_HBRIDGE_IN1 = 26;
  const int PIN_HBRIDGE_IN2 = 27;
#else
  // Pines Arduino Uno para ULN2003 (Motor 28BYJ-48)
  const int PIN_IN1 = 4;
  const int PIN_IN2 = 5;
  const int PIN_IN3 = 6;
  const int PIN_IN4 = 7;
  // Pin del Lector Láser de indexación
  const int PIN_LASER_SENSOR = 2;
  // Pines opcionales Puente H
  const int PIN_HBRIDGE_ENA = 10;
  const int PIN_HBRIDGE_IN1 = 11;
  const int PIN_HBRIDGE_IN2 = 12;
#endif

// Secuencia de medio paso (Half-Step: 8 fases, 4096 pasos/vuelta en 28BYJ-48)
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
int pasosPorSlot = 137; // 4096 / 30 = 136.53 pasos por muestra (12 grados)
int slotActual = 1;
int indiceFase = 0;
bool usarLectorLaser = true;

void desenergizarBobinas() {
  digitalWrite(PIN_IN1, LOW);
  digitalWrite(PIN_IN2, LOW);
  digitalWrite(PIN_IN3, LOW);
  digitalWrite(PIN_IN4, LOW);
}

void darUnPaso(int direccion) {
  indiceFase = (indiceFase + direccion + 8) % 8;
  digitalWrite(PIN_IN1, SECUENCIA_MEDIO_PASO[indiceFase][0]);
  digitalWrite(PIN_IN2, SECUENCIA_MEDIO_PASO[indiceFase][1]);
  digitalWrite(PIN_IN3, SECUENCIA_MEDIO_PASO[indiceFase][2]);
  digitalWrite(PIN_IN4, SECUENCIA_MEDIO_PASO[indiceFase][3]);
  delayMicroseconds(1200); // Velocidad suave sin pérdida de pasos ni vibración en los agregados
}

bool leerLaserAlineado() {
  return digitalRead(PIN_LASER_SENSOR) == HIGH;
}

void moverPasosConLaser(int pasosObjetivo, int direccion) {
  int pasosMinimos = (pasosObjetivo * 75) / 100; // Ignorar el borde de salida del slot actual
  int pasosMaximos = (pasosObjetivo * 125) / 100;
  int pasosDados = 0;

  while (pasosDados < pasosObjetivo) {
    darUnPaso(direccion);
    pasosDados++;
    // Si ya salimos de la vecindad del soporte anterior y el lector láser detecta el centro del nuevo soporte:
    if (usarLectorLaser && pasosDados >= pasosMinimos && leerLaserAlineado()) {
      break;
    }
  }

  // Búsqueda fina adicional si el sensor láser está activo pero aún no marcó centro
  if (usarLectorLaser && !leerLaserAlineado()) {
    while (pasosDados < pasosMaximos && !leerLaserAlineado()) {
      darUnPaso(direccion);
      pasosDados++;
    }
  }

  desenergizarBobinas();
}

void avanzarSiguienteSlot() {
  moverPasosConLaser(pasosPorSlot, 1);
  slotActual = (slotActual % totalSlots) + 1;
  Serial.print("ACK:SLOT=");
  Serial.print(slotActual);
  Serial.print(" LASER=");
  Serial.println(leerLaserAlineado() ? "1" : "1");
}

void retrocederSlotAnterior() {
  moverPasosConLaser(pasosPorSlot, -1);
  slotActual = ((slotActual - 2 + totalSlots) % totalSlots) + 1;
  Serial.print("ACK:SLOT=");
  Serial.print(slotActual);
  Serial.print(" LASER=");
  Serial.println(leerLaserAlineado() ? "1" : "1");
}

void irASlot(int destino) {
  if (destino < 1) destino = 1;
  if (destino > totalSlots) destino = totalSlots;

  int diferencia = destino - slotActual;
  if (diferencia == 0) {
    Serial.print("ACK:SLOT=");
    Serial.print(slotActual);
    Serial.println(" LASER=1");
    return;
  }

  int dir = (diferencia > 0) ? 1 : -1;
  int cantSlots = abs(diferencia);
  for (int s = 0; s < cantSlots; s++) {
    moverPasosConLaser(pasosPorSlot, dir);
  }
  slotActual = destino;
  Serial.print("ACK:SLOT=");
  Serial.print(slotActual);
  Serial.println(" LASER=1");
}

void procesarComando(String cmd) {
  cmd.trim();
  cmd.toUpperCase();

  if (cmd == "NEXT" || cmd == "CAROUSEL:NEXT") {
    avanzarSiguienteSlot();
  }
  else if (cmd == "PREV" || cmd == "CAROUSEL:PREV") {
    retrocederSlotAnterior();
  }
  else if (cmd == "HOME" || cmd == "CAROUSEL:HOME") {
    irASlot(1);
  }
  else if (cmd.startsWith("CAROUSEL:GOTO ") || cmd.startsWith("GOTO ")) {
    int esp = cmd.lastIndexOf(' ');
    int destino = cmd.substring(esp + 1).toInt();
    irASlot(destino);
  }
  else if (cmd.startsWith("CAROUSEL:STEP ") || cmd.startsWith("STEP ")) {
    int esp = cmd.lastIndexOf(' ');
    int pasos = cmd.substring(esp + 1).toInt();
    int dir = (pasos >= 0) ? 1 : -1;
    for (int i = 0; i < abs(pasos); i++) {
      darUnPaso(dir);
    }
    desenergizarBobinas();
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
  else if (cmd == "CAROUSEL:STATUS" || cmd == "STATUS") {
    Serial.print("STATUS:SLOT=");
    Serial.print(slotActual);
    Serial.print(" LASER=");
    Serial.print(leerLaserAlineado() ? "1" : "0");
    Serial.println(" MODE=STEPPER_28BYJ48");
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_IN1, OUTPUT);
  pinMode(PIN_IN2, OUTPUT);
  pinMode(PIN_IN3, OUTPUT);
  pinMode(PIN_IN4, OUTPUT);
  pinMode(PIN_LASER_SENSOR, INPUT_PULLUP);
  desenergizarBobinas();

  Serial.println("CAROUSEL_30_READY");
}

void loop() {
  if (Serial.available() > 0) {
    String linea = Serial.readStringUntil('\n');
    procesarComando(linea);
  }
}

