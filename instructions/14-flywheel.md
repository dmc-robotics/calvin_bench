# 14. Known-Inertia Flywheel (Validating the J Fit)

**Gives:** proof that the J measurement method works. Add a flywheel whose inertia you can calculate exactly; the measured change in J should match the calculation.

**When:** after experiment 4 works. Needs a machined flywheel (CNC).

## Configuration
- **Where:** **Bench fixture**, with a guard: the steel flywheel stores a lot of energy
- **Drivetrain:** Motor + belt, run **without** the wheel and then with the **flywheel** in its place
- **Firmware:** **Bench sketch** on the Teensy (`firmware/bench`, flashed in place of instinctus). Instinctus not used
- **Connections:** Teensy USB → Mac, Teensy ↔ ODrive over CAN
- **Power:** Battery
- **Motors:** One

## Making the flywheel
- A plain steel disc is easiest to calculate. Example: 100 mm diameter × 10 mm thick ≈ 0.62 kg, J ≈ 7.7 × 10⁻⁴ kg·m². That's the same order as the expected actuator J, which makes for a clear measurement.
- Make it mount where the wheel goes, concentric, with a bore and bolt pattern that center it well. Any wobble adds error and vibration.
- Calculate J from measurements of the actual part, not the drawing:
  - Weigh it (kitchen scale) and measure the outer and bore diameters with calipers.
  - Annulus: J = ½ × m × (r_outer² + r_inner²).
  - Bolt holes and hubs change J slightly. Model them in CAD from the same measured mass, or ignore them if they're small.

## Procedure
1. Run experiment 4 without the wheel (if not already done).
2. Mount the flywheel in place of the wheel. Run experiment 4 with identical settings.
3. Keep speeds moderate: a heavy steel disc stores a lot of energy. Battery power, guard in place.

## Analysis
- J_flywheel(measured) = J_with flywheel − J_without. Compare with the calculated value.
- Within a few % means the method and the torque gain G are right. A consistent error points at G (experiment 2), since J is fitted from torque ÷ acceleration.

## Done when
Measured and calculated flywheel inertia agree within a few %.
