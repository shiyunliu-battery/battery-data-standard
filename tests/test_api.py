from __future__ import annotations

import importlib
import json
import subprocess
import sys

import polars as pl
import pytest

import battery_data_standard as bds
from battery_data_standard import __version__
from battery_data_standard.validation import validate


def test_neware_flat_csv_normalizes_units_and_sign(tmp_path):
    raw = tmp_path / "neware.csv"
    raw.write_text(
        "\n".join(
            [
                "DateTime,Cycle ID,Step ID,Record ID,Time(h:min:s.ms),Voltage(V),Current(mA),Temperature(C),Capacitance_Chg(mAh),Capacitance_DChg(mAh),Engy_Chg(mWh),Engy_DChg(mWh),Status",
                "2026-01-01 00:00:00,1,1,1,0:00:00.0,3.50,1000,25,0,0,0,0,C",
                "2026-01-01 00:00:10,1,1,2,0:00:10.0,3.60,1000,25,10,0,36,0,C",
                "2026-01-01 00:00:20,1,2,3,0:00:00.0,3.55,1000,25,10,5,36,18,D",
            ]
        ),
        encoding="utf-8",
    )

    df = bds.read(raw, cycler="neware")

    assert {"Test Time / s", "Voltage / V", "Current / A"}.isdisjoint(df.columns)
    assert df["test_time_s"].to_list() == [0.0, 10.0, 20.0]
    assert df["current_a"].to_list() == [1.0, 1.0, -1.0]
    assert df["charge_capacity_ah"].to_list()[1] == pytest.approx(0.01)
    assert "power_w" in df.columns
    assert validate(df).valid


def test_neware_multisection_file(tmp_path):
    raw = tmp_path / "neware_multi.csv"
    raw.write_text(
        "\n".join(
            [
                '"Cycle ID","Other"',
                ',"Step ID","Status","DCIR(O)"',
                ',,"Record ID","Time(h:min:s.ms)","Voltage(V)","Current(mA)","Temperature(C)","Capacitance_Chg(mAh)","Capacitance_DChg(mAh)","Engy_Chg(mWh)","Engy_DChg(mWh)"',
                '1,"cycle-row"',
                ',"1","C","0.050"',
                ',,"1","0:00:00.0","3.50","1000","25","0","0","0","0"',
                ',,"2","0:00:10.0","3.60","1000","25","10","0","36","0"',
                ',"2","D","0.049"',
                ',,"3","0:00:00.0","3.55","1000","25","10","5","36","18"',
            ]
        ),
        encoding="utf-8",
    )

    df, report = bds.read_with_report(raw, cycler="neware", repair_policy="repair")

    assert df.height == 3
    assert df["test_time_s"].to_list() == [0.0, 10.0, 10.000001]
    assert "internal_resistance_ohm" in df.columns
    assert any("step time" in warning.lower() for warning in report.warnings)


def test_neware_excel_style_alias_variants(tmp_path):
    raw = tmp_path / "neware_alias_variants.csv"
    raw.write_text(
        "\n".join(
            [
                "Cycle Index,Step Index,Record Index,Relative Time (h:min:s.ms),Voltage(V),Cur (mA),DChg. Capacity(mAh)",
                "1,2,1,0:00:00.0,3.50,-500,0",
                "1,2,2,0:00:05.0,3.45,-600,0.75",
            ]
        ),
        encoding="utf-8",
    )

    df = bds.read(raw, cycler="neware", current_sign="preserve")

    assert df["test_time_s"].to_list() == [0.0, 5.0]
    assert df["current_a"].to_list() == pytest.approx([-0.5, -0.6])
    assert df["discharge_capacity_ah"].to_list() == pytest.approx([0.0, 0.00075])


def test_neware_excel_workbook_prefers_detail_sheet_and_cur_amp_alias(tmp_path):
    raw = tmp_path / "Na1_Q.xlsx"
    pd = pytest.importorskip("pandas")

    with pd.ExcelWriter(raw) as writer:
        pd.DataFrame({"Testing Information": ["Na1_Q.xlsx", "Cycle Mode:Charge First"]}).to_excel(
            writer, sheet_name="Info", index=False
        )
        pd.DataFrame(
            {
                "Channel": [1],
                "ToTal of Cycle": [1],
                "Capacity of charge(Ah)": [0.01],
                "Capacity of discharge(Ah)": [0.008],
            }
        ).to_excel(writer, sheet_name="Cycle_31_2_1", index=False)
        pd.DataFrame(
            {
                "Channel": [1],
                "CyCle": [1],
                "Step": [1],
                "Raw Step ID": [2],
                "Status": ["CCCV_Chg"],
                "Start Voltage(V)": [3.8],
                "End Voltage(V)": [3.9],
                "Start Current(A)": [1.0],
                "End Current(A)": [0.1],
                "CapaCity(Ah)": [0.01],
                "Relative Time(h:min:s.ms)": ["0:00:10.000"],
                "Absolute Time": ["2024-02-29 16:46:38"],
            }
        ).to_excel(writer, sheet_name="Statis_31_2_1", index=False)
        pd.DataFrame(
            {
                "Record Index": [1, 2, 3, 4],
                "Status": ["CCCV_Chg", "CCCV_Chg", "Rest", "CC_DChg"],
                "JumpTo": [1, 1, 1, 1],
                "Cycle": [1, 1, 1, 1],
                "Step": [1, 1, 2, 3],
                "Cur(A)": [1.25, 1.20, 0.0, -0.5],
                "Voltage(V)": [3.8172, 3.8848, 3.9440, 3.8395],
                "CapaCity(Ah)": [0.0, 0.001, 0.0, 0.002],
                "Energy(Wh)": [0.0, 0.0038, 0.0, 0.0077],
                "Relative Time(h:min:s.ms)": [
                    "0:00:00.000",
                    "0:00:01.000",
                    "0:00:00.000",
                    "0:00:00.000",
                ],
                "Absolute Time": [
                    "2024-02-29 16:46:38",
                    "2024-02-29 16:46:39",
                    "2024-02-29 16:46:40",
                    "2024-02-29 16:46:41",
                ],
            }
        ).to_excel(writer, sheet_name="Detail_31_2_1", index=False)

    detected = bds.detect(raw)
    df, report = bds.read_with_report(raw, cycler="auto")

    assert detected.cycler == "neware"
    assert report.cycler == "neware"
    assert report.sheet_name == "Detail_31_2_1"
    assert report.metadata["neware_layout"] == "excel-detail-sheet"
    assert df.height == 4
    assert df["test_time_s"].to_list() == [0.0, 1.0, 2.0, 3.0]
    assert df["current_a"].to_list() == [1.25, 1.2, 0.0, -0.5]
    assert df["charge_capacity_ah"].to_list() == [0.0, 0.001, 0.0, None]
    assert df["discharge_capacity_ah"].to_list() == [0.0, None, 0.0, 0.002]
    assert df["charge_energy_wh"].to_list() == [0.0, 0.0038, 0.0, None]
    assert df["discharge_energy_wh"].to_list() == [0.0, None, 0.0, 0.0077]
    assert validate(df).valid


def test_neware_excel_split_detail_sheets_merge_auxiliary_channels(tmp_path):
    raw = tmp_path / "Na1CCCV_50.xlsx"
    aux_continuation = tmp_path / "Na1CCCV_50__1.xlsx"
    pd = pytest.importorskip("pandas")

    with pd.ExcelWriter(raw) as writer:
        pd.DataFrame({"Testing Information": ["Na1CCCV_50.xlsx"]}).to_excel(
            writer, sheet_name="Info", index=False
        )
        pd.DataFrame(
            {
                "Record Index": [1, 2],
                "Status": ["CCCV_Chg", "CC_DChg"],
                "JumpTo": [1, 1],
                "Cycle": [1, 1],
                "Step": [1, 2],
                "Cur(A)": [1.0, -0.5],
                "Voltage(V)": [3.5, 3.4],
                "CapaCity(Ah)": [0.01, 0.02],
                "Energy(Wh)": [0.035, 0.068],
                "Relative Time(h:min:s.ms)": ["0:00:00.000", "0:00:01.000"],
                "Absolute Time": ["2024-04-03 09:58:36", "2024-04-03 09:58:37"],
            }
        ).to_excel(writer, sheet_name="Detail_31_1_1", index=False)
        pd.DataFrame(
            {
                "Record Index": [3, 4],
                "Status": ["Rest", "CCCV_Chg"],
                "JumpTo": [1, 1],
                "Cycle": [1, 1],
                "Step": [3, 4],
                "Cur(A)": [0.0, 0.8],
                "Voltage(V)": [3.45, 3.6],
                "CapaCity(Ah)": [0.0, 0.03],
                "Energy(Wh)": [0.0, 0.108],
                "Relative Time(h:min:s.ms)": ["0:00:00.000", "0:00:01.000"],
                "Absolute Time": ["2024-04-03 09:58:38", "2024-04-03 09:58:39"],
            }
        ).to_excel(writer, sheet_name="Detail_31_1_1_1", index=False)
        pd.DataFrame(
            {
                "Record ID": [1, 2],
                "Step Name": ["CCCV_Chg", "CC_DChg"],
                "Relative Time(h:min:s.ms)": ["0:00:00.000", "0:00:01.000"],
                "Realtime": ["2024-04-03 09:58:36", "2024-04-03 09:58:37"],
                "Auxiliary channel TU1 U(V)": [0.001, 0.002],
                "Gap of Voltage": [0, 0],
            }
        ).to_excel(writer, sheet_name="DetailVol_31_1_1", index=False)
        pd.DataFrame(
            {
                "Record ID": [3, 4],
                "Step Name": ["Rest", "CCCV_Chg"],
                "Relative Time(h:min:s.ms)": ["0:00:00.000", "0:00:01.000"],
                "Realtime": ["2024-04-03 09:58:38", "2024-04-03 09:58:39"],
                "Auxiliary channel TU1 U(V)": [0.003, 0.004],
                "Gap of Voltage": [0, 0],
            }
        ).to_excel(writer, sheet_name="DetailVol_31_1_1_1", index=False)
        pd.DataFrame(
            {
                "Record ID": [1, 2],
                "Step Name": ["CCCV_Chg", "CC_DChg"],
                "Relative Time(h:min:s.ms)": ["0:00:00.000", "0:00:01.000"],
                "Realtime": ["2024-04-03 09:58:36", "2024-04-03 09:58:37"],
                "Auxiliary channel TU1 T(oC)": [25.0, 25.5],
                "Gap of Temperature": [0, 0],
            }
        ).to_excel(writer, sheet_name="DetailTemp_31_1_1", index=False)

    with pd.ExcelWriter(aux_continuation) as writer:
        pd.DataFrame(
            {
                "Record ID": [3, 4],
                "Step Name": ["Rest", "CCCV_Chg"],
                "Relative Time(h:min:s.ms)": ["0:00:00.000", "0:00:01.000"],
                "Realtime": ["2024-04-03 09:58:38", "2024-04-03 09:58:39"],
                "Auxiliary channel TU1 T(oC)": [26.0, 26.5],
                "Gap of Temperature": [0, 0],
            }
        ).to_excel(writer, sheet_name="DetailTemp_31_1_1_1", index=False)

    df, report = bds.read_with_report(raw, cycler="auto")

    assert bds.detect_kind(raw).kind == "timeseries"
    assert bds.detect_kind(aux_continuation).kind == "unsupported"
    assert report.cycler == "neware"
    assert report.metadata["neware_layout"] == "excel-split-detail-sheets"
    assert report.metadata["selected_sheets"] == ["Detail_31_1_1", "Detail_31_1_1_1"]
    assert report.metadata["record_index_monotonic"] is True
    assert report.metadata["absolute_time_monotonic"] is True
    assert report.metadata["auxiliary_columns"] == [
        "Auxiliary channel TU1 T / degC",
        "Auxiliary channel TU1 U / V",
    ]
    assert str(aux_continuation) in report.metadata["auxiliary_paths"]
    assert df["record_index"].to_list() == [1, 2, 3, 4]
    assert df["test_time_s"].to_list() == [0.0, 1.0, 2.0, 3.0]
    assert df["current_a"].to_list() == [1.0, -0.5, 0.0, 0.8]
    assert df["Auxiliary channel TU1 U / V"].to_list() == [0.001, 0.002, 0.003, 0.004]
    assert df["Auxiliary channel TU1 T / degC"].to_list() == [25.0, 25.5, 26.0, 26.5]
    assert df["temperature_t1_deg_c"].to_list() == [25.0, 25.5, 26.0, 26.5]
    assert validate(df).valid
    out = tmp_path / "detail.bdf.csv"
    bds.convert(raw, out, cycler="auto")
    exported = pl.read_csv(out)
    assert "Auxiliary channel TU1 U (V)" in exported.columns
    assert "Auxiliary channel TU1 T (degC)" in exported.columns
    assert "Surface Temperature T1 (degC)" in exported.columns
    assert all("/" not in column for column in exported.columns)
    assert all("NEWARE" not in column for column in exported.columns)


def test_neware_record_workbook_merges_continuations_and_step_cycle_context(tmp_path):
    raw = tmp_path / "900-1C.xlsx"
    duplicate_csv = tmp_path / "renamed_duplicate.csv"
    continuation = tmp_path / "900-1C_1.xlsx"
    pd = pytest.importorskip("pandas")

    with pd.ExcelWriter(raw) as writer:
        pd.DataFrame([["device", 31, 2, 2]]).to_excel(writer, sheet_name="unit", index=False, header=False)
        pd.DataFrame(
            {
                "Cycle Index": [1],
                "Chg. Cap.(Ah)": [0.864],
                "DChg. Cap.(Ah)": [0.8155],
                "Chg.-DChg. Eff(%)": [94.38],
                "Chg. Time": ["01:08:31"],
                "DChg. Time": ["00:54:55"],
            }
        ).to_excel(writer, sheet_name="cycle", index=False)
        pd.DataFrame(
            {
                "Cycle Index": [1, 1],
                "Step Index": [1, 2],
                "Step Number": [1, 2],
                "Step Type": ["Rest", "CC DChg"],
                "Step Time": ["00:00:01", "00:00:02"],
                "Oneset Date": ["2025-08-06 09:59:23", "2025-08-06 09:59:25"],
                "End Date": ["2025-08-06 09:59:24", "2025-08-06 09:59:27"],
                "Capacity(Ah)": [0.0, 0.8155],
                "Energy(Wh)": [0.0, 2.3105],
            }
        ).to_excel(writer, sheet_name="step", index=False)
        pd.DataFrame(
            {
                "DataPoint": [1, 2],
                "Step Type": ["Rest", "Rest"],
                "Time": ["00:00:00", "00:00:01"],
                "Total Time": ["00:00:00", "00:00:01"],
                "Current(A)": [0.0, 0.0],
                "Voltage(V)": [1.8585, 1.8586],
                "Capacity(Ah)": [0.0, 0.0],
                "Energy(Wh)": [0.0, 0.0],
                "Date": ["2025-08-06 09:59:23", "2025-08-06 09:59:24"],
                "Power(W)": [0.0, 0.0],
            }
        ).to_excel(writer, sheet_name="record", index=False)

    pd.DataFrame(
        {
            "DataPoint": [1, 2],
            "Step Type": ["Rest", "Rest"],
            "Time": ["00:00:00", "00:00:01"],
            "Total Time": ["00:00:00", "00:00:01"],
            "Current(A)": [0.0, 0.0],
            "Voltage(V)": [1.8585, 1.8586],
            "Capacity(Ah)": [0.0, 0.0],
            "Energy(Wh)": [0.0, 0.0],
            "Date": ["2025-08-06 09:59:23", "2025-08-06 09:59:24"],
            "Power(W)": [0.0, 0.0],
        }
    ).to_csv(duplicate_csv, index=False)

    with pd.ExcelWriter(continuation) as writer:
        pd.DataFrame(
            {
                "DataPoint": [3, 4],
                "Step Type": ["CC DChg", "CC DChg"],
                "Time": ["00:00:00", "00:00:01"],
                "Total Time": ["00:00:02", "00:00:03"],
                "Current(A)": [0.5, 0.6],
                "Voltage(V)": [1.75, 1.70],
                "Capacity(Ah)": [0.01, 0.02],
                "Energy(Wh)": [0.0175, 0.034],
                "Date": ["2025-08-06 09:59:25", "2025-08-06 09:59:26"],
                "Power(W)": [0.875, 1.02],
            }
        ).to_excel(writer, sheet_name="record", index=False)

    detected = bds.detect(raw)
    df, report = bds.read_with_report(raw, cycler="auto")

    assert bds.detect_kind(raw).kind == "timeseries"
    assert detected.cycler == "neware"
    assert report.metadata["neware_layout"] == "excel-record-sheet"
    assert str(continuation) in report.metadata["record_continuation_paths"]
    assert report.metadata["step_context_joined"] is True
    assert report.metadata["cycle_context_joined"] is True
    assert df.height == 4
    assert df["test_time_s"].to_list() == [0.0, 1.0, 2.0, 3.0]
    assert df["cycle_index"].to_list() == [1, 1, 1, 1]
    assert df["step_index"].to_list() == [1, 1, 2, 2]
    assert df.columns[:5] == ["test_time_s", "date_time", "unix_time_s", "voltage_v", "current_a"]
    assert df["current_a"].to_list() == [0.0, 0.0, -0.5, -0.6]
    assert df["discharge_capacity_ah"].to_list()[-2:] == [0.01, 0.02]
    assert "step_time_s" in df.columns
    assert "NEWARE Step Type" in df.columns
    assert "NEWARE Cycle Chg. Cap. / Ah" not in df.columns
    assert validate(df).valid

    groups = bds.group_neware_files([duplicate_csv, raw, continuation])
    assert len(groups) == 1
    assert groups[0]["primary_path"] == str(raw)
    assert groups[0]["record_paths"] == [str(raw), str(continuation)]
    assert groups[0]["duplicate_paths"] == [str(duplicate_csv)]
    assert groups[0]["order_checks"][0]["date_order_ok"] is True
    assert groups[0]["order_checks"][0]["point_continuity_ok"] is True

    out_dir = tmp_path / "out"
    reports = bds.convert_neware_groups([duplicate_csv, raw, continuation], out_dir)
    assert len(reports) == 1
    assert reports[0].rows == 4
    assert (out_dir / "900-1C.bds.csv").exists()
    assert (out_dir / "neware-group-manifest.json").exists()
    exported = pl.read_csv(out_dir / "900-1C.bds.csv")
    assert exported.columns[:6] == [
        "Record Index",
        "Date Time",
        "Test Time (s)",
        "Voltage (V)",
        "Current (A)",
        "Cycle Count",
    ]
    assert exported.columns[6] == "Step Index"
    assert exported["Record Index"].to_list() == [1, 2, 3, 4]
    assert exported["Test Time (s)"].to_list() == [0.0, 1.0, 2.0, 3.0]
    assert exported["Step Index"].to_list() == [1, 1, 2, 2]
    assert "unix_time_s" not in exported.columns
    assert "step_index" not in exported.columns
    assert "NEWARE Step Type" not in exported.columns
    assert "Step Type" in exported.columns
    assert reports[0].columns == exported.columns
    assert reports[0].metadata["export_format"] == "battery-data-standard-export-v1"


def test_generic_profile_and_convert_report(tmp_path):
    raw = tmp_path / "raw.csv"
    raw.write_text("t_s,E,I\n0,3.4,0.1\n5,3.5,0.2\n", encoding="utf-8")
    profile = tmp_path / "profile.json"
    profile.write_text(
        json.dumps(
            {
                "columns": {
                    "test_time_s": "t_s",
                    "voltage_v": "E",
                    "current_a": "I",
                }
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out.bdf.csv"
    report_path = tmp_path / "report.json"

    report = bds.convert(raw, out, cycler="generic", profile=profile, report_path=report_path)

    assert out.exists()
    assert report_path.exists()
    assert report.validation.valid
    assert report.rows == 2
    assert report.current_sign == "charge-positive"
    exported = pl.read_csv(out)
    assert exported.columns == ["Record Index", "Test Time (s)", "Voltage (V)", "Current (A)", "Power (W)"]
    assert exported["Record Index"].to_list() == [1, 2]
    assert exported["Test Time (s)"].to_list() == [0.0, 5.0]
    assert report.metadata["internal_columns"] == ["test_time_s", "voltage_v", "current_a", "power_w"]


def test_arbin_adapter_preserves_charge_positive_current_without_status(tmp_path):
    raw = tmp_path / "arbin.csv"
    raw.write_text(
        "Test Time (s),Voltage (V),Current (A)\n0,3.4,1.0\n1,3.5,-2.0\n",
        encoding="utf-8",
    )

    df, report = bds.read_with_report(raw, cycler="arbin")

    assert df["current_a"].to_list() == [1.0, -2.0]
    assert report.metadata["raw_current_sign"] == "charge-positive"


def test_repair_policy_warn_does_not_modify_duplicate_times(tmp_path):
    raw = tmp_path / "generic.csv"
    raw.write_text("Test Time (s),Voltage (V),Current (A)\n5,3.4,0.1\n5,3.5,0.2\n", encoding="utf-8")

    df, report = bds.read_with_report(raw, cycler="generic", strict=False)

    assert df["test_time_s"].to_list() == [5.0, 5.0]
    assert any("Would shift test_time_s" in warning for warning in report.warnings)
    assert any("Would offset duplicate" in warning for warning in report.warnings)
    assert report.metadata["repair_policy"] == "warn"


def test_repair_policy_repair_modifies_duplicate_times(tmp_path):
    raw = tmp_path / "generic.csv"
    raw.write_text("Test Time (s),Voltage (V),Current (A)\n5,3.4,0.1\n5,3.5,0.2\n", encoding="utf-8")

    df = bds.read(raw, cycler="generic", repair_policy="repair")

    assert df["test_time_s"].to_list() == [0.0, 0.000001]


def test_dataset_index_neware_excel_style_time_column(tmp_path):
    raw = tmp_path / "bdc_000197_neware_dst.xlsx"
    pd = pytest.importorskip("pandas")
    pd.DataFrame(
        {
            "Time": [1, 2, 3],
            "Cycle": [0, 0, 0],
            "Voltage/V": [4.1912, 4.1907, 4.1906],
            "Current/A": [-0.097151, -0.098604, -0.098737],
            "SOC": [1.0, 0.999992, 0.999983],
        }
    ).to_excel(raw, sheet_name="0dst", index=False)

    detected = bds.detect(raw)
    df = bds.read(raw, cycler="auto", current_sign="preserve", repair_policy="repair")

    assert detected.cycler == "generic"
    assert df["test_time_s"].to_list() == [0.0, 1.0, 2.0]
    assert df["voltage_v"].to_list()[0] == pytest.approx(4.1912)
    assert df["current_a"].to_list()[1] == pytest.approx(-0.098604)
    assert validate(df).valid


def test_dataset_index_maccor_tab_export_with_preamble(tmp_path):
    raw = tmp_path / "bdc_000154_maccor_form.txt"
    raw.write_text(
        "\n".join(
            [
                "Today's Date:\t11 March 2024\tDate of Test:\t6 September 2023, 09:37:54 PM",
                "Filename:\tA123013_01_FORM_01\tTester Channel:\t4",
                "Procedure:\tA123_FORM_01.000\tDescription:\t3/4/22 A123 Formation Step 1",
                "Rec\tCycle\tStep\tTest Time\tStep Time\tCapacity\tEnergy\tCurrent\tVoltage\tMD\tES\tDPT Time\tACImp/Ohms\tDCIR/Ohms\tAux #1\t Units\tAux #2\t Units",
                "1\t0\t1\t  0d 00:00:0\t  0d 00:00:0\t0\t0\t0.000\t3.266\tR\t0\t09/06/2023 9:37:54 PM\t0.00000\t0.00000\t-0.00071\t  V \t-0.00048\t  V ",
                "2\t0\t1\t  0d 00:00:45\t  0d 00:00:45\t0\t0\t0.000\t3.266\tR\t1\t09/06/2023 9:38:39 PM\t0.00000\t0.00000\t-0.00055\t  V \t-0.00063\t  V ",
                "3\t0\t1\t  0d 00:01:30\t  0d 00:01:30\t0\t0\t0.000\t3.267\tR\t1\t09/06/2023 9:39:24 PM\t0.00000\t0.00000\t-0.00055\t  V \t-0.00079\t  V ",
            ]
        ),
        encoding="utf-8",
    )

    df = bds.read(raw, cycler="auto", current_sign="preserve")

    assert df["test_time_s"].to_list() == [0.0, 45.0, 90.0]
    assert df["cycle_index"].to_list() == [0, 0, 0]
    assert df["step_index"].to_list() == [1, 1, 1]
    assert validate(df).valid


def test_auto_detection_does_not_prefer_neware_without_signatures(tmp_path):
    raw = tmp_path / "headerless_figure_data.txt"
    raw.write_text("2.260690 -0.000172\n2.260967 -0.089925\n", encoding="utf-8")

    detected = bds.detect(raw)

    assert detected.cycler == "generic"


def test_biologic_mpt_header_count_and_units(tmp_path):
    raw = tmp_path / "biologic.mpt"
    raw.write_text(
        "\n".join(
            [
                "EC-Lab ASCII FILE",
                "Nb header lines : 5",
                "Technique : GCPL",
                "Acquisition started on : 05/21/2026 09:00:00.000",
                "mode\ttime/s\tEwe/V\tI/mA\tQ discharge/mA.h\tcycle number\tNs",
                "1\t0\t3.500\t1,5\t0\t1\t1",
                "1\t10\t3.490\t2,0\t1,25\t1\t1",
                "1\t15\t3.480\t-1,0\t1,50\t1\t2",
            ]
        ),
        encoding="utf-8",
    )

    detected = bds.detect(raw)
    df = bds.read(raw, cycler="auto", current_sign="preserve")

    assert detected.cycler == "biologic"
    assert df["test_time_s"].to_list() == [0.0, 10.0, 15.0]
    assert df["step_time_s"].to_list() == [0.0, 10.0, 0.0]
    assert df["date_time"].to_list() == [
        "2026-05-21T09:00:00.000",
        "2026-05-21T09:00:10.000",
        "2026-05-21T09:00:15.000",
    ]
    assert df["current_a"].to_list() == pytest.approx([0.0015, 0.002, -0.001])
    assert df["discharge_capacity_ah"].to_list() == pytest.approx([0.0, 0.00125, 0.0015])
    assert validate(df).valid


def test_maccor_positional_export_without_standard_column_names(tmp_path):
    raw = tmp_path / "maccor_positional.txt"
    raw.write_text(
        "\n".join(
            [
                "cycle_col\tstep_col\ttest_time_col\tstep_time_col\tcap_col\tcurrent_col\tvoltage_col",
                "0\t1\t0d 00:00:00\t0d 00:00:00\t0\t100\t3.200",
                "0\t1\t0d 00:00:05\t0d 00:00:05\t0\t200\t3.210",
            ]
        ),
        encoding="utf-8",
    )

    df = bds.read(raw, cycler="maccor", current_sign="preserve")

    assert df["test_time_s"].to_list() == [0.0, 5.0]
    assert df["cycle_index"].to_list() == [0, 0]
    assert df["step_index"].to_list() == [1, 1]
    assert df["current_a"].to_list() == [0.1, 0.2]
    assert df["voltage_v"].to_list() == [3.2, 3.21]
    assert validate(df).valid


def test_matlab_named_vectors_convert_to_bdf(tmp_path):
    scipy_io = pytest.importorskip("scipy.io")
    raw = tmp_path / "drive_cycle.mat"
    scipy_io.savemat(
        raw,
        {
            "t": [1.0, 1.2, 1.4],
            "volt": [3.4, 3.5, 3.6],
            "current": [-0.1, -0.2, -0.3],
            "soc": [1.0, 0.99, 0.98],
        },
    )

    df = bds.read(raw, cycler="auto", current_sign="preserve", repair_policy="repair")

    assert df["test_time_s"].to_list() == pytest.approx([0.0, 0.2, 0.4])
    assert df["voltage_v"].to_list() == [3.4, 3.5, 3.6]
    assert df["current_a"].to_list() == [-0.1, -0.2, -0.3]
    assert validate(df).valid


def test_matlab_novonix_data_vectors_convert_to_bdf(tmp_path, monkeypatch):
    from battery_data_standard import io as bds_io

    raw = tmp_path / "novonix_like.mat"
    raw.write_bytes(b"matlab fixture stub")
    variables = {
        "CurrentData": [[0.0], [0.0], [0.1]],
        "VoltageData": [[4.19776106], [4.19763517], [4.197824]],
        "TimeData": [[0.0], [1.0003], [2.0001]],
        "StepIndex": [[9], [9], [9]],
        "CycleIndex": [[1], [1], [1]],
        "TempData": [[25.0], [25.1], [25.2]],
    }
    monkeypatch.setattr(bds_io, "_load_matlab_variables", lambda path: variables)

    df = bds.read(raw, cycler="auto", current_sign="preserve")

    assert df["test_time_s"].to_list() == [0.0, 1.0003, 2.0001]
    assert df["voltage_v"].to_list() == [4.19776106, 4.19763517, 4.197824]
    assert df["current_a"].to_list() == [0.0, 0.0, 0.1]
    assert df["cycle_index"].to_list() == [1, 1, 1]
    assert df["step_index"].to_list() == [9, 9, 9]
    assert df["ambient_temperature_deg_c"].to_list() == [25.0, 25.1, 25.2]
    assert validate(df).valid


def test_matlab_dataset_u_i_vectors_convert_to_bdf(tmp_path, monkeypatch):
    from battery_data_standard import io as bds_io

    raw = tmp_path / "dataset_ui.mat"
    raw.write_bytes(b"matlab fixture stub")
    variables = {
        "Dataset_Time": [0.0, 1.0, 2.0],
        "Dataset_U": [3.7, 3.8, 3.9],
        "Dataset_I": [0.0, -1.0, 1.0],
        "Dataset_CycCount": [1, 1, 1],
        "Dataset_tStep": [0.0, 1.0, 2.0],
        "Dataset_T1": [22.0, 22.1, 22.2],
    }
    monkeypatch.setattr(bds_io, "_load_matlab_variables", lambda path: variables)

    df = bds.read(raw, cycler="auto", current_sign="preserve", repair_policy="repair")

    assert df["test_time_s"].to_list() == [0.0, 1.0, 2.0]
    assert df["voltage_v"].to_list() == [3.7, 3.8, 3.9]
    assert df["current_a"].to_list() == [0.0, -1.0, 1.0]
    assert validate(df).valid


def test_matlab_ocv_matrix_heuristic_convert_to_bdf(tmp_path):
    scipy_io = pytest.importorskip("scipy.io")
    raw = tmp_path / "C1202_OCV.mat"
    scipy_io.savemat(
        raw,
        {
            "C1202_OCV": [
                [0, 0, 10.0, 0, 0, 0, 0.1, 4.0],
                [0, 0, 11.0, 0, 0, 0, 0.2, 4.1],
                [0, 0, 12.0, 0, 0, 0, 0.3, 4.2],
            ]
        },
    )

    df = bds.read(raw, cycler="auto", current_sign="preserve", repair_policy="repair")

    assert df["test_time_s"].to_list() == pytest.approx([0.0, 1.0, 2.0])
    assert df["voltage_v"].to_list() == [4.0, 4.1, 4.2]
    assert df["current_a"].to_list() == [0.1, 0.2, 0.3]
    assert validate(df).valid


def test_validate_detects_missing_required_column():
    report = validate(pl.DataFrame({"test_time_s": [0.0, 1.0], "voltage_v": [3.4, 3.5]}))

    assert not report.valid
    assert any(
        issue.code == "missing-required-column" and issue.column == "current_a" for issue in report.issues
    )


def test_validate_rejects_unsupported_schema_version():
    report = validate(
        pl.DataFrame({"test_time_s": [0.0, 1.0], "voltage_v": [3.4, 3.5], "current_a": [0.1, 0.2]}),
        schema_version="bdf-unknown",
    )

    assert report.schema_version == "bdf-unknown"
    assert not report.valid
    assert any(issue.code == "unsupported-schema-version" for issue in report.issues)


def test_validate_rejects_non_finite_voltage_and_current():
    report = validate(
        pl.DataFrame(
            {
                "test_time_s": [0.0, 1.0],
                "voltage_v": [3.4, float("nan")],
                "current_a": [0.1, float("inf")],
            }
        )
    )

    assert not report.valid
    assert any(issue.code == "non-finite-required" and issue.column == "voltage_v" for issue in report.issues)
    assert any(issue.code == "non-finite-required" and issue.column == "current_a" for issue in report.issues)


def test_validate_rejects_non_finite_test_time():
    report = validate(
        pl.DataFrame({"test_time_s": [0.0, float("inf")], "voltage_v": [3.4, 3.5], "current_a": [0.1, 0.2]})
    )

    assert not report.valid
    assert any(
        issue.column == "test_time_s" and issue.code in {"non-finite-required", "non-finite-test-time"}
        for issue in report.issues
    )


def test_validate_non_strict_downgrades_non_increasing_time():
    report = validate(
        pl.DataFrame({"test_time_s": [0.0, 0.0], "voltage_v": [3.4, 3.5], "current_a": [0.1, 0.2]}),
        strict=False,
    )

    assert report.valid
    assert any(
        issue.code == "non-increasing-test-time" and issue.level == "warning" for issue in report.issues
    )


def test_cli_detect_and_validate(tmp_path):
    raw = tmp_path / "neware.csv"
    raw.write_text("DateTime,Voltage(V),Current(mA)\n2026-01-01 00:00:00,3.5,1000\n", encoding="utf-8")

    detect_run = subprocess.run(
        [sys.executable, "-m", "battery_data_standard.cli", "detect", str(raw)],
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(detect_run.stdout)["cycler"] == "neware"

    out = tmp_path / "out.csv"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "battery_data_standard.cli",
            "convert",
            str(raw),
            str(out),
            "--cycler",
            "neware",
            "--no-strict",
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    validate_run = subprocess.run(
        [sys.executable, "-m", "battery_data_standard.cli", "validate", str(out)],
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(validate_run.stdout)["valid"] is True


def test_public_version_and_module_cli():
    assert __version__ == "0.2.1"
    run = subprocess.run(
        [sys.executable, "-m", "battery_data_standard", "--version"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert "0.2.1" in run.stdout


def test_short_import_alias_matches_public_api():
    short_bds = importlib.import_module("bds")

    assert short_bds.__version__ == __version__
    assert short_bds.read is bds.read
    assert short_bds.convert is bds.convert
