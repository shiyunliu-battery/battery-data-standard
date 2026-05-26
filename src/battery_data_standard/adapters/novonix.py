"""Novonix cycler adapter."""

from __future__ import annotations

from .generic import GenericAdapter


class NovonixAdapter(GenericAdapter):
    id = "novonix"
    display_name = "Novonix"
    adapter_version = "1"
    support_tier = "fixture-backed"
    raw_current_sign = "charge-positive"
    signatures = ("novonix", "novonix hpc data file", "[summary]", "cycle number", "step time", "run time")
    column_aliases = {
        "Test Time / s": ("Test Time (s)", "Test Time", "Run Time (h)", "Run Time(h)", "Run Time"),
        "Step Time / s": ("Step Time (s)", "Step Time", "Step Time (h)", "Step Time(h)"),
        "Voltage / V": ("Potential (V)", "Voltage (V)"),
        "Current / A": ("Current (A)",),
        "Cycle Count / 1": ("Cycle Number", "Cycle"),
        "Step Count / 1": ("Step Number", "Step"),
        "Step Index / 1": ("Step position", "Step Position"),
        "Date Time ISO": ("Date and Time",),
        "Ambient Temperature / degC": ("Temperature (°C)", "Circuit Temperature (°C)"),
        "Charging Capacity / Ah": ("Capacity (Ah)",),
        "Charging Energy / Wh": ("Energy (Wh)",),
        "Power / W": ("Power(W)", "Power (W)"),
    }
