"""Run folders: runs/<timestamp>_<experiment>_<motor>/ holding meta.json, CSV tables and JSON files, finished.json
once the recording ended normally (an aborted run has none), and code.diff when it was recorded with uncommitted changes.

The only code that reads or writes run folders. Rows go in as dataclasses (their fields are the CSV columns)
and come back as the same dataclasses.
"""
import csv
import json
import subprocess
import typing
from dataclasses import asdict, fields
from datetime import datetime
from pathlib import Path

from bench.errors import BenchError

REPOSITORY = Path(__file__).resolve().parent.parent
RUNS_DIRECTORY = REPOSITORY / "runs"


class Run:
    def __init__(self, directory):
        self.directory = Path(directory)

    @classmethod
    def create(cls, experiment, motor, meta):
        """A new run folder with meta.json: `experiment` and `motor` (which `bench analyze` dispatches on), when it
        started, the code that recorded it, then `meta`. Uncommitted changes to that code go in code.diff."""
        started = datetime.now().astimezone()
        run = cls(RUNS_DIRECTORY / f"{started:%Y-%m-%d_%H%M%S}_{experiment}_{motor}")
        run.directory.mkdir(parents=True)
        diff = git("diff", "HEAD")
        if diff:
            run.path("code.diff").write_text(diff)
        code = {"commit": git("rev-parse", "HEAD").strip(), "uncommitted_changes": bool(diff)}
        run.write_json("meta", {
            "experiment": experiment, "motor": motor, "started_at": started.isoformat(timespec="seconds"), "code": code, **meta,
        })
        return run

    @property
    def name(self):
        return self.directory.name

    @property
    def meta(self):
        return self.read_json("meta")

    @property
    def finished(self):
        return self.path("finished.json").exists()

    def finish(self):
        """Mark the recording as ended normally, so batch analyses can skip aborted runs."""
        self.write_json("finished", {"finished_at": datetime.now().isoformat(timespec="seconds")})

    def path(self, filename):
        return self.directory / filename

    def write_json(self, name, data):
        self.path(f"{name}.json").write_text(json.dumps(data, indent=2) + "\n")

    def read_json(self, name):
        return json.loads(self._existing(f"{name}.json").read_text())

    def append(self, table, *rows):
        """Append dataclass rows to <table>.csv, writing the header (the dataclass fields) when the file is new."""
        if not rows:
            return
        path = self.path(f"{table}.csv")
        is_new = not path.exists()
        with path.open("a", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(asdict(rows[0])))
            if is_new:
                writer.writeheader()
            writer.writerows(asdict(row) for row in rows)

    def rows(self, table, row_type):
        """<table>.csv as `row_type` dataclasses: each cell converted to its field's type, empty cells to None."""
        types = {field.name: field.type for field in fields(row_type)}
        with self._existing(f"{table}.csv").open() as file:
            reader = csv.DictReader(file)
            if missing := [name for name in types if name not in (reader.fieldnames or [])]:
                raise BenchError(f"{self.name}/{table}.csv is missing columns: {', '.join(missing)}.")
            return [
                row_type(**{name: cell(row[name], types[name], f"{table}.csv line {reader.line_num}, {name}") for name in types})
                for row in reader
            ]

    def _existing(self, filename):
        if not (path := self.path(filename)).exists():
            raise BenchError(f"{self.directory} has no {filename}.")
        return path


def git(*arguments):
    return subprocess.run(["git", "-C", str(REPOSITORY), *arguments], capture_output=True, text=True, check=True).stdout


def cell(text, field_type, where):
    """A CSV cell as `field_type`: str, int, float or bool, or one of those | None."""
    optional = type(None) in typing.get_args(field_type)
    if not text:  # empty, or missing from a short row
        if optional:
            return None
        raise BenchError(f"{where} is empty.")
    value_type = next(arg for arg in typing.get_args(field_type) if arg is not type(None)) if optional else field_type
    try:
        if value_type is bool:
            return {"True": True, "False": False}[text]
        return value_type(text)
    except (KeyError, ValueError):
        raise BenchError(f"{where} is {text!r}, expected {value_type.__name__}.")
