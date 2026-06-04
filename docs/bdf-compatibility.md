# BDF Compatibility Status

BDS supports a `target=bdf` export preset for legacy BDF-style column names:

```bash
bds convert raw_export.csv normalized.bdf.csv --target bdf
```

This target writes slash-unit labels such as:

- `Test Time / s`;
- `Voltage / V`;
- `Current / A`;
- `Cycle Count / 1`;
- `Step Count / 1`.

## Important Boundary

`target=bdf` is a column-shape compatibility preset, not a formal Battery Data
Format governance or conformance certification. Formal BDF conformance requires
an explicit conformance report and versioned policy that can track the Battery
Data Alliance specification as it evolves.

## Recommended Positioning

Use BDS as the first-mile converter and QA layer:

1. Read messy vendor files locally.
2. Validate required time-series fields.
3. Preserve provenance, unit transforms, current-sign evidence, and warnings.
4. Export a BDS table, downstream staging table, or legacy BDF-style table.

When BDF compatibility matters, keep the conversion report with the data file so
downstream users can see exactly which fields were mapped, inferred, repaired,
or absent.
