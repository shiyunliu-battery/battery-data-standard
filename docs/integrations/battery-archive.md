# battery-data-standard + Battery Archive

## Question

I already have raw cycler files. How do I use BDS to prepare a clean package for
Battery Archive-style sharing?

## Use This When

Use this path when the goal is to publish or exchange raw cycler data together
with normalized, schema-checked tables and enough provenance for another lab to
reproduce the conversion.

BDS should not replace the repository's submission rules. Treat this recipe as a
local packaging checklist before upload.

## Convert A Directory

```bash
bds batch raw_exports battery_archive_ready \
  --recursive \
  --target battery-archive \
  --format parquet \
  --manifest battery_archive_manifest.jsonl \
  --current-sign preserve \
  --repair-policy repair
```

This creates:

- time-series Parquet files for raw cycling data;
- EIS Parquet files for impedance data detected by `detect-kind`;
- skipped records for helper files;
- error records for files that need a new fixture or profile.

## Suggested Package Layout

```text
dataset/
  raw/
    original_cycler_exports/
  normalized/
    cell_001.battery-archive.parquet
    cell_002.battery-archive.parquet
    cell_001_eis.eis.parquet
  reports/
    cell_001.conversion-report.json
    cell_002.conversion-report.json
  battery_archive_manifest.jsonl
  metadata.json
  README.md
```

Keep raw files and normalized files together. The normalized files are for
search, reuse, and analysis. The raw files are the provenance anchor.

## Minimal Metadata Sidecar

```json
{
  "dataset_title": "Example cycling dataset",
  "source": "raw cycler exports converted with battery-data-standard",
  "bds_version": "record from conversion report",
  "current_sign": "preserve",
  "files": [
    {
      "raw_path": "raw/original_cycler_exports/cell_001.mpt",
      "normalized_path": "normalized/cell_001.battery-archive.parquet",
      "report_path": "reports/cell_001.conversion-report.json",
      "cell_id": "cell_001",
      "cycler": "biologic"
    }
  ]
}
```

## Validate Before Sharing

```bash
bds validate normalized/cell_001.battery-archive.parquet
bds validate-eis normalized/cell_001_eis.eis.parquet
```

## Compatibility Table Entry

When the package exposes a new edge case, add a local compatibility note:

| Field | Example |
| --- | --- |
| Cycler | BioLogic |
| Software version | EC-Lab version if known |
| Export setting | `.mpt`, `.mpr`, `.csv`, workbook, etc. |
| BDS adapter | `biologic` |
| Result | passed, repaired, skipped, or error |
| Fixture path | `fixtures/community/biologic/example_name` |

## Known Limits

- Repository metadata requirements can be stricter than BDS metadata.
- Do not publish sensitive operator names, sample IDs, or proprietary protocols
  without redaction.
- If a file requires a new adapter rule, add a minimal fixture before publishing
  the normalized output as authoritative.
