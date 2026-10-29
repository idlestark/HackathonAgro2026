from pathlib import Path
import os


def get_state_dir() -> Path:
    """Return per-user writable state directory for Water Drop Method."""
    base = Path(os.environ.get("APPDATA", Path.home()))
    state_dir = base / "WaterDropMethod"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def _migrate_legacy_file(filename: str, destination: Path) -> None:
    """Copy a legacy cwd state file to the canonical state path if needed."""
    legacy = Path.cwd() / filename
    if destination.exists() or not legacy.exists():
        return

    try:
        destination.write_text(legacy.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        # Never block app execution for an optional migration step.
        return


def get_threshold_file(migrate_legacy: bool = True) -> Path:
    destination = get_state_dir() / "threshold.txt"
    if migrate_legacy:
        _migrate_legacy_file("threshold.txt", destination)
    return destination


def get_hole_area_file(migrate_legacy: bool = True) -> Path:
    destination = get_state_dir() / "hole_area.txt"
    if migrate_legacy:
        _migrate_legacy_file("hole_area.txt", destination)
    return destination


def get_pump_timing_file(migrate_legacy: bool = True) -> Path:
    destination = get_state_dir() / "pump_timing.txt"
    if migrate_legacy:
        _migrate_legacy_file("pump_timing.txt", destination)
    return destination


def get_carousel_config_file(migrate_legacy: bool = True) -> Path:
    destination = get_state_dir() / "carousel_config.txt"
    if migrate_legacy:
        _migrate_legacy_file("carousel_config.txt", destination)
    return destination


