# Python API Reference

Stable high-level entry points are exported from `battery_data_standard` and from
the short alias package `bds`.

```python
import battery_data_standard as bds
# or
import bds
```

The public API returns Polars dataframes and report objects. Report objects
provide `to_dict()` and `to_json()` methods for serialization.

## Time-Series Conversion

### `read`

```python
read(
    path,
    cycler=None,
    profile=None,
    strict=True,
    keep_raw=False,
    current_sign="charge-positive",
    repair_policy="warn",
    time_sampling_policy="repair",
    time_sampling_interval_s=None,
    time_sampling_interpolation="linear",
    time_sampling_tolerance=0.1,
    detection_threshold=0.1,
    current_sign_check="none",
    sheet=None,
)
```

Reads a supported cycler export into a normalized Polars dataframe.

Use `cycler="auto"` or `cycler=None` for automatic detection. Use an explicit
cycler id such as `neware`, `arbin`, `maccor`, `biologic`, `novonix`,
`basytec`, `landt`, or `generic` when the source system is known.

`read()` returns a lower-level normalized dataframe for package internals and
advanced users. For public BDS handoff, display, or saved files, convert it to
the export template:

```python
from battery_data_standard.export import to_export_frame

export_df = to_export_frame(df)
```

For real experimental datasets, preserve the raw instrument current sign and
repair documented time-axis issues with:

```python
df = bds.read(
    path,
    cycler="auto",
    current_sign="preserve",
    repair_policy="repair",
)
```

`current_sign="preserve"` keeps the source file's current sign convention.
`repair_policy="repair"` applies documented repairs such as shifting elapsed
test time to start at zero.

`time_sampling_policy="repair"` checks regular `test_time_s` sampling and
inserts missing samples only when a fixed interval is detected or supplied. Use
`time_sampling_policy="warn"` to report missing time points without insertion,
or set `time_sampling_interval_s=1`, `2`, `10`, or another protocol interval.
The default interpolation method is `time_sampling_interpolation="linear"`.

`current_sign_check="adjacent"` runs an optional conservative O(n) sanity check that
compares adjacent voltage changes with the current direction when
`current_sign` is `charge-positive` or `discharge-positive`. Use
`current_sign_check="none"` to skip this check. The default is `none` so large
files and heuristic-free workflows do not pay the extra scan cost unless they
ask for it.

### `read_with_report`

```python
read_with_report(path, ...)
```

Returns `(dataframe, ConversionReport)`. This is the recommended entry point for
automated pipelines that need conversion warnings, provenance, adapter metadata,
and validation details.

### `convert`

```python
convert(
    input_path,
    output_path,
    format="csv",
    cycler=None,
    profile=None,
    metadata=None,
    strict=True,
    keep_raw=False,
    current_sign="charge-positive",
    repair_policy="warn",
    time_sampling_policy="repair",
    time_sampling_interval_s=None,
    time_sampling_interpolation="linear",
    time_sampling_tolerance=0.1,
    detection_threshold=0.1,
    current_sign_check="none",
    report_path=None,
    report_formats=None,
    write_sidecars=False,
    sheet=None,
    target="bds",
)
```

Converts a supported time-series export and writes CSV or Parquet output. The
function returns `ConversionReport`.

`format` must be `csv` or `parquet`. Use `report_path="auto"` for the standard
user workflow: the converted data file is written together with JSON and PDF
reports named from the output stem, for example
`normalized.bds.report.json` and `normalized.bds.report.pdf`.

Use `report_formats=("html", "xlsx")` with `report_path="auto"` to add review
formats while keeping the default JSON and PDF reports. Passing a single report
filename writes the format implied by the suffix, such as `report.json`,
`report.html`, `report.xlsx`, or `report.pdf`. If `write_sidecars=True`, report
and metadata sidecars are written next to the output.

`target` selects the output schema preset. The default `bds` target writes the
standard normalized table. Other targets write staging tables for downstream
tools:

| Target | Output shape |
| --- | --- |
| `bds` | Standard BDS export columns such as `Test Time (s)`, `Voltage (V)`, and `Current (A)`. |
| `bdf` | Legacy BDF-style export with slash-unit column names; not a formal conformance certificate. |
| `duckdb` | Same standard table, recommended with Parquet. |
| `polars` | Same standard table, recommended with Parquet. |
| `battery-archive` | Same standard table for archive-style packaging, recommended with Parquet. |
| `cellpy` | cellpy-like lower-case staging columns. |
| `beep` | BEEP-like lower-case staging columns. |
| `pybamm` | Drive-cycle staging table with `time_s` and `current_a`. |
| `pyprobe` | Diagnostic staging table with `time_s`, `voltage_v`, `current_a`, and optional cycle/step fields. |

Available targets are discoverable with:

```python
bds.list_export_targets()
```

## EIS Conversion

### `read_eis`

```python
read_eis(path, sheet=None)
```

Reads an EIS file into the standardized EIS table.

### `convert_eis`

```python
convert_eis(input_path, output_path, format="csv", sheet=None)
```

Converts an EIS file and writes standardized CSV or Parquet output.

### `validate_eis`

```python
validate_eis(dataframe)
```

Validates an in-memory standardized EIS dataframe and returns
`ValidationReport`.

## Batch Conversion

### `batch_convert`

```python
batch_convert(
    input_dir,
    output_dir,
    recursive=False,
    manifest_path=None,
    fail_fast=False,
    format="csv",
    cycler="auto",
    profile=None,
    metadata=None,
    strict=True,
    keep_raw=False,
    current_sign="charge-positive",
    repair_policy="warn",
    time_sampling_policy="repair",
    time_sampling_interval_s=None,
    time_sampling_interpolation="linear",
    time_sampling_tolerance=0.1,
    detection_threshold=0.1,
    current_sign_check="none",
    write_sidecars=False,
    sheet=None,
    excel_sheets="auto",
    target="bds",
)
```

Converts a directory, a single file, or a supported archive. The function returns
a list of per-file records. If `manifest_path` is provided, records are also
written as JSONL.

`excel_sheets` controls workbook handling in batch mode:

| Value | Behavior |
| --- | --- |
| `auto` | Let the adapter select the relevant sheet or sheet group. |
| `first` | Process only the first workbook sheet. |
| `all` | Process each workbook sheet independently. |
| `name` | Process the sheet passed with `sheet`; `sheet` is required. |

Archives are expanded into temporary storage. Supported archive suffixes are
`.zip`, `.tar`, `.tar.gz`, and `.tgz`.

## Intake Audit

### `doctor`

```python
report = bds.doctor("raw_export.csv", cycler="auto")
```

Returns `DoctorReport` for one file without writing converted data. The report
focuses on troubleshooting: data kind, adapter candidates, selected adapter,
missing required columns, validation issues, warnings, unmapped columns,
suspicious headers, suggested next steps, and the minimum anonymized fixture
checklist.

The equivalent CLI is:

```bash
bds doctor raw_export.csv
bds doctor raw_export.csv --json
```

### `explain`

```python
report = bds.explain(
    "raw_export.csv",
    cycler="auto",
    current_sign="preserve",
    repair_policy="warn",
)
```

Returns `ExplainReport` for one file without writing converted data. The report
includes data-kind detection, adapter candidates, selected adapter, confidence,
sheet, source columns, canonical/export column mapping, unit transforms,
current-sign evidence, repair policy, validation issues, warnings, unmapped
columns, and a recommended next action.

The equivalent CLI is:

```bash
bds explain raw_export.csv --text
bds explain raw_export.csv --json report.json --html report.html --xlsx report.xlsx
```

Python callers can write the same formatted diagnostic reports:

```python
bds.write_explain_reports(report, "reports", formats=("json", "html", "xlsx"))
```

PDF output is also supported.

### `audit`

```python
from battery_data_standard.audit import audit

report = audit(
    "raw_exports",
    recursive=True,
    json_path="audit.json",
    html_path="audit.html",
)
```

Audits raw files without writing converted data outputs. The report includes
file-level status, data kind, cycler, detection confidence, quality score,
quality grade, missing required columns, unit conversions, repair operations,
current-sign evidence, duplicate timestamps, non-monotonic time, suspicious flat
voltage/current checks, cycle/step anomaly checks, and errors.

Directory audit skips obvious helper files such as README files, manifests,
metadata/report sidecars, labels, summaries, and procedure files. Optional
columns are reported under `completeness`; missing optional columns are not
quality-score penalties.

The equivalent CLI is:

```bash
bds audit raw_exports --recursive --json audit.json --html audit.html
```

### `audit_file`

```python
from battery_data_standard.audit import audit_file

record = audit_file("raw_export.csv")
```

Returns one `AuditRecord` for a single file.

## Detection and Metadata

### `detect`

```python
detect(path)
```

Returns `DetectionResult` with the selected cycler, confidence score, reason,
candidate list, and path.

### `detect_kind`

```python
detect_kind(path, sheet=None)
```

Returns `DataKindResult` for operational routing. Possible kinds include
`timeseries`, `eis`, `unsupported`, and `unknown`.

### `list_supported_formats`

```python
list_supported_formats()
```

Returns adapter metadata including cycler id, display name, support tier,
evidence tier, extensions, unsupported extensions, and adapter version.

### `group_neware_files`

```python
group_neware_files(paths)
```

Groups NEWARE record exports by file content when a single test is split across
multiple files.

### `convert_neware_groups`

```python
convert_neware_groups(paths, output_dir, ...)
```

Converts grouped NEWARE record exports into one output per grouped test.

## Validation

### `validate`

```python
validate(dataframe, schema_version=..., strict=True)
```

Validates an in-memory normalized dataframe and returns `ValidationReport`.

### `validate_file`

```python
from battery_data_standard.api import validate_file

validate_file(path, schema_version=..., strict=True)
```

Validates an existing normalized CSV, Excel, or Parquet file on disk. This helper
is available from `battery_data_standard.api`.

## Reports

### `ConversionReport`

`ConversionReport` includes:

- `input_path` and `output_path`;
- `cycler`, `adapter_version`, `support_tier`, `evidence_tier`, and `detection_confidence`;
- `schema_version`, `rows`, and `columns`;
- `validation`, a `ValidationReport`;
- `warnings`, `provenance`, and `metadata`;
- source details such as `encoding`, `delimiter`, `header_row`, `sheet_name`,
  and `raw_rows`;
- `repair_operations` and `unmapped_columns`;
- `current_sign`.

Time-sampling findings are stored in `metadata["time_sampling"]` when the
time-series path is used. The record includes policy, expected interval,
interval confidence, missing sample count, gap locations, interpolation method,
and inserted row count when repair is applied.

Current-sign and step/cycle sanity findings are stored in
`metadata["current_sign_sanity"]`, `metadata["current_sign_confidence"]`,
`metadata["semantic_sources"]`, and `metadata["step_cycle_semantics"]`.
Temperature semantic findings are stored in `metadata["temperature_semantics"]`
and `metadata["temperature_semantics_confidence"]`. These
records are conservative diagnostics; they warn about trust-affecting ambiguity
but do not automatically change scientific semantics.

### `ValidationReport`

`ValidationReport` includes:

- `valid`;
- `schema_version`;
- `rows`;
- `columns`;
- `issues`.

Each issue includes `level`, `code`, `message`, and an optional `column`.
Production pipelines should branch on `valid` and issue `code` values rather
than parsing free-text messages.

### `DetectionResult`

`DetectionResult` includes:

- `cycler`;
- `confidence`;
- `reason`;
- `candidates`;
- `path`.

### `ExplainReport`

`ExplainReport` includes:

- `status`;
- `data_kind`;
- `detection`;
- `selected_adapter` and `confidence`;
- `sheet`;
- `source_columns`, `canonical_columns`, and `export_columns`;
- `column_mapping` and `unit_transforms`;
- `current_sign` and `current_sign_evidence`;
- `repair_policy`;
- `validation`, `warnings`, `unmapped_columns`, and `time_sampling`;
- `recommended_next_action`;
- `error_type` and `error` when diagnostics cannot complete conversion.

## Batch Records

`batch_convert()` and `bds batch` use these record semantics:

| Status | Record type | Meaning |
| --- | --- | --- |
| `ok` | `converted` | A time-series or EIS file was converted. |
| `unsupported` | `skipped` | The file was identified as unsupported or non-raw helper content. |
| `error` | `error` | Conversion was attempted and failed. |

Common fields include:

| Field | Meaning |
| --- | --- |
| `input_path` | Path used by the converter. For archive members this is the temporary extracted path. |
| `output_path` | Written output path for converted records; `null` for skipped records. |
| `archive_path` | Source archive path when the record came from an archive. |
| `archive_member` | Original member name inside an archive. |
| `sheet_name` | Workbook sheet used for the record, or `null`. |
| `data_kind` | Detected operational kind. |
| `kind_confidence` | Confidence score from `detect_kind()`. |
| `kind_reason` | Human-readable reason from `detect_kind()`. |
| `record_type` | `converted`, `skipped`, or `error`. |

Converted time-series records include serialized `ConversionReport` fields. EIS records
include validation details, row count, and columns. Skipped records include
`skip_reason`. Error records include `error_type` and `error`.

## Exceptions

Public API callers should catch `BatteryDataStandardError` or one of its
subclasses:

- `DetectionError`
- `AmbiguousDetectionError`
- `UnsupportedFormatError`
- `UnsupportedFeatureError`
- `ConversionError`
- `FileIOError`
- `ValidationFailed`

`ValidationFailed` carries the validation report that caused strict validation to
fail.
