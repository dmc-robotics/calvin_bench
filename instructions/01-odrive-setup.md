# 1. ODrive Setup and Frozen Configuration

**Goal:** A calibrated ODrive with a known, saved configuration. Every other experiment depends on it, and changing the config later (current-loop bandwidth, estimator bandwidth, anticogging, limits) changes the actuator you're measuring.

**When:** M0. Repeat for the second ODrive.

## Configuration
- **Where:** **Bench fixture**
- **Drivetrain:** Motor only
- **Firmware:** None on the Teensy (it isn't needed). Driven from odrivetool over the ODrive's USB. Instinctus not used
- **Connections:** ODrive USB → Mac
- **Power:** Battery
- **Motors:** One at a time; repeat for the second ODrive

## Equipment
- ODrive S1 + D5312s + ODrive OA1 mounted on the bench rig. The belt and wheel aren't needed until experiment 2. 2 Ω 50 W brake resistor per S1. Battery; USB cable to the Mac with Isolator.
- `odrivetool` (`uv tool install odrive`) and ODrive's web GUI.

## Procedure
Commands run in the `odrivetool` shell unless noted.


**GUI Config**
Update the firmware and follow the GUI Wizard, then check every value below. Skip velocity and position tuning: torque control doesn't use those gains, so leave `vel_gain` and `vel_integrator_gain` at their defaults (1/6 and 1/3).

**Power and safety** 

Each S1 has its own 2 Ω 50 W brake resistor (it ships with the S1) soldered to its R+ and R− pads. Mount it on metal, away from the LiPo and wiring. Regen up to `max_regen_current` goes into the battery and the resistor dissipates the rest, so it only warms during hard braking. The `dc_max_negative_current` trip is a backstop: it fires only if the resistor saturates (above roughly 220 W of braking at 16 V), a fast transient beats it, or the resistor isn't working. Leave DC bus voltage feedback off; ODrive's recommended ramp starts above the 17.0 V overvoltage trip.

```python
odrv0.config.dc_bus_overvoltage_trip_level = 18.0 # 4S full is 16.8 V. Start sessions below full charge; regen raises the bus voltage.
odrv0.config.dc_bus_undervoltage_trip_level = 13.0
odrv0.config.dc_max_positive_current = 40 # Wiring, connectors, fuse and e-stop contact must be rated for it.
odrv0.config.dc_max_negative_current = -7 # Keep smaller than the 1C battery limit (7.2 A).
odrv0.config.brake_resistor0.resistance = 2.0
odrv0.config.brake_resistor0.enable = True
odrv0.config.max_regen_current = 5.0 # Positive (unlike dc_max_negative_current). Battery takes regen up to here. Keep it about 2 A inside dc_max_negative_current.
```

**E-stop input**

A second normally-closed (NC) contact on the e-stop button goes to an ODrive GPIO configured as the min endstop. Pressing the button disarms the axis with `ESTOP_REQUESTED` (the motor coasts), and it stays disarmed until the errors are cleared. This adds to the battery disconnect; it doesn't replace it. It depends on the ODrive's firmware and config, and ODrive says endstops used as an e-stop are not SIL safety rated.

```
G11 ──── NC contact ──── GND
```
- G11 is one of the S1's Hall pins: input capable, with a 2.7 kΩ hardware pull-up to +5 V and a low-pass filter. The closed contact holds it low; pressing the button, or a broken wire, lets it go high and triggers the stop. No external resistor is needed.
- Wire a dry contact only: nothing but the switch and GND on the pin. All S1 GPIOs are 5 V tolerant (except isolated pins with the isolator on 3.3 V).
- G11 is free as long as no Hall sensors are wired; the OA1 encoder uses the RS485 port.
- Other pins work too; change the `11`s below. G1 and G2 are identical to G11. G3, G9 and G10 (ENC0) have the same pull-up but only if no ABZ encoder uses them. The isolated inputs G5, G7 and G8 need V+ ISO powered and an external pull-up, because the pull-up modes do nothing on them.
- Second ODrive: its own NC contact on the same button, to its own G11.

```python
odrv0.config.gpio11_mode = GpioMode.DIGITAL # The hardware pull-up makes DIGITAL_PULL_UP redundant.
odrv0.axis0.min_endstop.config.gpio_num = 11
odrv0.axis0.min_endstop.config.is_active_high = True # Pressed = contact open = high.
odrv0.axis0.min_endstop.config.debounce_ms = 50
odrv0.axis0.min_endstop.config.enabled = True
odrv0.save_configuration() # Required for endstop changes to take effect. The board reboots.
odrv0.axis0.min_endstop.state # After the reboot: False released, True pressed.
```

**Motor and encoder**

The GUI Wizard's D5312s and OA1 choices set most of these.
```python
odrv0.axis0.config.motor.motor_type = MotorType.PMSM_CURRENT_CONTROL
odrv0.axis0.config.motor.pole_pairs = 7
odrv0.axis0.config.motor.torque_constant = 8.27 / 330
odrv0.axis0.config.motor.current_soft_max = 10 # Bench torque limit: 0.25 N·m motor-side. Raise only when an experiment needs it.
odrv0.axis0.config.motor.current_hard_max = 20
odrv0.axis0.config.motor.calibration_current = 10
odrv0.axis0.config.motor.resistance_calib_max_voltage = 2
odrv0.rs485_encoder_group0.config.mode = Rs485EncoderMode.ODRIVE_OA1
odrv0.axis0.config.load_encoder = EncoderId.RS485_ENCODER0
odrv0.axis0.config.commutation_encoder = EncoderId.RS485_ENCODER0
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
odrv0.can.config.baud_rate = 0 # Automatic baud rate detection; locks onto the Teensy's 1 Mbit/s.
odrv0.axis0.config.can.node_id = 1 # 1 left, 2 right.
odrv0.axis0.config.can.encoder_msg_rate_ms = 1
odrv0.axis0.config.can.iq_msg_rate_ms = 1
odrv0.axis0.config.can.torques_msg_rate_ms = 1
odrv0.axis0.config.can.bus_voltage_msg_rate_ms = 1000
odrv0.axis0.config.can.temperature_msg_rate_ms = 1000
odrv0.axis0.config.can.heartbeat_msg_rate_ms = 100
odrv0.axis0.config.can.error_msg_rate_ms = 100
```

**Watchdog**
```python
odrv0.axis0.config.watchdog_timeout = 0.1 # Enabled after the smoke test.
```

**Anticogging**

Off (`anticogging.enabled = False`, `ac-off` in the backup name). Characterize with the setting you'll actually run on the robot; turning it on later means a new configuration.

**Smoke test**
```python
odrv0.axis0.requested_state = AxisState.CLOSED_LOOP_CONTROL
odrv0.axis0.controller.input_torque = 0.02 # The motor should turn gently.
odrv0.axis0.controller.input_torque = 0
odrv0.axis0.requested_state = AxisState.IDLE
```

**E-stop test**

Arm again at a small torque, then press the e-stop. The motor should stop driving.
```python
odrv0.axis0.requested_state = AxisState.CLOSED_LOOP_CONTROL
odrv0.axis0.controller.input_torque = 0.02
# Press the e-stop.
dump_errors(odrv0) # Should show ESTOP_REQUESTED and the axis idle.
odrv0.axis0.controller.input_torque = 0
# Release the e-stop.
odrv0.clear_errors()
```
Repeat with the e-stop wire unplugged at the ODrive instead of pressing the button; it should trip the same way.

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
odrivetool backup-config odrive/<left|right>_<YYYY-MM-DD>_v<firmware>_ac-<on|off>.json # From the Mac shell.
```

## Pitfalls
- Any later config change means saving a new backup file and treating earlier runs as a different configuration.
- `erase_configuration()` also removes the e-stop input and the brake resistor config. Redo them, and the e-stop test, after any erase.
- `DC_BUS_OVER_REGEN_CURRENT` means braking harder than the battery and resistor can absorb, or the resistor isn't working. `BRAKE_RESISTOR_DISARMED` means it saturated or faulted.

## Done when
The motor spins in torque mode from odrivetool, `dump_errors` is clean, the e-stop test disarms the axis (button and unplugged wire), and the backup file is saved in `odrive/`.
