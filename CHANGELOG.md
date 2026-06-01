# Changelog

## 0.2.0 - 2026-06-01

- Added export targets for DuckDB, Polars, cellpy, BEEP, PyBaMM, PyProBE, and Battery Archive workflows.
- Added `bds audit` and API support for intake quality scoring across raw folders.
- Added Repower and PEC adapters, BioLogic `.mpr` support through the optional `mpr` extra, and Gamry `.DTA` EIS reading.
- Lowered the supported Python floor to Python 3.10 and expanded CI coverage to Python 3.10 through 3.13.

## 0.1.2 - 2026-05-30

- Documented how to preserve raw current sign and apply explicit time-axis
  repairs for real experimental datasets.
- Documented how to display user-facing export labels such as `Test Time (s)`,
  `Voltage (V)`, and `Current (A)` from the internal normalized dataframe.
- Added Arbin Excel workbook hardening so `Channel_*` sheets are preferred
  over duplicate/raw `RawData_*` sheets during automatic time-series reading.
- Added EIS Excel workbook hardening for Arbin/Gamry-style `ACIM_*` sheets
  with `Freq`, `Zmod`, and `Zphz` magnitude/phase columns.
- Added MATLAB vector mapping improvements for Novonix-style
  `CurrentData`/`VoltageData`/`TimeData` files and struct fields such as
  `Dataset.U` and `Dataset.I`.

## 0.1.1 - 2026-05-27

- Improved CSV header detection for Novonix exports that place protocol and
  step-limit sections before the `[Data]` table.
- Preserved Novonix attribution for files with `Date and Time`, `Run Time (h)`,
  `Step Time (h)`, `Current (A)`, and `Potential (V)` columns after a structured
  preamble.

## 0.1.0 - 2026-05-01

- Published the initial public package for battery cycler data conversion.
- Added the `battery_data_standard` Python package and the `bds` import alias.
- Added the `bds` command-line interface for format detection, conversion, validation,
  schema inspection, and batch processing.
- Added adapters for NEWARE, Arbin, Maccor, BioLogic, Novonix, BaSyTec, LANDT,
  and generic tabular exports.
- Added support for CSV, text, Excel, MATLAB, and Parquet input families where
  time, voltage, and current data can be mapped to the standard schema.
- Added standardized BDS time-series outputs with validation reports,
  column provenance, source metadata, and optional sidecar reports.
- Added EIS detection, reading, conversion, and validation entry points.
- Added archive-aware batch conversion with JSONL manifests for directories and
  supported archive files.
- Added step-level and cycle-level summary helpers for normalized time-series
  data.
- Set the normalized current convention to charge-positive and discharge-negative
  by default.
