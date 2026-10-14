"""An ODrive S1 driven over its USB from the Mac (no Teensy, no CAN), for holding torque against a fixture.

`connect()` is the only way in: it refuses the wrong or a misconfigured ODrive, caps vel_limit (not saved) and idles
the axis on every exit. Torque goes on only through `apply()` inside `armed()`; together they feed the watchdog,
abort on shaft motion and end idle. Units are ODrive's: rev, rev/s, motor-side N·m.
"""
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
# While `during()` runs, nothing feeds the watchdog or checks for shaft motion.
DURING_LIMIT_S = WATCHDOG_TIMEOUT_RANGE_S[0]
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


class ODriveUsb:
    def __init__(self, device):
        self._device = device
        self._axis = device.axis0
        self._highest_torque_Nm = 0.0  # what connect() checked the config for
        self._start_position = None  # set while armed
        self.velocity_cap_rev_per_s = None

    @classmethod
    @contextmanager
    def connect(cls, motor, highest_torque_Nm, timeout_s=10):
        """The ODrive for `motor` on USB, checked for torques up to `highest_torque_Nm`, with vel_limit capped.
        Idle on entry and on every exit, then vel_limit restored."""
        drive = cls(odrive.find_sync(timeout=timeout_s))
        controller_config = drive._axis.controller.config
        original_velocity_limit = None
        try:
            drive.stop()
            drive._require_ready(motor, highest_torque_Nm)
            drive._read_every_property_used()
            drive._highest_torque_Nm = highest_torque_Nm
            drive.velocity_cap_rev_per_s = drive._velocity_cap_for(highest_torque_Nm)
            original_velocity_limit = controller_config.vel_limit
            controller_config.vel_limit = drive.velocity_cap_rev_per_s
            yield drive
        finally:
            drive.stop()
            if original_velocity_limit is not None:
                try:
                    controller_config.vel_limit = original_velocity_limit
                except Exception as error:
                    print(f"Couldn't restore vel_limit ({error}). Reboot the ODrive; don't save its config.")

    @contextmanager
    def armed(self):
        """Closed loop at zero torque for the block, idle on every exit. Inside it, only call `apply()`:
        nothing else feeds the watchdog."""
        axis = self._axis
        try:
            axis.controller.input_torque = 0
            axis.watchdog_feed()
            axis.requested_state = AxisState.CLOSED_LOOP_CONTROL
            end = time.monotonic() + ARMING_S
            while time.monotonic() < end:
                axis.watchdog_feed()
                time.sleep(LOOP_PERIOD_S)
            self._require_closed_loop()
            self._start_position, _ = self.motion()
            yield
        finally:
            self._start_position = None
            self.stop()

    def apply(self, torque_Nm, seconds, during=None):
        """Hold `torque_Nm` for `seconds` with the shaft stalled against the fixture. Only inside `armed()`.

        Every LOOP_PERIOD_S it feeds the watchdog, aborts if the shaft moved, records the signals and calls `during()`,
        which must return within DURING_LIMIT_S. Returns (time.monotonic(), Signals) for each tick. The torque stays on.
        """
        if self._start_position is None:
            raise RuntimeError("apply() is only allowed inside armed().")
        if abs(torque_Nm) > self._highest_torque_Nm:
            raise BenchError(
                f"{torque_Nm:+.3f} N·m is above the {self._highest_torque_Nm:.3f} N·m the ODrive was checked for. Motor idled."
            )
        axis = self._axis
        axis.controller.input_torque = torque_Nm
        ticks = []
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            axis.watchdog_feed()
            position, velocity = self.motion()
            if abs(position - self._start_position) > MOTION_LIMIT_REV or abs(velocity) > SPEED_LIMIT_REV_PER_S:
                raise BenchError("The shaft moved during the hold: the fixture slipped. Motor idled.")
            ticks.append((time.monotonic(), self.signals()))
            if during:
                started = time.monotonic()
                during()
                if (took_s := time.monotonic() - started) > DURING_LIMIT_S:
                    raise BenchError(
                        f"Reading during the hold took {took_s:.2f} s (limit {DURING_LIMIT_S} s), "
                        "starving the watchdog and the slip check. Motor idled."
                    )
            time.sleep(LOOP_PERIOD_S)
        self._require_closed_loop()
        return ticks

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

    def _require_ready(self, motor, highest_torque_Nm):
        """Refuse the wrong or a misconfigured ODrive, listing every problem."""
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
        elif (velocity_cap := self._velocity_cap_for(highest_torque_Nm)) > VELOCITY_CAP_MAX_REV_PER_S:
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

        if problems:
            raise BenchError("Not starting:\n  - " + "\n  - ".join(problems))

    def _read_every_property_used(self):
        """So a firmware missing one fails here, motor idle, rather than partway through a hold."""
        self.identity()
        self.motion()
        self.signals()
        self.temperatures()

    def _velocity_cap_for(self, torque_Nm):
        """A vel_limit that can't clip `torque_Nm` at stall."""
        return VELOCITY_CAP_HEADROOM * torque_Nm / self._axis.controller.config.vel_gain

    def _require_closed_loop(self):
        if self._axis.current_state != AxisState.CLOSED_LOOP_CONTROL:
            self.stop()
            dump_errors(self._device)
            raise BenchError("The axis isn't in closed loop. Clear the errors and rerun.")
