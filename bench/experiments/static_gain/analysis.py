"""Experiment 2's analysis (instructions/02-static-torque-gain.md, Analysis). Pure: Measurements in, Results out."""
from dataclasses import dataclass

import numpy as np

from bench import motors, units
from bench.errors import BenchError
from bench.experiments.static_gain.data import DIRECTIONS, MINIMUM_LEVELS

TARE_DRIFT_LIMIT_G = 2.0
CURRENT_MISMATCH_LIMIT = 0.02


@dataclass(frozen=True)
class DirectionResult:
    """One direction's entry in results.json."""
    k: float
    offset_Nm: float
    torque_constant_NmA: float
    max_residual_Nm: float
    max_residual_percent: float
    tare_drift_g: float
    static_friction_per_level_Nm: list[float] | None = None  # None without a from-above pass
    static_friction_Nm: float | None = None


@dataclass(frozen=True)
class Results:
    """results.json."""
    k: float
    G: float
    torque_constant_configured_NmA: float
    torque_constant_expected_NmA: float
    asymmetry_percent: float | None  # None with only one direction
    directions: dict[str, DirectionResult]
    warnings: list[str]


@dataclass(frozen=True)
class DirectionFit:
    """One direction's fit, τ = k × τ_command + offset, on the from-below readings."""
    command: np.ndarray  # N·m, every measured row
    torque: np.ndarray  # N·m on the scale, signed like the command
    from_below: np.ndarray  # mask of the rows that go into the fit
    residuals: np.ndarray  # N·m, from-below rows only
    result: DirectionResult
    warnings: list[str]


def fit(rows, arm_length_m, torque_constant_NmA, minimum_scale_readings=None):
    """The Analysis section of instructions/02 on data.csv's Measurements. Returns (Results, DirectionFit per direction).
    Readings averaged from fewer than `minimum_scale_readings` balance readings are flagged as low confidence."""
    fits = {}
    warnings = []
    if minimum_scale_readings and (holds := [row.hold for row in rows if row.scale_samples is not None and row.scale_samples < minimum_scale_readings]):
        warnings.append(f"low confidence: holds {', '.join(map(str, holds))} had fewer than {minimum_scale_readings} balance readings.")
    for direction, sign in DIRECTIONS.items():
        selected = [row for row in rows if row.direction == direction]
        if not selected:
            continue
        direction_fit = fit_direction(selected, sign, arm_length_m, torque_constant_NmA)
        if direction_fit is None:
            warnings.append(f"{direction} skipped: incomplete (needs a tare before and after and {MINIMUM_LEVELS}+ levels).")
            continue
        fits[direction] = direction_fit
        warnings += [f"{direction}: {warning}" for warning in direction_fit.warnings]

    if not fits:
        raise BenchError("No complete direction in this run.")

    k = float(np.mean([direction_fit.result.k for direction_fit in fits.values()]))
    results = Results(
        k=k,
        G=motors.BELT_RATIO * k,
        torque_constant_configured_NmA=torque_constant_NmA,
        torque_constant_expected_NmA=k * torque_constant_NmA,
        asymmetry_percent=100 * abs(fits["positive"].result.k - fits["negative"].result.k) / k if len(fits) == 2 else None,
        directions={direction: direction_fit.result for direction, direction_fit in fits.items()},
        warnings=warnings,
    )
    return results, fits


def fit_direction(rows, sign, arm_length_m, torque_constant_NmA):
    """Fit one direction's rows. None if it's incomplete."""
    tares = np.array([row.scale_g for row in rows if row.approach == "tare"])
    measured = [row for row in rows if row.approach != "tare"]
    command = np.array([row.torque_command_Nm for row in measured])
    from_below = np.array([row.approach == "below" for row in measured], dtype=bool)
    if len(tares) < 2 or len(np.unique(command[from_below])) < MINIMUM_LEVELS:
        return None
    if missing := [row.hold for row in measured if row.iq_setpoint_A is None or row.iq_measured_A is None]:
        raise BenchError(f"holds {', '.join(map(str, missing))} have no iq_setpoint_A or iq_measured_A; every held level needs both.")
    scale = np.array([row.scale_g for row in measured])
    torque = sign * units.grams_to_newtons(scale - np.mean(tares)) * arm_length_m

    warnings = []
    tare_drift = float(np.ptp(tares))
    if tare_drift > TARE_DRIFT_LIMIT_G:
        warnings.append(f"tare drifted {tare_drift:.1f} g. Consider redoing this direction.")
    iq_setpoint = np.array([row.iq_setpoint_A for row in measured])
    current_mismatch = np.max(np.abs(iq_setpoint * torque_constant_NmA - command) / np.abs(command))
    if current_mismatch > CURRENT_MISMATCH_LIMIT:
        warnings.append(
            f"Iq setpoint differs from the command by up to {100 * current_mismatch:.0f}%. "
            "Torque was clipped (current limit or velocity cap); k is wrong."
        )

    below_command, below_torque = command[from_below], torque[from_below]
    k, offset = np.polyfit(below_command, below_torque, 1)
    residuals = below_torque - (k * below_command + offset)
    iq_measured = np.array([row.iq_measured_A for row in measured])
    measured_torque_constant, _ = np.polyfit(iq_measured[from_below], below_torque, 1)

    stiction = static_friction(command, torque, from_below, sign)
    if stiction and min(stiction) < 0:
        warnings.append("from-above readings are below the from-below ones; stiction is unreliable.")
    result = DirectionResult(
        k=float(k),
        offset_Nm=float(offset),
        torque_constant_NmA=float(measured_torque_constant),
        max_residual_Nm=float(np.max(np.abs(residuals))),
        max_residual_percent=float(100 * np.max(np.abs(residuals)) / np.max(np.abs(below_torque))),
        tare_drift_g=tare_drift,
        static_friction_per_level_Nm=stiction or None,
        static_friction_Nm=float(np.mean(stiction)) if stiction else None,
    )
    return DirectionFit(command, torque, from_below, residuals, result, warnings)


def static_friction(command, torque, from_below, sign):
    """Half the from-above minus from-below torque at each level that has both (instructions/02, Analysis step 7)."""
    friction = []
    for index in np.flatnonzero(~from_below):
        matches = from_below & np.isclose(command, command[index])
        if matches.any():
            friction.append(float(0.5 * sign * (torque[index] - torque[matches][0])))
    return friction
