# 1. ODrive Setup and Frozen Configuration

**Gives:** a calibrated ODrive with a known, saved configuration. Every other experiment depends on it, and changing the config later (current-loop bandwidth, estimator bandwidth, anticogging, limits) changes the actuator you're measuring.

**When:** M0. Repeat for the second ODrive.

## Configuration
- **Where:** **Bench fixture**
- **Drivetrain:** Motor only, belt off or slack
- **Firmware:** None on the Teensy (it isn't needed). Driven from odrivetool over the ODrive's USB. Instinctus not used
- **Connections:** ODrive USB → Mac
- **Power:** Battery
- **Motors:** One at a time; repeat for the second ODrive

## Equipment
- ODrive S1 + D5312s mounted on the bench rig, **motor only** (belt off or slack). The belt and wheel aren't needed until experiment 2. Battery or bench supply; USB cable to the Mac.
- `odrivetool` (`pip install odrive`), or ODrive's web GUI.

## Procedure
1. **Connect and update.** Power the S1, plug in USB, run `odrivetool`. Update to the latest firmware (`odrivetool dfu`, or the web GUI) before configuring; an update can reset the config.
2. **Start clean.** `odrv0.erase_configuration()` (the board reboots).
3. **Power and safety settings:**
   - `odrv0.config.dc_bus_overvoltage_trip_level` ≈ 17.5 V (4S full is 16.8 V)
   - `odrv0.config.dc_bus_undervoltage_trip_level` ≈ 13.0 V
   - `odrv0.config.dc_max_negative_current` small (e.g. −1 to −3 A) unless you know the battery and wiring can take more regen.
4. **Motor and encoder.** Use ODrive's preset for the D5312s if the web GUI offers one; otherwise set the motor type, pole pairs and current limits from ODrive's D5312s data sheet, and the encoder per ODrive's setup guide for your encoder. Set `odrv0.axis0.config.motor.torque_constant = 8.27 / 330`.
5. **Calibrate:** `odrv0.axis0.requested_state = AxisState.FULL_CALIBRATION_SEQUENCE`. The motor must spin freely, ideally unloaded: the encoder-offset step turns it slowly, and a heavy load can throw the result off. Check `dump_errors(odrv0)` afterwards.
6. **Control mode:**
   - `odrv0.axis0.controller.config.control_mode = ControlMode.TORQUE_CONTROL`
   - `odrv0.axis0.controller.config.input_mode = InputMode.PASSTHROUGH`
   - **Velocity limit in torque mode:** by default ODrive cuts torque near `vel_limit`, which defaults to a low value. Set `odrv0.axis0.controller.config.vel_limit` to a deliberate safety cap (e.g. 50 rev/s motor-side) and keep `enable_torque_mode_vel_limit` on as a safety net. Know that it reduces torque near that speed; experiments that approach it must account for it.
7. **CAN:**
   - `odrv0.can.config.baud_rate = 1000000`
   - `odrv0.axis0.config.can.node_id = 1` (left) or `2` (right)
   - Message rates (`odrv0.axis0.config.can.*`): `encoder_msg_rate_ms = 1`, `iq_msg_rate_ms = 1`, `torques_msg_rate_ms = 1`, `bus_voltage_msg_rate_ms = 10`, `temperature_msg_rate_ms = 100`, `heartbeat_msg_rate_ms = 100`, `error_msg_rate_ms = 100`
8. **Watchdog:** `odrv0.axis0.config.enable_watchdog = True`, `odrv0.axis0.config.watchdog_timeout = 0.1`. It's fed by torque commands over CAN. Leave it **off** while driving the motor from odrivetool (nothing feeds it there) and turn it on before CAN control.
9. **Anticogging:** decide now. If you want it, run the anticogging calibration (see ODrive docs) and enable it. Characterize with the setting you'll actually run on the robot.
10. **Save:** `odrv0.save_configuration()`.
11. **Smoke test:** `odrv0.axis0.requested_state = AxisState.CLOSED_LOOP_CONTROL`, then `odrv0.axis0.controller.input_torque = 0.02`. The motor should turn gently. Set it back to `0`, then `odrv0.axis0.requested_state = AxisState.IDLE`.
12. **Freeze it:** `odrivetool backup-config ../odrive/<left|right>-<YYYY-MM-DD>.json`.

## Record
- Firmware version, the backup file, whether anticogging is on, and the node ID.

## Pitfalls
- Any later config change means saving a new backup file and treating earlier runs as a different configuration.

## Done when
The motor spins in torque mode from odrivetool, `dump_errors` is clean, and the backup file is saved in `odrive/`.
