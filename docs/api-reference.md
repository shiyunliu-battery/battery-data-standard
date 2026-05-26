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
    detection_threshold=0.1,
    sheet=None,
)
```

Reads a supported cycler export into a normalized BDF-style Polars dataframe.

Use `cycler="auto"` or `cycler=None` for automatic detection. Use an explicit
cycler id such as `neware`, `arbin`, `maccor`, `biologic`, `novonix`,
`basytec`, `landt`, or `generic` when the source system is known.

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
    detection_threshold=0.1,
    report_path=None,
    write_sidecars=False,
    sheet=None,
)
```

Converts a supported time-series export and writes CSV or Parquet output. The
function returns `ConversionReport`.

`format` must be `csv` or `parquet`. If `report_path` is provided, the conversion
report is written as JSON. If `write_sidecars=True`, report and metadata
sidecars are written next to the output.

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
    detection_threshold=0.1,
    write_sidecars=False,
    sheet=None,
    excel_sheets="auto",
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
`bdf-timeseries`, `eis`, `unsupported`, and `unknown`.

### `list_supported_formats`

```python
list_supported_formats()
```

Returns adapter metadata including cycler id, display name, support tier,
extensions, unsupported extensions, and adapter version.

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

Validates an in-memory BDF-style dataframe and returns `ValidationReport`.

### `validate_file`

```python
from battery_data_standard.api import validate_file

validate_file(path, schema_version=..., strict=True)
```

Validates an existing BDF-style CSV, Excel, or Parquet file on disk. This helper
is available from `battery_data_standard.api`.

## Reports

### `ConversionReport`

`ConversionReport` includes:

- `input_path` and `output_path`;
- `cycler`, `adapter_version`, `support_tier`, and `detection_confidence`;
- `schema_version`, `rows`, and `columns`;
- `validation`, a `ValidationReport`;
- `warnings`, `provenance`, and `metadata`;
- source details such as `encoding`, `delimiter`, `header_row`, `sheet_name`,
  and `raw_rows`;
- `repair_operations` and `unmapped_columns`;
- `current_sign`.

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

## Batch Records

`batch_convert()` and `bds batch` use these record semantics:

| Status | Record type | Meaning |
| --- | --- | --- |
| `ok` | `converted` | A BDF time-series or EIS file was converted. |
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

Converted BDF records include serialized `ConversionReport` fields. EIS records
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
