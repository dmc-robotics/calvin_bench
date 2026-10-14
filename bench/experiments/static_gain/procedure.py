"""Recording experiment 2, step by step as in instructions/02-static-torque-gain.md (Procedure).

The ODrive driver owns the motor's safety; this module decides what to hold and when, reads the balance during
each hold (or asks for typed readings without one) and writes the rows through Run.
"""
import math
import statistics
import time
from contextlib import nullcontext
from dataclasses import asdict, dataclass

from bench import console
from bench.experiments.static_gain.data import DIRECTIONS, EXPERIMENT, Measurement, ScaleSample
from bench.hardware.odrive_usb import ODriveUsb, Signals
from bench.hardware.scale import Scale
from bench.runs import Run


@dataclass(frozen=True)
class Reading:
    """The scale reading for one tare or hold: a mean over the end of it, or a typed value (no spread or counts)."""
    grams: float
    std_g: float | None = None
    samples: int | None = None
    stable_samples: int | None = None

    def __str__(self):
        if self.samples is None:
            return f"{self.grams:.1f} g"
        return f"{self.grams:.1f} g ± {self.std_g:.1f} ({self.stable_samples}/{self.samples} stable)"


def record(settings):
    scale = Scale(settings.scale_port) if settings.scale_port else None
    if scale:
        print(f"Scale {scale.balance_id} (firmware {scale.firmware}) on {scale.port}.")
    print("Connecting to the ODrive over USB...")
    with scale or nullcontext(), ODriveUsb.connect(settings.motor, settings.highest_torque_Nm) as drive:
        identity = drive.identity()
        print(
            f"ODrive {identity['serial']}, node {identity['node_id']} ({settings.motor}). "
            f"Levels {', '.join(f'{level:.3f}' for level in settings.levels_Nm)} N·m, each held {settings.hold_s} s, both directions."
        )
        console.confirm("Arm clamped, scale in place, CAN unplugged (or Teensy off), area clear, e-stop in reach?")

        run = Run.create(EXPERIMENT, settings.motor, {
            "settings": asdict(settings),
            "odrive": identity,
            "velocity_cap_rev_per_s": drive.velocity_cap_rev_per_s,
            "scale": scale.identity() if scale else "manual",
        })
        run.write_json("odrive_config", drive.config())
        print(f"Recording to {run.directory}")

        recorder = Recorder(settings, drive, scale, run)
        for direction, sign in DIRECTIONS.items():
            console.confirm(f"\n{direction.capitalize()} direction: scale placed so {direction} torque pushes the arm onto it?")
            recorder.tare(direction)
            for approach in settings.approaches:
                for level in settings.levels_Nm:
                    recorder.level(direction, approach, sign * level)
            recorder.tare(direction, again=True)

    print(f"\nDone. Analyze with: bench analyze {run.directory}")


class Recorder:
    """The steps of one recording, writing a row for each. Keeps the rest timer between holds."""

    def __init__(self, settings, drive, scale, run):
        self.settings = settings
        self.drive = drive
        self.scale = scale
        self.run = run
        self._last_hold_end = -math.inf

    def tare(self, direction, again=False):
        """The arm's resting weight, motor idle."""
        self._rest()
        label = "Tare again" if again else "Tare"
        samples = []
        if self.scale:
            print(f"Motor idle. Reading the {label.lower()} for {self.settings.hold_s} s...")
            samples = [
                ScaleSample(direction, "tare", 0.0, round(time_s, 3), weight.grams, weight.stable)
                for time_s, weight in self.scale.sample(self.settings.hold_s)
            ]
        reading = self._reading(samples, label)
        self.run.append("data", measurement(direction, "tare", 0.0, reading, self.drive.temperatures()))
        print(f"  {label}: {reading}")

    def level(self, direction, approach, torque_Nm):
        """Hold one torque level and record it. Typing r instead of a reading repeats the hold."""
        label = f"{torque_Nm:+.3f} N·m ({approach})"
        reading = None
        while reading is None:
            temperatures = wait_until_cool(self.drive)
            self._rest()
            signals, samples = self._hold(direction, approach, torque_Nm)
            reading = self._reading(samples, label, allow_repeat=True)
        self.run.append("data", measurement(direction, approach, torque_Nm, reading, temperatures, signals))
        print(f"  {label}: {reading}, Iq {signals.iq_measured_A:+.2f} A, {temperatures}")

    def _hold(self, direction, approach, torque_Nm):
        """Hold `torque_Nm`, from above first if `approach` says so, polling the balance throughout.
        Returns (Signals averaged over the last sample_s, ScaleSamples)."""
        settings = self.settings
        weights = []

        def poll_scale():
            now = time.monotonic()
            weights.extend((now, weight) for weight in self.scale.poll())

        during = poll_scale if self.scale else None
        if self.scale:
            self.scale.clear()
        try:
            with self.drive.armed():
                if approach == "above":
                    self.drive.apply(torque_Nm + math.copysign(settings.overshoot_Nm, torque_Nm), settings.overshoot_s, during)
                started_at = time.monotonic()
                ticks = self.drive.apply(torque_Nm, settings.hold_s, during)
        finally:
            self._last_hold_end = time.monotonic()
        window_start = started_at + settings.hold_s - settings.sample_s
        signals = Signals(*map(statistics.fmean, zip(*(signals for when, signals in ticks if when >= window_start))))
        samples = [
            ScaleSample(direction, approach, torque_Nm, round(when - started_at, 3), weight.grams, weight.stable)
            for when, weight in weights
        ]
        return signals, samples

    def _reading(self, samples, label, allow_repeat=False):
        """The settled reading from the balance's samples, or a typed one when there's no scale or too few samples.
        None if they typed r to repeat."""
        if self.scale:
            self.run.append("scale", *samples)
            reading = settle(samples, self.settings.hold_s - self.settings.sample_s, self.settings.minimum_scale_readings)
            if reading:
                return reading
            question = f"{label}: too few scale readings. Type it (g)"
        else:
            question = f"{label}: scale reading (g)"
        grams = console.ask_number(f"{question}{', r to repeat' if allow_repeat else ''}: ", allow_repeat)
        return None if grams is None else Reading(grams)

    def _rest(self):
        time.sleep(max(0.0, self._last_hold_end + self.settings.rest_s - time.monotonic()))


def settle(samples, window_start_s, minimum):
    """Mean, spread and counts of the samples from `window_start_s` on, or None if there are fewer than `minimum`.
    The motor can keep the balance from ever reporting stable, so unstable readings count too; the stable count says how settled it was."""
    window = [sample for sample in samples if sample.time_s >= window_start_s]
    if len(window) < minimum:
        return None
    grams = [sample.scale_g for sample in window]
    return Reading(
        round(statistics.fmean(grams), 2), round(statistics.pstdev(grams), 2), len(window), sum(sample.stable for sample in window)
    )


def wait_until_cool(drive):
    while (temperatures := drive.temperatures()).too_hot:
        console.pause(f"Too hot ({temperatures}). Let it cool.")
    return temperatures


def measurement(direction, approach, torque_Nm, reading, temperatures, signals=None):
    iq_setpoint, iq_measured, vbus = (round(value, 4) for value in signals) if signals else (None, None, None)
    return Measurement(
        direction, approach, torque_Nm, reading.grams, reading.std_g, reading.samples, reading.stable_samples,
        iq_setpoint, iq_measured, vbus, temperatures.fet_C, temperatures.motor_C,
    )
