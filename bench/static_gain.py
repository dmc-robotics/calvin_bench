"""Experiment 2: static torque gain. A lever arm on the motor shaft pushes on a kitchen scale.

`record` drives the ODrive over its USB (no Teensy) and prompts for the scale readings.
`analyze` follows the Analysis section of instructions/02-static-torque-gain.md.
"""
import csv
import json
import math
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import odrive
from odrive.enums import AxisState, ControlMode, InputMode
from odrive.utils import backup_config, dump_errors

from bench import runs, units

EXPERIMENT = "static-gain"
DIRECTIONS = {"positive": 1.0, "negative": -1.0}
MOTOR_NODE_IDS = {"left": 1, "right": 2}
CSV_COLUMNS = [
    "direction", "approach", "torque_command_Nm", "scale_g",
    "iq_setpoint_A", "iq_measured_A", "vbus_V", "fet_temperature_C", "motor_temperature_C",
]

ARMING_SECONDS = 0.3
OVERSHOOT_NM = 0.05
OVERSHOOT_SECONDS = 0.5
HOLD_SECONDS = 2.5
SAMPLE_SECONDS = 1.0  # averaged at the end of each hold
LOOP_PERIOD = 0.02
REST_SECONDS = 5.0  # minimum time idle between holds

# The arm is clamped to the shaft: if it slips or misses the scale it spins freely.
MOTION_LIMIT_REV = 0.03
SPEED_LIMIT_REV_PER_S = 0.5
# Torque-mode velocity limiting clamps torque to vel_gain × (vel_limit − vel), so the
# temporary cap must leave headroom at stall or it clips the measurement.
VELOCITY_CAP_HEADROOM = 1.5
VELOCITY_CAP_MAX_REV_PER_S = 5.0
WATCHDOG_TIMEOUT_RANGE_S = (0.05, 0.2)
FET_TEMPERATURE_LIMIT_C = 80.0
MOTOR_TEMPERATURE_LIMIT_C = 60.0

TARE_DRIFT_LIMIT_G = 2.0
CURRENT_MISMATCH_LIMIT = 0.02
MINIMUM_LEVELS = 3

COLORS = {"positive": "#2a78d6", "negative": "#eb6834"}


def record(motor, arm_length, levels, from_above, max_torque):
    highest = max(levels) + (OVERSHOOT_NM if from_above else 0)
    if highest > max_torque:
        raise SystemExit(
            f"Levels reach {highest:.3f} N·m, above --max-torque {max_torque:.3f} N·m. Raise --max-torque deliberately if you mean it."
        )

    print("Connecting to the ODrive over USB...")
    odrive_device = odrive.find_sync(timeout=10)
    axis = odrive_device.axis0
    original_velocity_limit = None
    try:
        stop(axis)
        velocity_cap = check_device(odrive_device, motor, highest)
        print(
            f"ODrive {odrive_device.serial_number:X}, node {axis.config.can.node_id} ({motor}). "
            f"Levels {', '.join(f'{level:.3f}' for level in levels)} N·m, each held {HOLD_SECONDS} s, both directions."
        )
        if input("Arm clamped, scale in place, area clear, e-stop in reach? [y/N] ").strip().lower() != "y":
            raise SystemExit("Aborted.")

        run_directory = runs.create_run_directory(EXPERIMENT, motor)
        (run_directory / "odrive_config.json").write_text(json.dumps(backup_config(odrive_device), indent=2) + "\n")
        runs.write_meta(run_directory, {
            "experiment": EXPERIMENT,
            "motor": motor,
            "arm_length_m": arm_length,
            "levels_Nm": levels,
            "from_above": from_above,
            "overshoot_Nm": OVERSHOOT_NM,
            "hold_s": HOLD_SECONDS,
            "sample_s": SAMPLE_SECONDS,
            "odrive_serial": f"{odrive_device.serial_number:X}",
            "firmware": f"{odrive_device.fw_version_major}.{odrive_device.fw_version_minor}.{odrive_device.fw_version_revision}",
            "node_id": axis.config.can.node_id,
            "torque_constant_NmA": axis.config.motor.torque_constant,
            "velocity_cap_rev_per_s": velocity_cap,
        })
        data_path = run_directory / "data.csv"
        with data_path.open("w", newline="") as file:
            csv.writer(file).writerow(CSV_COLUMNS)
        print(f"Recording to {run_directory}")

        original_velocity_limit = axis.controller.config.vel_limit
        axis.controller.config.vel_limit = velocity_cap

        approaches = ["below", "above"] if from_above else ["below"]
        last_hold_end = 0.0
        for direction, sign in DIRECTIONS.items():
            prompt = f"\n{direction.capitalize()} direction: scale placed so {direction} torque pushes the arm onto it? [y/N] "
            if input(prompt).strip().lower() != "y":
                raise SystemExit("Aborted.")
            record_tare(data_path, direction, axis)
            for approach in approaches:
                for level in levels:
                    torque = sign * level
                    reading = None
                    while reading is None:
                        temperatures = wait_until_cool(axis)
                        time.sleep(max(0.0, last_hold_end + REST_SECONDS - time.monotonic()))
                        iq_setpoint, iq_measured, vbus = hold(odrive_device, torque, approach)
                        last_hold_end = time.monotonic()
                        reading = ask_grams(f"{torque:+.3f} N·m ({approach}): scale reading (g), r to repeat: ", allow_repeat=True)
                    append_row(data_path, [
                        direction, approach, torque, reading, f"{iq_setpoint:.4f}", f"{iq_measured:.4f}", f"{vbus:.3f}",
                        temperatures["fet"], temperatures["motor"],
                    ])
                    print(f"  Iq {iq_measured:+.2f} A, {format_temperatures(temperatures)}")
            record_tare(data_path, direction, axis, again=True)
    finally:
        stop(axis)
        if original_velocity_limit is not None:
            try:
                axis.controller.config.vel_limit = original_velocity_limit
            except Exception as error:
                print(f"Couldn't restore vel_limit ({error}). Reboot the ODrive; don't save its config.")

    print(f"\nDone. Analyze with: bench static-gain analyze {run_directory}")


def check_device(odrive_device, motor, highest_torque):
    """Refuse to run on the wrong or unsafe ODrive. Reads every property `record` uses, before any torque. Returns the velocity cap."""
    axis = odrive_device.axis0
    controller_config = axis.controller.config
    problems = []

    node_id = axis.config.can.node_id
    if node_id != MOTOR_NODE_IDS[motor]:
        problems.append(f"node ID is {node_id}, but {motor} is {MOTOR_NODE_IDS[motor]}. Wrong ODrive?")
    if controller_config.control_mode != ControlMode.TORQUE_CONTROL or controller_config.input_mode != InputMode.PASSTHROUGH:
        problems.append("not set to torque control + passthrough (experiment 1).")
    if not controller_config.enable_torque_mode_vel_limit:
        problems.append("enable_torque_mode_vel_limit is off, so the velocity cap wouldn't apply.")
    velocity_cap = VELOCITY_CAP_HEADROOM * highest_torque / controller_config.vel_gain
    if velocity_cap > VELOCITY_CAP_MAX_REV_PER_S:
        problems.append(f"vel_gain {controller_config.vel_gain:.3f} needs a velocity cap of {velocity_cap:.1f} rev/s to avoid clipping torque.")
    if not axis.config.enable_watchdog:
        problems.append("the watchdog is off (experiment 1 turns it on).")
    elif not WATCHDOG_TIMEOUT_RANGE_S[0] <= axis.config.watchdog_timeout <= WATCHDOG_TIMEOUT_RANGE_S[1]:
        problems.append(f"watchdog_timeout is {axis.config.watchdog_timeout} s, expected {WATCHDOG_TIMEOUT_RANGE_S[0]}–{WATCHDOG_TIMEOUT_RANGE_S[1]} s.")

    read_signals(odrive_device)
    read_motion(axis)
    temperatures(axis)
    axis.config.motor.torque_constant

    if problems:
        raise SystemExit("Not starting:\n  - " + "\n  - ".join(problems))
    return velocity_cap


def record_tare(data_path, direction, axis, again=False):
    grams = ask_grams(f"Motor idle. Tare reading{' again' if again else ''} (g): ")
    current_temperatures = temperatures(axis)
    append_row(data_path, [direction, "tare", 0, grams, "", "", "", current_temperatures["fet"], current_temperatures["motor"]])


def append_row(data_path, row):
    with data_path.open("a", newline="") as file:
        csv.writer(file).writerow(row)


def hold(odrive_device, torque, approach):
    """Arm, hold `torque` for HOLD_SECONDS, disarm. Returns mean (Iq setpoint, Iq measured, vbus) over the last SAMPLE_SECONDS."""
    axis = odrive_device.axis0
    axis.controller.input_torque = 0
    axis.watchdog_feed()
    axis.requested_state = AxisState.CLOSED_LOOP_CONTROL
    end = time.monotonic() + ARMING_SECONDS
    while time.monotonic() < end:
        axis.watchdog_feed()
        time.sleep(LOOP_PERIOD)
    check_closed_loop(odrive_device)
    start_position, _ = read_motion(axis)

    if approach == "above":
        axis.controller.input_torque = torque + math.copysign(OVERSHOOT_NM, torque)
        watch(odrive_device, start_position, OVERSHOOT_SECONDS)
    axis.controller.input_torque = torque
    watch(odrive_device, start_position, HOLD_SECONDS - SAMPLE_SECONDS)
    samples = watch(odrive_device, start_position, SAMPLE_SECONDS, sample=True)
    check_closed_loop(odrive_device)
    stop(axis)
    return np.mean(samples, axis=0)


def watch(odrive_device, start_position, seconds, sample=False):
    """Feed the watchdog and stop on shaft motion for `seconds`. Returns the signal samples if `sample`."""
    axis = odrive_device.axis0
    samples = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        axis.watchdog_feed()
        position, velocity = read_motion(axis)
        if abs(position - start_position) > MOTION_LIMIT_REV or abs(velocity) > SPEED_LIMIT_REV_PER_S:
            stop(axis)
            raise SystemExit("The shaft moved during the hold: the arm slipped or missed the scale. Motor idled.")
        if sample:
            samples.append(read_signals(odrive_device))
        time.sleep(LOOP_PERIOD)
    return samples


def read_motion(axis):
    return axis.pos_estimate, axis.vel_estimate


def read_signals(odrive_device):
    foc = odrive_device.axis0.motor.foc
    return foc.Iq_setpoint, foc.Iq_measured, odrive_device.vbus_voltage


def check_closed_loop(odrive_device):
    if odrive_device.axis0.current_state != AxisState.CLOSED_LOOP_CONTROL:
        stop(odrive_device.axis0)
        dump_errors(odrive_device)
        raise SystemExit("The axis isn't in closed loop. Clear the errors and rerun.")


def stop(axis):
    try:
        axis.requested_state = AxisState.IDLE
    except Exception as error:
        print(f"Couldn't idle the axis ({error}). Cut power.")
    try:
        axis.controller.input_torque = 0
    except Exception as error:
        print(f"Couldn't zero the torque command ({error}).")


def temperatures(axis):
    motor_thermistor = axis.motor.motor_thermistor
    return {
        "fet": round(axis.motor.fet_thermistor.temperature, 1),
        "motor": round(motor_thermistor.temperature, 1) if motor_thermistor.config.enabled else None,
    }


def wait_until_cool(axis):
    while True:
        current = temperatures(axis)
        too_hot = current["fet"] > FET_TEMPERATURE_LIMIT_C or (
            current["motor"] is not None and current["motor"] > MOTOR_TEMPERATURE_LIMIT_C
        )
        if not too_hot:
            return current
        input(f"Too hot ({format_temperatures(current)}). Let it cool, then press Enter.")


def format_temperatures(temperatures):
    motor = "n/a" if temperatures["motor"] is None else f"{temperatures['motor']:.0f} °C"
    return f"FET {temperatures['fet']:.0f} °C, motor {motor}"


def ask_grams(prompt, allow_repeat=False):
    while True:
        answer = input(prompt).strip().lower()
        if allow_repeat and answer == "r":
            return None
        try:
            grams = float(answer)
        except ValueError:
            grams = math.nan
        if math.isfinite(grams):
            return grams
        print("  Enter a number in grams" + (", or r." if allow_repeat else "."))


def analyze(run_directory, show=True):
    run_directory = Path(run_directory)
    meta = runs.read_meta(run_directory)
    with (run_directory / "data.csv").open() as file:
        rows = list(csv.DictReader(file))
    arm_length = meta["arm_length_m"]
    torque_constant = meta["torque_constant_NmA"]

    fits = {}
    for direction, sign in DIRECTIONS.items():
        selected = [row for row in rows if row["direction"] == direction]
        if not selected:
            continue
        tares = [float(row["scale_g"]) for row in selected if row["approach"] == "tare"]
        measured = [row for row in selected if row["approach"] != "tare"]
        command = np.array([float(row["torque_command_Nm"]) for row in measured])
        if len(tares) < 2 or len(np.unique(command)) < MINIMUM_LEVELS:
            print(f"Skipping {direction}: incomplete (needs a tare before and after and {MINIMUM_LEVELS}+ levels).")
            continue

        scale = np.array([float(row["scale_g"]) for row in measured])
        iq_setpoint = np.array([float(row["iq_setpoint_A"]) for row in measured])
        iq_measured = np.array([float(row["iq_measured_A"]) for row in measured])
        from_below = np.array([row["approach"] == "below" for row in measured])

        tare_drift = max(tares) - min(tares)
        if tare_drift > TARE_DRIFT_LIMIT_G:
            print(f"Warning: {direction} tare drifted {tare_drift:.1f} g. Consider redoing this direction.")
        current_mismatch = np.max(np.abs(iq_setpoint * torque_constant - command) / np.abs(command))
        if current_mismatch > CURRENT_MISMATCH_LIMIT:
            print(
                f"Warning: {direction} Iq setpoint differs from the command by up to {100 * current_mismatch:.0f}%. "
                "Torque was clipped (current limit or velocity cap); k is wrong."
            )
        torque = sign * units.grams_to_newtons(scale - np.mean(tares)) * arm_length

        k, offset = np.polyfit(command[from_below], torque[from_below], 1)
        residuals = torque[from_below] - (k * command[from_below] + offset)
        measured_torque_constant, _ = np.polyfit(iq_measured[from_below], torque[from_below], 1)
        summary = {
            "k": float(k),
            "offset_Nm": float(offset),
            "torque_constant_NmA": float(measured_torque_constant),
            "max_residual_Nm": float(np.max(np.abs(residuals))),
            "max_residual_percent": float(100 * np.max(np.abs(residuals)) / np.max(np.abs(torque[from_below]))),
            "tare_drift_g": float(tare_drift),
        }
        if not from_below.all():
            static_friction = []
            for index in np.flatnonzero(~from_below):
                matches = from_below & np.isclose(command, command[index])
                if matches.any():
                    static_friction.append(float(0.5 * sign * (torque[index] - torque[matches][0])))
            if any(value < 0 for value in static_friction):
                print(f"Warning: {direction} has from-above readings below the from-below ones; stiction is unreliable.")
            summary["static_friction_per_level_Nm"] = static_friction
            summary["static_friction_Nm"] = float(np.mean(static_friction))
        fits[direction] = {
            "summary": summary,
            "command": command,
            "torque": torque,
            "from_below": from_below,
            "residuals": residuals,
        }

    if not fits:
        raise SystemExit("No complete direction in this run.")

    k = float(np.mean([fit["summary"]["k"] for fit in fits.values()]))
    results = {
        "k": k,
        "G": units.BELT_RATIO * k,
        "torque_constant_configured_NmA": torque_constant,
        "torque_constant_expected_NmA": k * torque_constant,
    }
    if len(fits) == 2:
        results["asymmetry_percent"] = 100 * abs(fits["positive"]["summary"]["k"] - fits["negative"]["summary"]["k"]) / k
    results["directions"] = {direction: fit["summary"] for direction, fit in fits.items()}
    (run_directory / "results.json").write_text(json.dumps(results, indent=2) + "\n")

    print_report(run_directory, arm_length, fits, results)
    plot(run_directory, fits, results, show)


def print_report(run_directory, arm_length, fits, results):
    print(f"{run_directory.name}   L = {arm_length:.3f} m\n")
    print(f"{'direction':<10} {'k':>6} {'offset':>13} {'Kt':>13} {'max residual':>20} {'stiction':>13}")
    for direction, fit in fits.items():
        summary = fit["summary"]
        stiction = f"{1000 * summary['static_friction_Nm']:.1f} mN·m" if "static_friction_Nm" in summary else "—"
        print(
            f"{direction:<10} {summary['k']:>6.3f} {1000 * summary['offset_Nm']:>+8.1f} mN·m"
            f" {summary['torque_constant_NmA']:>8.4f} N·m/A"
            f" {1000 * summary['max_residual_Nm']:>8.1f} mN·m ({summary['max_residual_percent']:.1f}%)"
            f" {stiction:>13}"
        )
    print()
    if "asymmetry_percent" in results:
        print(f"k = {results['k']:.3f}  (asymmetry {results['asymmetry_percent']:.1f}%)")
    else:
        print(f"k = {results['k']:.3f}  (single direction only)")
    print(f"G = {units.BELT_RATIO:g} × k = {results['G']:.3f}")
    print(
        f"Kt expected k × {results['torque_constant_configured_NmA']:.4f} (configured)"
        f" = {results['torque_constant_expected_NmA']:.4f} N·m/A"
    )


def plot(run_directory, fits, results, show):
    figure, (fit_axes, residual_axes) = plt.subplots(
        2, 1, sharex=True, figsize=(7, 7), height_ratios=[3, 1], layout="constrained"
    )
    limit = 1.1 * max(np.max(np.abs(fit["command"])) for fit in fits.values())
    fit_axes.plot([-limit, limit], [-limit, limit], color="#999999", linestyle="--", linewidth=1, label="ideal (k = 1)")

    for direction, fit in fits.items():
        color = COLORS[direction]
        below = fit["from_below"]
        k, offset = fit["summary"]["k"], fit["summary"]["offset_Nm"]
        span = np.array([fit["command"][below].min(), fit["command"][below].max()])
        fit_axes.plot(span, k * span + offset, color=color, linewidth=2)
        fit_axes.plot(
            fit["command"][below], fit["torque"][below], "o", color=color, markersize=8,
            markeredgecolor="white", label=f"{direction}: k = {k:.3f}",
        )
        if not below.all():
            fit_axes.plot(
                fit["command"][~below], fit["torque"][~below], "o", color=color, markersize=8,
                markerfacecolor="none", label=f"{direction}, from above",
            )
        residual_axes.plot(fit["command"][below], 1000 * fit["residuals"], "o", color=color, markersize=8, markeredgecolor="white")

    residual_axes.axhline(0, color="#999999", linewidth=1)
    fit_axes.set_title(f"{run_directory.name}\nk = {results['k']:.3f}, G = {results['G']:.3f}")
    fit_axes.set_ylabel("Measured torque (N·m, motor side)")
    fit_axes.legend(loc="upper left", frameon=False)
    residual_axes.set_ylabel("Residual (mN·m)")
    residual_axes.set_xlabel("Commanded torque (N·m, motor side)")
    for axes in (fit_axes, residual_axes):
        axes.grid(alpha=0.3)
        axes.spines[["top", "right"]].set_visible(False)

    figure.savefig(run_directory / "plot.png", dpi=150)
    print(f"\nPlot: {run_directory / 'plot.png'}")
    if show:
        plt.show()
