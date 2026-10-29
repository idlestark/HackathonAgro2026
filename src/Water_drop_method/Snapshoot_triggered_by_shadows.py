"""Capture webcam snapshots when an Arduino photodiode detects a shadow."""

import argparse
import math
import queue
import sys
import threading
import time
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator, FormatStrFormatter, MaxNLocator

if __package__:
    from .camera_device import CameraOpenCV
    from .data_acquisition import ArduinoUno
    from .paths import get_threshold_file
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from Water_drop_method.camera_device import CameraOpenCV
    from Water_drop_method.data_acquisition import ArduinoUno
    from Water_drop_method.paths import get_threshold_file


def update_detector_state(value: float, threshold: float, armed: bool) -> tuple[bool, bool]:
    """Return the next armed state and whether this reading triggers a snapshot."""
    if armed and value < threshold:
        return False, True
    if not armed and value >= threshold:
        return True, False
    return armed, False


class PhotodiodeMonitor:
    def __init__(self, measurer: ArduinoUno, threshold: float) -> None:
        self.measurer = measurer
        self.threshold = threshold
        self.armed = True
        self.detection_enabled = True
        self.triggers: queue.Queue[float] = queue.Queue()
        self.errors: queue.Queue[Exception] = queue.Queue()
        self.stop_event = threading.Event()
        self.state_lock = threading.Lock()
        self.thread = threading.Thread(target=self._read_loop, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _process_value(self, value: float) -> None:
        with self.state_lock:
            if not self.detection_enabled:
                return

            self.armed, triggered = update_detector_state(
                value,
                self.threshold,
                self.armed,
            )
            if triggered:
                self.detection_enabled = False
                self.triggers.put_nowait(value)

    def _read_loop(self) -> None:
        try:
            while not self.stop_event.is_set():
                value = self.measurer.measure()
                if value is not None:
                    self._process_value(value)
        except Exception as exc:
            self.errors.put(exc)

    def resume_detection(self) -> None:
        with self.state_lock:
            self.detection_enabled = True

    def raise_if_failed(self) -> None:
        try:
            error = self.errors.get_nowait()
        except queue.Empty:
            return
        raise RuntimeError(f"Arduino photodiode reader failed: {error}") from error

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=1)
        if self.thread.is_alive():
            raise RuntimeError("Arduino photodiode reader did not stop within one second.")


def ask_yes_no(prompt: str) -> bool:
    while True:
        answer = input(f"{prompt} [Y/N]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer Y or N.")


def collect_calibration_samples(measurer: ArduinoUno, sample_count: int) -> list[float]:
    print(f"Collecting {sample_count} photodiode readings...")
    measurer.stop()
    deadline = time.monotonic() + 30
    values: list[float] = []

    while len(values) < sample_count:
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Received {len(values)} of {sample_count} samples within 30 seconds."
            )
        value = measurer.measure()
        if value is not None:
            values.append(value)

    measurer.stop()
    return values


def show_calibration_plot(values: list[float], threshold: float | None = None) -> None:
    figure, axes = plt.subplots(figsize=(9, 5))
    axes.plot(range(1, len(values) + 1), values, linewidth=0.8)
    axes.set_title("Photodiode threshold calibration")
    axes.set_xlabel("Sample")
    axes.set_ylabel("Photodiode voltage (V)")
    axes.yaxis.set_major_locator(MaxNLocator(nbins=12))
    axes.yaxis.set_major_formatter(FormatStrFormatter("%.4f"))
    axes.yaxis.set_minor_locator(AutoMinorLocator(2))
    axes.grid(True, which="major", linestyle="--", alpha=0.65)
    axes.grid(True, which="minor", linestyle=":", alpha=0.4)

    minimum = min(values)
    maximum = max(values)
    if threshold is not None:
        minimum = min(minimum, threshold)
        maximum = max(maximum, threshold)
    padding = max((maximum - minimum) * 0.08, 0.005)
    axes.set_ylim(max(0, minimum - padding), min(5, maximum + padding))

    if threshold is not None:
        axes.axhline(threshold, color="red", linestyle="-", label=f"Threshold: {threshold:.4f} V")
        axes.legend()

    figure.tight_layout()
    plt.show()
    plt.close(figure)


def prompt_for_threshold(values: list[float]) -> float:
    print(f"Observed photodiode range: {min(values):.4f} to {max(values):.4f} V.")
    while True:
        answer = input("Enter the threshold in volts (0-5): ").strip()
        try:
            threshold = float(answer)
        except ValueError:
            print("Enter a numeric threshold.")
            continue
        if not math.isfinite(threshold) or not 0 <= threshold <= 5:
            print("The Arduino photodiode threshold must be between 0 and 5 V.")
            continue
        return threshold


def select_threshold(values: list[float]) -> float:
    show_calibration_plot(values)
    while True:
        threshold = prompt_for_threshold(values)
        show_calibration_plot(values, threshold)
        if ask_yes_no(f"Confirm threshold {threshold:.4f} V?"):
            return threshold


def wait_for_snapshot_close(window_name: str, monitor: PhotodiodeMonitor) -> None:
    while True:
        monitor.raise_if_failed()
        key = cv2.waitKey(20)
        try:
            is_visible = cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) >= 1
        except cv2.error:
            is_visible = False
        if key == 27 or not is_visible:
            try:
                cv2.destroyWindow(window_name)
            except cv2.error:
                pass
            return


def run(port: str, camera_device: int, sample_count: int) -> None:
    if sample_count <= 0:
        raise ValueError("The calibration sample count must be positive.")

    measurer: ArduinoUno | None = None
    camera: CameraOpenCV | None = None
    monitor: PhotodiodeMonitor | None = None
    try:
        if not ask_yes_no("Ready to connect to the Arduino and collect calibration readings?"):
            print("Calibration cancelled.")
            return

        measurer = ArduinoUno(port=port, baudrate=115200, timeout=0.1)
        measurer.start()
        values = collect_calibration_samples(measurer, sample_count)
        threshold = select_threshold(values)

        try:
            with get_threshold_file().open("w", encoding="utf-8") as threshold_file:
                threshold_file.write(f"{threshold}\n")
        except OSError as exc:
            raise OSError(f"Could not save the threshold: {exc}") from exc
        print(f"Threshold saved: {threshold:.4f} V.")

        if not ask_yes_no("Start continuous shadow-triggered measurement?"):
            print("Measurement not started.")
            return

        camera = CameraOpenCV()
        camera.start(device=camera_device)
        measurer.stop()
        monitor = PhotodiodeMonitor(measurer, threshold)
        monitor.start()
        print("Measuring. Close each snapshot window to resume detection; press Ctrl+C to stop.")

        window_name = "Shadow-triggered snapshot"
        while True:
            monitor.raise_if_failed()
            try:
                measured_value = monitor.triggers.get(timeout=0.1)
            except queue.Empty:
                continue

            frame = camera.get_frame()
            cv2.imshow(window_name, frame)
            print(f"Shadow detected at {measured_value:.4f} V; snapshot displayed.")
            wait_for_snapshot_close(window_name, monitor)
            monitor.resume_detection()
            print("Snapshot closed; waiting for the signal to return to or above the threshold.")
    finally:
        cleanup_errors: list[str] = []
        if monitor is not None:
            try:
                monitor.stop()
            except Exception as exc:
                cleanup_errors.append(str(exc))
        if camera is not None:
            try:
                camera.stop()
            except Exception as exc:
                cleanup_errors.append(f"Could not release the camera: {exc}")
            try:
                camera.close_window()
            except Exception as exc:
                cleanup_errors.append(f"Could not close camera windows: {exc}")
        if measurer is not None:
            try:
                measurer.stop()
            except Exception as exc:
                cleanup_errors.append(f"Could not clear the Arduino input buffer: {exc}")
            try:
                measurer.close()
            except Exception as exc:
                cleanup_errors.append(f"Could not close the Arduino connection: {exc}")
        if cleanup_errors:
            raise RuntimeError("Cleanup failed: " + "; ".join(cleanup_errors))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture webcam snapshots when an Arduino photodiode detects shadows."
    )
    parser.add_argument("--port", default="COM3", help="Arduino serial port (default: COM3)")
    parser.add_argument("--camera", type=int, default=1, help="USB webcam index (default: 1)")
    parser.add_argument(
        "--samples",
        type=int,
        default=5000,
        help="Number of photodiode readings used for threshold calibration (default: 5000)",
    )
    args = parser.parse_args()

    try:
        run(port=args.port, camera_device=args.camera, sample_count=args.samples)
    except KeyboardInterrupt:
        print("\nInterrupted; stopping measurement.")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
