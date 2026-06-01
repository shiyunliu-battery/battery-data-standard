"""Repower CSV adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from .base import AdapterResult
from .generic import GenericAdapter


class RepowerAdapter(GenericAdapter):
    id = "repower"
    display_name = "Repower"
    adapter_version = "1"
    support_tier = "fixture-backed"
    raw_current_sign = "charge-positive"
    extensions = (".csv", ".txt")
    signatures = (
        "Relative Time(Sec)",
        "Relative Time(Hour)",
        "Voltage(V)",
        "Current(A)",
        "Step State",
        "Cycle ID",
    )
    column_aliases = {
        "date_time": ("System Time", "System time"),
        "test_time_s": ("Relative Time(Sec)", "Relative Time(Hour)", "Time [s]", "Relative time [s]"),
        "voltage_v": ("Voltage(V)", "Voltage [V]"),
        "current_a": ("Current(A)", "Current [A]"),
        "cycle_index": ("Cycle ID", "Cycle from cycler"),
        "step_index": ("Step ID", "Step from cycler"),
        "charge_capacity_ah": ("Charge Capacity(Ah)", "Charge capacity [A.h]"),
        "discharge_capacity_ah": ("Discharge Capacity(Ah)", "Discharge capacity [A.h]"),
        "charge_energy_wh": ("Charge Energy(Wh)", "Charge energy [W.h]"),
        "discharge_energy_wh": ("Discharge Energy(Wh)", "Discharge energy [W.h]"),
        "ambient_temperature_deg_c": ("Temperature [degC]", "Temperature(degC)"),
    }

    def read_raw_with_metadata(self, path: Path, options: dict[str, Any] | None = None) -> AdapterResult:
        result = super().read_raw_with_metadata(path, options=options)
        data = _rename_single_repower_temperature(result.data)
        result.data = data
        return result


def _rename_single_repower_temperature(data: pl.DataFrame) -> pl.DataFrame:
    if "Temperature(degC)" in data.columns or "Temperature [degC]" in data.columns:
        return data
    mtv_columns = [column for column in data.columns if str(column).strip().lower().startswith("mtv")]
    if len(mtv_columns) != 1:
        return data
    return data.rename({mtv_columns[0]: "Temperature(degC)"})
