# Schema Compatibility

The package exports the active schema identifier as `BDS_SCHEMA_VERSION`.

```python
import bds

print(bds.BDS_SCHEMA_VERSION)
```

The current schema identifier is also included in every `ConversionReport`.
`BDF_SCHEMA_VERSION` remains available as a legacy compatibility constant for
older integrations.

## Compatibility Policy

During the pre-1.0 beta period:

- schema columns may change between minor releases;
- conversion reports include the schema version used for each output;
- downstream pipelines should pin package versions;
- release candidates should be validated against representative source exports
  before production rollout;
- breaking schema changes should be documented in `CHANGELOG.md`.

## Required BDS Export Columns

Default BDS time-series exports require:

| Column | Unit | Meaning |
| --- | --- | --- |
| `Test Time (s)` | s | Elapsed test time. |
| `Voltage (V)` | V | Instantaneous voltage. |
| `Current (A)` | A | Instantaneous current. |

Optional BDS export columns include absolute time, cycle count, step count, step
time, capacity, energy, temperature, power, and internal resistance.

## Export Labels

Written CSV and Parquet outputs use user-facing labels such as `Test Time (s)`.
Lower-level adapter labels are treated as implementation details.

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
