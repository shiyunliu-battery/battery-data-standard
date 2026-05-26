"""Step and cycle summary helpers for normalized BDF-style data."""

from __future__ import annotations

import polars as pl


def summarize_steps(df: pl.DataFrame) -> pl.DataFrame:
    """Summarize a normalized dataframe by cycle and step when available."""
    group_cols = [col for col in ("Cycle Count / 1", "Step Count / 1") if col in df.columns]
    if not group_cols:
        if "Step Index / 1" in df.columns:
            group_cols = ["Step Index / 1"]
        else:
            return _summary_for_whole_table(df, label="all")
    return _group_summary(df, group_cols)


def summarize_cycles(df: pl.DataFrame) -> pl.DataFrame:
    """Summarize a normalized dataframe by cycle when available."""
    if "Cycle Count / 1" not in df.columns:
        return _summary_for_whole_table(df, label="all")
    return _group_summary(df, ["Cycle Count / 1"])


def _group_summary(df: pl.DataFrame, group_cols: list[str]) -> pl.DataFrame:
    return df.group_by(group_cols, maintain_order=True).agg(_summary_exprs(df))


def _summary_for_whole_table(df: pl.DataFrame, *, label: str) -> pl.DataFrame:
    summary = df.select(_summary_exprs(df))
    return summary.with_columns(pl.lit(label).alias("Group")).select(["Group", *summary.columns])


def _summary_exprs(df: pl.DataFrame) -> list[pl.Expr]:
    exprs: list[pl.Expr] = [
        pl.len().alias("Rows / 1"),
    ]
    if "Test Time / s" in df.columns:
        exprs.extend(
            [
                pl.col("Test Time / s").min().alias("Start Test Time / s"),
                pl.col("Test Time / s").max().alias("End Test Time / s"),
                (pl.col("Test Time / s").max() - pl.col("Test Time / s").min()).alias("Duration / s"),
            ]
        )
    if "Voltage / V" in df.columns:
        exprs.extend(
            [
                pl.col("Voltage / V").min().alias("Min Voltage / V"),
                pl.col("Voltage / V").max().alias("Max Voltage / V"),
            ]
        )
    if "Current / A" in df.columns:
        exprs.extend(
            [
                pl.col("Current / A").min().alias("Min Current / A"),
                pl.col("Current / A").max().alias("Max Current / A"),
            ]
        )
    if "Charging Capacity / Ah" in df.columns:
        exprs.append(pl.col("Charging Capacity / Ah").max().alias("Charging Capacity End / Ah"))
    if "Discharging Capacity / Ah" in df.columns:
        exprs.append(pl.col("Discharging Capacity / Ah").max().alias("Discharging Capacity End / Ah"))
    if "Charging Energy / Wh" in df.columns:
        exprs.append(pl.col("Charging Energy / Wh").max().alias("Charging Energy End / Wh"))
    if "Discharging Energy / Wh" in df.columns:
        exprs.append(pl.col("Discharging Energy / Wh").max().alias("Discharging Energy End / Wh"))
    return exprs
