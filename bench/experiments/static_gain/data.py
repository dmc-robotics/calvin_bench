"""What a static-gain run holds: its Settings (in meta.json), data.csv rows (Measurement) and scale.csv rows (ScaleSample)."""
from dataclasses import dataclass

from bench.errors import BenchError
from bench.hardware import scale

EXPERIMENT = "static-gain"
DIRECTIONS = {"positive": 1.0, "negative": -1.0}
DEFAULT_LEVELS_NM = (0.05, 0.10, 0.15, 0.20, 0.25)
DEFAULT_MAX_TORQUE_NM = 0.25


@dataclass(frozen=True)
class Settings:
    """Everything that shapes a recording. Saved whole in meta.json."""
    motor: str
    arm_length_m: float  # shaft center to scale contact
    levels_Nm: tuple[float, ...] = DEFAULT_LEVELS_NM  # torque magnitudes, motor-side
    from_above: bool = False  # add a pass approaching each level from above (stiction)
    max_torque_Nm: float = DEFAULT_MAX_TORQUE_NM
    scale_port: str | None = scale.DEFAULT_PORT  # None: the readings are typed in
    overshoot_Nm: float = 0.05  # how far above a level the from-above pass starts
    overshoot_s: float = 0.5
    hold_s: float = 2.5
    sample_s: float = 1.0  # averaged at the end of each hold and tare
    rest_s: float = 5.0  # minimum time idle between holds
    minimum_scale_readings: int = 4  # in the averaged window; ~8 normally

    def __post_init__(self):
        if self.highest_torque_Nm > self.max_torque_Nm:
            raise BenchError(
                f"Levels reach {self.highest_torque_Nm:.3f} N·m, above the max torque {self.max_torque_Nm:.3f} N·m. "
                "Raise --max-torque deliberately if you mean it."
            )

    @property
    def highest_torque_Nm(self):
        return max(self.levels_Nm) + (self.overshoot_Nm if self.from_above else 0.0)

    @property
    def approaches(self):
        return ("below", "above") if self.from_above else ("below",)


@dataclass(frozen=True)
class Measurement:
    """A data.csv row: a tare (motor idle, command 0, no Iq or vbus) or a held torque level. Empty cells are None."""
    direction: str  # positive or negative
    approach: str  # tare, below or above
    torque_command_Nm: float
    scale_g: float  # mean over the end of the hold, or typed in
    scale_std_g: float | None  # None for typed readings, as are the counts
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
    direction: str
    approach: str
    torque_command_Nm: float
    time_s: float
    scale_g: float
    stable: bool
