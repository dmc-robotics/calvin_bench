# 1. ODrive Setup and Frozen Configuration

**Gives:** a calibrated ODrive with a known, saved configuration. Every other experiment depends on it, and changing the config later (current-loop bandwidth, estimator bandwidth, anticogging, limits) changes the actuator you're measuring.

**When:** M0. Repeat for the second ODrive.

## Configuration
- **Where:** **Bench fixture**
- **Drivetrain:** Motor only
- **Firmware:** None on the Teensy (it isn't needed). Driven from odrivetool over the ODrive's USB. Instinctus not used
- **Connections:** ODrive USB → Mac
- **Power:** Battery
- **Motors:** One at a time; repeat for the second ODrive

## Equipment
- ODrive S1 + D5312s + ODrive OA1 mounted on the bench rig. The belt and wheel aren't needed until experiment 2. Battery or bench supply; USB cable to the Mac.
- `odrivetool` (`pip install odrive`), or ODrive's web GUI.

## Procedure
Commands run in the `odrivetool` shell unless noted.

**Connect and update**
```python
odrivetool # From the Mac shell, with the S1 powered and USB plugged in.
odrivetool dfu # From the Mac shell (or use the web GUI). Update to the latest firmware. Will wipe config
```
**Start clean**
```python
odrv0.erase_configuration() # The board reboots.
```

**Power and safety**
```python
odrv0.config.dc_bus_overvoltage_trip_level = 17.5 # 4S full is 16.8 V.
odrv0.config.dc_bus_undervoltage_trip_level = 13.0
odrv0.config.dc_max_negative_current = -2 # Keep small (−1 to −3 A) unless the battery and wiring can take more regen.
```

**Motor and encoder**

Use ODrive's D5312s preset if the web GUI offers one; otherwise set the motor type, pole pairs and current limits from ODrive's D5312s data sheet, and the encoder per ODrive's setup guide for your encoder.
```python
odrv0.axis0.config.motor.torque_constant = 8.27 / 330
```

**Calibrate**
```python
odrv0.axis0.requested_state = AxisState.FULL_CALIBRATION_SEQUENCE # Motor must spin freely, ideally unloaded.
dump_errors(odrv0) # Should be clean.
```

**Control mode**
```python
odrv0.axis0.controller.config.control_mode = ControlMode.TORQUE_CONTROL
odrv0.axis0.controller.config.input_mode = InputMode.PASSTHROUGH
odrv0.axis0.controller.config.vel_limit = 50 # Safety cap, rev/s motor-side. Torque mode cuts torque near vel_limit.
odrv0.axis0.controller.config.enable_torque_mode_vel_limit = True # Safety net. Experiments near vel_limit must account for it.
```

**CAN**
```python
odrv0.can.config.baud_rate = 1000000
odrv0.axis0.config.can.node_id = 1 # 1 left, 2 right.
odrv0.axis0.config.can.encoder_msg_rate_ms = 1
odrv0.axis0.config.can.iq_msg_rate_ms = 1
odrv0.axis0.config.can.torques_msg_rate_ms = 1
odrv0.axis0.config.can.bus_voltage_msg_rate_ms = 10
odrv0.axis0.config.can.temperature_msg_rate_ms = 100
odrv0.axis0.config.can.heartbeat_msg_rate_ms = 100
odrv0.axis0.config.can.error_msg_rate_ms = 100
```

**Watchdog**
```python
odrv0.axis0.config.watchdog_timeout = 0.1 # Enabled after the smoke test.
```

**Anticogging**

Decide now. If you want it, run the anticogging calibration (see ODrive docs) and enable it. Characterize with the setting you'll actually run on the robot.

**Smoke test**
```python
odrv0.axis0.requested_state = AxisState.CLOSED_LOOP_CONTROL
odrv0.axis0.controller.input_torque = 0.02 # The motor should turn gently.
odrv0.axis0.controller.input_torque = 0
odrv0.axis0.requested_state = AxisState.IDLE
```

**Enable watchdog**
```python
odrv0.axis0.config.enable_watchdog = True # Fed by CAN torque commands; leave False while driving from odrivetool. odrv0.clear_errors()  clears tripped error.
```

**Save**
```python
odrv0.save_configuration()
```

**Freeze it**
```sh
odrivetool backup-config ../odrive/<left|right>-<YYYY-MM-DD>.json # From the Mac shell.
```

## Record
- Firmware version, the backup file, whether anticogging is on, and the node ID.

## Pitfalls
- Any later config change means saving a new backup file and treating earlier runs as a different configuration.

## Done when
The motor spins in torque mode from odrivetool, `dump_errors` is clean, and the backup file is saved in `odrive/`.
