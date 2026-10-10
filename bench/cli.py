"""The `bench` command line tool."""
import argparse
import math

DEFAULT_STATIC_GAIN_LEVELS = [0.05, 0.10, 0.15, 0.20, 0.25]


def positive_number(text):
    value = float(text)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError(f"{text} isn't a positive number")
    return value


def parse_levels(text):
    levels = [positive_number(level) for level in text.split(",")]
    if len(set(levels)) < 3:
        raise argparse.ArgumentTypeError("need at least 3 distinct levels for a line fit")
    return levels


def arm_length(text):
    value = positive_number(text)
    if value >= 1:
        raise argparse.ArgumentTypeError("arm length is in meters, e.g. 0.200")
    return value


def main():
    parser = argparse.ArgumentParser(prog="bench", description="Calvin actuator characterization")
    subcommands = parser.add_subparsers(dest="command", required=True)

    run_parser = subcommands.add_parser("run", help="run an experiment on the bench (M3)")
    run_parser.add_argument("experiment")

    plot_parser = subcommands.add_parser("plot", help="plot a recorded run (M3)")
    plot_parser.add_argument("run_directory")

    static_gain_parser = subcommands.add_parser("static-gain", help="experiment 2: static torque gain (lever arm + scale)")
    static_gain_actions = static_gain_parser.add_subparsers(dest="action", required=True)

    record_parser = static_gain_actions.add_parser("record", help="guided recording over the ODrive's USB")
    record_parser.add_argument("--motor", required=True, choices=["left", "right"])
    record_parser.add_argument("--arm-length", type=arm_length, required=True, help="shaft center to scale contact (m)")
    record_parser.add_argument(
        "--levels", type=parse_levels, default=DEFAULT_STATIC_GAIN_LEVELS,
        help="comma-separated torque magnitudes, N·m motor-side (default: %(default)s)",
    )
    record_parser.add_argument("--from-above", action="store_true", help="add a pass approaching each level from above (stiction)")
    record_parser.add_argument("--max-torque", type=positive_number, default=0.25, help="refuse levels above this, N·m (default: %(default)s)")

    analyze_parser = static_gain_actions.add_parser("analyze", help="fit k and G, write results.json and plot.png")
    analyze_parser.add_argument("run_directory")
    analyze_parser.add_argument("--no-show", action="store_true", help="save the plot without opening a window")

    arguments = parser.parse_args()

    if arguments.command == "static-gain":
        from bench import static_gain

        if arguments.action == "record":
            try:
                static_gain.record(arguments.motor, arguments.arm_length, arguments.levels, arguments.from_above, arguments.max_torque)
            except KeyboardInterrupt:
                parser.exit(1, "\nInterrupted. Motor idled.\n")
        else:
            static_gain.analyze(arguments.run_directory, show=not arguments.no_show)
        return

    parser.exit(1, f"bench {arguments.command}: not implemented yet (see PLAN.md, M3)\n")


if __name__ == "__main__":
    main()
