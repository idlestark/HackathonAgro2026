"""Modular Peristaltic Pump Controller for the Water Drop Method.

Controls an Arduino / ESP32 microcontroller operating a dual MOSFET driver
to actuate a 12V peristaltic pump with millisecond accuracy.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def list_serial_ports() -> List[Tuple[str, str]]:
    """Scan and return available serial ports as a list of (port, description) tuples.

    Includes a virtual Simulation port for offline development and testing.
    """
    ports: List[Tuple[str, str]] = []
    try:
        import serial.tools.list_ports
        for port_info in serial.tools.list_ports.comports():
            desc = f"{port_info.device} ({port_info.description})" if port_info.description else port_info.device
            ports.append((port_info.device, desc))
    except ImportError:
        pass

    ports.append(("Simulation", "Virtual Simulation Device (No hardware)"))
    return ports


class PeristalticPump:
    """Controls a peristaltic pump via serial communication with an Arduino or ESP32."""

    def __init__(
        self,
        port: str = "COM3",
        baudrate: int = 115200,
        pulse_ms: int = 14,
        interval_ms: int = 200,
        drop_volume_ul: float = 20.0,
        timeout: float = 1.0,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.pulse_ms = int(pulse_ms)
        self.interval_ms = int(interval_ms)
        self.drop_volume_ul = float(drop_volume_ul)
        self.timeout = timeout

        self._connection: Any = None
        self._is_connected: bool = False
        self._is_running: bool = False
        self._is_simulation: bool = False
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def is_simulation(self) -> bool:
        return self._is_simulation

    def connect(self, port: Optional[str] = None, baudrate: Optional[int] = None) -> bool:
        """Connect to the serial port or start simulation mode."""
        if port is not None:
            self.port = port
        if baudrate is not None:
            self.baudrate = baudrate

        with self._lock:
            if self._is_connected:
                return True

            if self.port.lower() in ("simulation", "sim", "virtual", "test"):
                self._is_simulation = True
                self._is_connected = True
                self._is_running = False
                logger.info("PeristalticPump connected in SIMULATION mode.")
                return True

            try:
                import serial
                self._connection = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=self.timeout,
                )
                self._is_simulation = False
                self._is_connected = True
                self._is_running = False
                # Give microcontroller time to initialize (DTR reset on Arduino Uno)
                time.sleep(2.0)
                # Flush startup garbage
                self._connection.reset_input_buffer()
                # Apply initial timing parameters
                self._send_command_unlocked(f"SET {self.pulse_ms} {self.interval_ms}")
                logger.info(f"PeristalticPump connected to {self.port} at {self.baudrate} baud.")
                return True
            except Exception as exc:
                self._is_connected = False
                self._connection = None
                logger.error(f"Failed to connect to pump on {self.port}: {exc}")
                raise ConnectionError(f"Could not open port {self.port}: {exc}") from exc

    def disconnect(self) -> None:
        """Stop the pump and close the serial connection."""
        with self._lock:
            if not self._is_connected:
                return

            try:
                if self._is_running:
                    self._stop_unlocked()
            except Exception:
                pass

            if self._connection is not None:
                try:
                    self._connection.close()
                except Exception:
                    pass
                self._connection = None

            self._is_connected = False
            self._is_running = False
            self._is_simulation = False
            logger.info("PeristalticPump disconnected.")

    def _send_command_unlocked(self, cmd: str) -> str:
        """Send command without acquiring lock (must be called with self._lock held)."""
        if not self._is_connected:
            raise ConnectionError("Pump controller is not connected.")

        if self._is_simulation:
            if cmd == "START":
                self._is_running = True
                return "ACK:STARTED"
            elif cmd == "STOP":
                self._is_running = False
                return "ACK:STOPPED"
            elif cmd == "DROP":
                return "ACK:DROP_DELIVERED"
            elif cmd.startswith("SET "):
                parts = cmd.split()
                if len(parts) >= 3:
                    self.pulse_ms = int(parts[1])
                    self.interval_ms = int(parts[2])
                return f"ACK:CONFIG_UPDATED {self.pulse_ms} {self.interval_ms}"
            return "ACK:OK"

        if self._connection and self._connection.is_open:
            payload = f"{cmd}\n".encode("utf-8")
            self._connection.write(payload)
            self._connection.flush()
            response = self._connection.readline().decode("utf-8", errors="ignore").strip()
            return response

        raise ConnectionError("Serial port connection was lost.")

    def start(self) -> str:
        """Start continuous drop delivery."""
        with self._lock:
            resp = self._send_command_unlocked("START")
            self._is_running = True
            return resp

    def _stop_unlocked(self) -> str:
        resp = self._send_command_unlocked("STOP")
        self._is_running = False
        return resp

    def stop(self) -> str:
        """Stop drop delivery immediately."""
        with self._lock:
            return self._stop_unlocked()

    def single_drop(self) -> str:
        """Deliver a single calibrated drop for testing or priming."""
        with self._lock:
            return self._send_command_unlocked("DROP")

    def set_timing(self, pulse_ms: int, interval_ms: int) -> str:
        """Configure drop pulse duration and inter-drop interval in milliseconds."""
        p = max(1, int(pulse_ms))
        i = max(10, int(interval_ms))
        with self._lock:
            self.pulse_ms = p
            self.interval_ms = i
            return self._send_command_unlocked(f"SET {p} {i}")

    def calculate_metrics(
        self,
        pulse_ms: Optional[int] = None,
        interval_ms: Optional[int] = None,
        drop_volume_ul: Optional[float] = None,
    ) -> Dict[str, float]:
        """Calculate cadence (drops/s) and flow rate (mL/min) based on current or provided parameters."""
        p = self.pulse_ms if pulse_ms is None else max(1, int(pulse_ms))
        i = self.interval_ms if interval_ms is None else max(10, int(interval_ms))
        vol = self.drop_volume_ul if drop_volume_ul is None else float(drop_volume_ul)

        cycle_time_ms = p + i
        drops_per_second = 1000.0 / cycle_time_ms if cycle_time_ms > 0 else 0.0
        # Flow rate in mL/min = (drops/s) * (vol uL / 1000 uL/mL) * (60 s/min)
        flow_rate_ml_min = drops_per_second * (vol / 1000.0) * 60.0

        return {
            "pulse_ms": float(p),
            "interval_ms": float(i),
            "cycle_time_ms": float(cycle_time_ms),
            "drops_per_second": round(drops_per_second, 2),
            "flow_rate_ml_min": round(flow_rate_ml_min, 2),
            "drop_volume_ul": vol,
        }

    @staticmethod
    def calculate_interval_for_target_flow(
        target_flow_ml_min: float = 6.0,
        pulse_ms: int = 14,
        drop_volume_ul: float = 20.0,
    ) -> int:
        """Calculate the required inter-drop interval in ms to achieve a given flow rate (e.g. 6.0 mL/min)."""
        if target_flow_ml_min <= 0 or drop_volume_ul <= 0:
            return 200

        # target_flow (mL/min) = (drops_per_sec * drop_volume_ul * 60) / 1000
        # drops_per_sec = (target_flow * 1000) / (drop_volume_ul * 60)
        drops_per_sec = (target_flow_ml_min * 1000.0) / (drop_volume_ul * 60.0)
        total_period_ms = 1000.0 / drops_per_sec
        interval_ms = int(round(total_period_ms - pulse_ms))
        return max(10, interval_ms)
