"""The driver's safety guarantees, against a fake ODrive device."""
import time

import pytest
from odrive.enums import AxisState

from bench.errors import BenchError
from bench.hardware.odrive_usb import ODriveUsb
from fakes import TORQUE_CONSTANT_NMA


def test_connect_caps_the_velocity_and_restores_it(device):
    config = device.axis0.controller.config
    with ODriveUsb.connect("left", 0.25) as drive:
        assert drive.velocity_cap_rev_per_s == pytest.approx(1.5 * 0.25 / config.vel_gain)
        assert config.vel_limit == drive.velocity_cap_rev_per_s
    assert config.vel_limit == 10.0
    assert device.axis0.is_idle


def test_connect_lists_every_problem_and_changes_nothing(device):
    axis = device.axis0
    axis.config.can.node_id = 2
    axis.config.enable_watchdog = False
    axis.controller.config.vel_gain = 0
    axis.config.motor.current_soft_max = 5.0
    with pytest.raises(BenchError) as error, ODriveUsb.connect("left", 0.25):
        pass
    message = str(error.value)
    for problem in ("Wrong ODrive", "watchdog is off", "vel_gain is 0", "above current_soft_max"):
        assert problem in message
    assert axis.arm_count == 0
    assert axis.controller.config.vel_limit == 10.0


def test_connect_restores_the_velocity_limit_and_idles_on_error(device):
    with pytest.raises(RuntimeError), ODriveUsb.connect("left", 0.25):
        device.axis0.requested_state = AxisState.CLOSED_LOOP_CONTROL  # set behind the driver's back
        device.axis0.controller.input_torque = 0.2
        raise RuntimeError
    assert device.axis0.is_idle
    assert device.axis0.controller.config.vel_limit == 10.0


def test_apply_holds_the_torque_and_returns_the_signals_each_tick(device):
    with ODriveUsb.connect("left", 0.25) as drive:
        with drive.armed():
            ticks = drive.apply(0.1, 0.1)
            assert device.axis0.controller.input_torque == 0.1  # still on after apply returns
        assert device.axis0.is_idle  # by armed itself, not by connect's cleanup
    assert len(ticks) >= 4
    assert [when for when, _ in ticks] == sorted(when for when, _ in ticks)
    for _, signals in ticks:
        assert signals.iq_setpoint_A == pytest.approx(0.1 / TORQUE_CONSTANT_NMA)
        assert signals.vbus_V == pytest.approx(device.vbus_voltage)
    assert device.axis0.watchdog_feeds >= 5


def test_segments_in_one_armed_block_stay_armed(device):
    with ODriveUsb.connect("left", 0.25) as drive, drive.armed():
        drive.apply(0.15, 0.05)
        drive.apply(0.1, 0.05)
    assert device.axis0.arm_count == 1
    assert [torque for torque in device.axis0.torque_log if torque != 0] == [0.15, 0.1]
    assert device.axis0.torque_log[-1] == 0


def test_apply_refuses_a_torque_above_the_checked_one(device):
    with ODriveUsb.connect("left", 0.25) as drive, pytest.raises(BenchError, match="checked for"):
        with drive.armed():
            drive.apply(-0.3, 0.1)
    assert all(torque == 0 for torque in device.axis0.torque_log)
    assert device.axis0.is_idle


def test_apply_is_refused_outside_armed(device):
    with ODriveUsb.connect("left", 0.25) as drive, pytest.raises(RuntimeError, match="armed"):
        drive.apply(0.1, 0.1)
    assert all(torque == 0 for torque in device.axis0.torque_log)


def test_shaft_motion_aborts_and_ends_idle(device):
    device.axis0.slip_after_reads = 2
    with ODriveUsb.connect("left", 0.25) as drive:
        with pytest.raises(BenchError, match="shaft moved"), drive.armed():
            drive.apply(0.1, 0.5)
        assert device.axis0.is_idle


def test_a_failing_callback_ends_idle(device):
    def unplugged_scale():
        raise OSError("device disconnected")

    with ODriveUsb.connect("left", 0.25) as drive:
        with pytest.raises(OSError), drive.armed():
            drive.apply(0.1, 0.5, during=unplugged_scale)
        assert device.axis0.is_idle


def test_a_blocking_callback_aborts_and_ends_idle(device):
    def blocking_scale():
        time.sleep(0.06)

    with ODriveUsb.connect("left", 0.25) as drive:
        with pytest.raises(BenchError, match="took"), drive.armed():
            drive.apply(0.1, 0.5, during=blocking_scale)
        assert device.axis0.is_idle


def test_arming_refuses_to_continue_if_the_axis_isnt_in_closed_loop(device):
    device.axis0.refuses_closed_loop = True
    with ODriveUsb.connect("left", 0.25) as drive, pytest.raises(BenchError, match="closed loop"):
        with drive.armed():
            drive.apply(0.1, 0.1)
    assert all(torque == 0 for torque in device.axis0.torque_log)
    assert device.axis0.is_idle
