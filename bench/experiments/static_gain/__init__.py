"""Experiment 2: static torque gain (instructions/02-static-torque-gain.md).

A lever arm on the motor shaft pushes on the OHAUS balance while the ODrive holds torque levels; the fit gives k, then G = 4 × k.
  data.py       Settings and the rows a run holds
  procedure.py  recording: the guided steps
  analysis.py   fitting (pure: rows in, results out)
  report.py     the printed report and plot
"""
import argparse

from bench.arguments import positive_number
from bench.experiments.static_gain import analysis, procedure, report
from bench.experiments.static_gain.data import DEFAULT_LEVELS_NM, DEFAULT_MAX_TORQUE_NM, EXPERIMENT, Settings
from bench.hardware.odrive_usb import NODE_IDS
from bench.hardware.scale import DEFAULT_PORT

NAME = EXPERIMENT
DESCRIPTION = "experiment 2: static torque gain (lever arm + scale), over the ODrive's USB"


def add_arguments(parser):
    parser.add_argument("--motor", required=True, choices=list(NODE_IDS))
    parser.add_argument("--arm-length", type=arm_length, required=True, help="shaft center to scale contact (m)")
    parser.add_argument(
        "--levels", type=levels, default=DEFAULT_LEVELS_NM,
        help="comma-separated torque magnitudes, N·m motor-side (default: %(default)s)",
    )
    parser.add_argument("--from-above", action="store_true", help="add a pass approaching each level from above (stiction)")
    parser.add_argument("--max-torque", type=positive_number, default=DEFAULT_MAX_TORQUE_NM, help="refuse levels above this, N·m (default: %(default)s)")
    parser.add_argument("--scale", metavar="PORT", default=DEFAULT_PORT, help="the OHAUS balance's port (default: %(default)s)")
    parser.add_argument("--no-scale", action="store_true", help="type the scale readings instead")


def record(arguments):
    procedure.record(Settings(
        motor=arguments.motor,
        arm_length_m=arguments.arm_length,
        levels_Nm=tuple(arguments.levels),
        from_above=arguments.from_above,
        max_torque_Nm=arguments.max_torque,
        scale_port=None if arguments.no_scale else arguments.scale,
    ))


def analyze(run, show=True):
    meta = run.meta
    arm_length_m = meta["settings"]["arm_length_m"]
    results, fits = analysis.fit(run.rows("data"), arm_length_m, meta["odrive"]["torque_constant_NmA"])
    run.write_json("results", results)
    report.print_report(run.name, arm_length_m, results)
    report.plot(run, fits, results, show)


def levels(text):
    values = [positive_number(level) for level in text.split(",")]
    if len(set(values)) < analysis.MINIMUM_LEVELS:
        raise argparse.ArgumentTypeError(f"need at least {analysis.MINIMUM_LEVELS} distinct levels for a line fit")
    return values


def arm_length(text):
    value = positive_number(text)
    if value >= 1:
        raise argparse.ArgumentTypeError("arm length is in meters, e.g. 0.200")
    return value
