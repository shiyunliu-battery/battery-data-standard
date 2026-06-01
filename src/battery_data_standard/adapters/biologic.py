"""BioLogic EC-Lab adapter."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from ..io import read_table_with_metadata, read_text
from ..reports import ColumnProvenance
from ..schema import ALL_COLUMNS
from .base import AdapterResult
from .generic import GenericAdapter


class BiologicAdapter(GenericAdapter):
    id = "biologic"
    display_name = "BioLogic"
    adapter_version = "1"
    support_tier = "fixture-backed"
    raw_current_sign = "charge-positive"
    extensions = (".mpt", ".mpr", ".txt", ".csv")
    signatures = ("biologic", "ec-lab", "time/s", "ewe/v", "ecell/v", "i/ma", "nb header lines")
    column_aliases = {
        "test_time_s": ("time/s", "time/s.", "Time/s"),
        "step_time_s": ("step time/s", "Step time/s", "step_time/s"),
        "voltage_v": ("Ewe/V", "Ecell/V", "Ewe/V vs.", "<Ewe>/V", "Ecell_V", "Ewe_V"),
        "current_a": ("I/mA", "<I>/mA", "I/A", "<I>/A", "I_mA", "I_A"),
        "cycle_index": ("cycle number", "Ns changes"),
        "step_index": ("Ns",),
        "charge_capacity_ah": ("Q charge/mA.h", "Capacity/mA.h", "(Q-Qo)/mA.h"),
        "discharge_capacity_ah": ("Q discharge/mA.h",),
        "charge_energy_wh": ("Energy charge/W.h", "Energy charge/mW.h"),
        "discharge_energy_wh": ("Energy discharge/W.h", "Energy discharge/mW.h"),
        "power_w": ("P/W",),
        "internal_resistance_ohm": ("R/Ohm", "Rapp/Ohm"),
        "ambient_temperature_deg_c": ("Temperature/°C", "Temperature/degC", "Temperature/Â°C", "T/°C"),
    }

    def read_raw(self, path: Path, options: dict[str, Any] | None = None) -> pl.DataFrame:
        return super().read_raw(path, options=options)

    def read_raw_with_metadata(self, path: Path, options: dict[str, Any] | None = None) -> AdapterResult:
        result = read_table_with_metadata(path, options=options)
        metadata = dict(result.metadata)
        if path.suffix.lower() in {".mpt", ".txt", ".csv"}:
            text, _encoding = read_text(path)
            metadata.update(_parse_biologic_header_metadata(text))
        return AdapterResult(result.data, metadata=metadata)

    def normalize(
        self,
        raw: pl.DataFrame,
        *,
        profile: dict[str, Any] | None = None,
        strict: bool = True,
        keep_raw: bool = False,
        current_sign: str = "charge-positive",
        repair_policy: str = "warn",
    ) -> AdapterResult:
        result = super().normalize(
            raw,
            profile=profile,
            strict=strict,
            keep_raw=keep_raw,
            current_sign=current_sign,
            repair_policy=repair_policy,
        )
        return _replace_step_time_within_step(result)

    def process(
        self,
        path: Path,
        *,
        profile: dict[str, Any] | None = None,
        strict: bool = True,
        keep_raw: bool = False,
        current_sign: str = "charge-positive",
        repair_policy: str = "warn",
        options: dict[str, Any] | None = None,
    ) -> AdapterResult:
        raw_result = self.read_raw_with_metadata(path, options=options)
        raw = raw_result.data
        normalized = self.normalize(
            raw,
            profile=profile,
            strict=strict,
            keep_raw=keep_raw,
            current_sign=current_sign,
            repair_policy=repair_policy,
        )
        repaired = self.repair(normalized.data, repair_policy=repair_policy)
        normalized.data = repaired.data
        _append_datetime_from_acquisition_start(normalized, raw_result.metadata)
        normalized.warnings[:0] = raw_result.warnings
        normalized.warnings.extend(repaired.warnings)
        normalized.metadata.update(raw_result.metadata)
        normalized.metadata.update(self.extract_metadata(raw))
        normalized.metadata.update(repaired.metadata)
        normalized.metadata.update(
            {
                "source_backend": "native",
                "raw_current_sign": self.raw_current_sign,
                "repair_policy": repair_policy,
                "adapter_version": self.adapter_version,
                "support_tier": self.support_tier,
                "output_rows": normalized.data.height,
            }
        )
        return normalized


def _parse_biologic_header_metadata(text: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    header_lines: list[str] = []
    for line in text.splitlines()[:250]:
        if "time/s" in line.lower() and ("ewe/v" in line.lower() or "ecell/v" in line.lower()):
            break
        header_lines.append(line)

    for line in header_lines:
        key, separator, value = line.partition(":")
        if not separator:
            continue
        clean_key = re.sub(r"\s+", " ", key).strip().lower()
        clean_value = value.strip()
        if not clean_value:
            continue
        if clean_key == "acquisition started on":
            started = _parse_biologic_datetime(clean_value)
            if started is not None:
                metadata["biologic_acquisition_started_at"] = started.isoformat(timespec="milliseconds")
                metadata["biologic_acquisition_started_at_raw"] = clean_value
                metadata["biologic_datetime_timezone"] = "unspecified"
        elif clean_key == "technique started on":
            started = _parse_biologic_datetime(clean_value)
            if started is not None:
                metadata["biologic_technique_started_at"] = started.isoformat(timespec="milliseconds")
                metadata["biologic_technique_started_at_raw"] = clean_value
        elif clean_key in {
            "device",
            "ec-lab for windows v11.36 (software)",
            "internet server v11.36 (firmware)",
            "command interpretor v11.36 (firmware)",
            "electrode material",
            "comments",
            "current amplifier",
        }:
            metadata[f"biologic_{clean_key.replace(' ', '_')}"] = clean_value
    return metadata


def _parse_biologic_datetime(value: str) -> datetime | None:
    value = value.strip()
    for fmt in (
        "%m/%d/%Y %H:%M:%S.%f",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y",
        "%d/%m/%Y %H:%M:%S.%f",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _replace_step_time_within_step(result: AdapterResult) -> AdapterResult:
    df = result.data
    if df.is_empty() or "test_time_s" not in df.columns or "step_index" not in df.columns:
        return result

    test_times = df["test_time_s"].cast(pl.Float64, strict=False).to_list()
    step_counts = df["step_index"].to_list()
    step_times: list[float | None] = []
    current_step: Any = object()
    step_start: float | None = None

    for test_time, step_count in zip(test_times, step_counts, strict=True):
        if test_time is None:
            step_times.append(None)
            continue
        value = float(test_time)
        if step_start is None or step_count != current_step or value < step_start:
            current_step = step_count
            step_start = value
        step_times.append(value - step_start)

    df = df.with_columns(pl.Series("step_time_s", step_times, dtype=pl.Float64))
    result.data = _select_existing_bds_order(df)
    result.provenance = [item for item in result.provenance if item.column != "step_time_s"]
    result.provenance.append(
        ColumnProvenance(
            "step_time_s",
            "time/s|Ns",
            source_unit="s",
            transform="derived elapsed seconds within consecutive BioLogic Ns step",
        )
    )
    mapped = set(result.metadata.get("mapped_columns", []))
    mapped.update({"time/s", "Ns"})
    result.metadata["mapped_columns"] = sorted(mapped)
    result.metadata["biologic_step_time_source"] = "derived_from_test_time_and_Ns"
    return result


def _append_datetime_from_acquisition_start(result: AdapterResult, metadata: dict[str, Any]) -> None:
    if "date_time" in result.data.columns or "test_time_s" not in result.data.columns:
        return
    start_value = metadata.get("biologic_acquisition_started_at")
    if not start_value:
        return
    try:
        start = datetime.fromisoformat(str(start_value))
    except ValueError:
        return

    offsets = result.data["test_time_s"].cast(pl.Float64, strict=False).to_list()
    values = [
        None
        if offset is None
        else (start + timedelta(milliseconds=round(float(offset) * 1000))).isoformat(timespec="milliseconds")
        for offset in offsets
    ]
    result.data = _select_existing_bds_order(result.data.with_columns(pl.Series("date_time", values)))
    result.provenance.append(
        ColumnProvenance(
            "date_time",
            "Acquisition started on|test_time_s",
            transform="derived local timestamp from BioLogic header start time plus elapsed seconds",
        )
    )
    result.metadata["biologic_datetime_derived"] = True


def _select_existing_bds_order(df: pl.DataFrame) -> pl.DataFrame:
    ordered = [column for column in ALL_COLUMNS if column in df.columns]
    ordered.extend(column for column in df.columns if column not in set(ordered))
    return df.select(ordered)
