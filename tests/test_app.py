from pathlib import Path
import sys


def _ensure_src_import_path():
    src = str(Path("src").resolve())
    if src not in sys.path:
        sys.path.insert(0, src)


def test_app_uses_relative_imports_for_internal_modules():
    source = Path("src/Water_drop_method/app.py").read_text(encoding="utf-8")
    assert "from .camera_device import CameraOpenCV as cam" in source
    assert "from .data_acquisition import NIUSB6009 as dac" in source
    assert "from Camera import" not in source
    assert "from DAC import" not in source


def test_paths_helpers_return_txt_files_in_state_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    _ensure_src_import_path()

    from Water_drop_method.paths import get_hole_area_file, get_threshold_file

    threshold_file = get_threshold_file()
    hole_area_file = get_hole_area_file()

    assert threshold_file.name == "threshold.txt"
    assert hole_area_file.name == "hole_area.txt"
    assert threshold_file.parent.exists()
    assert hole_area_file.parent.exists()
    assert threshold_file.parent == tmp_path / "WaterDropMethod"


def test_main_module_uses_package_relative_import():
    source = Path("src/Water_drop_method/__main__.py").read_text(encoding="utf-8")
    assert "from .app import main" in source


def test_paths_helpers_support_real_write_and_read(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    _ensure_src_import_path()

    from Water_drop_method.paths import get_hole_area_file, get_threshold_file

    threshold_file = get_threshold_file()
    hole_area_file = get_hole_area_file()

    threshold_file.write_text("2.5\n", encoding="utf-8")
    hole_area_file.write_text("101\n", encoding="utf-8")

    assert get_threshold_file().read_text(encoding="utf-8").strip() == "2.5"
    assert get_hole_area_file().read_text(encoding="utf-8").strip() == "101"


def test_legacy_root_files_are_migrated_once(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    _ensure_src_import_path()

    (tmp_path / "threshold.txt").write_text("1.23\n", encoding="utf-8")
    (tmp_path / "hole_area.txt").write_text("77\n", encoding="utf-8")

    from Water_drop_method.paths import get_hole_area_file, get_threshold_file

    threshold_file = get_threshold_file()
    hole_area_file = get_hole_area_file()

    assert threshold_file.read_text(encoding="utf-8").strip() == "1.23"
    assert hole_area_file.read_text(encoding="utf-8").strip() == "77"
