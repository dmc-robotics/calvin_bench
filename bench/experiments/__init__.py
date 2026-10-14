"""One package per experiment, each with the same entry points, which the CLI calls:

  NAME, DESCRIPTION
  add_arguments(parser)   its `bench record <NAME>` options
  record(arguments)       record a run into runs/
  analyze(run, show)      fit a run folder, write results.json, print the report and plot

Inside, by convention: data.py (settings and row types), procedure.py (recording), analysis.py (pure fitting)
and report.py (printing and plotting). Hardware lives in bench.hardware, run folders in bench.runs.
"""
