# 6. Latency and Feedback Age

**Gives:** the delay τ_d from "Teensy sends a torque command" to "the effect appears in the feedback", and the age distribution of feedback samples. Delay is the main limit on how aggressive the LQR can be.

**When:** M4 (both CAN buses and µs timestamps in place).

## Configuration
- **Where:** **Robot on a stand**, wheels off the ground (chassis supported so both wheels spin freely), motors installed as they'll run
- **Drivetrain:** Motor + belt + wheel
- **Firmware:** **Bench sketch** on the Teensy (`firmware/bench`, flashed in place of instinctus). Instinctus not used (M4: both CAN buses wired)
- **Connections:** Teensy USB → Mac, Teensy ↔ both ODrives over CAN1 and CAN3
- **Power:** Battery
- **Motors:** Both connected, so timing is measured with the real bus setup; measure one at a time

## Idea
The firmware timestamps every command it sends and every feedback message it receives, in µs. A torque step shows up in Iq_measured almost immediately (the ODrive's current loop is fast), and in velocity soon after.

## Waveform
- 50+ small torque steps (e.g. ±0.03 N·m motor-side) at random intervals of 100–300 ms, alternating sign so the wheel doesn't wander off.
- Random timing matters: the ODrive sends feedback on its own clock, and random timing spreads the steps across that cycle.

## Analysis
- For each step: τ_d = (arrival time of the first Iq message showing the new setpoint) − (command send time). Plot the distribution and report the mean and worst case.
- **Feedback age:** at each 1 kHz tick, age = tick time − arrival time of the latest encoder message. Plot the distribution; expect 0–1 ms with feedback at 1 ms.
- **Loop jitter:** the distribution of the ISR's actual start times around 1 ms intervals, and its execution time.
- Total delay seen by the controller ≈ command → effect + feedback age + half a control period.

## Optional cross-check
Toggle a GPIO pin when the command is sent and watch it alongside the CAN bus on a logic analyzer. Only if numbers look suspicious.

## Done when
A τ_d mean and worst case, and a feedback-age histogram, for each motor.
