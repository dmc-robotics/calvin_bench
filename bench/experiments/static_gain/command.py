"""The CLI entry points for static gain: `bench record static-gain` flags, and record/analyze."""
from dataclasses import asdict, replace

from bench.experiments.static_gain import analysis, procedure, report
from bench.experiments.static_gain.data import DEFAULT_ARM_LENGTH_M, DEFAULT_LEVELS_NM, DEFAULT_MAX_TORQUE_NM, NAME, Measurement, Settings
from bench.motors import NODE_IDS

# Safe to hard-code: macOS names the port after the serial number of the FTDI chip inside the balance,
# so it stays the same across replugs, reboots and USB sockets.
DEFAULT_SCALE_PORT = "/dev/cu.usbserial-DN04KNBY"
DESCRIPTION = "experiment 2: static torque gain (lever arm + scale), over the ODrive's USB"


def add_arguments(parser):
    parser.add_argument(
        "--motor",
        required = True,
        choices  = list(NODE_IDS),
    )
    parser.add_argument(
        "--arm-length",
        type    = float,
        default = DEFAULT_ARM_LENGTH_M,
        help    = "shaft center to scale contact, m (default: %(default)s)",
    )
    parser.add_argument(
        "--levels",
        type    = levels,
        default = DEFAULT_LEVELS_NM,
        help    = "comma-separated torque magnitudes, N·m motor-side (default: %(default)s)",
    )
    parser.add_argument(
        "--from-above",
        action = "store_true",
        help   = "add a pass approaching each level from above (stiction)",
    )
    parser.add_argument(
        "--max-torque",
        type    = float,
        default = DEFAULT_MAX_TORQUE_NM,
        help    = "refuse levels above this, N·m (default: %(default)s)",
    )
    parser.add_argument(
        "--scale",
        metavar = "PORT",
        default = DEFAULT_SCALE_PORT,
        help    = "the OHAUS balance's port (default: %(default)s)",
    )
    parser.add_argument(
        "--no-scale",
        action = "store_true",
        help   = "type the scale readings instead",
    )


def record(arguments):
    procedure.record(Settings(
        motor         = arguments.motor,
        arm_length_m  = arguments.arm_length,
        levels_Nm     = arguments.levels,
        from_above    = arguments.from_above,
        max_torque_Nm = arguments.max_torque,
        scale_port    = None if arguments.no_scale else arguments.scale,
    ))


def analyze(run, show=True):
    meta = run.meta
    settings = meta["settings"]
    arm_length_m = settings["arm_length_m"]
    results, fits = analysis.fit(
        run.rows("data", Measurement), arm_length_m, meta["odrive"]["torque_constant_NmA"], settings.get("minimum_scale_readings"),
    )
    if not run.finished:
        results = replace(results, warnings=["the recording didn't finish (no finished.json).", *results.warnings])
    run.write_json("results", asdict(results))
    report.print_report(run.name, arm_length_m, results)
    report.plot(run, fits, results, show)


def levels(text):
    return tuple(float(level) for level in text.split(","))
