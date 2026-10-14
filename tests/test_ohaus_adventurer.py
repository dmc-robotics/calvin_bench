"""The balance driver against FakeBalance, and its parsing against replies recorded from the real AX8201/E."""
import pytest

from bench.hardware import ohaus_adventurer
from bench.hardware.ohaus_adventurer import OhausAdventurer, OhausError, Quantity, Weight, parse_weight
from fakes import FakeBalance

PORT = "/dev/cu.fake"


@pytest.fixture
def fake(monkeypatch):
    fake = FakeBalance(load_g=263.1)
    monkeypatch.setattr(ohaus_adventurer.serial, "Serial", lambda *arguments, **options: fake)
    return fake


@pytest.fixture
def balance(fake):
    with OhausAdventurer.connect(PORT) as balance:
        fake.received.clear()
        yield balance


@pytest.mark.parametrize("line, weight", [
    ("        0.0     g", Weight(0.0, "g", True, False)),
    ("      263.1     g", Weight(263.1, "g", True, False)),
    ("        4.0     g ?", Weight(4.0, "g", False, False)),
    ("        0.0     g N", Weight(0.0, "g", True, True)),
    ("      -10.0     g N", Weight(-10.0, "g", True, True)),
    ("     -263.1     g", Weight(-263.1, "g", True, False)),
    ("     1.3651     g ? NET", Weight(1.3651, "g", False, True)),  # the manual's spelling
    ("      0.263    kg", Weight(0.263, "kg", True, False)),
])
def test_weight_lines_parse(line, weight):
    assert parse_weight(line.strip()) == weight


@pytest.mark.parametrize("line", [
    "Tare:        0.0     g T", "Gross:        0.0     g G", "Net:        0.0     g N", "APW: 2.06 g",
    "Balance ID: B816716802", "Weighing", "10/14/2026               16:47", "OK!", "S S        0.0 g", "0.0",
])
def test_other_lines_are_not_weights(line):
    assert parse_weight(line) is None


def test_connect_identifies_the_balance_turns_acknowledgements_on_and_closes_the_port(fake):
    with OhausAdventurer.connect(PORT) as balance:
        assert balance.identity() == {"port": PORT, "balance_id": "B000000001", "firmware": "Sr 1.06"}
        assert fake.received[:2] == ["1RL", "0P"]
        assert fake.acknowledge
        assert not fake.closed
    assert fake.closed


def test_connect_stops_a_print_mode_left_running(fake):
    fake.acknowledge = True
    fake.continuous = True
    with OhausAdventurer.connect(PORT):
        assert not fake.continuous


@pytest.mark.parametrize("setup, message", [
    (lambda fake: setattr(fake, "standby", True), "standby"),
    (lambda fake: setattr(fake, "silent", True), "No reply to 1RL"),
    (lambda fake: setattr(fake, "unit", "kg"), "reading in kg. Switch it to g"),
])
def test_connect_refuses_and_closes_the_port(fake, setup, message):
    setup(fake)
    with pytest.raises(OhausError, match=message), OhausAdventurer.connect(PORT, unit="g"):
        pass
    assert fake.closed


def test_connect_closes_the_port_on_ctrl_c(fake):
    with pytest.raises(KeyboardInterrupt), OhausAdventurer.connect(PORT):
        raise KeyboardInterrupt
    assert fake.closed


def test_a_port_that_wont_open_raises_ohaus_error(monkeypatch):
    def refuse(*arguments, **options):
        raise ohaus_adventurer.serial.SerialException("[Errno 2] No such file or directory")

    monkeypatch.setattr(ohaus_adventurer.serial, "Serial", refuse)
    with pytest.raises(OhausError, match="Can't open the balance on /dev/cu.fake"), OhausAdventurer.connect(PORT):
        pass


def test_tare_makes_weights_net_and_zero_clears_it(fake, balance):
    balance.tare()
    assert balance.weight() == Weight(0.0, "g", True, True)
    assert balance.tare_weight() == Quantity(263.1, "g")
    fake.load_g = 0.0
    assert balance.weight() == Weight(-263.1, "g", True, True)
    balance.zero()
    assert balance.weight() == Weight(0.0, "g", True, False)
    assert fake.received == ["T", "IP", "PT", "IP", "Z", "IP"]


def test_preset_tare(fake, balance):
    balance.set_tare(12.34)
    assert balance.tare_weight() == Quantity(12.3, "g")
    balance.clear_tare()
    assert balance.tare_weight() == Quantity(0.0, "g")
    assert fake.received == ["12.34T", "PT", "0T", "PT"]


def test_a_refused_value_raises(balance):
    with pytest.raises(OhausError, match="refused -5T: not a command it knows, or a bad value"):
        balance.set_tare(-5)


def test_standby_refuses_everything_until_wake(fake, balance, monkeypatch):
    monkeypatch.setattr(ohaus_adventurer, "REPLY_TIMEOUT_S", 0.05)
    fake.transition_commands = 2  # the real one keeps weighing ~0.3 s after OFF, and ignores commands ~1.1 s after ON
    balance.standby()
    with pytest.raises(OhausError, match="standby"):
        balance.weight()
    balance.wake()
    assert balance.weight().value == 263.1
    assert fake.received == ["OFF", "IP", "IP", "IP", "IP", "ON", "IP", "IP", "IP", "IP"]


def test_calibration(fake, balance):
    balance.begin_span_calibration()
    with pytest.raises(OhausError, match="busy"):
        balance.weight()
    balance.abort_calibration()
    balance.weight()
    with pytest.raises(OhausError, match="this model doesn't have it"):
        balance.begin_internal_calibration()
    assert fake.received == ["C", "IP", "AC", "IP", "IC"]


def test_counting_and_percent_weights(fake, balance):
    balance.set_piece_weight(2.5)
    assert balance.piece_weight() == Quantity(2.5, "g")
    balance.set_reference_weight(1000)
    assert balance.reference_weight() == Quantity(1000.0, "g")
    assert fake.received == ["2.5#", "P#", "1000%", "P%"]


def test_header_lines(fake, balance):
    balance.set_header(1, "Calvin bench")
    assert balance.header(1) == "Calvin bench"
    assert balance.header(5) == ""
    assert fake.received == ['H 1 "Calvin bench"', "1H", "5H"]
    with pytest.raises(ValueError):
        balance.header(6)
    with pytest.raises(ValueError):
        balance.set_header(2, "x" * 26)


def test_print_modes(fake, balance):
    balance.print_when_stable()
    balance.print_when_stable(include_zero=True)
    balance.print_every(2)
    for seconds in (2.5, True, 0, 3601):
        with pytest.raises(ValueError):
            balance.print_every(seconds)
    balance.print_continuously()
    assert [weight.value for weight in balance.readings()] == [263.1]
    balance.stop_printing()
    assert balance.readings() == []
    assert fake.received == ["SLP", "SLZP", "2P", "CP", "0P"]


def test_stable_weight_waits_for_a_stable_reading(fake, balance, monkeypatch):
    replies = iter([False, False, True])
    monkeypatch.setattr(FakeBalance, "weight_line", lambda self: f"263.1 g{'' if next(replies) else ' ?'}")
    assert balance.stable_weight() == Weight(263.1, "g", True, False)
    assert fake.received == ["IP", "IP", "IP"]


def test_poll_never_waits_and_keeps_one_request_outstanding(fake, balance, monkeypatch):
    monkeypatch.setattr(ohaus_adventurer.time, "sleep", lambda seconds: pytest.fail("poll slept"))
    fake.lag = 2
    readings = [balance.poll() for _ in range(4)]
    assert readings[:3] == [[], [], []]
    assert readings[3] == [Weight(263.1, "g", True, False)]
    assert fake.received == ["IP", "IP"]  # the second only once the first was answered


def test_poll_asks_again_when_a_reply_is_lost(fake, balance, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(ohaus_adventurer.time, "monotonic", lambda: clock[0])
    fake.silent = True
    balance.poll()
    balance.poll()
    clock[0] += ohaus_adventurer.REPLY_TIMEOUT_S + 0.01
    balance.poll()
    assert fake.received == ["IP", "IP"]


def test_poll_raises_when_the_balance_goes_to_standby(fake, balance):
    fake.standby_after_weights = 2
    balance.poll()
    balance.poll()
    with pytest.raises(OhausError, match="standby"):
        balance.poll()


def test_poll_checks_the_unit(fake):
    with OhausAdventurer.connect(PORT, unit="g") as balance:
        fake.unit = "kg"
        balance.poll()
        with pytest.raises(OhausError, match="reading in kg"):
            balance.poll()


def test_clear_waits_out_a_reply_in_flight(fake, balance):
    fake.lag = 3
    balance.poll()  # asks while 263.1 g is on the pan
    fake.load_g = 100.0
    balance.clear()
    readings = []
    while not readings:
        readings = balance.poll()
    assert readings == [Weight(100.0, "g", True, False)]


def test_poll_asks_again_as_soon_as_any_reply_arrives(fake, balance, monkeypatch):
    monkeypatch.setattr(FakeBalance, "weight_line", lambda self: "Overload")
    balance.poll()
    assert balance.poll() == []
    assert fake.received == ["IP", "IP"]


def test_clear_drops_a_line_caught_halfway(fake, balance):
    fake.arrive(b"      26")
    balance.clear()
    fake.arrive(b"3.1     g\r\n      263.2     g\r\n")
    assert balance.readings() == [Weight(263.2, "g", True, False)]


def test_an_unplugged_balance_raises_ohaus_error_not_the_failed_close(fake):
    with pytest.raises(OhausError, match="Lost the balance on /dev/cu.fake"), OhausAdventurer.connect(PORT) as balance:
        fake.unplugged = True
        balance.poll()
