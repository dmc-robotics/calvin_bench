# TODO: `bench` code review follow-up

_Review of 2026-10-13. Item IDs (H1, M3, …) are for reference in questions. Do the steps in order, one commit each, with `uv run pytest` green after each._

**Verdict:** in good shape for ~900 lines: safety lives in `finally` blocks and context managers, the analysis is pure, the tests run the real driver against a fake device, and there's one module each for run folders and prompts. No rewrite needed. The main issues are `SystemExit` used as the error mechanism, a three-call safety sequence, an experiment template modeled on the one atypical experiment, run data that loses its types when read back, and docs that already disagree with the code.

## Decisions for you

- [x] **Hold index column** (M3): add a `hold` column to `data.csv` and `scale.csv`, so a repeated hold's scale samples can be told apart and linked to their measurement row. This changes the CSV format.
- [x] **Delete Python stubs** (Low): remove `bench/waveforms.py`, `bench/hardware/link.py` and the unused `scipy` dependency until M3. Decided 2026-10-14: keep them. They mark where M3's code goes, and M3 will likely need `scipy`.
- [x] **Split `hold()`** (H2): the driver keeps the safety (`armed()` context + `apply(torque_Nm, seconds, during)`); the profile, overshoot, sampling window and averaging move to static-gain's procedure. Done in step 2.
- [x] **Typed run reader** (M1): approve `Run.rows(table, RowType)` returning dataclasses. For the 1 kHz data at M3, choosing between numpy structured arrays and pandas is a separate decision.

## Steps

### 1. H1: exceptions in the core, exit codes at the edge
Why: drivers, a parser, a dataclass and the pure analysis each call `SystemExit`. That ties every layer to the CLI. `except Exception` can't catch it. One incomplete run would kill a batch analysis (experiments 9 and 11) or `bench serve`.
- [x] Add `bench/errors.py` with `class BenchError(Exception)`. No subclasses until something needs to catch one specifically.
- [x] Remove `ShaftMoved` (`odrive_usb.py:36`): the shaft-motion check raises `BenchError`. Delete the catch-and-reword in `procedure.py:124–125`.
- [x] Replace the `raise SystemExit` sites: `console.py:8`, `odrive_usb.py:118,226`, `scale.py:41,50,103,118`, `analysis.py:41`, `data.py:30`.
- [x] In `cli.main`, catch `BenchError` once (`parser.exit(1, f"{error}\n")`), next to the `KeyboardInterrupt` handler.
- [x] Give a friendly `BenchError` for an unknown `experiment` in `meta.json` (`cli.py:32` currently raises `KeyError`).
- [x] Tests: change `pytest.raises(SystemExit)` to `BenchError`, and add a test that an incomplete run raises `BenchError`.

### 2. H2: make the safe path the only path
Why: a procedure currently has to call `connect()`, then `require_ready()`, then `velocity_cap_for()`, then `velocity_limited()`. Forgetting either of the middle two leaves the motor unchecked or uncapped. That breaks the CLAUDE.md layering: `odrive_usb.py` owns motor safety, config checks included, and procedures have no safety logic of their own.
- [x] `ODriveUsb.connect(motor, highest_torque_Nm)` finds the ODrive, idles it, runs the checks (raising before anything changes), lowers `vel_limit` and yields. On exit it restores `vel_limit` and idles.
- [x] Expose `velocity_cap_rev_per_s` as an attribute for `meta.json`. `velocity_cap_for` is private; `velocity_limited` is folded into `connect` (idle first, then restore).
- [x] Remove the bare getter calls in `require_ready` (`odrive_usb.py:112–115`). The early read is now one named method, `_read_every_property_used()`.
- [x] Torque guard: `connect` stores `highest_torque_Nm`. `apply()` raises `BenchError` for a larger torque before setting it, because above it the cap and the `current_soft_max` check no longer hold and the data would be silently clipped. Test: an over-limit torque raises and is never commanded.
- [x] Split `hold()` into `armed()` + `apply()` in the driver; the overshoot, sampling window and averaging move to `procedure.py`.
- [x] `apply()` times each `during()` call and raises `BenchError` if one takes longer than `DURING_LIMIT_S` (the shortest allowed watchdog timeout).
- [x] Update `procedure.py:38–40,58` and `tests/test_odrive_usb.py`. The safety tests keep their intent: idle on exit, wrong ODrive moves nothing, `vel_limit` restored.

### 3. M4: validation and defaults in one place
Why: validation is split across argparse types, `Settings.__post_init__` and the driver. A `Settings` built in code skips the argparse checks, and nothing checks `0 < sample_s ≤ hold_s` (an empty average fails after the hold).
- [x] Move every settings check into `Settings.__post_init__`: positive values, arm length < 1 m, ≥ 3 distinct levels, `0 < sample_s ≤ hold_s`, and max torque. Keep the argparse types to parsing only (`static_gain/__init__.py:54–65`).
- [x] Remove the `data.py` → `bench.hardware.scale` import (`data.py:4,20`) and let the CLI supply the default port.
- [x] Keep one constant for the experiment name: `NAME` in `data.py`, re-exported by the package (`EXPERIMENT` is gone).
- [x] Move `NODE_IDS` to `bench/motors.py` so `Settings` can check the motor name without importing the driver. `arguments.py` is gone: nothing left to share.
- [x] Tests for the `Settings` validation cases (`tests/test_static_gain_settings.py`).

### 4. M3: make `procedure.py` easier to read
- [x] Rename `Recorder` (`procedure.py:70`) to `Session`. Today it has the same name as InstinctusCore's ISR ring buffer `Recorder`.
- [x] Move the `scale.csv` append out of `_reading()` (`:138`) into `tare()`/`level()`. Today a getter-like method has a hidden write.
- [x] Replace "`None` means repeat", which is passed through `console.ask_number` and `_reading`, with a named `REPEAT` sentinel.
- [x] Build `Measurement` with keyword arguments (`procedure.py:170–175`, `tests/test_static_gain_analysis.py:28–31,37`).
- [x] Add the `hold` index column, and update the columns in `instructions/02`. Tares get numbers too, since they have scale samples; a repeated hold uses up a number and has no `data.csv` row.

### 5. M1 + M2: typed data from run folders to report
Why: rows are written as dataclasses but read back as `dict[str, str]`. So the "pure" analysis parses CSV strings, and `report.py` looks up results by string key.
- [x] Add `Run.rows(table, RowType)` returning row dataclasses: empty cells become `None` and `"True"`/`"False"` become booleans (`runs.py:57–59`).
- [x] Use attributes in the analysis and drop `column()`'s string parsing (`analysis.py:59–65,110–111`).
- [x] Add `DirectionResult` and `Results` dataclasses, with `None` for absent values and `asdict()` for `results.json`. `DirectionFit` then holds the arrays plus `result` (`analysis.py:14–22,43–54,82–96`).
- [x] Make `report.py` read attributes instead of `summary['k']` and the `"key" in results` checks (`report.py:13–30`).
- [x] Tests: the typed round trip, including `None` and `bool` cells. Analysis tests can pass `Measurement`s directly.

### 6. M5: one lifecycle shape for every instrument
- [x] Add `OhausAdventurer.connect(port)` as a classmethod context manager, matching `ODriveUsb.connect`. Today `OhausAdventurer.__init__` does I/O (`ohaus_adventurer.py:37–62`, `procedure.py:34–38`).

### 7. M6 + Low: docs and tidy-ups
- [x] `README.md:5` says Instinctus is "This Repo". Fix it to describe calvin_bench.
- [x] Rewrite the `units.py` docstring (`:1–5`) to describe what's there now, not the rev→rad functions that don't exist yet.
- [x] `instructions/02` Procedure: the refusal list leaves out the `vel_gain`, `torque_constant` and `current_soft_max` checks. Describe what the person does, and say the script lists every problem.
- [x] Trim module docstrings that repeat the layout (`static_gain/__init__.py:4–7`, `procedure.py:3–4`, `experiments/__init__.py`). The layout belongs in CLAUDE.md.
- [x] H3 wording: in `experiments/__init__.py`, CLAUDE.md ("same shape") and PLAN's Python layout row, make the **entry points** the contract (`NAME`, `DESCRIPTION`, `add_arguments`, `record`, `analyze`) and the four-file split optional.
- [x] Import `TORQUE_CONSTANT_NMA` from `tests/fakes.py` instead of repeating it in `test_static_gain_analysis.py:10`.
- [x] Rename the procedure's `odrive` variable to `drive` (done in step 2), so it doesn't share a name with the `odrive` library used in `odrive_usb.py`.
- [x] ~~Delete the Python stubs and `scipy`.~~ Kept (see Decisions).

## After the steps

- [x] Flesh out `OhausAdventurer` (`bench/hardware/ohaus_adventurer.py`). Renamed from `Scale` (`scale.py`) on 2026-10-14: hardware classes and modules are named for the hardware; "scale" stays the generic word and variable name. The untracked `docs/` folder (the AX manual and datasheet) belongs to this work.
  - [x] Probe the real balance (no motor) for the replies the manual leaves out: `ES`/`EL`, `NET`, `OK!`, tare, standby, streaming, `PFMT`, calibration.
  - [x] Rewrite the driver as a self-contained file (pyserial only, `OhausError`) covering the manual's command table (Table 9-6), parsing the §7.2 output format including `NET` and `?`.
  - [x] `FakeBalance` serial stand-in in `tests/fakes.py`; driver tests from the probe's verbatim replies; procedure tests run the real driver.
  - [x] Experiment 2: `connect(port, unit="g")`, `DEFAULT_PORT` moves to `static_gain`, `hold_s` 2.5 → 3.0 s, the CLI catches `OhausError`, balance settings in `instructions/02`.
  - [x] Docs: CLAUDE.md Scale section, PLAN.md decision.

## Review of 2026-10-14 (architecture + code review)

### 1. Safety, in the ODrive driver
- [x] Replace `DURING_LIMIT_S` with a check of the time between watchdog feeds: raise if a gap passes half the configured `watchdog_timeout`; the accepted timeout range is now 0.1–0.2 s. The old 0.05 s `during()` limit equalled the shortest accepted timeout, so the sleep and USB reads could push a gap past it.
- [x] Torque guard rejects NaN: `if not abs(torque_Nm) <= limit`.
- [x] `armed()` refuses a motor that's too hot; `wait_until_cool` stays as the procedure's prompt.
- [x] `FakeAxis`: a watchdog that idles the axis after a feed gap longer than `watchdog_timeout`, and a settable `vel_estimate`. Tests: a feed gap aborts, a speed slip aborts, Ctrl-C mid-hold ends idle with `vel_limit` restored, NaN and a hot motor are refused.

### 2. Balance driver
- [x] `poll()` clears the pending request on any reply line, not only a weight (an unparseable reply slows it to one request per `REPLY_TIMEOUT_S`).
- [x] Wrap pyserial I/O errors (unplugged balance) as `OhausError`.
- [x] After `clear()` resets the input, drop the partial line up to the next line break (matters during a print mode).
- [x] Tidy: one name for the port (`connection` vs `_serial`), `print_every(True)` refused, neutral refusal wording in `readings()`.

### 3. CLI and docs
- [x] `Run.read_json`/`Run.rows` raise `BenchError` for a missing file (wrong path, run aborted before `data.csv`).
- [x] `instructions/02` step 6: `--from-above` at 0.30 N·m needs 12.0 A, so also raise `current_soft_max` to ~12 A.
- [x] An empty averaging window (a `sample_s` shorter than a tick) raises `BenchError` after the hold instead of a TypeError. Checked in the procedure, not `Settings`: the floor is the hold loop's tick, and a 0.1 s floor would slow the procedure tests.
- [x] Rename `std_g`/`scale_std_g` to `standard_deviation_g`/`scale_standard_deviation_g` (no recorded runs yet).
- [x] `meta["scale"]` is `None` without a balance, not `"manual"`.
- [x] A run marks itself finished (`finished.json`, `Run.finished`), so later batch analyses (experiment 9) can skip aborted runs.

### Bench check (needs the user's go-ahead)
- [ ] Arm once at zero torque: does ODrive 0.6.12 flag the watchdog while idle? If so, `armed()` fails every hold with "Clear the errors".

## Pre-run review of 2026-10-14 (before the first real experiment 2 run)

- [x] `odrive_config.json` is dumped in `connect()` before the velocity cap (`drive.configuration`), so it shows the real `vel_limit`.
- [x] `odrive.csv`: every hold-loop tick (time, feed gap, position, velocity, Iq setpoint and measured, vbus), overshoot and repeats included.
- [x] `meta.json` gets `started_at`. (Git provenance was added, then removed on the user's call: not needed.)
- [x] Temperatures in `data.csv` are read right after the hold, not before the rest.
- [x] Too few balance readings are used and flagged as low confidence (printed, and an analysis warning), never typed in. No readings at all stops the run.
- [x] The hold loop sleeps to the next tick instead of a fixed 0.02 s, so read time doesn't add to the feed gap. Each hold prints its largest gap.
- [x] No ODrive found raises `BenchError`; `scale.csv` gets a `net` column; the analysis warns about a run without `finished.json`; `instructions/02` fixes (step reference, don't save the raised `current_soft_max`).
- [x] Third code review: an aborted hold still writes its `odrive.csv`/`scale.csv` rows (the slip tick included); the fake watchdog counts trips; float tolerance on `max_torque_Nm`; the analysis counts only from-below levels and refuses a held level without Iq; the balance port has a write timeout; tick timestamps taken at the feed; `finished_at` has its UTC offset; safer test timing.
- [ ] **Bench check script (needs the user's go-ahead):** arm at zero torque while polling the balance (largest feed gap; does 0.6.12 flag the watchdog while idle?), then 0.02 N·m with the arm on the scale (Iq sign with `motor.direction = -1`; which way positive torque turns the shaft).
- [ ] Depending on the check: correct the Iq sign in the analysis (the clipping warning and Kt fit assume Iq has the command's sign), a setup line in `instructions/02` on finding the positive direction, and stop the run if the first level reads below the tare ("scale on the wrong side?").

## M3 design notes (record in PLAN.md Decisions, don't build yet)

- [ ] **H3:** use one shared waveform procedure, `record_waveform(link, waveform, run)` (load → play → stream rows). A waveform experiment supplies only `Settings`, a waveform, `fit` and `report`, so it doesn't copy static-gain's `procedure.py`.
- [ ] Write 1 kHz streams through an open writer instead of reopening the file on every `Run.append`.
- [ ] Read 1 kHz tables back as columns (numpy structured arrays or pandas), not row objects.
- [ ] **Teensy protocol, decide before M2** (it crosses firmware, `link.py` and every waveform run's CSV):
  - Torque *and* velocity mode (experiment 3's bench version is a velocity staircase; its stiction ramp is torque).
  - Waveforms longer than Teensy RAM (experiment 12: 60 s; experiment 11's warm-up: 5 min): chunked upload or `repeat n`.
  - The host sends a heartbeat every ≤ 50 ms during `play`; the Teensy's link timeout is defined on it.
  - Rows carry a sequence number and a dropped-sample counter (experiment 7).
  - How a two-motor run is recorded (M4, experiments 6–7): a `motor` column or prefixed columns.
- [ ] **ODrive USB stays plugged in, read-only, on M3 runs** (config dump, Kt, config checks). At M3 split a read-only `inspect()` out of `ODriveUsb.connect` for `link.py` to reuse; `connect` adds the stall-only checks and the velocity cap.
- [ ] **`link.py` gets `ODriveUsb`'s lifecycle:** `TeensyLink.connect(motor, limits)` pushes the limits and checks the echo, idles on every exit; `play()` is the only way to move a motor. Update CLAUDE.md's safety-ownership line then.
- [ ] **Analyses over several runs (M3–M5):** record inputs at record time (`meta["inputs"] = {"friction": "<run>"}`), add a `results(run)` entry point that reads `results.json` typed, mark held-out runs in meta, and put experiments 9/11/13 and export under one `bench compare`/`bench export` command rather than fake experiments.
- [x] Move `NODE_IDS` (the motor names) out of `odrive_usb.py:20` once experiments that don't use the USB driver need `--motor`. Done early in step 3 (`bench/motors.py`).

## Leave alone

- The `finally`/context-manager safety in `hold()` and `connect()`. The tests that use the real driver against `FakeDevice`.
- Pure `analysis.fit`, `runs.py` as the only file I/O, `console.py` as the only place that prompts.
- The experiment registry in `cli.py`, the unit-suffixed names, and the raw ODrive sign convention.
- `Signals`/`Weight` as `NamedTuple`s (`Signals` relies on being a tuple for `zip(*samples)`).
- The tests' monkeypatching of module globals. It's acceptable at this size; pass the instruments in instead if it spreads.
