"""Novonix cycler adapter."""

from __future__ import annotations

from .generic import GenericAdapter


class NovonixAdapter(GenericAdapter):
    id = "novonix"
    display_name = "Novonix"
    adapter_version = "1"
    support_tier = "fixture-backed"
    evidence_tier = "public-fixture-backed"
    raw_current_sign = "charge-positive"
    signatures = ("novonix", "novonix hpc data file", "[summary]", "cycle number", "step time", "run time")
    column_aliases = {
        "test_time_s": ("Test Time (s)", "Test Time", "Run Time (h)", "Run Time(h)", "Run Time"),
        "step_time_s": ("Step Time (s)", "Step Time", "Step Time (h)", "Step Time(h)"),
        "voltage_v": ("Potential (V)", "Voltage (V)"),
        "current_a": ("Current (A)",),
        "cycle_index": ("Cycle Number", "Cycle"),
        "step_index": ("Step Number", "Step"),
        "record_index": ("Step position", "Step Position"),
        "date_time": ("Date and Time",),
        "ambient_temperature_deg_c": ("Temperature (°C)", "Circuit Temperature (°C)"),
        "charge_capacity_ah": ("Capacity (Ah)",),
        "charge_energy_wh": ("Energy (Wh)",),
        "power_w": ("Power(W)", "Power (W)"),
    }
