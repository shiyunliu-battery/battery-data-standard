# battery-data-standard + PyBaMM

## Question

I already have raw cycler files. How do I use BDS to create data that PyBaMM can
use for model comparison or current-profile simulations?

## Use This When

Use this path when you want a measured current, voltage, or temperature profile
from a cycler export to drive or compare against a PyBaMM model.

## Convert Raw Files

For a reusable file:

```bash
bds convert raw.mpt pybamm_drive_cycle.csv --target pybamm --current-sign discharge-positive
```

For Python-only work, read the target export directly:

```python
import polars as pl

profile = pl.read_csv("pybamm_drive_cycle.csv")
time_s = profile["time_s"].to_numpy()
current_a = profile["current_a"].to_numpy()
```

## Extract A PyBaMM Input Profile

```python
import numpy as np
import polars as pl

profile = pl.read_csv("pybamm_drive_cycle.csv").drop_nulls().sort("time_s")

time_s = np.asarray(profile["time_s"].to_list(), dtype=float)
current_a = np.asarray(profile["current_a"].to_list(), dtype=float)
```

`time_s` and `current_a` are the typical handoff arrays for a PyBaMM current
input function. For measured-voltage comparison, also write the default BDS
export and read the `Voltage (V)` column.

## Example Current Interpolant

```python
import pybamm

model = pybamm.lithium_ion.SPM()
parameter_values = model.default_parameter_values

current = pybamm.Interpolant(time_s, current_a, pybamm.t)
parameter_values.update({"Current function [A]": current})

simulation = pybamm.Simulation(model, parameter_values=parameter_values)
solution = simulation.solve([float(time_s[0]), float(time_s[-1])])
```

Check the current sign convention for the specific model and experiment setup.
Use `current_sign="preserve"` when inspecting data so the source sign is
explicit before any model-specific sign adjustment.

## Export A Compact Profile

```python
profile.write_csv("pybamm_current_profile.csv")
```

## Known Limits

- BDS does not infer electrochemical model parameters.
- Raw cycling data often includes rests, pulses, and protection steps; decide
  whether to use the whole profile or a selected step/cycle before fitting.
- Temperature and EIS outputs can be exported separately, but this recipe is for
  current/voltage time-series handoff.
