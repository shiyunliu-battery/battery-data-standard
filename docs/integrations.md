# Ecosystem Integrations

These pages show how to use `battery-data-standard` (BDS) as the first
normalization step before downstream battery, data engineering, or modelling
tools.

The common pattern is:

1. Start with raw cycler exports.
2. Convert with BDS to a validated CSV or Parquet table.
3. Load that table into the downstream tool, or reshape it with the small
   mapping shown in the integration page.

## Data Engineering

- [battery-data-standard + DuckDB](integrations/duckdb.md)
- [battery-data-standard + Polars](integrations/polars.md)

## Battery Analysis Tools

- [battery-data-standard + cellpy](integrations/cellpy.md)
- [battery-data-standard + BEEP](integrations/beep.md)

## Modelling And Diagnostic Workflows

- [battery-data-standard + PyBaMM](integrations/pybamm.md)
- [battery-data-standard + PyProBE](integrations/pyprobe.md)

## Repositories

- [battery-data-standard + Battery Archive](integrations/battery-archive.md)

## BDS Export Labels

For public handoff, use `bds convert` or `bds.convert(...)`. The default BDS
export uses labels such as `Test Time (s)`, `Voltage (V)`, and `Current (A)`.
Integration pages prefer those export labels and target presets over internal
adapter labels.
