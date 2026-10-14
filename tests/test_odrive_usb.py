"""The driver's safety guarantees, against a fake ODrive device."""
import pytest
from odrive.enums import AxisState

from bench.errors import BenchError
from bench.hardware.odrive_usb import ODriveUsb
from fakes import TORQUE_CONSTANT_NMA


def test_require_ready_accepts_a_good_config(device):
    with ODriveUsb.connect() as odrive:
        odrive.require_ready("left", 0.25)


def test_require_ready_lists_every_problem(device):
    axis = device.axis0
    axis.config.can.node_id = 2
    axis.config.enable_watchdog = False
    axis.controller.config.vel_gain = 0
    axis.config.motor.current_soft_max = 5.0
    with ODriveUsb.connect() as odrive, pytest.raises(BenchError) as error:
        odrive.require_ready("left", 0.25)
    message = str(error.value)
    for problem in ("Wrong ODrive", "watchdog is off", "vel_gain is 0", "above current_soft_max"):
        assert problem in message
    assert axis.arm_count == 0


def test_hold_returns_mean_signals_and_ends_idle(device):
    with ODriveUsb.connect() as odrive:
        hold = odrive.hold([(0.1, 0.1)], sample_s=0.05)
        assert device.axis0.is_idle  # by hold itself, not by connect's cleanup
    assert hold.signals.iq_setpoint_A == pytest.approx(0.1 / TORQUE_CONSTANT_NMA)
    assert hold.signals.vbus_V == pytest.approx(device.vbus_voltage)
    assert device.axis0.watchdog_feeds >= 5


def test_hold_applies_the_profile_in_order(device):
    with ODriveUsb.connect() as odrive:
        odrive.hold([(0.15, 0.05), (0.1, 0.1)], sample_s=0.05)
    torques = [torque for torque in device.axis0.torque_log if torque != 0]
    assert torques == [0.15, 0.1]
    assert device.axis0.torque_log[-1] == 0


def test_hold_aborts_on_shaft_motion_and_ends_idle(device):
    device.axis0.slip_after_reads = 2
    with ODriveUsb.connect() as odrive:
        with pytest.raises(BenchError, match="shaft moved"):
            odrive.hold([(0.1, 0.5)], sample_s=0.1)
        assert device.axis0.is_idle


def test_hold_ends_idle_when_the_callback_fails(device):
    def unplugged_scale():
        raise OSError("device disconnected")

    with ODriveUsb.connect() as odrive:
        with pytest.raises(OSError):
            odrive.hold([(0.1, 0.5)], sample_s=0.1, during=unplugged_scale)
        assert device.axis0.is_idle


def test_hold_refuses_to_continue_if_the_axis_drops_out_of_closed_loop(device):
    device.axis0.refuses_closed_loop = True
    with ODriveUsb.connect() as odrive, pytest.raises(BenchError, match="closed loop"):
        odrive.hold([(0.1, 0.1)], sample_s=0.05)
    assert all(torque == 0 for torque in device.axis0.torque_log)
    assert device.axis0.is_idle


def test_velocity_limited_restores_the_limit_even_on_error(device):
    config = device.axis0.controller.config
    with ODriveUsb.connect() as odrive, pytest.raises(RuntimeError):
        with odrive.velocity_limited(2.0):
            assert config.vel_limit == 2.0
            raise RuntimeError
    assert config.vel_limit == 10.0


def test_connect_idles_the_axis_on_exit(device):
    with pytest.raises(RuntimeError), ODriveUsb.connect():
        device.axis0.requested_state = AxisState.CLOSED_LOOP_CONTROL  # set behind the driver's back
        device.axis0.controller.input_torque = 0.2
        raise RuntimeError
    assert device.axis0.is_idle
