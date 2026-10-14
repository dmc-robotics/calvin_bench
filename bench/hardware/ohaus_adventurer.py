"""OHAUS Adventurer (AX) balance over its USB Device port or RS-232, in the OHAUS output format.

Self-contained (pyserial only) so other projects can copy it. Written against an AX8201/E: 8200 g capacity, 0.1 g
readability, 0.08 g repeatability (sd), ±0.2 g linearity, settles in ≤ 1.5 s (typical), external calibration only,
60 min warm-up for best accuracy. Manual: Adventurer Instruction Manual 30206078 (§7.2 output format, §9.3 commands).

The USB Device port (square USB-B; USB Host is for flash drives) is an FTDI FT230X serial bridge, so macOS needs no
driver. 9600 baud, 8N1, no handshake: the RS-232 menu's defaults.

Commands are ASCII lines ending in CR LF. Replies seen on an AX8201/E, firmware Sr 1.06 (probed 2026-10-14):
  IP          weight now: "        0.0     g", then a blank line per Feed setting (4 by default).
              "?" after the unit: unstable or below the minimum weight. "N" last: net, a tare is set.
  PV, PSN     "Sr 1.06", "Balance ID: B816716802"
  PT          "Tare:      263.1     g T" ("PT" instead of "T" for a preset tare)
  P#, P%      "APW: 2.06 g", "Ref. Weight: 1000.0 g"
  xH          "H 1 \"text\"" (header line x, 1-5); H x "text" sets it
  CP          a weight line ~10 times a second. xP prints the whole printout block every x s.
  0P          stops every print mode (CP, SLP, SLZP, xP)
  others      "OK!" (Z, T, xT, 0T, ON, OFF, C, AC, x#, x%, H x "text", xRL, SLP, SLZP, xP, 0P), with acknowledgements on
Refusals:
  ES          not a command it knows, or a bad value (e.g. -5T)
  EL          it's in standby: every command but ON gets this. OFF takes ~0.3 s to take effect; after ON,
              commands go unanswered for 0.4-1.1 s, and C for a few seconds more.
  "IP I"      busy, e.g. IP during a span calibration
  "IC L"      not available, e.g. internal calibration on an /E model
Not exposed:
  SP, 1S      print when stable (see below)
  P, 0S       the same as IP in the weighing application
  S, SI       MT-SICS commands it also answers ("S S        0.0 g"); not in the manual
A weight reply takes ~100 ms, so polling gives ~8.7 readings/s; CP gives ~10.3/s.

Where the balance differs from the manual (trust the balance):
  - Net weights end in "N", not "NET" (§7.2). parse_weight accepts both.
  - Only ES is documented. EL, "<command> I" and "<command> L" are not in the manual.
  - SP ("Print on Stability") sent while the reading is unstable is dropped, never answered, rather than printed
    once it settles. stable_weight() polls IP instead.
  - PFMT n (Table 9-6) is refused with ES in every syntax tried ("PFMT 1", "PFMT 0;", "PFMT;0"). Set the output
    format on the touchscreen instead (Communication > Print Settings > Print Output).
  - H ("Enter Print Header Lines") alone is refused with ES; the manual gives no syntax. xH reads a line and
    H x "text" sets it.
  - PV prints only "Sr 1.06", not the terminal and base software versions the manual lists.
  - CP lines end in a single CR LF; the Feed setting's extra blank lines (§7.2) only follow IP, SP and P.
  - CP isn't acknowledged with OK!, though every other command that doesn't print is.
  - The "USB INPUT" list (§9.4) spells SLZP as "LZP", which is refused with ES; Table 9-6's SLZP works.
"""
import re
import time
from contextlib import contextmanager
from typing import NamedTuple

import serial

BAUD = 9600
REPLY_TIMEOUT_S = 1.0
STANDBY_TIMEOUT_S = 2.0
WAKE_TIMEOUT_S = 5.0
POLL_PERIOD_S = 0.02
HEADER_LINES = range(1, 6)
HEADER_LENGTH = 25
WEIGHT = re.compile(r"^(-?\d+(?:\.\d+)?)\s+(\S+)(?:\s+(\?))?(?:\s+(N|NET|G))?$")
LABELLED_VALUE = re.compile(r"^[^:]+:\s*(-?\d+(?:\.\d+)?)\s+(\S+)")
HEADER = re.compile(r'^H \d "(.*)"$')
REFUSED = re.compile(r"^\S+ ([IL])$")
FORMAT_HINT = "Set its output format to OHAUS and Numeric Value Only off (Communication > Print Settings > Print Output)."


class OhausError(Exception):
    """The balance refused a command, didn't answer, or answered something this driver doesn't understand."""


class Weight(NamedTuple):
    value: float
    unit: str  # as displayed: g, kg, ct, ...
    stable: bool  # False while unstable or below the minimum weight
    net: bool  # True while a tare is set


class Quantity(NamedTuple):
    value: float
    unit: str


class OhausAdventurer:
    """`poll` and `readings` never block, so a control loop can read the balance as it runs. Every other method waits
    for the balance's reply (~0.1 s). While a print mode runs, use readings(); the queries would take its lines as replies."""

    def __init__(self, connection, port, unit=None):
        self._serial = connection
        self.port = port
        self.unit = unit
        self._buffer = b""
        self._requested_at = None
        self.firmware = None
        self.balance_id = None

    @classmethod
    @contextmanager
    def connect(cls, port, unit=None):
        """The balance on `port`, identified and checked to answer in the OHAUS format. With `unit`, every weight is
        checked to be in it. Turns acknowledgements on and stops any print mode, so replies aren't mixed with
        printouts. The port is closed on every exit."""
        try:
            connection = serial.Serial(port, BAUD, timeout=0, exclusive=True)
        except serial.SerialException as error:
            raise OhausError(f"Can't open the balance on {port}: {error}")
        try:
            balance = cls(connection, port, unit)
            balance._start()
            yield balance
        finally:
            connection.close()

    def identity(self):
        return {"port": self.port, "balance_id": self.balance_id, "firmware": self.firmware}

    def weight(self):
        """The displayed weight now, stable or not."""
        line = self._query("IP")
        weight = self._weight(line)
        if weight is None:
            raise OhausError(f"The balance's weight reply didn't parse: {line!r}. {FORMAT_HINT}")
        return weight

    def stable_weight(self, timeout_s=10.0):
        """The first stable weight, polling IP. Waits up to `timeout_s`. Not SP: contrary to the manual, the balance
        drops SP when the reading is unstable."""
        end = time.monotonic() + timeout_s
        while time.monotonic() < end:
            if (weight := self.weight()).stable:
                return weight
        raise OhausError(f"The balance didn't settle within {timeout_s} s.")

    def poll(self):
        """Request a weight if none is pending, without waiting. Returns the Weights that have arrived."""
        weights = self.readings()
        if weights:
            self._requested_at = None
        now = time.monotonic()
        if self._requested_at is None or now - self._requested_at > REPLY_TIMEOUT_S:
            self._write("IP")
            self._requested_at = now
        return weights

    def readings(self):
        """The Weights that have arrived, without waiting: replies to poll() or what a print mode sends.
        Other lines (OK!, a printout's labelled lines) are skipped; refusals raise."""
        weights = []
        for line in self._read_lines():
            raise_if_refused(line, "IP")
            if (weight := self._weight(line)) is not None:
                weights.append(weight)
        return weights

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
        """Wait out a polled reply still on its way, then drop everything received, so the next reading is fresh."""
        if self._requested_at is not None:
            end = self._requested_at + REPLY_TIMEOUT_S
            while time.monotonic() < end and not self._read_lines():
                time.sleep(POLL_PERIOD_S)
        self._serial.reset_input_buffer()
        self._buffer = b""
        self._requested_at = None

    def zero(self):
        """Zero the display, like the Zero key. Also clears the tare."""
        self._command("Z")

    def tare(self):
        """Tare the load on the pan, like the Tare key. Weights are then net."""
        self._command("T")

    def set_tare(self, value):
        """A preset tare, in the displayed unit. The balance rounds it to its readability and refuses a negative one."""
        self._command(f"{number(value)}T")

    def clear_tare(self):
        self._command("0T")

    def tare_weight(self):
        """The tare in use (0 without one)."""
        return labelled_value(self._query("PT"))

    def standby(self):
        """Display off; the balance then refuses every command but wake(). Returns once it does (~0.3 s)."""
        self._command("OFF")
        end = time.monotonic() + STANDBY_TIMEOUT_S
        while time.monotonic() < end:
            if self._reply_to("IP") == "EL":
                return
        raise OhausError("The balance didn't go into standby.")

    def wake(self):
        """Out of standby. Returns once it answers again (0.4-1.1 s)."""
        self._command("ON")
        end = time.monotonic() + WAKE_TIMEOUT_S
        while time.monotonic() < end:
            if parse_weight(self._reply_to("IP") or "") is not None:
                return
        raise OhausError(f"The balance didn't wake within {WAKE_TIMEOUT_S} s.")

    def print_continuously(self):
        """Send a weight ~10 times a second until stop_printing(). Collect them with readings().
        The balance doesn't acknowledge CP, so this waits for the first weight (and drops it)."""
        self._exchange("CP", lambda line: parse_weight(line) is not None)

    def print_when_stable(self, include_zero=False):
        """Send each stable non-zero weight (and stable zero readings with `include_zero`) until stop_printing()."""
        self._command("SLZP" if include_zero else "SLP")

    def print_every(self, seconds):
        """Send the whole printout block (header, weight, gross, net, tare) every `seconds` until stop_printing()."""
        if not (isinstance(seconds, int) and 1 <= seconds <= 3600):
            raise ValueError(f"The print interval is {seconds} s, expected a whole number of seconds from 1 to 3600.")
        self._command(f"{seconds}P")

    def stop_printing(self):
        self._command("0P")

    def begin_span_calibration(self):
        """Start a span calibration with external masses; the balance's display leads the rest.
        Goes unanswered for a few seconds after wake()."""
        self._command("C")

    def begin_internal_calibration(self):
        """Start an internal calibration. AutoCal models only: an /E model refuses it."""
        self._command("IC")

    def abort_calibration(self):
        self._command("AC")

    def piece_weight(self):
        """The counting application's average piece weight."""
        return labelled_value(self._query("P#"))

    def set_piece_weight(self, grams):
        self._command(f"{number(grams)}#")

    def reference_weight(self):
        """The percent application's reference weight."""
        return labelled_value(self._query("P%"))

    def set_reference_weight(self, grams):
        self._command(f"{number(grams)}%")

    def header(self, line):
        """Printout header line `line` (1-5)."""
        reply = self._query(f"{check_header_line(line)}H")
        if (match := HEADER.match(reply)) is None:
            raise OhausError(f"The balance's header reply didn't parse: {reply!r}.")
        return match[1]

    def set_header(self, line, text):
        if len(text) > HEADER_LENGTH or '"' in text:
            raise ValueError(f"Header text {text!r} must be at most {HEADER_LENGTH} characters, without double quotes.")
        self._command(f'H {check_header_line(line)} "{text}"')

    def _start(self):
        self._command("1RL")
        self._command("0P")
        self.firmware = self._query("PV")
        self.balance_id = self._query("PSN").partition(":")[2].strip()
        self.weight()

    def _command(self, command):
        """Send a command the balance acknowledges with OK! Lines a print mode sends meanwhile are skipped."""
        self._exchange(command, lambda line: line == "OK!")

    def _query(self, command):
        return self._exchange(command, lambda line: True)

    def _exchange(self, command, accept):
        """Send `command` and return the first reply line `accept` takes. Raises if it's refused or unanswered."""
        line = self._reply_to(command, accept)
        if line is None:
            raise OhausError(f"No reply to {command} from the balance on {self.port}. Is it on, and is this its port?")
        raise_if_refused(line, command)
        return line

    def _reply_to(self, command, accept=lambda line: True):
        """Send `command` and return the first reply line `accept` takes or that refuses it, or None after REPLY_TIMEOUT_S."""
        self.clear()
        self._write(command)
        end = time.monotonic() + REPLY_TIMEOUT_S
        while time.monotonic() < end:
            for line in self._read_lines():
                if is_refusal(line) or accept(line):
                    return line
            time.sleep(POLL_PERIOD_S)
        return None

    def _weight(self, line):
        weight = parse_weight(line)
        if weight is not None and self.unit is not None and weight.unit != self.unit:
            raise OhausError(f"The balance is reading in {weight.unit}. Switch it to {self.unit}.")
        return weight

    def _write(self, command):
        self._serial.write(command.encode("ascii") + b"\r\n")

    def _read_lines(self):
        self._buffer += self._serial.read(self._serial.in_waiting)
        *lines, self._buffer = self._buffer.split(b"\n")
        return [text for text in (line.decode("ascii", "replace").strip() for line in lines) if text]


def parse_weight(line):
    """The Weight in an unlabelled weight line (§7.2), or None if `line` isn't one."""
    match = WEIGHT.match(line)
    if match is None:
        return None
    value, unit, unstable, gross_or_net = match.groups()
    return Weight(float(value), unit, unstable is None, gross_or_net in ("N", "NET"))  # the balance sends N; the manual says NET


def labelled_value(line):
    """The Quantity in a labelled reply like "Tare:      263.1     g T"."""
    match = LABELLED_VALUE.match(line)
    if match is None:
        raise OhausError(f"The balance's reply didn't parse: {line!r}. {FORMAT_HINT}")
    return Quantity(float(match[1]), match[2])


def is_refusal(line):
    return line in ("ES", "EL") or REFUSED.match(line) is not None


def raise_if_refused(line, command):
    if line == "ES":
        raise OhausError(f"The balance refused {command}: not a command it knows, or a bad value.")
    if line == "EL":
        raise OhausError(f"The balance is in standby, so it refused {command}. Wake it with its power key or wake().")
    if match := REFUSED.match(line):
        reason = "it's busy, e.g. calibrating" if match[1] == "I" else "this model doesn't have it"
        raise OhausError(f"The balance refused {command}: {reason}.")


def number(value):
    """A command argument: 12.34 → "12.34", 10.0 → "10"."""
    return f"{value:.6f}".rstrip("0").rstrip(".")


def check_header_line(line):
    if line not in HEADER_LINES:
        raise ValueError(f"Header line {line}, expected 1 to 5.")
    return line
