"""Unit conversions. So far: grams on the scale to newtons.

ODrive's rev and rev/s to rad and rad/s join when an experiment needs them. Torques stay in commanded motor-side N·m
through every analysis; `bench export` applies the measured G once (PLAN, Torque units through analysis).
"""
STANDARD_GRAVITY = 9.80665  # m/s²


def grams_to_newtons(grams):
    return grams / 1000 * STANDARD_GRAVITY
