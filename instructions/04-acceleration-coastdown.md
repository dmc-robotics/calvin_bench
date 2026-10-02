# 4. Constant-Torque Acceleration and Coast-Down (J)

**Gives:** the actuator inertia J (rotor + pulleys + belt, reflected to the wheel axle), using the friction from experiment 3.

**When:** bench CLI (M3+). Battery power: the wheel spins up and is braked.

## Configuration
- **Where:** **Robot on a stand**, wheels off the ground (chassis supported so both wheels spin freely), motors installed as they'll run
- **Drivetrain:** Motor + belt + wheel
- **Firmware:** **Bench sketch** on the Teensy (`firmware/bench`, flashed in place of instinctus). Instinctus not used
- **Connections:** Teensy USB → Mac, Teensy ↔ ODrive over CAN
- **Power:** **Battery**
- **Motors:** One at a time

## Idea
J × dω/dt = τ_motor − friction(ω). With known torque and friction, the slope of the speed curve gives J. Coasting (zero torque) gives friction ÷ J, a cross-check.

## Waveform
For each torque level (e.g. 0.03, 0.06, 0.10 N·m motor-side), in each direction:
1. Start at rest. Step to the torque and hold until the speed reaches ~60–70% of the velocity limit, or a fixed time (about 1–2 s).
2. Step to **0 torque (still closed loop)** and record the coast-down until it nearly stops.
3. Rest a few seconds between runs.

## Settings
- Velocity limit (safety cap) above the expected peak speed, so it doesn't clip the acceleration.
- Record at 1 kHz: command, velocity, Iq, bus voltage.

## Analysis
- Convert to wheel side: ω_wheel = rev/s × 2π / 4 and τ_wheel = G × τ_command.
- In the acceleration phase, fit J from τ_wheel − τ_friction(ω) = J × dω/dt. Fit to the speed curve instead of differentiating noisy data, e.g. simulate the model and fit J by least squares.
- In the coast-down, −τ_friction(ω) = J × dω/dt, a check on both J and the friction model.
- **Wheel on vs off:** report J without the wheel (see experiment 13), or subtract the CAD wheel inertia. Record which.

## Pitfalls
- Speeds near the velocity limit reduce torque (torque-mode velocity limiting). Stop accelerating well before it.
- At high speed the motor runs out of voltage (see experiment 8), so torque falls short. Use the measured Iq, not the command, as the actual torque.

## Done when
J values from different torque levels and both directions agree within a few percent.
