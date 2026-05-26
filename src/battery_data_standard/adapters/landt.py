"""LANDT cycler adapter."""

from __future__ import annotations

from pathlib import Path

from ..reports import DetectionResult
from .generic import GenericAdapter


class LandtAdapter(GenericAdapter):
    id = "landt"
    display_name = "LANDT"
    adapter_version = "1"
    support_tier = "fixture-backed"
    raw_current_sign = "charge-positive"
    signatures = ("landt", "land", "testtime")
    column_aliases = {
        "Test Time / s": ("TestTime", "Test Time(s)", "Total Time(s)", "Time(s)", "Time(h)", "t"),
        "Step Time / s": ("StepTime", "Step Time(s)", "Step Time"),
        "Voltage / V": ("Voltage/V", "Voltage(V)", "Voltage(V) ", "Voltage", "V"),
        "Current / A": ("Current/A", "Current(A)", "Current(mA)", "Current", "I"),
        "Power / W": ("Power(W)", "Power", "P"),
        "Cycle Count / 1": ("Cycle", "Cycle ID"),
        "Step Count / 1": ("Step", "Step ID"),
        "Charging Capacity / Ah": ("Charge Capacity(Ah)", "Chg Capacity(Ah)"),
        "Discharging Capacity / Ah": ("Discharge Capacity(Ah)", "DChg Capacity(Ah)"),
        "Ambient Temperature / degC": ("Temperature(°C)", "Temperature(C)", "Temp(C)", "TA", "T1"),
    }

    def sniff(self, path: Path, sample: str) -> DetectionResult:
        lower = sample.lower()
        if "testtime" in lower and ("voltage/v" in lower or "voltage(v)" in lower):
            return DetectionResult(self.id, 0.65, "LANDT-style TestTime and voltage/current columns")
        return super().sniff(path, sample)
