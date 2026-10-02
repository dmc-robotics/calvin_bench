# 9. Left/Right Comparison

**Gives:** whether the two actuators really match. LQR uses one model for both wheels, so this checks that assumption.

**When:** after experiments 2–5 are done on the first motor.

## Configuration
- **Where:** Same as each repeated experiment (2: bench fixture; 3–5: robot on a stand)
- **Drivetrain:** Same as each repeated experiment
- **Firmware:** Same as each repeated experiment. Instinctus not used
- **Connections:** Same as each repeated experiment; second motor on CAN3, node 2
- **Power:** Same as each repeated experiment; match the battery charge to the first motor's runs
- **Motors:** The second motor, after the first is done

## Procedure
1. Repeat experiments 2, 3, 4 and 5 on the second motor (CAN3, node 2), with the same settings and waveforms.
2. Same battery charge level and similar motor temperature as the first motor's runs.

## Analysis
- Compare G, b, τ_c, J and τ_d between sides. Differences within the run-to-run spread (experiment 11) mean they match.
- If they differ meaningfully (e.g. > 10% in G or J), check belt tension, pulleys and calibration first. If it's real, `actuator.yaml` keeps separate values for each side.

## Done when
A short table of both sides' parameters, with a "match / don't match" note.
