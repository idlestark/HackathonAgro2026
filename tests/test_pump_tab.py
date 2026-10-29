import os
from pathlib import Path
import sys
import tkinter as tk
import pytest

# Ensure src path is in sys.path
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from Water_drop_method.app import WaterDropMethod
from Water_drop_method.paths import get_pump_timing_file


@pytest.fixture(scope="module")
def shared_tk_root():
    root = tk.Tk()
    root.withdraw()
    yield root
    try:
        root.destroy()
    except Exception:
        pass


def test_pump_tab_flow_and_tutorial(monkeypatch, tmp_path, shared_tk_root):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    root = shared_tk_root

    app = WaterDropMethod(root)

    # 1. Check tab is present
    tab_names = [app.notebook.tab(i, "text") for i in range(app.notebook.index("end"))]
    assert "Pump Control" in tab_names

    # 2. Check pump attributes and hardware defaults (14 ms / 200 ms)
    assert hasattr(app, "pump")
    assert not app.pump.is_connected
    assert app.auto_pump_on_measurement.get() is True
    assert app.pump_pulse_var.get() == 14
    assert app.pump_interval_var.get() == 200

    # 3. Test preset calculation
    app.apply_target_6ml_preset()
    assert app.pump_pulse_var.get() == 14
    assert app.pump_interval_var.get() == 200

    # 4. Connect to simulation mode
    for dev, desc in app.pump_ports_list:
        if dev == "Simulation":
            app.pump_port_var.set(desc)
            break

    app.toggle_pump_connection()
    assert app.pump.is_connected
    assert app.pump.is_simulation
    assert "Connected" in app.pump_status_label.cget("text")

    # 5. Start flow in simulation
    app.start_pump_flow()
    assert app.pump.is_running
    assert "RUNNING" in app.pump_status_label.cget("text")

    # 6. Deliver single drop
    app.deliver_single_drop()

    # 7. Stop flow
    app.stop_pump_flow()
    assert not app.pump.is_running

    # 8. Test persistence: save new default and reload
    app.save_pump_timing_default(15, 210)
    p, i = app.load_pump_timing_default()
    assert (p, i) == (15, 210)

    # 9. Test tutorial window opens cleanly
    app.show_measurement_tutorial()
    toplevels = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
    assert len(toplevels) == 1
    toplevels[0].destroy()

    # Cleanup tab widgets
    app.cleanup_camera()
    app.cleanup_dac()
    app.pump.disconnect()
    for child in root.winfo_children():
        child.destroy()


def test_pump_loads_saved_defaults_on_startup(monkeypatch, tmp_path, shared_tk_root):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    root = shared_tk_root

    # Pre-write custom default timing
    timing_file = get_pump_timing_file()
    timing_file.write_text("18,250\n", encoding="utf-8")

    app = WaterDropMethod(root)
    assert app.pump_pulse_var.get() == 18
    assert app.pump_interval_var.get() == 250
    assert app.pump.pulse_ms == 18
    assert app.pump.interval_ms == 250

    app.cleanup_camera()
    app.cleanup_dac()
    app.pump.disconnect()
    for child in root.winfo_children():
        child.destroy()
