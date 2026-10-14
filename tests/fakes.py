"""Hardware stand-ins for the real drivers to talk to: a fake ODrive device for ODriveUsb, and a fake balance's serial
port for OhausAdventurer that can weigh the torque the fake motor is holding."""
import re
from types import SimpleNamespace

from odrive.enums import AxisState, ControlMode, InputMode

from bench import units

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
    """Iq tracks the torque command exactly; the motor then makes `k` times the commanded torque (lever_load weighs that)."""

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


class FakeBalance:
    """A serial port with an OHAUS Adventurer behind it, replying as the AX8201/E did when probed (firmware Sr 1.06).

    `load_g` is the gross load on the pan: a number, or a function for one that changes. A reply arrives `lag` reads
    of `in_waiting` after its command, so a test can catch one in flight; `reset_input_buffer` only drops what has arrived.
    """

    def __init__(self, load_g=0.0, unit="g", lag=0):
        self.load_g = load_g
        self.unit = unit
        self.lag = lag
        self.stable = True
        self.standby_after_weights = None  # goes into standby after this many weight replies
        self.silent = False
        self.standby = False
        self.transition_commands = 0  # after OFF, commands still answered as awake; after ON, ignored
        self.calibrating = False
        self.acknowledge = False
        self.continuous = False
        self.zero_g = 0.0
        self.tare_g = 0.0
        self.headers = {line: "" for line in range(1, 6)}
        self.piece_weight_g = 2.06
        self.reference_weight_g = 1000.0
        self.received = []
        self.closed = False
        self._weights_sent = 0
        self._transition_left = 0
        self._arrived = b""
        self._in_flight = []  # [reads left, bytes]

    def gross_g(self):
        return (self.load_g() if callable(self.load_g) else self.load_g) - self.zero_g

    def weight_line(self):
        net = self.gross_g() - self.tare_g
        return f"{net:11.1f} {self.unit:>5}{'' if self.stable else ' ?'}{' N' if self.tare_g else ''}"

    @property
    def in_waiting(self):
        if self.continuous:
            self._reply(self.weight_line())
        for reply in self._in_flight:
            reply[0] -= 1
        self._arrived += b"".join(data for reads, data in self._in_flight if reads < 0)
        self._in_flight = [reply for reply in self._in_flight if reply[0] >= 0]
        return len(self._arrived)

    def read(self, size):
        data, self._arrived = self._arrived[:size], self._arrived[size:]
        return data

    def reset_input_buffer(self):
        self._arrived = b""

    def close(self):
        self.closed = True

    def write(self, data):
        command = data.decode("ascii").removesuffix("\r\n")
        self.received.append(command)
        if not self.silent:
            self._answer(command)

    def _answer(self, command):
        if self._transition_left and command not in ("ON", "OFF"):
            self._transition_left -= 1
            if not self.standby:  # still waking: unanswered
                return
        elif self.standby and command != "ON":
            return self._reply("EL")
        if self.calibrating and command == "IP":
            return self._reply("IP I")
        if command == "IP":
            self._weights_sent += 1
            if self._weights_sent == self.standby_after_weights:
                self.standby = True
            return self._reply(self.weight_line() + "\r\n" * 4)
        queries = {
            "PV": "Sr 1.06",
            "PSN": "Balance ID: B000000001",
            "PT": f"Tare: {self.tare_g:10.1f} {self.unit:>5} T",
            "P#": f"APW: {self.piece_weight_g} g",
            "P%": f"Ref. Weight: {self.reference_weight_g:.1f} g",
        }
        if command in queries:
            return self._reply(queries[command])
        if command == "CP":  # answered by the weights it starts sending, not OK!
            self.continuous = True
            return
        if header := re.fullmatch(r"([1-5])H", command):
            return self._reply(f'H {header[1]} "{self.headers[int(header[1])]}"')
        if self._act(command):
            if self.acknowledge:
                self._reply("OK!")
        elif command == "IC":
            self._reply("IC L")
        else:
            self._reply("ES")

    def _act(self, command):
        """Carry out a command acknowledged with OK! True if it's one."""
        actions = {
            "Z": lambda: (setattr(self, "zero_g", self.zero_g + self.gross_g()), setattr(self, "tare_g", 0.0)),
            "T": lambda: setattr(self, "tare_g", self.gross_g()),
            "OFF": lambda: self._enter_standby(True),
            "ON": lambda: self._enter_standby(False),
            "C": lambda: setattr(self, "calibrating", True),
            "AC": lambda: setattr(self, "calibrating", False),
            "SLP": lambda: None,
            "SLZP": lambda: None,
            "0P": lambda: setattr(self, "continuous", False),
            "0RL": lambda: setattr(self, "acknowledge", False),
            "1RL": lambda: setattr(self, "acknowledge", True),
        }
        if command in actions:
            actions[command]()
        elif match := re.fullmatch(r"(\d+(?:\.\d+)?)([T#%P])", command):
            value, kind = float(match[1]), match[2]
            if kind == "P" and not (value.is_integer() and value <= 3600):
                return False
            attribute = {"T": "tare_g", "#": "piece_weight_g", "%": "reference_weight_g"}.get(kind)
            if attribute:
                setattr(self, attribute, round(value, 1) if kind == "T" else value)
        elif match := re.fullmatch(r'H ([1-5]) "([^"]{0,25})"', command):
            self.headers[int(match[1])] = match[2]
        else:
            return False
        return True

    def _enter_standby(self, standby):
        self.standby = standby
        self._transition_left = self.transition_commands

    def _reply(self, line):
        self._in_flight.append([self.lag, (line + "\r\n").encode("ascii")])


def lever_load(axis, arm_length_m, tare_g=50.0):
    """The load a lever arm of `arm_length_m` puts on the balance: its resting `tare_g` plus the fake motor's torque."""
    return lambda: tare_g + axis.k * abs(axis.controller.input_torque) / arm_length_m / units.STANDARD_GRAVITY * 1000
