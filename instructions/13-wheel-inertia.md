# 13. Wheel Inertia (CAD Cross-Check)

**Gives:** the wheel's own inertia, to check the CAD value. It also tells you whether the J from experiment 4 includes the wheel, so it isn't counted twice in the robot model.

**When:** after experiment 4 works. One extra pair of runs.

## Configuration
- **Where:** **Bench fixture** (easier to remove and refit the wheel)
- **Drivetrain:** Motor + belt, run **with** the wheel and then **without** it (pulley and belt stay on)
- **Firmware:** **Bench sketch** on the Teensy (`firmware/bench`, flashed in place of instinctus). Instinctus not used
- **Connections:** Teensy USB → Mac, Teensy ↔ ODrive over CAN
- **Power:** Battery
- **Motors:** One

## Procedure
1. Run experiment 4 **with the wheel** on.
2. Remove the wheel (leaving the pulley and whatever else stays on the actuator) and run experiment 4 again with identical settings.
3. Use the same torque levels and directions both times.

## Analysis
- J_wheel = J_with − J_without. Compare with the CAD value for the wheel about its axle.
- Friction may differ slightly without the wheel's weight on the bearings. Use each configuration's own friction fit.
- `actuator.yaml` reports **J_without** (the actuator only); the wheel's inertia comes from CAD in the robot model.

## Done when
J_wheel within ~10% of CAD, or the reason it isn't understood.
