# Step and Cycle Semantics

Step and cycle fields are more than column names. Different cycler exports may
use the same words for different concepts, or reuse step numbers inside each
cycle.

## BDS Fields

| Canonical field | Export label | Meaning |
| --- | --- | --- |
| `cycle_index` | `Cycle Count` | Source cycle identifier or count when available. |
| `step_index` | `Step Index` | Source step identifier/count from the procedure when available. |
| `record_index` | `Record Index` | Source record/data-point index, or generated row order. |
| `step_time_s` | `Step Time (s)` | Elapsed time within the active step. |
| `test_time_s` | `Test Time (s)` | Elapsed time from the start of the full test. |

The legacy `target=bdf` export uses slash-unit column names and maps
`record_index` to `Step Index / 1` for older compatibility. Prefer the default
`bds` target for new public handoff unless an integration explicitly requires
the legacy BDF-style shape.

## Ambiguity

BDS preserves source step and cycle values when they are present. When a source
file does not contain whole-test time, BDS may reconstruct `test_time_s` from
step time under the selected repair policy and reports that operation in
warnings/provenance.

Use `bds explain` or conversion reports to check whether step/cycle fields came
from source columns, were joined from context sheets, or were absent. Use
`bds.summarize_steps(df)` and `bds.summarize_cycles(df)` for quick sanity checks
after reading a file.

## Audit Checks

Audit reports flag decreasing or negative cycle/step values. These warnings do
not prove the file is wrong; they point to cases that need procedure-aware
review before downstream aggregation.
