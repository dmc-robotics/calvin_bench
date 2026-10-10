# Experiment Instructions

One file per experiment from `../PLAN.md`. Each says what it measures, what you need, the steps, what to record and how to read the result.

| # | File | Gives | Needs |
|---|---|---|---|
| 1 | [01-odrive-setup.md](01-odrive-setup.md) | Frozen ODrive configuration | odrivetool (M0) |
| 2 | [02-static-torque-gain.md](02-static-torque-gain.md) | Real torque per commanded torque → G (× belt ratio) | `bench static-gain` over ODrive USB (M0) |
| 3 | [03-friction-sweep.md](03-friction-sweep.md) | Viscous, Coulomb and static friction | odrivetool (rough, M0) or bench (M3+) |
| 4 | [04-acceleration-coastdown.md](04-acceleration-coastdown.md) | Actuator inertia J | bench (M3+) |
| 5 | [05-chirp.md](05-chirp.md) | Frequency response: J, b, delay, resonance | bench (M3+) |
| 6 | [06-latency.md](06-latency.md) | Delay τ_d, feedback age | bench (M4) |
| 7 | [07-velocity-noise.md](07-velocity-noise.md) | Velocity noise and lag | bench (M4) |
| 8 | [08-torque-speed-limit.md](08-torque-speed-limit.md) | Torque available vs speed | bench (M3+) |
| 9 | [09-left-right-comparison.md](09-left-right-comparison.md) | Left/right mismatch | repeats of 2–5 |
| 11 | [11-repeatability.md](11-repeatability.md) | Parameter spreads | repeats of 4–5 |
| 12 | [12-rich-excitation.md](12-rich-excitation.md) | Data for later learned/RL models | bench (M3+) |
| 13 | [13-wheel-inertia.md](13-wheel-inertia.md) | Wheel inertia (CAD check) | repeat of 4 |
| 14 | [14-flywheel.md](14-flywheel.md) | Check that the J fit is right | flywheel + repeat of 4 |

Suggested order: 1 → 2 → 3 (rough) → [build M1–M3] → 4 → 5 → 8 → [M4] → 6 → 7 → 13 → 14 → 11 → 9 → 12.

## Configurations

Each file starts with a **Configuration** section. The terms mean:

- **Bench fixture:** a motor out of the robot, mounted on the bench rig with its belt and wheel as on the robot (or motor only, or with a flywheel, as the file says). Used where you need hands-on access: lever arm, removing the wheel, mounting a flywheel.
- **Robot on a stand:** the assembled robot with its chassis supported so both wheels spin freely in the air. Used for the main dynamic data, so the actuator is measured exactly as installed (real belt tension, pulleys, mounting).
- **odrivetool:** the Mac talks straight to the ODrive over its USB port. The Teensy isn't involved.
- **Bench sketch:** the Teensy runs `firmware/bench` instead of instinctus and talks to the ODrive(s) over CAN; the Mac talks to the Teensy over USB. The Jetson, IMU and ToF sensors aren't used. Reflash instinctus afterwards if needed.

**Instinctus is never needed for these experiments.**

## Before every session

- [ ] Wheel (or flywheel) clear of everything, fasteners tight, nothing loose that a spinning wheel can catch.
- [ ] Physical e-stop (power disconnect) within reach.
- [ ] **Battery power** for anything that accelerates and then brakes hard. A bench supply can't absorb regenerated energy; the bus voltage spikes and the ODrive faults (or the supply is damaged). The bench supply is fine for static tests (experiment 2) and slow ones.
- [ ] ODrive errors cleared, watchdog on, torque limit set to what the experiment needs and no higher.
- [ ] Note the battery voltage and motor temperature.
- [ ] Belt at the tension it will run with on the robot. Tension changes friction (and possibly J), so set it once and don't adjust it between experiments. If you must, note it.

## Every run (experiment 10)

- Dump the ODrive config with the run (once the bench CLI exists it does this automatically; before that, `odrivetool backup-config odrive/<date>.json` whenever the config changes).
- Log raw signals, not filtered ones: command, position, velocity, Iq setpoint/measured, torque estimate, bus voltage/current, axis state/error, µs timestamps.
- Write down anything unusual (noises, a fault, a re-tensioned belt) in the run's notes. It's much harder to remember later.

## Conventions

- **ODrive units are motor-side:** revolutions, rev/s, N·m at the motor shaft, amps. **LQR wants wheel-side SI.** With the 4:1 belt:
  - wheel angle (rad) = motor revolutions × 2π / 4
  - wheel speed (rad/s) = motor rev/s × 2π / 4
  - wheel torque (N·m) ≈ 4 × motor torque × belt efficiency. Experiment 2 measures this directly as G.
- **Torque constant:** ODrive's convention is `torque_constant = 8.27 / KV` = 8.27 / 330 ≈ 0.0251 N·m/A for the D5312s. Motor torque ≈ 0.0251 × Iq.
- **Rough scale:** the 4S battery gives ~80 rev/s no-load motor speed (~20 rev/s at the wheel). 0.1 N·m motor-side ≈ 4 A ≈ 0.4 N·m at the wheel.
- **Directions:** test both. "Forward" is whichever direction moves the robot forward; record which sign that is for each motor (the firmware's per-motor `direction`).

## A note on odrivetool names

Attribute names below are for ODrive firmware 0.6.x and may differ slightly in your version. Use tab completion in odrivetool to confirm (`odrv0.axis0.<tab>`), and check the ODrive docs. ODrive's web GUI (https://gui.odriverobotics.com) can do the same setup with presets for ODrive's own motors.

## Tooling status

The `bench` CLI is built in milestone M3 (see `../PLAN.md`). Until then, experiments 1 and 3 run from odrivetool, and experiment 2 uses `bench static-gain record` / `analyze` over the ODrive's USB. Instructions that need the bench describe the waveform and settings; whoever implements the CLI defines the actual command names and should update these files.
