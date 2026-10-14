# 2. Static Torque Gain (G)

`τ_wheel = G × τ_command`

You command torque in motor-side N·m: `input_torque` over odrivetool or CAN. `G` converts that command into real wheel-side torque.

`G` has two parts: `G = belt_ratio × k`.

- `belt_ratio`: exact (4 for Calvin), because it's set by the pulley tooth counts and a toothed belt doesn't slip.
- `k`: the real motor torque per commanded torque, ideally 1.0. It isn't exactly 1 because the ODrive doesn't measure torque; it computes it as `torque_constant × Iq`. The motor's `torque_constant = 8.27 / 330` is a nominal figure derived from the motor's `Kv`. The real motor differs a bit (magnet strength, saturation at higher current, temperature). This experiment measures `k` directly.

So G ≈ 4, and the experiment tells you how far from 4.

## Configuration
- **Bench fixture:** lever arm and scale
- **Drivetrain:** **Motor only** Arm clamped to the motor shaft.
- **Firmware:** Teensy isn't needed. Driven by `bench record static-gain` over the ODrive's USB. **Unplug CAN from the ODrive (or power the Teensy off):** a CAN host can override the torque command or keep feeding the watchdog.
- **Connections:** ODrive USB → Mac; the balance's USB Device port (the square USB-B socket) → Mac
- **Power:** Battery

## Equipment
- Scale: the OHAUS Adventurer AX8201/E (0.1 g), read by the script over USB. Any gram scale works if you type the readings in.
- A rigid lever arm.
- Clamp point: the motor's free shaft end.
- Ruler or calipers.

## Setup
1. **Balance:** switch it on at least an hour ahead (the manual's warm-up for best accuracy) and set it to grams. On its touchscreen: Auto Tare, Auto Off and Auto Standby off (a balance that tares itself or sleeps mid-run spoils or stops the run); Communication > Print Settings > Print Output: Output Format OHAUS, Numeric Value Only off. The script turns any auto-print off when it connects.
2. Clamp the arm so it sticks out horizontally. It must not slip.
3. Put the scale under the arm's tip so the arm rests on it when level. Use a narrow contact point (a bolt head or an edge) so the length is well defined.
4. Measure `L`, from the shaft (or axle) center to the contact point, in meters.
5. With the motor idle, the scale reads the **tare**, the arm's resting weight. The script reads it; don't zero the balance with the arm on it, or its auto-zero tracking can creep the near-zero readings.

## Procedure
Recorded with `bench record static-gain`. It talks to the ODrive over USB, so close `odrivetool` first.

```sh
bench record static-gain --motor left --arm-length 0.200
```

It reads the balance on `/dev/cu.usbserial-DN04KNBY`, named after the balance's own USB chip, so it doesn't change; `--scale <port>` overrides it. Set the balance to grams. With `--no-scale`, the script asks you to type each reading instead.

Before connecting, it refuses bad settings, for example an arm length of 1 m or more (millimeters typed as meters), fewer than 3 distinct levels, or levels above `--max-torque`.

Before anything moves, the script checks the ODrive and refuses to start if:
- the node ID doesn't match `--motor` (left 1, right 2), so it can't drive the wrong ODrive;
- it isn't in torque control + passthrough, or `enable_torque_mode_vel_limit` is off;
- `vel_gain` isn't positive, or is so low that the velocity cap needed to hold the top level without clipping would be above 5 rev/s;
- `torque_constant` isn't positive, or the top level needs more current than `current_soft_max`;
- the watchdog is off or its timeout isn't 0.1–0.2 s.

It lists every problem at once. Fix them in odrivetool (experiment 1 sets all of these), save the config, and rerun.

While it runs:
- `vel_limit` is lowered to a few rev/s (enough headroom not to clip the torque at stall) and restored at the end. It isn't saved.
- The watchdog is fed during each hold. The motor is idle whenever the script waits for you. Ctrl-C idles it.
- If the shaft moves during a hold (the arm slipped or missed the scale), the motor idles and the run stops.
- If anything (usually reading the balance) holds up the loop so the watchdog goes more than half its timeout without a feed, the motor idles and the run stops, before the ODrive's watchdog trips.
- If the balance refuses to answer (standby, calibrating) or switches away from grams, the motor idles and the run stops with the reason.
- Holds are at least 5 s apart, and it waits for you to let things cool if the FET passes 80 °C or the motor passes 60 °C; the driver itself won't arm a motor that hot. The motor temperature reads n/a if its thermistor isn't enabled on the ODrive.

1. Confirm the setup and that the scale is placed for the positive direction. It reads the tare (Setup step 5).
2. It steps through the levels: 0.05, 0.10, 0.15, 0.20, 0.25 N·m motor-side by default (`--levels` changes them; at least 3). That's ≈ 2–10 A; with a 0.2 m arm it's roughly 25–130 g on the scale, so a 1 g scale gives a few % at the low end and better above.
3. At each level it arms the motor, holds the torque for 3 s, then idles. It polls the balance through the hold (~8 readings/s) and averages the last second, which starts 0.5 s after the balance's typical 1.5 s settling time. Unstable readings count too, since the motor may keep the balance from ever settling. It prints the mean ± standard deviation and how many readings were stable. With `--no-scale`, watch the scale and type the reading at the end of the hold; `r` repeats the level.
4. After the last level it reads the tare again.
5. **Other direction:** move the scale to the other side of the axle (or flip the arm), confirm, and repeat from the tare.
6. Optional: `--from-above` adds a second pass per direction that approaches each level from 0.05 N·m higher. The difference shows static friction (hysteresis). The top level then reaches 0.30 N·m, so it also needs `--max-torque 0.3`.

Each run goes to `runs/<timestamp>_static-gain_<motor>/`:
- `meta.json`: written once at the start. `experiment` and `motor`; `settings` (every setting of the recording: arm length, levels, hold and averaging times, scale port…); `odrive` (serial, firmware, node ID, configured `torque_constant_NmA`); `velocity_cap_rev_per_s`; `scale` (the balance's port, ID and firmware, or `manual`).
- `odrive_config.json`: the full ODrive config, as `odrivetool backup-config` would save it.
- `data.csv`: every measurement, one row each, appended as it's taken. Columns `hold, direction, approach, torque_command_Nm, scale_g, scale_std_g, scale_samples, scale_stable_samples, iq_setpoint_A, iq_measured_A, vbus_V, fet_temperature_C, motor_temperature_C`. `approach` is `tare` (motor idle, command 0, the Iq and vbus columns empty), `below` or `above`. `hold` numbers every tare and hold in the run from 0; a repeated hold (`r`) uses up a number and has no row. `scale_g` is the mean over the last second; the spread and counts are empty for typed readings.
- `scale.csv` (not with `--no-scale`): every balance reading, `hold, direction, approach, torque_command_Nm, time_s, scale_g, stable`. `hold` is the tare or hold it was read during, the same number as its `data.csv` row (repeated holds have no row). `time_s` counts from when the torque was applied (negative during a from-above overshoot); `stable` is `True` or `False`. Use it to check the balance settles before the averaged last second.

Without the script the same procedure works by hand in odrivetool: type the rows into `data.csv` (every column above, numbering the `hold`s yourself; the spread, counts and motor temperature can be empty) and write `meta.json` with at least `{"experiment": "static-gain", "settings": {"arm_length_m": …}, "odrive": {"torque_constant_NmA": …}}`.

## Analysis
`bench analyze runs/<run_directory>` does all of this. It prints a report and writes `results.json` and `plot.png` (measured vs commanded torque with the fits, and the residuals) into the run folder.

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

## Done when
A `G` for each direction, close to each other (within a few %), with sensible residuals.
