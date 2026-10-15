# The Calvin Robot Project: Calvin Bench

**WARNING: This software is unsafe in its current state. Do not run the experiments as they are AI generated stubs.**

Calvin is a two-wheeled self-balancing robot with on board AI processing and computer vision. The code for the project is broken into separate repos:

- **Calvin Instinctus**: Code for the Teensy 4.1. This provides for Calvin's low level functionality and safety.
- **Calvin Cogitator**: Code that runs on the Jetson. This is Calvin's high level thought.
- **Calvin Explorator**: A native macOS app for monitoring Calvin from a Mac.
- **Calvin Bench**: This repo. Measures each drive actuator (Teensy → ODrive S1 → motor → belt → wheel) and produces `actuator.yaml`, the input to Calvin's balance controller.

## Usage

Python 3.15, managed with [uv](https://docs.astral.sh/uv/):

```sh
uv sync                  # install
uv run bench --help      # list commands and experiments
uv run pytest            # tests (fake hardware, nothing moves)
```

Each experiment has step-by-step instructions in [`instructions/`](instructions/README.md), including the safety checklist to go through before every session. Read the experiment's file before recording.

**Record** a run into a new folder under `runs/`:

```sh
uv run bench record static-gain --motor left --arm-length 0.200
```

`uv run bench record <experiment> --help` lists an experiment's options. Static gain, for example, takes `--levels`, `--from-above`, `--max-torque`, and `--scale <port>` or `--no-scale` to type the balance readings by hand.

**Analyze** a run. Its `meta.json` says which experiment it was; the results (`results.json`, `plot.png`) are written into the run folder:

```sh
uv run bench analyze runs/<run folder>          # add --no-show to skip the plot window
```

**Firmware:** experiments that use the Teensy need the bench sketch flashed in place of instinctus: `cd firmware/bench && grot build && grot load`. Static gain doesn't; it talks to the ODrive over USB. Not implemented yet.

