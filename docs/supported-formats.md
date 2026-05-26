# Supported Formats

Support tiers describe project validation scope. They do not imply vendor
certification, complete coverage of every export option, or compatibility with
all historical cycler software versions.

## Adapter Matrix

| Cycler id | Display name | Input suffixes | Unsupported suffixes | Support tier | Scope |
| --- | --- | --- | --- | --- | --- |
| `neware` | NEWARE | `.csv`, `.txt`, `.tsv`, `.xlsx`, `.xls`, `.mat`, `.parquet` | none declared | `fixture-backed` | Common NEWARE tabular exports, including flat files and workbook-style data where columns can be mapped to BDF time-series fields. |
| `arbin` | Arbin | `.csv`, `.txt`, `.tsv`, `.xlsx`, `.xls`, `.mat`, `.parquet` | none declared | `fixture-backed` | Common Arbin tabular exports and charge-positive current convention handling. |
| `maccor` | Maccor | `.csv`, `.txt`, `.tsv`, `.xlsx`, `.xls`, `.mat`, `.parquet` | none declared | `fixture-backed` | Common Maccor tabular exports, including files with metadata preambles. |
| `biologic` | BioLogic | `.mpt`, `.txt`, `.csv` | `.mpr` | `fixture-backed` | EC-Lab text exports. Binary `.mpr` files are not supported. |
| `novonix` | Novonix | `.csv`, `.txt`, `.tsv`, `.xlsx`, `.xls`, `.mat`, `.parquet` | none declared | `fixture-backed` | Common Novonix tabular exports. |
| `basytec` | BaSyTec | `.csv`, `.txt`, `.tsv`, `.xlsx`, `.xls`, `.mat`, `.parquet` | none declared | `fixture-backed` | Common BaSyTec tabular exports. |
| `landt` | LANDT | `.csv`, `.txt`, `.tsv`, `.xlsx`, `.xls`, `.mat`, `.parquet` | none declared | `fixture-backed` | Common LANDT tabular exports. |
| `generic` | Generic CSV/Excel/MATLAB/Parquet | `.csv`, `.txt`, `.tsv`, `.xlsx`, `.xls`, `.mat`, `.parquet` | none declared | `fixture-backed` | Generic tabular data with recognizable or profile-mapped time, voltage, and current columns. |

The runtime source of truth is:

```bash
bds formats
```

or:

```python
import bds

formats = bds.list_supported_formats()
```

## Support-Tier Definitions

`fixture-backed` means the adapter has representative validation coverage for
the documented path. It does not guarantee that every regional export setting,
firmware version, delimiter, language, or workbook layout is supported.

`best_effort` is reserved for behavior that is implemented but not supported by
representative validation coverage.

## Generic Inputs

Generic conversion is appropriate when the input table contains time, voltage,
and current columns that can be recognized by built-in aliases or mapped with a
profile.

Supported generic families include:

- delimited text: `.csv`, `.txt`, `.tsv`;
- Excel workbooks: `.xlsx`, `.xls`;
- MATLAB files: `.mat`, with the `matlab` optional extra installed;
- Parquet files: `.parquet`.

## EIS Inputs

EIS routing is separate from BDF time-series conversion. Use `detect-kind`,
`convert-eis`, `read_eis()`, or `batch_convert()` for EIS files.

## Unsupported Inputs

Known unsupported inputs include:

- BioLogic `.mpr` binary files;
- helper files such as README files, labels, procedures, datasheets, and summary
  tables that do not contain raw time-series or EIS data;
- files without enough information to map time, voltage, and current columns.

Unsupported helper files are skipped in batch mode. Single-file conversion
commands report an error when conversion cannot be completed.
