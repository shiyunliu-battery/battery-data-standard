# Changelog

## 0.1.0 - 2026-05-01

- Published the initial public package for BDF-oriented battery cycler data conversion.
- Added the `battery_data_standard` Python package and the `bds` import alias.
- Added the `bds` command-line interface for format detection, conversion, validation,
  schema inspection, and batch processing.
- Added adapters for NEWARE, Arbin, Maccor, BioLogic, Novonix, BaSyTec, LANDT,
  and generic tabular exports.
- Added support for CSV, text, Excel, MATLAB, and Parquet input families where
  time, voltage, and current data can be mapped to the standard schema.
- Added standardized BDF-style time-series outputs with validation reports,
  column provenance, source metadata, and optional sidecar reports.
- Added EIS detection, reading, conversion, and validation entry points.
- Added archive-aware batch conversion with JSONL manifests for directories and
  supported archive files.
- Added step-level and cycle-level summary helpers for normalized time-series
  data.
- Set the normalized current convention to charge-positive and discharge-negative
  by default.
