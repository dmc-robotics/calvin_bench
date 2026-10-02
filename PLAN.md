# Calvin Bench: Plan

_Last updated 2026-10-01._

## Status

- **Current milestone: M0** (ODrive bring-up over USB). Needs the user at the bench.
- File structure is scaffolded (firmware stubs compile; the Python CLI is a stub). Nothing has run on hardware yet.
- Next code work: M1 (InstinctusCore `ODriveCan` + bench sketch text commands), once M0 is done.

## Goal

Measure each drive actuator (Teensy CAN torque command → ODrive S1 → D5312s → 4:1 belt → wheel) and write a simulator-neutral **`actuator.yaml`** with nominal values and spreads. It feeds the first LQR (designed in a separate "twin" project, created later) and, after that, an RL policy.

Model to fit, per side: J·ω̇ = G·u(t−τ_d) − τ_c·sgn(ω) − b·ω − τ_cog(θ), plus a torque–speed limit that depends on bus voltage. `actuator.yaml` reports **J for the actuator only** (rotor, pulleys, belt, reflected to the wheel axle) — the wheel's inertia comes from CAD, so don't count it twice.

## Milestones

Each is a small slice you can see working on the bench.

### M0 — ODrive bring-up over USB (no code)
- Wire one S1 + motor on the bench, battery powered, e-stop in reach.
- odrivetool: calibrate, decide anticogging, set `torque_constant` (8.27/330), limits, CAN 1 Mbit/s, node ID (left 1, right 2), torque control + passthrough. Cyclic messages: encoder estimates, Iq and torques at 1 ms; bus voltage 10 ms; temperature, heartbeat, error 100 ms. Turn on the watchdog (~0.1 s; it's fed by torque commands). Make sure the torque-mode velocity limit can't clip tests.
- Spin it in torque mode from odrivetool. Measure G with the lever arm on the scale (experiment 2) and do a rough friction check.
- Save the config dump into `odrive/` — this is the frozen baseline.
- **Done when:** motor spins in torque mode, config saved, first number for G.

### M1 — InstinctusCore `ODriveCan`, one motor
- `InstinctusCore/src/ODriveCan.*`: FlexCAN_T4 wrapper. Commands (axis state, controller mode, torque, clear errors, estop). Feedback parsed in the CAN receive interrupt into `MotorFeedback`, each message stamped with `micros()` on arrival. A `direction` (+1/−1) per motor so positive = robot forward (determine physically).
- Bench sketch: text commands over USB serial (`enable`, `idle`, `torque 0.05`, `status`).
- **Done when:** the motor spins on CAN commands typed in a serial monitor, `status` shows live position/velocity/Iq/Vbus, and the ODrive watchdog idles the motor when commands stop.

### M2 — Loop, safety, recorder, waveform player
- `SafetySupervisor` (torque clamp, speed limit, ODrive fault → idle, link timeout → idle) and `Recorder` (fixed ring buffer: ISR pushes, `loop()` drains) in InstinctusCore. `WaveformPlayer` and the text protocol in the bench sketch's `src/`.
- 1 kHz `IntervalTimer` loop (a short pattern in the sketch, not a framework): latest feedback → `player.next()` → `safety.check()` → send torque → `recorder.push()`. Record loop timing too.
- Protocol: `load` a torque array, `play` **streams CSV rows over USB while it runs** (RAM only holds ~6 s), `stop`, `config` limits. Write the exact commands and columns into this file when settled.
- **Done when:** a torque step plays and streams a sensible CSV with µs timestamps.

### M3 — Python `bench` CLI (minimum)
- `bench/`: serial link, waveform generators (step, staircase, chirp, PRBS, multi-sine), run folders (`runs/<timestamp>_<experiment>_<motor>/` with `meta.json` + `data.csv`), plotting. Conversion from ODrive units to SI / wheel side happens in one place on the host.
- **Done when:** `bench run step --motor left --torque 0.1 --duration 2` creates a run folder and a plot.

### M4 — Second motor + timing check
- Second CAN Pal on CAN3; both motors in the sketch. Measure command→response latency, feedback age, loop jitter, velocity noise (experiments 6–7).
- **Done when:** both motors run waveforms together and there's a first τ_d.

### M5 — Experiments + fitting → `actuator.yaml`
- Experiments below as Python definitions (just waveforms + settings). Fit friction → J → chirp frequency response (J, b, τ_d, resonance). `bench export` writes `actuator.yaml`; validate on held-out runs (and the flywheel, if made).
- **Done when:** `actuator.yaml` exists and replaying held-out runs through the fitted model matches measured velocity.

### Later
Twin project + LQR design · `bench serve` + an Explorator "Bench" page · instinctus adopts InstinctusCore for its balance loop · RL simulator choice.

## Experiments

Step-by-step instructions for each one: [`instructions/`](instructions/README.md).

**Needed for LQR**
1. ODrive setup and frozen config (M0).
2. Static torque gain: lever arm on a scale → G. Both directions, ~5 torque levels each, arm at the wheel; fit a line per direction (slope = G, intercept = friction/offset). Subtract the arm's resting weight; keep stall holds short.
3. Steady-state friction: velocity sweep, both directions → b, τ_c, stiction.
4. Constant-torque acceleration and coast-down → J.
5. Chirp torque, wheel off the ground → J, b, τ_d, any belt resonance.
6. Latency: torque step → first response; CAN feedback-age distribution.
7. Velocity-estimate noise and lag.
8. Torque–speed limit at nominal 4S voltage.
9. Left/right comparison.

**Easy wins (cheap now, useful for RL later)**
10. Log raw signals and dump the ODrive config with every run.
11. Repeat 4–5 three times, cold and warm → parameter spreads.
12. A few minutes of random multi-sine/PRBS torque, some runs held out.
13. Experiment 4 with and without the wheel → wheel inertia check against CAD.
14. One machined flywheel of known inertia → validates J.

**Deferred:** reaction-torque dyno, wheel-side encoder (only if 5 shows a belt resonance), second flywheel, voltage sweeps, anticogging comparisons.

**Safety:** battery for anything that brakes hard (a bench supply can't absorb regen); ODrive CAN watchdog on; physical e-stop.

## Decisions

| Topic | Decision |
|---|---|
| Battery | 4S LiPo |
| CAN | Teensy 4.1 + 2× Adafruit CAN Pal. Left: CAN1 (pins 22/23), node 1. Right: CAN3 (pins 30/31), node 2. 1 Mbit/s, one bus per ODrive (~50% load at 1 kHz). Jetson stays on Serial1, so CAN2 is unused |
| Control layering | Teensy runs balance only (LQR, later a small fixed-cost RL policy) at 1 kHz. Jetson sends higher-level commands at 20–50 Hz |
| Design principle | Keep the Teensy lean, fast, reliable, deterministic. Logic on the host |
| Firmware | Two sketches flashed separately — `calvin_bench/firmware/bench/` and `calvin_instinctus/instinctus/` — sharing **InstinctusCore** (ODriveCan, SafetySupervisor, Recorder) at `calvin_instinctus/InstinctusCore/`, symlinked into `~/code/arduino/libraries/`. Rebuild after library edits |
| Experiments run on the Teensy | Host uploads a waveform; the Teensy plays it on its own timer and streams samples back. New experiments need no reflash |
| Project boundaries | calvin_bench = actuator measurement only → `actuator.yaml`. A separate twin project (working name *simulacrum*) will hold the plant model, LQR and RL environment; create it when LQR design starts |
| Modeling | LQR first on an accurate physical model; RL later, approach TBD. Collect what LQR needs plus the easy wins |
| Mass properties | From CAD, not the bench |
| Explorator | Optional later: a GUI over the CLI (`bench serve`, same WebSocket envelope as the cogitator gateway) |
| RL simulator | Undecided; leaning MuJoCo. Not needed until after LQR |
| Equipment | Scale, bench PSU, battery, voltmeter, Mac, Teensy 4.1, 2× CAN Pal. Nothing else required; a logic analyzer or USB-CAN adapter only if debugging gets stubborn |
| calvin_theory | Personal learning notes; not a dependency |

## Decision log (why)

- **CAN1 + CAN3:** CAN2's pins are Serial1, the Jetson link. The CAN Pals were already on hand.
- **Balance on the Teensy, higher-level on the Jetson:** the Teensy's timing is deterministic; Linux and the serial link aren't. Bench latency tests then cover everything the balance loop sees.
- **Separate twin project:** keeps calvin_bench about measurement; `actuator.yaml` is the only interface, so splitting later costs nothing.
- **LQR first, data for later:** collect what LQR needs plus cheap extras; a later teardown is acceptable.
- **Two sketches + shared library:** the bench rig has no IMU/ToF/Jetson, so production code shouldn't need "missing sensor" modes; sharing the CAN/safety code means the bench measures the same path the balance loop uses.
- **InstinctusCore lives in calvin_instinctus:** keeps all Calvin code together; the symlink makes both sketches build against the same files.
- **Stream instead of record-then-dump:** two motors at 1 kHz fill Teensy RAM in ~6 s.

## Housekeeping done (2026-10-01)

- GIGA code removed from calvin_instinctus; its CLAUDE.md/README updated (Teensy, 4S, CAN 1 Mbit/s, ISM330DHCX IMU).
- calvin_instinctus moved from `~/code/arduino/` to `~/code/robotics/calvin/`.
- Rosetta reinstalled after the macOS 27 upgrade (the Teensy toolchain is x86-only).
- Arduino libraries cleaned up: broken symlinks repointed to `librarius`; GigaEventQueue, Adafruit ICM20X and STM32duino VL53L4CX removed. If ToF start-up ever hangs, the VL53L4CX library's unbounded I2C retry loop is the likely cause.
