# 11. Repeatability (Parameter Spreads)

**Gives:** how much the fitted parameters vary from run to run and with temperature. The spread becomes the "± range" in `actuator.yaml`: useful for checking LQR robustness, and later for randomizing the RL simulator.

**When:** after experiments 4 and 5 work. About 15 minutes.

## Configuration
- **Where:** **Robot on a stand**, wheels off the ground (chassis supported so both wheels spin freely), motors installed as they'll run
- **Drivetrain:** Motor + belt + wheel
- **Firmware:** **Bench sketch** on the Teensy (`firmware/bench`, flashed in place of instinctus). Instinctus not used
- **Connections:** Teensy USB → Mac, Teensy ↔ ODrive over CAN
- **Power:** Battery
- **Motors:** One at a time (ideally both, one after the other)

## Procedure
1. **Cold:** motor at room temperature (rested ≥ 30 min). Run experiment 4 (one torque level per direction) and experiment 5 (one amplitude). Repeat 3 times.
2. **Warm:** run the motor moderately for about 5 minutes (e.g. a slow back-and-forth torque waveform) until the motor temperature has risen and settled. Repeat the same runs 3 times.
3. Record the motor temperature and bus voltage for each run.

## Analysis
- Fit J, b, τ_c and τ_d for each run. Report the mean and standard deviation, separately for cold and warm and combined.
- Friction usually drops as the motor warms. If the cold/warm difference is large, note which condition the robot normally runs in.

## Done when
A mean ± spread for each parameter, on at least one motor (ideally both).
