"""EIS table normalization helpers."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import polars as pl

from .exceptions import ConversionError
from .io import read_table_with_metadata, write_dataframe
from .reports import ValidationIssue, ValidationReport

EIS_SCHEMA_VERSION = "eis-2026-05"
EIS_REQUIRED_COLUMNS = ("Frequency_Hz", "Zre_exp_Ohm", "Zim_exp_Ohm")


def read_eis(path: str | Path, *, sheet: str | int | None = None) -> pl.DataFrame:
    """Read CSV/Excel-like EIS data into an eisfit-compatible table."""
    input_path = Path(path)
    result = read_table_with_metadata(input_path, options={"sheet": sheet})
    raw = _add_frequency_values_from_sibling(input_path, result.data)
    return normalize_eis_frame(raw)


def convert_eis(
    input_path: str | Path,
    output_path: str | Path,
    *,
    format: str = "csv",
    sheet: str | int | None = None,
) -> ValidationReport:
    """Convert an EIS file into the package EIS standard table."""
    df = read_eis(input_path, sheet=sheet)
    report = validate_eis(df)
    if not report.valid:
        raise ConversionError(
            "EIS validation failed: "
            + "; ".join(issue.message for issue in report.issues if issue.level == "error")
        )
    write_dataframe(df, output_path, fmt=format)
    return report


def validate_eis(df: pl.DataFrame, *, schema_version: str = EIS_SCHEMA_VERSION) -> ValidationReport:
    issues: list[ValidationIssue] = []
    for column in EIS_REQUIRED_COLUMNS:
        if column not in df.columns:
            issues.append(
                ValidationIssue(
                    "error",
                    "missing-required-eis-column",
                    f"Missing required EIS column {column}.",
                    column,
                )
            )

    for column in EIS_REQUIRED_COLUMNS:
        if column not in df.columns:
            continue
        values = df[column].cast(pl.Float64, strict=False).to_list()
        invalid = sum(value is None or not math.isfinite(float(value)) for value in values)
        if invalid:
            issues.append(
                ValidationIssue(
                    "error",
                    "invalid-eis-numeric-values",
                    f"{column} has {invalid} null or non-finite values.",
                    column,
                )
            )

    if "Frequency_Hz" in df.columns:
        values = df["Frequency_Hz"].cast(pl.Float64, strict=False).to_list()
        non_positive = sum(
            value is not None and math.isfinite(float(value)) and float(value) <= 0 for value in values
        )
        if non_positive:
            issues.append(
                ValidationIssue(
                    "error",
                    "non-positive-eis-frequency",
                    f"Frequency_Hz has {non_positive} non-positive values.",
                    "Frequency_Hz",
                )
            )

    return ValidationReport(
        valid=not any(issue.level == "error" for issue in issues),
        schema_version=schema_version,
        rows=df.height,
        columns=list(df.columns),
        issues=issues,
    )


def normalize_eis_frame(raw: pl.DataFrame) -> pl.DataFrame:
    raw = _clean_columns(raw)
    raw = _expand_complex_impedance_column(raw)
    freq_col = _find_column(
        raw.columns,
        (
            "Frequency_Hz",
            "Frequency (Hz)",
            "Frequency(Hz)",
            "Frequency/Hz",
            "Frequency_Hz",
            "Frequency",
            "Data: Frequency",
            "Fit: Frequency",
            "freq/Hz",
            "freq",
            "Freq",
        ),
    )
    zre_col = _find_column(
        raw.columns,
        (
            "Zre_exp_Ohm",
            "Zreal_Ohm",
            "Zreal",
            "Zre",
            "Z'",
            "Data: Z'",
            "Fit: Z'",
            "Re(Z)/Ohm",
            "Re(Z)",
            "impedance_R/Ohm",
            "impedance_R",
            "R(ohm)",
            "Z1 /Ohm",
            "Z1",
            "Real_Ohm",
        ),
    )
    zim_col = _find_column(
        raw.columns,
        (
            "Zim_exp_Ohm",
            "Zimag_Ohm",
            "Zimag",
            "Zim",
            "Z''",
            "Data: Z''",
            "Fit: Z''",
            "Im(Z)/Ohm",
            "Im(Z)",
            "-Im(Z)/Ohm",
            "-Im(Z)",
            "impedance_I/Ohm",
            "impedance_I",
            "X(ohm)",
            "Z2 /Ohm",
            "Z2",
            "Imag_Ohm",
        ),
    )
    if freq_col is None or zre_col is None or zim_col is None:
        raise ConversionError(
            "Could not infer EIS frequency, real impedance, and imaginary impedance columns. "
            f"Raw columns: {raw.columns}"
        )

    freq = _float_values(raw[freq_col])
    zre = _float_values(raw[zre_col])
    zim = _float_values(raw[zim_col])
    if _is_negative_imaginary_column(zim_col):
        zim = [None if value is None else -value for value in zim]

    rows: list[dict[str, Any]] = []
    context_columns = [col for col in raw.columns if col not in {freq_col, zre_col, zim_col}]
    for index, (f_value, zr_value, zi_value) in enumerate(zip(freq, zre, zim, strict=True)):
        if (
            f_value is None
            or zr_value is None
            or zi_value is None
            or not math.isfinite(f_value)
            or not math.isfinite(zr_value)
            or not math.isfinite(zi_value)
            or f_value <= 0
        ):
            continue
        row: dict[str, Any] = {
            "Frequency_Hz": f_value,
            "Zre_exp_Ohm": zr_value,
            "Zim_exp_Ohm": zi_value,
            "-Zim_exp_Ohm": -zi_value,
            "Phase_exp_deg": math.degrees(math.atan2(zi_value, zr_value)),
        }
        for column in context_columns:
            if _looks_like_context(column):
                row[column] = raw[column][index]
        rows.append(row)

    if not rows:
        raise ConversionError("No valid EIS rows found after normalization.")
    df = pl.DataFrame(rows)
    return df.sort("Frequency_Hz", descending=True)


def looks_like_eis_columns(columns: list[str]) -> bool:
    slugs = {_slug(column) for column in columns}
    has_freq = any("freq" in slug or "frequency" in slug for slug in slugs)
    has_real = any(
        token in slug
        for slug in slugs
        for token in ("zre", "zreal", "rez", "realohm", "impedancer", "roh", "rohm")
    ) or any("z'" in str(column).lower() and "z''" not in str(column).lower() for column in columns)
    has_imag = any(
        token in slug for slug in slugs for token in ("zim", "zimag", "imz", "imagohm", "impedancei", "xohm")
    ) or any("z''" in str(column).lower() for column in columns)
    return has_freq and has_real and has_imag


def _add_frequency_values_from_sibling(path: Path, raw: pl.DataFrame) -> pl.DataFrame:
    if "Frequency_Hz" in raw.columns or "FREQUENCY_VALUE" in raw.columns:
        return raw
    if "FREQUENCY_ID" not in raw.columns or "IMPEDANCE_VALUE" not in raw.columns:
        return raw
    frequency_path = path.parent / "frequencies.csv"
    if not frequency_path.exists():
        return raw
    frequencies = read_table_with_metadata(frequency_path).data
    if "FREQUENCY_ID" not in frequencies.columns or "FREQUENCY_VALUE" not in frequencies.columns:
        return raw
    mapping = {
        str(key): _parse_float(value)
        for key, value in zip(
            frequencies["FREQUENCY_ID"].to_list(),
            frequencies["FREQUENCY_VALUE"].to_list(),
            strict=False,
        )
    }
    values = [mapping.get(str(value)) for value in raw["FREQUENCY_ID"].to_list()]
    return raw.with_columns(pl.Series("Frequency_Hz", values, dtype=pl.Float64))


def _expand_complex_impedance_column(raw: pl.DataFrame) -> pl.DataFrame:
    if "IMPEDANCE_VALUE" not in raw.columns:
        return raw
    parsed = [_parse_complex(value) for value in raw["IMPEDANCE_VALUE"].to_list()]
    if not any(value is not None for value in parsed):
        return raw
    zre = [None if value is None else value.real for value in parsed]
    zim = [None if value is None else value.imag for value in parsed]
    return raw.with_columns(
        pl.Series("Zre_exp_Ohm", zre, dtype=pl.Float64),
        pl.Series("Zim_exp_Ohm", zim, dtype=pl.Float64),
    )


def _clean_columns(df: pl.DataFrame) -> pl.DataFrame:
    rename = {col: str(col).strip().replace("\t", "") for col in df.columns}
    rename = {old: new for old, new in rename.items() if old != new}
    return df.rename(rename) if rename else df


def _find_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    exact = {str(column).strip().lower(): column for column in columns}
    for candidate in candidates:
        key = candidate.strip().lower()
        if key in exact:
            return exact[key]
    slugs = {_slug(column): column for column in columns}
    for candidate in candidates:
        key = _slug(candidate)
        if key in slugs:
            return slugs[key]
    return None


def _float_values(series: pl.Series) -> list[float | None]:
    values: list[float | None] = []
    for value in series.to_list():
        values.append(_parse_float(value))
    return values


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _parse_complex(value: Any) -> complex | None:
    if value is None:
        return None
    text = str(value).strip().strip("()").replace("i", "j")
    try:
        number = complex(text)
    except ValueError:
        return None
    if not math.isfinite(number.real) or not math.isfinite(number.imag):
        return None
    return number


def _is_negative_imaginary_column(column: str) -> bool:
    text = column.strip().lower()
    return text.startswith("-") or "-im" in text or "minus" in text


def _looks_like_context(column: str) -> bool:
    slug = _slug(column)
    return any(
        token in slug
        for token in (
            "soc",
            "temperature",
            "temp",
            "voltage",
            "current",
            "time",
            "cycle",
            "cell",
            "battery",
            "measure",
        )
    )


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())
