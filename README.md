# Battery Data Standard

`battery-data-standard` is a Python library and command-line tool for converting
battery cycler exports into a consistent BDF-style tabular representation. It is
intended for laboratories, battery test teams, and data pipelines that need a
repeatable path from vendor files to analysis-ready CSV or Parquet outputs.

The package is vendor-neutral. It is not certified by any cycler vendor or by
the Battery Data Alliance. Adapter support describes behavior implemented and
validated by this project; users should verify representative exports from their
own cycler software before using the package in automated production workflows.

## Installation

Python 3.12 or newer is required.

```bash
pip install battery-data-standard
```

Optional extras are available for additional input formats:

```bash
pip install "battery-data-standard[yaml]"
pip install "battery-data-standard[matlab]"
```

The package installs the `bds` command and exposes both the full package name
and a short import alias:

```python
import battery_data_standard as bds
# or
import bds
```

## Scope

The package provides:

- conversion of supported battery cycler time-series exports to BDF-style CSV or
  Parquet files;
- conversion of supported EIS tables to a standardized EIS table;
- cycler detection, data-kind detection, validation, conversion reports, and
  batch manifests;
- archive-aware batch conversion for directories, zip archives, and tar
  archives;
- optional profile files for lab-specific column naming.

The package does not upload source data to an external service. It reads local
files and writes local outputs.

## Command-Line Usage

Inspect the installed version:

```bash
bds --version
```

Detect a cycler export:

```bash
bds detect raw_export.csv
```

Convert a time-series file:

```bash
bds convert raw_export.csv normalized.bdf.csv --cycler auto --report report.json
```

Validate a converted file:

```bash
bds validate normalized.bdf.csv
```

Convert a directory or archive and write a JSONL manifest:

```bash
bds batch raw_exports normalized_exports --recursive --manifest manifest.jsonl
bds batch raw_exports.zip normalized_exports --manifest manifest.jsonl
```

Inspect runtime adapter metadata and the pinned schema:

```bash
bds formats
bds inspect-schema
```

## Python API

Read a supported time-series export into a Polars dataframe:

```python
import bds

df = bds.read("raw_export.csv", cycler="auto")
```

Use an explicit cycler when the source format is known:

```python
df = bds.read("arbin_export.csv", cycler="arbin")
```

Convert a file and keep the conversion report:

```python
report = bds.convert(
    "raw_export.csv",
    "normalized.bdf.csv",
    cycler="auto",
    report_path="report.json",
)
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

## Output Model

The converter standardizes supported cycler exports into a time-series table.
Every successful BDF time-series conversion must contain three required fields:

| Field | Unit | Description |
| --- | --- | --- |
| `Test Time / s` | s | Elapsed time from the start of the test. |
| `Voltage / V` | V | Measured cell or channel voltage. |
| `Current / A` | A | Measured current. |

Additional fields, such as cycle number, step number, capacity, energy,
temperature, power, and internal resistance, are included when they are available
in the source file.

The internal dataframe uses canonical BDF-style labels. Exported CSV and Parquet
files use easier-to-read labels, for example `Test Time (s)`, `Voltage (V)`, and
`Current (A)`.

## Supported Format Families

The package includes adapters for NEWARE, Arbin, Maccor, BioLogic, Novonix,
BaSyTec, LANDT, and generic tabular exports. Generic readers support delimited
text, Excel, MATLAB, and Parquet inputs where the file contains or can be mapped
to time, voltage, and current columns.

BioLogic `.mpt` text exports are supported. Binary BioLogic `.mpr` files are not
supported; export `.mpt` text files from EC-Lab before conversion.

See [docs/supported-formats.md](docs/supported-formats.md) for adapter scope and
support-tier definitions.

## EIS Data

EIS files use a separate standardized table from row-wise BDF time-series data.
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
time-series files, EIS files, and unsupported helper files.

## Profiles

Profiles map lab-specific column names to canonical column names. JSON profiles
are supported by the base installation. YAML profiles require the `yaml` extra.

```json
{
  "columns": {
    "Test Time / s": "time_seconds",
    "Voltage / V": "cell_voltage",
    "Current / A": "cell_current"
  }
}
```

Use a profile from the CLI:

```bash
bds convert lab_export.csv normalized.bdf.csv --cycler generic --profile profile.json
```

## Current Sign Convention

The default current convention is charge-positive and discharge-negative.

Use `--current-sign preserve` to retain the source sign convention, or
`--current-sign discharge-positive` when a downstream workflow requires
discharge-positive current. When a source file contains a recognizable
charge/discharge status column, adapters use it to normalize current sign more
explicitly.

## Validation and Reports

Every conversion returns or writes a machine-readable report with schema version,
row count, columns, validation status, warnings, provenance, adapter metadata,
and repair operations.

Strict validation is enabled by default. Repairable issues are reported with the
default `repair_policy="warn"`. Use `repair_policy="repair"` or
`--repair-policy repair` only when the pipeline explicitly accepts the documented
normalizations.

## Documentation

Public documentation is in the `docs` directory:

- [Python API reference](docs/api-reference.md)
- [Supported formats](docs/supported-formats.md)
- [Export template](docs/export-template.md)
- [Schema compatibility](docs/schema-compatibility.md)

## License and Attribution

This project is distributed under the MIT License.

The package targets a BDF-oriented output schema inspired by the Battery Data
Format project from the Battery Data Alliance. This project is not an official
Battery Data Alliance project and is not certified by the Battery Data Alliance.
