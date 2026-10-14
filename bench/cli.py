"""The `bench` command line tool: `bench record <experiment> ...` and `bench analyze <run folder>`."""
import argparse

from bench.errors import BenchError
from bench.experiments import static_gain
from bench.hardware.ohaus_adventurer import OhausError
from bench.runs import Run

EXPERIMENTS = {experiment.NAME: experiment for experiment in (static_gain,)}


def main():
    parser = argparse.ArgumentParser(prog="bench", description="Calvin actuator characterization")
    subcommands = parser.add_subparsers(dest="command", required=True)

    record_parser = subcommands.add_parser("record", help="record an experiment into a new run folder")
    experiment_parsers = record_parser.add_subparsers(dest="experiment", required=True)
    for name, experiment in EXPERIMENTS.items():
        experiment.add_arguments(experiment_parsers.add_parser(name, help=experiment.DESCRIPTION))

    analyze_parser = subcommands.add_parser("analyze", help="analyze a run folder (its meta.json names the experiment)")
    analyze_parser.add_argument("run_directory")
    analyze_parser.add_argument("--no-show", action="store_true", help="save the plot without opening a window")

    arguments = parser.parse_args()

    try:
        if arguments.command == "record":
            EXPERIMENTS[arguments.experiment].record(arguments)
        else:
            analyze(Run(arguments.run_directory), show=not arguments.no_show)
    except (BenchError, OhausError) as error:
        parser.exit(1, f"{error}\n")
    except KeyboardInterrupt:
        parser.exit(1, "\nInterrupted. Motor idled.\n" if arguments.command == "record" else "\n")


def analyze(run, show):
    name = run.meta["experiment"]
    if name not in EXPERIMENTS:
        raise BenchError(f"{run.name} is a {name!r} run, which bench can't analyze yet.")
    EXPERIMENTS[name].analyze(run, show=show)


if __name__ == "__main__":
    main()
