# Water Drop Method

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)
![Status](https://img.shields.io/badge/status-active-success)

Desktop app based on Tkinter to implement the Water Drop Method and determine the Sample Breakdown Energy of water-stable soil aggregates.

## Distribution

The application is currently distributed as a compiled build for Windows 64-bit.

- GitHub Releases: https://github.com/alencina-faa/Water-drop-method/releases
- SourceForge: https://sourceforge.net/projects/water-drop-method/

## Highlights

- GUI workflow with tabs for camera preview, threshold setup, measurement, drop energy, and video processing.
- Runtime state persisted per user on Windows.
- Package-safe import structure for src-layout projects.
- Basic automated test suite with structural and persistence checks.

## Project Structure

- `src/Water_drop_method`: application package
- `tests`: automated tests
- `output`: local build artifacts (ignored by git)

## Requirements

- Python 3.10+
- Dependencies:
  - `pillow`
  - `numpy`
  - `matplotlib`
  - `opencv-python`
  - `nidaqmx` and/or `pyserial`

## Install (Editable)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

## Run

```bash
python -m Water_drop_method
```

## Run the shadow-triggered snapshot script

The standalone console script asks before calibration and measurement, collects Arduino photodiode readings, and displays them in a gridded plot. Enter and confirm the threshold in volts in the console. It then displays one webcam snapshot per shadow event. Close each snapshot window to resume detection; it rearms only after the photodiode reading returns to or above the threshold. Press `Ctrl+C` to stop measurement.

```bash
python -m Water_drop_method.Snapshoot_triggered_by_shadows
```

The defaults are Arduino port `COM3`, webcam index `0`, and `5000` calibration samples. Override them with `--port`, `--camera`, or `--samples`.

## Run Tests

```bash
pytest -q
```

## Tabs Guide

| Tab | What it is used for | Main actions | Screenshot |
| --- | --- | --- | --- |
| Camera | Preview the camera feed and validate framing before measurements. | Select camera device, Start Preview, Stop Preview. | <img src="screenshots/image1.png" alt="Camera tab" width="80%" /> |
| Set Threshold | Compute and confirm the photodiode threshold. | Select DAC device, set number of measures, Set Threshold, Confirm Threshold. | <img src="screenshots/image2.png" alt="Set Threshold tab" width="80%" /> |
| Measurement | Execute the drop measurement workflow with real-time drop-by-drop wear analysis and automatic carousel rotation. | Select camera and DAC, enable Real-Time Wear & Auto-Carousel (1–30 samples), Save File As, start/stop acquisition. | <img src="screenshots/image3.png" alt="Measurement tab" width="80%" /> |
| Pump Control | Configure, calibrate, and automate the 12V peristaltic pump replacing the Mariotte tube. | Connect COM/Simulation, adjust pulse/interval, Preset 6.0 mL/min, Deliver 1 Drop, Start/Stop pump. | - |
| Carousel (30) | Control the 30-aggregate rotating disc driven by 28BYJ-48 stepper (ULN2003) / DC H-Bridge on ESP32 with optical laser alignment reader. | Connect ESP32/Simulation, Home/Next/Prev/Go to Slot, verify Laser Reader alignment, inspect 30-sample breakdown matrix & export CSV. | - |
| Drop Energy | Estimate drop velocity and impact energy from physical parameters. | Configure physical values and run Start Simulation. | <img src="screenshots/image4.png" alt="Drop Energy tab" width="80%" /> |
| Video Processing | Batch-process videos and analyze normalized area over frames. | Load videos folder, define hole area, Process Videos, inspect plots and outputs. | <img src="screenshots/image5.png" alt="Video Processing tab" width="80%" /> |
| Help | Browse a guided, clickable explanation for every tab inside the app. | Select a topic on the left, read the step-by-step guidance on the right. | <img src="screenshots/image6.png" alt="Help tab" width="80%" /> |

## Peristaltic Pump & Hardware Setup

For wiring diagrams, MOSFET connection schematics, Arduino/ESP32 sketches, and 6.0 mL/min calibration details, consult [docs/peristaltic_pump_guide.md](docs/peristaltic_pump_guide.md).


## Runtime State Files

The app stores runtime state in a per-user writable folder:

- Windows: `%APPDATA%\\WaterDropMethod`
- Fallback: `<home>/WaterDropMethod`

Persisted files:

- `threshold.txt`
- `hole_area.txt`
- `pump_timing.txt`
- `carousel_config.txt`

## Legacy Migration

If legacy `threshold.txt`, `hole_area.txt`, `pump_timing.txt`, or `carousel_config.txt` files are found in the current working directory, the app performs a one-time best-effort copy to the per-user state folder when those values are requested.

These runtime files are intentionally excluded from version control.

---

## Update: Hackathon Agro 2026

Modernización y automatización integral del sistema para:
1. Reemplazar el tubo de Mariotte tradicional por una **bomba peristáltica dosificadora de 12V** accionada por **módulo dual MOSFET** y microcontrolador (**Arduino Uno / ESP32**).
2. Incorporar un **disco giratorio (carrusel) superior de 30 agregados** accionado por **motores de paso 28BYJ-48 con driver ULN2003** (y soporte para **motores DC con puente H**) gobernados por una placa **ESP32** con **lector óptico láser** de posicionamiento.
3. Procesar mediante la **cámara en tiempo real, gota a gota, el desgaste sufrido por el agregado**, determinando automáticamente el instante exacto en que la muestra se deshace o rompe para girar a la siguiente posición del disco y medir secuencialmente los **30 agregados** con solo su colocación inicial ($\le 30\text{ min}$ de tiempo de operador).

### Principales Mejoras Implementadas:

1. **Disco Giratorio Automático de 30 Agregados + Lector Láser (`Carousel (30)`):**
   - **Accionamiento electromecánico:** Control integrado desde Python (`carousel_controller.py`) y firmware ESP32/Arduino (`WDM_carousel_stepper.ino` y `WDM_photodiode_and_pump.ino`) compatible con motores de paso **28BYJ-48 + driver ULN2003** en secuencia de medio paso ($4096\text{ pasos/rev} \Rightarrow 137\text{ pasos por muestra a } 12^\circ$) y **motores continuos con Puente H (L298N / L9110)**.
   - **Alineación submilimétrica con Lector Láser:** Cada soporte de $2,8\text{ mm}$ de diámetro cuenta con indexación óptica detectada por un sensor láser digital (`PIN_LASER_SENSOR`). Durante el giro entre muestras, el motor realiza el avance rápido inicial y ajusta paso a paso hasta que el lector láser confirma la alineación exacta debajo de la aguja hipodérmica 18G.
   - **Aislamiento contra salpicaduras ($> 3\text{ cm}$):** Geometría calculada para 30 soportes separados a $12^\circ$ con arco de $3,5\text{ cm}$ ($\varnothing = 33,42\text{ cm}$, radio $16,71\text{ cm}$) y mamparas radiales antisalpicadura para impedir que el radio de salpicadura de las gotas ($3\text{ cm}$) humedezca los agregados contiguos antes de ser medidos.
   - **Matriz de estado de las 30 muestras en vivo:** Visualización interactiva en grilla $6 \times 5$ con estado por muestra (`PENDING`, `MEASURING`, `BROKEN`, `STABLE_500`), número de gotas hasta ruptura, área normalizada final y energía de ruptura en $\text{mJ}$, exportable a CSV (`Export 30-Sample CSV`).

2. **Procesamiento de Desgaste por Cámara en Tiempo Real, Gota a Gota (`RealTimeWearAnalyzer`):**
   - Implementación en tiempo real del algoritmo óptico de la tesis doctoral (Bocchio, 2026):
     - Estabilización lumínica automática durante los primeros 20 fotogramas y captura automática del **fotograma base (frame 21)** para fijar la **Región de Interés (ROI)** con margen de $20\text{ px}$ y el área inicial del agregado ($A_i$).
     - Con cada gota detectada por el fotodiodo, se recorta la ROI, se convierte a escala de grises y se aplica umbralización binaria inversa a `40` (`cv2.THRESH_BINARY_INV`), extrayendo el contorno máximo ($A_c \le A_i$) y suavizándolo con media móvil de 5 fotogramas.
     - Cálculo gota a gota del **Área Normalizada** y del **Porcentaje de Desgaste**:
       $$\text{Área Normalizada} = \frac{A_c - A_s}{A_i - A_s}$$
       donde $A_s$ es el área del orificio vacío del soporte de $2,8\text{ mm}$ (`hole_area`, configurable en la GUI, por defecto `4000 px²`).
   - **Detección automática de ruptura y reemplazo de muestra:** Cuando la cámara detecta en tiempo real que el agregado se deshizo o atravesó el soporte ($\text{Área Normalizada} \le 0$), o cuando alcanza el límite de 500 gotas:
     1. Detiene instantáneamente la bomba peristáltica (`STOP`).
     2. Guarda el video `.avi` y las métricas de energía de ruptura de esa posición (`_slot01.avi`, `_slot02.avi`, ...).
     3. Ordena al ESP32 girar el disco giratorio hasta la siguiente posición validada por el **lector láser** (`CAROUSEL:NEXT`).
     4. Reanuda automáticamente la medición para el siguiente agregado hasta completar los 30 agregados del lote.

3. **Control de Flujo Continuo de Bomba Peristáltica sin Bloqueos:**
   - Firmware en C++ (`.ino`) para Arduino / ESP32 basado en temporización no bloqueante con `millis()`, eliminando las pausas de `delay()`.
   - Comunicación bidireccional por puerto Serial (115200 baudios) con protocolo unificado para bomba y carrusel (`START`, `STOP`, `DROP`, `SET <pulso> <intervalo>`, `CAROUSEL:NEXT`, `CAROUSEL:PREV`, `CAROUSEL:GOTO`, `CAROUSEL:HOME`, `CAROUSEL:STEP`, `CAROUSEL:CONFIG`, `CAROUSEL:STATUS`).
4. **Pestaña "Pump Control" en la Aplicación:**
   - Detección automática de puertos COM (incluye modo *Simulation* para pruebas sin hardware).
   - Calibración en tiempo real de pulso de encendido (`pulse_ms`) e intervalo entre gotas (`interval_ms`).
   - Valores predeterminados del banco experimental (**14 ms de pulso / 200 ms de intervalo $\approx$ 6.0 mL/min**).
   - Botón **`⭐ Save as Default...`** con diálogo de confirmación para persistir nuevas calibraciones en `%APPDATA%\WaterDropMethod\pump_timing.txt`.
   - Botón **`💧 1 Drop (Prime)`** para purgado rápido de mangueras y cebado de la aguja.
   - Tablero en vivo con indicadores de cadencia (gotas/s), caudal (mL/min) y período (ms).
5. **Documentación Técnica y Esquemática:**
   - Guía del disco giratorio de 30 agregados, lector láser y visión en tiempo real: [`docs/carousel_30_aggregates_guide.md`](docs/carousel_30_aggregates_guide.md).
   - Guía de la bomba peristáltica y MOSFET: [`docs/peristaltic_pump_guide.md`](docs/peristaltic_pump_guide.md).


