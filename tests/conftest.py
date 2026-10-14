import matplotlib
import pytest

matplotlib.use("Agg")

from bench import runs
from bench.hardware import odrive_usb
from fakes import FakeDevice


@pytest.fixture
def device(monkeypatch):
    """A fake ODrive that ODriveUsb.connect() finds, with arming shortened so holds are quick."""
    fake = FakeDevice()
    monkeypatch.setattr(odrive_usb.odrive, "find_sync", lambda timeout: fake)
    monkeypatch.setattr(odrive_usb, "backup_config", lambda device: {"fake": True})
    monkeypatch.setattr(odrive_usb, "dump_errors", lambda device: None)
    monkeypatch.setattr(odrive_usb, "ARMING_S", 0.02)
    return fake


@pytest.fixture
def runs_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(runs, "RUNS_DIRECTORY", tmp_path / "runs")
    return tmp_path / "runs"
