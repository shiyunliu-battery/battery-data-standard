"""Maccor cycler adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from ..io import read_table
from .generic import GenericAdapter


class MaccorAdapter(GenericAdapter):
    id = "maccor"
    display_name = "Maccor"
    adapter_version = "1"
    support_tier = "fixture-backed"
    raw_current_sign = "charge-positive"
    signatures = (
        "date of test",
        "maccor",
        "prog time",
        "test (sec)",
        "testtime",
        "cyc#",
        "dpt time",
        "watt-hr",
    )
    column_aliases = {
        "test_time_s": (
            "Prog Time",
            "Test (Sec)",
            "Test(Sec)",
            "Test Time",
            "Test Time (sec)",
            "Test Time (seconds)",
            "Test Time (Hr)",
            "Test Time (h)",
            "TestTime",
            "TestTime(s)",
        ),
        "date_time": ("DPT", "DPt Time", "DPT Time", "Date Time", "Date of Test"),
        "step_time_s": (
            "Step Time",
            "Step (Sec)",
            "Step(Sec)",
            "Step Time (sec)",
            "Step Time (seconds)",
            "StepTime",
            "StepTime(s)",
        ),
        "voltage_v": ("Voltage", "Volts", "Voltage (V)", "Voltage(V)"),
        "current_a": ("Current", "Amps", "Current (A)", "Current(A)", "Current (mA)", "Current(mA)"),
        "cycle_index": ("Cycle", "Cyc#", "Cycle ID", "Cycle P"),
        "step_index": ("Step", "Step ID"),
        "record_index": ("Rec#", "Record", "Record ID"),
        "ambient_temperature_deg_c": ("LogTemp001", "Temperature (°C)", "EVTemp (C)", "Temp 1"),
        "charge_capacity_ah": ("Chg Capacity (Ah)", "Chg Capacity (AHr)", "WF Chg Cap"),
        "discharge_capacity_ah": ("DChg Capacity (Ah)", "DChg Capacity (AHr)", "WF Dis Cap"),
        "charge_energy_wh": ("Chg Energy (Wh)", "Chg Energy (WHr)"),
        "discharge_energy_wh": ("DChg Energy (Wh)", "DChg Energy (WHr)"),
        "power_w": ("Power", "Power(W)"),
        "internal_resistance_ohm": ("ACImp/Ohms", "DCIR/Ohms", "ACImp (Ohms)", "DCIR (Ohms)"),
    }

    def read_raw(self, path: Path, options: dict[str, Any] | None = None) -> pl.DataFrame:
        raw = read_table(path, options=options)
        if _has_aliases(raw, self.column_aliases, ("test_time_s", "voltage_v", "current_a")):
            return raw
        if raw.width < 7:
            return raw

        positional = (
            "Cycle",
            "Step",
            "Test Time (seconds)",
            "Step Time (seconds)",
            "Capacity (mAh)",
            "Current (mA)",
            "Voltage (V)",
            "DPt Time (seconds)",
            "Temperature (Celsius)",
            "EV Temperature (Celsius)",
        )
        rename: dict[str, str] = {}
        for source, target in zip(raw.columns, positional, strict=False):
            if source != target and target not in raw.columns:
                rename[source] = target
        return raw.rename(rename) if rename else raw


def _has_aliases(
    raw: pl.DataFrame,
    aliases: dict[str, tuple[str, ...]],
    labels: tuple[str, ...],
) -> bool:
    slugs = {_slug(col) for col in raw.columns}
    for label in labels:
        candidates = aliases.get(label, ())
        if not any(_slug(candidate) in slugs for candidate in candidates):
            return False
    return True


def _slug(value: str) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())
