"""Arbin cycler adapter."""

from __future__ import annotations

from .generic import GenericAdapter


class ArbinAdapter(GenericAdapter):
    id = "arbin"
    display_name = "Arbin"
    adapter_version = "1"
    support_tier = "fixture-backed"
    raw_current_sign = "charge-positive"
    signatures = (
        "arbin",
        "cycle index",
        "cycle_index",
        "step index",
        "step_index",
        "test time",
        "test_time",
        "data point",
        "data_point",
        "date_time",
        "charge_capacity",
        "discharge_capacity",
        "statisticbystep",
        "statisticbycycle",
    )
    column_aliases = {
        "Test Time / s": (
            "Test_Time",
            "Test Time (s)",
            "Test Time (min)",
            "Test Time (h)",
            "Test Time",
            "Test_Time(s)",
            "TestTime(s)",
        ),
        "Date Time ISO": ("DateTime", "Date Time", "Date_Time", "Date_Time                    "),
        "Step Time / s": (
            "Step_Time",
            "Step Time (s)",
            "Step Time (min)",
            "Step Time (h)",
            "Step_Time(s)",
            "StepTime(s)",
        ),
        "Cycle Count / 1": ("Cycle_Index", "Cycle Index"),
        "Step Count / 1": ("Step_Index", "Step Index"),
        "Step Index / 1": ("Data_Point", "Data Point", "DataPoint"),
        "Current / A": ("Current", "Current (A)", "Current(A)", "Current_mA", "Current (mA)"),
        "Voltage / V": ("Voltage", "Voltage (V)", "Voltage(V)"),
        "Charging Capacity / Ah": ("Charge_Capacity", "Charge Capacity (Ah)", "Charge_Capacity(Ah)"),
        "Discharging Capacity / Ah": (
            "Discharge_Capacity",
            "Discharge Capacity (Ah)",
            "Discharge_Capacity(Ah)",
        ),
        "Charging Energy / Wh": ("Charge_Energy", "Charge Energy (Wh)", "Charge_Energy(Wh)"),
        "Discharging Energy / Wh": ("Discharge_Energy", "Discharge Energy (Wh)", "Discharge_Energy(Wh)"),
        "Power / W": ("Power", "Power (W)", "Power(W)"),
        "Internal Resistance / ohm": (
            "Internal_Resistance",
            "Internal Resistance",
            "Internal Resistance (Ohm)",
            "ACR (Ohm)",
            "IR (Ohms)",
        ),
        "Ambient Temperature / degC": (
            "Temperature",
            "Aux_Temperature_1 (C)",
            "Aux_Temperature_1(C)",
            "Aux_Temperature_2 (C)",
            "Aux_Temperature_2(C)",
        ),
    }
