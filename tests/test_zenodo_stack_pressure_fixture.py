from __future__ import annotations

from pathlib import Path

import pytest

import battery_data_standard as bds
from battery_data_standard.validation import validate

FIXTURE = Path(__file__).with_name("240805_MBTF_DYNAMIC_SPRINGS_01_Channel_1_Wb_1.xlsx")


pytestmark = pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="Zenodo stack-pressure workbook fixture is not available in tests/.",
)


def test_zenodo_stack_pressure_workbook_converts_to_bds_timeseries(tmp_path):
    kind = bds.detect_kind(FIXTURE)
    detection = bds.detect(FIXTURE)
    df, report = bds.read_with_report(
        FIXTURE,
        cycler="auto",
        current_sign="preserve",
        repair_policy="warn",
    )

    assert kind.kind == "timeseries"
    assert detection.cycler == "arbin"
    assert report.cycler == "arbin"
    assert report.schema_version == bds.BDS_SCHEMA_VERSION
    assert report.validation.valid
    assert report.sheet_name == "Channel-1_1"
    assert report.metadata["selected_sheets"] == ["Channel-1_1"]
    assert df.height == 18405
    assert validate(df).valid

    assert df["test_time_s"].min() == pytest.approx(300.0006)
    assert df["test_time_s"].max() == pytest.approx(243578.2982)
    assert df["voltage_v"].min() == pytest.approx(2.999246)
    assert df["voltage_v"].max() == pytest.approx(4.200632)
    assert df["current_a"].min() == pytest.approx(-68.16183)
    assert df["current_a"].max() == pytest.approx(13.65068)
    assert df["cycle_index"].unique().sort().to_list() == [1, 2]

    output = tmp_path / "stack_pressure.bds.csv"
    export_report = bds.convert(
        FIXTURE,
        output,
        cycler="auto",
        current_sign="preserve",
        repair_policy="warn",
    )

    assert output.exists()
    assert export_report.metadata["export_target"] == "bds"
    assert export_report.output_path == str(output)
    assert export_report.columns[:8] == [
        "Record Index",
        "Date Time",
        "Test Time (s)",
        "Voltage (V)",
        "Current (A)",
        "Cycle Count",
        "Step Index",
        "Step Time (s)",
    ]


def test_zenodo_stack_pressure_workbook_explicit_eis_sheet_routes_to_eis():
    kind = bds.detect_kind(FIXTURE, sheet="ACIM_chan_1")
    df = bds.read_eis(FIXTURE, sheet="ACIM_chan_1")
    report = bds.validate_eis(df)

    assert kind.kind == "eis"
    assert df.height == 1600
    assert df.columns[:5] == [
        "Frequency_Hz",
        "Zre_exp_Ohm",
        "Zim_exp_Ohm",
        "-Zim_exp_Ohm",
        "Phase_exp_deg",
    ]
    assert report.valid


def test_zenodo_stack_pressure_workbook_pybamm_target_exports_compact_profile(tmp_path):
    output = tmp_path / "stack_pressure_pybamm.csv"

    report = bds.convert(
        FIXTURE,
        output,
        cycler="auto",
        current_sign="preserve",
        repair_policy="warn",
        target="pybamm",
    )

    assert output.exists()
    assert report.metadata["export_target"] == "pybamm"
    assert report.columns == ["time_s", "current_a"]
