# 2. Static Torque Gain (G)

`τ_wheel = G × τ_command`

You command torque in motor-side N·m: `input_torque` over odrivetool or CAN. `G` converts that command into real wheel-side torque.

`G` has two parts: `G = belt_ratio × k`.

- `belt_ratio`: exact (4 for Calvin), because it's set by the pulley tooth counts and a toothed belt doesn't slip.
- `k`: the real motor torque per commanded torque, ideally 1.0. It isn't exactly 1 because the ODrive doesn't measure torque; it computes it as `torque_constant × Iq`. The motor's `torque_constant = 8.27 / 330` is a nominal figure derived from the motor's `Kv`. The real motor differs a bit (magnet strength, saturation at higher current, temperature). This experiment measures `k` directly.

So G ≈ 4, and the experiment tells you how far from 4.

## Configuration
- **Bench fixtureL:** lever arm and scale
- **Drivetrain:** **Motor only** Arm clamped to the motor shaft.
- **Firmware:** Teensy isn't needed. Driven from `odrivetool` over the ODrive's USB.
- **Connections:** ODrive USB → Mac
- **Power:** Battery

## Equipment
- Kitchen scale (grams); a rigid lever arm, ~0.2 m; something to raise the scale to shaft height.
- Clamp point: the motor's free shaft end.
- Ruler or calipers.

## Setup
1. Clamp the arm so it sticks out horizontally. It must not slip.
2. Put the scale under the arm's tip so the arm rests on it when level. Use a narrow contact point (a bolt head or an edge) so the length is well defined.
3. Measure `L`, from the shaft (or axle) center to the contact point, in meters.
4. With the motor idle, read the scale: this is the **tare**, the arm's resting weight.

## Procedure
1. Closed loop, torque mode. Command a small torque in the direction that pushes the arm down onto the scale.
2. For each level, e.g. 0.05, 0.10, 0.15, 0.20, 0.25 N·m motor-side (≈ 2–10 A; with a 0.2 m arm that's roughly 25–130 g on the scale, so a 1 g scale gives a few % at the low end and better above):
   - Set `odrv0.axis0.controller.input_torque`.
   - Wait about a second for the reading to settle.
   - Record the scale reading, `odrv0.axis0.motor.foc.Iq_measured` and `odrv0.vbus_voltage`.
   - Set `odrv0.axis0.controller.input_torque` back to 0. Keep each hold to **2–3 seconds** and pause between levels: a stalled motor heats quickly at these currents. Check the motor temperature between directions.
3. Idle the motor. Re-read the tare.
4. **Other direction:** move the scale to the other side of the axle (or flip the arm) and repeat with negative torques.
5. Optional: repeat each direction once more, approaching each level from a higher torque rather than from zero. The difference shows static friction (hysteresis).

## Analysis
1. **Tare:** average the readings from before (Setup step 4) and after (Procedure step 3). If they differ by more than a gram or two, the scale drifted; redo that direction.
2. **Measured torque at each level:** `F = (reading − tare) / 1000 × 9.81` N, then `τ = F × L` N·m (motor-side). Give `τ` the sign of the command, so the negative direction gives negative values.
3. **Fit each direction** by least squares: `τ = k × τ_command + c`.
   - `k` is the real torque per commanded torque. Expect it near 1.0.
   - `c` is an offset, mostly cogging torque at the rotor angle the arm sits at, plus tare error. It is **not** friction: with the shaft stalled, friction can take any value inside its stiction band, so it doesn't show up as a clean intercept. It should be small next to the torque levels.
   - Residuals should be a few % with no trend. If they curve down at the top, the motor is saturating; fit `k` on the straight part and note the torque where it bends.
4. **Combine:** `k = (k₊ + k₋) / 2`. The asymmetry `|k₊ − k₋| / k` should be within a few %.
5. **G:** `G = 4 × k` (the belt ratio). The arm is on the motor shaft, so this assumes the belt passes static torque without loss, which a toothed belt does at stall. Belt drag is a friction term, measured in experiments 3–5.
6. **Torque constant cross-check:** fit `τ = Kt × Iq_measured + c` the same way. Expect `Kt ≈ k × 0.0251` N·m/A. A mismatch means the current loop isn't delivering the commanded current; check `dump_errors` before trusting `k`.
7. **Stiction (optional, Procedure step 5):** at each level, half the difference between the from-above and from-below torques is the static friction torque.

**Record:** `L`, `k₊`, `k₋`, `k`, `G`, `Kt`, `c₊`, `c₋`, the largest residual, and the motor temperature.

## Pitfalls
- An arm that isn't level changes the effective length (cos error); within ±5° it's negligible.
- Belt stretch: the arm may creep as torque rises. Read once it has settled.
- Scales drift when warm or heavily loaded. Re-tare between directions.

## Done when
A `G` for each direction, close to each other (within a few %), with sensible residuals.
