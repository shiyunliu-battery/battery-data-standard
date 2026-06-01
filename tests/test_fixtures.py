from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import bds
from battery_data_standard.validation import validate

FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def _fixture_cases() -> list[tuple[Path, dict]]:
    cases: list[tuple[Path, dict]] = []
    for manifest in sorted(FIXTURE_ROOT.glob("*/manifest.jsonl")):
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if line.strip():
                cases.append((manifest.parent, json.loads(line)))
    return cases


@pytest.mark.parametrize(
    ("fixture_dir", "case"),
    _fixture_cases(),
    ids=lambda value: value.get("name", str(value)) if isinstance(value, dict) else value.name,
)
def test_public_fixture_converts_and_validates(fixture_dir: Path, case: dict):
    source = fixture_dir / case["input"]

    detected = bds.detect(source)
    df, report = bds.read_with_report(
        source,
        cycler=case.get("cycler_arg", "auto"),
        current_sign=case.get("current_sign", "charge-positive"),
        repair_policy=case.get("repair_policy", "warn"),
        strict=False,
    )
    validation = validate(df, strict=False)

    assert detected.cycler == case["expected_cycler"]
    assert report.cycler == case["expected_cycler"]
    assert report.support_tier in {"fixture-backed", "best_effort"}
    assert report.raw_rows is None or report.raw_rows >= case["min_rows"]
    assert df.height >= case["min_rows"]
    assert validation.valid
    for column in case["required_columns"]:
        assert column in df.columns
    assert df["test_time_s"].to_list()[0] == pytest.approx(case["expected_first_time"])


def test_fixture_cli_convert_writes_report(tmp_path):
    source = FIXTURE_ROOT / "neware" / "flat.csv"
    output = tmp_path / "neware.bdf.csv"
    report = tmp_path / "report.json"

    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "battery_data_standard.cli",
            "convert",
            str(source),
            str(output),
            "--cycler",
            "auto",
            "--report",
            str(report),
        ],
        text=True,
        capture_output=True,
        check=True,
    )

    stdout_report = json.loads(run.stdout)
    saved_report = json.loads(report.read_text(encoding="utf-8"))
    assert output.exists()
    assert stdout_report["cycler"] == "neware"
    assert stdout_report["encoding"] == "utf-8-sig"
    assert stdout_report["delimiter"] == ","
    assert stdout_report["header_row"] == 0
    assert saved_report["unmapped_columns"] == stdout_report["unmapped_columns"]
