"""The driver's safety guarantees, against a fake ODrive device."""
import math
import time

import pytest
from odrive.enums import AxisState

from bench.errors import BenchError
from bench.hardware import odrive_usb
from bench.hardware.odrive_usb import ODriveUsb
from fakes import TORQUE_CONSTANT_NMA


def test_connect_caps_the_velocity_and_restores_it(device):
    config = device.axis0.controller.config
    with ODriveUsb.connect("left", 0.25) as drive:
        assert drive.velocity_cap_rev_per_s == pytest.approx(1.5 * 0.25 / config.vel_gain)
        assert config.vel_limit == drive.velocity_cap_rev_per_s
        assert drive.configuration["axis0.controller.config.vel_limit"] == 10.0  # as found, not the cap
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
    assert [tick.time_s for tick in ticks] == sorted(tick.time_s for tick in ticks)
    for tick in ticks:
        assert tick.iq_setpoint_A == pytest.approx(0.1 / TORQUE_CONSTANT_NMA)
        assert tick.vbus_V == pytest.approx(device.vbus_voltage)
        assert tick.feed_gap_s < 0.05
    assert device.axis0.watchdog_feeds >= 5


def test_segments_in_one_armed_block_stay_armed(device):
    with ODriveUsb.connect("left", 0.25) as drive, drive.armed():
        drive.apply(0.15, 0.05)
        drive.apply(0.1, 0.05)
    assert device.axis0.arm_count == 1
    assert [torque for torque in device.axis0.torque_log if torque != 0] == [0.15, 0.1]
    assert device.axis0.torque_log[-1] == 0


@pytest.mark.parametrize("torque_Nm", [-0.3, math.nan])
def test_apply_refuses_a_torque_above_the_checked_one(device, torque_Nm):
    with ODriveUsb.connect("left", 0.25) as drive, pytest.raises(BenchError, match="checked for"):
        with drive.armed():
            drive.apply(torque_Nm, 0.1)
    assert all(torque == 0 for torque in device.axis0.torque_log)
    assert device.axis0.is_idle


def test_arming_refuses_a_hot_motor(device):
    device.axis0.motor.fet_thermistor.temperature = 85.0
    with ODriveUsb.connect("left", 0.25) as drive, pytest.raises(BenchError, match="Too hot"):
        with drive.armed():
            drive.apply(0.1, 0.1)
    assert device.axis0.arm_count == 0
    assert device.axis0.is_idle


def test_connect_refuses_a_watchdog_timeout_too_short_for_the_hold_loop(device):
    device.axis0.config.watchdog_timeout = 0.05
    with pytest.raises(BenchError, match="watchdog_timeout"), ODriveUsb.connect("left", 0.25):
        pass


def test_apply_is_refused_outside_armed(device):
    with ODriveUsb.connect("left", 0.25) as drive, pytest.raises(RuntimeError, match="armed"):
        drive.apply(0.1, 0.1)
    assert all(torque == 0 for torque in device.axis0.torque_log)


def test_shaft_speed_aborts_and_ends_idle(device):
    with ODriveUsb.connect("left", 0.25) as drive:
        with pytest.raises(BenchError, match="shaft moved"), drive.armed():
            device.axis0.vel_estimate = 1.0
            drive.apply(0.1, 0.5)
        assert device.axis0.is_idle


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


def test_ctrl_c_mid_hold_ends_idle_with_the_velocity_limit_restored(device):
    def interrupt():
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt), ODriveUsb.connect("left", 0.25) as drive, drive.armed():
        drive.apply(0.1, 0.5, during=interrupt)
    assert device.axis0.is_idle
    assert device.axis0.controller.config.vel_limit == 10.0


def test_a_callback_slower_than_a_tick_doesnt_add_the_ticks_sleep(device):
    def slow_scale():
        time.sleep(0.035)  # with a fixed 0.02 s sleep on top, past half the 0.1 s timeout

    with ODriveUsb.connect("left", 0.25) as drive, drive.armed():
        ticks = drive.apply(0.1, 0.2, during=slow_scale)
    assert max(tick.feed_gap_s for tick in ticks) < 0.05


def test_a_blocking_callback_aborts_before_the_watchdog_trips(device):
    def blocking_scale():
        time.sleep(0.06)

    with ODriveUsb.connect("left", 0.25) as drive:
        with pytest.raises(BenchError, match="between watchdog feeds"), drive.armed():
            drive.apply(0.1, 0.5, during=blocking_scale)
        assert device.axis0.is_idle
    assert not device.axis0.watchdog_tripped


def test_the_fake_watchdog_trips_on_a_gap_the_driver_misses(device, monkeypatch):
    monkeypatch.setattr(odrive_usb, "FEED_GAP_FRACTION", 2.0)

    def blocking_scale():
        time.sleep(0.15)

    with ODriveUsb.connect("left", 0.25) as drive:
        with pytest.raises(BenchError, match="closed loop"), drive.armed():
            drive.apply(0.1, 0.1, during=blocking_scale)
        assert device.axis0.is_idle


def test_arming_refuses_to_continue_if_the_axis_isnt_in_closed_loop(device):
    device.axis0.refuses_closed_loop = True
    with ODriveUsb.connect("left", 0.25) as drive, pytest.raises(BenchError, match="closed loop"):
        with drive.armed():
            drive.apply(0.1, 0.1)
    assert all(torque == 0 for torque in device.axis0.torque_log)
    assert device.axis0.is_idle


def test_no_odrive_on_usb_raises_bench_error(device, monkeypatch):
    def time_out(timeout):
        raise TimeoutError

    monkeypatch.setattr(odrive_usb.odrive, "find_sync", time_out)
    with pytest.raises(BenchError, match="No ODrive on USB"), ODriveUsb.connect("left", 0.25):
        pass
