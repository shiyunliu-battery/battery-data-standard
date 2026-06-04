"""User-facing export column formatting."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from itertools import pairwise

import polars as pl

from .exceptions import ConversionError
from .reports import ValidationIssue, ValidationReport
from .schema import canonical_label_for

EXPORT_FORMAT_VERSION = "battery-data-standard-export-v1"


@dataclass(frozen=True)
class ExportTarget:
    id: str
    description: str
    recommended_format: str = "csv"
    file_token: str = "bds"


EXPORT_TARGETS: tuple[ExportTarget, ...] = (
    ExportTarget("bds", "Default Battery Data Standard CSV/Parquet export.", "csv", "bds"),
    ExportTarget("bdf", "Legacy BDF-compatible CSV/Parquet export.", "csv", "bdf"),
    ExportTarget("duckdb", "Analysis-ready table for DuckDB SQL workflows.", "parquet", "duckdb"),
    ExportTarget("polars", "Analysis-ready table for Polars workflows.", "parquet", "polars"),
    ExportTarget("cellpy", "cellpy-like staging table with lower-case analysis columns.", "csv", "cellpy"),
    ExportTarget("beep", "BEEP-like staging table with common structuring columns.", "csv", "beep"),
    ExportTarget("pybamm", "PyBaMM drive-cycle staging table with time/current columns.", "csv", "pybamm"),
    ExportTarget(
        "pyprobe", "PyProBE diagnostic staging table with time/current/voltage columns.", "parquet", "pyprobe"
    ),
    ExportTarget(
        "battery-archive",
        "Battery Archive-style package table using the standard normalized export.",
        "parquet",
        "battery-archive",
    ),
)

EXPORT_TARGET_IDS = tuple(target.id for target in EXPORT_TARGETS)

_EXPORT_TARGET_ALIASES = {
    "default": "bds",
    "standard": "bds",
    "battery_data_standard": "bds",
    "battery-data-standard": "bds",
    "battery_archive": "battery-archive",
    "archive": "battery-archive",
    "py-bamm": "pybamm",
    "py-probe": "pyprobe",
}

_STANDARD_TARGETS = {"bds", "duckdb", "polars", "battery-archive"}

_VENDOR_PREFIXES = ("NEWARE ", "Arbin ", "Maccor ", "BioLogic ", "Novonix ", "BaSyTec ", "LANDT ")

_DROP_EXPORT_COLUMNS = {
    "unix_time_s",
}

_PREFERRED_EXPORT_COLUMNS = [
    "Record Index",
    "Date Time",
    "Test Time (s)",
    "Voltage (V)",
    "Current (A)",
    "Cycle Count",
    "Step Index",
    "Step Time (s)",
    "Power (W)",
    "Charging Capacity (Ah)",
    "Discharging Capacity (Ah)",
    "Charging Energy (Wh)",
    "Discharging Energy (Wh)",
    "Step Type",
]

_REQUIRED_EXPORT_COLUMNS = ("Record Index", "Test Time (s)", "Voltage (V)", "Current (A)")

_DIRECT_RENAMES = {
    "date_time": "Date Time",
    "test_time_s": "Test Time (s)",
    "voltage_v": "Voltage (V)",
    "current_a": "Current (A)",
    "cycle_index": "Cycle Count",
    "step_time_s": "Step Time (s)",
    "power_w": "Power (W)",
    "charge_capacity_ah": "Charging Capacity (Ah)",
    "discharge_capacity_ah": "Discharging Capacity (Ah)",
    "charge_energy_wh": "Charging Energy (Wh)",
    "discharge_energy_wh": "Discharging Energy (Wh)",
    "ambient_temperature_deg_c": "Ambient Temperature (degC)",
    "temperature_t1_deg_c": "Surface Temperature T1 (degC)",
    "internal_resistance_ohm": "Internal Resistance (ohm)",
}

_BDF_EXPORT_RENAMES = {
    "date_time": "Date Time ISO",
    "test_time_s": "Test Time / s",
    "voltage_v": "Voltage / V",
    "current_a": "Current / A",
    "unix_time_s": "Unix Time / s",
    "cycle_index": "Cycle Count / 1",
    "step_index": "Step Count / 1",
    "record_index": "Step Index / 1",
    "step_time_s": "Step Time / s",
    "power_w": "Power / W",
    "ambient_temperature_deg_c": "Ambient Temperature / degC",
    "temperature_t1_deg_c": "Surface Temperature T1 / degC",
    "charge_capacity_ah": "Charging Capacity / Ah",
    "discharge_capacity_ah": "Discharging Capacity / Ah",
    "charge_energy_wh": "Charging Energy / Wh",
    "discharge_energy_wh": "Discharging Energy / Wh",
    "internal_resistance_ohm": "Internal Resistance / ohm",
}

_INTEGRATION_EXPORT_RENAMES = {
    "pybamm": {"test_time_s": "time_s", "current_a": "current_a"},
    "pyprobe": {
        "test_time_s": "time_s",
        "voltage_v": "voltage_v",
        "current_a": "current_a",
        "cycle_index": "cycle_index",
        "step_index": "step_index",
        "step_time_s": "step_time_s",
        "charge_capacity_ah": "charge_capacity_ah",
        "discharge_capacity_ah": "discharge_capacity_ah",
    },
    "cellpy": {
        "record_index": "data_point",
        "test_time_s": "test_time",
        "current_a": "current",
        "voltage_v": "voltage",
        "date_time": "datetime",
        "step_time_s": "step_time",
        "cycle_index": "cycle_index",
        "step_index": "step_index",
        "charge_capacity_ah": "charge_capacity",
        "discharge_capacity_ah": "discharge_capacity",
        "charge_energy_wh": "charge_energy",
        "discharge_energy_wh": "discharge_energy",
    },
    "beep": {
        "test_time_s": "test_time",
        "current_a": "current",
        "voltage_v": "voltage",
        "cycle_index": "cycle_index",
        "step_index": "step_index",
        "step_time_s": "step_time",
        "charge_capacity_ah": "charge_capacity",
        "discharge_capacity_ah": "discharge_capacity",
        "charge_energy_wh": "charge_energy",
        "discharge_energy_wh": "discharge_energy",
    },
}


def list_export_targets() -> list[dict[str, str]]:
    """Return available export targets for CLI/API discovery."""
    return [
        {
            "id": target.id,
            "description": target.description,
            "recommended_format": target.recommended_format,
        }
        for target in EXPORT_TARGETS
    ]


def normalize_export_target(target: str | None) -> str:
    """Normalize an export target id or alias."""
    value = (target or "bds").strip().lower().replace("_", "-")
    value = _EXPORT_TARGET_ALIASES.get(value, value)
    if value not in EXPORT_TARGET_IDS:
        raise ConversionError(
            f"Unsupported export target {target!r}. Supported targets: {', '.join(EXPORT_TARGET_IDS)}."
        )
    return value


def output_suffix_for_target(target: str | None) -> str:
    """Return the filename token used for batch outputs for an export target."""
    target_id = normalize_export_target(target)
    for spec in EXPORT_TARGETS:
        if spec.id == target_id:
            return spec.file_token
    return "bds"


def export_label_for_canonical(column: str, *, target: str | None = "bds") -> str | None:
    """Return the user-facing export label for a canonical BDS column."""
    target_id = normalize_export_target(target)
    if target_id == "bdf":
        return _BDF_EXPORT_RENAMES.get(column, column)
    if target_id in _STANDARD_TARGETS:
        if column == "record_index":
            return "Record Index"
        return _DIRECT_RENAMES.get(column, _format_export_column_name(column))
    return _INTEGRATION_EXPORT_RENAMES.get(target_id, {}).get(column)


def to_export_frame(df: pl.DataFrame, *, target: str | None = "bds") -> pl.DataFrame:
    """Format normalized data for a user-facing file export target."""
    target_id = normalize_export_target(target)
    canonical = _canonicalize_input_frame(df)
    if target_id == "bdf":
        return _to_legacy_bdf_export_frame(canonical)
    standard = _to_standard_export_frame(canonical)
    if target_id in _STANDARD_TARGETS:
        return standard
    return _to_integration_frame(standard, target_id)


def _to_standard_export_frame(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty() and not df.columns:
        return df

    columns: list[pl.Series] = []
    used_sources: set[str] = set()
    used_targets: set[str] = set()

    def add(source: str, target: str) -> None:
        if source not in df.columns or target in used_targets:
            return
        columns.append(df[source].alias(target))
        used_sources.add(source)
        used_targets.add(target)

    # Internal semantics:
    # - record_index is the source record/data-point index.
    # - step_index is the source step index/count.
    if "record_index" in df.columns:
        add("record_index", "Record Index")
    else:
        columns.append(pl.Series("Record Index", range(1, df.height + 1), dtype=pl.Int64))
        used_targets.add("Record Index")
    add("date_time", "Date Time")
    add("test_time_s", "Test Time (s)")
    add("voltage_v", "Voltage (V)")
    add("current_a", "Current (A)")
    add("cycle_index", "Cycle Count")
    add("step_index", "Step Index")
    add("step_time_s", "Step Time (s)")
    add("power_w", "Power (W)")
    add("charge_capacity_ah", "Charging Capacity (Ah)")
    add("discharge_capacity_ah", "Discharging Capacity (Ah)")
    add("charge_energy_wh", "Charging Energy (Wh)")
    add("discharge_energy_wh", "Discharging Energy (Wh)")
    add("NEWARE Step Type", "Step Type")

    for source, target in _DIRECT_RENAMES.items():
        add(source, target)

    for source in df.columns:
        if source in used_sources or source in _DROP_EXPORT_COLUMNS:
            continue
        target = _format_export_column_name(source)
        if target in used_targets:
            target = _dedupe_target(target, used_targets)
        columns.append(df[source].alias(target))
        used_targets.add(target)

    output = pl.DataFrame(columns) if columns else df.clear()
    preferred = [column for column in _PREFERRED_EXPORT_COLUMNS if column in output.columns]
    preferred.extend(column for column in output.columns if column not in set(preferred))
    return output.select(preferred)


def _to_legacy_bdf_export_frame(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty() and not df.columns:
        return df
    columns = [
        df[source].alias(target) for source, target in _BDF_EXPORT_RENAMES.items() if source in df.columns
    ]
    used = set(_BDF_EXPORT_RENAMES)
    columns.extend(df[source] for source in df.columns if source not in used)
    output = pl.DataFrame(columns) if columns else df.clear()
    preferred = [target for source, target in _BDF_EXPORT_RENAMES.items() if target in output.columns]
    preferred.extend(column for column in output.columns if column not in set(preferred))
    return output.select(preferred)


def _canonicalize_input_frame(df: pl.DataFrame) -> pl.DataFrame:
    rename: dict[str, str] = {}
    used_targets = set(df.columns)
    for column in df.columns:
        canonical = canonical_label_for(column)
        if canonical is None or canonical == column or canonical in used_targets:
            continue
        rename[column] = canonical
        used_targets.add(canonical)
    return df.rename(rename) if rename else df


def _to_integration_frame(df: pl.DataFrame, target: str) -> pl.DataFrame:
    if target == "pybamm":
        return _select_target_columns(
            df,
            target,
            required=(
                ("Test Time (s)", "time_s"),
                ("Current (A)", "current_a"),
            ),
        )
    if target == "pyprobe":
        return _select_target_columns(
            df,
            target,
            required=(
                ("Test Time (s)", "time_s"),
                ("Voltage (V)", "voltage_v"),
                ("Current (A)", "current_a"),
            ),
            optional=(
                ("Cycle Count", "cycle_index"),
                ("Step Index", "step_index"),
                ("Step Time (s)", "step_time_s"),
                ("Charging Capacity (Ah)", "charge_capacity_ah"),
                ("Discharging Capacity (Ah)", "discharge_capacity_ah"),
            ),
        )
    if target == "cellpy":
        return _select_target_columns(
            df,
            target,
            required=(
                ("Record Index", "data_point"),
                ("Test Time (s)", "test_time"),
                ("Current (A)", "current"),
                ("Voltage (V)", "voltage"),
            ),
            optional=(
                ("Date Time", "datetime"),
                ("Step Time (s)", "step_time"),
                ("Cycle Count", "cycle_index"),
                ("Step Index", "step_index"),
                ("Charging Capacity (Ah)", "charge_capacity"),
                ("Discharging Capacity (Ah)", "discharge_capacity"),
                ("Charging Energy (Wh)", "charge_energy"),
                ("Discharging Energy (Wh)", "discharge_energy"),
            ),
        )
    if target == "beep":
        return _select_target_columns(
            df,
            target,
            required=(
                ("Test Time (s)", "test_time"),
                ("Current (A)", "current"),
                ("Voltage (V)", "voltage"),
            ),
            optional=(
                ("Cycle Count", "cycle_index"),
                ("Step Index", "step_index"),
                ("Step Time (s)", "step_time"),
                ("Charging Capacity (Ah)", "charge_capacity"),
                ("Discharging Capacity (Ah)", "discharge_capacity"),
                ("Charging Energy (Wh)", "charge_energy"),
                ("Discharging Energy (Wh)", "discharge_energy"),
            ),
        )
    raise ConversionError(f"Unsupported export target {target!r}.")


def _select_target_columns(
    df: pl.DataFrame,
    target: str,
    *,
    required: tuple[tuple[str, str], ...],
    optional: tuple[tuple[str, str], ...] = (),
) -> pl.DataFrame:
    missing = [source for source, _target in required if source not in df.columns]
    if missing:
        raise ConversionError(f"Cannot export target {target!r}; missing required columns: {missing}.")
    columns = [pl.col(source).alias(target_name) for source, target_name in required]
    columns.extend(
        pl.col(source).alias(target_name) for source, target_name in optional if source in df.columns
    )
    return df.select(columns)


def looks_like_export_frame(df: pl.DataFrame) -> bool:
    """Return true when a table uses the user-facing export schema."""
    columns = set(df.columns)
    return {"Record Index", "Voltage (V)", "Current (A)"}.issubset(columns)


def validate_export_frame(df: pl.DataFrame, *, strict: bool = True) -> ValidationReport:
    """Validate the user-facing exported table schema."""
    issues: list[ValidationIssue] = []
    columns = list(df.columns)

    if df.is_empty():
        issues.append(ValidationIssue("error", "empty-dataframe", "Dataframe has no rows."))

    for column in _REQUIRED_EXPORT_COLUMNS:
        if column not in columns:
            issues.append(
                ValidationIssue(
                    "error", "missing-required-column", f"Missing required column {column}.", column
                )
            )
            continue
        casted = df[column].cast(pl.Float64, strict=False)
        failed = casted.null_count() - df[column].null_count()
        if failed > 0:
            issues.append(
                ValidationIssue(
                    "error", "non-numeric-required", f"{column} has {failed} non-numeric values.", column
                )
            )
        non_finite = sum(not math.isfinite(float(value)) for value in casted.drop_nulls().to_list())
        if non_finite:
            issues.append(
                ValidationIssue(
                    "error",
                    "non-finite-required",
                    f"{column} contains {non_finite} non-finite values.",
                    column,
                )
            )

    if "Record Index" in columns and not df.is_empty():
        indexes = [float(value) for value in df["Record Index"].cast(pl.Float64, strict=False).drop_nulls()]
        if len(indexes) != df.height:
            issues.append(
                ValidationIssue(
                    "error",
                    "invalid-record-index",
                    "Record Index could not be parsed for every row.",
                    "Record Index",
                )
            )
        elif any(b <= a for a, b in pairwise(indexes)):
            issues.append(
                ValidationIssue(
                    "error" if strict else "warning",
                    "non-increasing-record-index",
                    "Record Index should be strictly increasing.",
                    "Record Index",
                )
            )

    valid = not any(issue.level == "error" for issue in issues)
    return ValidationReport(valid, EXPORT_FORMAT_VERSION, df.height, columns, issues)


def _format_export_column_name(name: str) -> str:
    output = str(name).strip()
    for prefix in _VENDOR_PREFIXES:
        if output.startswith(prefix):
            output = output[len(prefix) :]
            break
    output = _slash_unit_to_parentheses(output)
    output = re.sub(r"\s+", " ", output).strip()
    return output


def _slash_unit_to_parentheses(name: str) -> str:
    match = re.search(r"\s*/\s*([A-Za-z0-9°µμΩOhmohm%.-]+)\s*$", name)
    if not match:
        return name
    unit = match.group(1)
    base = name[: match.start()].rstrip()
    return f"{base} ({unit})"


def _dedupe_target(target: str, used_targets: set[str]) -> str:
    counter = 2
    candidate = f"{target}_{counter}"
    while candidate in used_targets:
        counter += 1
        candidate = f"{target}_{counter}"
    return candidate
