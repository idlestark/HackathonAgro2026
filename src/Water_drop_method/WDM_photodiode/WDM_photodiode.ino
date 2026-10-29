void setup() {
  // Inicializa la comunicación serie a 9600 baudios
  // (Esta velocidad DEBE coincidir con la configurada en el script de Python)
  Serial.begin(115200);
}

void loop() {
  // Ejemplo 1: Leer un sensor en el pin analógico A0
  int valorSensor = analogRead(A0);

  // Enviar el valor seguido de un salto de línea (\n)
  Serial.println(valorSensor);

  // Pausa de 10 ms entre envíos
  //delay(10);
}
