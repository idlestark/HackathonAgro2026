/*
 * ============================================================================
 * Proyecto: Water Drop Method - Control de Bomba Peristáltica
 * Autor: Pair Programming Antigravity & Usuario
 * Hardware: Arduino Uno (Pin 9) o ESP32-C3 (GPIO 18) + Módulo Dual MOSFET + Bomba 12V
 * ============================================================================
 * 
 * PROTOCOLO SERIE (115200 baudios):
 * ----------------------------------------------------------------------------
 *  - START                  : Inicia el goteo continuo no bloqueante.
 *  - STOP                   : Detiene la bomba de inmediato.
 *  - DROP                   : Entrega una única gota calibrada (para prueba o cebado).
 *  - SET <pulso> <intervalo>: Configura tiempos en ms (ej: SET 14 186).
 *  - STATUS                 : Devuelve el estado actual de la bomba y configuración.
 * 
 * RESPUESTAS:
 *  - ACK:STARTED
 *  - ACK:STOPPED
 *  - ACK:DROP_DELIVERED
 *  - ACK:CONFIG_UPDATED <pulso> <intervalo>
 *  - STATUS: RUNNING=<0/1> PULSE=<ms> INTERVAL=<ms>
 * ============================================================================
 */

#if defined(ESP32)
  const int PIN_BOMBA = 5;  // GPIO para ESP32-C3
#else
  const int PIN_BOMBA = 9;   // Pin digital PWM para Arduino Uno
#endif

// Parámetros de temporización por defecto (entregarGota(14) + delay(200) -> 6 mL/min)
unsigned long duracionPulsoMs = 14;     // Tiempo en HIGH (duración de la gota)
unsigned long intervaloGotaMs = 200;    // Tiempo en LOW (reposo entre gotas)

bool bombaActiva = false;
bool enFaseDePulso = false;
unsigned long tiempoUltimaTransicion = 0;

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BOMBA, OUTPUT);
  digitalWrite(PIN_BOMBA, LOW);

  // Señal de inicio lista
  Serial.println("PUMP_READY");
}

void procesarComando(String cmd) {
  cmd.trim();
  cmd.toUpperCase();

  if (cmd == "START") {
    bombaActiva = true;
    enFaseDePulso = true;
    digitalWrite(PIN_BOMBA, HIGH);
    tiempoUltimaTransicion = millis();
    Serial.println("ACK:STARTED");
  } 
  else if (cmd == "STOP") {
    bombaActiva = false;
    enFaseDePulso = false;
    digitalWrite(PIN_BOMBA, LOW);
    Serial.println("ACK:STOPPED");
  } 
  else if (cmd == "DROP") {
    // Entrega una gota individual
    digitalWrite(PIN_BOMBA, HIGH);
    delay(duracionPulsoMs);
    digitalWrite(PIN_BOMBA, LOW);
    Serial.println("ACK:DROP_DELIVERED");
  } 
  else if (cmd.startsWith("SET ")) {
    // Formato: SET <pulso_ms> <intervalo_ms>
    int primerEspacio = cmd.indexOf(' ');
    int segundoEspacio = cmd.indexOf(' ', primerEspacio + 1);

    if (segundoEspacio != -1) {
      unsigned long nuevoPulso = cmd.substring(primerEspacio + 1, segundoEspacio).toInt();
      unsigned long nuevoIntervalo = cmd.substring(segundoEspacio + 1).toInt();

      if (nuevoPulso > 0 && nuevoIntervalo > 0) {
        duracionPulsoMs = nuevoPulso;
        intervaloGotaMs = nuevoIntervalo;
        Serial.print("ACK:CONFIG_UPDATED ");
        Serial.print(duracionPulsoMs);
        Serial.print(" ");
        Serial.println(intervaloGotaMs);
      } else {
        Serial.println("ERROR:VALORES_INVALIDOS");
      }
    } else {
      Serial.println("ERROR:FORMATO_SET");
    }
  } 
  else if (cmd == "STATUS") {
    Serial.print("STATUS: RUNNING=");
    Serial.print(bombaActiva ? "1" : "0");
    Serial.print(" PULSE=");
    Serial.print(duracionPulsoMs);
    Serial.print(" INTERVAL=");
    Serial.println(intervaloGotaMs);
  }
}

void loop() {
  // 1. Recepción y procesamiento de comandos serie
  if (Serial.available() > 0) {
    String entrada = Serial.readStringUntil('\n');
    procesarComando(entrada);
  }

  // 2. Control temporal no bloqueante con millis()
  if (bombaActiva) {
    unsigned long ahora = millis();

    if (enFaseDePulso) {
      // Si ya pasó el tiempo de duración del pulso, apagamos la bomba
      if (ahora - tiempoUltimaTransicion >= duracionPulsoMs) {
        digitalWrite(PIN_BOMBA, LOW);
        enFaseDePulso = false;
        tiempoUltimaTransicion = ahora;
      }
    } else {
      // Si ya pasó el intervalo de reposo entre gotas, encendemos la bomba
      if (ahora - tiempoUltimaTransicion >= intervaloGotaMs) {
        digitalWrite(PIN_BOMBA, HIGH);
        enFaseDePulso = true;
        tiempoUltimaTransicion = ahora;
      }
    }
  }
}
