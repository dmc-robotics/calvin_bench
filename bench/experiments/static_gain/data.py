"""What a static-gain run holds: its Settings (in meta.json), data.csv rows (Measurement), scale.csv rows (ScaleSample)
and odrive.csv rows (ODriveSample)."""
import math
from dataclasses import dataclass

from bench.errors import BenchError
from bench.motors import NODE_IDS

NAME = "static-gain"
DIRECTIONS = {"positive": 1.0, "negative": -1.0}
DEFAULT_LEVELS_NM = (0.05, 0.10, 0.15, 0.20, 0.25)
DEFAULT_MAX_TORQUE_NM = 0.25
MINIMUM_LEVELS = 3  # for a line fit
TORQUE_TOLERANCE_NM = 1e-9  # float rounding in a level plus the overshoot


@dataclass(frozen=True)
class Settings:
    """Everything that shapes a recording. Saved whole in meta.json."""
    motor: str
    arm_length_m: float  # shaft center to scale contact
    levels_Nm: tuple[float, ...] = DEFAULT_LEVELS_NM  # torque magnitudes, motor-side
    from_above: bool = False  # add a pass approaching each level from above (stiction)
    max_torque_Nm: float = DEFAULT_MAX_TORQUE_NM
    scale_port: str | None = None  # None: the readings are typed in
    overshoot_Nm: float = 0.05  # how far above a level the from-above pass starts
    overshoot_s: float = 0.5
    hold_s: float = 3.0  # the averaged last sample_s starts 0.5 s after the balance's typical 1.5 s settling
    sample_s: float = 1.0  # averaged at the end of each hold and tare
    rest_s: float = 5.0  # minimum time idle between holds
    minimum_scale_readings: int = 4  # in the averaged window (~8 normally); fewer is recorded but flagged as low confidence

    def __post_init__(self):
        """Refuse bad settings however they were built, listing every problem."""
        problems = []
        if self.motor not in NODE_IDS:
            problems.append(f"motor is {self.motor!r}, expected {' or '.join(NODE_IDS)}.")
        for name in ("arm_length_m", "max_torque_Nm", "overshoot_Nm", "overshoot_s", "hold_s", "sample_s"):
            if not is_positive(value := getattr(self, name)):
                problems.append(f"{name} is {value}, expected a positive number.")
        if self.arm_length_m >= 1:
            problems.append(f"arm_length_m is {self.arm_length_m}: it's in meters, e.g. 0.200.")
        if not all(map(is_positive, self.levels_Nm)):
            problems.append(f"levels_Nm are {self.levels_Nm}, expected positive torque magnitudes.")
        if len(set(self.levels_Nm)) < MINIMUM_LEVELS:
            problems.append(f"levels_Nm are {self.levels_Nm}, expected at least {MINIMUM_LEVELS} distinct levels for a line fit.")
        if self.sample_s > self.hold_s:
            problems.append(f"sample_s {self.sample_s} is longer than hold_s {self.hold_s}.")
        if not self.rest_s >= 0:
            problems.append(f"rest_s is {self.rest_s}, expected 0 or more.")
        if self.minimum_scale_readings < 1:
            problems.append(f"minimum_scale_readings is {self.minimum_scale_readings}, expected 1 or more.")
        if self.levels_Nm and self.highest_torque_Nm > self.max_torque_Nm + TORQUE_TOLERANCE_NM:
            problems.append(
                f"levels reach {self.highest_torque_Nm:.3f} N·m, above the max torque {self.max_torque_Nm:.3f} N·m. "
                "Raise --max-torque deliberately if you mean it."
            )
        if problems:
            raise BenchError("Bad settings:\n  - " + "\n  - ".join(problems))

    @property
    def highest_torque_Nm(self):
        return max(self.levels_Nm) + (self.overshoot_Nm if self.from_above else 0.0)

    @property
    def approaches(self):
        return ("below", "above") if self.from_above else ("below",)


@dataclass(frozen=True)
class Measurement:
    """A data.csv row: a tare (motor idle, command 0, no Iq or vbus) or a held torque level. Empty cells are None."""
    hold: int  # numbers every tare and hold in the run from 0, repeats included; scale.csv rows carry the same number
    direction: str  # positive or negative
    approach: str  # tare, below or above
    torque_command_Nm: float
    scale_g: float  # mean over the end of the hold, or typed in
    scale_standard_deviation_g: float | None  # None for typed readings, as are the counts
    scale_samples: int | None
    scale_stable_samples: int | None
    iq_setpoint_A: float | None
    iq_measured_A: float | None
    vbus_V: float | None
    fet_temperature_C: float
    motor_temperature_C: float | None  # None when the motor thermistor isn't enabled


@dataclass(frozen=True)
class ScaleSample:
    """A scale.csv row: one balance reading. time_s counts from when the torque was applied (negative during an overshoot)."""
    hold: int  # the tare or hold it was read during: the data.csv row with this number, none if it was repeated
    direction: str
    approach: str
    torque_command_Nm: float
    time_s: float
    scale_g: float
    stable: bool
    net: bool  # True if the balance had a tare set: someone pressed Tare


@dataclass(frozen=True)
class ODriveSample:
    """An odrive.csv row: one pass of the hold loop, raw ODrive units. time_s as in scale.csv."""
    hold: int
    direction: str
    approach: str
    torque_command_Nm: float  # the level; the overshoot's own torque is torque_command_Nm ± overshoot_Nm while time_s < 0
    time_s: float
    feed_gap_s: float  # since the watchdog's previous feed
    position_rev: float
    velocity_rev_per_s: float
    iq_setpoint_A: float
    iq_measured_A: float
    vbus_V: float


def is_positive(value):
    return math.isfinite(value) and value > 0
