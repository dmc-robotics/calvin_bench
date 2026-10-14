# TODO: `bench` code review follow-up

_Review of 2026-10-13. Item IDs (H1, M3, …) are for reference in questions. Do the steps in order, one commit each, with `uv run pytest` green after each._

**Verdict:** in good shape for ~900 lines: safety lives in `finally` blocks and context managers, the analysis is pure, the tests run the real driver against a fake device, and there's one module each for run folders and prompts. No rewrite needed. The main issues are `SystemExit` used as the error mechanism, a three-call safety sequence, an experiment template modeled on the one atypical experiment, run data that loses its types when read back, and docs that already disagree with the code.

## Decisions for you

- [ ] **Hold index column** (M3): add a `hold` column to `data.csv` and `scale.csv`, so a repeated hold's scale samples can be told apart and linked to their measurement row. This changes the CSV format.
- [ ] **Delete Python stubs** (Low): remove `bench/waveforms.py`, `bench/hardware/link.py` and the unused `scipy` dependency until M3. PLAN already describes them.
- [x] **Split `hold()`** (H2): the driver keeps the safety (`armed()` context + `apply(torque_Nm, seconds, during)`); the profile, overshoot, sampling window and averaging move to static-gain's procedure. Done in step 2.
- [ ] **Typed run reader** (M1): approve `Run.rows(table, RowType)` returning dataclasses. For the 1 kHz data at M3, choosing between numpy structured arrays and pandas is a separate decision.

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
- [ ] Move every settings check into `Settings.__post_init__`: positive values, arm length < 1 m, ≥ 3 distinct levels, `0 < sample_s ≤ hold_s`, and max torque. Keep the argparse types to parsing only (`static_gain/__init__.py:54–65`).
- [ ] Remove the `data.py` → `bench.hardware.scale` import (`data.py:4,20`) and let the CLI supply the default port.
- [ ] Keep one constant for the experiment name: `NAME = EXPERIMENT` (`static_gain/__init__.py:17`, `data.py:6`).
- [ ] Tests for the `Settings` validation cases.

### 4. M3: make `procedure.py` easier to read
- [ ] Rename `Recorder` (`procedure.py:70`) to `Session`. Today it has the same name as InstinctusCore's ISR ring buffer `Recorder`.
- [ ] Move the `scale.csv` append out of `_reading()` (`:138`) into `tare()`/`level()`. Today a getter-like method has a hidden write.
- [ ] Replace "`None` means repeat", which is passed through `console.ask_number` and `_reading`, with a named `REPEAT` sentinel.
- [ ] Build `Measurement` with keyword arguments (`procedure.py:170–175`, `tests/test_static_gain_analysis.py:28–31,37`).
- [ ] _(If decided)_ Add the `hold` index column, and update the columns in `instructions/02`.

### 5. M1 + M2: typed data from run folders to report
Why: rows are written as dataclasses but read back as `dict[str, str]`. So the "pure" analysis parses CSV strings, and `report.py` looks up results by string key.
- [ ] Add `Run.rows(table, RowType)` returning row dataclasses: empty cells become `None` and `"True"`/`"False"` become booleans (`runs.py:57–59`).
- [ ] Use attributes in the analysis and drop `column()`'s string parsing (`analysis.py:59–65,110–111`).
- [ ] Add `DirectionResult` and `Results` dataclasses, with `None` for absent values and `asdict()` for `results.json`. `DirectionFit` then holds the arrays plus `result` (`analysis.py:14–22,43–54,82–96`).
- [ ] Make `report.py` read attributes instead of `summary['k']` and the `"key" in results` checks (`report.py:13–30`).
- [ ] Tests: the typed round trip, including `None` and `bool` cells. Analysis tests can pass `Measurement`s directly.

### 6. M5: one lifecycle shape for every instrument
- [ ] Add `Scale.connect(port)` as a classmethod context manager, matching `ODriveUsb.connect`. Today `Scale.__init__` does I/O (`scale.py:37–62`, `procedure.py:34–38`).

### 7. M6 + Low: docs and tidy-ups
- [ ] `README.md:5` says Instinctus is "This Repo". Fix it to describe calvin_bench.
- [ ] Rewrite the `units.py` docstring (`:1–5`) to describe what's there now, not the rev→rad functions that don't exist yet.
- [ ] `instructions/02` Procedure: the refusal list leaves out the `vel_gain`, `torque_constant` and `current_soft_max` checks. Describe what the person does, and say the script lists every problem.
- [ ] Trim module docstrings that repeat the layout (`static_gain/__init__.py:4–7`, `procedure.py:3–4`, `experiments/__init__.py`). The layout belongs in CLAUDE.md.
- [ ] H3 wording: in `experiments/__init__.py`, CLAUDE.md ("same shape") and PLAN's Python layout row, make the **entry points** the contract (`NAME`, `DESCRIPTION`, `add_arguments`, `record`, `analyze`) and the four-file split optional.
- [ ] Import `TORQUE_CONSTANT_NMA` from `tests/fakes.py` instead of repeating it in `test_static_gain_analysis.py:10`.
- [x] Rename the procedure's `odrive` variable to `drive` (done in step 2), so it doesn't share a name with the `odrive` library used in `odrive_usb.py`.
- [ ] _(If decided)_ Delete the Python stubs and `scipy`.

## M3 design notes (record in PLAN.md Decisions, don't build yet)

- [ ] **H3:** use one shared waveform procedure, `record_waveform(link, waveform, run)` (load → play → stream rows). A waveform experiment supplies only `Settings`, a waveform, `fit` and `report`, so it doesn't copy static-gain's `procedure.py`.
- [ ] Write 1 kHz streams through an open writer instead of reopening the file on every `Run.append`.
- [ ] Read 1 kHz tables back as columns (numpy structured arrays or pandas), not row objects.
- [ ] Move `NODE_IDS` (the motor names) out of `odrive_usb.py:20` once experiments that don't use the USB driver need `--motor`.

## Leave alone

- The `finally`/context-manager safety in `hold()` and `connect()`. The tests that use the real driver against `FakeDevice`.
- Pure `analysis.fit`, `runs.py` as the only file I/O, `console.py` as the only place that prompts.
- The experiment registry in `cli.py`, the unit-suffixed names, and the raw ODrive sign convention.
- `arguments.py` as its own module: putting it in `cli.py` would create an import cycle.
- `Signals`/`Weight` as `NamedTuple`s (`Signals` relies on being a tuple for `zip(*samples)`).
- The tests' monkeypatching of module globals. It's acceptable at this size; pass the instruments in instead if it spreads.
