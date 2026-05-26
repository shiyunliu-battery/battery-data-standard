"""Shared normalization logic used by native adapters."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC
from itertools import pairwise
from typing import Any

import pandas as pd
import polars as pl

from ..exceptions import ConversionError
from ..profiles import profile_column_map
from ..reports import ColumnProvenance
from ..schema import ALL_COLUMNS, CANONICAL_COLUMNS, LABEL_TO_SPEC, REQUIRED_COLUMNS, aliases_for

VALID_CURRENT_SIGN = {"preserve", "discharge-positive", "charge-positive"}
VALID_REPAIR_POLICY = {"none", "warn", "repair"}


@dataclass
class NormalizationState:
    warnings: list[str]
    provenance: list[ColumnProvenance]
    used_columns: set[str]


def normalize_raw_frame(
    raw: pl.DataFrame,
    *,
    adapter_id: str,
    aliases: dict[str, tuple[str, ...]] | None = None,
    profile: dict[str, Any] | None = None,
    strict: bool = True,
    keep_raw: bool = False,
    current_sign: str = "charge-positive",
    raw_current_sign: str = "unknown",
):
    from .base import AdapterResult

    if current_sign not in VALID_CURRENT_SIGN:
        raise ConversionError(
            f"current_sign must be one of {sorted(VALID_CURRENT_SIGN)}, got {current_sign!r}"
        )

    raw = _clean_raw_columns(raw)
    aliases = aliases or {}
    profile_map = profile_column_map(profile or {})
    state = NormalizationState(warnings=[], provenance=[], used_columns=set())
    output: dict[str, pl.Series] = {}

    for spec in CANONICAL_COLUMNS:
        label = spec.label
        candidates = tuple(profile_map.get(label, ())) + tuple(aliases.get(label, ())) + aliases_for(label)
        source = _find_column(raw.columns, candidates)
        if source is None:
            continue
        series, source_unit, transform = _convert_column(raw[source], source, label)
        output[label] = series.alias(label)
        state.used_columns.add(source)
        state.provenance.append(ColumnProvenance(label, source, source_unit=source_unit, transform=transform))

    _derive_datetime_columns(output, raw, state)
    _derive_test_time(output, state)
    _derive_power(output, state)
    _apply_current_sign(output, raw, state, current_sign, raw_current_sign)

    if keep_raw:
        for col in raw.columns:
            if col in state.used_columns:
                continue
            raw_name = f"raw:{col}"
            if raw_name not in output:
                output[raw_name] = raw[col].alias(raw_name)

    if strict:
        missing = [col for col in REQUIRED_COLUMNS if col not in output]
        if missing:
            raise ConversionError(
                f"Missing required BDF columns after {adapter_id} normalization: {missing}. "
                f"Raw columns: {raw.columns}"
            )

    ordered = [label for label in ALL_COLUMNS if label in output]
    ordered.extend(col for col in output if col not in ordered)
    df = pl.DataFrame([output[col] for col in ordered]) if output else pl.DataFrame()
    unmapped = [col for col in raw.columns if col not in state.used_columns]
    return AdapterResult(
        df,
        warnings=state.warnings,
        provenance=state.provenance,
        metadata={
            "mapped_columns": sorted(state.used_columns),
            "unmapped_columns": unmapped,
        },
    )


def repair_bdf_frame(df: pl.DataFrame, *, policy: str = "warn") -> tuple[pl.DataFrame, list[str]]:
    warnings: list[str] = []
    if policy not in VALID_REPAIR_POLICY:
        raise ConversionError(f"repair_policy must be one of {sorted(VALID_REPAIR_POLICY)}, got {policy!r}")
    if df.is_empty() or "Test Time / s" not in df.columns:
        return df, warnings

    if policy == "none":
        return df, []
    if policy == "warn":
        return df, _repair_operations(df)

    before = df.height
    required_present = [c for c in REQUIRED_COLUMNS if c in df.columns]
    if required_present:
        mask = pl.any_horizontal([pl.col(c).is_null() for c in required_present])
        df = df.filter(~mask)
        dropped = before - df.height
        if dropped:
            warnings.append(f"Dropped {dropped} rows with null required values.")

    if df.is_empty():
        return df, warnings

    times = df["Test Time / s"].cast(pl.Float64, strict=False).to_list()
    if any(t is not None and not math.isfinite(float(t)) for t in times):
        warnings.append("Non-finite test times were set to null before repair.")
        df = df.with_columns(
            pl.when(pl.col("Test Time / s").is_finite())
            .then(pl.col("Test Time / s"))
            .otherwise(None)
            .alias("Test Time / s")
        ).drop_nulls("Test Time / s")

    times = [float(t) for t in df["Test Time / s"].to_list()]
    if times != sorted(times):
        df = df.sort("Test Time / s")
        warnings.append("Rows were sorted by Test Time / s.")

    times = [float(t) for t in df["Test Time / s"].to_list()]
    if not times:
        return df, warnings
    min_time = min(times)
    if abs(min_time) > 1e-12:
        df = df.with_columns((pl.col("Test Time / s") - min_time).alias("Test Time / s"))
        warnings.append("Test Time / s was shifted to start at 0.")
        times = [float(t) for t in df["Test Time / s"].to_list()]

    adjusted = []
    previous = -math.inf
    changed = False
    for value in times:
        new_value = value
        if new_value <= previous:
            new_value = previous + 1e-6
            changed = True
        adjusted.append(new_value)
        previous = new_value
    if changed:
        df = df.with_columns(pl.Series("Test Time / s", adjusted))
        warnings.append("Duplicate or non-increasing test times were offset by 1e-6 s.")
    return df, warnings


def _clean_raw_columns(raw: pl.DataFrame) -> pl.DataFrame:
    rename: dict[str, str] = {}
    seen: dict[str, int] = {}
    for col in raw.columns:
        clean = re.sub(r"[\t\"]+", "", str(col)).strip()
        clean = _normalize_header_unit_separator(clean)
        count = seen.get(clean, 0)
        seen[clean] = count + 1
        if count:
            clean = f"{clean}_{count + 1}"
        if clean != col:
            rename[col] = clean
    return raw.rename(rename) if rename else raw


def _normalize_header_unit_separator(header: str) -> str:
    match = re.match(
        r"^(.+?),\s*(s|sec|second|seconds|ms|h|hr|hour|hours|A|mA|V|mV|W|mW|Wh|mWh|Ah|mAh|As|C|degC|Ohm|Ohms|mOhm)$",
        header,
        flags=re.IGNORECASE,
    )
    if not match:
        return header
    base, unit = match.groups()
    if not re.search(r"[A-Za-z]", base):
        return header
    return f"{base.strip()}({unit.strip()})"


def _find_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    exact = {str(c).strip().lower(): c for c in columns}
    for candidate in candidates:
        key = str(candidate).strip().lower()
        if key in exact:
            return exact[key]

    slugs = {_slug(c): c for c in columns}
    for candidate in candidates:
        key = _slug(candidate)
        if key in slugs:
            return slugs[key]
    return None


def _convert_column(series: pl.Series, source: str, label: str) -> tuple[pl.Series, str | None, str | None]:
    unit = _source_unit(source)
    target_unit = LABEL_TO_SPEC[label].unit
    if label == "Unix Time / s":
        numeric = _float_series(series)
        values = numeric.to_list()
        if any(v is not None for v in values):
            return numeric, unit, "numeric"
        parsed = _parse_unix_time(series.to_list())
        return pl.Series(series.name, parsed, dtype=pl.Float64), unit, "parsed UTC timestamp"
    if label in {"Date Time ISO"}:
        return _string_series(series), unit, "string"
    if target_unit == "1":
        return _int_series(series), unit, "integer"
    if target_unit in {"s", "A", "V", "degC", "Ah", "Wh", "W", "ohm"}:
        if label == "Test Time / s" or label == "Step Time / s":
            numeric = _duration_series(series)
        else:
            numeric = _float_series(series)
        factor = _unit_factor(unit, target_unit)
        if factor != 1.0:
            numeric = (numeric * factor).alias(series.name)
            return numeric, unit, f"unit conversion x{factor:g}"
        return numeric, unit, "numeric"
    return series, unit, None


def _derive_datetime_columns(
    output: dict[str, pl.Series],
    raw: pl.DataFrame,
    state: NormalizationState,
) -> None:
    if "Unix Time / s" in output:
        return
    source = None
    if "Date Time ISO" in output:
        values = output["Date Time ISO"].to_list()
        source = "Date Time ISO"
    else:
        candidates = ("DateTime", "Datetime", "Date Time", "Realtime", "Absolute Time")
        raw_source = _find_column(raw.columns, candidates)
        if raw_source is None:
            return
        values = raw[raw_source].to_list()
        source = raw_source

    unix_values = _parse_unix_time(values)
    if not any(v is not None for v in unix_values):
        state.warnings.append(f"Could not parse timestamps from {source}.")
        return
    output["Unix Time / s"] = pl.Series("Unix Time / s", unix_values, dtype=pl.Float64)
    state.provenance.append(
        ColumnProvenance("Unix Time / s", source, source_unit=None, transform="parsed UTC timestamp")
    )


def _derive_test_time(output: dict[str, pl.Series], state: NormalizationState) -> None:
    if "Test Time / s" in output:
        return
    if "Unix Time / s" in output:
        values = list(output["Unix Time / s"].to_list())
        valid = [float(v) for v in values if v is not None and math.isfinite(float(v))]
        if valid:
            start = min(valid)
            derived = [None if v is None else float(v) - start for v in values]
            output["Test Time / s"] = pl.Series("Test Time / s", derived, dtype=pl.Float64)
            state.provenance.append(
                ColumnProvenance(
                    "Test Time / s",
                    "Unix Time / s",
                    source_unit="s",
                    transform="derived elapsed seconds from timestamp",
                )
            )
            return
    if "Step Time / s" in output:
        step = [None if v is None else float(v) for v in output["Step Time / s"].to_list()]
        output["Test Time / s"] = pl.Series("Test Time / s", _elapsed_from_step_time(step), dtype=pl.Float64)
        state.warnings.append(
            "No whole-test time or timestamp was found; reconstructed Test Time / s from step time."
        )
        state.provenance.append(
            ColumnProvenance(
                "Test Time / s",
                "Step Time / s",
                source_unit="s",
                transform="cumulative non-negative step-time increments",
            )
        )


def _derive_power(output: dict[str, pl.Series], state: NormalizationState) -> None:
    if "Power / W" in output:
        return
    if "Voltage / V" in output and "Current / A" in output:
        power = output["Voltage / V"] * output["Current / A"]
        output["Power / W"] = power.alias("Power / W")
        state.provenance.append(ColumnProvenance("Power / W", "Voltage / V|Current / A", transform="V * I"))


def _apply_current_sign(
    output: dict[str, pl.Series],
    raw: pl.DataFrame,
    state: NormalizationState,
    current_sign: str,
    raw_current_sign: str,
) -> None:
    if current_sign == "preserve" or "Current / A" not in output:
        return

    status_source = _find_column(
        raw.columns, ("Status", "State", "Step Type", "Type", "Mode", "MD", "Command", "Test step")
    )
    if status_source is None:
        if _apply_raw_current_sign(output, state, current_sign, raw_current_sign):
            return
        state.warnings.append(
            f"Current sign set to {current_sign}, but no charge/discharge status column "
            "or adapter sign convention was found; values were preserved."
        )
        return

    current = [None if v is None else float(v) for v in output["Current / A"].to_list()]
    statuses = [_classify_status(v) for v in raw[status_source].to_list()]
    if not any(status in {"charge", "discharge"} for status in statuses):
        if any(status == "rest" for status in statuses):
            state.provenance.append(
                ColumnProvenance(
                    "Current / A",
                    status_source,
                    transform=f"current sign preserved for rest-only rows under {current_sign}",
                )
            )
            return
        if _apply_raw_current_sign(output, state, current_sign, raw_current_sign):
            state.warnings.append(
                f"Status column {status_source} had no recognizable charge/discharge labels; "
                "used adapter current sign convention."
            )
            return
        state.warnings.append(
            f"Status column {status_source} had no recognizable charge/discharge labels; "
            "current sign was preserved."
        )
        return

    signed: list[float | None] = []
    for value, status in zip(current, statuses, strict=True):
        if value is None:
            signed.append(None)
        elif status == "charge":
            signed.append(-abs(value) if current_sign == "discharge-positive" else abs(value))
        elif status == "discharge":
            signed.append(abs(value) if current_sign == "discharge-positive" else -abs(value))
        elif status == "rest":
            signed.append(value)
        elif (
            raw_current_sign in {"charge-positive", "discharge-positive"} and raw_current_sign != current_sign
        ):
            signed.append(-value)
        else:
            signed.append(value)
    output["Current / A"] = pl.Series("Current / A", signed, dtype=pl.Float64)
    state.provenance.append(
        ColumnProvenance("Current / A", status_source, transform=f"current sign normalized to {current_sign}")
    )
    unknown_count = sum(status is None for status in statuses)
    if unknown_count:
        fallback = (
            "adapter convention"
            if raw_current_sign in {"charge-positive", "discharge-positive"}
            else "raw values"
        )
        state.warnings.append(
            f"Status column {status_source} had {unknown_count} unrecognized rows; used {fallback} for those rows."
        )


def _apply_raw_current_sign(
    output: dict[str, pl.Series],
    state: NormalizationState,
    current_sign: str,
    raw_current_sign: str,
) -> bool:
    if raw_current_sign not in {"charge-positive", "discharge-positive"}:
        return False
    if raw_current_sign != current_sign:
        output["Current / A"] = (-output["Current / A"]).alias("Current / A")
        state.provenance.append(
            ColumnProvenance(
                "Current / A",
                "adapter raw_current_sign",
                transform=f"flipped from {raw_current_sign} to {current_sign}",
            )
        )
    return True


def _parse_unix_time(values: list[Any]) -> list[float | None]:
    cleaned: list[Any] = []
    for value in values:
        if value is None:
            cleaned.append(value)
            continue
        text = str(value).strip()
        if re.match(r"^\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}\s+\d{1,2}:\d{2}:\d{2}(?:\.\d+)?s$", text):
            text = text[:-1]
        cleaned.append(text)
    parsed = pd.to_datetime(
        pd.Series(cleaned, dtype="object"),
        errors="coerce",
        utc=True,
        format="mixed",
    )
    unix: list[float | None] = []
    for value in parsed:
        if pd.isna(value):
            unix.append(None)
        else:
            unix.append(value.to_pydatetime().replace(tzinfo=UTC).timestamp())

    finite = [v for v in unix if v is not None]
    if finite:
        feb_1970 = 2678400.0
        has_later = any(v > feb_1970 for v in finite)
        if has_later:
            unix = [None if v is not None and 0 <= v < feb_1970 else v for v in unix]
    return unix


def _elapsed_from_step_time(values: list[float | None]) -> list[float | None]:
    elapsed: list[float | None] = []
    total = 0.0
    previous: float | None = None
    for value in values:
        if value is None:
            elapsed.append(None)
            continue
        if previous is None:
            increment = max(value, 0.0)
        else:
            increment = value - previous
            if increment < 0:
                increment = max(value, 0.0)
        total += max(increment, 0.0)
        elapsed.append(total)
        previous = value
    if elapsed and elapsed[0] is not None:
        first = elapsed[0]
        elapsed = [None if v is None else v - first for v in elapsed]
    return elapsed


def _string_series(series: pl.Series) -> pl.Series:
    return pl.Series(
        series.name, [None if v is None else str(v).strip().strip('"') for v in series.to_list()]
    )


def _int_series(series: pl.Series) -> pl.Series:
    return pl.Series(
        series.name, [None if (v := _parse_number(x)) is None else int(v) for x in series.to_list()]
    )


def _float_series(series: pl.Series) -> pl.Series:
    return pl.Series(series.name, [_parse_number(x) for x in series.to_list()], dtype=pl.Float64)


def _duration_series(series: pl.Series) -> pl.Series:
    return pl.Series(series.name, [_parse_duration(x) for x in series.to_list()], dtype=pl.Float64)


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).strip().strip('"').replace("\t", "")
    if text in {"", "-", "--", "nan", "NaN", "None"}:
        return None
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif re.search(r"\d,\d", text):
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _parse_duration(value: Any) -> float | None:
    numeric = _parse_number(value)
    if numeric is not None:
        return numeric
    if value is None:
        return None
    text = str(value).strip().strip('"')
    match = re.match(r"^\s*(\d+)d\s+(\d+):(\d+):(\d+(?:\.\d+)?)\s*$", text)
    if match:
        days, hours, minutes = map(int, match.groups()[:3])
        seconds = float(match.group(4))
        return days * 86400 + hours * 3600 + minutes * 60 + seconds
    if ":" in text:
        parts = text.split(":")
        try:
            nums = [float(part) for part in parts]
        except ValueError:
            return None
        if len(nums) == 3:
            hours, minutes, seconds = nums
            return hours * 3600 + minutes * 60 + seconds
        if len(nums) == 4:
            days, hours, minutes, seconds = nums
            return days * 86400 + hours * 3600 + minutes * 60 + seconds
    return None


def _source_unit(source: str) -> str | None:
    text = source.strip()
    slug = _slug(text)
    if "millisecond" in slug or slug.endswith("milliseconds") or slug.endswith("msec"):
        return "ms"
    if slug.endswith("second") or slug.endswith("seconds"):
        return "s"
    if slug.endswith("hour") or slug.endswith("hours"):
        return "h"
    if slug.endswith("ampere"):
        return "A"
    if slug.endswith("volt"):
        return "V"
    match = re.search(r"\(([^)]+)\)|\[([^\]]+)\]|/\s*([A-Za-z0-9Ω°µμ.]+)\s*$", text)
    if not match:
        return None
    unit = next(group for group in match.groups() if group)
    return (
        unit.replace("Ω", "ohm")
        .replace("Ω", "ohm")
        .replace("°C", "degC")
        .replace("Â°C", "degC")
        .replace("�C", "degC")
        .replace("℃", "degC")
        .replace("癈", "degC")
        .replace("μ", "µ")
        .replace("A.h", "Ah")
        .replace("W.h", "Wh")
        .replace("Ohms", "ohm")
        .replace("Ohm", "ohm")
    )


def _unit_factor(source_unit: str | None, target_unit: str) -> float:
    if not source_unit or source_unit == target_unit:
        return 1.0
    key = (source_unit.lower().replace(" ", ""), target_unit.lower())
    factors = {
        ("ma", "a"): 1e-3,
        ("µa", "a"): 1e-6,
        ("ua", "a"): 1e-6,
        ("mv", "v"): 1e-3,
        ("mah", "ah"): 1e-3,
        ("ma.h", "ah"): 1e-3,
        ("mahr", "ah"): 1e-3,
        ("mahrs", "ah"): 1e-3,
        ("ma*h", "ah"): 1e-3,
        ("ahr", "ah"): 1.0,
        ("ahrs", "ah"): 1.0,
        ("a*h", "ah"): 1.0,
        ("mwh", "wh"): 1e-3,
        ("mw.h", "wh"): 1e-3,
        ("mwhr", "wh"): 1e-3,
        ("mwhrs", "wh"): 1e-3,
        ("mw*h", "wh"): 1e-3,
        ("whr", "wh"): 1.0,
        ("whrs", "wh"): 1.0,
        ("w*h", "wh"): 1.0,
        ("mw", "w"): 1e-3,
        ("h", "s"): 3600.0,
        ("hr", "s"): 3600.0,
        ("hour", "s"): 3600.0,
        ("hours", "s"): 3600.0,
        ("min", "s"): 60.0,
        ("ms", "s"): 1e-3,
        ("sec", "s"): 1.0,
        ("secs", "s"): 1.0,
        ("second", "s"): 1.0,
        ("seconds", "s"): 1.0,
        ("c", "degc"): 1.0,
        ("degc", "degc"): 1.0,
        ("celsius", "degc"): 1.0,
        ("degcelsius", "degc"): 1.0,
        ("ohm", "ohm"): 1.0,
        ("ohms", "ohm"): 1.0,
        ("o", "ohm"): 1.0,
        ("mohm", "ohm"): 1e-3,
        ("mω", "ohm"): 1e-3,
        ("kohm", "ohm"): 1e3,
    }
    return factors.get(key, 1.0)


def _classify_status(value: Any) -> str | None:
    text = str(value).strip().lower()
    if not text:
        return None
    if text in {"c", "chg"} or ("charge" in text and "dis" not in text):
        return "charge"
    if text in {"d", "dchg"} or "discharge" in text or "dch" in text:
        return "discharge"
    if text in {"r", "rest", "idle", "pause", "ocv", "open circuit"} or "rest" in text:
        return "rest"
    if text.startswith("c"):
        return "charge"
    if text.startswith("d"):
        return "discharge"
    return None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _repair_operations(df: pl.DataFrame) -> list[str]:
    operations: list[str] = []
    if df.is_empty() or "Test Time / s" not in df.columns:
        return operations

    required_present = [c for c in REQUIRED_COLUMNS if c in df.columns]
    if required_present:
        mask = pl.any_horizontal([pl.col(c).is_null() for c in required_present])
        dropped = df.filter(mask).height
        if dropped:
            operations.append(f"Would drop {dropped} rows with null required values.")

    try:
        times_series = df["Test Time / s"].cast(pl.Float64, strict=False)
    except Exception:
        operations.append("Would coerce Test Time / s to numeric and drop invalid rows.")
        return operations

    times_raw = times_series.to_list()
    non_finite = sum(t is not None and not math.isfinite(float(t)) for t in times_raw)
    if non_finite:
        operations.append(f"Would drop {non_finite} rows with non-finite Test Time / s.")

    times = [float(t) for t in times_raw if t is not None and math.isfinite(float(t))]
    if not times:
        return operations
    if times != sorted(times):
        operations.append("Would sort rows by Test Time / s.")
    min_time = min(times)
    if abs(min_time) > 1e-12:
        operations.append("Would shift Test Time / s to start at 0.")
    sorted_times = sorted(times)
    if any(b <= a for a, b in pairwise(sorted_times)):
        operations.append("Would offset duplicate or non-increasing test times by 1e-6 s.")
    return operations
