"""Synthetic data.csv rows with known k, offset and stiction; the analysis must recover them."""
from dataclasses import replace

import pytest

from bench import units
from bench.errors import BenchError
from bench.experiments.static_gain import analysis
from bench.experiments.static_gain.data import DEFAULT_LEVELS_NM, DIRECTIONS, Measurement
from bench.runs import Run
from fakes import TORQUE_CONSTANT_NMA

ARM_LENGTH_M = 0.2
TARE_G = 50.0
K = {"positive": 0.97, "negative": 1.01}
OFFSET_NM = {"positive": 0.004, "negative": -0.003}
STICTION_NM = 0.006


def make_measurements(from_above=False, setpoint_error=0.0, tare_drift_g=0.0):
    measurements = []
    for direction, sign in DIRECTIONS.items():
        measurements.append(tare(len(measurements), direction, TARE_G))
        approaches = {"below": 0.0, "above": STICTION_NM} if from_above else {"below": 0.0}
        for approach, stiction in approaches.items():
            for level in DEFAULT_LEVELS_NM:
                command = sign * level
                # Coming from above, friction holds back the arm's release: more torque on the scale.
                torque = K[direction] * command + OFFSET_NM[direction] + sign * 2 * stiction
                grams = TARE_G + tare_drift_g / 2 + sign * torque / ARM_LENGTH_M / units.STANDARD_GRAVITY * 1000
                measurements.append(Measurement(
                    hold=len(measurements), direction=direction, approach=approach, torque_command_Nm=command,
                    scale_g=grams, scale_standard_deviation_g=0.1, scale_samples=8, scale_stable_samples=8,
                    iq_setpoint_A=command / TORQUE_CONSTANT_NMA * (1 + setpoint_error), iq_measured_A=command / TORQUE_CONSTANT_NMA,
                    vbus_V=15.8, fet_temperature_C=30.0, motor_temperature_C=None,
                ))
        measurements.append(tare(len(measurements), direction, TARE_G + tare_drift_g))
    return measurements


def tare(hold, direction, grams):
    return Measurement(
        hold=hold, direction=direction, approach="tare", torque_command_Nm=0.0,
        scale_g=grams, scale_standard_deviation_g=0.0, scale_samples=8, scale_stable_samples=8,
        iq_setpoint_A=None, iq_measured_A=None, vbus_V=None, fet_temperature_C=30.0, motor_temperature_C=None,
    )


def fit(tmp_path, measurements):
    """Through a real data.csv, as `bench analyze` reads it."""
    run = Run(tmp_path)
    run.append("data", *measurements)
    return analysis.fit(run.rows("data", Measurement), ARM_LENGTH_M, TORQUE_CONSTANT_NMA)[0]


def test_recovers_k_offset_and_g(tmp_path):
    results = fit(tmp_path, make_measurements())
    for direction in DIRECTIONS:
        result = results.directions[direction]
        assert result.k == pytest.approx(K[direction])
        assert result.offset_Nm == pytest.approx(OFFSET_NM[direction], abs=1e-9)
        assert result.max_residual_Nm == pytest.approx(0, abs=1e-9)
        assert result.tare_drift_g == 0
        assert result.static_friction_Nm is None
    k = (K["positive"] + K["negative"]) / 2
    assert results.k == pytest.approx(k)
    assert results.G == pytest.approx(units.BELT_RATIO * k)
    assert results.asymmetry_percent == pytest.approx(100 * abs(K["positive"] - K["negative"]) / k)
    assert results.warnings == []


def test_measured_torque_constant_is_k_times_the_configured_one(tmp_path):
    # Iq tracks the command, and the motor makes k times the commanded torque.
    results = fit(tmp_path, make_measurements())
    for direction in DIRECTIONS:
        assert results.directions[direction].torque_constant_NmA == pytest.approx(K[direction] * TORQUE_CONSTANT_NMA)


def test_stiction_from_above(tmp_path):
    results = fit(tmp_path, make_measurements(from_above=True))
    for direction in DIRECTIONS:
        result = results.directions[direction]
        assert result.static_friction_Nm == pytest.approx(STICTION_NM)
        assert result.static_friction_per_level_Nm == pytest.approx([STICTION_NM] * len(DEFAULT_LEVELS_NM))
        assert result.k == pytest.approx(K[direction])  # the from-above pass stays out of the fit


def test_warns_on_clipped_torque(tmp_path):
    warnings = fit(tmp_path, make_measurements(setpoint_error=-0.05)).warnings
    assert len(warnings) == 2
    assert all("clipped" in warning for warning in warnings)


def test_warns_on_tare_drift(tmp_path):
    results = fit(tmp_path, make_measurements(tare_drift_g=3.0))
    assert results.directions["positive"].tare_drift_g == pytest.approx(3.0)
    assert sum("tare drifted" in warning for warning in results.warnings) == 2


def test_skips_an_incomplete_direction(tmp_path):
    results = fit(tmp_path, make_measurements()[:-1])  # the negative direction's closing tare is missing
    assert list(results.directions) == ["positive"]
    assert results.asymmetry_percent is None
    assert len(results.warnings) == 1
    assert "negative skipped" in results.warnings[0]


def test_a_run_with_no_complete_direction_raises(tmp_path):
    incomplete = [m for m in make_measurements() if m.approach != "tare"]
    with pytest.raises(BenchError, match="No complete direction"):
        fit(tmp_path, incomplete)


def test_counts_only_the_from_below_levels_toward_a_complete_direction(tmp_path):
    two_below = [m for m in make_measurements(from_above=True) if m.approach != "below" or abs(m.torque_command_Nm) < 0.11]
    with pytest.raises(BenchError, match="No complete direction"):
        fit(tmp_path, two_below)


def test_a_held_level_without_iq_is_refused(tmp_path):
    measurements = make_measurements()
    measurements[1] = replace(measurements[1], iq_setpoint_A=None)
    with pytest.raises(BenchError, match="holds 1 have no iq_setpoint_A"):
        fit(tmp_path, measurements)
