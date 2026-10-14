"""Run folders: runs/<timestamp>_<experiment>_<motor>/ holding meta.json, CSV tables and JSON files.

The only code that reads or writes run folders. Rows go in as dataclasses (their fields are the CSV columns)
and come back as dicts of strings, as csv.DictReader gives them.
"""
import csv
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

RUNS_DIRECTORY = Path(__file__).resolve().parent.parent / "runs"


class Run:
    def __init__(self, directory):
        self.directory = Path(directory)

    @classmethod
    def create(cls, experiment, motor, meta):
        """A new run folder with meta.json: `experiment` and `motor` (which `bench analyze` dispatches on), then `meta`."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        run = cls(RUNS_DIRECTORY / f"{timestamp}_{experiment}_{motor}")
        run.directory.mkdir(parents=True)
        run.write_json("meta", {"experiment": experiment, "motor": motor, **meta})
        return run

    @property
    def name(self):
        return self.directory.name

    @property
    def meta(self):
        return self.read_json("meta")

    def path(self, filename):
        return self.directory / filename

    def write_json(self, name, data):
        self.path(f"{name}.json").write_text(json.dumps(data, indent=2) + "\n")

    def read_json(self, name):
        return json.loads(self.path(f"{name}.json").read_text())

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

    def rows(self, table):
        with self.path(f"{table}.csv").open() as file:
            return list(csv.DictReader(file))
