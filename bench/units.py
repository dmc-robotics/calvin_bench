"""Conversion from ODrive units to SI: angles and speeds (rev, rev/s) to the wheel side in rad and rad/s.

The only place unit conversion happens. Torques stay in commanded motor-side N·m through every analysis;
`bench export` applies the measured G once (PLAN, Torque units through analysis).
"""
BELT_RATIO = 4.0
STANDARD_GRAVITY = 9.80665  # m/s²


def grams_to_newtons(grams):
    return grams / 1000 * STANDARD_GRAVITY
