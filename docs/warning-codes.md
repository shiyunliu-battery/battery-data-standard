# Warning and Issue Codes

BDS reports are machine-readable. Production pipelines should branch on
`valid`, `status`, and issue `code` values rather than parsing message text.

## Validation Codes

Common validation issue codes include:

| Code | Meaning | Typical action |
| --- | --- | --- |
| `missing-required-column` | A required BDS column is absent. | Check column aliases, use a profile, or file an adapter issue. |
| `null-required-values` | A required column contains nulls. | Inspect the source rows and repair policy. |
| `non-numeric-required` | A required numeric column has non-numeric values. | Check header-row detection and decimal formatting. |
| `non-finite-required` | A required numeric column contains NaN or infinity. | Remove or repair invalid rows before analysis. |
| `non-increasing-test-time` | `test_time_s` is not strictly increasing. | Use `repair_policy="repair"` only if shifting or sorting is scientifically acceptable. |
| `missing-sample-timepoints` | A regular `test_time_s` grid has one or more missing sample points. | Review `metadata["time_sampling"]`; use `time_sampling_policy="warn"` to avoid interpolation or set the expected interval explicitly. |
| `missing-optional-column` | Optional metadata or measurement columns are absent. | Informational for audits; not a quality-score penalty. |
| `unsupported-schema-version` | The requested schema is not supported by this release. | Pin a compatible package version or update the pipeline. |

## Audit Codes

Audit records may include additional issue codes:

| Code | Meaning |
| --- | --- |
| `duplicated-timestamps` | Duplicate elapsed-time values were detected. |
| `non-monotonic-time` | One or more elapsed-time transitions moved backward or stayed flat. |
| `suspicious-flat-voltage` | Voltage appears flat across enough points to be suspicious. |
| `suspicious-flat-current` | Current appears flat across enough points to be suspicious. |
| `cycle-anomalies` | Cycle index has decreases or negative values. |
| `step-anomalies` | Step index has decreases or negative values. |
| `conversion-error` | Conversion failed during audit. |
| `unsupported-file` | The file was identified as helper content or unsupported data. |

Optional-column coverage is exposed as `record.completeness` in audit JSON and
HTML reports. It is useful for dataset profiling, but it does not mean a valid
minimal file is poor quality.
