# Guía de Integración y Calibración: Bomba Peristáltica 12V

Este documento describe la sustitución del tubo de Mariotte por una **bomba peristáltica de 12V** accionada por un **módulo dual MOSFET** y controlada mediante microcontrolador (**Arduino Uno** o **ESP32-C3**), totalmente integrada con la aplicación **Water Drop Method**.

---

## 1. Diagrama de Conexionado

### Componentes necesarios:
1. **Bomba Peristáltica 12V** (motor DC).
2. **Módulo Driver Dual MOSFET de Potencia** (15A / 400W, entrada trigger 3.3V - 20V DC).
3. **Placa Arduino Uno R3** o **ESP32-C3**.
4. **Fuente de Alimentación Externa 12V DC** (mínimo 1A a 2A recomendada para el motor).
5. Cable USB de conexión a la PC.
6. (Opcional recomendado) Diodo de protección contra retorno inductivo (ej. 1N4007) en paralelo con los bornes de la bomba.

### Esquema Eléctrico:

```text
       FUENTE EXTERNA 12V DC
           +12V      GND (0V)
             │          │
             │          │
   ┌─────────┼──────────┼──────────────────────────────────────┐
   │         ▼          ▼                                      │
   │      [ VIN+       VIN- ]                                  │
   │                                                           │
   │              MÓDULO DUAL MOSFET (15A / 400W)              │
   │                                                           │
   │      [ OUT+       OUT- ]   ───► Bornes del Motor 12V      │
   │         │          │            de la Bomba Peristáltica  │
   │         └────┬─────┘                                      │
   │              │                                            │
   │         [+]──┴──[-] (Diodo 1N4007 flyback recomendado)    │
   │                                                           │
   │      ENTRADA DE SEÑAL (Trigger):                          │
   │      [ PWM / TRIG ]   ──────► Pin 9 (Arduino Uno)         │
   │                                o GPIO 18 (ESP32-C3)       │
   │                                                           │
   │      [    GND     ]   ──────► GND del Arduino / ESP32     │
   │                               (¡Masa común indispensable!)│
   └───────────────────────────────────────────────────────────┘
```

> **IMPORTANTE:**
> 1. Conecta la **tierra (GND)** del microcontrolador al terminal **GND de señal** del módulo MOSFET.
> 2. No alimentes la bomba de 12V directamente desde los pines de 5V o 3.3V del Arduino/ESP32; utiliza siempre la fuente de alimentación externa de 12V conectada a `VIN+` y `VIN-`.

---

## 2. Sketches de Microcontrolador (.ino)

Se proporcionan dos sketches listos para compilar:

1. **`src/Water_drop_method/WDM_peristaltic_pump/WDM_peristaltic_pump.ino`**:
   - Firmware especializado exclusivamente para el control de la bomba.
   - Ideal si utilizas una placa dedicada solo a la bomba (o si usas NI-USB6009 para el fotodiodo).
2. **`src/Water_drop_method/WDM_photodiode_and_pump/WDM_photodiode_and_pump.ino`**:
   - Firmware integrado que lee el fotodiodo por entrada analógica (`A0` en Uno / `GPIO 0` en ESP32-C3) y al mismo tiempo controla la bomba peristáltica sin bloqueos de `delay()`.

### Protocolo Serie (115200 baudios):
- `START`: Activa el goteo periódico continuo.
- `STOP`: Detiene la bomba de inmediato.
- `DROP`: Entrega un único pulso de gota (para prueba o cebado de la aguja).
- `SET <pulso_ms> <intervalo_ms>`: Actualiza los tiempos al vuelo sin reiniciar la placa.
- `STATUS`: Consulta el estado actual.

---

## 3. Calibración para Flujo de 6.0 mL/min (5 gotas/segundo)

El método calibrado en tu banco experimental utiliza:
- **`entregarGota(14);`** $\longrightarrow$ Pulso ON de **14 ms**.
- **`delay(200);`** $\longrightarrow$ Intervalo OFF de **200 ms**.
- **Flujo resultante verificado:** $\approx 6.0\ \text{mL/min}$.

### Gestión de Valores por Defecto en la Pestaña "Pump Control":
1. **Valores Iniciales del Sistema:**
   - Al iniciar la app por primera vez, carga exactamente **14 ms** de pulso y **200 ms** de intervalo.
2. **Botón `⭐ Save as Default...`:**
   - Si en el futuro cambias de motor, tubo o aguja y calibras otros valores (por ejemplo, 16 ms y 190 ms), presiona este botón.
   - Te mostrará un diálogo de confirmación:
     > *"¿Estás seguro de que deseas guardar esta configuración como el nuevo valor POR DEFECTO? Se cargará automáticamente cada vez que inicies el programa."*
   - Al confirmar, se persiste en `%APPDATA%\WaterDropMethod\pump_timing.txt`.
3. **Botón `Reset to Factory`:**
   - Si deseas volver a los valores originales de laboratorio (**14 ms / 200 ms**), presiona este botón para restablecerlos de inmediato.
4. **Botón `Preset 14 ms / 200 ms`:**
   - Vuelve a colocar 14 ms y 200 ms en los controles sin sobreescribir tu archivo de configuración permanente.

---

## 4. Uso Modular desde Python

Puedes invocar el controlador de la bomba desde cualquier script externo de Python:

```python
import time
from Water_drop_method.pump_controller import PeristalticPump

# 1. Instanciar el controlador (o usar port="Simulation" para pruebas)
pump = PeristalticPump(port="COM3", baudrate=115200, pulse_ms=14, interval_ms=186)

# 2. Conectar
pump.connect()

# 3. Entregar una gota de prueba
pump.single_drop()
time.sleep(1)

# 4. Iniciar flujo continuo a 6 mL/min
pump.start()
time.sleep(10)  # Bombear durante 10 segundos

# 5. Detener y desconectar
pump.stop()
pump.disconnect()
```

---

## 5. Automatización con la Medición

En la pestaña **Pump Control** se incluye la opción:
> ☑ **Auto-start pump on 'Start Measurement' and stop on finish**

Cuando está tildada:
1. Al presionar **Start Measurement** en la pestaña de medición, la bomba se enciende automáticamente.
2. Al registrarse la totalidad de gotas programadas (o presionar **Stop Measurement**), la bomba se detiene de inmediato.
