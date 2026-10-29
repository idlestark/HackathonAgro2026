"""Modular Carousel & Real-Time Wear Controller for the Water Drop Method.

Implements:
1. CarouselController: Controls a 30-aggregate rotating disc driven by a 28BYJ-48
   stepper motor (with ULN2003 driver) and/or DC motor (with H-bridge) on an ESP32
   or Arduino microcontroller, utilizing an optical laser reader (lector láser)
   for sub-millimetric slot alignment under the hypodermic needle.
2. RealTimeWearAnalyzer: Processes camera frames drop-by-drop in real time to compute
   aggregate contour area (Ac), 5-frame moving average, and normalized area
   (Ac - As) / (Ai - As), automatically determining when the sample breaks or
   disintegrates so the carousel can advance to the next aggregate.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# 28BYJ-48 in half-step mode has ~4096 steps per 360° revolution.
# For 30 aggregates spaced 12° apart: 4096 / 30 ≈ 136.53 steps per slot.
DEFAULT_TOTAL_SLOTS = 30
DEFAULT_STEPS_PER_REV = 4096
DEFAULT_STEPS_PER_SLOT = 137


class CarouselController:
    """Controls the 30-aggregate rotating carousel with stepper/DC motor and laser reader."""

    def __init__(
        self,
        port: str = "COM3",
        baudrate: int = 115200,
        total_slots: int = DEFAULT_TOTAL_SLOTS,
        steps_per_slot: int = DEFAULT_STEPS_PER_SLOT,
        motor_mode: str = "STEPPER_28BYJ48",
        use_laser_stop: bool = True,
        timeout: float = 2.0,
        shared_pump: Optional[Any] = None,
    ) -> None:
        self.port = port
        self.baudrate = int(baudrate)
        self.total_slots = max(1, int(total_slots))
        self.steps_per_slot = max(1, int(steps_per_slot))
        self.motor_mode = motor_mode  # "STEPPER_28BYJ48" or "DC_HBRIDGE"
        self.use_laser_stop = bool(use_laser_stop)
        self.timeout = float(timeout)
        self.shared_pump = shared_pump

        self._connection: Any = None
        self._is_connected: bool = False
        self._is_simulation: bool = False
        self._current_slot: int = 1  # 1-based index (1..30)
        self._laser_aligned: bool = True
        self._is_moving: bool = False
        self._lock = threading.Lock()

        # Track status and results of all 30 slots
        self.slot_results: Dict[int, Dict[str, Any]] = {
            slot: {
                "slot": slot,
                "status": "PENDING",  # PENDING, MEASURING, BROKEN, STABLE
                "drops": 0,
                "energy_mj": 0.0,
                "initial_area_px": 0.0,
                "final_area_px": 0.0,
                "normalized_final": 1.0,
                "video_file": "",
            }
            for slot in range(1, self.total_slots + 1)
        }

    @property
    def is_connected(self) -> bool:
        if self.shared_pump is not None and getattr(self.shared_pump, "is_connected", False):
            return True
        return self._is_connected

    @property
    def is_simulation(self) -> bool:
        if self.shared_pump is not None and getattr(self.shared_pump, "is_connected", False):
            return bool(getattr(self.shared_pump, "is_simulation", False))
        return self._is_simulation

    @property
    def current_slot(self) -> int:
        return self._current_slot

    @property
    def laser_aligned(self) -> bool:
        return self._laser_aligned

    @property
    def is_moving(self) -> bool:
        return self._is_moving

    def reset_slot_results(self) -> None:
        """Reset all 30 aggregate slot records to PENDING."""
        with self._lock:
            for slot in range(1, self.total_slots + 1):
                self.slot_results[slot] = {
                    "slot": slot,
                    "status": "PENDING",
                    "drops": 0,
                    "energy_mj": 0.0,
                    "initial_area_px": 0.0,
                    "final_area_px": 0.0,
                    "normalized_final": 1.0,
                    "video_file": "",
                }

    def record_slot_result(
        self,
        slot: int,
        status: str,
        drops: int,
        energy_mj: float,
        initial_area_px: float = 0.0,
        final_area_px: float = 0.0,
        normalized_final: float = 0.0,
        video_file: str = "",
    ) -> None:
        """Store measurement outcome for a specific aggregate slot."""
        with self._lock:
            if 1 <= slot <= self.total_slots:
                self.slot_results[slot] = {
                    "slot": slot,
                    "status": status,
                    "drops": int(drops),
                    "energy_mj": round(float(energy_mj), 4),
                    "initial_area_px": round(float(initial_area_px), 1),
                    "final_area_px": round(float(final_area_px), 1),
                    "normalized_final": round(float(normalized_final), 4),
                    "video_file": str(video_file),
                }

    def connect(
        self,
        port: Optional[str] = None,
        baudrate: Optional[int] = None,
        shared_pump: Optional[Any] = None,
    ) -> bool:
        """Connect to the ESP32/Arduino carousel controller or start simulation mode."""
        if shared_pump is not None:
            self.shared_pump = shared_pump
        if port is not None:
            self.port = port
        if baudrate is not None:
            self.baudrate = int(baudrate)

        with self._lock:
            if self.shared_pump is not None and getattr(self.shared_pump, "is_connected", False):
                self._is_connected = True
                self._is_simulation = bool(getattr(self.shared_pump, "is_simulation", False))
                self._laser_aligned = True
                logger.info("CarouselController attached to shared pump serial connection.")
                return True

            if self._is_connected:
                return True

            if self.port.lower() in ("simulation", "sim", "virtual", "test"):
                self._is_simulation = True
                self._is_connected = True
                self._current_slot = 1
                self._laser_aligned = True
                logger.info("CarouselController connected in SIMULATION mode.")
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
                time.sleep(2.0)
                self._connection.reset_input_buffer()
                self._send_command_unlocked(f"CAROUSEL:CONFIG {self.total_slots} {self.steps_per_slot}")
                self._laser_aligned = True
                logger.info(f"CarouselController connected on {self.port} at {self.baudrate} baud.")
                return True
            except Exception as exc:
                self._is_connected = False
                self._connection = None
                logger.error(f"Failed to connect CarouselController on {self.port}: {exc}")
                raise ConnectionError(f"Could not open port {self.port}: {exc}") from exc

    def disconnect(self) -> None:
        """Close serial connection if owned by CarouselController."""
        with self._lock:
            self.shared_pump = None
            if not self._is_connected:
                return
            if self._connection is not None:
                try:
                    self._connection.close()
                except Exception:
                    pass
                self._connection = None
            self._is_connected = False
            self._is_simulation = False
            logger.info("CarouselController disconnected.")

    def _send_command_unlocked(self, cmd: str) -> str:
        """Send serial command to ESP32/Arduino or handle in simulation mode."""
        if not self.is_connected:
            raise ConnectionError("Carousel controller is not connected.")

        if self.is_simulation:
            return self._simulate_command(cmd)

        # If sharing connection with PeristalticPump on the same ESP32/Arduino
        if self.shared_pump is not None and getattr(self.shared_pump, "is_connected", False):
            conn = getattr(self.shared_pump, "_connection", None)
            if conn is not None and conn.is_open:
                payload = f"{cmd}\n".encode("utf-8")
                conn.write(payload)
                conn.flush()
                return conn.readline().decode("utf-8", errors="ignore").strip()

        if self._connection is not None and self._connection.is_open:
            payload = f"{cmd}\n".encode("utf-8")
            self._connection.write(payload)
            self._connection.flush()
            return self._connection.readline().decode("utf-8", errors="ignore").strip()

        raise ConnectionError("Carousel serial connection lost.")

    def _simulate_command(self, cmd: str) -> str:
        """Simulate ESP32 + 28BYJ-48 / H-Bridge + Laser reader responses."""
        parts = cmd.strip().upper().split()
        if not parts:
            return "ACK:OK"

        action = parts[0]
        if action in ("NEXT", "CAROUSEL:NEXT"):
            self._current_slot = (self._current_slot % self.total_slots) + 1
            self._laser_aligned = True
            return f"ACK:SLOT={self._current_slot} LASER=1"

        if action in ("PREV", "CAROUSEL:PREV"):
            self._current_slot = ((self._current_slot - 2) % self.total_slots) + 1
            self._laser_aligned = True
            return f"ACK:SLOT={self._current_slot} LASER=1"

        if action in ("HOME", "CAROUSEL:HOME"):
            self._current_slot = 1
            self._laser_aligned = True
            return "ACK:SLOT=1 LASER=1 HOME=1"

        if action in ("GOTO", "CAROUSEL:GOTO") and len(parts) >= 2:
            target = int(parts[1])
            target = max(1, min(self.total_slots, target))
            self._current_slot = target
            self._laser_aligned = True
            return f"ACK:SLOT={self._current_slot} LASER=1"

        if action in ("STEP", "CAROUSEL:STEP") and len(parts) >= 2:
            steps = int(parts[1])
            return f"ACK:STEPPED {steps} LASER={1 if self._laser_aligned else 0}"

        if action in ("CAROUSEL:CONFIG", "SET_STEPS"):
            if len(parts) >= 3:
                self.total_slots = max(1, int(parts[1]))
                self.steps_per_slot = max(1, int(parts[2]))
            elif len(parts) >= 2:
                self.steps_per_slot = max(1, int(parts[1]))
            return f"ACK:CAROUSEL_CONFIG SLOTS={self.total_slots} STEPS={self.steps_per_slot}"

        if action in ("LASER", "CAROUSEL:LASER", "CAROUSEL:STATUS"):
            return f"STATUS:SLOT={self._current_slot} LASER={1 if self._laser_aligned else 0} MODE={self.motor_mode}"

        return "ACK:OK"

    def next_slot(self) -> Dict[str, Any]:
        """Advance the rotating disc to the next aggregate position and align with laser sensor."""
        with self._lock:
            self._is_moving = True
            try:
                resp = self._send_command_unlocked("CAROUSEL:NEXT")
                self._parse_slot_response(resp, fallback_slot=(self._current_slot % self.total_slots) + 1)
                return {
                    "slot": self._current_slot,
                    "laser_aligned": self._laser_aligned,
                    "response": resp,
                }
            finally:
                self._is_moving = False

    def prev_slot(self) -> Dict[str, Any]:
        """Move the rotating disc to the previous aggregate position."""
        with self._lock:
            self._is_moving = True
            try:
                resp = self._send_command_unlocked("CAROUSEL:PREV")
                self._parse_slot_response(resp, fallback_slot=((self._current_slot - 2) % self.total_slots) + 1)
                return {
                    "slot": self._current_slot,
                    "laser_aligned": self._laser_aligned,
                    "response": resp,
                }
            finally:
                self._is_moving = False

    def goto_slot(self, target_slot: int) -> Dict[str, Any]:
        """Rotate carousel directly to a specific slot (1..total_slots) and verify laser lock."""
        target = max(1, min(self.total_slots, int(target_slot)))
        with self._lock:
            self._is_moving = True
            try:
                resp = self._send_command_unlocked(f"CAROUSEL:GOTO {target}")
                self._parse_slot_response(resp, fallback_slot=target)
                return {
                    "slot": self._current_slot,
                    "laser_aligned": self._laser_aligned,
                    "response": resp,
                }
            finally:
                self._is_moving = False

    def home(self) -> Dict[str, Any]:
        """Return the carousel to Slot 1 using the optical laser index."""
        with self._lock:
            self._is_moving = True
            try:
                resp = self._send_command_unlocked("CAROUSEL:HOME")
                self._parse_slot_response(resp, fallback_slot=1)
                return {
                    "slot": self._current_slot,
                    "laser_aligned": self._laser_aligned,
                    "response": resp,
                }
            finally:
                self._is_moving = False

    def fine_step(self, steps: int) -> str:
        """Jog the stepper motor by a given number of steps for sub-millimetric alignment."""
        with self._lock:
            return self._send_command_unlocked(f"CAROUSEL:STEP {int(steps)}")

    def configure(self, total_slots: int = 30, steps_per_slot: int = 137, motor_mode: str = "STEPPER_28BYJ48") -> str:
        """Update carousel mechanical parameters."""
        with self._lock:
            self.total_slots = max(1, int(total_slots))
            self.steps_per_slot = max(1, int(steps_per_slot))
            self.motor_mode = motor_mode
            if self.is_connected:
                return self._send_command_unlocked(f"CAROUSEL:CONFIG {self.total_slots} {self.steps_per_slot}")
            return "ACK:SAVED_OFFLINE"

    def check_laser(self) -> bool:
        """Query the optical laser sensor state."""
        with self._lock:
            resp = self._send_command_unlocked("CAROUSEL:STATUS")
            self._parse_slot_response(resp, fallback_slot=self._current_slot)
            return self._laser_aligned

    def _parse_slot_response(self, resp: str, fallback_slot: int) -> None:
        """Extract SLOT=<n> and LASER=<0|1> from microcontroller response."""
        self._current_slot = fallback_slot
        self._laser_aligned = True
        for token in resp.replace(":", " ").split():
            if token.startswith("SLOT="):
                try:
                    self._current_slot = int(token.split("=")[1])
                except ValueError:
                    pass
            elif token.startswith("LASER="):
                try:
                    self._laser_aligned = int(token.split("=")[1]) == 1
                except ValueError:
                    pass

    @staticmethod
    def calculate_geometry(
        total_slots: int = 30,
        min_arc_spacing_cm: float = 3.5,
        support_hole_diameter_mm: float = 2.8,
        steps_per_rev: int = 4096,
    ) -> Dict[str, float]:
        """Compute mechanical and positioning metrics for the 30-aggregate carousel.

        Ensures adjacent supports are separated beyond the 3 cm splash zone (with splash
        baffles) and computes sub-millimetric step resolution.
        """
        slots = max(1, int(total_slots))
        circumference_cm = slots * float(min_arc_spacing_cm)
        diameter_cm = circumference_cm / math.pi
        radius_cm = diameter_cm / 2.0
        angle_per_slot_deg = 360.0 / slots
        steps_per_slot = steps_per_rev / float(slots)
        # Tangential arc length per motor step in mm
        arc_per_step_mm = (circumference_cm * 10.0) / float(steps_per_rev)
        hole_area_mm2 = math.pi * ((support_hole_diameter_mm / 2.0) ** 2)

        return {
            "total_slots": float(slots),
            "disc_diameter_cm": round(diameter_cm, 2),
            "disc_radius_cm": round(radius_cm, 2),
            "arc_spacing_cm": round(float(min_arc_spacing_cm), 2),
            "angle_per_slot_deg": round(angle_per_slot_deg, 2),
            "steps_per_slot": round(steps_per_slot, 2),
            "positioning_resolution_mm": round(arc_per_step_mm, 4),
            "support_hole_diameter_mm": round(support_hole_diameter_mm, 2),
            "support_hole_area_mm2": round(hole_area_mm2, 2),
        }


class RealTimeWearAnalyzer:
    """Real-time drop-by-drop soil aggregate wear and rupture detector.

    Implements the thesis methodology (Bocchio, 2026 - Section 2.3.1.6):
    - Identifies the aggregate contour via grayscale + inverse binary thresholding (cutoff=40).
    - Establishes a fixed Region of Interest (ROI) with a 20-pixel margin around the initial
      aggregate bounding box.
    - Tracks only the largest contour (excluding detached fragments) and caps area at Ai.
    - Applies a 5-frame rolling mean to smooth drop impact vibration.
    - Normalizes area: Normalized Area = (Ac - As) / (Ai - As), where As is the 2.8 mm support
      orifice area in pixels^2.
    - Triggers rupture when Normalized Area <= rupture_threshold (default 0.0, i.e., Ac <= As).
    """

    def __init__(
        self,
        hole_area_px: float = 4000.0,
        binary_threshold: int = 40,
        rolling_window: int = 5,
        roi_margin_px: int = 20,
        rupture_threshold: float = 0.0,
    ) -> None:
        self.hole_area_px = float(hole_area_px)
        self.binary_threshold = int(binary_threshold)
        self.rolling_window = max(1, int(rolling_window))
        self.roi_margin_px = max(0, int(roi_margin_px))
        self.rupture_threshold = float(rupture_threshold)

        self.reset()

    def reset(self) -> None:
        """Reset analyzer state for a new aggregate sample."""
        self.is_initialized: bool = False
        self.roi_box: Optional[Tuple[int, int, int, int]] = None  # (x1, y1, w1, h1)
        self.initial_area_px: float = 0.0  # Ai
        self.first_rolling_mean: Optional[float] = None
        self.raw_areas: List[float] = []
        self.smoothed_areas: List[float] = []
        self.normalized_areas: List[float] = []
        self.drop_numbers: List[int] = []
        self.is_broken: bool = False
        self.rupture_drop: Optional[int] = None

    def initialize_baseline(self, frame: np.ndarray) -> Dict[str, Any]:
        """Establish initial aggregate contour Ai and fixed ROI from baseline frame (e.g. frame 21)."""
        self.reset()
        if frame is None or frame.size == 0:
            raise ValueError("Empty frame provided for baseline initialization.")

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        _, thresh = cv2.threshold(gray, self.binary_threshold, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        h_img, w_img = gray.shape[:2]
        if contours:
            max_contour = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(max_contour)
            m = self.roi_margin_px
            x1 = max(x - m, 0)
            y1 = max(y - m, 0)
            w1 = min(w + 2 * m, w_img - x1)
            h1 = min(h + 2 * m, h_img - y1)
            max_area = float(cv2.contourArea(max_contour))
        else:
            # Fallback to full frame if synthetic/blank test frame has no dark contour
            x1, y1, w1, h1 = 0, 0, w_img, h_img
            max_area = max(self.hole_area_px * 2.0, 8000.0)

        if max_area <= self.hole_area_px:
            # Ensure denominator (Ai - As) is positive even on small synthetic test contours
            max_area = self.hole_area_px + max(1000.0, max_area)

        self.roi_box = (x1, y1, w1, h1)
        self.initial_area_px = max_area
        self.is_initialized = True

        return {
            "initialized": self.is_initialized,
            "roi_box": self.roi_box,
            "initial_area_px": self.initial_area_px,
            "hole_area_px": self.hole_area_px,
        }

    def process_drop_frame(self, frame: np.ndarray, drop_number: Optional[int] = None) -> Dict[str, Any]:
        """Analyze a single drop frame in real time and determine current wear and rupture status."""
        if frame is None or frame.size == 0:
            raise ValueError("Empty frame provided to process_drop_frame.")

        if not self.is_initialized or self.roi_box is None:
            self.initialize_baseline(frame)

        assert self.roi_box is not None
        x1, y1, w1, h1 = self.roi_box
        frame_rec = frame[y1 : y1 + h1, x1 : x1 + w1]
        gray_rec = cv2.cvtColor(frame_rec, cv2.COLOR_BGR2GRAY) if len(frame_rec.shape) == 3 else frame_rec
        _, thr = cv2.threshold(gray_rec, self.binary_threshold, 255, cv2.THRESH_BINARY_INV)
        ctrs, _ = cv2.findContours(thr, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        annotated_roi = frame_rec.copy() if len(frame_rec.shape) == 3 else cv2.cvtColor(frame_rec, cv2.COLOR_GRAY2BGR)
        if ctrs:
            cmax = max(ctrs, key=cv2.contourArea)
            area = float(cv2.contourArea(cmax))
            if area > self.initial_area_px:
                area = self.initial_area_px
            cv2.drawContours(annotated_roi, [cmax], -1, (0, 255, 0), 2)
        else:
            area = 0.0

        self.raw_areas.append(area)
        current_drop_num = int(drop_number) if drop_number is not None else len(self.raw_areas)
        self.drop_numbers.append(current_drop_num)

        # Rolling mean over up to `rolling_window` recent frames
        window_slice = self.raw_areas[-self.rolling_window :]
        rolling_mean = float(np.mean(window_slice))
        self.smoothed_areas.append(rolling_mean)

        if self.first_rolling_mean is None and len(self.raw_areas) >= self.rolling_window:
            self.first_rolling_mean = rolling_mean

        ref_initial = max(self.initial_area_px, self.first_rolling_mean or 0.0)
        denom = ref_initial - self.hole_area_px
        if abs(denom) <= 1e-9:
            denom = 1.0

        normalized = (rolling_mean - self.hole_area_px) / denom
        normalized = min(1.0, normalized)

        self.normalized_areas.append(float(normalized))

        # Check rupture condition: Ac <= As (normalized <= rupture_threshold)
        # Require at least rolling_window frames (or immediate complete disappearance area == 0)
        if not self.is_broken:
            if (len(self.raw_areas) >= self.rolling_window and normalized <= self.rupture_threshold) or (
                area < self.hole_area_px and normalized <= self.rupture_threshold
            ):
                self.is_broken = True
                self.rupture_drop = current_drop_num

        wear_percent = max(0.0, min(100.0, (1.0 - normalized) * 100.0))

        return {
            "drop_number": current_drop_num,
            "raw_area_px": round(area, 2),
            "smoothed_area_px": round(rolling_mean, 2),
            "initial_area_px": round(self.initial_area_px, 2),
            "hole_area_px": round(self.hole_area_px, 2),
            "normalized_area": round(float(normalized), 4),
            "wear_percent": round(wear_percent, 1),
            "is_broken": self.is_broken,
            "rupture_drop": self.rupture_drop,
            "annotated_roi": annotated_roi,
        }
