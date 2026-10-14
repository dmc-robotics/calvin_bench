"""Recording end to end: the real procedure, ODriveUsb and OhausAdventurer against a fake ODrive device and balance."""
import builtins

import pytest

from bench.errors import BenchError
from bench.experiments import static_gain
from bench.experiments.static_gain import procedure
from bench.experiments.static_gain.data import DEFAULT_LEVELS_NM, Measurement, ScaleSample, Settings
from bench.runs import Run
from bench.hardware import ohaus_adventurer
from bench.hardware.ohaus_adventurer import OhausError
from fakes import FakeBalance, lever_load

ARM_LENGTH_M = 0.2
QUICK = {"hold_s": 0.06, "sample_s": 0.04, "rest_s": 0.0, "overshoot_s": 0.02, "minimum_scale_readings": 1}


class Bench:
    """Answers the prompts: y to every confirmation, then the typed readings in order. Keeps the prompts it saw."""

    def __init__(self, readings=(), confirm="y"):
        self.readings = list(readings)
        self.confirm = confirm
        self.prompts = []

    def __call__(self, prompt=""):
        self.prompts.append(prompt)
        if "[y/N]" in prompt:
            return self.confirm
        return str(self.readings.pop(0))


SCALE_PORT = "/dev/cu.fake"


@pytest.fixture
def scale(device, monkeypatch):
    """A fake balance under the arm, weighing the torque the fake motor holds."""
    fake = FakeBalance(lever_load(device.axis0, ARM_LENGTH_M))
    monkeypatch.setattr(ohaus_adventurer.serial, "Serial", lambda *arguments, **options: fake)
    return fake


def only_run(runs_directory):
    [directory] = runs_directory.iterdir()
    return Run(directory)


def test_record_then_analyze_recovers_k(device, scale, runs_directory, monkeypatch):
    monkeypatch.setattr(builtins, "input", Bench())
    procedure.record(Settings("left", ARM_LENGTH_M, scale_port=SCALE_PORT, **QUICK))

    run = only_run(runs_directory)
    meta = run.meta
    assert meta["experiment"] == "static-gain"
    assert meta["settings"]["arm_length_m"] == ARM_LENGTH_M
    assert meta["odrive"]["node_id"] == 1
    assert meta["velocity_cap_rev_per_s"] == pytest.approx(1.5 * max(DEFAULT_LEVELS_NM) / device.axis0.controller.config.vel_gain)
    assert meta["scale"]["balance_id"] == "B000000001"
    assert run.read_json("odrive_config") == {"fake": True}
    rows = run.rows("data", Measurement)
    assert len(rows) == 2 * (2 + len(DEFAULT_LEVELS_NM))
    holds = [row.hold for row in rows]
    assert holds == list(range(len(holds)))
    assert {sample.hold for sample in run.rows("scale", ScaleSample)} == set(holds)  # every tare and hold has its scale samples

    static_gain.analyze(run, show=False)
    results = run.read_json("results")
    assert results["k"] == pytest.approx(device.axis0.k, rel=1e-3)
    for summary in results["directions"].values():
        assert summary["torque_constant_NmA"] == pytest.approx(results["torque_constant_expected_NmA"], rel=1e-3)
    assert results["warnings"] == []

    assert device.axis0.is_idle
    assert device.axis0.controller.config.vel_limit == 10.0  # restored
    assert scale.closed


def test_from_above_overshoots_first(device, scale, runs_directory, monkeypatch):
    monkeypatch.setattr(builtins, "input", Bench())
    procedure.record(Settings("left", ARM_LENGTH_M, levels_Nm=(0.05, 0.1, 0.15), from_above=True, scale_port=SCALE_PORT, **QUICK))

    assert max(device.axis0.torque_log) == pytest.approx(0.15 + 0.05)
    assert min(device.axis0.torque_log) == pytest.approx(-(0.15 + 0.05))
    approaches = [row.approach for row in only_run(runs_directory).rows("data", Measurement)]
    assert approaches.count("above") == 2 * 3


def test_without_a_scale_the_readings_are_typed(device, runs_directory, monkeypatch):
    levels = (0.05, 0.1, 0.15)
    readings = [50, 60, 70, 80, 50] * 2  # tare, three levels, tare; for each direction
    monkeypatch.setattr(builtins, "input", Bench(readings))
    procedure.record(Settings("left", ARM_LENGTH_M, levels_Nm=levels, **QUICK))

    run = only_run(runs_directory)
    rows = run.rows("data", Measurement)
    assert [row.scale_g for row in rows] == readings
    assert all(row.scale_samples is None for row in rows)
    assert not run.path("scale.csv").exists()
    assert run.meta["scale"] == "manual"


def test_r_repeats_a_level(device, runs_directory, monkeypatch):
    levels = (0.05, 0.1, 0.15)
    monkeypatch.setattr(builtins, "input", Bench([50, "r", 60, 70, 80, 50] + [50, 60, 70, 80, 50]))
    procedure.record(Settings("left", ARM_LENGTH_M, levels_Nm=levels, **QUICK))

    assert device.axis0.arm_count == 2 * len(levels) + 1
    holds = [row.hold for row in only_run(runs_directory).rows("data", Measurement)]
    assert holds == [0, *range(2, 2 * (2 + len(levels)) + 1)]  # hold 1 was repeated, so it has no row


def test_shaft_motion_stops_the_run_with_the_motor_idle(device, scale, runs_directory, monkeypatch):
    monkeypatch.setattr(builtins, "input", Bench())
    device.axis0.slip_after_reads = 3
    with pytest.raises(BenchError, match="shaft moved"):
        procedure.record(Settings("left", ARM_LENGTH_M, scale_port=SCALE_PORT, **QUICK))
    assert device.axis0.is_idle
    assert device.axis0.controller.config.vel_limit == 10.0


def test_the_balance_going_to_standby_mid_hold_stops_the_run_with_the_motor_idle(device, scale, runs_directory, monkeypatch):
    monkeypatch.setattr(builtins, "input", Bench())
    scale.standby_after_weights = 8  # partway through the holds, after the tare
    with pytest.raises(OhausError, match="standby"):
        procedure.record(Settings("left", ARM_LENGTH_M, scale_port=SCALE_PORT, **QUICK))
    assert device.axis0.arm_count >= 1
    assert device.axis0.is_idle
    assert device.axis0.controller.config.vel_limit == 10.0
    assert scale.closed


def test_declining_the_safety_check_moves_nothing_and_writes_nothing(device, scale, runs_directory, monkeypatch):
    bench = Bench(confirm="n")
    monkeypatch.setattr(builtins, "input", bench)
    with pytest.raises(BenchError, match="Aborted"):
        procedure.record(Settings("left", ARM_LENGTH_M, scale_port=SCALE_PORT, **QUICK))
    assert "e-stop" in bench.prompts[0]
    assert device.axis0.arm_count == 0
    assert not runs_directory.exists()


def test_the_wrong_odrive_moves_nothing(device, scale, runs_directory, monkeypatch):
    monkeypatch.setattr(builtins, "input", Bench())
    with pytest.raises(BenchError, match="Wrong ODrive"):
        procedure.record(Settings("right", ARM_LENGTH_M, scale_port=SCALE_PORT, **QUICK))
    assert device.axis0.arm_count == 0
