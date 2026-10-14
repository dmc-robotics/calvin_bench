"""Hardware stand-ins: a fake ODrive device for the real ODriveUsb driver to talk to, and a fake balance that weighs
the torque the fake motor is holding."""
from types import SimpleNamespace

from odrive.enums import AxisState, ControlMode, InputMode

from bench import units
from bench.hardware.ohaus_adventurer import Weight

TORQUE_CONSTANT_NMA = 8.27 / 330


class FakeController:
    def __init__(self, axis):
        self._axis = axis
        self._input_torque = 0.0
        self.config = SimpleNamespace(
            control_mode=ControlMode.TORQUE_CONTROL, input_mode=InputMode.PASSTHROUGH,
            enable_torque_mode_vel_limit=True, vel_gain=1 / 6, vel_limit=10.0,
        )

    @property
    def input_torque(self):
        return self._input_torque

    @input_torque.setter
    def input_torque(self, torque):
        self._input_torque = torque
        self._axis.torque_log.append(torque)


class FakeFoc:
    """Iq tracks the torque command exactly; the motor then makes `k` times the commanded torque (FakeOhausAdventurer weighs that)."""

    def __init__(self, axis):
        self._axis = axis

    @property
    def Iq_setpoint(self):
        return self._axis.controller.input_torque / TORQUE_CONSTANT_NMA

    @property
    def Iq_measured(self):
        return self.Iq_setpoint


class FakeAxis:
    def __init__(self, node_id, k):
        self.k = k
        self.torque_log = []  # every input_torque written, in order
        self.arm_count = 0
        self.watchdog_feeds = 0
        self.slip_after_reads = None  # the shaft moves after this many position reads
        self.refuses_closed_loop = False
        self._position_reads = 0
        self._requested_state = AxisState.IDLE
        self.config = SimpleNamespace(
            can=SimpleNamespace(node_id=node_id),
            enable_watchdog=True,
            watchdog_timeout=0.1,
            motor=SimpleNamespace(torque_constant=TORQUE_CONSTANT_NMA, current_soft_max=10.0),
        )
        self.controller = FakeController(self)
        self.motor = SimpleNamespace(
            foc=FakeFoc(self),
            fet_thermistor=SimpleNamespace(temperature=30.0),
            motor_thermistor=SimpleNamespace(temperature=25.0, config=SimpleNamespace(enabled=False)),
        )
        self.vel_estimate = 0.0

    @property
    def requested_state(self):
        return self._requested_state

    @requested_state.setter
    def requested_state(self, state):
        if state == AxisState.CLOSED_LOOP_CONTROL:
            self.arm_count += 1
        self._requested_state = state

    @property
    def current_state(self):
        if self.refuses_closed_loop:
            return AxisState.IDLE
        return self._requested_state

    @property
    def pos_estimate(self):
        self._position_reads += 1
        moved = self.slip_after_reads is not None and self._position_reads > self.slip_after_reads
        return 1.0 if moved else 0.0

    @property
    def is_idle(self):
        return self._requested_state == AxisState.IDLE and self.controller.input_torque == 0

    def watchdog_feed(self):
        self.watchdog_feeds += 1


class FakeDevice:
    def __init__(self, node_id=1, k=0.97):
        self.axis0 = FakeAxis(node_id, k)
        self.serial_number = 0x3A2B1C
        self.fw_version_major, self.fw_version_minor, self.fw_version_revision = 0, 6, 12
        self.vbus_voltage = 15.8


class FakeOhausAdventurer:
    """Reads the tare plus whatever the fake motor pushes onto it through an arm of `arm_length_m`."""

    port = "/dev/cu.fake"
    balance_id = "FAKE"
    firmware = "Sr 0"

    def __init__(self, axis, arm_length_m, tare_g=50.0):
        self._axis = axis
        self._arm_length_m = arm_length_m
        self.tare_g = tare_g

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        self.closed = True

    def identity(self):
        return {"port": self.port, "balance_id": self.balance_id, "firmware": self.firmware}

    def weight(self):
        torque = self._axis.k * abs(self._axis.controller.input_torque)
        return Weight(self.tare_g + torque / self._arm_length_m / units.STANDARD_GRAVITY * 1000, True)

    def poll(self):
        return [self.weight()]

    def sample(self, seconds):
        return [(seconds * index / 10, self.weight()) for index in range(11)]

    def clear(self):
        pass
