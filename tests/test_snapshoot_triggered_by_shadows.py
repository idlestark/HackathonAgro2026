from pathlib import Path
import sys


src = str(Path("src").resolve())
if src not in sys.path:
    sys.path.insert(0, src)

from Water_drop_method.Snapshoot_triggered_by_shadows import (
    PhotodiodeMonitor,
    update_detector_state,
)


def test_detector_triggers_once_until_signal_returns_to_threshold():
    armed, triggered = update_detector_state(value=0.4, threshold=0.5, armed=True)
    assert (armed, triggered) == (False, True)

    armed, triggered = update_detector_state(value=0.3, threshold=0.5, armed=armed)
    assert (armed, triggered) == (False, False)

    armed, triggered = update_detector_state(value=0.5, threshold=0.5, armed=armed)
    assert (armed, triggered) == (True, False)

    armed, triggered = update_detector_state(value=0.4, threshold=0.5, armed=armed)
    assert (armed, triggered) == (False, True)


def test_monitor_ignores_values_while_snapshot_is_open_and_rearms_afterwards():
    class FakeMeasurer:
        def measure(self):
            return None

    monitor = PhotodiodeMonitor(FakeMeasurer(), threshold=0.5)
    monitor._process_value(0.4)
    assert monitor.triggers.get_nowait() == 0.4

    monitor._process_value(0.6)
    assert monitor.triggers.empty()

    monitor.resume_detection()
    monitor._process_value(0.4)
    assert monitor.triggers.empty()

    monitor._process_value(0.5)
    monitor._process_value(0.4)
    assert monitor.triggers.get_nowait() == 0.4
