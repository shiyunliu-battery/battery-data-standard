# battery-data-standard + cellpy

## Question

I already have raw cycler files. How do I use BDS to create data that can be
staged for cellpy workflows?

## Use This When

Use this path when BDS can read a raw cycler export and you want a stable,
unit-normalized table before moving data into a cellpy project.

BDS is not a replacement for cellpy's native instrument loaders. The practical
integration is to use BDS as a pre-normalization step and then write a
cellpy-like staging CSV with the columns a cellpy loader or local import script
can map.

## Convert Raw Files

```bash
bds convert raw.mpt cellpy_staging.csv --target cellpy --current-sign preserve --repair-policy repair
```

## Create A cellpy-Like Staging CSV

```python
import polars as pl

cellpy_like = pl.read_csv("cellpy_staging.csv")
```

If your source file does not contain every optional capacity or energy column,
the target export omits those optional columns. Add null columns in your local
import script only if your cellpy workflow requires them.

## Suggested Mapping

| BDS export column | cellpy-like staging column |
| --- | --- |
| `Record Index` | `data_point` |
| `Date Time` | `datetime` |
| `Test Time (s)` | `test_time` |
| `Step Time (s)` | `step_time` |
| `Cycle Count` | `cycle_index` |
| `Step Index` | `step_index` |
| `Current (A)` | `current` |
| `Voltage (V)` | `voltage` |
| `Charging Capacity (Ah)` | `charge_capacity` |
| `Discharging Capacity (Ah)` | `discharge_capacity` |
| `Charging Energy (Wh)` | `charge_energy` |
| `Discharging Energy (Wh)` | `discharge_energy` |

## Keep The Raw File

Keep the original raw file and the BDS conversion report alongside
`cellpy_staging.csv`. The report records which adapter was used, what columns
were mapped, and what repairs were applied.

## Known Limits

- This page describes a staging table, not a guaranteed native `.h5` cellpy
  file writer.
- A production cellpy workflow should still define a local loader or import
  function that maps the staging columns into the exact cellpy version used by
  the lab.
- Capacity sign conventions should be checked against the downstream cellpy
  workflow before fitting or reporting capacities.
