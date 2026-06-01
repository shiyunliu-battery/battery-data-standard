# battery-data-standard + BEEP

## Question

I already have raw cycler files. How do I use BDS before a BEEP workflow?

## Use This When

Use this path when you want BDS to normalize or screen raw cycler exports before
they enter a BEEP structuring or feature-generation pipeline.

BEEP has its own supported raw-file formats and structuring logic. BDS should
not pretend to be a native BEEP replacement. The useful bridge is:

1. Let BDS detect, validate, and normalize messy raw files.
2. Use the BDS report to decide whether a file is safe for a BEEP pipeline.
3. For formats BEEP does not natively structure, write a BEEP-style staging CSV
   and a metadata sidecar for a small local BEEP adapter.

## Convert Raw Files

```bash
bds convert raw.mpt beep_staging.csv \
  --target beep \
  --current-sign preserve \
  --repair-policy repair \
  --report normalized.report.json
```

## Create A BEEP-Style Staging CSV

```python
import json
import polars as pl

beep_staging = pl.read_csv("beep_staging.csv")

metadata = {
    "source": "battery-data-standard",
    "bds_report": "normalized.report.json",
    "current_sign": "preserve",
    "units": {
        "test_time": "s",
        "voltage": "V",
        "current": "A",
        "charge_capacity": "Ah",
        "discharge_capacity": "Ah",
    },
}

with open("beep_staging.metadata.json", "w", encoding="utf-8") as handle:
    json.dump(metadata, handle, indent=2)
```

## Suggested Mapping

| BDS export column | BEEP-style staging column |
| --- | --- |
| `Test Time (s)` | `test_time` |
| `Voltage (V)` | `voltage` |
| `Current (A)` | `current` |
| `Cycle Count` | `cycle_index` |
| `Step Index` | `step_index` |
| `Step Time (s)` | `step_time` |
| `Charging Capacity (Ah)` | `charge_capacity` |
| `Discharging Capacity (Ah)` | `discharge_capacity` |

## Batch Screening Before BEEP

```bash
bds batch raw_exports bds_exports \
  --recursive \
  --target beep \
  --format parquet \
  --manifest bds_manifest.jsonl \
  --current-sign preserve \
  --repair-policy repair
```

Use `bds_manifest.jsonl` to separate:

- converted time-series files;
- EIS files, which should not be passed to a time-series BEEP pipeline;
- unsupported helper files;
- conversion errors that need a new fixture.

## Known Limits

- This page does not claim that BEEP can directly ingest every BDS export.
- When BEEP already supports a raw cycler file, prefer BEEP's native structuring
  path and use BDS as an independent validation/preflight step.
- For raw formats only BDS supports, keep the BDS staging CSV plus metadata and
  implement a small local BEEP adapter around that normalized table.
