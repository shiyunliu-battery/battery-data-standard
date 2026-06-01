# battery-data-standard + DuckDB

## Question

I already have raw cycler files. How do I turn them into data that DuckDB can
query?

## Use This When

Use this path when you want SQL queries over many converted cycling files,
especially when the files are large enough that opening every file in a notebook
is painful.

## Convert Raw Files

For one file:

```bash
bds convert raw.mpt normalized.duckdb.parquet --target duckdb --format parquet --current-sign preserve
```

For a directory or archive:

```bash
bds batch raw_exports normalized_exports --recursive --target duckdb --format parquet --current-sign preserve
```

Parquet is the preferred handoff format for DuckDB because it preserves typed
columns and can be queried directly without importing into a database first.

## Query With DuckDB

```python
import duckdb

result = duckdb.sql("""
    SELECT
        "Cycle Count",
        max("Voltage (V)") AS max_voltage_v,
        min("Voltage (V)") AS min_voltage_v,
        avg("Current (A)") AS mean_current_a
    FROM 'normalized_exports/**/*.duckdb.parquet'
    GROUP BY "Cycle Count"
    ORDER BY "Cycle Count"
""").df()
```

## Keep Conversion Metadata

For automated pipelines, write a report next to the converted data:

```bash
bds convert raw.mpt normalized.duckdb.parquet --target duckdb --format parquet --report normalized.report.json
```

The data file is for DuckDB. The report is for provenance, source adapter,
warnings, repair operations, and unmapped raw columns.

## EIS Data

EIS files use the EIS route:

```bash
bds convert-eis gamry.DTA normalized.eis.parquet --format parquet
```

Then query the impedance table:

```python
import duckdb

nyquist = duckdb.sql("""
    SELECT "Frequency_Hz", "Zre_exp_Ohm", "Zim_exp_Ohm"
    FROM 'normalized.eis.parquet'
    ORDER BY "Frequency_Hz" DESC
""").df()
```

## Known Limits

- DuckDB does not fix raw cycler headers or units; BDS should do that first.
- Use `bds detect-kind` before batch conversion if a directory mixes time-series
  files, EIS files, README files, and summary tables.
- If a file cannot be mapped to canonical columns, keep the conversion report and add
  a fixture before broadening production conversion rules.
