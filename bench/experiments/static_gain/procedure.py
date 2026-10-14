"""Recording experiment 2, step by step as in instructions/02-static-torque-gain.md (Procedure)."""
import math
import statistics
import time
from contextlib import nullcontext
from dataclasses import asdict, dataclass

from bench import console
from bench.errors import BenchError
from bench.experiments.static_gain.data import DIRECTIONS, NAME, Measurement, ODriveSample, ScaleSample
from bench.hardware.odrive_usb import ODriveUsb, Signals
from bench.hardware.ohaus_adventurer import OhausAdventurer
from bench.runs import Run


@dataclass(frozen=True)
class Reading:
    """The scale reading for one tare or hold: a mean over the end of it, or a typed value (no spread or counts)."""
    grams: float
    standard_deviation_g: float | None = None
    samples: int | None = None
    stable_samples: int | None = None

    def __str__(self):
        if self.samples is None:
            return f"{self.grams:.1f} g"
        return f"{self.grams:.1f} g ± {self.standard_deviation_g:.1f} ({self.stable_samples}/{self.samples} stable)"


def record(settings):
    print("Connecting over USB...")
    scale_connection = OhausAdventurer.connect(settings.scale_port, unit="g") if settings.scale_port else nullcontext()
    with scale_connection as scale, ODriveUsb.connect(settings.motor, settings.highest_torque_Nm) as drive:
        if scale:
            print(f"Scale {scale.balance_id} (firmware {scale.firmware}) on {scale.port}.")
        identity = drive.identity()
        print(
            f"ODrive {identity['serial']}, node {identity['node_id']} ({settings.motor}). "
            f"Levels {', '.join(f'{level:.3f}' for level in settings.levels_Nm)} N·m, each held {settings.hold_s} s, both directions."
        )
        console.confirm("Arm clamped, scale in place, CAN unplugged (or Teensy off), area clear, e-stop in reach?")

        run = Run.create(NAME, settings.motor, {
            "settings": asdict(settings),
            "odrive": identity,
            "velocity_cap_rev_per_s": drive.velocity_cap_rev_per_s,
            "scale": scale.identity() if scale else None,  # None: typed in
        })
        run.write_json("odrive_config", drive.configuration)
        print(f"Recording to {run.directory}")

        session = Session(settings, drive, scale, run)
        for direction, sign in DIRECTIONS.items():
            console.confirm(f"\n{direction.capitalize()} direction: scale placed so {direction} torque pushes the arm onto it?")
            session.tare(direction)
            for approach in settings.approaches:
                for level in settings.levels_Nm:
                    session.level(direction, approach, sign * level)
            session.tare(direction, again=True)
        run.finish()

    print(f"\nDone. Analyze with: bench analyze {run.directory}")


class Session:
    """The steps of one recording, writing a row for each. Numbers every tare and hold, and keeps the rest timer between holds."""

    def __init__(self, settings, drive, scale, run):
        self.settings = settings
        self.drive = drive
        self.scale = scale
        self.run = run
        self._holds = 0
        self._last_hold_end = -math.inf

    def tare(self, direction, again=False):
        """The arm's resting weight, motor idle."""
        self._rest()
        hold = self._next_hold()
        label = "Tare again" if again else "Tare"
        samples = []
        if self.scale:
            print(f"Motor idle. Reading the {label.lower()} for {self.settings.hold_s} s...")
            samples = [
                ScaleSample(hold, direction, "tare", 0.0, round(time_s, 3), weight.value, weight.stable, weight.net)
                for time_s, weight in self.scale.sample(self.settings.hold_s)
            ]
        self.run.append("scale", *samples)
        reading = self._reading(samples, label)
        self.run.append("data", measurement(hold, direction, "tare", 0.0, reading, self.drive.temperatures()))
        print(f"  {label}: {reading}")

    def level(self, direction, approach, torque_Nm):
        """Hold one torque level and record it. Typing r instead of a reading repeats the hold under a new number."""
        label = f"{torque_Nm:+.3f} N·m ({approach})"
        while True:
            wait_until_cool(self.drive)
            self._rest()
            hold = self._next_hold()
            signals, scale_samples, largest_feed_gap_s = self._hold(hold, direction, approach, torque_Nm)
            temperatures = self.drive.temperatures()
            reading = self._reading(scale_samples, label, allow_repeat=True)
            if reading is not console.REPEAT:
                break
        self.run.append("data", measurement(hold, direction, approach, torque_Nm, reading, temperatures, signals))
        print(f"  {label}: {reading}, Iq {signals.iq_measured_A:+.2f} A, {temperatures}, feed gap ≤ {1000 * largest_feed_gap_s:.0f} ms")

    def _next_hold(self):
        hold = self._holds
        self._holds += 1
        return hold

    def _hold(self, hold, direction, approach, torque_Nm):
        """Hold `torque_Nm`, from above first if `approach` says so, polling the balance throughout. Every balance
        reading and ODrive tick goes to scale.csv and odrive.csv, even if the hold aborts.
        Returns (Signals averaged over the last sample_s, ScaleSamples, the largest gap between watchdog feeds)."""
        settings = self.settings
        weights = []
        ticks = []
        started_at = None

        def poll_scale():
            now = time.monotonic()
            weights.extend((now, weight) for weight in self.scale.poll())

        during = poll_scale if self.scale else None
        if self.scale:
            self.scale.clear()
        try:
            with self.drive.armed():
                if approach == "above":
                    self.drive.apply(torque_Nm + math.copysign(settings.overshoot_Nm, torque_Nm), settings.overshoot_s, during, ticks)
                started_at = time.monotonic()
                self.drive.apply(torque_Nm, settings.hold_s, during, ticks)
        finally:
            self._last_hold_end = time.monotonic()
            if started_at is None:  # aborted before the level's torque went on: time from the abort
                started_at = self._last_hold_end
            scale_samples = [
                ScaleSample(hold, direction, approach, torque_Nm, round(when - started_at, 3), weight.value, weight.stable, weight.net)
                for when, weight in weights
            ]
            self.run.append("scale", *scale_samples)
            self.run.append("odrive", *(
                ODriveSample(hold, direction, approach, torque_Nm, round(tick.time_s - started_at, 3), round(tick.feed_gap_s, 4), *tick[2:])
                for tick in ticks
            ))
        window_start = started_at + settings.hold_s - settings.sample_s
        if not (window := [tick for tick in ticks if tick.time_s >= window_start]):
            raise BenchError(f"No ODrive readings in the last {settings.sample_s} s of the hold: sample_s is shorter than the hold loop's tick.")
        signals = Signals(*(statistics.fmean(getattr(tick, name) for tick in window) for name in Signals._fields))
        return signals, scale_samples, max(tick.feed_gap_s for tick in ticks)

    def _reading(self, samples, label, allow_repeat=False):
        """The reading from the balance's samples, or a typed one without a scale (console.REPEAT if they typed r).
        Fewer balance readings than minimum_scale_readings are used anyway and flagged as low confidence."""
        if self.scale:
            if (reading := settle(samples, self.settings.hold_s - self.settings.sample_s)) is None:
                raise BenchError(f"{label}: no balance readings in the last {self.settings.sample_s} s. Motor idle.")
            if reading.samples < self.settings.minimum_scale_readings:
                print(f"  {label}: low confidence, only {reading.samples} balance readings (expected {self.settings.minimum_scale_readings}+).")
            return reading
        grams = console.ask_number(f"{label}: scale reading (g){', r to repeat' if allow_repeat else ''}: ", allow_repeat)
        return grams if grams is console.REPEAT else Reading(grams)

    def _rest(self):
        time.sleep(max(0.0, self._last_hold_end + self.settings.rest_s - time.monotonic()))


def settle(samples, window_start_s):
    """Mean, spread and counts of the samples from `window_start_s` on, or None if there are none.
    The motor can keep the balance from ever reporting stable, so unstable readings count too; the stable count says how settled it was."""
    if not (window := [sample for sample in samples if sample.time_s >= window_start_s]):
        return None
    grams = [sample.scale_g for sample in window]
    return Reading(
        round(statistics.fmean(grams), 2), round(statistics.pstdev(grams), 2), len(window), sum(sample.stable for sample in window)
    )


def wait_until_cool(drive):
    while (temperatures := drive.temperatures()).too_hot:
        console.pause(f"Too hot ({temperatures}). Let it cool.")


def measurement(hold, direction, approach, torque_Nm, reading, temperatures, signals=None):
    iq_setpoint, iq_measured, vbus = (round(value, 4) for value in signals) if signals else (None, None, None)
    return Measurement(
        hold=hold, direction=direction, approach=approach, torque_command_Nm=torque_Nm,
        scale_g=reading.grams, scale_standard_deviation_g=reading.standard_deviation_g, scale_samples=reading.samples, scale_stable_samples=reading.stable_samples,
        iq_setpoint_A=iq_setpoint, iq_measured_A=iq_measured, vbus_V=vbus,
        fet_temperature_C=temperatures.fet_C, motor_temperature_C=temperatures.motor_C,
    )
