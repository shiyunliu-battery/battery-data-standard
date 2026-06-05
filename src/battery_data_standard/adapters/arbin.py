"""Arbin cycler adapter."""

from __future__ import annotations

from .generic import GenericAdapter


class ArbinAdapter(GenericAdapter):
    id = "arbin"
    display_name = "Arbin"
    adapter_version = "1"
    support_tier = "fixture-backed"
    evidence_tier = "public-fixture-backed"
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
        "test_time_s": (
            "Test_Time",
            "Test Time (s)",
            "Test Time (min)",
            "Test Time (h)",
            "Test Time",
            "Test_Time(s)",
            "TestTime(s)",
        ),
        "date_time": ("DateTime", "Date Time", "Date_Time", "Date_Time                    "),
        "step_time_s": (
            "Step_Time",
            "Step Time (s)",
            "Step Time (min)",
            "Step Time (h)",
            "Step_Time(s)",
            "StepTime(s)",
        ),
        "cycle_index": ("Cycle_Index", "Cycle Index"),
        "step_index": ("Step_Index", "Step Index"),
        "record_index": ("Data_Point", "Data Point", "DataPoint"),
        "current_a": ("Current", "Current (A)", "Current(A)", "Current_mA", "Current (mA)"),
        "voltage_v": ("Voltage", "Voltage (V)", "Voltage(V)"),
        "charge_capacity_ah": ("Charge_Capacity", "Charge Capacity (Ah)", "Charge_Capacity(Ah)"),
        "discharge_capacity_ah": (
            "Discharge_Capacity",
            "Discharge Capacity (Ah)",
            "Discharge_Capacity(Ah)",
        ),
        "charge_energy_wh": ("Charge_Energy", "Charge Energy (Wh)", "Charge_Energy(Wh)"),
        "discharge_energy_wh": ("Discharge_Energy", "Discharge Energy (Wh)", "Discharge_Energy(Wh)"),
        "power_w": ("Power", "Power (W)", "Power(W)"),
        "internal_resistance_ohm": (
            "Internal_Resistance",
            "Internal Resistance",
            "Internal Resistance (Ohm)",
            "ACR (Ohm)",
            "IR (Ohms)",
        ),
        "ambient_temperature_deg_c": (
            "Temperature",
            "Aux_Temperature_1 (C)",
            "Aux_Temperature_1(C)",
            "Aux_Temperature(C)_1",
            "Aux_Temperature(degC)_1",
            "Aux_Temperature(°C)_1",
            "Aux_Temperature(Â°C)_1",
            "Aux_Temperature(Ąć)_1",
            "Aux_Temperature(¡æ)_1",
            "Aux_Temperature_2 (C)",
            "Aux_Temperature_2(C)",
        ),
    }
