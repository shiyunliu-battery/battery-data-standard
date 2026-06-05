"""PEC CSV adapter."""

from __future__ import annotations

from .generic import GenericAdapter


class PecAdapter(GenericAdapter):
    id = "pec"
    display_name = "PEC"
    adapter_version = "1"
    support_tier = "fixture-backed"
    evidence_tier = "public-fixture-backed"
    raw_current_sign = "charge-positive"
    extensions = (".csv", ".txt")
    signatures = (
        "total time",
        "step time",
        "testregime",
        "position_start_time",
        "charge_capacity_mah",
        "discharge_capacity_mah",
    )
    column_aliases = {
        "date_time": ("Real_Time", "Real Time"),
        "test_time_s": (
            "Total_Time_Seconds",
            "Total Time (Seconds)",
            "Total_Time_Decimal_Hours",
            "Total Time (Decimal Hours)",
            "Total Time (Hours in hh:mm:ss.xxx)",
        ),
        "step_time_s": (
            "Step_Time_Seconds",
            "Step Time (Seconds)",
            "Step_Time_Decimal_Hours",
            "Step Time (Decimal Hours)",
            "Step Time (Hours in hh:mm:ss.xxx)",
        ),
        "voltage_v": ("Voltage_mV", "Voltage_V", "Voltage (mV)", "Voltage (V)"),
        "current_a": ("Current_mA", "Current_A", "Current (mA)", "Current (A)"),
        "cycle_index": ("Cycle",),
        "step_index": ("Step",),
        "charge_capacity_ah": ("Charge_Capacity_mAh", "Charge Capacity (mAh)"),
        "discharge_capacity_ah": ("Discharge_Capacity_mAh", "Discharge Capacity (mAh)"),
        "charge_energy_wh": ("Charge_Capacity_mWh", "Charge Energy (mWh)"),
        "discharge_energy_wh": ("Discharge_Capacity_mWh", "Discharge Energy (mWh)"),
        "internal_resistance_ohm": ("Internal_Resistance_1_mOhm", "Internal Resistance 1 (mOhm)"),
    }
