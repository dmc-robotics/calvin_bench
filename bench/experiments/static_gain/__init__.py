"""Experiment 2: static torque gain (instructions/02-static-torque-gain.md).

A lever arm on the motor shaft pushes on the OHAUS balance while the ODrive holds torque levels; the fit gives k, then G = 4 × k.
"""
from bench.experiments.static_gain.command import DESCRIPTION, NAME, add_arguments, analyze, record
