"""The `bench` command line tool: `bench record <experiment> ...` and `bench analyze <run folder>`."""
import argparse

from bench.errors import BenchError
from bench.experiments import static_gain
from bench.hardware.ohaus_adventurer import OhausError
from bench.runs import Run

EXPERIMENTS = {experiment.NAME: experiment for experiment in (static_gain,)}


def main():
    parser = build_parser()
    arguments = parser.parse_args()

    try:
        match arguments.command:
            case "record":
                experiment = EXPERIMENTS[arguments.experiment]
                experiment.record(arguments)
            case "analyze":
                run = Run(arguments.run_directory)
                analyze(run, show=not arguments.no_show)
    except (BenchError, OhausError) as error:
        parser.exit(1, f"{error}\n")
    except KeyboardInterrupt:
        if arguments.command == "record":
            parser.exit(1, "\nInterrupted. Motor idled.\n")
        parser.exit(1, "\n")


def build_parser():
    parser = argparse.ArgumentParser(prog="bench", description="Calvin actuator characterization")
    subcommands = parser.add_subparsers(dest="command", required=True)

    record_parser = subcommands.add_parser(
        "record",
        help="record an experiment into a new run folder",
    )
    experiment_parsers = record_parser.add_subparsers(dest="experiment", required=True)
    for name, experiment in EXPERIMENTS.items():
        experiment_parser = experiment_parsers.add_parser(name, help=experiment.DESCRIPTION)
        experiment.add_arguments(experiment_parser)

    analyze_parser = subcommands.add_parser(
        "analyze",
        help="analyze a run folder (its meta.json names the experiment)",
    )
    analyze_parser.add_argument(
        "run_directory",
        help = "a run folder (any folder with a meta.json written by bench record)",
    )
    analyze_parser.add_argument(
        "--no-show",
        action = "store_true",
        help   = "save the plot without opening a window",
    )

    return parser


def analyze(run, show):
    name = run.meta["experiment"]
    if name not in EXPERIMENTS:
        raise BenchError(f"{run.name} is a {name!r} run, which bench can't analyze yet.")
    EXPERIMENTS[name].analyze(run, show=show)


if __name__ == "__main__":
    main()
