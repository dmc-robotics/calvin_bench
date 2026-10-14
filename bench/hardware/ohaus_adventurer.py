"""OHAUS Adventurer AX8201/E balance (0.1 g) over USB.

Cable to its USB Device port, the square USB-B socket (USB Host is for flash drives). Inside the balance is an
FTDI FT230X serial bridge, so macOS needs no driver: 9600 baud, 8N1.
Commands are ASCII lines ending in CR LF:
  IP   weight now, stable or not: "       32.2     g ?" ("?" = unstable), then a few blank lines
  PV   firmware version: "Sr 1.06"
  PSN  balance ID: "Balance ID: B816716802"
  EL   the reply to every command when the balance won't act on it (cause not yet pinned down: menu, standby or error state?)
A weight reply takes ~90 ms, so polling gives ~8 readings/s.
"""
import re
import time
from contextlib import contextmanager
from typing import NamedTuple

import serial

from bench.errors import BenchError

# Safe to hard-code: macOS names the port after the serial number of the FTDI chip inside the balance,
# so it stays the same across replugs, reboots and USB sockets.
DEFAULT_PORT = "/dev/cu.usbserial-DN04KNBY"

BAUD = 9600
REPLY_TIMEOUT_S = 1.0
POLL_PERIOD_S = 0.02
REFUSED_HINT = " The balance refused the command: check it's on, weighing, and not in a menu or error state."
WEIGHT = re.compile(r"^(-?)\s*(\d+\.?\d*)\s+(\S+)\s*(\?)?$")


class Weight(NamedTuple):
    grams: float
    stable: bool


class OhausAdventurer:
    """`poll` never blocks, so a control loop (e.g. one feeding the ODrive watchdog) can read the balance as it runs."""

    def __init__(self, connection, port):
        self._serial = connection
        self.port = port
        self._buffer = b""
        self._requested_at = None
        self.firmware = None
        self.balance_id = None

    @classmethod
    @contextmanager
    def connect(cls, port=DEFAULT_PORT):
        """The balance on `port`, checked to answer and to weigh in grams. The port is closed on every exit."""
        try:
            connection = serial.Serial(port, BAUD, timeout=0)
        except serial.SerialException as error:
            raise BenchError(f"Can't open the scale on {port}: {error}")
        try:
            scale = cls(connection, port)
            scale._identify()
            yield scale
        finally:
            connection.close()

    def identity(self):
        return {"port": self.port, "balance_id": self.balance_id, "firmware": self.firmware}

    def poll(self):
        """Request a weight if none is pending. Returns the Weights that have arrived."""
        readings = [reading for reading in map(parse_weight, self._read_lines()) if reading is not None]
        if readings:
            self._requested_at = None
        now = time.monotonic()
        if self._requested_at is None or now - self._requested_at > REPLY_TIMEOUT_S:
            self._serial.write(b"IP\r\n")
            self._requested_at = now
        return readings

    def sample(self, seconds):
        """Poll for `seconds`. Returns (time from the start, Weight) pairs."""
        self.clear()
        start = time.monotonic()
        readings = []
        while time.monotonic() - start < seconds:
            readings += [(time.monotonic() - start, weight) for weight in self.poll()]
            time.sleep(POLL_PERIOD_S)
        return readings

    def clear(self):
        """Drop stale replies, e.g. one still in flight from an earlier poll."""
        self._serial.reset_input_buffer()
        self._buffer = b""
        self._requested_at = None

    def _identify(self):
        self.firmware = self._query(b"PV")
        self.balance_id = self._query(b"PSN").partition(":")[2].strip()
        reply = self._query(b"IP")
        if parse_weight(reply) is None:
            raise BenchError(f"The scale's weight reply didn't parse: {reply!r}.{REFUSED_HINT if reply == 'EL' else ''}")

    def _query(self, command):
        self.clear()
        self._serial.write(command + b"\r\n")
        end = time.monotonic() + REPLY_TIMEOUT_S
        while time.monotonic() < end:
            lines = self._read_lines()
            if lines:
                return lines[0]
            time.sleep(POLL_PERIOD_S)
        raise BenchError(f"No reply from the scale on {self.port}. Is it on, and is this its port?")

    def _read_lines(self):
        self._buffer += self._serial.read(self._serial.in_waiting)
        *lines, self._buffer = self._buffer.split(b"\n")
        return [text for text in (line.decode("ascii", "replace").strip() for line in lines) if text]


def parse_weight(line):
    """The Weight in a weight reply, or None if `line` isn't one."""
    match = WEIGHT.match(line)
    if match is None:
        return None
    sign, value, unit, unstable = match.groups()
    if unit != "g":
        raise BenchError(f"The scale is reading in {unit}. Switch it to grams.")
    return Weight(float(sign + value), unstable is None)
