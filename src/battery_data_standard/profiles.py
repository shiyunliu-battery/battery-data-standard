"""Profile loading and mapping helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .exceptions import UnsupportedFeatureError, UnsupportedFormatError
from .schema import ALL_COLUMNS, MACHINE_TO_LABEL, canonical_label_for

FIELD_TO_CANONICAL = {
    "test_time": "test_time_s",
    "time": "test_time_s",
    "date_time": "date_time",
    "date_time_iso": "date_time",
    "cycle_index": "cycle_index",
    "cycle": "cycle_index",
    "step_index": "step_index",
    "step": "step_index",
    "data_point": "record_index",
    "record": "record_index",
    "step_time": "step_time_s",
    "voltage": "voltage_v",
    "current": "current_a",
    "temperature": "ambient_temperature_deg_c",
    "internal_resistance": "internal_resistance_ohm",
    "charge_capacity": "charge_capacity_ah",
    "discharge_capacity": "discharge_capacity_ah",
    "charge_energy": "charge_energy_wh",
    "discharge_energy": "discharge_energy_wh",
    "power": "power_w",
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
    alias = canonical_label_for(key)
    if alias is not None:
        return alias
    return FIELD_TO_CANONICAL.get(key.strip().lower())
