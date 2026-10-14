"""Argument types shared by the experiments' command lines."""
import argparse
import math


def positive_number(text):
    value = float(text)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError(f"{text} isn't a positive number")
    return value
