"""Validation for normalized time-series data frames."""

from __future__ import annotations

import math
from itertools import pairwise

import polars as pl

from .reports import ValidationIssue, ValidationReport
from .schema import BDS_SCHEMA_VERSION, OPTIONAL_COLUMNS, REQUIRED_COLUMNS, SUPPORTED_SCHEMA_VERSIONS


def validate(
    df: pl.DataFrame,
    schema_version: str = BDS_SCHEMA_VERSION,
    strict: bool = True,
) -> ValidationReport:
    issues: list[ValidationIssue] = []
    columns = list(df.columns)

    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        issues.append(
            ValidationIssue(
                "error",
                "unsupported-schema-version",
                f"Unsupported schema version {schema_version}; expected {BDS_SCHEMA_VERSION}.",
            )
        )

    if df.is_empty():
        issues.append(ValidationIssue("error", "empty-dataframe", "Dataframe has no rows."))

    for column in REQUIRED_COLUMNS:
        if column not in columns:
            issues.append(
                ValidationIssue(
                    "error", "missing-required-column", f"Missing required column {column}.", column
                )
            )

    for column in REQUIRED_COLUMNS:
        if column not in columns:
            continue
        nulls = df[column].null_count()
        if nulls:
            issues.append(
                ValidationIssue(
                    "error", "null-required-values", f"{column} contains {nulls} null values.", column
                )
            )
        if column in {"test_time_s", "voltage_v", "current_a"}:
            casted = df[column].cast(pl.Float64, strict=False)
            failed = casted.null_count() - df[column].null_count()
            if failed > 0:
                issues.append(
                    ValidationIssue(
                        "error", "non-numeric-required", f"{column} has {failed} non-numeric values.", column
                    )
                )
            non_finite = sum(not math.isfinite(float(v)) for v in casted.drop_nulls().to_list())
            if non_finite:
                issues.append(
                    ValidationIssue(
                        "error",
                        "non-finite-required",
                        f"{column} contains {non_finite} non-finite values.",
                        column,
                    )
                )

    if "test_time_s" in columns and not df.is_empty():
        times = [float(v) for v in df["test_time_s"].cast(pl.Float64, strict=False).drop_nulls().to_list()]
        if len(times) != df.height:
            issues.append(
                ValidationIssue(
                    "error",
                    "invalid-test-time",
                    "test_time_s could not be parsed for every row.",
                    "test_time_s",
                )
            )
        elif any(not math.isfinite(t) for t in times):
            issues.append(
                ValidationIssue(
                    "error",
                    "non-finite-test-time",
                    "test_time_s contains non-finite values.",
                    "test_time_s",
                )
            )
        elif any(b <= a for a, b in pairwise(times)):
            issues.append(
                ValidationIssue(
                    "error" if strict else "warning",
                    "non-increasing-test-time",
                    "test_time_s must be strictly increasing.",
                    "test_time_s",
                )
            )

    for column in OPTIONAL_COLUMNS:
        if column not in columns:
            issues.append(
                ValidationIssue(
                    "warning", "missing-optional-column", f"Optional column {column} is absent.", column
                )
            )

    valid = not any(issue.level == "error" for issue in issues)
    return ValidationReport(valid, schema_version, df.height, columns, issues)
