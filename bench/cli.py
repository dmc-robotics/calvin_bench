"""The `bench` command line tool: `bench record <experiment> ...` and `bench analyze <run folder>`."""
import argparse

from bench.experiments import static_gain
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

    if arguments.command == "record":
        try:
            EXPERIMENTS[arguments.experiment].record(arguments)
        except KeyboardInterrupt:
            parser.exit(1, "\nInterrupted. Motor idled.\n")
    else:
        run = Run(arguments.run_directory)
        EXPERIMENTS[run.meta["experiment"]].analyze(run, show=not arguments.no_show)


if __name__ == "__main__":
    main()
