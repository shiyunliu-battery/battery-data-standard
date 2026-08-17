# Battery Data Standard

**Inspect, diagnose, and convert battery cycler data locally.**

[![PyPI 0.3.1](https://img.shields.io/badge/PyPI-0.3.1-blue.svg)](https://pypi.org/project/battery-data-standard/0.3.1/)
[![Python >=3.10](https://img.shields.io/badge/Python-%3E%3D3.10-blue.svg)](https://pypi.org/project/battery-data-standard/0.3.1/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Package](https://img.shields.io/badge/package-bds-blue.svg)](https://pypi.org/project/battery-data-standard/)

`battery-data-standard` (BDS) is an open-source command-line tool and Python
library for working with battery cycler exports.

BDS detects file formats, explains column and unit mappings, identifies
time-axis and current-sign risks, reports unsupported fields, and converts
supported data to CSV or Parquet for downstream workflows.

```bash
bds inspect raw_export.csv
```

Inspection is local and non-mutating. It does not modify the source file,
insert missing samples, or silently change current values.

The package is vendor-neutral and independent. It is not certified by any cycler
vendor or standards body. Adapter support describes behavior implemented and
validated by this project; users should verify representative exports from their
own cycler software before using the package in automated production workflows.

## Installation

Python 3.10 or newer is required.

```bash
pip install --upgrade battery-data-standard
```

Optional extras are available for additional input formats:

```bash
pip install "battery-data-standard[yaml]"
pip install "battery-data-standard[matlab]"
pip install "battery-data-standard[mpr]"
```

The package installs the `bds` command and exposes both the full package name
and a short import alias:

```python
import battery_data_standard as bds

# or
import bds
```

## Features

The package can:

- inspect unfamiliar battery cycler files before conversion;
- detect supported cycler and data formats;
- explain column, unit, and current-sign mappings;
- report missing fields, sampling gaps, and unmapped columns;
- provide suggested next steps when a file cannot be processed cleanly;
- convert supported time-series and EIS data to CSV or Parquet;
- generate JSON, HTML, Excel, and PDF reports;
- process directories, zip archives, and tar archives locally;
- export staging data for BDF, PyProBE, PyBaMM, cellpy, BEEP, DuckDB, and
  Polars workflows;
- use optional column-mapping profiles for lab-specific headers.

The package does not upload source data to an external service. It reads local
files and writes local outputs.

## Quick Start

Inspect the installed version:

```bash
bds --version
```

Inspect an unfamiliar file:

```bash
bds inspect raw_export.csv
```

Preview mappings for a downstream target:

```bash
bds inspect raw_export.csv --target bdf --format json
bds inspect raw_export.csv --target pyprobe
```

Write review reports:

```bash
bds inspect raw_export.csv --output inspect.json --output inspect.html
```

Detect only the likely cycler format:

```bash
bds detect raw_export.csv
```

Convert a time-series file:

```bash
bds convert raw_export.csv normalized.bds.csv --cycler auto --report auto
```

`--report auto` writes `normalized.bds.report.json` and
`normalized.bds.report.pdf` next to the converted CSV. Add
`--report-format html` or `--report-format xlsx` when those review formats are
needed.

Export directly to a downstream staging format:

```bash
bds convert raw_export.csv pybamm_drive_cycle.csv --target pybamm
bds convert raw_export.csv pyprobe_staging.parquet --target pyprobe --format parquet
```

Validate a converted file:

```bash
bds validate normalized.bds.csv
```

Convert a directory or archive and write a JSONL manifest:

```bash
bds batch raw_exports normalized_exports --recursive --manifest manifest.jsonl
bds batch raw_exports.zip normalized_exports --manifest manifest.jsonl
```

Audit a raw folder before committing to conversion:

```bash
bds audit raw_exports --recursive --json audit.json --html audit.html
```

The audit report scores each raw data file and highlights conversion failures,
missing required fields, unit conversions, time-axis repairs, current-sign
evidence, duplicate timestamps, non-monotonic time, suspicious flat
voltage/current, and cycle/step anomalies. Optional-column coverage is reported
separately so small but valid fixtures are not treated as low-quality data just
because they omit fields such as temperature or energy.

Inspect runtime adapter metadata and the pinned schema:

```bash
bds formats
bds inspect-schema
```

`bds formats` reports each adapter's support tier and evidence tier so users can
tell whether support is backed by public fixtures or unit tests.

## Python API

Read a supported time-series export into a Polars dataframe:

```python
import bds

df = bds.read("raw_export.csv", cycler="auto")
```

Show the user-facing export column names defined in the export template:

```python
import bds

export_df = bds.to_export_frame(df)
print(export_df.columns)
```

### Preserve Raw Current Sign And Repair Time Axis

For real experimental datasets, it is often useful to preserve the current sign
exactly as recorded by the source file, allow documented time-axis repairs, and
record any regular-sampling gaps:

```python
df = bds.read(
    path,
    cycler="auto",
    current_sign="preserve",
    repair_policy="repair",
    time_sampling_policy="repair",
)
```

Use `current_sign="preserve"` when downstream analysis should keep the raw
charge/discharge sign convention from the instrument. Use
`repair_policy="repair"` when the pipeline accepts documented normalizations
such as shifting elapsed test time to start at zero or sorting non-monotonic time
values.

When a fixed sampling interval is detected, BDS checks for missing time points.
By default, missing points on that regular grid are interpolated with
`time_sampling_interpolation="linear"` and recorded in the conversion report.
Use `time_sampling_policy="warn"` to report gaps without inserting rows, or set
`time_sampling_interval_s=1`, `2`, `10`, or another known interval when the
sampling cadence is defined by the test protocol.

Use an explicit cycler when the source format is known:

```python
df = bds.read("arbin_export.csv", cycler="arbin")
```

Convert a file and keep the conversion report:

```python
report = bds.convert(
    "raw_export.csv",
    "normalized.bds.csv",
    cycler="auto",
    report_path="auto",
)
```

This writes the converted CSV plus JSON and PDF reports. HTML and Excel reports
can be added with `report_formats=("html", "xlsx")`.

Write a downstream staging table by selecting an export target:

```python
bds.convert("raw_export.csv", "pybamm_drive_cycle.csv", target="pybamm")
bds.convert("raw_export.csv", "cellpy_staging.csv", target="cellpy")
```

Read data and report information in memory:

```python
df, report = bds.read_with_report("raw_export.csv", cycler="auto", strict=False)
```

Create step-level or cycle-level summaries from a normalized dataframe:

```python
steps = bds.summarize_steps(df)
cycles = bds.summarize_cycles(df)
```

## Internal Normalized Model and Export Targets

The converter uses an internal BDS time-series table as an implementation
contract for parsing and export. It is not presented as a universal
scientific-data quality guarantee. Every successful default export contains
three required fields:

| Field | Unit | Description |
| --- | --- | --- |
| `Test Time (s)` | s | Elapsed time from the start of the test. |
| `Voltage (V)` | V | Measured cell or channel voltage. |
| `Current (A)` | A | Measured current. |

Additional fields, such as cycle number, step number, capacity, energy,
temperature, power, and internal resistance, are included when they are available
in the source file.

The default BDS CSV and Parquet exports use user-facing labels with units in
parentheses. Lower-level adapter data may use internal labels; prefer
`bds convert` or `to_export_frame(..., target="bds")` for public handoff.

## Supported Format Families

The package includes adapters for NEWARE, Arbin, Maccor, BioLogic, Repower, PEC,
Novonix, BaSyTec, LANDT, and generic tabular exports. Generic readers support
delimited text, Excel, MATLAB, and Parquet inputs where the file contains or can
be mapped to time, voltage, and current columns.

BioLogic `.mpt` text exports are supported by default. Binary BioLogic `.mpr`
files are supported through the optional `mpr` extra, which installs the
`galvani` backend.

See [docs/supported-formats.md](docs/supported-formats.md) for adapter scope and
support-tier definitions.

## EIS Data

EIS files use a separate standardized table from row-wise time-series data.
Use EIS-specific commands or API functions for known impedance files:

```bash
bds detect-kind impedance.csv
bds convert-eis impedance.csv normalized.eis.csv
```

```python
eis = bds.read_eis("impedance.csv")
report = bds.convert_eis("impedance.csv", "normalized.eis.csv")
```

`read()` and `convert()` are time-series entry points. `batch` and
`batch_convert()` can route mixed directories and archives that contain
time-series files, EIS files, including Gamry `.DTA` ZCURVE files, and
unsupported helper files.

## Column-Mapping Profiles

Profiles map lab-specific column names to canonical column names. JSON profiles
are supported by the base installation. YAML profiles require the `yaml` extra.

```json
{
  "columns": {
    "test_time": "time_seconds",
    "voltage": "cell_voltage",
    "current": "cell_current"
  }
}
```

Use a profile from the CLI:

```bash
bds convert lab_export.csv normalized.bds.csv --cycler generic --profile profile.json
```

## Current Sign Convention

The default current convention is charge-positive and discharge-negative.

Use `--current-sign preserve` to retain the source sign convention, or
`--current-sign discharge-positive` when a downstream workflow requires
discharge-positive current. When a source file contains a recognizable
charge/discharge status column, adapters use it to normalize current sign more
explicitly.

BDS can record a warning-only adjacent-point current-sign sanity check in
conversion metadata and audit records when `current_sign` is charge-positive or
discharge-positive. Use `--current-sign-check adjacent` to enable this O(n)
heuristic for files that need extra sign review.

## Validation and Reports

Every conversion returns a machine-readable report with schema version, row
count, columns, validation status, warnings, provenance, adapter metadata, repair
operations, and time-sampling findings. With `report_path="auto"`, BDS writes
JSON and PDF reports by default; HTML and Excel reports are optional formats.

Strict validation is enabled by default. Repairable issues are reported with the
default `repair_policy="warn"`. Use `repair_policy="repair"` or
`--repair-policy repair` only when the pipeline explicitly accepts the documented
normalizations.

## Documentation

Public documentation is in the `docs` directory:

- [Python API reference](docs/api-reference.md)
- [Supported formats](docs/supported-formats.md)
- [Export template](docs/export-template.md)
- [Export targets](docs/export-template.md#export-targets)
- [Schema compatibility](docs/schema-compatibility.md)
- [Diagnostics and audit reports](docs/diagnostics.md)
- [Current sign convention](docs/current-sign.md)
- [Step and cycle semantics](docs/step-cycle-semantics.md)
- [BDF compatibility status](docs/bdf-compatibility.md)
- [Warning and issue codes](docs/warning-codes.md)
- [Fixture contribution guide](docs/fixture-contribution.md)
- [Ecosystem integrations](docs/integrations.md)

## License and Attribution

This project is distributed under the MIT License. See [NOTICE.md](NOTICE.md)
for the project independence notice.
