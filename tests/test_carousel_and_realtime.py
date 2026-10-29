import tkinter as tk
import numpy as np
import cv2
import pytest

from Water_drop_method.carousel_controller import CarouselController, RealTimeWearAnalyzer
from Water_drop_method.paths import get_carousel_config_file
from Water_drop_method.app import WaterDropMethod


def _make_synthetic_aggregate_frame(radius: int, width: int = 320, height: int = 240) -> np.ndarray:
    """Create a bright background (220) with a dark aggregate circle (intensity 15 < threshold 40)."""
    frame = np.full((height, width, 3), 220, dtype=np.uint8)
    if radius > 0:
        cv2.circle(frame, (width // 2, height // 2), radius, (15, 15, 15), -1)
    return frame


def test_carousel_controller_simulation_navigation():
    carousel = CarouselController(total_slots=30, steps_per_slot=137)
    carousel.connect(port="Simulation")
    assert carousel.is_connected
    assert carousel.is_simulation
    assert carousel.current_slot == 1
    assert carousel.laser_aligned

    res_next = carousel.next_slot()
    assert res_next["slot"] == 2
    assert res_next["laser_aligned"] is True

    res_goto = carousel.goto_slot(30)
    assert res_goto["slot"] == 30

    # Wrapping from 30 -> 1
    res_wrap = carousel.next_slot()
    assert res_wrap["slot"] == 1

    res_prev = carousel.prev_slot()
    assert res_prev["slot"] == 30

    res_home = carousel.home()
    assert res_home["slot"] == 1

    # Record slot breakdown metrics
    carousel.record_slot_result(slot=1, drops=42, broken=True, final_normalized_area=-0.03)
    assert carousel.slot_results[1]["status"] == "BROKEN"
    assert carousel.slot_results[1]["drops"] == 42
    assert carousel.slot_results[1]["energy_mj"] == pytest.approx(42 * 0.102, rel=1e-3)


def test_carousel_geometry_splash_isolation():
    geom = CarouselController.calculate_geometry(total_slots=30, min_arc_spacing_cm=3.5)
    assert geom["total_slots"] == 30.0
    assert geom["angle_per_slot_deg"] == pytest.approx(12.0)
    assert geom["disc_diameter_cm"] == pytest.approx(33.42, abs=0.05)
    assert geom["steps_per_slot"] == pytest.approx(136.53, abs=0.05)
    assert geom["arc_spacing_cm"] >= 3.5


def test_realtime_wear_analyzer_drop_by_drop_rupture():
    # Support hole area = pi * r_hole^2. With r_hole = 20 px, area ~ 1256 px^2.
    hole_area = 1250.0
    analyzer = RealTimeWearAnalyzer(hole_area_px=hole_area, binary_threshold=40, rolling_window=5)

    # Frame 21 baseline: initial aggregate radius = 45 px (area ~ 6361 px^2)
    baseline_frame = _make_synthetic_aggregate_frame(radius=45)
    init_res = analyzer.initialize_baseline(baseline_frame)
    assert init_res["initialized"] is True
    assert init_res["initial_area_px"] > hole_area

    # Drops 1..5: intact aggregate (radius 45) -> Normalized area ~ 1.0, not broken
    for _ in range(5):
        info = analyzer.process_drop_frame(_make_synthetic_aggregate_frame(radius=45))
        assert info["is_broken"] is False
        assert info["normalized_area"] > 0.85

    # Progressive wear: radius shrinks to 30 px
    for _ in range(5):
        info = analyzer.process_drop_frame(_make_synthetic_aggregate_frame(radius=30))
        assert 0.1 < info["normalized_area"] < 0.8
        assert info["is_broken"] is False

    # Rupture: aggregate disintegrates down to support hole radius (radius = 18 px -> area ~ 1017 <= 1250)
    rupture_detected = False
    for _ in range(5):
        info = analyzer.process_drop_frame(_make_synthetic_aggregate_frame(radius=18))
        if info["is_broken"]:
            rupture_detected = True
            break

    assert rupture_detected is True
    assert info["normalized_area"] <= 0.0
    assert info["wear_percent"] == pytest.approx(100.0)
    assert info["annotated_roi"] is not None


def test_gui_carousel_and_realtime_measurement_integration(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cfg_path = get_carousel_config_file(migrate_legacy=False)
    assert cfg_path.parent.exists()

    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError:
        pytest.skip("Tkinter display unavailable in headless environment")

    try:
        app = WaterDropMethod(root)
        # Verify Carousel (30) tab and Real-Time Wear controls exist
        assert hasattr(app, "carousel")
        assert hasattr(app, "wear_analyzer")
        assert app.carousel.total_slots == 30
        assert app.realtime_wear_enabled.get() is True
        assert app.auto_carousel_on_rupture.get() is True

        # Navigate carousel from GUI methods
        app.carousel_home()
        assert app.carousel.current_slot == 1
        app.carousel_next()
        assert app.carousel.current_slot == 2
        app.carousel_prev()
        assert app.carousel.current_slot == 1
    finally:
        root.destroy()
