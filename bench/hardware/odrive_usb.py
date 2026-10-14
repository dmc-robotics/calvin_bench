"""An ODrive S1 driven over its USB from the Mac (no Teensy, no CAN), for holding torque against a fixture.

Safety is built into the class, so procedures can't forget it:
- `connect()` idles the axis when it opens and on every exit, errors and Ctrl-C included;
- `hold()` feeds the watchdog every LOOP_PERIOD_S, aborts on shaft motion and always ends idle;
- `velocity_limited()` restores vel_limit on exit (it's never saved);
- `require_ready()` refuses the wrong or a misconfigured ODrive before any torque.
Units are ODrive's: rev, rev/s, motor-side N·m.
"""
import statistics
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import NamedTuple

import odrive
from odrive.enums import AxisState, ControlMode, InputMode
from odrive.utils import backup_config, dump_errors

from bench.errors import BenchError

NODE_IDS = {"left": 1, "right": 2}

LOOP_PERIOD_S = 0.02
ARMING_S = 0.3
# A hold is against a fixture (a lever arm on a scale, a clamp): if it slips, the shaft spins freely.
MOTION_LIMIT_REV = 0.03
SPEED_LIMIT_REV_PER_S = 0.5
# Torque-mode velocity limiting clamps torque to vel_gain × (vel_limit − vel), so a velocity cap
# must leave headroom at stall or it clips the torque.
VELOCITY_CAP_HEADROOM = 1.5
VELOCITY_CAP_MAX_REV_PER_S = 5.0
WATCHDOG_TIMEOUT_RANGE_S = (0.05, 0.2)
FET_TEMPERATURE_LIMIT_C = 80.0
MOTOR_TEMPERATURE_LIMIT_C = 60.0


class Signals(NamedTuple):
    iq_setpoint_A: float
    iq_measured_A: float
    vbus_V: float


@dataclass(frozen=True)
class Temperatures:
    fet_C: float
    motor_C: float | None  # None when the motor thermistor isn't enabled

    @property
    def too_hot(self):
        return self.fet_C > FET_TEMPERATURE_LIMIT_C or (self.motor_C is not None and self.motor_C > MOTOR_TEMPERATURE_LIMIT_C)

    def __str__(self):
        motor = "n/a" if self.motor_C is None else f"{self.motor_C:.0f} °C"
        return f"FET {self.fet_C:.0f} °C, motor {motor}"


@dataclass(frozen=True)
class Hold:
    signals: Signals  # means over the sampled end of the hold
    final_started_at: float  # time.monotonic() when the final segment's torque was applied


class ODriveUsb:
    def __init__(self, device):
        self._device = device
        self._axis = device.axis0

    @classmethod
    @contextmanager
    def connect(cls, timeout_s=10):
        """The first ODrive found on USB; idle on entry and on every exit."""
        connection = cls(odrive.find_sync(timeout=timeout_s))
        try:
            connection.stop()
            yield connection
        finally:
            connection.stop()

    def require_ready(self, motor, highest_torque_Nm):
        """Refuse the wrong or a misconfigured ODrive, listing every problem. Reads every property used later, before any torque."""
        axis = self._axis
        controller_config = axis.controller.config
        motor_config = axis.config.motor
        problems = []

        node_id = axis.config.can.node_id
        if node_id != NODE_IDS[motor]:
            problems.append(f"node ID is {node_id}, but {motor} is {NODE_IDS[motor]}. Wrong ODrive?")
        if controller_config.control_mode != ControlMode.TORQUE_CONTROL or controller_config.input_mode != InputMode.PASSTHROUGH:
            problems.append("not set to torque control + passthrough (experiment 1).")
        if not controller_config.enable_torque_mode_vel_limit:
            problems.append("enable_torque_mode_vel_limit is off, so the velocity cap wouldn't apply.")
        if controller_config.vel_gain <= 0:
            problems.append(f"vel_gain is {controller_config.vel_gain}, expected positive.")
        elif (velocity_cap := self.velocity_cap_for(highest_torque_Nm)) > VELOCITY_CAP_MAX_REV_PER_S:
            problems.append(f"vel_gain {controller_config.vel_gain:.3f} needs a velocity cap of {velocity_cap:.1f} rev/s to avoid clipping torque.")
        if motor_config.torque_constant <= 0:
            problems.append(f"torque_constant is {motor_config.torque_constant}, expected positive.")
        elif (current_needed := highest_torque_Nm / motor_config.torque_constant) > motor_config.current_soft_max:
            problems.append(
                f"{highest_torque_Nm:.3f} N·m needs {current_needed:.1f} A, above current_soft_max {motor_config.current_soft_max:.1f} A, "
                "so it would clip. Lower the torque or raise current_soft_max."
            )
        if not axis.config.enable_watchdog:
            problems.append("the watchdog is off (experiment 1 turns it on).")
        elif not WATCHDOG_TIMEOUT_RANGE_S[0] <= axis.config.watchdog_timeout <= WATCHDOG_TIMEOUT_RANGE_S[1]:
            problems.append(f"watchdog_timeout is {axis.config.watchdog_timeout} s, expected {WATCHDOG_TIMEOUT_RANGE_S[0]}–{WATCHDOG_TIMEOUT_RANGE_S[1]} s.")

        self.identity()
        self.signals()
        self.motion()
        self.temperatures()

        if problems:
            raise BenchError("Not starting:\n  - " + "\n  - ".join(problems))

    def velocity_cap_for(self, torque_Nm):
        """A vel_limit that can't clip `torque_Nm` at stall."""
        return VELOCITY_CAP_HEADROOM * torque_Nm / self._axis.controller.config.vel_gain

    def identity(self):
        device = self._device
        return {
            "serial": f"{device.serial_number:X}",
            "firmware": f"{device.fw_version_major}.{device.fw_version_minor}.{device.fw_version_revision}",
            "node_id": self._axis.config.can.node_id,
            "torque_constant_NmA": self._axis.config.motor.torque_constant,
        }

    def config(self):
        """The full config, as `odrivetool backup-config` saves it."""
        return backup_config(self._device)

    @contextmanager
    def velocity_limited(self, limit_rev_per_s):
        """vel_limit lowered for the block (not saved), restored on exit."""
        controller_config = self._axis.controller.config
        original = controller_config.vel_limit
        controller_config.vel_limit = limit_rev_per_s
        try:
            yield
        finally:
            try:
                controller_config.vel_limit = original
            except Exception as error:
                print(f"Couldn't restore vel_limit ({error}). Reboot the ODrive; don't save its config.")

    def hold(self, profile, sample_s, during=None):
        """Arm, apply each (torque N·m, seconds) of `profile` in turn with the shaft stalled against a fixture, then idle.

        Every LOOP_PERIOD_S it feeds the watchdog, checks for shaft motion and calls `during()` (which must not block).
        Returns the mean signals over the last `sample_s` of the final segment. Always ends idle.
        """
        axis = self._axis
        *leading, (final_torque_Nm, final_s) = profile
        try:
            axis.controller.input_torque = 0
            axis.watchdog_feed()
            axis.requested_state = AxisState.CLOSED_LOOP_CONTROL
            end = time.monotonic() + ARMING_S
            while time.monotonic() < end:
                axis.watchdog_feed()
                time.sleep(LOOP_PERIOD_S)
            self._require_closed_loop()
            start_position, _ = self.motion()

            for torque_Nm, seconds in leading:
                axis.controller.input_torque = torque_Nm
                self._watch(start_position, seconds, during)
            axis.controller.input_torque = final_torque_Nm
            final_started_at = time.monotonic()
            self._watch(start_position, final_s - sample_s, during)
            samples = self._watch(start_position, sample_s, during, sample=True)
            self._require_closed_loop()
        finally:
            self.stop()
        return Hold(Signals(*map(statistics.fmean, zip(*samples))), final_started_at)

    def motion(self):
        return self._axis.pos_estimate, self._axis.vel_estimate

    def signals(self):
        foc = self._axis.motor.foc
        return Signals(foc.Iq_setpoint, foc.Iq_measured, self._device.vbus_voltage)

    def temperatures(self):
        motor = self._axis.motor
        return Temperatures(
            round(motor.fet_thermistor.temperature, 1),
            round(motor.motor_thermistor.temperature, 1) if motor.motor_thermistor.config.enabled else None,
        )

    def stop(self):
        """Idle the axis and zero the torque command. Never raises: it runs on the way out of errors."""
        try:
            self._axis.requested_state = AxisState.IDLE
        except Exception as error:
            print(f"Couldn't idle the axis ({error}). Cut power.")
        try:
            self._axis.controller.input_torque = 0
        except Exception as error:
            print(f"Couldn't zero the torque command ({error}).")

    def _watch(self, start_position, seconds, during, sample=False):
        samples = []
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self._axis.watchdog_feed()
            position, velocity = self.motion()
            if abs(position - start_position) > MOTION_LIMIT_REV or abs(velocity) > SPEED_LIMIT_REV_PER_S:
                raise BenchError("The shaft moved during the hold: the fixture slipped. Motor idled.")
            if sample:
                samples.append(self.signals())
            if during:
                during()
            time.sleep(LOOP_PERIOD_S)
        return samples

    def _require_closed_loop(self):
        if self._axis.current_state != AxisState.CLOSED_LOOP_CONTROL:
            self.stop()
            dump_errors(self._device)
            raise BenchError("The axis isn't in closed loop. Clear the errors and rerun.")
