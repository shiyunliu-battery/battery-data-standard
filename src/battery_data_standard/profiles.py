"""Profile loading and mapping helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .exceptions import UnsupportedFeatureError, UnsupportedFormatError
from .schema import ALL_COLUMNS, MACHINE_TO_LABEL

FIELD_TO_CANONICAL = {
    "test_time": "Test Time / s",
    "time": "Test Time / s",
    "date_time": "Date Time ISO",
    "date_time_iso": "Date Time ISO",
    "cycle_index": "Cycle Count / 1",
    "cycle": "Cycle Count / 1",
    "step_index": "Step Count / 1",
    "step": "Step Count / 1",
    "data_point": "Step Index / 1",
    "record": "Step Index / 1",
    "step_time": "Step Time / s",
    "voltage": "Voltage / V",
    "current": "Current / A",
    "temperature": "Ambient Temperature / degC",
    "internal_resistance": "Internal Resistance / ohm",
    "charge_capacity": "Charging Capacity / Ah",
    "discharge_capacity": "Discharging Capacity / Ah",
    "charge_energy": "Charging Energy / Wh",
    "discharge_energy": "Discharging Energy / Wh",
    "power": "Power / W",
}


def load_profile(profile: str | Path | dict[str, Any] | None) -> dict[str, Any]:
    if profile is None:
        return {}
    if isinstance(profile, dict):
        return profile
    path = Path(profile)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:
            raise UnsupportedFeatureError(
                "YAML profiles require the optional PyYAML dependency. "
                "Install with battery-data-standard[yaml]."
            ) from exc
        data = yaml.safe_load(text)
        return data or {}
    raise UnsupportedFormatError(f"Unsupported profile file extension: {path.suffix}")


def profile_column_map(profile: dict[str, Any]) -> dict[str, list[str]]:
    """Return a canonical-label -> raw-column candidates mapping."""
    if not profile:
        return {}

    raw = profile.get("columns") or profile.get("column_names") or profile
    if not isinstance(raw, dict):
        raise UnsupportedFormatError("Profile must be a mapping or contain a 'columns' mapping.")

    out: dict[str, list[str]] = {}
    for key, value in raw.items():
        canonical = _canonicalize_key(str(key))
        if canonical is None:
            continue
        values = value if isinstance(value, list) else [value]
        out.setdefault(canonical, [])
        out[canonical].extend(str(v) for v in values if v is not None)
    return out


def _canonicalize_key(key: str) -> str | None:
    if key in ALL_COLUMNS:
        return key
    if key in MACHINE_TO_LABEL:
        return MACHINE_TO_LABEL[key]
    return FIELD_TO_CANONICAL.get(key.strip().lower())
