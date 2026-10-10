"""Run folders: runs/<timestamp>_<experiment>_<motor>/ with meta.json and data.csv."""
import json
from datetime import datetime
from pathlib import Path

RUNS_DIRECTORY = Path(__file__).resolve().parent.parent / "runs"


def create_run_directory(experiment, motor):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_directory = RUNS_DIRECTORY / f"{timestamp}_{experiment}_{motor}"
    run_directory.mkdir(parents=True)
    return run_directory


def write_meta(run_directory, meta):
    (Path(run_directory) / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")


def read_meta(run_directory):
    return json.loads((Path(run_directory) / "meta.json").read_text())
