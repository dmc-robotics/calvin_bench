"""Rows go into a run folder as dataclasses and come back as the same dataclasses."""
from dataclasses import dataclass

import pytest

from bench.errors import BenchError
from bench.runs import Run


@dataclass(frozen=True)
class Row:
    count: int
    name: str
    value: float
    maybe: float | None
    flag: bool


def test_rows_round_trip_with_types(tmp_path):
    rows = [Row(1, "a", 0.25, None, True), Row(2, "b", -1.5, 3.0, False)]
    run = Run(tmp_path)
    run.append("table", *rows)
    assert run.rows("table", Row) == rows


def test_an_empty_cell_in_a_required_column_is_refused(tmp_path):
    (tmp_path / "table.csv").write_text("count,name,value,maybe,flag\n1,a,,,True\n")
    with pytest.raises(BenchError, match="line 2, value is empty"):
        Run(tmp_path).rows("table", Row)


def test_a_cell_of_the_wrong_type_is_refused(tmp_path):
    (tmp_path / "table.csv").write_text("count,name,value,maybe,flag\n1,a,0.5,,yes\n")
    with pytest.raises(BenchError, match="flag is 'yes', expected bool"):
        Run(tmp_path).rows("table", Row)


def test_a_missing_column_is_refused(tmp_path):
    (tmp_path / "table.csv").write_text("count,name,value\n1,a,0.5\n")
    with pytest.raises(BenchError, match="missing columns: maybe, flag"):
        Run(tmp_path).rows("table", Row)


def test_a_missing_file_is_refused(tmp_path):
    run = Run(tmp_path)
    with pytest.raises(BenchError, match="has no meta.json"):
        run.meta
    with pytest.raises(BenchError, match="has no table.csv"):
        run.rows("table", Row)


def test_a_run_is_finished_once_marked(tmp_path):
    run = Run(tmp_path)
    assert not run.finished
    run.finish()
    assert run.finished
