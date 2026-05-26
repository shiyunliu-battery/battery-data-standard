# Export Template

CSV and Parquet exports use a consistent user-facing column template across
cycler adapters. Internal normalized data keeps canonical BDF-style labels such
as `Test Time / s`; exported files use labels with units in parentheses.

## Required Export Columns

The exported BDF time-series table requires:

| Column | Meaning |
| --- | --- |
| `Record Index` | Sequential source record index. If no source record index is available, it is generated from row order. |
| `Test Time (s)` | Elapsed test time in seconds. |
| `Voltage (V)` | Instantaneous voltage in volts. |
| `Current (A)` | Instantaneous current in amperes. |

## Preferred Column Order

When present, columns are written in this order:

1. `Record Index`
2. `Date Time`
3. `Test Time (s)`
4. `Voltage (V)`
5. `Current (A)`
6. `Cycle Count`
7. `Step Index`
8. `Step Time (s)`
9. `Power (W)`
10. `Charging Capacity (Ah)`
11. `Discharging Capacity (Ah)`
12. `Charging Energy (Wh)`
13. `Discharging Energy (Wh)`
14. `Step Type`

Additional adapter-specific or auxiliary columns are appended after the
preferred columns. Vendor prefixes are removed where possible, and slash-style
units are rewritten as parenthesized units.

## Internal-to-Export Mapping

| Internal canonical column | Export column |
| --- | --- |
| `Step Index / 1` | `Record Index` |
| `Date Time ISO` | `Date Time` |
| `Test Time / s` | `Test Time (s)` |
| `Voltage / V` | `Voltage (V)` |
| `Current / A` | `Current (A)` |
| `Cycle Count / 1` | `Cycle Count` |
| `Step Count / 1` | `Step Index` |
| `Step Time / s` | `Step Time (s)` |
| `Power / W` | `Power (W)` |
| `Charging Capacity / Ah` | `Charging Capacity (Ah)` |
| `Discharging Capacity / Ah` | `Discharging Capacity (Ah)` |
| `Charging Energy / Wh` | `Charging Energy (Wh)` |
| `Discharging Energy / Wh` | `Discharging Energy (Wh)` |
| `NEWARE Step Type` | `Step Type` |

`Unix Time / s` is retained only in the internal normalized dataframe and report
metadata. It is not written to the user-facing export table.

## Time Semantics

`Date Time` is the absolute sample timestamp when the source file provides one,
or when an adapter can derive it from a source start timestamp and elapsed test
time. If the source file does not include timezone information, the timestamp is
preserved as local or unspecified time; the package does not assert UTC.

`Test Time (s)` is elapsed time from the start of the full test.

`Step Time (s)` is elapsed time within the active step.

## Validation

Use:

```bash
bds validate normalized.bdf.csv
```

or:

```python
from battery_data_standard.api import validate_file

report = validate_file("normalized.bdf.csv")
```

Export validation accepts the user-facing export labels. Internal dataframe
validation uses canonical BDF-style labels.
