from pathlib import Path
import sys

# Ensure src path is available
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import pytest
from Water_drop_method.pump_controller import PeristalticPump, list_serial_ports


def test_list_serial_ports_includes_simulation():
    ports = list_serial_ports()
    assert any(p[0] == "Simulation" for p in ports)


def test_flow_rate_calculations_for_target():
    # 5 drops/sec * 20 uL * 60 s = 6.0 mL/min
    # total period = 200 ms -> pulse 14 ms + interval 186 ms
    pump = PeristalticPump(pulse_ms=14, interval_ms=186, drop_volume_ul=20.0)
    metrics = pump.calculate_metrics()

    assert metrics["drops_per_second"] == 5.0
    assert metrics["flow_rate_ml_min"] == 6.0
    assert metrics["cycle_time_ms"] == 200.0


def test_calculate_interval_for_target_flow():
    interval = PeristalticPump.calculate_interval_for_target_flow(
        target_flow_ml_min=6.0,
        pulse_ms=14,
        drop_volume_ul=20.0,
    )
    assert interval == 186


def test_simulation_lifecycle():
    pump = PeristalticPump(port="Simulation", pulse_ms=14, interval_ms=186)
    assert not pump.is_connected
    assert not pump.is_running

    assert pump.connect()
    assert pump.is_connected
    assert pump.is_simulation
    assert not pump.is_running

    start_resp = pump.start()
    assert "ACK:STARTED" in start_resp
    assert pump.is_running

    drop_resp = pump.single_drop()
    assert "ACK:DROP_DELIVERED" in drop_resp

    timing_resp = pump.set_timing(15, 200)
    assert "ACK:CONFIG_UPDATED" in timing_resp
    assert pump.pulse_ms == 15
    assert pump.interval_ms == 200

    stop_resp = pump.stop()
    assert "ACK:STOPPED" in stop_resp
    assert not pump.is_running

    pump.disconnect()
    assert not pump.is_connected


def test_unconnected_commands_raise_error():
    pump = PeristalticPump(port="COM99")
    with pytest.raises(ConnectionError):
        pump.start()
