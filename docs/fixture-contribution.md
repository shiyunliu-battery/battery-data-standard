# Fixture Contribution Guide

Reduced fixtures help BDS support real cycler exports without asking users to
share full private experiments. A good fixture is the smallest file that still
reproduces detection, parsing, unit conversion, current-sign, or validation
behavior.

## What To Keep

- Keep the original header rows, units, delimiter, worksheet name, and encoding
  whenever possible.
- Keep the columns needed to reproduce the problem, especially time, voltage,
  current, status/step type, cycle, step, capacity, energy, temperature, and
  any vendor-specific metadata rows that affect parsing.
- Keep enough rows to show the behavior. Five to twenty rows is often enough;
  use more only when the bug depends on a repeated cycle, a step transition, or
  a sampling gap.
- If the current sign is important, keep at least one charge row and one
  discharge row, plus the source status column if it exists.

## What To Remove

- Remove or replace cell IDs, customer names, project names, operator names,
  sample names, serial numbers, barcodes, file paths, and comments that reveal
  confidential work.
- Remove long procedure descriptions unless the parser needs those rows to find
  the data table.
- Remove most measurement rows after confirming the reduced file still fails or
  still demonstrates the requested mapping.
- Replace proprietary values with simple representative values only when doing
  so does not change units, signs, headers, step transitions, or parser behavior.

## How To Submit

1. Run `bds explain <file> --text` on the reduced file.
2. Confirm the reduced file still shows the same detection, conversion, or
   validation behavior as the original.
3. Open a cycler import issue and paste the `bds explain` output.
4. Attach the reduced file if policy allows it.
5. State clearly whether the file may be added to public regression tests under
   `tests/fixtures`.

If the file cannot be shared publicly, include the header row, cycler model,
software/export version, sheet name, current sign convention, and a short
description of the expected columns.
