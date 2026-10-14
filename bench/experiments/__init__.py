"""One package per experiment. The CLI calls only these entry points, so they are the whole contract:

  NAME, DESCRIPTION
  add_arguments(parser)   its `bench record <NAME>` options
  record(arguments)       record a run into runs/
  analyze(run, show)      fit a run folder, write results.json, print the report and plot

How a package splits into files is up to it; static_gain's split is one way, not a template.
"""
