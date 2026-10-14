"""Settings refuse bad values however they're built, listing every problem."""
import pytest

from bench.errors import BenchError
from bench.experiments.static_gain.data import Settings


def test_the_defaults_are_valid():
    Settings("left", 0.2)


@pytest.mark.parametrize("changes, problem", [
    ({"motor": "middle"}, "motor is 'middle'"),
    ({"arm_length_m": 0}, "arm_length_m is 0"),
    ({"arm_length_m": 200}, "in meters"),
    ({"levels_Nm": (0.05, -0.1, 0.15)}, "expected positive torque magnitudes"),
    ({"levels_Nm": (0.05, 0.1, 0.1)}, "at least 3 distinct levels"),
    ({"max_torque_Nm": float("nan")}, "max_torque_Nm is nan"),
    ({"sample_s": 0}, "sample_s is 0"),
    ({"hold_s": 1.0, "sample_s": 2.0}, "longer than hold_s"),
    ({"rest_s": -1}, "rest_s is -1"),
    ({"minimum_scale_readings": 0}, "minimum_scale_readings is 0"),
    ({"from_above": True}, "above the max torque"),  # 0.25 + 0.05 overshoot > 0.25
])
def test_bad_settings_are_refused(changes, problem):
    with pytest.raises(BenchError) as error:
        Settings(**{"motor": "left", "arm_length_m": 0.2} | changes)
    assert problem in str(error.value)


def test_every_problem_is_listed():
    with pytest.raises(BenchError) as error:
        Settings("middle", 200, sample_s=0)
    message = str(error.value)
    for problem in ("motor is", "in meters", "sample_s is 0"):
        assert problem in message
