# 8. Torque-Speed Limit

**Gives:** how much torque is actually available at each speed at nominal 4S voltage. As speed rises, the motor's back-EMF eats into the battery voltage until the ODrive can't push the commanded current. LQR uses this to choose how hard it may command and to check gains won't saturate.

**When:** bench CLI (M3+). **Battery** at nominal charge (~15–15.5 V). Wheel off the ground, guarded: this test reaches high speed.

## Configuration
- **Where:** **Robot on a stand**, wheels off the ground (chassis supported so both wheels spin freely), motors installed as they'll run. Guard the wheels: this test reaches high speed
- **Drivetrain:** Motor + belt + wheel
- **Firmware:** **Bench sketch** on the Teensy (`firmware/bench`, flashed in place of instinctus). Instinctus not used
- **Connections:** Teensy USB → Mac, Teensy ↔ ODrive over CAN
- **Power:** Battery, at nominal charge (~15–15.5 V)
- **Motors:** One at a time

## Procedure
1. Raise the velocity limit for this test only, to just below the motor's no-load speed (~80 rev/s at 16.8 V; lower as the battery sags). Keep a hand on the e-stop.
2. Command a large torque (e.g. 70–80% of the current limit) from rest and let the wheel accelerate. Then go to zero torque and coast down, or command negative torque gently.
3. Repeat in the other direction.
4. Restore the normal velocity limit afterwards.

## Analysis
- Plot Iq_measured vs Iq_setpoint against speed. Where measured falls below setpoint, the voltage limit has been reached. That curve × torque constant (× G) is the available torque vs speed.
- Note the bus voltage during the run, since the limit scales roughly with it.

## Pitfalls
- Braking from high speed regenerates a lot of energy. Battery only, and keep `dc_max_negative_current` sensible.
- Motor and FET temperature: watch them; this test draws the most power.

## Done when
An available-torque-vs-speed curve at the recorded bus voltage, for each direction.
