"""The `bench` command line tool."""
import argparse


def main():
    parser = argparse.ArgumentParser(prog="bench", description="Calvin actuator characterization")
    subcommands = parser.add_subparsers(dest="command", required=True)

    run_parser = subcommands.add_parser("run", help="run an experiment on the bench (M3)")
    run_parser.add_argument("experiment")

    plot_parser = subcommands.add_parser("plot", help="plot a recorded run (M3)")
    plot_parser.add_argument("run_directory")

    arguments = parser.parse_args()
    parser.exit(1, f"bench {arguments.command}: not implemented yet (see PLAN.md, M3)\n")


if __name__ == "__main__":
    main()
