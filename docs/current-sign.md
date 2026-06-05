# Current Sign Convention

The default BDS convention is charge-positive and discharge-negative current.

```bash
bds convert raw_export.csv normalized.bds.csv --current-sign charge-positive
```

Use `--current-sign preserve` when downstream analysis should retain the source
instrument convention exactly:

```bash
bds convert raw_export.csv normalized.bds.csv --current-sign preserve
```

Use `--current-sign discharge-positive` when a downstream workflow expects
discharge-positive current.

## Evidence In Reports

Conversion reports and `bds explain` include the requested `current_sign` and
provenance entries for current mapping. Audit records add
`current_sign_evidence`, for example:

- current sign normalized from a status column;
- current sign flipped from a known adapter convention;
- raw current mapped without explicit charge/discharge sign evidence.

The last case is not automatically wrong. It means BDS did not find a source
status column or adapter-level sign convention strong enough to explain the sign
semantics. Review voltage, capacity, and procedure context before trusting
scientific conclusions that depend on sign.

## Adjacent-Point Sanity Check

When requested, BDS can run a conservative adjacent-point sanity check while
`current_sign` is `charge-positive` or `discharge-positive`. The check compares
each usable neighboring row pair, such as 1 s to 2 s, and asks whether voltage
movement agrees with the current direction. Pairs are used only when both rows
have the same non-rest current direction, so step and pulse transition edges are
less likely to dominate the result.

This check is O(n) in the number of rows and writes
`metadata["current_sign_sanity"]` plus `metadata["current_sign_confidence"]`.
It is a warning-only diagnostic and never flips current values. It is disabled by
default to avoid extra cost on large files. Enable it with:

```bash
bds audit raw_export.csv --current-sign-check adjacent
bds convert raw_export.csv normalized.bds.csv --current-sign-check adjacent
```

## Recommended Practice

For new file families, run:

```bash
bds explain raw_export.csv --current-sign preserve --text
```

Then compare current direction with the source software, voltage trend, and
charge/discharge capacity columns. If the source uses an unusual convention,
record that in the fixture manifest or conversion metadata.
