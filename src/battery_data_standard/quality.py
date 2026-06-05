"""Reusable quality checks for conversion reports and intake audits."""

from __future__ import annotations

import math
from itertools import pairwise
from typing import Any

import polars as pl

from .reports import ColumnProvenance


def quality_checks(
    df: pl.DataFrame,
    *,
    provenance: list[ColumnProvenance] | None = None,
    current_sign: str = "charge-positive",
    current_sign_check: str = "none",
) -> dict[str, Any]:
    """Return conservative quality checks for a normalized time-series frame."""
    if current_sign_check not in {"adjacent", "none"}:
        raise ValueError("current_sign_check must be one of ['adjacent', 'none']")
    checks: dict[str, Any] = {}
    if df.is_empty():
        checks["current_sign_confidence"] = "disabled" if current_sign_check == "none" else "inconclusive"
        checks["current_sign_sanity"] = (
            _disabled_sign_sanity()
            if current_sign_check == "none"
            else {
                "status": "inconclusive",
                "method": "adjacent",
                "reason": "empty dataframe",
            }
        )
        checks["semantic_sources"] = semantic_sources(provenance or [])
        checks["step_cycle_semantics"] = _step_cycle_semantics(df, checks["semantic_sources"])
        return checks
    if "test_time_s" in df.columns:
        times = _float_values(df["test_time_s"])
        finite_times = [value for value in times if value is not None and math.isfinite(value)]
        checks["duplicated_timestamps"] = len(finite_times) - len(set(finite_times))
        checks["non_monotonic_time"] = sum(1 for left, right in pairwise(finite_times) if right <= left)
    if "voltage_v" in df.columns:
        checks["suspicious_flat_voltage"] = _flat_signal(df["voltage_v"])
    if "current_a" in df.columns:
        checks["suspicious_flat_current"] = _flat_signal(df["current_a"])
    if "cycle_index" in df.columns:
        checks["cycle_anomalies"] = _index_anomalies(df["cycle_index"])
    if "step_index" in df.columns:
        checks["step_anomalies"] = _index_anomalies(df["step_index"])

    sign_sanity = (
        _disabled_sign_sanity()
        if current_sign_check == "none"
        else _current_sign_sanity_adjacent(df, current_sign=current_sign)
    )
    checks["current_sign_confidence"] = sign_sanity["confidence"]
    checks["current_sign_sanity"] = sign_sanity
    checks["semantic_sources"] = semantic_sources(provenance or [])
    checks["step_cycle_semantics"] = _step_cycle_semantics(df, checks["semantic_sources"])
    return checks


def semantic_sources(provenance: list[ColumnProvenance]) -> dict[str, dict[str, str | None]]:
    """Describe whether important semantic fields were source-provided or inferred."""
    fields = ("test_time_s", "cycle_index", "step_index")
    by_column = {item.column: item for item in provenance}
    result: dict[str, dict[str, str | None]] = {}
    for field in fields:
        item = by_column.get(field)
        if item is None:
            result[field] = {"origin": "absent", "source": None, "transform": None}
            continue
        transform = item.transform or ""
        if (
            field == "test_time_s"
            and item.source != field
            and any(token in transform.lower() for token in ("derived", "cumulative", "reconstructed"))
        ):
            origin = "inferred"
        else:
            origin = "source"
        result[field] = {"origin": origin, "source": item.source, "transform": item.transform}
    return result


def _disabled_sign_sanity() -> dict[str, Any]:
    return {
        "status": "disabled",
        "method": "none",
        "confidence": "disabled",
        "reason": "current sign sanity check was disabled",
        "evidence": [],
    }


def _current_sign_sanity_adjacent(df: pl.DataFrame, *, current_sign: str) -> dict[str, Any]:
    if current_sign not in {"charge-positive", "discharge-positive"}:
        return {
            "status": "inconclusive",
            "method": "adjacent",
            "confidence": "inconclusive",
            "reason": "current sign was preserved, so expected charge/discharge polarity is unknown",
            "evidence": [],
        }
    if "current_a" not in df.columns or "voltage_v" not in df.columns:
        return {
            "status": "inconclusive",
            "method": "adjacent",
            "confidence": "inconclusive",
            "reason": "current or voltage column is missing",
            "evidence": [],
        }
    current = _float_values(df["current_a"])
    voltage = _float_values(df["voltage_v"])
    directions = [_current_direction(value, current_sign=current_sign) for value in current]
    pair_evidence = _adjacent_voltage_sign_evidence(voltage, directions)
    conflicts = pair_evidence["conflicts"]
    agreements = pair_evidence["agreements"]
    checked_pairs = int(pair_evidence["checked_pairs"])
    conflict_count = int(pair_evidence["conflict_count"])
    agreement_count = int(pair_evidence["agreement_count"])

    if checked_pairs < 3:
        return {
            "status": "inconclusive",
            "method": "adjacent",
            "confidence": "inconclusive",
            "reason": "fewer than three adjacent same-direction current/voltage pairs",
            "evidence": [],
            "checked_pairs": checked_pairs,
        }

    conflict_fraction = conflict_count / checked_pairs if checked_pairs else 0.0
    agreement_fraction = agreement_count / checked_pairs if checked_pairs else 0.0
    if conflict_count and (conflict_fraction >= 0.65):
        confidence = "high" if conflict_fraction >= 0.85 else "medium"
        return {
            "status": "suspicious",
            "method": "adjacent",
            "confidence": confidence,
            "reason": "; ".join(conflicts[:3]),
            "evidence": conflicts,
            "agreements": agreements,
            "checked_pairs": checked_pairs,
            "conflict_pairs": conflict_count,
            "agreement_pairs": agreement_count,
            "conflict_fraction": round(conflict_fraction, 3),
        }
    if agreement_count:
        confidence = "high" if agreement_fraction >= 0.8 else "medium"
        return {
            "status": "ok",
            "method": "adjacent",
            "confidence": confidence,
            "reason": "; ".join(agreements[:3]),
            "evidence": agreements,
            "checked_pairs": checked_pairs,
            "conflict_pairs": conflict_count,
            "agreement_pairs": agreement_count,
            "conflict_fraction": round(conflict_fraction, 3),
        }
    return {
        "status": "inconclusive",
        "method": "adjacent",
        "confidence": "low",
        "reason": "no clear adjacent voltage trend across non-rest current pairs",
        "evidence": [],
        "checked_pairs": checked_pairs,
    }


def _adjacent_voltage_sign_evidence(
    voltage: list[float | None], directions: list[str | None]
) -> dict[str, Any]:
    conflicts: list[str] = []
    agreements: list[str] = []
    checked_pairs = 0
    conflict_count = 0
    agreement_count = 0
    for index in range(len(voltage) - 1):
        direction = directions[index]
        if direction not in {"charge", "discharge"} or directions[index + 1] != direction:
            continue
        left = voltage[index]
        right = voltage[index + 1]
        if left is None or right is None or not math.isfinite(left) or not math.isfinite(right):
            continue
        delta = right - left
        tolerance = max(1e-5, max(abs(left), abs(right)) * 1e-5)
        if abs(delta) <= tolerance:
            continue
        checked_pairs += 1
        if direction == "charge" and delta < 0:
            conflict_count += 1
            if len(conflicts) < 5:
                conflicts.append(
                    f"row {index}->{index + 1}: charge current with voltage decrease {delta:g} V"
                )
        elif direction == "discharge" and delta > 0:
            conflict_count += 1
            if len(conflicts) < 5:
                conflicts.append(
                    f"row {index}->{index + 1}: discharge current with voltage increase {delta:g} V"
                )
        else:
            agreement_count += 1
            if len(agreements) < 5:
                agreements.append(f"row {index}->{index + 1}: {direction} current matches voltage trend")
    return {
        "conflicts": conflicts,
        "agreements": agreements,
        "checked_pairs": checked_pairs,
        "conflict_count": conflict_count,
        "agreement_count": agreement_count,
    }


def _step_cycle_semantics(df: pl.DataFrame, sources: dict[str, dict[str, str | None]]) -> dict[str, Any]:
    inferred = sorted(field for field, item in sources.items() if item.get("origin") == "inferred")
    result: dict[str, Any] = {
        "repeated_step_segments": 0,
        "step_transition_discontinuities": 0,
        "examples": [],
        "inferred_fields": inferred,
        "semantic_sources": sources,
    }
    if df.is_empty() or "step_index" not in df.columns:
        return result

    steps = [_stable_value(value) for value in df["step_index"].to_list()]
    cycles = (
        [_stable_value(value) for value in df["cycle_index"].to_list()]
        if "cycle_index" in df.columns
        else [None] * len(steps)
    )
    result.update(_repeated_step_segments(cycles, steps))
    result.update(_step_transition_discontinuities(df, cycles, steps))
    return result


def _repeated_step_segments(cycles: list[Any], steps: list[Any]) -> dict[str, Any]:
    examples: list[dict[str, Any]] = []
    repeated = 0
    for cycle in _ordered_unique(cycles):
        indices = [index for index, value in enumerate(cycles) if value == cycle]
        seen: set[Any] = set()
        last_step: Any = object()
        for index in indices:
            step = steps[index]
            if step is None:
                continue
            if step != last_step:
                if step in seen:
                    repeated += 1
                    if len(examples) < 5:
                        examples.append({"cycle": cycle, "step": step, "row": index})
                seen.add(step)
                last_step = step
    return {"repeated_step_segments": repeated, "repeated_step_examples": examples}


def _step_transition_discontinuities(df: pl.DataFrame, cycles: list[Any], steps: list[Any]) -> dict[str, Any]:
    examples: list[dict[str, Any]] = []
    transitions = 0
    test_time = _float_values(df["test_time_s"]) if "test_time_s" in df.columns else [None] * len(steps)
    step_time = _float_values(df["step_time_s"]) if "step_time_s" in df.columns else [None] * len(steps)
    for index in range(1, len(steps)):
        if steps[index] is None or steps[index - 1] is None or steps[index] == steps[index - 1]:
            continue
        reason = None
        left_test = test_time[index - 1]
        right_test = test_time[index]
        if left_test is not None and right_test is not None and right_test <= left_test:
            reason = "test_time_s did not increase at step transition"
        left_step = step_time[index - 1]
        right_step = step_time[index]
        if (
            reason is None
            and left_step is not None
            and right_step is not None
            and right_step > left_step + 1e-9
            and right_step > 1e-9
        ):
            reason = "step_time_s did not reset at step transition"
        if reason is not None:
            transitions += 1
            if len(examples) < 5:
                examples.append(
                    {
                        "row": index,
                        "cycle": cycles[index],
                        "previous_step": steps[index - 1],
                        "step": steps[index],
                        "reason": reason,
                    }
                )
    return {
        "step_transition_discontinuities": transitions,
        "step_transition_examples": examples,
    }


def _current_direction(value: float | None, *, current_sign: str) -> str | None:
    if value is None or not math.isfinite(value) or abs(value) <= 1e-12:
        return None
    if current_sign == "charge-positive":
        return "charge" if value > 0 else "discharge"
    return "discharge" if value > 0 else "charge"


def _flat_signal(series: pl.Series) -> dict[str, Any]:
    values = [value for value in _float_values(series) if value is not None and math.isfinite(value)]
    if len(values) < 10:
        return {"flag": False, "reason": "fewer than 10 numeric points"}
    span = max(values) - min(values)
    mean_abs = sum(abs(value) for value in values) / len(values)
    tolerance = max(1e-9, mean_abs * 1e-6)
    return {"flag": span <= tolerance, "span": span, "points": len(values)}


def _index_anomalies(series: pl.Series) -> dict[str, int]:
    values = [value for value in _float_values(series) if value is not None and math.isfinite(value)]
    decreases = sum(1 for left, right in pairwise(values) if right < left)
    negative = sum(1 for value in values if value < 0)
    return {"decreases": decreases, "negative_values": negative}


def _float_values(series: pl.Series) -> list[float | None]:
    values: list[float | None] = []
    for value in series.to_list():
        if value is None:
            values.append(None)
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            values.append(None)
            continue
        values.append(number)
    return values


def _stable_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isfinite(number) and number.is_integer():
        return int(number)
    return number if math.isfinite(number) else None


def _ordered_unique(values: list[Any]) -> list[Any]:
    unique: list[Any] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique
