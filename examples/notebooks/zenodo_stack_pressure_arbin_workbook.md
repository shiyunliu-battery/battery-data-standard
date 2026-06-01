# Zenodo Stack-Pressure Arbin Workbook

Convert one Arbin Excel workbook to BDS exports and downstream staging files.

Data: Schommer, A., Orozco Corzo, M., & Paul, H. (2024). *Dataset: Stack pressure on lithium-ion pouch cells: a comparative study of constant pressure and fixed displacement devices* [Data set]. Zenodo. https://doi.org/10.5281/zenodo.13755167

Setup:

```bash
py -m pip install -e .
```

## 1. Locate File

Place `240805_MBTF_DYNAMIC_SPRINGS_01_Channel_1_Wb_1.xlsx` under either `examples/data/` or `tests/`.

```python
from __future__ import annotations

from pathlib import Path
import sys

current = Path.cwd().resolve()
repo_root = current
for candidate in [current, *current.parents]:
    if (candidate / "pyproject.toml").exists() and (candidate / "src").exists():
        repo_root = candidate
        break

src_path = repo_root / "src"
if src_path.exists() and str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

candidates = [
    repo_root / "examples" / "data" / "240805_MBTF_DYNAMIC_SPRINGS_01_Channel_1_Wb_1.xlsx",
    repo_root / "tests" / "240805_MBTF_DYNAMIC_SPRINGS_01_Channel_1_Wb_1.xlsx",
]
data_path = next((path for path in candidates if path.exists()), None)
if data_path is None:
    raise FileNotFoundError("Place the workbook under examples/data/ or tests/.")

print("Workbook:", data_path.relative_to(repo_root).as_posix())
print("Size MB:", round(data_path.stat().st_size / 1_000_000, 2))
```

## 2. Detect

```python
import battery_data_standard as bds

kind = bds.detect_kind(data_path)
detection = bds.detect(data_path)

print("Kind:", kind.kind)
print("Reason:", kind.reason)
print("Adapter:", detection.cycler)
print("Confidence:", detection.confidence)
```

## 3. Read And Validate

```python
from battery_data_standard.export import to_export_frame

df, report = bds.read_with_report(
    data_path,
    cycler="auto",
    current_sign="preserve",
    repair_policy="warn",
)
bds_frame = to_export_frame(df, target="bds")

print("Schema:", report.schema_version)
print("Sheet:", report.sheet_name)
print("Rows:", df.height)
print("Valid:", report.validation.valid)
print("Warnings:", len(report.warnings))
print("Internal columns:", df.columns[:8])
print("BDS export columns:", bds_frame.columns[:8])
```

## 4. Numeric Checks

```python
checks = {
    "time_s_min": bds_frame["Test Time (s)"].min(),
    "time_s_max": bds_frame["Test Time (s)"].max(),
    "voltage_v_min": bds_frame["Voltage (V)"].min(),
    "voltage_v_max": bds_frame["Voltage (V)"].max(),
    "current_a_min": bds_frame["Current (A)"].min(),
    "current_a_max": bds_frame["Current (A)"].max(),
    "cycles": bds_frame["Cycle Count"].unique().sort().to_list(),
    "step_count": bds_frame["Step Index"].n_unique(),
}

for key, value in checks.items():
    print(f"{key}: {value}")
```

## 5. Write Exports

```python
output_dir = repo_root / "examples" / "output" / "zenodo_stack_pressure"
output_dir.mkdir(parents=True, exist_ok=True)

bds_output = output_dir / "240805_MBTF_DYNAMIC_SPRINGS_01_Channel_1_Wb_1.bds.csv"
pybamm_output = output_dir / "240805_MBTF_DYNAMIC_SPRINGS_01_Channel_1_Wb_1.pybamm.csv"

bds_report = bds.convert(
    data_path,
    bds_output,
    cycler="auto",
    current_sign="preserve",
    repair_policy="warn",
)
pybamm_report = bds.convert(
    data_path,
    pybamm_output,
    cycler="auto",
    current_sign="preserve",
    repair_policy="warn",
    target="pybamm",
)

print("BDS:", bds_output.relative_to(repo_root).as_posix())
print("BDS columns:", bds_report.columns[:8])
print("PyBaMM:", pybamm_output.relative_to(repo_root).as_posix())
print("PyBaMM columns:", pybamm_report.columns)
```

## 6. EIS Sheet

```python
eis_kind = bds.detect_kind(data_path, sheet="ACIM_chan_1")
eis = bds.read_eis(data_path, sheet="ACIM_chan_1")
eis_report = bds.validate_eis(eis)

print("Kind:", eis_kind.kind)
print("Rows:", eis.height)
print("Columns:", eis.columns[:7])
print("Valid:", eis_report.valid)
```

## 7. Export Target

```python
target_name = "pyprobe"
format_name = "parquet"
exercise_output = output_dir / f"exercise.{target_name}.{format_name}"

exercise_report = bds.convert(
    data_path,
    exercise_output,
    cycler="auto",
    current_sign="preserve",
    repair_policy="warn",
    target=target_name,
    format=format_name,
)

print("Target:", target_name)
print("Output:", exercise_output.relative_to(repo_root).as_posix())
print("Columns:", exercise_report.columns)
```
