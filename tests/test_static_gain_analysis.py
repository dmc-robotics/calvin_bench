"""Synthetic data.csv rows with known k, offset and stiction; the analysis must recover them."""
import pytest

from bench import units
from bench.errors import BenchError
from bench.experiments.static_gain import analysis
from bench.experiments.static_gain.data import DEFAULT_LEVELS_NM, DIRECTIONS, Measurement
from bench.runs import Run

ARM_LENGTH_M = 0.2
TORQUE_CONSTANT_NMA = 8.27 / 330
TARE_G = 50.0
K = {"positive": 0.97, "negative": 1.01}
OFFSET_NM = {"positive": 0.004, "negative": -0.003}
STICTION_NM = 0.006


def make_measurements(from_above=False, setpoint_error=0.0, tare_drift_g=0.0):
    measurements = []
    for direction, sign in DIRECTIONS.items():
        measurements.append(tare(direction, TARE_G))
        approaches = {"below": 0.0, "above": STICTION_NM} if from_above else {"below": 0.0}
        for approach, stiction in approaches.items():
            for level in DEFAULT_LEVELS_NM:
                command = sign * level
                # Coming from above, friction holds back the arm's release: more torque on the scale.
                torque = K[direction] * command + OFFSET_NM[direction] + sign * 2 * stiction
                grams = TARE_G + tare_drift_g / 2 + sign * torque / ARM_LENGTH_M / units.STANDARD_GRAVITY * 1000
                measurements.append(Measurement(
                    direction, approach, command, grams, 0.1, 8, 8,
                    command / TORQUE_CONSTANT_NMA * (1 + setpoint_error), command / TORQUE_CONSTANT_NMA, 15.8, 30.0, None,
                ))
        measurements.append(tare(direction, TARE_G + tare_drift_g))
    return measurements


def tare(direction, grams):
    return Measurement(direction, "tare", 0.0, grams, 0.0, 8, 8, None, None, None, 30.0, None)


def fit(tmp_path, measurements):
    """Through a real data.csv, so the rows come back as strings with empty cells, as `bench analyze` sees them."""
    run = Run(tmp_path)
    run.append("data", *measurements)
    return analysis.fit(run.rows("data"), ARM_LENGTH_M, TORQUE_CONSTANT_NMA)[0]


def test_recovers_k_offset_and_g(tmp_path):
    results = fit(tmp_path, make_measurements())
    for direction in DIRECTIONS:
        summary = results["directions"][direction]
        assert summary["k"] == pytest.approx(K[direction])
        assert summary["offset_Nm"] == pytest.approx(OFFSET_NM[direction], abs=1e-9)
        assert summary["max_residual_Nm"] == pytest.approx(0, abs=1e-9)
        assert summary["tare_drift_g"] == 0
        assert "static_friction_Nm" not in summary
    k = (K["positive"] + K["negative"]) / 2
    assert results["k"] == pytest.approx(k)
    assert results["G"] == pytest.approx(units.BELT_RATIO * k)
    assert results["asymmetry_percent"] == pytest.approx(100 * abs(K["positive"] - K["negative"]) / k)
    assert results["warnings"] == []


def test_measured_torque_constant_is_k_times_the_configured_one(tmp_path):
    # Iq tracks the command, and the motor makes k times the commanded torque.
    results = fit(tmp_path, make_measurements())
    for direction in DIRECTIONS:
        assert results["directions"][direction]["torque_constant_NmA"] == pytest.approx(K[direction] * TORQUE_CONSTANT_NMA)


def test_stiction_from_above(tmp_path):
    results = fit(tmp_path, make_measurements(from_above=True))
    for direction in DIRECTIONS:
        summary = results["directions"][direction]
        assert summary["static_friction_Nm"] == pytest.approx(STICTION_NM)
        assert summary["k"] == pytest.approx(K[direction])  # the from-above pass stays out of the fit


def test_warns_on_clipped_torque(tmp_path):
    warnings = fit(tmp_path, make_measurements(setpoint_error=-0.05))["warnings"]
    assert len(warnings) == 2
    assert all("clipped" in warning for warning in warnings)


def test_warns_on_tare_drift(tmp_path):
    results = fit(tmp_path, make_measurements(tare_drift_g=3.0))
    assert results["directions"]["positive"]["tare_drift_g"] == pytest.approx(3.0)
    assert sum("tare drifted" in warning for warning in results["warnings"]) == 2


def test_skips_an_incomplete_direction(tmp_path):
    results = fit(tmp_path, make_measurements()[:-1])  # the negative direction's closing tare is missing
    assert list(results["directions"]) == ["positive"]
    assert "asymmetry_percent" not in results
    assert len(results["warnings"]) == 1
    assert "negative skipped" in results["warnings"][0]


def test_a_run_with_no_complete_direction_raises(tmp_path):
    incomplete = [m for m in make_measurements() if m.approach != "tare"]
    with pytest.raises(BenchError, match="No complete direction"):
        fit(tmp_path, incomplete)
