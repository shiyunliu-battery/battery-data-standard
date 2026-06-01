# battery-data-standard + Polars

## Question

I already have raw cycler files. How do I turn them into data that Polars can
analyze?

## Use This When

Use this path when you want fast dataframe operations in Python and you want BDS
to normalize raw cycler exports before analysis.

## File-Based Path

For reusable analysis, convert to Parquet:

```bash
bds convert raw.mpt normalized.polars.parquet --target polars --format parquet --current-sign preserve
```

Then read lazily with Polars:

```python
import polars as pl

lf = pl.scan_parquet("normalized_exports/**/*.polars.parquet")

cycle_summary = (
    lf.group_by("Cycle Count")
    .agg(
        pl.max("Voltage (V)").alias("max_voltage_v"),
        pl.min("Voltage (V)").alias("min_voltage_v"),
        pl.max("Discharging Capacity (Ah)").alias("discharge_capacity_ah"),
    )
    .collect()
)
```

## In-Memory Path

If you already have an in-memory dataframe from `bds.read()`, convert it to the
same BDS export shape before writing Polars expressions intended for files:

```python
import battery_data_standard as bds
import polars as pl
from battery_data_standard.export import to_export_frame

df = bds.read("raw.mpt", cycler="auto", current_sign="preserve")
bds_df = to_export_frame(df, target="polars")

cycle_summary = bds_df.group_by("Cycle Count").agg(
    pl.max("Voltage (V)").alias("max_voltage_v"),
    pl.min("Voltage (V)").alias("min_voltage_v"),
    pl.max("Discharging Capacity (Ah)").alias("discharge_capacity_ah"),
)
```

## EIS Data

```bash
bds convert-eis impedance.csv normalized.eis.parquet --format parquet
```

```python
import polars as pl

eis = pl.read_parquet("normalized.eis.parquet")
```

The standardized EIS columns are `Frequency_Hz`, `Zre_exp_Ohm`, and
`Zim_exp_Ohm`.

## Known Limits

- Prefer `bds convert --target polars --format parquet` for shareable files.
- If you use `bds.read()` in memory, call `to_export_frame(..., target="polars")`
  before copying file-based examples.
