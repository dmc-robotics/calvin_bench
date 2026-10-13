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
  bench/               Python package: the `bench` CLI, serial link, waveforms, runs, units, fitting
  odrive/              ODrive config backups (the frozen baseline; committed)
  runs/                recorded runs (gitignored)
```

## Firmware

- The bench sketch uses `InstinctusCore` (in `../calvin_instinctus/InstinctusCore/`, symlinked into `~/code/arduino/libraries/`) for the ODrive CAN driver, safety supervisor and recorder. Bench-only pieces (waveform player, USB text protocol) live in `firmware/bench/src/`.
- Build and flash: `cd firmware/bench && grot build && grot load`. Rebuild after any `InstinctusCore` edit.
- Teensy RAM holds only ~6 s of 1 kHz two-motor data, so the sketch **streams samples to the host during a run** rather than storing whole runs.
- ODrive CAN protocol: https://docs.odriverobotics.com/v/latest/manual/can-protocol.html. Arbitration ID = `node_id << 5 | cmd_id`; little-endian float32 payloads. Firmware keeps ODrive's units; **all conversion to SI and wheel side happens in `bench/units.py`**.

## Python

- Python 3.15 (`.python-version`), managed with uv: `uv sync`, then `uv run bench --help`.

## Scale (experiment 2)

OHAUS Adventurer AX8201/E, 0.1 g, read by `bench static-gain record` (`Scale` in `bench/static_gain.py`; `--no-scale` to type readings).
- Cable to its **USB Device** port (square USB-B; USB Host is for flash drives). Inside is an FTDI FT230X serial bridge, no driver: `/dev/cu.usbserial-DN04KNBY` (the chip's serial number, so it's fixed; the `--scale` default), 9600 baud, 8N1.
- ASCII commands ending in CR LF. `IP` → `"       32.2     g ?"` (`?` = unstable) then blank lines; `PV` → `Sr 1.06`; `PSN` → `Balance ID: B816716802`.
- ~90 ms per reply, ~8 readings/s when polled. Read it non-blocking: the hold loop feeds the ODrive watchdog every 20 ms.

## Bench safety (on top of the root rules)
- Keep torque limits small until the user raises them.
- Do not move motors without user permission.

