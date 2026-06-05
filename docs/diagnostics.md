# Diagnostics and Audit Reports

BDS diagnostics are meant to answer the question: "What did the converter think
this file was, and what would it do to the data?"

## Single-File Explain

Use `bds explain` before conversion when a file is new, private, or failing:

```bash
bds explain raw_export.csv
bds explain raw_export.csv --text
bds explain raw_export.csv --json report.json --html report.html --xlsx report.xlsx
bds explain raw_export.csv --pdf report.pdf
```

JSON remains the machine-readable diagnostic record. HTML and Excel are intended
for ordinary user review and lab QA. PDF is the recommended fixed-layout report
format for archival review and sharing.

The diagnostic report includes:

- data kind: time-series, EIS, unsupported, or unknown;
- adapter candidates, selected adapter, confidence, and sheet;
- source columns, canonical columns, export columns, and mapping provenance;
- unit transforms, current-sign evidence, and current-sign confidence;
- semantic source notes for inferred time, step, and cycle fields;
- repair policy, validation issues, warnings, and unmapped columns;
- recommended next action.

Python callers can use the same diagnostic:

```python
import bds

report = bds.explain("raw_export.csv", current_sign="preserve")
print(report.to_json())
print(report.to_text())
bds.write_explain_reports(report, "reports", formats=("json", "html", "xlsx"))
```

`explain` does not write converted data. It reuses the same detection,
normalization, validation, and export formatting path as conversion, with
`strict=False` so diagnostic output can still be returned for imperfect files.

## Conversion Reports

For ordinary conversion, use `report_path="auto"`:

```python
import bds

report = bds.convert(
    "raw_export.csv",
    "normalized.bds.csv",
    cycler="auto",
    report_path="auto",
)
```

This writes the converted CSV plus `normalized.bds.report.json` and
`normalized.bds.report.pdf`. Other report formats are explicit:

```python
bds.convert(
    "raw_export.csv",
    "normalized.bds.csv",
    report_path="auto",
    report_formats=("html", "xlsx"),
)
```

HTML, Excel, and PDF reports use the same section structure and blue visual
style. JSON remains the source of truth for automated pipelines.

Current-sign sanity is optional. Use `current_sign_check="adjacent"` in Python,
or `--current-sign-check adjacent` in the CLI, to run the O(n) adjacent-point
heuristic when a file needs extra sign review.

## Time Sampling

Time-series conversion checks the `test_time_s` column for missing samples on a
regular grid. If the expected interval is known, pass it explicitly:

```python
bds.convert(
    "raw_export.csv",
    "normalized.bds.csv",
    report_path="auto",
    time_sampling_interval_s=1,
)
```

The default `time_sampling_policy="repair"` inserts missing rows only when a
regular interval is detected or supplied. Numeric measurement columns are
interpolated with `time_sampling_interpolation="linear"` by default. Use
`time_sampling_policy="warn"` to record gaps without inserting rows, or use
`time_sampling_policy="none"` to disable this check.

The report records the inferred interval, confidence, number of missing samples,
gap locations, interpolation method, and number of inserted rows.

## Folder Audit

Use `bds audit` for intake triage across a folder:

```bash
bds audit raw_exports --recursive --json audit.json --html audit.html
```

Directory audit skips obvious helper files such as README files, manifests,
metadata sidecars, labels, summaries, procedure files, and conversion-report
sidecars. Single-file audit still explains an explicitly selected helper file.

Audit quality scores focus on trust-affecting issues: conversion failure,
required-column problems, detection confidence, time-axis anomalies, repair
operations, current-sign evidence, and suspicious flat signals. Optional-column
coverage is reported separately under `completeness`.

## Recommended Workflow

1. Run `bds explain` on one representative file.
2. Review mapping, units, current sign evidence, and validation issues.
3. Run `bds convert --report auto` once the diagnostic looks right.
4. Run `bds audit` on the whole folder before batch conversion.
