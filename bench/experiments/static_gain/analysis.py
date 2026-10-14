"""Experiment 2's analysis (instructions/02-static-torque-gain.md, Analysis). Pure: data.csv rows in, results out."""
from dataclasses import dataclass

import numpy as np

from bench import units
from bench.experiments.static_gain.data import DIRECTIONS

TARE_DRIFT_LIMIT_G = 2.0
CURRENT_MISMATCH_LIMIT = 0.02
MINIMUM_LEVELS = 3


@dataclass
class DirectionFit:
    """One direction's fit, τ = k × τ_command + offset, on the from-below readings."""
    command: np.ndarray  # N·m, every measured row
    torque: np.ndarray  # N·m on the scale, signed like the command
    from_below: np.ndarray  # mask of the rows that go into the fit
    residuals: np.ndarray  # N·m, from-below rows only
    summary: dict  # this direction's entry in results.json
    warnings: list


def fit(rows, arm_length_m, torque_constant_NmA):
    """The Analysis section of instructions/02 on data.csv rows. Returns (results for results.json, DirectionFit per direction)."""
    fits = {}
    warnings = []
    for direction, sign in DIRECTIONS.items():
        selected = [row for row in rows if row["direction"] == direction]
        if not selected:
            continue
        direction_fit = fit_direction(selected, sign, arm_length_m, torque_constant_NmA)
        if direction_fit is None:
            warnings.append(f"{direction} skipped: incomplete (needs a tare before and after and {MINIMUM_LEVELS}+ levels).")
            continue
        fits[direction] = direction_fit
        warnings += [f"{direction}: {warning}" for warning in direction_fit.warnings]

    if not fits:
        raise SystemExit("No complete direction in this run.")

    k = float(np.mean([direction_fit.summary["k"] for direction_fit in fits.values()]))
    results = {
        "k": k,
        "G": units.BELT_RATIO * k,
        "torque_constant_configured_NmA": torque_constant_NmA,
        "torque_constant_expected_NmA": k * torque_constant_NmA,
    }
    if len(fits) == 2:
        results["asymmetry_percent"] = 100 * abs(fits["positive"].summary["k"] - fits["negative"].summary["k"]) / k
    results["directions"] = {direction: direction_fit.summary for direction, direction_fit in fits.items()}
    results["warnings"] = warnings
    return results, fits


def fit_direction(rows, sign, arm_length_m, torque_constant_NmA):
    """Fit one direction's rows. None if it's incomplete."""
    tares = column([row for row in rows if row["approach"] == "tare"], "scale_g")
    measured = [row for row in rows if row["approach"] != "tare"]
    command = column(measured, "torque_command_Nm")
    if len(tares) < 2 or len(np.unique(command)) < MINIMUM_LEVELS:
        return None
    from_below = np.array([row["approach"] == "below" for row in measured])
    torque = sign * units.grams_to_newtons(column(measured, "scale_g") - np.mean(tares)) * arm_length_m

    warnings = []
    tare_drift = float(np.ptp(tares))
    if tare_drift > TARE_DRIFT_LIMIT_G:
        warnings.append(f"tare drifted {tare_drift:.1f} g. Consider redoing this direction.")
    current_mismatch = np.max(np.abs(column(measured, "iq_setpoint_A") * torque_constant_NmA - command) / np.abs(command))
    if current_mismatch > CURRENT_MISMATCH_LIMIT:
        warnings.append(
            f"Iq setpoint differs from the command by up to {100 * current_mismatch:.0f}%. "
            "Torque was clipped (current limit or velocity cap); k is wrong."
        )

    below_command, below_torque = command[from_below], torque[from_below]
    k, offset = np.polyfit(below_command, below_torque, 1)
    residuals = below_torque - (k * below_command + offset)
    measured_torque_constant, _ = np.polyfit(column(measured, "iq_measured_A")[from_below], below_torque, 1)
    summary = {
        "k": float(k),
        "offset_Nm": float(offset),
        "torque_constant_NmA": float(measured_torque_constant),
        "max_residual_Nm": float(np.max(np.abs(residuals))),
        "max_residual_percent": float(100 * np.max(np.abs(residuals)) / np.max(np.abs(below_torque))),
        "tare_drift_g": tare_drift,
    }

    stiction = static_friction(command, torque, from_below, sign)
    if stiction:
        if min(stiction) < 0:
            warnings.append("from-above readings are below the from-below ones; stiction is unreliable.")
        summary["static_friction_per_level_Nm"] = stiction
        summary["static_friction_Nm"] = float(np.mean(stiction))
    return DirectionFit(command, torque, from_below, residuals, summary, warnings)


def static_friction(command, torque, from_below, sign):
    """Half the from-above minus from-below torque at each level that has both (instructions/02, Analysis step 7)."""
    friction = []
    for index in np.flatnonzero(~from_below):
        matches = from_below & np.isclose(command, command[index])
        if matches.any():
            friction.append(float(0.5 * sign * (torque[index] - torque[matches][0])))
    return friction


def column(rows, name):
    return np.array([float(row[name]) for row in rows])
