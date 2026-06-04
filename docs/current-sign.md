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

## Recommended Practice

For new file families, run:

```bash
bds explain raw_export.csv --current-sign preserve --text
```

Then compare current direction with the source software, voltage trend, and
charge/discharge capacity columns. If the source uses an unusual convention,
record that in the fixture manifest or conversion metadata.
