# 3. Steady-State Friction Sweep

**Gives:** friction torque vs speed in both directions → viscous friction b, Coulomb friction τ_c, and stiction.

**When:** a rough version at M0 from odrivetool; the real one once the bench CLI exists (M3+).

## Configuration
- **Where:** Rough version: **bench fixture**. Real version: **Robot on a stand**, wheels off the ground (chassis supported so both wheels spin freely), motors installed as they'll run
- **Drivetrain:** Motor + belt + wheel, belt at running tension
- **Firmware:** Rough version: none (odrivetool over the ODrive's USB). Real version: **Bench sketch** on the Teensy (`firmware/bench`, flashed in place of instinctus). Instinctus not used
- **Connections:** Rough: ODrive USB → Mac. Real: Teensy USB → Mac, Teensy ↔ ODrive over CAN
- **Power:** Battery
- **Motors:** One at a time

## Idea
In **velocity control**, the ODrive holds a constant speed. At constant speed the motor torque exactly balances friction, so the measured torque (Iq × torque constant) **is** the friction at that speed.

## Procedure (odrivetool, rough)
1. Wheel off the ground. Switch to `ControlMode.VELOCITY_CONTROL`. Set the velocity limit above the highest test speed.
2. For speeds such as ±0.5, 1, 2, 4, 8, 12, 16, 24, 32, 40 rev/s motor-side:
   - Set `odrv0.axis0.controller.input_vel`.
   - Wait about 3 s to settle.
   - Read `odrv0.axis0.motor.foc.Iq_measured` several times and average.
3. Do every speed in both directions.
4. Switch back to torque mode afterwards.

## Procedure (bench, M3+)
Same staircase of speeds, 3 s per step, logged at 1 kHz; average the last 2 s of each step. Then a slow torque ramp from zero in each direction to find the breakaway torque (stiction): the torque at which the wheel first starts to move.

## Analysis
- Friction torque τ_f(ω) = 0.0251 × Iq (motor-side; × G for wheel-side).
- Fit τ_f = τ_c × sign(ω) + b × ω separately for each direction. Look for extra friction at low speed (the Stribeck effect), which shows up as a bump near zero speed.

## Pitfalls
- The ODrive's velocity loop gains affect how steady the speed is, but not the steady-state torque, so the default gains are fine.
- Belt tension and temperature change friction. Note both, and use a warm motor for the main data.

## Done when
A friction curve for each direction, with b and τ_c fitted.
