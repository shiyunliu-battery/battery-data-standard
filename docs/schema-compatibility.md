# Schema Compatibility

The package exports the active schema identifier as `BDF_SCHEMA_VERSION`.

```python
import bds

print(bds.BDF_SCHEMA_VERSION)
```

The current schema identifier is also included in every `ConversionReport`.

## Compatibility Policy

During the pre-1.0 beta period:

- schema columns may change between minor releases;
- conversion reports include the schema version used for each output;
- downstream pipelines should pin package versions;
- release candidates should be validated against representative source exports
  before production rollout;
- breaking schema changes should be documented in `CHANGELOG.md`.

## Required Canonical Columns

BDF time-series data requires:

| Column | Unit | Meaning |
| --- | --- | --- |
| `Test Time / s` | s | Elapsed test time. |
| `Voltage / V` | V | Instantaneous voltage. |
| `Current / A` | A | Instantaneous current. |

Optional canonical columns include absolute time, cycle count, step count, step
time, capacity, energy, temperature, power, and internal resistance.

## Export Labels

Internal normalized data uses canonical labels such as `Test Time / s`. Written
CSV and Parquet outputs use user-facing labels such as `Test Time (s)`.

See [export-template.md](export-template.md) for the export column order and
mapping.

## Validation Issue Codes

Validation reports are machine-readable. Each issue contains:

- `level`: `error` or `warning`;
- `code`: issue identifier within the release line;
- `message`: human-readable description;
- `column`: affected canonical or export column when applicable.

Production systems should branch on `valid` and issue `code` values rather than
parsing free-text messages.
