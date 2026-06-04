"""Regular time-sampling checks and interpolation for time-series tables."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

import polars as pl

from .exceptions import ConversionError
from .reports import ValidationIssue

TIME_SAMPLING_POLICIES = ("none", "warn", "repair")
TIME_SAMPLING_INTERPOLATION_METHODS = ("linear", "forward-fill", "backward-fill", "nearest")

_FLOAT_DTYPES = {pl.Float32, pl.Float64}
_INTEGER_DTYPES = {
    pl.Int8,
    pl.Int16,
    pl.Int32,
    pl.Int64,
    pl.UInt8,
    pl.UInt16,
    pl.UInt32,
    pl.UInt64,
}


@dataclass
class TimeSamplingResult:
    data: pl.DataFrame
    metadata: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    validation_issues: list[ValidationIssue] = field(default_factory=list)
    repair_operations: list[str] = field(default_factory=list)


def apply_time_sampling_policy(
    df: pl.DataFrame,
    *,
    policy: str = "repair",
    expected_interval_s: float | None = None,
    interpolation_method: str = "linear",
    tolerance: float = 0.1,
    max_inserted_rows: int = 100_000,
) -> TimeSamplingResult:
    """Detect missing samples on a regular time grid and optionally interpolate them."""
    policy = _normalize_policy(policy)
    method = _normalize_interpolation(interpolation_method)
    if tolerance < 0:
        raise ConversionError("time_sampling_tolerance must be non-negative.")
    if max_inserted_rows < 0:
        raise ConversionError("time_sampling_max_inserted_rows must be non-negative.")

    metadata: dict[str, Any] = {
        "policy": policy,
        "interpolation_method": method,
        "tolerance_fraction": tolerance,
        "expected_interval_s": expected_interval_s,
        "status": "not-checked" if policy == "none" else "checked",
        "original_rows": df.height,
        "output_rows": df.height,
    }
    if policy == "none":
        return TimeSamplingResult(df, metadata)
    if "test_time_s" not in df.columns:
        metadata["status"] = "no-time-column"
        return TimeSamplingResult(df, metadata)
    if df.height < 3 and expected_interval_s is None:
        metadata["status"] = "insufficient-data"
        return TimeSamplingResult(df, metadata)

    times = _numeric_times(df)
    if times is None:
        metadata["status"] = "invalid-time-column"
        return TimeSamplingResult(df, metadata)
    if any(b <= a for a, b in pairwise(times)):
        metadata["status"] = "non-increasing-time"
        return TimeSamplingResult(df, metadata)

    deltas = [b - a for a, b in pairwise(times)]
    expected, confidence = _expected_interval(
        deltas, expected_interval_s=expected_interval_s, tolerance=tolerance
    )
    metadata["expected_interval_s"] = expected
    metadata["interval_confidence"] = confidence
    if expected is None:
        metadata["status"] = "irregular-interval"
        return TimeSamplingResult(df, metadata)
    if expected <= 0 or not math.isfinite(expected):
        metadata["status"] = "invalid-expected-interval"
        return TimeSamplingResult(df, metadata)
    if expected_interval_s is None and len(deltas) >= 4 and confidence < 0.5:
        metadata["status"] = "irregular-interval"
        return TimeSamplingResult(df, metadata)

    gaps = _sampling_gaps(times, expected=expected, tolerance=tolerance)
    missing_points = sum(int(gap["missing_count"]) for gap in gaps)
    metadata["missing_points"] = missing_points
    metadata["gaps"] = [_public_gap(gap) for gap in gaps[:50]]
    metadata["gaps_truncated"] = len(gaps) > 50
    if missing_points == 0:
        metadata["status"] = "no-gaps"
        return TimeSamplingResult(df, metadata)

    warning = (
        f"Time sampling check found {missing_points} missing sample point(s) "
        f"using an expected interval of {_format_seconds(expected)} s."
    )
    issue = ValidationIssue(
        "warning",
        "missing-sample-timepoints",
        warning,
        "test_time_s",
    )
    if policy == "warn":
        metadata["status"] = "gaps-detected"
        return TimeSamplingResult(df, metadata, warnings=[warning], validation_issues=[issue])
    if missing_points > max_inserted_rows:
        metadata["status"] = "too-many-gaps-not-repaired"
        warning = (
            f"{warning} Automatic interpolation was skipped because it would insert "
            f"{missing_points} rows, above the configured limit of {max_inserted_rows}."
        )
        issue.message = warning
        return TimeSamplingResult(df, metadata, warnings=[warning], validation_issues=[issue])

    repaired = _insert_interpolated_rows(df, times, gaps, method=method)
    operation = (
        f"Inserted {missing_points} interpolated sample row(s) on the test_time_s grid "
        f"using {method} interpolation."
    )
    metadata["status"] = "repaired"
    metadata["output_rows"] = repaired.height
    metadata["inserted_rows"] = missing_points
    return TimeSamplingResult(
        repaired,
        metadata,
        warnings=[warning],
        validation_issues=[issue],
        repair_operations=[operation],
    )


def _normalize_policy(policy: str) -> str:
    normalized = str(policy).strip().lower().replace("_", "-")
    if normalized not in TIME_SAMPLING_POLICIES:
        raise ConversionError(
            "Unsupported time_sampling_policy "
            f"{policy!r}. Supported policies: {', '.join(TIME_SAMPLING_POLICIES)}."
        )
    return normalized


def _normalize_interpolation(method: str) -> str:
    normalized = str(method).strip().lower().replace("_", "-")
    aliases = {"ffill": "forward-fill", "bfill": "backward-fill"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in TIME_SAMPLING_INTERPOLATION_METHODS:
        raise ConversionError(
            "Unsupported time_sampling_interpolation "
            f"{method!r}. Supported methods: {', '.join(TIME_SAMPLING_INTERPOLATION_METHODS)}."
        )
    return normalized


def _numeric_times(df: pl.DataFrame) -> list[float] | None:
    casted = df["test_time_s"].cast(pl.Float64, strict=False)
    if casted.null_count() != df["test_time_s"].null_count():
        return None
    values = casted.to_list()
    if any(value is None or not math.isfinite(float(value)) for value in values):
        return None
    return [float(value) for value in values]


def _expected_interval(
    deltas: list[float],
    *,
    expected_interval_s: float | None,
    tolerance: float,
) -> tuple[float | None, float]:
    if not deltas:
        return None, 0.0
    if expected_interval_s is not None:
        expected = float(expected_interval_s)
        if expected <= 0 or not math.isfinite(expected):
            raise ConversionError("time_sampling_interval_s must be a positive finite value.")
        return expected, _interval_confidence(deltas, expected, tolerance)

    rounded_counts: dict[float, int] = {}
    for delta in deltas:
        if delta <= 0 or not math.isfinite(delta):
            continue
        rounded = round(delta, 9)
        rounded_counts[rounded] = rounded_counts.get(rounded, 0) + 1
    if not rounded_counts:
        return None, 0.0
    top_count = max(rounded_counts.values())
    if top_count == 1 and len(deltas) < 3:
        return None, 0.0
    expected = min(
        rounded_counts,
        key=lambda value: (-rounded_counts[value], value),
    )
    return expected, _interval_confidence(deltas, expected, tolerance)


def _interval_confidence(deltas: list[float], expected: float, tolerance: float) -> float:
    if not deltas:
        return 0.0
    tolerance_abs = max(1e-9, abs(expected) * tolerance)
    hits = sum(abs(delta - expected) <= tolerance_abs for delta in deltas)
    return hits / len(deltas)


def _sampling_gaps(times: list[float], *, expected: float, tolerance: float) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    tolerance_abs = max(1e-9, abs(expected) * tolerance)
    for index, (start, end) in enumerate(pairwise(times)):
        delta = end - start
        if delta <= expected + tolerance_abs:
            continue
        multiples = round(delta / expected)
        if multiples <= 1:
            continue
        if abs(delta - (multiples * expected)) > tolerance_abs:
            continue
        missing_times = [start + expected * step for step in range(1, multiples)]
        gaps.append(
            {
                "index": index,
                "start_time_s": start,
                "end_time_s": end,
                "observed_interval_s": delta,
                "missing_count": len(missing_times),
                "_missing_times_s": missing_times,
            }
        )
    return gaps


def _public_gap(gap: dict[str, Any]) -> dict[str, Any]:
    times = list(gap.get("_missing_times_s") or [])
    return {
        "start_time_s": gap["start_time_s"],
        "end_time_s": gap["end_time_s"],
        "observed_interval_s": gap["observed_interval_s"],
        "missing_count": gap["missing_count"],
        "missing_times_s": times[:20],
        "missing_times_truncated": len(times) > 20,
    }


def _insert_interpolated_rows(
    df: pl.DataFrame,
    times: list[float],
    gaps: list[dict[str, Any]],
    *,
    method: str,
) -> pl.DataFrame:
    rows = df.to_dicts()
    schema = df.schema
    gaps_by_index = {int(gap["index"]): gap for gap in gaps}
    output: list[dict[str, Any]] = []
    for index, row in enumerate(rows[:-1]):
        output.append(row)
        gap = gaps_by_index.get(index)
        if gap is None:
            continue
        next_row = rows[index + 1]
        start = times[index]
        end = times[index + 1]
        for missing_time in gap["_missing_times_s"]:
            output.append(
                _interpolated_row(
                    row,
                    next_row,
                    float(missing_time),
                    start_time=start,
                    end_time=end,
                    schema=schema,
                    method=method,
                )
            )
    output.append(rows[-1])
    return pl.DataFrame(output).select(df.columns)


def _interpolated_row(
    previous: dict[str, Any],
    following: dict[str, Any],
    time_s: float,
    *,
    start_time: float,
    end_time: float,
    schema: dict[str, pl.DataType],
    method: str,
) -> dict[str, Any]:
    row: dict[str, Any] = {}
    ratio = (time_s - start_time) / (end_time - start_time)
    for column, dtype in schema.items():
        if column == "test_time_s":
            row[column] = time_s
            continue
        if column == "record_index":
            row[column] = None
            continue
        row[column] = _interpolate_value(
            column,
            previous.get(column),
            following.get(column),
            ratio=ratio,
            dtype=dtype,
            method=method,
        )
    return row


def _interpolate_value(
    column: str,
    previous: Any,
    following: Any,
    *,
    ratio: float,
    dtype: pl.DataType,
    method: str,
) -> Any:
    if previous is None and following is None:
        return None
    if previous is None:
        return following if method in {"backward-fill", "nearest"} else None
    if following is None:
        return previous if method in {"forward-fill", "nearest"} else None
    if method == "forward-fill":
        return previous
    if method == "backward-fill":
        return following
    if method == "nearest":
        return previous if ratio <= 0.5 else following
    if _is_continuous_numeric(column, dtype):
        try:
            return float(previous) + ratio * (float(following) - float(previous))
        except (TypeError, ValueError):
            return previous if ratio <= 0.5 else following
    if previous == following:
        return previous
    return previous if ratio <= 0.5 else following


def _is_continuous_numeric(column: str, dtype: pl.DataType) -> bool:
    if dtype not in _FLOAT_DTYPES and dtype not in _INTEGER_DTYPES:
        return False
    if column in {"cycle_index", "step_index", "record_index"}:
        return False
    if column in {"unix_time_s", "step_time_s"}:
        return True
    if column.endswith(("_s", "_v", "_a", "_w", "_ah", "_wh", "_ohm")):
        return True
    lowered = column.lower()
    return any(token in lowered for token in ("temperature", "resistance", "soc", "capacity", "energy"))


def _format_seconds(value: float) -> str:
    return f"{value:.9g}"
