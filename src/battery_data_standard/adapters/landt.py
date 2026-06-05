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
    evidence_tier = "public-fixture-backed"
    raw_current_sign = "charge-positive"
    signatures = ("landt", "land", "testtime")
    column_aliases = {
        "test_time_s": ("TestTime", "Test Time(s)", "Total Time(s)", "Time(s)", "Time(h)", "t"),
        "step_time_s": ("StepTime", "Step Time(s)", "Step Time"),
        "voltage_v": ("Voltage/V", "Voltage(V)", "Voltage(V) ", "Voltage", "V"),
        "current_a": ("Current/A", "Current(A)", "Current(mA)", "Current", "I"),
        "power_w": ("Power(W)", "Power", "P"),
        "cycle_index": ("Cycle", "Cycle ID"),
        "step_index": ("Step", "Step ID"),
        "charge_capacity_ah": ("Charge Capacity(Ah)", "Chg Capacity(Ah)"),
        "discharge_capacity_ah": ("Discharge Capacity(Ah)", "DChg Capacity(Ah)"),
        "ambient_temperature_deg_c": ("Temperature(°C)", "Temperature(C)", "Temp(C)", "TA", "T1"),
    }

    def sniff(self, path: Path, sample: str) -> DetectionResult:
        lower = sample.lower()
        if "testtime" in lower and ("voltage/v" in lower or "voltage(v)" in lower):
            return DetectionResult(self.id, 0.65, "LANDT-style TestTime and voltage/current columns")
        return super().sniff(path, sample)
