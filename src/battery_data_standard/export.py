"""User-facing export column formatting."""

from __future__ import annotations

import math
import re
from itertools import pairwise

import polars as pl

from .reports import ValidationIssue, ValidationReport

EXPORT_FORMAT_VERSION = "battery-data-standard-export-v1"

_VENDOR_PREFIXES = ("NEWARE ", "Arbin ", "Maccor ", "BioLogic ", "Novonix ", "BaSyTec ", "LANDT ")

_DROP_EXPORT_COLUMNS = {
    "Unix Time / s",
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
    "Date Time ISO": "Date Time",
    "Test Time / s": "Test Time (s)",
    "Voltage / V": "Voltage (V)",
    "Current / A": "Current (A)",
    "Cycle Count / 1": "Cycle Count",
    "Step Time / s": "Step Time (s)",
    "Power / W": "Power (W)",
    "Charging Capacity / Ah": "Charging Capacity (Ah)",
    "Discharging Capacity / Ah": "Discharging Capacity (Ah)",
    "Charging Energy / Wh": "Charging Energy (Wh)",
    "Discharging Energy / Wh": "Discharging Energy (Wh)",
}


def to_export_frame(df: pl.DataFrame) -> pl.DataFrame:
    """Format normalized BDF-style data for user-facing file exports."""
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
    # - Step Index / 1 is the source record/data-point index.
    # - Step Count / 1 is the source step index/count.
    if "Step Index / 1" in df.columns:
        add("Step Index / 1", "Record Index")
    else:
        columns.append(pl.Series("Record Index", range(1, df.height + 1), dtype=pl.Int64))
        used_targets.add("Record Index")
    add("Date Time ISO", "Date Time")
    add("Test Time / s", "Test Time (s)")
    add("Voltage / V", "Voltage (V)")
    add("Current / A", "Current (A)")
    add("Cycle Count / 1", "Cycle Count")
    add("Step Count / 1", "Step Index")
    add("Step Time / s", "Step Time (s)")
    add("Power / W", "Power (W)")
    add("Charging Capacity / Ah", "Charging Capacity (Ah)")
    add("Discharging Capacity / Ah", "Discharging Capacity (Ah)")
    add("Charging Energy / Wh", "Charging Energy (Wh)")
    add("Discharging Energy / Wh", "Discharging Energy (Wh)")
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
