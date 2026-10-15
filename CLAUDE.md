# Calvin Bench

Calvin is a robotics project contained in `~/code/robotics/calvin/`. See `~/code/robotics/calvin/CLAUDE.md` for project level information. This file is for `calvin_bench` infromation only.

Actuator characterization. The bench measures each drive actuator (Teensy CAN command → ODrive S1 → D5312s → 4:1 belt → wheel) and produces `actuator.yaml`, the input to the first LQR design and later an RL policy. This repo only measures; controller design happens elsewhere.

**Read `PLAN.md` next.** It has the current status, the milestones (M0–M5) and the decisions. Update it as you work: tick milestones, record new decisions and any interface details you settle (protocol, CSV columns, `actuator.yaml` fields). Step-by-step experiment procedures are in `instructions/`.

## Layout

```
calvin_bench/
  PLAN.md              status, milestones, decisions
  instructions/        how to run each experiment
  firmware/bench/      Teensy bench sketch (bench.ino + src/), flashed in place of instinctus
  bench/               Python package: the `bench` CLI, hardware drivers, experiments, run folders, units
  tests/               pytest: fake hardware (tests/fakes.py), driver safety, procedures end to end, analyses
  odrive/              ODrive config backups (the frozen baseline; committed)
  runs/                recorded runs (gitignored)
```

## Firmware

- The bench sketch uses `InstinctusCore` (in `../calvin_instinctus/InstinctusCore/`, symlinked into `~/code/arduino/libraries/`) for the ODrive CAN driver, safety supervisor and recorder. Bench-only pieces (waveform player, USB text protocol) live in `firmware/bench/src/`.
- Build and flash: `cd firmware/bench && grot build && grot load`. Rebuild after any `InstinctusCore` edit.
- Teensy RAM holds only ~6 s of 1 kHz two-motor data, so the sketch **streams samples to the host during a run** rather than storing whole runs.
- ODrive CAN protocol: https://docs.odriverobotics.com/v/latest/manual/can-protocol.html. Arbitration ID = `node_id << 5 | cmd_id`; little-endian float32 payloads. Firmware keeps ODrive's units; **all conversion to SI and wheel side happens in `bench/units.py`**.

## Python

- Python 3.15 (`.python-version`), managed with uv: `uv sync`, then `uv run bench --help`. Tests: `uv run pytest`.
- Commands: `bench record <experiment> ...` writes a run folder; `bench analyze <run folder>` picks the analysis from its `meta.json`.
- Layers, each with one job; keep them apart:
  - `bench/hardware/`: drivers, each module and class named for its hardware ("scale" stays the generic word and variable name). `odrive_usb.py` owns motor safety (idle on every exit, watchdog fed, motion abort, config checks); `ohaus_adventurer.py` is the balance; `link.py` the Teensy (M3).
  - `bench/experiments/<name>/`: one package per experiment. Its contract is the entry points the CLI calls (`NAME`, `DESCRIPTION`, `add_arguments`, `record`, `analyze`; see `bench/experiments/__init__.py`); how it splits into files is up to it. 
  - `bench/runs.py` is the only code that touches run folders; `bench/console.py` asks every question; `bench/units.py` does every unit conversion.
- New experiment: add a package with those entry points and list it in `bench/cli.py`. Add tests against `tests/fakes.py`.

## Experiments
See `instructions` for details. 

### Static Gain (#2)
`0data.py`: Settings, saved whole in meta.json, and the row dataclasses, whose fields are the CSV columns
`procedure.py`: the steps; no safety logic of its own
`analysis.py`: pure: rows in, results with warnings out
`report.py`: printing, plots
  
## Scale
OHAUS Adventurer AX8201/E, 0.1 g, read by `bench record static-gain` (`--no-scale` to type readings). The driver is `OhausAdventurer` in `bench/hardware/ohaus_adventurer.py`. It's self-contained (pyserial only, raises `OhausError`, which the CLI catches next to `BenchError`) so other projects can copy it; keep it free of `bench` imports. It covers the manual's whole command table; its docstring lists every reply. The manual and datasheet are in `docs/`.

- USB Device with an internal FTDI FT230X serial bridge - the port is`/dev/cu.usbserial-DN04KNBY` (the chip's serial number, so it's fixed; `DEFAULT_SCALE_PORT` in `static_gain`), 9600 baud, 8N1.
- ASCII commands ending in CR LF. `IP` → `"       32.2     g ?"` then blank lines: `?` = unstable, a trailing `N` = net (tared; the manual says `NET`). Other commands answer `OK!`. Refusals: `ES` unknown command or bad value, `EL` standby, `IP I` busy (calibrating), `IC L` not on this model. `SP` is useless: sent while unstable, it's never answered.
- ~100 ms per reply, ~8.7 readings/s when polled (`CP` streams ~10.3/s). Read it non-blocking: the hold loop feeds the ODrive watchdog every 20 ms.


## Bench safety (on top of the root rules)
- Keep torque limits small until the user raises them.
- Do not move motors without user permission.

