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
- **Firmware:** Teensy isn't needed. Driven by `bench static-gain record` over the ODrive's USB.
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
Recorded with `bench static-gain record`. It talks to the ODrive over USB, so close odrivetool first.

```sh
bench static-gain record --motor left --arm-length 0.200
```

Before anything moves, the script checks the ODrive and refuses to start if:
- the node ID doesn't match `--motor` (left 1, right 2), so it can't drive the wrong ODrive;
- it isn't in torque control + passthrough, or `enable_torque_mode_vel_limit` is off;
- the watchdog is off or its timeout isn't 0.05–0.2 s (experiment 1 turns it on).

While it runs:
- `vel_limit` is lowered to a few rev/s (enough headroom not to clip the torque at stall) and restored at the end. It isn't saved.
- The watchdog is fed during each hold. The motor is idle whenever the script waits for you. Ctrl-C idles it.
- If the shaft moves during a hold (the arm slipped or missed the scale), the motor idles and the run stops.
- Holds are at least 5 s apart, and it waits for you to let things cool if the FET passes 80 °C or the motor passes 60 °C. The motor temperature reads n/a if its thermistor isn't enabled on the ODrive.

1. Confirm the setup, confirm the scale is placed for the positive direction, and enter the tare (Setup step 4).
2. It steps through the levels: 0.05, 0.10, 0.15, 0.20, 0.25 N·m motor-side by default (`--levels` changes them; at least 3). That's ≈ 2–10 A; with a 0.2 m arm it's roughly 25–130 g on the scale, so a 1 g scale gives a few % at the low end and better above.
3. At each level it arms the motor, holds the torque for 2.5 s, then idles. **Watch the scale during the hold** and type the reading at the end of it; `r` repeats the level.
4. After the last level it asks for the tare again.
5. **Other direction:** move the scale to the other side of the axle (or flip the arm), confirm, and repeat from the tare.
6. Optional: `--from-above` adds a second pass per direction that approaches each level from 0.05 N·m higher. The difference shows static friction (hysteresis). The top level then reaches 0.30 N·m, so it also needs `--max-torque 0.3`.

Each run goes to `runs/<timestamp>_static-gain_<motor>/`:
- `meta.json`: settings fixed at the start (arm length, levels, ODrive serial and firmware, node ID, configured `torque_constant`, velocity cap). Written once.
- `odrive_config.json`: the full ODrive config, as `odrivetool backup-config` would save it.
- `data.csv`: every measurement, one row each, appended as it's taken. Columns `direction, approach, torque_command_Nm, scale_g, iq_setpoint_A, iq_measured_A, vbus_V, fet_temperature_C, motor_temperature_C`. `approach` is `tare` (motor idle, command 0, the Iq and vbus columns empty), `below` or `above`.

Without the script the same procedure works by hand in odrivetool: type the rows into `data.csv` and write `meta.json` with at least `arm_length_m` and `torque_constant_NmA`.

## Analysis
`bench static-gain analyze runs/<run_directory>` does all of this. It prints a report and writes `results.json` and `plot.png` (measured vs commanded torque with the fits, and the residuals) into the run folder.

1. **Tare:** average the `tare` readings from before and after. If they differ by more than a gram or two, the scale drifted; redo that direction.
2. **Measured torque at each level:** `F = (reading − tare) / 1000 × 9.81` N, then `τ = F × L` N·m (motor-side). Give `τ` the sign of the command, so the negative direction gives negative values.
3. **Fit each direction** by least squares: `τ = k × τ_command + c`.
   - `k` is the real torque per commanded torque. Expect it near 1.0.
   - `c` is an offset, mostly cogging torque at the rotor angle the arm sits at, plus tare error. It is **not** friction: with the shaft stalled, friction can take any value inside its stiction band, so it doesn't show up as a clean intercept. It should be small next to the torque levels.
   - Residuals should be a few % with no trend. If they curve down at the top, the motor is saturating; fit `k` on the straight part and note the torque where it bends.
4. **Combine:** `k = (k₊ + k₋) / 2`. The asymmetry `|k₊ − k₋| / k` should be within a few %.
5. **G:** `G = 4 × k` (the belt ratio). The arm is on the motor shaft, so this assumes the belt passes static torque without loss, which a toothed belt does at stall. Belt drag is a friction term, measured in experiments 3–5.
6. **Torque constant cross-check:** fit `τ = Kt × Iq_measured + c` the same way. Expect `Kt ≈ k ×` the configured `torque_constant` (0.0251 N·m/A). Separately, `iq_setpoint_A × torque_constant` should equal the command; if it doesn't, the torque was clipped (current limit or velocity cap) and `k` is wrong. The analyzer warns about both.
7. **Stiction (optional, Procedure step 5):** at each level, half the difference between the from-above and from-below torques is the static friction torque.

**Record:** the run folder holds it all: `L` in `meta.json`, temperatures in `data.csv`, the ODrive config (including anticogging) in `odrive_config.json`; `k₊`, `k₋`, `k`, `G`, `Kt`, `c₊`, `c₋`, residuals and stiction in `results.json`.

## Pitfalls
- An arm that isn't level changes the effective length (cos error); within ±5° it's negligible.
- Belt stretch: the arm may creep as torque rises. Read once it has settled.
- Scales drift when warm or heavily loaded. Re-tare between directions.

## Done when
A `G` for each direction, close to each other (within a few %), with sensible residuals.
