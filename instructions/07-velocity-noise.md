# 7. Velocity-Estimate Noise and Lag

**Gives:** how noisy and how delayed the ODrive's velocity estimate is. Wheel velocity is an LQR state, so its noise limits the velocity gain and its lag adds to the delay.

**When:** M4.

## Configuration
- **Where:** **Robot on a stand**, wheels off the ground (chassis supported so both wheels spin freely), motors installed as they'll run
- **Drivetrain:** Motor + belt + wheel
- **Firmware:** **Bench sketch** on the Teensy (`firmware/bench`, flashed in place of instinctus). Instinctus not used (M4: both CAN buses wired)
- **Connections:** Teensy USB → Mac, Teensy ↔ both ODrives over CAN1 and CAN3
- **Power:** Battery
- **Motors:** Both connected; measure one at a time

## Procedure
1. **Standstill:** closed loop, zero torque, wheel still. Record 10 s.
2. **Constant speed:** apply a small constant torque until friction balances it and the speed levels off. Record 10 s at that steady speed. Repeat at 2–3 torque levels (speeds).
3. **Lag:** reuse the chirp data from experiment 5, or the step data from experiment 6.

## Analysis
- Noise: the standard deviation of velocity (after removing the mean or a slow trend), and its spectrum. Report in wheel rad/s.
- Compare with velocity computed from position differences (Δposition / Δt using the arrival timestamps). If the differenced velocity is cleaner or faster, the controller could use that instead.
- Lag: relative to velocity derived from position, the estimate's phase lag at each frequency. Its bandwidth is set by the ODrive's encoder estimator bandwidth setting, part of the frozen config.

## Done when
A noise standard deviation and an estimated lag for each motor.
