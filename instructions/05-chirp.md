# 5. Chirp Torque Excitation (Frequency Response)

**Gives:** the frequency response from torque command to wheel velocity → a second estimate of J and b, the total delay τ_d (from phase lag at high frequency), and any belt resonance.

**When:** bench CLI (M3+). Wheel off the ground, battery power.

## Configuration
- **Where:** **Robot on a stand**, wheels off the ground (chassis supported so both wheels spin freely), motors installed as they'll run
- **Drivetrain:** Motor + belt + wheel
- **Firmware:** **Bench sketch** on the Teensy (`firmware/bench`, flashed in place of instinctus). Instinctus not used
- **Connections:** Teensy USB → Mac, Teensy ↔ ODrive over CAN
- **Power:** Battery
- **Motors:** One at a time

## Waveform
- Sine sweep with a logarithmically rising frequency, 0.5 Hz → 50 Hz over 20 s:
  u(t) = A × sin(2π × f(t) × t), with f rising exponentially from start to end.
- Amplitude A: run at two levels, e.g. 0.03 and 0.08 N·m motor-side. The smaller one shows behavior near stiction, the larger is cleaner.
- Fade the start and end in and out over ~0.5 s so the sweep doesn't begin with a jolt.
- Optional: add a small constant torque offset so the wheel stays turning in one direction, avoiding zero speed where friction is jumpy. Watch the speed, since a constant offset keeps accelerating until friction balances it.

## Settings
- Record at 1 kHz: command, velocity, position, Iq, timestamps.
- Velocity limit well above anything the chirp reaches.

## Analysis
- Estimate the frequency response H(f) = velocity / command, e.g. with `scipy.signal.csd` / `welch` (H = cross spectrum ÷ input spectrum), plus coherence.
- A pure inertia + friction plant looks like 1/(J s + b): magnitude falls at −20 dB/decade above the corner frequency b/J.
- Delay τ_d shows as extra phase lag growing linearly with frequency: phase lag = 360° × f × τ_d.
- A resonance (from belt springiness) shows as a peak or notch. Note its frequency. If it's anywhere near the expected balance-control bandwidth (a few Hz to ~20 Hz), add the wheel-side encoder (deferred item in PLAN.md).

## Pitfalls
- Only trust frequencies where coherence is high (> 0.9).
- At high frequency the motion is tiny; encoder resolution and noise limit what you can see.

## Done when
A Bode plot for each motor and amplitude, a J and b consistent with experiment 4, and a τ_d estimate.
