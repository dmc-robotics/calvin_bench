"""The balance driver's connect(), against a fake serial port."""
import pytest

from bench.errors import BenchError
from bench.hardware import ohaus_adventurer
from bench.hardware.ohaus_adventurer import OhausAdventurer

REPLIES = {b"PV": b"Sr 1.06\r\n", b"PSN": b"Balance ID: B816716802\r\n", b"IP": b"       32.2     g  \r\n\r\n"}


class FakeSerial:
    """Answers each command with its reply in `replies`."""

    def __init__(self, replies):
        self._replies = replies
        self._pending = b""
        self.closed = False

    @property
    def in_waiting(self):
        return len(self._pending)

    def write(self, data):
        self._pending += self._replies.get(data.strip(), b"")

    def read(self, size):
        data, self._pending = self._pending[:size], self._pending[size:]
        return data

    def reset_input_buffer(self):
        self._pending = b""

    def close(self):
        self.closed = True


def connect_to(monkeypatch, replies):
    port = FakeSerial(replies)
    monkeypatch.setattr(ohaus_adventurer.serial, "Serial", lambda *arguments, **options: port)
    return port


def test_connect_identifies_the_balance_and_closes_the_port(monkeypatch):
    port = connect_to(monkeypatch, REPLIES)
    with OhausAdventurer.connect("/dev/cu.fake") as scale:
        assert scale.identity() == {"port": "/dev/cu.fake", "balance_id": "B816716802", "firmware": "Sr 1.06"}
        assert not port.closed
    assert port.closed


def test_connect_closes_the_port_when_the_balance_refuses(monkeypatch):
    port = connect_to(monkeypatch, REPLIES | {b"IP": b"EL\r\n"})
    with pytest.raises(BenchError, match="refused"), OhausAdventurer.connect("/dev/cu.fake"):
        pass
    assert port.closed
