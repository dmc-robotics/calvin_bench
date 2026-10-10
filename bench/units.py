"""Conversion from ODrive units (rev, rev/s, motor-side N·m) to SI at the wheel.

The only place unit conversion happens.
"""
BELT_RATIO = 4.0
STANDARD_GRAVITY = 9.80665  # m/s²


def grams_to_newtons(grams):
    return grams / 1000 * STANDARD_GRAVITY
