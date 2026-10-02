# 12. Rich Excitation Dataset

**Gives:** a few minutes of varied, random-looking torque data. Not needed for LQR. It's cheap insurance for later: checking the model on data it wasn't fitted to, and training learned or corrected models for the RL stage.

**When:** bench CLI (M3+), any time after the main experiments. Wheel off the ground, battery.

## Configuration
- **Where:** **Robot on a stand**, wheels off the ground (chassis supported so both wheels spin freely), motors installed as they'll run
- **Drivetrain:** Motor + belt + wheel
- **Firmware:** **Bench sketch** on the Teensy (`firmware/bench`, flashed in place of instinctus). Instinctus not used
- **Connections:** Teensy USB → Mac, Teensy ↔ ODrive over CAN
- **Power:** Battery
- **Motors:** One at a time

## Waveforms
- **Multi-sine:** a sum of sines at many frequencies (0.5–40 Hz), with random phases, scaled to a target amplitude.
- **PRBS:** a pseudo-random binary sequence switching between +A and −A, with the minimum switching interval varied (e.g. 5, 20 and 100 ms) so it excites different frequency bands.
- Amplitudes: 3 levels (e.g. 0.03, 0.06, 0.10 N·m motor-side). About 60 s per waveform/amplitude combination.
- Add a slowly varying offset to some runs so the data covers different speeds, not just around zero.

## Procedure
1. Generate each waveform with a fixed random seed and save the seed with the run, so the waveform can be regenerated.
2. Run each once. Run one or two combinations a second time and mark them **held out**: never used for fitting, only for testing a model.

## Done when
Runs covering all three amplitudes and both waveform types, with the held-out runs labeled.
