"""Prompts for the person at the bench. Procedures print their own progress lines; every question goes through here."""
import math

from bench.errors import BenchError

REPEAT = object()  # what ask_number returns when they type r


def confirm(question):
    """Continue on y, abort the run on anything else."""
    if input(f"{question} [y/N] ").strip().lower() != "y":
        raise BenchError("Aborted.")


def ask_number(prompt, allow_repeat=False):
    """A finite number typed in, or REPEAT if `allow_repeat` and they type r."""
    while True:
        answer = input(prompt).strip().lower()
        if allow_repeat and answer == "r":
            return REPEAT
        try:
            value = float(answer)
        except ValueError:
            value = math.nan
        if math.isfinite(value):
            return value
        print("  Enter a number" + (", or r." if allow_repeat else "."))


def pause(message):
    input(f"{message} Press Enter to continue.")
