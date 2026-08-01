# BDF Compatibility

BDS exports to the Battery Data Format (BDF), the open standard published by
the Battery Data Alliance:

```bash
bds convert raw_export.csv normalized.bdf.csv --target bdf
```

This writes BDF preferred labels (`Test Time / s`, `Voltage / V`,
`Current / A`, `Cycle Count / 1`, `Step Count / 1`).

## Scope

`--target bdf` aligns column labels and units with the BDF table schema. It
does not emit ontology bindings, JSON-LD/CSVW metadata, or a conformance
report, so this output is BDF-aligned rather than BDF-conformant. Where BDS
and the BDA specification differ, the specification is authoritative.
