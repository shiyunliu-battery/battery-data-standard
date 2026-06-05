# Supported Formats

Support tiers describe project validation scope. They do not imply vendor
certification, complete coverage of every export option, or compatibility with
all historical cycler software versions.

## Adapter Matrix

| Cycler id | Display name | Input suffixes | Unsupported suffixes | Support tier | Evidence tier | Scope |
| --- | --- | --- | --- | --- | --- | --- |
| `neware` | NEWARE | `.csv`, `.txt`, `.tsv`, `.xlsx`, `.xls`, `.mat`, `.parquet` | none declared | `fixture-backed` | `public-fixture-backed` | Common NEWARE tabular exports, including flat files and workbook-style data where columns can be mapped to canonical time-series fields. |
| `arbin` | Arbin | `.csv`, `.txt`, `.tsv`, `.xlsx`, `.xls`, `.mat`, `.parquet` | none declared | `fixture-backed` | `public-fixture-backed` | Common Arbin tabular exports and charge-positive current convention handling. |
| `maccor` | Maccor | `.csv`, `.txt`, `.tsv`, `.xlsx`, `.xls`, `.mat`, `.parquet` | none declared | `fixture-backed` | `public-fixture-backed` | Common Maccor tabular exports, including files with metadata preambles. |
| `biologic` | BioLogic | `.mpt`, `.mpr`, `.txt`, `.csv` | none declared | `fixture-backed` | `public-fixture-backed` | EC-Lab text exports plus binary `.mpr` through the optional `mpr` extra (`galvani`). |
| `repower` | Repower | `.csv`, `.txt` | none declared | `fixture-backed` | `public-fixture-backed` | Repower CSV-style exports with `Relative Time`, `Voltage(V)`, `Current(A)`, cycle, step, and status columns. |
| `pec` | PEC | `.csv`, `.txt` | none declared | `fixture-backed` | `public-fixture-backed` | PEC CSV-style exports with total/step time, voltage/current, cycle/step, capacity, energy, and resistance columns. |
| `novonix` | Novonix | `.csv`, `.txt`, `.tsv`, `.xlsx`, `.xls`, `.mat`, `.parquet` | none declared | `fixture-backed` | `public-fixture-backed` | Common Novonix tabular exports. |
| `basytec` | BaSyTec | `.csv`, `.txt`, `.tsv`, `.xlsx`, `.xls`, `.mat`, `.parquet` | none declared | `fixture-backed` | `public-fixture-backed` | Common BaSyTec tabular exports. |
| `landt` | LANDT | `.csv`, `.txt`, `.tsv`, `.xlsx`, `.xls`, `.mat`, `.parquet` | none declared | `fixture-backed` | `public-fixture-backed` | Common LANDT tabular exports. |
| `generic` | Generic CSV/Excel/MATLAB/Parquet | `.csv`, `.txt`, `.tsv`, `.xlsx`, `.xls`, `.mat`, `.parquet` | none declared | `fixture-backed` | `unit-test-backed` | Generic tabular data with recognizable or profile-mapped time, voltage, and current columns. |

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

`support_tier` describes the support promise. `fixture-backed` means the adapter
has representative validation coverage for the documented path. It does not
guarantee that every regional export setting, firmware version, delimiter,
language, or workbook layout is supported.

`evidence_tier` describes the public proof behind that promise. Public fixture
coverage means a reduced, anonymized source file is stored under
`tests/fixtures/<cycler>` with a manifest that exercises detection, conversion,
and validation. This is stronger evidence than an inline unit test that builds a
temporary file during test execution, because users can inspect the exact headers
and minimal raw file shape used for regression coverage.

`unit-test-backed` means behavior is covered by tests but not by an inspectable
public fixture file. `best-effort` means behavior is implemented without a
dedicated regression evidence tier.

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

EIS routing is separate from time-series conversion. Use `detect-kind`,
`convert-eis`, `read_eis()`, or `batch_convert()` for EIS files.

Supported EIS input families include CSV/Excel impedance tables and Gamry
`.DTA` files containing a `ZCURVE` table.

## Unsupported Inputs

Known unsupported inputs include:

- helper files such as README files, labels, procedures, datasheets, and summary
  tables that do not contain raw time-series or EIS data;
- files without enough information to map time, voltage, and current columns.

Unsupported helper files are skipped in batch mode. Single-file conversion
commands report an error when conversion cannot be completed.
