"""BaSyTec cycler adapter."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from ..io import read_table_with_metadata, read_text
from .base import AdapterResult
from .generic import GenericAdapter


class BasytecAdapter(GenericAdapter):
    id = "basytec"
    display_name = "BaSyTec"
    adapter_version = "1"
    support_tier = "fixture-backed"
    raw_current_sign = "charge-positive"
    signatures = ("basytec", "run_time", "c_vol", "c_cur", "~time[h]", "u[v]", "i[a]")
    column_aliases = {
        "Test Time / s": ("run_time", "time", "~Time[h]", "Time[h]", "Time[s]"),
        "Step Time / s": ("t-Step[h]", "t-Set[h]"),
        "Voltage / V": ("c_vol", "voltage", "U[V]", "U_Battery"),
        "Current / A": ("c_cur", "current", "I[A]", "I_Battery"),
        "Cycle Count / 1": ("Cyc-Count", "Cycle", "CycCount"),
        "Step Count / 1": ("Line", "Step", "Command"),
        "Ambient Temperature / degC": (
            "c_temp",
            "c_surf_temp",
            "amb_temp",
            "temperature",
            "T1[°C]",
            "T1[癈]",
        ),
        "Charging Capacity / Ah": ("ah_ch", "Ah[Ah]"),
        "Discharging Capacity / Ah": ("ah_dch",),
    }

    def read_raw_with_metadata(self, path: Path, options: dict[str, Any] | None = None) -> AdapterResult:
        result = read_table_with_metadata(path, options=options)
        metadata = dict(result.metadata)
        data = result.data

        try:
            text, _encoding = read_text(path)
        except OSError:
            text = ""
        start = _parse_basytec_start_time(text)
        if start is not None:
            metadata["basytec_start_of_test"] = start.isoformat()
            data = _add_datetime_column(data, start)

        return AdapterResult(data, metadata=metadata)


def _parse_basytec_start_time(text: str) -> datetime | None:
    for line in text.splitlines()[:80]:
        if "start of test" not in line.lower():
            continue
        _label, _sep, value = line.partition(":")
        value = value.strip()
        for fmt in ("%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def _add_datetime_column(data: pl.DataFrame, start: datetime) -> pl.DataFrame:
    if data.is_empty() or "DateTime" in data.columns:
        return data
    source = next(
        (column for column in ("~Time[h]", "Time[h]", "Time[s]", "run_time") if column in data.columns), None
    )
    if source is None:
        return data
    factor = 3600.0 if "[h]" in source.lower() else 1.0
    offsets = data[source].cast(pl.Float64, strict=False).to_list()
    values = [
        None if value is None else (start + timedelta(seconds=float(value) * factor)).isoformat()
        for value in offsets
    ]
    return data.with_columns(pl.Series("DateTime", values))
