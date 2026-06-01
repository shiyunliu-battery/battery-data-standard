# battery-data-standard + PyProBE

## Question

I already have raw cycler files. How do I use BDS to prepare data for PyProBE
diagnostic workflows?

## Use This When

Use this path when you need clean time, current, voltage, cycle, and step fields
before running a diagnostic workflow such as HPPC, GITT, OCV, rate testing, or
capacity checks in PyProBE or a PyProBE-adjacent notebook.

## Convert Raw Files

```bash
bds convert raw.mpt pyprobe_staging.parquet \
  --target pyprobe \
  --format parquet \
  --current-sign preserve \
  --repair-policy repair \
  --report pyprobe_staging.report.json
```

## Create A Diagnostic Staging Table

```python
import polars as pl

diagnostic = pl.read_parquet("pyprobe_staging.parquet")
```

## Suggested Mapping

| BDS export column | Diagnostic staging column |
| --- | --- |
| `Test Time (s)` | `time_s` |
| `Voltage (V)` | `voltage_v` |
| `Current (A)` | `current_a` |
| `Cycle Count` | `cycle_index` |
| `Step Index` | `step_index` |
| `Step Time (s)` | `step_time_s` |
| `Charging Capacity (Ah)` | `charge_capacity_ah` |
| `Discharging Capacity (Ah)` | `discharge_capacity_ah` |

## Select Diagnostic Segments

For HPPC-like pulse analysis, it is often better to pass a selected segment than
the whole raw test:

```python
hppc_cycle = diagnostic.filter(pl.col("cycle_index") == 5)
hppc_cycle.write_parquet("pyprobe_hppc_cycle_005.parquet")
```

For GITT-like analysis, preserve `step_index` and `step_time_s`; they are usually
needed to separate pulse and relaxation steps.

## EIS Data

If the raw file is EIS-only:

```bash
bds convert-eis gamry.DTA pyprobe_eis.parquet --format parquet
```

Then use `Frequency_Hz`, `Zre_exp_Ohm`, and `Zim_exp_Ohm` as the normalized EIS
handoff columns.

## Known Limits

- PyProBE workflows may expect project-specific metadata beyond the time-series
  table. Keep the BDS conversion report and any lab metadata next to the staging
  Parquet file.
- This page documents a normalized staging table, not a promise that every
  PyProBE version has a native BDS importer.
- If your PyProBE workflow has a formal procedure schema, add the schema fields
  as a metadata sidecar rather than encoding them in column names.
