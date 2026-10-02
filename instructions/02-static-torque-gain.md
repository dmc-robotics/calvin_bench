# 2. Static Torque Gain (G)

**Gives:** how much torque the motor really produces per commanded N·m (a check on the torque constant), plus a static friction estimate. G = wheel torque per commanded motor torque = belt ratio × that factor. A toothed belt doesn't slip, so the ratio is exactly the pulleys' tooth-count ratio (4:1; confirm by counting teeth). Belt drag shows up in the friction from experiments 3–5.

**When:** M0, from odrivetool. No firmware needed. The bench supply is fine (nothing moves).

## Configuration
- **Where:** **Bench fixture** (room for the lever arm and scale)
- **Drivetrain:** **Motor only** Arm clamped to the motor shaft. Do it right after experiment 1.
- **Firmware:** None on the Teensy (it isn't needed). Driven from odrivetool over the ODrive's USB.
- **Connections:** ODrive USB → Mac
- **Power:** Battery
- **Motors:** One at a time

## Equipment
- Kitchen scale (grams); a rigid lever arm, ~0.2 m (motor-side torques are small, so a longer arm gives bigger readings); something to raise the scale to shaft height.
- Clamp point: the motor's free shaft end (the D5312s is dual-shaft; use the end that doesn't carry the encoder magnet) or the motor-side pulley. For the belt-on variant: the wheel axle, driven pulley or hub, never the tire (it flexes).
- Ruler or calipers.

## Setup
1. Clamp the arm so it sticks out horizontally. It must not slip.
2. Put the scale under the arm's tip so the arm rests on it when level. Use a narrow contact point (a bolt head or an edge) so the length is well defined.
3. Measure **L**, from the shaft (or axle) center to the contact point, in meters.
4. With the motor idle, read the scale: this is the **tare**, the arm's resting weight.

## Procedure
1. Closed loop, torque mode. Command a small torque in the direction that pushes the arm **down** onto the scale.
2. For each level, e.g. 0.05, 0.10, 0.15, 0.20, 0.25 N·m motor-side (≈ 2–10 A; with a 0.2 m arm that's roughly 25–130 g on the scale, so a 1 g scale gives a few % at the low end and better above):
   - Set `odrv0.axis0.controller.input_torque`.
   - Wait about a second for the reading to settle.
   - Record the scale reading, `odrv0.axis0.motor.foc.Iq_measured` and `odrv0.vbus_voltage`.
   - Go back to 0. Keep each hold to **2–3 seconds** and pause between levels: a stalled motor heats quickly at these currents. Check the motor temperature between directions.
3. Idle the motor. Re-read the tare.
4. **Other direction:** move the scale to the other side of the axle (or flip the arm) and repeat with negative torques.
5. Optional: repeat each direction once more, approaching each level from a higher torque rather than from zero. The difference shows static friction (hysteresis).

## Analysis
- Force F = (reading − tare) / 1000 × 9.81 N; measured torque τ = F × L.
- For each direction, fit τ = k × τ_command + offset. **Slope k** = real torque per commanded torque (ideally 1.0 motor-only); intercept ≈ static friction.
- **G = belt ratio × k** (motor-only). For the belt-on variant, the slope is G directly (and includes the belt's static losses).
- Torque constant check: τ_command vs 0.0251 × Iq_measured should agree closely.
- Report k (and G) as the average of the two directions; the difference shows asymmetry.

## Pitfalls
- An arm that isn't level changes the effective length (cos error); within ±5° it's negligible.
- Belt stretch: the arm may creep as torque rises. Read once it has settled.
- Scales drift when warm or heavily loaded. Re-tare between directions.

## Done when
A G for each direction, close to each other (within a few %), with sensible residuals.
